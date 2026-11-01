"""
Unit and integration tests for the AQI India FastAPI REST API Gateway.
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from aqi_pipeline.config import PipelineConfig
from aqi_pipeline.api import create_app
from aqi_pipeline.pipeline import AQIPipeline


@pytest.fixture(scope="module")
def seeded_client(tmp_path_factory) -> TestClient:
    """Creates a seeded SQLite database and returns a configured TestClient."""
    db_dir = tmp_path_factory.mktemp("api_test_db")
    db_file = db_dir / "test_api_aqi.db"
    fixture_file = Path(__file__).parent / "fixtures" / "batch_cities_response.json"

    config = PipelineConfig(
        db_path=db_file,
        fixture_path=fixture_file,
        execution_mode="fixture",
        log_level="WARNING",
    )

    # Seed the database using offline fixture
    pipeline = AQIPipeline(config)
    pipeline.run(mode="fixture")

    app = create_app(config)
    return TestClient(app)


def test_api_root(seeded_client: TestClient) -> None:
    """Verifies that the root endpoint returns API metadata."""
    response = seeded_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "/docs" in data["documentation"]
    assert "/observations" in data["endpoints"]


def test_api_health(seeded_client: TestClient) -> None:
    """Verifies pipeline health and clean data rate reporting."""
    response = seeded_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OK"
    assert data["accepted_observations"] > 0
    assert data["clean_rate_percent"] >= 70.0


def test_api_get_observations_unfiltered(seeded_client: TestClient) -> None:
    """Verifies retrieval of clean observations without query filters."""
    response = seeded_client.get("/observations?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "city" in data[0]
    assert "pm2_5" in data[0]
    assert "aqi_category" in data[0]


def test_api_get_observations_filtered_by_city(seeded_client: TestClient) -> None:
    """Verifies filtering observations by city name."""
    response = seeded_client.get("/observations?city=New Delhi")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert all(r["city"].lower() == "new delhi" for r in data)


def test_api_analytics_endpoints(seeded_client: TestClient) -> None:
    """Verifies all SQL analytics reporting endpoints."""
    # Cities summary
    r_cities = seeded_client.get("/analytics/cities")
    assert r_cities.status_code == 200
    assert len(r_cities.json()) > 0
    assert "avg_pm2_5" in r_cities.json()[0]

    # Zonal summary
    r_zones = seeded_client.get("/analytics/zones")
    assert r_zones.status_code == 200
    assert len(r_zones.json()) > 0
    assert "zone" in r_zones.json()[0]

    # PM ratio analysis
    r_ratio = seeded_client.get("/analytics/pm-ratio")
    assert r_ratio.status_code == 200
    assert len(r_ratio.json()) > 0
    assert "pm_ratio" in r_ratio.json()[0]

    # Diurnal trends
    r_diurnal = seeded_client.get("/analytics/diurnal")
    assert r_diurnal.status_code == 200
    assert len(r_diurnal.json()) > 0


def test_api_analytics_export_csv(seeded_client: TestClient) -> None:
    """Verifies streaming CSV export via API."""
    response = seeded_client.get("/analytics/export")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment; filename=aqi_observations_export.csv" in response.headers["content-disposition"]
    assert "city" in response.text
    assert "timestamp_utc" in response.text


def test_api_anomaly_detect(seeded_client: TestClient) -> None:
    """Verifies Scikit-learn Isolation Forest execution via API."""
    response = seeded_client.post("/anomaly/detect?contamination=0.15")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Even if zero outliers in small fixture, response is valid list
    for item in data:
        assert item["is_anomaly"] is True


def test_api_pipeline_trigger_success(seeded_client: TestClient) -> None:
    """Verifies asynchronous pipeline trigger returns 202 Accepted."""
    response = seeded_client.post(
        "/pipeline/trigger",
        json={"mode": "fixture", "cities": ["Mumbai", "Bengaluru"]},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "ACCEPTED"
    assert data["mode"] == "fixture"
    assert data["selected_cities"] == ["Mumbai", "Bengaluru"]


def test_api_pipeline_trigger_invalid_mode(seeded_client: TestClient) -> None:
    """Verifies that invalid trigger modes are rejected with 400 Bad Request."""
    response = seeded_client.post(
        "/pipeline/trigger",
        json={"mode": "invalid_mode"},
    )
    assert response.status_code == 400
    assert "Invalid execution mode" in response.json()["detail"]
