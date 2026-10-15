"""
Configuration and Environment Settings for the AQI India ETL Pipeline.

Loads configuration from environment variables or .env file with sensible defaults,
defines geographical metadata for Indian monitoring locations, and sets physical
validation boundaries for air pollutants.
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Default target cities across diverse Indian geographic zones
DEFAULT_INDIAN_CITIES: Dict[str, Dict[str, Any]] = {
    "New Delhi": {
        "state": "Delhi",
        "zone": "North",
        "latitude": 28.6139,
        "longitude": 77.2090,
    },
    "Mumbai": {
        "state": "Maharashtra",
        "zone": "West",
        "latitude": 19.0760,
        "longitude": 72.8777,
    },
    "Bengaluru": {
        "state": "Karnataka",
        "zone": "South",
        "latitude": 12.9716,
        "longitude": 77.5946,
    },
    "Kolkata": {
        "state": "West Bengal",
        "zone": "East",
        "latitude": 22.5726,
        "longitude": 88.3639,
    },
    "Chennai": {
        "state": "Tamil Nadu",
        "zone": "South",
        "latitude": 13.0827,
        "longitude": 80.2707,
    },
    "Hyderabad": {
        "state": "Telangana",
        "zone": "South",
        "latitude": 17.3850,
        "longitude": 78.4867,
    },
    "Ahmedabad": {
        "state": "Gujarat",
        "zone": "West",
        "latitude": 23.0225,
        "longitude": 72.5714,
    },
    "Lucknow": {
        "state": "Uttar Pradesh",
        "zone": "North",
        "latitude": 26.8467,
        "longitude": 80.9462,
    },
}

# Physical plausible limits for data quality validation (in µg/m³, AQI is dimensionless)
# Values outside these bounds indicate sensor malfunctions or corrupt payloads.
POLLUTANT_VALIDATION_BOUNDS = {
    "pm2_5": {"min": 0.0, "max": 1000.0, "unit": "μg/m³"},
    "pm10": {"min": 0.0, "max": 2000.0, "unit": "μg/m³"},
    "carbon_monoxide": {"min": 0.0, "max": 50000.0, "unit": "μg/m³"},
    "nitrogen_dioxide": {"min": 0.0, "max": 1000.0, "unit": "μg/m³"},
    "sulphur_dioxide": {"min": 0.0, "max": 1000.0, "unit": "μg/m³"},
    "ozone": {"min": 0.0, "max": 1000.0, "unit": "μg/m³"},
    "us_aqi": {"min": 0.0, "max": 500.0, "unit": "USAQI"},
}


@dataclass
class PipelineConfig:
    """ETL Pipeline runtime configuration."""

    api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "AQI_API_BASE_URL", "https://air-quality-api.open-meteo.com/v1/air-quality"
        )
    )
    api_key: str | None = field(
        default_factory=lambda: os.getenv("AQI_API_KEY") or None
    )
    db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("AQI_DB_PATH", str(BASE_DIR / "aqi_india.db"))
        )
    )
    fixture_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "AQI_FIXTURE_PATH",
                str(BASE_DIR / "tests" / "fixtures" / "batch_cities_response.json"),
            )
        )
    )
    timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("AQI_TIMEOUT_SECONDS", "10.0"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("AQI_MAX_RETRIES", "3"))
    )
    backoff_factor: float = field(
        default_factory=lambda: float(os.getenv("AQI_BACKOFF_FACTOR", "1.5"))
    )
    rate_limit_delay_seconds: float = field(
        default_factory=lambda: float(os.getenv("AQI_RATE_LIMIT_DELAY", "0.2"))
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("AQI_LOG_LEVEL", "INFO").upper()
    )
    execution_mode: str = field(
        default_factory=lambda: os.getenv("AQI_EXECUTION_MODE", "live").lower()
    )
    cities: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: DEFAULT_INDIAN_CITIES.copy()
    )


def get_config(**overrides: Any) -> PipelineConfig:
    """Helper to instantiate config with optional overrides."""
    return PipelineConfig(**overrides)
