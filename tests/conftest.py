"""
Pytest Fixtures and Configuration for AQI India ETL Pipeline Tests.
"""

import json
from pathlib import Path
import pytest
from aqi_pipeline.config import PipelineConfig, get_config

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"


@pytest.fixture
def sample_live_response_payload():
    """Returns sample sanitized real API response dict."""
    with open(FIXTURES_DIR / "live_sample_response.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def batch_cities_payload():
    """Returns multi-city batch fixture dict."""
    with open(FIXTURES_DIR / "batch_cities_response.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def malformed_payload():
    """Returns malformed test payloads."""
    with open(FIXTURES_DIR / "malformed_response.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def temp_db_path(tmp_path):
    """Provides a fresh isolated SQLite database file path for testing."""
    return tmp_path / "test_aqi.db"


@pytest.fixture
def test_config(temp_db_path):
    """Provides a pipeline config pointed to temporary database and fast backoff."""
    return get_config(
        db_path=temp_db_path,
        fixture_path=FIXTURES_DIR / "batch_cities_response.json",
        timeout_seconds=2.0,
        max_retries=2,
        backoff_factor=0.01,
        rate_limit_delay_seconds=0.0,
        log_level="DEBUG",
        execution_mode="fixture",
    )


def pytest_addoption(parser):
    """Adds --run-live flag for optional live API tests."""
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live API smoke test against real Open-Meteo endpoint",
    )


def pytest_collection_modifyitems(config, items):
    """Skips live marked tests unless --run-live is explicitly supplied."""
    if config.getoption("--run-live"):
        return
    skip_live = pytest.mark.skip(reason="Pass --run-live to execute real network smoke tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
