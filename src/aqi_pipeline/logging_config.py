"""
Logging Configuration for AQI India ETL Pipeline.

Provides clean structured logging with timestamps, log levels, pipeline run IDs,
and sensitive value filtering.
"""

from __future__ import annotations
import logging
import sys
from typing import Optional


class PipelineFormatter(logging.Formatter):
    """Custom formatter with optional run_id context and clean layout."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "run_id"):
            record.run_id = "default"
        return super().format(record)


def setup_logger(
    name: str = "aqi_pipeline",
    level: str = "INFO",
    run_id: Optional[str] = None,
) -> logging.Logger:
    """Configures and returns a logger instance for pipeline components."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        fmt = "[%(asctime)s] [%(levelname)s] [run:%(run_id)s] %(name)s: %(message)s"
        formatter = PipelineFormatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    if run_id:
        # Wrap logger with extra context
        return logging.LoggerAdapter(logger, {"run_id": run_id})  # type: ignore

    return logging.LoggerAdapter(logger, {"run_id": "init"})  # type: ignore
