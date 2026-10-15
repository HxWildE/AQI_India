"""
Integration Tests for AQI India End-to-End Pipeline.

Verifies:
- Complete end-to-end execution flow (Extract -> Transform -> Load) using fixtures
- Pipeline-level idempotency on repeated execution
- Pipeline audit run logging in SQLite
- Quarantine routing and counting
"""

from pathlib import Path
from unittest.mock import patch
import pytest

from aqi_pipeline.config import get_config
from aqi_pipeline.pipeline import AQIPipeline


def test_full_fixture_e2e_run(test_config):
    """Verifies complete pipeline execution from offline fixture to database."""
    pipeline = AQIPipeline(test_config)

    summary = pipeline.run(mode="fixture")

    assert summary["status"] == "SUCCESS"
    assert summary["records_extracted"] == 6
    assert summary["records_accepted"] == 6
    assert summary["records_quarantined"] == 0
    assert summary["records_inserted"] == 6
    assert summary["records_updated"] == 0

    # Verify rows in database
    assert pipeline.loader.get_total_observations_count() == 6
    recent = pipeline.loader.get_recent_observations(10)
    cities_in_db = {r["city"] for r in recent}
    assert "New Delhi" in cities_in_db
    assert "Mumbai" in cities_in_db
    assert "Bengaluru" in cities_in_db


def test_e2e_idempotency_on_rerun(test_config):
    """
    CRITICAL END-TO-END IDEMPOTENCY TEST:
    Running the entire pipeline twice against the same data:
    Run 1: 6 inserted, 0 updated, total = 6.
    Run 2: 0 inserted, 6 updated, total = 6.
    """
    pipeline = AQIPipeline(test_config)

    # First run
    run1 = pipeline.run(mode="fixture")
    assert run1["records_inserted"] == 6
    assert run1["records_updated"] == 0
    assert pipeline.loader.get_total_observations_count() == 6

    # Second run immediately following
    run2 = pipeline.run(mode="fixture")
    assert run2["records_inserted"] == 0
    assert run2["records_updated"] == 6
    # Count remains exactly 6!
    assert pipeline.loader.get_total_observations_count() == 6


def test_pipeline_with_malformed_fixture_routes_to_quarantine(tmp_path):
    """Verifies that malformed input data is quarantined while valid data is loaded."""
    fixture_path = Path(__file__).parent / "fixtures" / "malformed_response.json"
    cfg = get_config(
        db_path=tmp_path / "quar_test.db",
        fixture_path=fixture_path,
        execution_mode="fixture",
    )
    pipeline = AQIPipeline(cfg)

    summary = pipeline.run(mode="fixture")

    assert summary["status"] == "SUCCESS"
    assert summary["records_extracted"] == 4
    # All 4 items in malformed_response.json are deliberately invalid
    assert summary["records_accepted"] == 0
    assert summary["records_quarantined"] == 4
    assert summary["records_inserted"] == 0
    assert pipeline.loader.get_total_quarantine_count() == 4
    assert pipeline.loader.get_total_observations_count() == 0


def test_pipeline_failure_audit_logging(test_config):
    """Verifies that catastrophic errors in pipeline are audited in pipeline_runs."""
    pipeline = AQIPipeline(test_config)

    # Force an unexpected extraction crash
    with patch.object(
        pipeline.extractor,
        "extract_from_fixtures",
        side_effect=RuntimeError("Simulated pipeline crash"),
    ):
        with pytest.raises(RuntimeError):
            pipeline.run(mode="fixture")

    # Verify run record was marked FAILED
    with pipeline.loader.get_connection() as conn:
        row = conn.execute(
            "SELECT status, error_message FROM pipeline_runs ORDER BY started_at DESC LIMIT 1;"
        ).fetchone()
        assert row["status"] == "FAILED"
        assert "Simulated pipeline crash" in row["error_message"]
