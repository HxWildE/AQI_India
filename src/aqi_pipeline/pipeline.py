"""
Pipeline Orchestrator and CLI Entrypoint for AQI India ETL.

Coordinates Extract, Transform, and Load stages with:
- Run ID generation and end-to-end execution timing
- Comprehensive audit metrics logging
- Live or deterministic fixture execution modes
- Clean formatted terminal summary output
"""

from __future__ import annotations
import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aqi_pipeline.config import PipelineConfig, get_config, DEFAULT_INDIAN_CITIES
from aqi_pipeline.extract import AQIExtractor
from aqi_pipeline.transform import AQITransformer
from aqi_pipeline.load import AQILoader
from aqi_pipeline.logging_config import setup_logger


class AQIPipeline:
    """Orchestrates the full AQI India ETL pipeline."""

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or get_config()
        self.logger = setup_logger("aqi_pipeline", level=self.config.log_level)
        self.extractor = AQIExtractor(self.config, logger=setup_logger("aqi_pipeline.extract", level=self.config.log_level))
        self.transformer = AQITransformer(self.config, logger=setup_logger("aqi_pipeline.transform", level=self.config.log_level))
        self.loader = AQILoader(self.config, logger=setup_logger("aqi_pipeline.load", level=self.config.log_level))

    def run(
        self,
        mode: Optional[str] = None,
        selected_cities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes an end-to-end ETL run.

        Args:
            mode: 'live' or 'fixture'
            selected_cities: Optional list of city names to filter
        """
        exec_mode = (mode or self.config.execution_mode).lower()
        self.config.execution_mode = exec_mode

        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        started_at = datetime.now(timezone.utc)

        self.logger.info("=" * 65)
        self.logger.info(f"STARTING AQI ETL PIPELINE [Run ID: {run_id}]")
        self.logger.info(f"Execution Mode: {exec_mode.upper()} | DB Path: {self.config.db_path}")
        self.logger.info("=" * 65)

        # Audit initial start
        self.loader.record_pipeline_run_start(run_id, exec_mode)

        try:
            # 1. EXTRACT
            cities_to_fetch = None
            if selected_cities:
                cities_to_fetch = {
                    c: DEFAULT_INDIAN_CITIES[c]
                    for c in selected_cities
                    if c in DEFAULT_INDIAN_CITIES
                }

            if exec_mode == "fixture":
                raw_payloads = self.extractor.extract_from_fixtures(self.config.fixture_path)
            else:
                raw_payloads = self.extractor.extract_all(cities_to_fetch)

            extracted_count = len(raw_payloads)
            self.logger.info(f"Stage 1/3 (Extract) finished: {extracted_count} raw payloads acquired")

            # 2. TRANSFORM
            trans_result = self.transformer.transform_all(raw_payloads)
            accepted_count = len(trans_result.accepted)
            quarantined_count = len(trans_result.quarantined)
            self.logger.info(
                f"Stage 2/3 (Transform) finished: {accepted_count} valid records, {quarantined_count} quarantined"
            )

            # 3. LOAD
            inserted_count, updated_count = self.loader.load_observations(trans_result.accepted)
            quar_loaded = self.loader.load_quarantine(trans_result.quarantined)
            self.logger.info(
                f"Stage 3/3 (Load) finished: {inserted_count} new, {updated_count} updated, {quar_loaded} quarantined logged"
            )

            # Audit Completion
            self.loader.record_pipeline_run_completion(
                run_id=run_id,
                status="SUCCESS",
                records_extracted=extracted_count,
                records_accepted=accepted_count,
                records_quarantined=quarantined_count,
                records_inserted=inserted_count,
                records_updated=updated_count,
                started_at_dt=started_at,
            )

            elapsed = round((datetime.now(timezone.utc) - started_at).total_seconds(), 2)
            summary = {
                "run_id": run_id,
                "status": "SUCCESS",
                "execution_mode": exec_mode,
                "started_at": started_at.isoformat(),
                "elapsed_seconds": elapsed,
                "records_extracted": extracted_count,
                "records_accepted": accepted_count,
                "records_quarantined": quarantined_count,
                "records_inserted": inserted_count,
                "records_updated": updated_count,
            }

            self.logger.info("=" * 65)
            self.logger.info(f"ETL RUN SUCCESSFUL in {elapsed}s (Run ID: {run_id})")
            self.logger.info(
                f"Summary: Extracted={extracted_count} | Accepted={accepted_count} | Inserted={inserted_count} | Updated={updated_count} | Quarantined={quarantined_count}"
            )
            self.logger.info("=" * 65)
            return summary

        except Exception as exc:
            elapsed = round((datetime.now(timezone.utc) - started_at).total_seconds(), 2)
            self.logger.error(f"PIPELINE RUN FAILED after {elapsed}s: {exc}", exc_info=True)
            self.loader.record_pipeline_run_completion(
                run_id=run_id,
                status="FAILED",
                records_extracted=0,
                records_accepted=0,
                records_quarantined=0,
                records_inserted=0,
                records_updated=0,
                started_at_dt=started_at,
                error_message=str(exc),
            )
            raise


def render_cli_summary(summary: Dict[str, Any], recent_rows: List[Dict[str, Any]]) -> None:
    """Prints a polished CLI summary using rich if available, or clean ASCII."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel

        console = Console()
        status_style = "bold green" if summary["status"] == "SUCCESS" else "bold red"

        summary_text = (
            f"[bold]Run ID:[/bold] {summary['run_id']}\n"
            f"[bold]Mode:[/bold] {summary['execution_mode'].upper()}\n"
            f"[bold]Status:[/bold] [{status_style}]{summary['status']}[/{status_style}]\n"
            f"[bold]Elapsed:[/bold] {summary['elapsed_seconds']}s\n"
            f"[bold]Records Extracted:[/bold] {summary['records_extracted']}\n"
            f"[bold]Records Accepted:[/bold] {summary['records_accepted']}\n"
            f"[bold]Records Quarantined:[/bold] {summary['records_quarantined']}\n"
            f"[bold]Database Inserts:[/bold] {summary['records_inserted']}\n"
            f"[bold]Database Updates (Idempotency):[/bold] {summary['records_updated']}"
        )
        console.print(Panel(summary_text, title="AQI India ETL Run Report", expand=False))

        if recent_rows:
            table = Table(title="Recent Clean Observations in SQLite")
            table.add_column("City", style="cyan")
            table.add_column("Timestamp (IST)", style="dim")
            table.add_column("PM2.5 (µg/m³)", justify="right")
            table.add_column("PM10 (µg/m³)", justify="right")
            table.add_column("Provider AQI", justify="right")
            table.add_column("Category", style="magenta")

            for r in recent_rows:
                table.add_row(
                    str(r["city"]),
                    str(r["timestamp_local"]),
                    f"{r['pm2_5']:.1f}" if r["pm2_5"] is not None else "N/A",
                    f"{r['pm10']:.1f}" if r["pm10"] is not None else "N/A",
                    f"{int(r['provider_aqi'])}" if r["provider_aqi"] is not None else "N/A",
                    str(r["aqi_category"]),
                )
            console.print(table)

    except ImportError:
        # Fallback to plain text
        print("\n" + "=" * 60)
        print("AQI INDIA ETL RUN REPORT")
        print("=" * 60)
        for k, v in summary.items():
            print(f"  {k:22}: {v}")
        print("=" * 60)


def main() -> None:
    """CLI Entrypoint parser."""
    parser = argparse.ArgumentParser(
        description="AQI India End-to-End ETL Pipeline CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["live", "fixture"],
        default="fixture",
        help="Pipeline execution mode: 'live' calls the real Open-Meteo API; 'fixture' uses offline JSON.",
    )
    parser.add_argument(
        "--cities",
        type=str,
        default="",
        help="Comma-separated list of Indian cities to run (e.g. 'New Delhi,Mumbai'). Defaults to all.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Custom SQLite database destination file path.",
    )
    parser.add_argument(
        "--fixture-path",
        type=str,
        default=None,
        help="Custom fixture file path for offline runs.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity level.",
    )
    parser.add_argument(
        "--show-recent",
        action="store_true",
        help="Print the most recent observations from SQLite after pipeline run.",
    )

    args = parser.parse_args()

    overrides: Dict[str, Any] = {
        "execution_mode": args.mode,
        "log_level": args.log_level,
    }
    if args.db_path:
        overrides["db_path"] = Path(args.db_path)
    if args.fixture_path:
        overrides["fixture_path"] = Path(args.fixture_path)

    config = get_config(**overrides)
    pipeline = AQIPipeline(config)

    selected_cities = [c.strip() for c in args.cities.split(",")] if args.cities else None

    try:
        summary = pipeline.run(mode=args.mode, selected_cities=selected_cities)
        recent_rows = pipeline.loader.get_recent_observations(limit=10) if args.show_recent else []
        render_cli_summary(summary, recent_rows)
    except Exception as exc:
        print(f"\n[FATAL] Pipeline execution failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
