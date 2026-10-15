"""
Transform Stage for AQI India ETL Pipeline.

Normalizes raw heterogeneous air quality API responses into strongly-typed,
validated observation models.

Key Principles:
1. Strict Validation: Invalid timestamps, negative pollutant readings, or out-of-range
   anomalies are routed to Quarantine with explicit rejection reasons.
2. No Silent Imputation: Missing values remain None (SQL NULL); they are NEVER replaced with 0.
3. Separation of Concerns: Provider-calculated AQI is stored explicitly as `provider_aqi`
   and categorized using standard US EPA AQI categories. Local derived metrics are never conflated.
4. Timezone Precision: Local Indian Standard Time (IST, UTC+05:30) timestamps are parsed
   and normalized into consistent ISO-8601 UTC strings for deterministic indexing.
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from aqi_pipeline.config import PipelineConfig, POLLUTANT_VALIDATION_BOUNDS, DEFAULT_INDIAN_CITIES
from aqi_pipeline.logging_config import setup_logger

# Fixed IST timezone offset (+05:30)
IST_TZ = timezone(timedelta(hours=5, minutes=30))


@dataclass
class ObservationRecord:
    """Clean, validated observation ready for analytical storage."""

    city: str
    state: Optional[str]
    zone: Optional[str]
    latitude: float
    longitude: float
    timestamp_local: str
    timestamp_utc: str
    pm2_5: Optional[float]
    pm10: Optional[float]
    carbon_monoxide: Optional[float]
    nitrogen_dioxide: Optional[float]
    sulphur_dioxide: Optional[float]
    ozone: Optional[float]
    provider_aqi: Optional[float]
    aqi_category: str
    data_source: str
    extracted_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuarantineRecord:
    """Rejected observation quarantined for audit and data quality tracking."""

    city: str
    timestamp_local: Optional[str]
    rejection_reason: str
    raw_payload_snippet: str
    quarantined_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TransformationResult:
    """Output container for accepted and quarantined observations."""

    accepted: List[ObservationRecord]
    quarantined: List[QuarantineRecord]


class AQITransformer:
    """Transforms and validates raw air quality observation payloads."""

    def __init__(self, config: PipelineConfig, logger: Optional[logging.Logger] = None) -> None:
        self.config = config
        self.logger = logger or setup_logger("aqi_pipeline.transform")

    @staticmethod
    def parse_timestamp(raw_time: Any) -> Tuple[str, str]:
        """
        Parses raw timestamp string and returns (local_iso, utc_iso).
        Expected format from Open-Meteo is ISO 'YYYY-MM-DDTHH:MM' in Asia/Kolkata.
        """
        if not raw_time or not isinstance(raw_time, str):
            raise ValueError(f"Missing or invalid timestamp type: {raw_time}")

        # Remove trailing Z if present and parse
        clean_time = raw_time.strip().rstrip("Z")
        try:
            # Handle YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS
            dt = datetime.fromisoformat(clean_time)
        except Exception as exc:
            raise ValueError(f"Cannot parse timestamp '{raw_time}': {exc}") from exc

        # Attach IST timezone if naive
        if dt.tzinfo is None:
            dt_local = dt.replace(tzinfo=IST_TZ)
        else:
            dt_local = dt.astimezone(IST_TZ)

        # Convert to UTC
        dt_utc = dt_local.astimezone(timezone.utc)

        return dt_local.isoformat(), dt_utc.isoformat()

    @staticmethod
    def validate_pollutant(name: str, raw_value: Any) -> Tuple[bool, Optional[float], Optional[str]]:
        """
        Validates individual pollutant reading against physical boundary rules.
        Missing (None) is allowed and returned as None.
        """
        if raw_value is None:
            return True, None, None

        try:
            val = float(raw_value)
        except (ValueError, TypeError):
            return False, None, f"{name} is not numeric ({raw_value})"

        bounds = POLLUTANT_VALIDATION_BOUNDS.get(name, {"min": 0.0, "max": 100000.0})
        if val < bounds["min"]:
            return False, None, f"{name} ({val}) is negative, below minimum {bounds['min']}"
        if val > bounds["max"]:
            return False, None, f"{name} ({val}) exceeds plausible threshold {bounds['max']}"

        return True, round(val, 2), None

    @staticmethod
    def get_us_aqi_category(aqi: Optional[float]) -> str:
        """
        Determines air quality advisory category based on US EPA AQI standard.
        Note: Clearly distinguished from Indian CPCB National AQI.
        """
        if aqi is None:
            return "Unavailable"
        if aqi <= 50:
            return "Good"
        if aqi <= 100:
            return "Moderate"
        if aqi <= 150:
            return "Unhealthy for Sensitive Groups"
        if aqi <= 200:
            return "Unhealthy"
        if aqi <= 300:
            return "Very Unhealthy"
        return "Hazardous"

    def transform_single(
        self, raw_payload: Dict[str, Any]
    ) -> Tuple[Optional[ObservationRecord], Optional[QuarantineRecord]]:
        """
        Transform a single city payload into an ObservationRecord or QuarantineRecord.
        """
        metadata = raw_payload.get("_metadata", {})
        city = metadata.get("city") or raw_payload.get("city") or "Unknown"
        extracted_at = metadata.get("extracted_at_utc", datetime.now(timezone.utc).isoformat())
        source = metadata.get("source", "open-meteo")

        current = raw_payload.get("current")
        if not current or not isinstance(current, dict):
            # Try top level if nested 'current' doesn't exist
            current = raw_payload

        # 1. Validate & Parse Timestamp
        raw_time = current.get("time")
        try:
            time_local, time_utc = self.parse_timestamp(raw_time)
        except ValueError as err:
            return None, QuarantineRecord(
                city=city,
                timestamp_local=str(raw_time),
                rejection_reason=f"Timestamp validation failed: {err}",
                raw_payload_snippet=json.dumps(current)[:300],
                quarantined_at_utc=datetime.now(timezone.utc).isoformat(),
            )

        # 2. Extract Coordinates and Geographic Context
        city_meta = DEFAULT_INDIAN_CITIES.get(city, {})
        lat = float(raw_payload.get("latitude", city_meta.get("latitude", 0.0)))
        lon = float(raw_payload.get("longitude", city_meta.get("longitude", 0.0)))
        state = city_meta.get("state")
        zone = city_meta.get("zone")

        # 3. Validate Pollutant Values (Strict validation without zero-imputation)
        pollutant_fields = [
            "pm2_5",
            "pm10",
            "carbon_monoxide",
            "nitrogen_dioxide",
            "sulphur_dioxide",
            "ozone",
            "us_aqi",
        ]
        cleaned_values: Dict[str, Optional[float]] = {}

        for field_name in pollutant_fields:
            raw_val = current.get(field_name)
            is_valid, val, err_reason = self.validate_pollutant(field_name, raw_val)
            if not is_valid:
                return None, QuarantineRecord(
                    city=city,
                    timestamp_local=time_local,
                    rejection_reason=f"Data quality violation: {err_reason}",
                    raw_payload_snippet=json.dumps(current)[:300],
                    quarantined_at_utc=datetime.now(timezone.utc).isoformat(),
                )
            cleaned_values[field_name] = val

        # Check that at least one major pollutant is present
        core_pollutants = [cleaned_values["pm2_5"], cleaned_values["pm10"], cleaned_values["us_aqi"]]
        if all(v is None for v in core_pollutants):
            return None, QuarantineRecord(
                city=city,
                timestamp_local=time_local,
                rejection_reason="Empty observation: all core pollutants (PM2.5, PM10, AQI) are missing",
                raw_payload_snippet=json.dumps(current)[:300],
                quarantined_at_utc=datetime.now(timezone.utc).isoformat(),
            )

        provider_aqi = cleaned_values["us_aqi"]
        category = self.get_us_aqi_category(provider_aqi)

        record = ObservationRecord(
            city=city,
            state=state,
            zone=zone,
            latitude=lat,
            longitude=lon,
            timestamp_local=time_local,
            timestamp_utc=time_utc,
            pm2_5=cleaned_values["pm2_5"],
            pm10=cleaned_values["pm10"],
            carbon_monoxide=cleaned_values["carbon_monoxide"],
            nitrogen_dioxide=cleaned_values["nitrogen_dioxide"],
            sulphur_dioxide=cleaned_values["sulphur_dioxide"],
            ozone=cleaned_values["ozone"],
            provider_aqi=provider_aqi,
            aqi_category=category,
            data_source=source,
            extracted_at_utc=extracted_at,
        )
        return record, None

    def transform_all(self, raw_payloads: List[Dict[str, Any]]) -> TransformationResult:
        """
        Processes a list of raw city payloads into accepted and quarantined records.
        """
        accepted: List[ObservationRecord] = []
        quarantined: List[QuarantineRecord] = []

        for payload in raw_payloads:
            rec, quar = self.transform_single(payload)
            if rec:
                accepted.append(rec)
            if quar:
                self.logger.warning(
                    f"Quarantined observation for {quar.city}: {quar.rejection_reason}"
                )
                quarantined.append(quar)

        self.logger.info(
            f"Transformation complete. Accepted: {len(accepted)}, Quarantined: {len(quarantined)}"
        )
        return TransformationResult(accepted=accepted, quarantined=quarantined)
