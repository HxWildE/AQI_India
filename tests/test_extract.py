"""
Unit Tests for Extract Stage.

Mocks external HTTP interactions to verify:
- Successful extraction parsing
- HTTP 429 rate limit backoff and Retry-After header handling
- 5xx transient server error retries
- 4xx permanent client error immediate abort
- Connection errors and timeouts
- Malformed/invalid JSON payloads
- Offline fixture ingestion
"""

import json
from unittest.mock import MagicMock, patch
import pytest
import requests

from aqi_pipeline.extract import AQIExtractor, ExtractionError


def test_fetch_city_success_mocked(test_config, sample_live_response_payload):
    """Verifies successful HTTP 200 response ingestion with metadata enrichment."""
    extractor = AQIExtractor(test_config)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = sample_live_response_payload
    mock_resp.raise_for_status.return_value = None

    with patch.object(extractor.session, "get", return_value=mock_resp) as mock_get:
        result = extractor.fetch_city_data("New Delhi", 28.6139, 77.2090)

        assert mock_get.call_count == 1
        assert "_metadata" in result
        assert result["_metadata"]["city"] == "New Delhi"
        assert result["_metadata"]["source"] == "open-meteo-air-quality-api"
        assert result["_metadata"]["execution_mode"] == "live"
        assert result["current"]["pm2_5"] == 95.7


def test_fetch_city_rate_limit_with_retry_after(test_config, sample_live_response_payload):
    """Verifies that HTTP 429 rate limits respect Retry-After header and succeed on retry."""
    extractor = AQIExtractor(test_config)

    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {"Retry-After": "0"}

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = sample_live_response_payload
    resp_200.raise_for_status.return_value = None

    with patch.object(extractor.session, "get", side_effect=[resp_429, resp_200]) as mock_get:
        result = extractor.fetch_city_data("Mumbai", 19.0760, 72.8777)
        assert mock_get.call_count == 2
        assert result["_metadata"]["city"] == "Mumbai"


def test_fetch_city_5xx_server_error_retry(test_config, sample_live_response_payload):
    """Verifies that 500 Internal Server Errors are retried up to max_retries."""
    extractor = AQIExtractor(test_config)

    resp_500 = MagicMock()
    resp_500.status_code = 500

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = sample_live_response_payload
    resp_200.raise_for_status.return_value = None

    with patch.object(extractor.session, "get", side_effect=[resp_500, resp_200]) as mock_get:
        result = extractor.fetch_city_data("Bengaluru", 12.9716, 77.5946)
        assert mock_get.call_count == 2
        assert result["_metadata"]["city"] == "Bengaluru"


def test_fetch_city_400_client_error_aborts_immediately(test_config):
    """Verifies that permanent 400 Bad Request client errors abort without retrying."""
    extractor = AQIExtractor(test_config)

    resp_400 = MagicMock()
    resp_400.status_code = 400
    resp_400.text = "Latitude must be in range of -90 to 90"

    with patch.object(extractor.session, "get", return_value=resp_400) as mock_get:
        with pytest.raises(ExtractionError) as exc_info:
            extractor.fetch_city_data("InvalidCity", 999.0, 77.0)

        # Must NOT retry permanent client errors
        assert mock_get.call_count == 1
        assert "Permanent client error" in str(exc_info.value)


def test_fetch_city_timeout_exhaustion(test_config):
    """Verifies that persistent timeouts exhaust all retries and raise ExtractionError."""
    extractor = AQIExtractor(test_config)

    with patch.object(
        extractor.session, "get", side_effect=requests.exceptions.Timeout("Connection timed out")
    ) as mock_get:
        with pytest.raises(ExtractionError) as exc_info:
            extractor.fetch_city_data("Chennai", 13.0827, 80.2707)

        assert mock_get.call_count == test_config.max_retries
        assert "Failed to fetch Chennai" in str(exc_info.value)


def test_fetch_city_invalid_json(test_config):
    """Verifies that responses with unparseable JSON raise ExtractionError."""
    extractor = AQIExtractor(test_config)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = requests.exceptions.JSONDecodeError("Unparseable", "doc", 0)

    with patch.object(extractor.session, "get", return_value=mock_resp):
        with pytest.raises(ExtractionError) as exc_info:
            extractor.fetch_city_data("Kolkata", 22.5726, 88.3639)
        assert "Malformed JSON" in str(exc_info.value)


def test_extract_from_fixtures(test_config):
    """Verifies that offline fixture extraction loads all cities correctly."""
    extractor = AQIExtractor(test_config)
    fixtures = extractor.extract_from_fixtures()

    assert len(fixtures) == 6
    delhi = next(f for f in fixtures if f["_metadata"]["city"] == "New Delhi")
    assert delhi["current"]["pm10"] == 106.2
    assert delhi["_metadata"]["execution_mode"] == "fixture"
