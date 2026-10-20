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


def test_zone_and_category_analytics_and_export(test_config, tmp_path):
    """Verifies zone aggregation, category breakdown, top polluted cities, and CSV export."""
    pipeline = AQIPipeline(test_config)
    pipeline.run(mode="fixture")

    analytics = AQIAnalytics(test_config)

    # 1. Test Zone metrics
    zone_df = analytics.get_zone_summary_metrics()
    assert not zone_df.empty
    assert "zone" in zone_df.columns
    assert "avg_aqi" in zone_df.columns
    assert "city_count" in zone_df.columns

    # 2. Test AQI Category breakdown
    cat_df = analytics.get_aqi_category_breakdown()
    assert not cat_df.empty
    assert "aqi_category" in cat_df.columns
    assert "count" in cat_df.columns
    assert "percentage" in cat_df.columns
    assert round(cat_df["percentage"].sum()) in (99, 100, 101)

    # 3. Test Top polluted cities
    top_df = analytics.get_top_polluted_cities(limit=3)
    assert len(top_df) <= 3
    assert "avg_aqi" in top_df.columns

    # 4. Test CSV Export
    csv_dest = tmp_path / "exports" / "test_observations.csv"
    res_path = analytics.export_observations_to_csv(csv_dest)
    assert res_path.exists()
    assert res_path.stat().st_size > 0
    read_back = pd.read_csv(res_path)
    assert len(read_back) == 6


def test_diurnal_trends_analytics(test_config):
    """Verifies diurnal hourly pattern calculation."""
    pipeline = AQIPipeline(test_config)
    pipeline.run(mode="fixture")

    analytics = AQIAnalytics(test_config)
    diurnal_df = analytics.get_hourly_diurnal_trends()
    assert not diurnal_df.empty
    assert "hour_of_day" in diurnal_df.columns
    assert "avg_pm2_5" in diurnal_df.columns
    assert "observation_count" in diurnal_df.columns
    assert (diurnal_df["hour_of_day"] >= 0).all() and (diurnal_df["hour_of_day"] <= 23).all()


