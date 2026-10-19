# 08 — Codebase Walkthrough & Module Breakdown

This document provides a guided tour through every source file in `src/aqi_pipeline/`, detailing the responsibilities, key functions, design rationale, and code symbols.

---

## 1. `config.py` — Pipeline Configuration & Environment

- **File Path**: [`src/aqi_pipeline/config.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/config.py)
- **Role**: Centralized configuration management using Python dataclasses and `python-dotenv`.

### Key Elements:
- `DEFAULT_INDIAN_CITIES`: A mapping of metropolitan Indian cities to geographic coordinates (latitude, longitude), administrative states, and geographic zones (North, South, East, West).
- `POLLUTANT_VALIDATION_BOUNDS`: Physical plausible limits for PM2.5, PM10, CO, NO2, SO2, O3, and US AQI.
- `PipelineConfig`: Dataclass aggregating all runtime knobs (API endpoints, credentials, SQLite file path, timeout seconds, retry counts, logging levels).
- `get_config(**overrides)`: Factory function enabling dynamic parameter overriding in tests and CLI invocations.

---

## 2. `logging_config.py` — Structured Observability

- **File Path**: [`src/aqi_pipeline/logging_config.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/logging_config.py)
- **Role**: Provides structured console logging with timestamping, module names, and pipeline run IDs.

### Key Elements:
- `PipelineFormatter`: Custom formatter that injects `[run:<run_id>]` into every log line for traceability.
- `setup_logger(name, level, run_id)`: Configures a `logging.LoggerAdapter` ensuring logs from different modules share a unified layout without duplicating handlers across child loggers (`logger.propagate = False`).

---

## 3. `extract.py` — Resilient Data Extraction

- **File Path**: [`src/aqi_pipeline/extract.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/extract.py)
- **Role**: Interacts with the Open-Meteo REST API and offline test fixtures.

### Key Methods:
- `fetch_city_data(city_name, latitude, longitude)`:
  - Executes HTTP GET requests using `requests.Session`.
  - Enforces explicit timeouts (`timeout_seconds`).
  - Implements bounded retries with exponential backoff on transient errors (5xx, timeouts, connection drops).
  - Handles HTTP 429 by inspecting the `Retry-After` header.
  - Aborts immediately on permanent 4xx client errors without useless retries.
  - Enriches raw JSON with `_metadata` (UTC timestamp, data source, execution mode).
- `extract_from_fixtures(fixture_path)`:
  - Reads pre-sanitized JSON fixtures from disk for deterministic, zero-network testing.
- `extract_all(cities)`:
  - Iterates through configured cities, incorporating pacing delays (`rate_limit_delay_seconds`) to avoid burst rate limiting.

---

## 4. `transform.py` — Schema Normalization & Validation

- **File Path**: [`src/aqi_pipeline/transform.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/transform.py)
- **Role**: Validates data quality, parses timezones, and converts raw JSON into typed dataclasses.

### Key Classes & Methods:
- `ObservationRecord`: Dataclass holding clean, validated air quality measurements ready for database insertion.
- `QuarantineRecord`: Dataclass holding rejected observations with the exact rejection reason and raw JSON snippet.
- `TransformationResult`: Container bundling `accepted: List[ObservationRecord]` and `quarantined: List[QuarantineRecord]`.
- `parse_timestamp(raw_time)`: Parses ISO-8601 strings from the API, associates the Indian Standard Time (IST, UTC+05:30) offset, and computes canonical UTC strings.
- `validate_pollutant(name, raw_value)`: Checks numeric types, non-negativity, and upper physical limits. Preserves `None` as missing (never replaces with zero).
- `get_us_aqi_category(aqi)`: Classifies the provider's US AQI score into standard advisory brackets ("Good", "Moderate", "Unhealthy", etc.).
- `transform_single(raw_payload)`: Core business logic function routing valid records to `ObservationRecord` and invalid records to `QuarantineRecord`.

---

## 5. `load.py` — SQLite Storage & Idempotency

- **File Path**: [`src/aqi_pipeline/load.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/load.py)
- **Role**: Manages relational storage, schema initialization, and transactional upserts.

### Key Elements:
- `SCHEMA_DDL`: SQL script defining `aqi_observations`, `aqi_quarantine`, and `pipeline_runs` tables, along with composite indexes.
- `load_observations(records)`:
  - Wraps batch writes in an explicit transaction (`BEGIN TRANSACTION` / `COMMIT` / `ROLLBACK`).
  - Executes `INSERT ... ON CONFLICT(city, timestamp_utc) DO UPDATE`.
  - Checks pre-existence to accurately track `records_inserted` versus `records_updated`.
- `load_quarantine(records)`: Persists rejected payloads for data quality auditing.
- `record_pipeline_run_start()` and `record_pipeline_run_completion()`: Records run telemetry (start time, finish time, elapsed seconds, record counts, exit status).

---

## 6. `pipeline.py` — Orchestrator & CLI

- **File Path**: [`src/aqi_pipeline/pipeline.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/pipeline.py)
- **Role**: Top-level coordinator and command-line interface.

