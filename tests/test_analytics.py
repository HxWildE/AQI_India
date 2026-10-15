"""
Unit Tests for Analytics and SQL Aggregations Module.
"""

import pytest
import pandas as pd
from aqi_pipeline.analytics import AQIAnalytics
from aqi_pipeline.pipeline import AQIPipeline


def test_analytics_metrics_and_summary(test_config):
    """Verifies SQL aggregations and city trend computations."""
    # Seed data via fixture run
    pipeline = AQIPipeline(test_config)
    pipeline.run(mode="fixture")

    analytics = AQIAnalytics(test_config)

    # 1. Test get_all_observations_df
    df = analytics.get_all_observations_df()
    assert not df.empty
    assert len(df) == 6
    assert "city" in df.columns
    assert "pm2_5" in df.columns

    # 2. Test get_city_summary_metrics
    summary_df = analytics.get_city_summary_metrics()
    assert len(summary_df) == 6
    assert "avg_aqi" in summary_df.columns
    assert "max_pm2_5" in summary_df.columns

    # 3. Test PM ratio analysis
    ratio_df = analytics.get_pm_ratio_analysis()
    assert not ratio_df.empty
    assert "pm_ratio" in ratio_df.columns
    delhi_ratio = ratio_df[ratio_df["city"] == "New Delhi"].iloc[0]["pm_ratio"]
    assert delhi_ratio is not None and delhi_ratio > 0

    # 4. Test data quality report
    report = analytics.get_data_quality_report()
    assert report["accepted_observations"] == 6
    assert report["clean_rate_percent"] == 100.0
