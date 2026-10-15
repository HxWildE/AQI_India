"""
Load Stage for AQI India ETL Pipeline.

Manages persistent relational storage in SQLite with:
- Automatic schema creation, constraints, and indexes
- Strict idempotency via natural composite unique key (city, timestamp_utc)
- Accurate accounting of inserted vs. updated records
- Transactional atomicity: partial failures rollback to prevent corrupted state
- Quarantine logging for data quality governance
- Pipeline run metadata audit tracking
- Inspection utilities for CLI diagnostics and integration tests
"""

from __future__ import annotations
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from aqi_pipeline.config import PipelineConfig
from aqi_pipeline.logging_config import setup_logger
from aqi_pipeline.transform import ObservationRecord, QuarantineRecord


SCHEMA_DDL = """
-- Analytical table for clean, validated air quality measurements
CREATE TABLE IF NOT EXISTS aqi_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    state TEXT,
    zone TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timestamp_local TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    pm2_5 REAL,
    pm10 REAL,
    carbon_monoxide REAL,
    nitrogen_dioxide REAL,
    sulphur_dioxide REAL,
    ozone REAL,
    provider_aqi REAL,
    aqi_category TEXT NOT NULL,
    data_source TEXT NOT NULL,
    extracted_at_utc TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_city_timestamp UNIQUE (city, timestamp_utc)
);

-- Index for temporal and geographic query filtering
CREATE INDEX IF NOT EXISTS idx_aqi_city_timestamp ON aqi_observations (city, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_aqi_category ON aqi_observations (aqi_category);
CREATE INDEX IF NOT EXISTS idx_aqi_timestamp_utc ON aqi_observations (timestamp_utc);

-- Quarantine table for defective or out-of-range observations
CREATE TABLE IF NOT EXISTS aqi_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    timestamp_local TEXT,
    rejection_reason TEXT NOT NULL,
    raw_payload_snippet TEXT,
    quarantined_at_utc TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Audit table tracking pipeline execution runs
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    execution_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    records_extracted INTEGER NOT NULL DEFAULT 0,
    records_accepted INTEGER NOT NULL DEFAULT 0,
    records_quarantined INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_updated INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    elapsed_seconds REAL,
    error_message TEXT
);
"""


