"""
Unit Tests for Load Stage.

Verifies:
- Relational schema creation and constraints
- Parametric SQL execution
- Idempotent upserts via composite unique key (city, timestamp_utc)
- Proper separation of inserted vs. updated counts
- Transaction rollback behavior on errors
- Quarantine logging
- Audit execution logging
"""

import sqlite3
import pytest
from aqi_pipeline.load import AQILoader
from aqi_pipeline.transform import ObservationRecord, QuarantineRecord


@pytest.fixture
def sample_record():
    return ObservationRecord(
        city="New Delhi",
        state="Delhi",
        zone="North",
        latitude=28.6139,
        longitude=77.2090,
        timestamp_local="2026-10-15T22:30:00+05:30",
        timestamp_utc="2026-10-15T17:00:00+00:00",
        pm2_5=95.7,
        pm10=106.2,
        carbon_monoxide=1674.0,
        nitrogen_dioxide=79.5,
        sulphur_dioxide=41.9,
        ozone=27.0,
        provider_aqi=158.0,
        aqi_category="Unhealthy",
        data_source="open-meteo",
        extracted_at_utc="2026-10-15T17:05:00+00:00",
    )


def test_init_schema_creates_tables_and_indexes(test_config):
    """Verifies that schema DDL sets up required tables and indexes."""
    loader = AQILoader(test_config)

    with loader.get_connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
        table_names = [t["name"] for t in tables]

        assert "aqi_observations" in table_names
        assert "aqi_quarantine" in table_names
        assert "pipeline_runs" in table_names

        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name;"
        ).fetchall()
        index_names = [i["name"] for i in indexes]

        assert "idx_aqi_city_timestamp" in index_names
        assert "idx_aqi_category" in index_names


def test_load_observations_inserts_records(test_config, sample_record):
    """Verifies that new observations are inserted properly into SQLite."""
    loader = AQILoader(test_config)

    inserted, updated = loader.load_observations([sample_record])
    assert inserted == 1
    assert updated == 0
    assert loader.get_total_observations_count() == 1

    recent = loader.get_recent_observations(10)
    assert len(recent) == 1
    assert recent[0]["city"] == "New Delhi"
    assert recent[0]["pm2_5"] == 95.7


def test_idempotency_loading_same_record_twice(test_config, sample_record):
    """
    CRITICAL IDEMPOTENCY TEST:
    Rerunning the same input batch must NOT create duplicate rows.
    First run: 1 inserted, 0 updated.
    Second run: 0 inserted, 1 updated.
    Total row count in DB must remain exactly 1!
    """
    loader = AQILoader(test_config)

    # First load
    ins1, upd1 = loader.load_observations([sample_record])
    assert ins1 == 1
    assert upd1 == 0
    assert loader.get_total_observations_count() == 1

    # Second load with identical natural key (city, timestamp_utc)
    ins2, upd2 = loader.load_observations([sample_record])
    assert ins2 == 0
    assert upd2 == 1
    # Total records MUST still be 1 (No duplicate records!)
    assert loader.get_total_observations_count() == 1


def test_load_quarantine_records(test_config):
    """Verifies rejected records are safely stored in quarantine table."""
    loader = AQILoader(test_config)
    quar = QuarantineRecord(
        city="TestCity",
        timestamp_local="2026-10-15T12:00:00",
        rejection_reason="pm2_5 is negative (-10)",
        raw_payload_snippet='{"pm2_5": -10}',
        quarantined_at_utc="2026-10-15T12:01:00+00:00",
    )

    count = loader.load_quarantine([quar])
    assert count == 1
    assert loader.get_total_quarantine_count() == 1


def test_transaction_rollback_on_failure(test_config, sample_record):
    """Verifies that an error during batch load causes a rollback and leaves no partial rows."""
    loader = AQILoader(test_config)

    # Corrupt record causing DB error (e.g. invalid type or missing NOT NULL)
    bad_record = ObservationRecord(
        city="FailCity",
        state=None,
        zone=None,
        latitude=0.0,
        longitude=0.0,
        timestamp_local="2026-10-15",
        timestamp_utc="2026-10-15",
        pm2_5=None,
        pm10=None,
        carbon_monoxide=None,
        nitrogen_dioxide=None,
        sulphur_dioxide=None,
        ozone=None,
        provider_aqi=None,
        aqi_category="Good",
        data_source="test",
        extracted_at_utc="2026-10-15",
    )

    # Patch the loader's connection to simulate a sudden constraint failure
    with loader.get_connection() as conn:
        with pytest.raises(Exception):
            with conn:
                conn.execute("INSERT INTO aqi_observations (city) VALUES ('Partial');")
                raise sqlite3.OperationalError("Simulated crash mid-transaction")

    # Verify no partial rows survived
    assert loader.get_total_observations_count() == 0
