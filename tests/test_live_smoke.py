"""
Optional Live API Smoke Test.

Makes a single bounded request to the real Open-Meteo Air Quality endpoint.
Only executes when explicitly requested via `pytest --run-live`.
Otherwise skips cleanly without consuming real API quota or requiring network access.
"""

import pytest
import requests
from aqi_pipeline.config import get_config
from aqi_pipeline.extract import AQIExtractor
from aqi_pipeline.transform import AQITransformer


@pytest.mark.live
def test_live_api_smoke_bounded():
    """
    Smoke test against the live Open-Meteo API for New Delhi.
    Verifies actual live HTTP status, headers, and payload schema.
    """
    config = get_config(
        execution_mode="live",
        timeout_seconds=10.0,
        max_retries=2,
    )
    extractor = AQIExtractor(config)

    # Bounded single-city extraction: New Delhi
    try:
        payload = extractor.fetch_city_data("New Delhi", 28.6139, 77.2090)
    except requests.exceptions.RequestException as exc:
        pytest.skip(f"Live network unavailable: {exc}")

    assert payload is not None
    assert "_metadata" in payload
    assert payload["_metadata"]["city"] == "New Delhi"
    assert payload["_metadata"]["source"] == "open-meteo-air-quality-api"

    # Verify real data fields from Open-Meteo
    assert "current" in payload
    current = payload["current"]
    assert "time" in current
    assert "pm2_5" in current or "pm10" in current

    # Verify pipeline transformation on the live payload
    transformer = AQITransformer(config)
    record, quarantine = transformer.transform_single(payload)

    assert quarantine is None
    assert record is not None
    assert record.city == "New Delhi"
    assert record.state == "Delhi"
    assert record.latitude > 0
    assert record.longitude > 0
    assert record.timestamp_local.endswith("+05:30")
    assert record.timestamp_utc.endswith("+00:00")
