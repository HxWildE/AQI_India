"""
Unit Tests for Transform Stage.

Verifies:
- Accurate schema normalization and dataclass mapping
- Timezone handling: parses IST (+05:30) and produces canonical UTC
- Preservation of missing measurements as None (never zero-imputed)
- Strict validation rules: negative values, out-of-range anomalies, and corrupt timestamps
- Segregation of rejected records into QuarantineRecord objects
- US EPA AQI category classification
"""

import pytest
from aqi_pipeline.transform import AQITransformer, ObservationRecord, QuarantineRecord


def test_transform_valid_observation(test_config, sample_live_response_payload):
    """Verifies that a valid payload transforms into an ObservationRecord."""
    sample_live_response_payload["_metadata"] = {
        "city": "New Delhi",
        "extracted_at_utc": "2026-10-15T18:00:00Z",
        "source": "open-meteo",
    }
    transformer = AQITransformer(test_config)
    record, quarantine = transformer.transform_single(sample_live_response_payload)

    assert quarantine is None
    assert isinstance(record, ObservationRecord)
    assert record.city == "New Delhi"
    assert record.state == "Delhi"
    assert record.zone == "North"
    assert record.pm2_5 == 95.7
    assert record.pm10 == 106.2
    assert record.provider_aqi == 158
    assert record.aqi_category == "Unhealthy"
    assert record.timestamp_local.endswith("+05:30")
    assert record.timestamp_utc.endswith("+00:00")


def test_timestamp_parsing_ist_and_utc():
    """Verifies timestamp parser calculates correct local IST and UTC representation."""
    local_iso, utc_iso = AQITransformer.parse_timestamp("2026-10-15T22:30")
    assert local_iso == "2026-10-15T22:30:00+05:30"
    # 22:30 IST is 17:00 UTC
    assert utc_iso == "2026-10-15T17:00:00+00:00"


def test_missing_values_preserved_as_none(test_config):
    """
    CRITICAL REQUIREMENT: Missing measurements must NOT be silently replaced with 0.
    They must remain None (SQL NULL).
    """
    payload = {
        "_metadata": {"city": "Mumbai"},
        "latitude": 19.0760,
        "longitude": 72.8777,
        "current": {
            "time": "2026-10-15T12:00",
            "pm2_5": 35.0,
            "pm10": None,  # Explicitly missing
            "carbon_monoxide": None,  # Missing
            "nitrogen_dioxide": 20.0,
            "sulphur_dioxide": None,
            "ozone": None,
            "us_aqi": 75,
        },
    }
    transformer = AQITransformer(test_config)
    record, quarantine = transformer.transform_single(payload)

    assert quarantine is None
    assert record is not None
    assert record.pm2_5 == 35.0
    assert record.pm10 is None
    assert record.carbon_monoxide is None
    assert record.sulphur_dioxide is None


def test_negative_pollutant_quarantined(test_config):
    """Negative pollutant values represent sensor errors and must be quarantined."""
    payload = {
        "_metadata": {"city": "Bengaluru"},
        "latitude": 12.9716,
        "longitude": 77.5946,
        "current": {
            "time": "2026-10-15T12:00",
            "pm2_5": -12.5,  # Invalid negative reading
            "pm10": 45.0,
            "us_aqi": 50,
        },
    }
    transformer = AQITransformer(test_config)
    record, quarantine = transformer.transform_single(payload)

    assert record is None
    assert isinstance(quarantine, QuarantineRecord)
    assert quarantine.city == "Bengaluru"
    assert "is negative" in quarantine.rejection_reason


def test_out_of_range_pollutant_quarantined(test_config):
    """Unphysically high values must be quarantined."""
    payload = {
        "_metadata": {"city": "Kolkata"},
        "latitude": 22.5726,
        "longitude": 88.3639,
        "current": {
            "time": "2026-10-15T12:00",
            "pm2_5": 50000.0,  # Exceeds max threshold 1000 µg/m³
            "pm10": 80.0,
            "us_aqi": 200,
        },
    }
    transformer = AQITransformer(test_config)
    record, quarantine = transformer.transform_single(payload)

    assert record is None
    assert isinstance(quarantine, QuarantineRecord)
    assert "exceeds plausible threshold" in quarantine.rejection_reason


def test_malformed_timestamp_quarantined(test_config):
    """Unparseable timestamps must be caught and quarantined."""
    payload = {
        "_metadata": {"city": "Hyderabad"},
        "latitude": 17.3850,
        "longitude": 78.4867,
        "current": {
            "time": "invalid-datetime-string",
            "pm2_5": 40.0,
            "pm10": 70.0,
            "us_aqi": 80,
        },
    }
    transformer = AQITransformer(test_config)
    record, quarantine = transformer.transform_single(payload)

    assert record is None
    assert isinstance(quarantine, QuarantineRecord)
    assert "Timestamp validation failed" in quarantine.rejection_reason


def test_empty_core_pollutants_quarantined(test_config):
    """Payloads lacking all core air quality metrics must be quarantined."""
    payload = {
        "_metadata": {"city": "Chennai"},
        "latitude": 13.0827,
        "longitude": 80.2707,
        "current": {
            "time": "2026-10-15T12:00",
            "pm2_5": None,
            "pm10": None,
            "us_aqi": None,
        },
    }
    transformer = AQITransformer(test_config)
    record, quarantine = transformer.transform_single(payload)

    assert record is None
    assert isinstance(quarantine, QuarantineRecord)
    assert "Empty observation" in quarantine.rejection_reason


def test_us_aqi_category_mapping():
    """Verifies US EPA AQI category break points."""
    assert AQITransformer.get_us_aqi_category(25) == "Good"
    assert AQITransformer.get_us_aqi_category(50) == "Good"
    assert AQITransformer.get_us_aqi_category(75) == "Moderate"
    assert AQITransformer.get_us_aqi_category(100) == "Moderate"
    assert AQITransformer.get_us_aqi_category(125) == "Unhealthy for Sensitive Groups"
    assert AQITransformer.get_us_aqi_category(175) == "Unhealthy"
    assert AQITransformer.get_us_aqi_category(250) == "Very Unhealthy"
    assert AQITransformer.get_us_aqi_category(350) == "Hazardous"
    assert AQITransformer.get_us_aqi_category(None) == "Unavailable"