class AQILoader:
    """Manages SQLite storage, idempotency, and audit trails."""

    def __init__(self, config: PipelineConfig, logger: Optional[logging.Logger] = None) -> None:
        self.config = config
        self.logger = logger or setup_logger("aqi_pipeline.load")
        self.db_path = self.config.db_path
        self._ensure_database_dir()
        self.init_schema()

    def _ensure_database_dir(self) -> None:
        """Creates parent directory for SQLite file if needed."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provides a managed SQLite connection context with foreign keys enabled."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Executes DDL statements to ensure tables and indexes exist."""
        with self.get_connection() as conn:
            conn.executescript(SCHEMA_DDL)
            conn.commit()
        self.logger.debug(f"Database schema initialized at {self.db_path}")

    def load_observations(
        self, records: List[ObservationRecord]
    ) -> Tuple[int, int]:
        """
        Idempotently loads cleaned observations into `aqi_observations`.

        Returns:
            Tuple of (records_inserted, records_updated)
        """
        if not records:
            return 0, 0

        inserted_count = 0
        updated_count = 0

        upsert_sql = """
        INSERT INTO aqi_observations (
            city, state, zone, latitude, longitude,
            timestamp_local, timestamp_utc,
            pm2_5, pm10, carbon_monoxide, nitrogen_dioxide, sulphur_dioxide, ozone,
            provider_aqi, aqi_category, data_source, extracted_at_utc,
            created_at, updated_at
        ) VALUES (
            :city, :state, :zone, :latitude, :longitude,
            :timestamp_local, :timestamp_utc,
            :pm2_5, :pm10, :carbon_monoxide, :nitrogen_dioxide, :sulphur_dioxide, :ozone,
            :provider_aqi, :aqi_category, :data_source, :extracted_at_utc,
            datetime('now'), datetime('now')
        )
        ON CONFLICT(city, timestamp_utc) DO UPDATE SET
            state = excluded.state,
            zone = excluded.zone,
            latitude = excluded.latitude,
            longitude = excluded.longitude,
            timestamp_local = excluded.timestamp_local,
            pm2_5 = excluded.pm2_5,
            pm10 = excluded.pm10,
            carbon_monoxide = excluded.carbon_monoxide,
            nitrogen_dioxide = excluded.nitrogen_dioxide,
            sulphur_dioxide = excluded.sulphur_dioxide,
            ozone = excluded.ozone,
            provider_aqi = excluded.provider_aqi,
            aqi_category = excluded.aqi_category,
            data_source = excluded.data_source,
            extracted_at_utc = excluded.extracted_at_utc,
            updated_at = datetime('now');
        """

        with self.get_connection() as conn:
            try:
                conn.execute("BEGIN TRANSACTION;")
                for rec in records:
                    # Check existence prior to upsert for accurate insert vs update metrics
                    cursor = conn.execute(
                        "SELECT 1 FROM aqi_observations WHERE city = ? AND timestamp_utc = ?",
                        (rec.city, rec.timestamp_utc),
                    )
                    exists = cursor.fetchone() is not None

                    conn.execute(upsert_sql, rec.to_dict())

                    if exists:
                        updated_count += 1
                    else:
                        inserted_count += 1

                conn.commit()
                self.logger.info(
                    f"Loaded observations: {inserted_count} inserted, {updated_count} updated"
                )
            except Exception as exc:
                conn.rollback()
                self.logger.error(f"Transaction aborted during observation load: {exc}")
                raise

        return inserted_count, updated_count

    def load_quarantine(self, records: List[QuarantineRecord]) -> int:
        """
        Inserts rejected observations into `aqi_quarantine`.
        """
        if not records:
            return 0

        insert_sql = """
        INSERT INTO aqi_quarantine (
            city, timestamp_local, rejection_reason, raw_payload_snippet, quarantined_at_utc
        ) VALUES (
            :city, :timestamp_local, :rejection_reason, :raw_payload_snippet, :quarantined_at_utc
        );
        """

        with self.get_connection() as conn:
            try:
                conn.execute("BEGIN TRANSACTION;")
                for rec in records:
                    conn.execute(insert_sql, rec.to_dict())
                conn.commit()
                self.logger.info(f"Recorded {len(records)} quarantined entries")
                return len(records)
            except Exception as exc:
                conn.rollback()
                self.logger.error(f"Failed to record quarantine records: {exc}")
                raise

    def record_pipeline_run_start(self, run_id: str, mode: str) -> None:
        """Logs initial pipeline start record."""
        sql = """
        INSERT INTO pipeline_runs (
            run_id, execution_mode, status, started_at
        ) VALUES (?, ?, 'STARTED', ?);
        """
        with self.get_connection() as conn:
            conn.execute(sql, (run_id, mode, datetime.now(timezone.utc).isoformat()))
            conn.commit()

    def record_pipeline_run_completion(
        self,
        run_id: str,
        status: str,
        records_extracted: int,
        records_accepted: int,
        records_quarantined: int,
        records_inserted: int,
        records_updated: int,
        started_at_dt: datetime,
        error_message: Optional[str] = None,
    ) -> None:
        """Updates pipeline run record with final audit metrics."""
        now = datetime.now(timezone.utc)
        elapsed = (now - started_at_dt).total_seconds()
        sql = """
        UPDATE pipeline_runs SET
            status = ?,
            records_extracted = ?,
            records_accepted = ?,
            records_quarantined = ?,
            records_inserted = ?,
            records_updated = ?,
            finished_at = ?,
            elapsed_seconds = ?,
            error_message = ?
        WHERE run_id = ?;
        """
        with self.get_connection() as conn:
            conn.execute(
                sql,
                (
                    status,
                    records_extracted,
                    records_accepted,
                    records_quarantined,
                    records_inserted,
                    records_updated,
                    now.isoformat(),
                    round(elapsed, 3),
                    error_message,
                    run_id,
                ),
            )
            conn.commit()

    def get_recent_observations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Queries recent observations for display or test verification."""
        sql = """
        SELECT id, city, state, timestamp_local, pm2_5, pm10, provider_aqi, aqi_category, updated_at
        FROM aqi_observations
        ORDER BY timestamp_utc DESC, city ASC
        LIMIT ?;
        """
        with self.get_connection() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_total_observations_count(self) -> int:
        """Returns total row count of aqi_observations."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM aqi_observations;").fetchone()
            return int(row["count"]) if row else 0

    def get_total_quarantine_count(self) -> int:
        """Returns total row count of aqi_quarantine."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM aqi_quarantine;").fetchone()
            return int(row["count"]) if row else 0
