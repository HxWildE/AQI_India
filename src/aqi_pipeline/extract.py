"""
Extract Stage for AQI India ETL Pipeline.

Handles resilient HTTP data extraction from the air quality provider with:
- Explicit timeouts on every network call
- Bounded exponential backoff retries for transient errors (5xx, timeouts, connection drops)
- Rate-limiting awareness and handling of HTTP 429 (Too Many Requests) with Retry-After header parsing
- Immediate failure without retry on permanent client errors (400, 401, 403, 404)
- Offline deterministic fixture mode for zero-dependency local runs and testing
- Extraction metadata tagging (UTC timestamp, data source, execution mode)
"""

from __future__ import annotations
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from aqi_pipeline.config import PipelineConfig, DEFAULT_INDIAN_CITIES
from aqi_pipeline.logging_config import setup_logger


class ExtractionError(Exception):
    """Raised when extraction fails terminally for a city."""
    pass


class AQIExtractor:
    """Resilient extractor for air quality observation data."""

    def __init__(self, config: PipelineConfig, logger: Optional[logging.Logger] = None) -> None:
        self.config = config
        self.logger = logger or setup_logger("aqi_pipeline.extract")
        self.session = requests.Session()

    def _calc_backoff(self, attempt: int) -> float:
        """Calculates exponential backoff delay for a given attempt."""
        return float(self.config.backoff_factor * (2 ** (attempt - 1)))

    def fetch_city_data(self, city_name: str, latitude: float, longitude: float) -> Dict[str, Any]:
        """
        Fetch real-time air quality metrics for a single Indian city with bounded retries.

        Retries on transient errors (timeouts, network resets, 5xx server errors, 429 rate limits).
        Does NOT retry on permanent client errors (400, 401, 403, 404).
        """
        params: Dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,us_aqi",
            "timezone": "Asia/Kolkata",
        }
        if self.config.api_key:
            params["apikey"] = self.config.api_key

        last_exception: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                self.logger.debug(f"Fetching AQI for {city_name} (attempt {attempt}/{self.config.max_retries})")
                response = self.session.get(
                    self.config.api_base_url,
                    params=params,
                    timeout=self.config.timeout_seconds,
                )

                if response.status_code == 429:
                    hdr = response.headers.get("Retry-After")
                    sleep_time = float(hdr) if hdr and hdr.isdigit() else self._calc_backoff(attempt)
                    self.logger.warning(f"Rate limited (429) for {city_name}. Backing off {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                    continue

                if 400 <= response.status_code < 500:
                    err_msg = f"Permanent client error HTTP {response.status_code} for {city_name}: {response.text[:200]}"
                    self.logger.error(err_msg)
                    raise ExtractionError(err_msg)

                if 500 <= response.status_code < 600:
                    self.logger.warning(f"Server error HTTP {response.status_code} for {city_name} on attempt {attempt}")
                    if attempt < self.config.max_retries:
                        time.sleep(self._calc_backoff(attempt))
                        continue
                    response.raise_for_status()

                response.raise_for_status()
                payload = response.json()
                payload["_metadata"] = {
                    "city": city_name,
                    "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source": "open-meteo-air-quality-api",
                    "execution_mode": "live",
                }
                self.logger.info(f"Successfully fetched live data for {city_name}")
                return payload

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_exception = exc
                self.logger.warning(f"Network error ({type(exc).__name__}) for {city_name} (attempt {attempt}/{self.config.max_retries})")
                if attempt < self.config.max_retries:
                    time.sleep(self._calc_backoff(attempt))
                else:
                    break
            except requests.exceptions.JSONDecodeError as exc:
                self.logger.error(f"Invalid JSON payload received for {city_name}: {exc}")
                raise ExtractionError(f"Malformed JSON from API for {city_name}") from exc

        err_detail = f"Failed to fetch {city_name} after {self.config.max_retries} attempts: {last_exception}"
        self.logger.error(err_detail)
        raise ExtractionError(err_detail)

    def extract_from_fixtures(self, fixture_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """
        Load sanitized historical or offline observations from local JSON fixtures.
        Allows full end-to-end pipeline execution and testing without network or API quotas.
        """
        path = fixture_path or self.config.fixture_path
        if not path.exists():
            raise FileNotFoundError(f"Fixture file not found at {path}")

        self.logger.info(f"Loading fixture data from {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        records: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            # Format: {"CityName": {payload}}
            for city_name, payload in data.items():
                p = dict(payload)
                p["_metadata"] = {
                    "city": city_name,
                    "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source": "sanitized_offline_fixture",
                    "execution_mode": "fixture",
                }
                records.append(p)
        elif isinstance(data, list):
            for item in data:
                p = dict(item)
                p["_metadata"] = {
                    "city": p.get("city", "Unknown"),
                    "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source": "sanitized_offline_fixture",
                    "execution_mode": "fixture",
                }
                records.append(p)

        self.logger.info(f"Loaded {len(records)} city fixture records")
        return records

    def extract_all(self, cities: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Extract observations for all configured cities according to execution mode.
        """
        if self.config.execution_mode == "fixture":
            return self.extract_from_fixtures()

        target_cities = cities or self.config.cities
        results: List[Dict[str, Any]] = []
        errors: List[str] = []

        for city_name, info in target_cities.items():
            try:
                lat = info["latitude"]
                lon = info["longitude"]
                payload = self.fetch_city_data(city_name, lat, lon)
                results.append(payload)
                # Polite pacing between sequential requests
                if self.config.rate_limit_delay_seconds > 0:
                    time.sleep(self.config.rate_limit_delay_seconds)
            except Exception as exc:
                self.logger.error(f"Skipping {city_name} due to extraction failure: {exc}")
                errors.append(f"{city_name}: {exc}")

        self.logger.info(
            f"Extraction completed. Succeeded: {len(results)}/{len(target_cities)}, Failed: {len(errors)}"
        )
        return results
