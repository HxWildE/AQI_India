"""
SQL Analytics and Trend Analysis Module for AQI India Pipeline.

Executes analytical queries on SQLite database to analyze:
- Pollutant trends across cities and time intervals
- Diurnal variations and statistical distributions
- Pollutant correlations (e.g., PM2.5 vs. PM10 ratio analysis)
- Data quality audits comparing accepted vs. quarantined records
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from aqi_pipeline.config import PipelineConfig, get_config
from aqi_pipeline.load import AQILoader
from aqi_pipeline.logging_config import setup_logger


class AQIAnalytics:
    """Provides SQL-driven analytics and statistical trend reporting."""

    def __init__(self, config: Optional[PipelineConfig] = None, logger: Optional[logging.Logger] = None) -> None:
        self.config = config or get_config()
        self.logger = logger or setup_logger("aqi_pipeline.analytics")
        self.loader = AQILoader(self.config)

    def get_all_observations_df(self) -> pd.DataFrame:
        """Fetches all clean observations as a pandas DataFrame."""
        sql = """
        SELECT 
            id, city, state, zone, latitude, longitude,
            timestamp_local, timestamp_utc,
            pm2_5, pm10, carbon_monoxide, nitrogen_dioxide, sulphur_dioxide, ozone,
            provider_aqi, aqi_category, data_source, extracted_at_utc, created_at
        FROM aqi_observations
        ORDER BY timestamp_utc ASC;
        """
        with self.loader.get_connection() as conn:
            df = pd.read_sql_query(sql, conn)
        return df

    def get_city_summary_metrics(self) -> pd.DataFrame:
        """
        Aggregates average, max, and min pollutant levels per city via SQL.
        """
        sql = """
        SELECT 
            city,
            COUNT(*) as total_observations,
            ROUND(AVG(pm2_5), 1) as avg_pm2_5,
            ROUND(MAX(pm2_5), 1) as max_pm2_5,
            ROUND(AVG(pm10), 1) as avg_pm10,
            ROUND(MAX(pm10), 1) as max_pm10,
            ROUND(AVG(provider_aqi), 0) as avg_aqi,
            ROUND(MAX(provider_aqi), 0) as max_aqi,
            MAX(timestamp_local) as latest_timestamp
        FROM aqi_observations
        GROUP BY city
        ORDER BY avg_aqi DESC;
        """
        with self.loader.get_connection() as conn:
            return pd.read_sql_query(sql, conn)

    def get_pm_ratio_analysis(self) -> pd.DataFrame:
        """
        Calculates PM2.5 to PM10 ratio per observation.
        In atmospheric science, PM2.5 / PM10 is normally between 0.3 and 0.8.
        A ratio > 1.0 is physically suspicious and suggests optical sensor calibration drift.
        """
        sql = """
        SELECT 
            city,
            timestamp_local,
            pm2_5,
            pm10,
            CASE 
                WHEN pm10 IS NOT NULL AND pm10 > 0 
                THEN ROUND(pm2_5 / pm10, 3)
                ELSE NULL 
            END as pm_ratio,
            provider_aqi,
            aqi_category
        FROM aqi_observations
        WHERE pm2_5 IS NOT NULL AND pm10 IS NOT NULL;
        """
        with self.loader.get_connection() as conn:
            return pd.read_sql_query(sql, conn)

    def get_data_quality_report(self) -> Dict[str, Any]:
        """
        Audits overall data quality comparing valid observations to quarantined records.
        """
        with self.loader.get_connection() as conn:
            obs_count = conn.execute("SELECT COUNT(*) FROM aqi_observations;").fetchone()[0]
            quar_count = conn.execute("SELECT COUNT(*) FROM aqi_quarantine;").fetchone()[0]
            runs_count = conn.execute("SELECT COUNT(*) FROM pipeline_runs;").fetchone()[0]

            quar_reasons = conn.execute("""
                SELECT rejection_reason, COUNT(*) as count 
                FROM aqi_quarantine 
                GROUP BY rejection_reason 
                ORDER BY count DESC;
            """).fetchall()

        total = obs_count + quar_count
        clean_rate = round((obs_count / total * 100), 1) if total > 0 else 100.0

        return {
            "total_records_processed": total,
            "accepted_observations": obs_count,
            "quarantined_records": quar_count,
            "clean_rate_percent": clean_rate,
            "total_pipeline_runs": runs_count,
            "quarantine_reasons": [dict(r) for r in quar_reasons],
        }

    def get_zone_summary_metrics(self) -> pd.DataFrame:
        """
        Aggregates air quality metrics by geographical zone (North, South, East, West).
        """
        sql = """
        SELECT 
            COALESCE(zone, 'Unspecified') as zone,
            COUNT(DISTINCT city) as city_count,
            COUNT(*) as total_observations,
            ROUND(AVG(pm2_5), 1) as avg_pm2_5,
            ROUND(MAX(pm2_5), 1) as max_pm2_5,
            ROUND(AVG(pm10), 1) as avg_pm10,
            ROUND(MAX(pm10), 1) as max_pm10,
            ROUND(AVG(provider_aqi), 0) as avg_aqi,
            ROUND(MAX(provider_aqi), 0) as max_aqi
        FROM aqi_observations
        GROUP BY zone
        ORDER BY avg_aqi DESC;
        """
        with self.loader.get_connection() as conn:
            return pd.read_sql_query(sql, conn)

    def get_aqi_category_breakdown(self) -> pd.DataFrame:
        """
        Computes distribution of observations across standard AQI categories.
        """
        sql = """
        SELECT 
            aqi_category,
            COUNT(*) as count,
            ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM aqi_observations), 1) as percentage
        FROM aqi_observations
        GROUP BY aqi_category
        ORDER BY count DESC;
        """
        with self.loader.get_connection() as conn:
            return pd.read_sql_query(sql, conn)

    def get_top_polluted_cities(self, limit: int = 5) -> pd.DataFrame:
        """
        Returns top most polluted cities ordered by average AQI.
        """
        sql = """
        SELECT 
            city,
            state,
            zone,
            ROUND(AVG(provider_aqi), 0) as avg_aqi,
            ROUND(AVG(pm2_5), 1) as avg_pm2_5,
            ROUND(AVG(pm10), 1) as avg_pm10,
            MAX(timestamp_local) as latest_timestamp
        FROM aqi_observations
        GROUP BY city, state, zone
        ORDER BY avg_aqi DESC
        LIMIT ?;
        """
        with self.loader.get_connection() as conn:
            return pd.read_sql_query(sql, conn, params=(limit,))

    def export_observations_to_csv(self, output_path: str | Path) -> Path:
        """
        Exports all clean analytical observations to a CSV file.
        """
        df = self.get_all_observations_df()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        self.logger.info(f"Exported {len(df)} observations to CSV at {out}")
        return out

    def get_hourly_diurnal_trends(self) -> pd.DataFrame:
        """
        Aggregates pollutant averages by hour of day (0-23 in IST)
        to identify diurnal cycles and peak pollution windows (e.g. morning rush hours, evening smog).
        """
        sql = """
        SELECT 
            CAST(SUBSTR(timestamp_local, 12, 2) AS INTEGER) as hour_of_day,
            COUNT(*) as observation_count,
            ROUND(AVG(pm2_5), 1) as avg_pm2_5,
            ROUND(AVG(pm10), 1) as avg_pm10,
            ROUND(AVG(provider_aqi), 0) as avg_aqi
        FROM aqi_observations
        WHERE timestamp_local IS NOT NULL AND LENGTH(timestamp_local) >= 13
        GROUP BY hour_of_day
        ORDER BY hour_of_day ASC;
        """
        with self.loader.get_connection() as conn:
            return pd.read_sql_query(sql, conn)


