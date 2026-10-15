"""
Unit Tests for Scikit-learn Anomaly Detection Module.
"""

import pytest
import pandas as pd
import numpy as np
from aqi_pipeline.anomaly import AQIAnomalyDetector


def test_anomaly_detection_with_outlier():
    """Verifies that an artificial extreme multi-pollutant spike is detected by Isolation Forest."""
    detector = AQIAnomalyDetector(contamination=0.2, random_state=42)

    # Normal baseline readings
    normal_data = [
        {"city": "CityA", "pm2_5": 25.0, "pm10": 50.0, "carbon_monoxide": 500.0, "nitrogen_dioxide": 20.0, "sulphur_dioxide": 10.0, "ozone": 30.0},
        {"city": "CityB", "pm2_5": 28.0, "pm10": 55.0, "carbon_monoxide": 520.0, "nitrogen_dioxide": 22.0, "sulphur_dioxide": 11.0, "ozone": 32.0},
        {"city": "CityC", "pm2_5": 30.0, "pm10": 60.0, "carbon_monoxide": 540.0, "nitrogen_dioxide": 25.0, "sulphur_dioxide": 12.0, "ozone": 35.0},
        {"city": "CityD", "pm2_5": 26.0, "pm10": 52.0, "carbon_monoxide": 510.0, "nitrogen_dioxide": 21.0, "sulphur_dioxide": 10.5, "ozone": 31.0},
        {"city": "CityE", "pm2_5": 29.0, "pm10": 58.0, "carbon_monoxide": 530.0, "nitrogen_dioxide": 23.0, "sulphur_dioxide": 11.5, "ozone": 33.0},
        # Massive anomaly
        {"city": "OutlierCity", "pm2_5": 850.0, "pm10": 1900.0, "carbon_monoxide": 45000.0, "nitrogen_dioxide": 850.0, "sulphur_dioxide": 800.0, "ozone": 800.0},
    ]
    df = pd.DataFrame(normal_data)

    scored_df = detector.detect_anomalies(df)

    assert "is_anomaly" in scored_df.columns
    assert "anomaly_score" in scored_df.columns
    assert "anomaly_reason" in scored_df.columns

    # The extreme outlier should be flagged as an anomaly
    outlier_row = scored_df[scored_df["city"] == "OutlierCity"].iloc[0]
    assert outlier_row["is_anomaly"] == True
    assert outlier_row["anomaly_score"] > 0.5


def test_domain_rule_pm_inversion_detected():
    """Verifies that an atmospheric impossibility (PM2.5 > PM10) is flagged."""
    detector = AQIAnomalyDetector(contamination=0.1, random_state=42)

    data = [
        {"city": "City1", "pm2_5": 30.0, "pm10": 60.0, "carbon_monoxide": 500.0, "nitrogen_dioxide": 20.0, "sulphur_dioxide": 10.0, "ozone": 30.0},
        {"city": "City2", "pm2_5": 35.0, "pm10": 70.0, "carbon_monoxide": 550.0, "nitrogen_dioxide": 22.0, "sulphur_dioxide": 12.0, "ozone": 32.0},
        {"city": "InvertedCity", "pm2_5": 90.0, "pm10": 30.0, "carbon_monoxide": 500.0, "nitrogen_dioxide": 20.0, "sulphur_dioxide": 10.0, "ozone": 30.0},
    ]
    df = pd.DataFrame(data)

    scored_df = detector.detect_anomalies(df)
    inv_row = scored_df[scored_df["city"] == "InvertedCity"].iloc[0]
    assert inv_row["is_anomaly"] == True
    assert "PM2.5 > PM10" in inv_row["anomaly_reason"]