### Key Elements:
- `AQIPipeline.run(mode, selected_cities)`: Orchestrates Extract -> Transform -> Load stages, calculates total elapsed run time, and records run results.
- `render_cli_summary(summary, recent_rows)`: Renders terminal summary tables using `rich` if installed, or clean ASCII formatting.
- `main()`: Command-line entrypoint parsing `--mode`, `--cities`, `--db-path`, `--show-recent`, and `--export-csv` flags.

---

## 7. `analytics.py` — SQL Trend Analytics & CSV Export

- **File Path**: [`src/aqi_pipeline/analytics.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/analytics.py)
- **Role**: Executes optimized SQLite analytical queries, calculates atmospheric ratios, and handles dataset exports.

### Key Methods:
- `get_all_observations_df()`: Fetches all clean observations as a pandas DataFrame ordered chronologically.
- `get_city_summary_metrics()`: SQL aggregation computing `AVG()` and `MAX()` for PM2.5, PM10, and AQI per city.
- `get_pm_ratio_analysis()`: Computes the PM2.5/PM10 mass concentration ratio per observation using SQL `CASE` logic.
- `get_zone_summary_metrics()`: Aggregates average pollutant levels across Indian geographic zones (`North`, `South`, `East`, `West`).
- `get_aqi_category_breakdown()`: Calculates counts and percentages of observations falling into each US EPA AQI category.
- `get_top_polluted_cities(limit)`: Ranks top polluted cities ordered by `avg_aqi DESC`.
- `get_data_quality_report()`: Audits clean vs. quarantined records to calculate overall Clean Data Rate percentage.
- `export_observations_to_csv(output_path)`: Exports the clean analytical dataset to CSV for external tools (Excel, Jupyter, Tableau).

---

## 8. `anomaly.py` — Scikit-Learn Anomaly Detection Engine

- **File Path**: [`src/aqi_pipeline/anomaly.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/anomaly.py)
- **Role**: Applies unsupervised machine learning to detect atmospheric outliers and optical sensor malfunctions.

### Key Elements:
- `AQIAnomalyDetector`: Core ML detector wrapping Scikit-learn's `IsolationForest` (100 estimators, 15% contamination).
- **Feature Space**: Standardizes 6 atmospheric pollutants simultaneously: `pm2_5`, `pm10`, `carbon_monoxide`, `nitrogen_dioxide`, `sulphur_dioxide`, and `ozone`.
- **Median Imputation & Scaling**: Imputes missing columns via median and scales features to zero-mean and unit-variance using `StandardScaler`.
- **Anomaly Scoring**: Inverts and normalizes Isolation Forest decision functions into an intuitive `[0, 1]` score where 1.0 represents an extreme outlier.
- **Physical Inversion Check**: Flags sensor baseline inversions where $PM_{2.5} > 1.05 \times PM_{10}$ (for $PM_{2.5} > 20\,\mu\text{g/m}^3$).

---

## 9. `app.py` — Full-Stack Streamlit Intelligence Dashboard

- **File Path**: [`app.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/app.py)
- **Role**: Interactive web dashboard providing live monitoring, data exploration, and health alerting.

### Key Features:
- **Real-Time KPI Cards**: Clean Observations, Clean Data Rate %, Peak Recorded AQI, and ML Outliers Detected.
- **Dynamic Health Advisory**: Color-coded alert banner reflecting the worst active AQI across selected cities (Good, Moderate, Unhealthy for Sensitive Groups, Unhealthy, Very Unhealthy, Hazardous).
- **Tab 1: City Observations & Map**: Renders an interactive map of Indian cities, latest summary metrics, time-series pollutant trends, and a direct CSV dataset download button.
- **Tab 2: SQL Trend Analysis**: Visualizes city AQI comparisons, PM2.5/PM10 ratio scatter plots, zonal comparisons, and AQI category breakdowns.
- **Tab 3: Scikit-Learn Anomaly Detection**: 2D scatter plots separating normal observations from ML outliers, with score and reasoning breakdowns.
- **Tab 4: Data Quality & Quarantine**: Rejection reasons audit tables and live `pipeline_runs` telemetry.

