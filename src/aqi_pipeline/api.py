"""
FastAPI REST API Gateway for AQI India Intelligence Platform.

Provides high-performance HTTP endpoints for:
- Observation querying with city and zonal filtering
- SQL analytics and atmospheric consistency (PM ratio, diurnal cycles)
- Machine learning anomaly detection via Scikit-learn Isolation Forest
- Asynchronous pipeline triggering via BackgroundTasks
- Automated OpenAPI documentation (/docs, /redoc)
"""

from __future__ import annotations
import io
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from aqi_pipeline.config import PipelineConfig, get_config
from aqi_pipeline.pipeline import AQIPipeline
from aqi_pipeline.analytics import AQIAnalytics
from aqi_pipeline.anomaly import AQIAnomalyDetector


# Pydantic Schemas for Request & Response validation
class PipelineTriggerRequest(BaseModel):
    mode: str = Field(default="fixture", description="Execution mode: 'live' or 'fixture'")
    cities: Optional[List[str]] = Field(default=None, description="Optional list of specific cities to run")


class PipelineTriggerResponse(BaseModel):
    status: str
    message: str
    mode: str
    selected_cities: Optional[List[str]] = None


class HealthStatusResponse(BaseModel):
    status: str
    total_records_processed: int
    accepted_observations: int
    quarantined_records: int
    clean_rate_percent: float
    total_pipeline_runs: int
    quarantine_reasons: List[Dict[str, Any]]


def create_app(config: Optional[PipelineConfig] = None) -> FastAPI:
    """Factory function to build and configure the FastAPI application."""
    app_config = config or get_config()
    pipeline = AQIPipeline(app_config)
    analytics = AQIAnalytics(app_config)
    detector = AQIAnomalyDetector()

    app = FastAPI(
        title="AQI India Intelligence API",
        description="High-performance REST API Gateway for India Air Quality ETL, SQL Analytics & ML Anomaly Detection.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/", tags=["System"])
    def root() -> Dict[str, Any]:
        """Root endpoint returning API metadata and navigation links."""
        return {
            "title": "AQI India Intelligence API",
            "version": "1.0.0",
            "status": "HEALTHY",
            "documentation": "/docs",
            "endpoints": [
                "/health",
                "/observations",
                "/analytics/cities",
                "/analytics/zones",
                "/analytics/pm-ratio",
                "/analytics/diurnal",
                "/analytics/export",
                "/anomaly/detect",
                "/pipeline/trigger",
            ],
        }

    @app.get("/health", response_model=HealthStatusResponse, tags=["System"])
    def health_check() -> Dict[str, Any]:
        """Audits pipeline health, accepted vs quarantined records, and clean data rate."""
        report = analytics.get_data_quality_report()
        report["status"] = "OK" if report["clean_rate_percent"] >= 70.0 else "DEGRADED"
        return report

    @app.get("/observations", tags=["Observations"])
    def get_observations(
        city: Optional[str] = Query(None, description="Filter by city name (e.g. 'New Delhi')"),
        zone: Optional[str] = Query(None, description="Filter by geographical zone (North, South, East, West)"),
        category: Optional[str] = Query(None, description="Filter by US EPA AQI category"),
        limit: int = Query(50, ge=1, le=500, description="Maximum number of observations to return"),
    ) -> List[Dict[str, Any]]:
        """Queries clean, validated air quality observations with optional spatial and category filtering."""
        df = analytics.get_all_observations_df()
        if df.empty:
            return []

        if city:
            df = df[df["city"].str.lower() == city.lower().strip()]
        if zone:
            df = df[df["zone"].str.lower() == zone.lower().strip()]
        if category:
            df = df[df["aqi_category"].str.lower() == category.lower().strip()]

        records = df.head(limit).to_dict(orient="records")
        # Sanitize NaN values for strict JSON compliance
        return [{k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()} for r in records]

    @app.get("/analytics/cities", tags=["Analytics"])
    def get_city_metrics() -> List[Dict[str, Any]]:
        """Returns aggregated average and peak pollutant levels per city."""
        df = analytics.get_city_summary_metrics()
        records = df.to_dict(orient="records")
        return [{k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()} for r in records]

    @app.get("/analytics/zones", tags=["Analytics"])
    def get_zone_metrics() -> List[Dict[str, Any]]:
        """Returns regional zone-level aggregated air quality summaries."""
        df = analytics.get_zone_summary_metrics()
        records = df.to_dict(orient="records")
        return [{k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()} for r in records]

    @app.get("/analytics/pm-ratio", tags=["Analytics"])
    def get_pm_ratio_metrics() -> List[Dict[str, Any]]:
        """Returns PM2.5/PM10 physical mass ratios to detect atmospheric optical sensor drift."""
        df = analytics.get_pm_ratio_analysis()
        records = df.to_dict(orient="records")
        return [{k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()} for r in records]

    @app.get("/analytics/diurnal", tags=["Analytics"])
    def get_diurnal_trends() -> List[Dict[str, Any]]:
        """Returns diurnal pollution distributions across 24-hour cycles."""
        df = analytics.get_hourly_diurnal_trends()
        records = df.to_dict(orient="records")
        return [{k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()} for r in records]

    @app.get("/analytics/export", tags=["Analytics"])
    def export_csv() -> StreamingResponse:
        """Streams the entire clean observation dataset as a downloadable CSV file."""
        df = analytics.get_all_observations_df()
        stream = io.StringIO()
        df.to_csv(stream, index=False)
        stream.seek(0)
        return StreamingResponse(
            iter([stream.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=aqi_observations_export.csv"},
        )

    @app.post("/anomaly/detect", tags=["Machine Learning"])
    def detect_anomalies(
        contamination: float = Query(0.10, ge=0.01, le=0.5, description="Expected proportion of outliers")
    ) -> List[Dict[str, Any]]:
        """
        Executes Scikit-learn Isolation Forest on observations to identify multivariate anomalies
        and physical optical sensor inversions.
        """
        df = analytics.get_all_observations_df()
        if df.empty or len(df) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient observation data to run Isolation Forest anomaly detection.",
            )

        detector.contamination = contamination
        scored_df = detector.detect_anomalies(df)
        anomalies = scored_df[scored_df["is_anomaly"]]

        records = anomalies.to_dict(orient="records")
        return [{k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()} for r in records]

    @app.post("/pipeline/trigger", status_code=status.HTTP_202_ACCEPTED, response_model=PipelineTriggerResponse, tags=["Orchestration"])
    def trigger_pipeline(
        payload: PipelineTriggerRequest,
        background_tasks: BackgroundTasks,
    ) -> Dict[str, Any]:
        """
        Triggers an ingestion batch in the background via BackgroundTasks.
        Returns 202 Accepted immediately to prevent blocking HTTP clients.
        """
        mode = payload.mode.lower().strip()
        if mode not in ("live", "fixture"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid execution mode. Must be 'live' or 'fixture'.",
            )

        background_tasks.add_task(pipeline.run, mode=mode, selected_cities=payload.cities)
        return {
            "status": "ACCEPTED",
            "message": f"Pipeline execution triggered in {mode.upper()} mode.",
            "mode": mode,
            "selected_cities": payload.cities,
        }

    return app


# Default application instance for uvicorn
app = create_app()
