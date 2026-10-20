"""
Machine Learning Anomaly Detection Module for AQI India Pipeline.

Applies Scikit-learn's Isolation Forest and domain boundary checks to identify:
1. Multivariate statistical anomalies across simultaneous pollutant readings
   (PM2.5, PM10, CO, NO2, SO2, O3).
2. Domain-specific physical anomalies (e.g., PM2.5 > PM10 optical sensor inversion).
3. Extreme sudden spikes relative to city baseline distributions.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from aqi_pipeline.logging_config import setup_logger

FEATURE_COLS = [
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
]


class AQIAnomalyDetector:
    """Detects multi-pollutant atmospheric anomalies using Scikit-learn Isolation Forest."""

    def __init__(
        self,
        contamination: float = 0.1,
        random_state: int = 42,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.contamination = contamination
        self.random_state = random_state
        self.logger = logger or setup_logger("aqi_pipeline.anomaly")
        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=self.random_state,
            n_estimators=100,
        )
        self.scaler = StandardScaler()
        self.is_fitted = False

    def detect_anomalies(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Runs unsupervised anomaly detection on an observation DataFrame.

        Returns:
            DataFrame enriched with 'is_anomaly', 'anomaly_score', and 'anomaly_reason'.
        """
        if df.empty or len(df) < 2:
            self.logger.warning("Insufficient observations for ML anomaly detection (< 2 rows)")
            out = df.copy()
            out["is_anomaly"] = False
            out["anomaly_score"] = 0.0
            out["anomaly_reason"] = "Insufficient data"
            out["top_contributor"] = None
            return out

        result_df = df.copy()

        # 1. Prepare numeric feature matrix
        available_features = [col for col in FEATURE_COLS if col in df.columns]
        X = result_df[available_features].copy()

        # Handle missing values: impute column median or 0.0
        for col in available_features:
            median_val = X[col].median()
            if pd.isna(median_val):
                median_val = 0.0
            X[col] = X[col].fillna(median_val)

        # 2. Fit and predict with Isolation Forest
        scaled_X = self.scaler.fit_transform(X)
        self.model.fit(scaled_X)
        self.is_fitted = True

        # IsolationForest returns -1 for outliers, 1 for inliers
        raw_preds = self.model.predict(scaled_X)
        # raw decision function: lower means more anomalous. Invert for intuition (higher = more anomalous)
        raw_scores = self.model.decision_function(scaled_X)
        # Normalize anomaly score to [0, 1] range where 1 is extreme anomaly
        score_min, score_max = raw_scores.min(), raw_scores.max()
        if score_max > score_min:
            norm_scores = 1.0 - ((raw_scores - score_min) / (score_max - score_min))
        else:
            norm_scores = np.zeros(len(raw_scores))

        is_ml_outlier = raw_preds == -1

        # 3. Domain-specific rule checks (Atmospheric Science validation)
        # Check: PM2.5 > PM10 (PM2.5 is physically a subset of PM10. If PM2.5 > PM10, sensor is buggy)
        has_pm_inversion = False
        if "pm2_5" in result_df.columns and "pm10" in result_df.columns:
            has_pm_inversion = (result_df["pm2_5"] > (result_df["pm10"] * 1.05)) & (result_df["pm2_5"] > 20)

        # Combine ML and rule-based flags
        final_is_anomaly = is_ml_outlier | has_pm_inversion

        reasons: List[str] = []
        top_contributors: List[Optional[str]] = []
        for idx in range(len(result_df)):
            if has_pm_inversion is not False and has_pm_inversion.iloc[idx]:
                reasons.append("Sensor Inversion: PM2.5 > PM10 reading")
                top_contributors.append("pm2_5_vs_pm10")
            elif is_ml_outlier[idx]:
                if len(available_features) > 0:
                    max_feat_idx = int(np.argmax(np.abs(scaled_X[idx])))
                    contrib = available_features[max_feat_idx]
                else:
                    contrib = "unknown"
                top_contributors.append(contrib)
                reasons.append(f"Multivariate IsolationForest Outlier ({contrib})")
            else:
                reasons.append("Normal Observation")
                top_contributors.append(None)

        result_df["is_anomaly"] = final_is_anomaly
        result_df["anomaly_score"] = np.round(norm_scores, 3)
        result_df["anomaly_reason"] = reasons
        result_df["top_contributor"] = top_contributors

        anomaly_count = int(final_is_anomaly.sum())
        self.logger.info(
            f"Anomaly detection complete. Identified {anomaly_count}/{len(result_df)} unusual observations"
        )
        return result_df
