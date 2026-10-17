# AQI India: End-to-End ETL Data Pipeline

A resilient, testable, and idempotent data engineering pipeline in Python that extracts real-time air quality observations across major Indian metropolitan cities, performs strict data validation, and loads structured observations into an analytical SQLite database.

---

## 1. Project Overview & Motivation

Air pollution is a critical public health and environmental challenge across urban India. While atmospheric models and monitoring stations produce massive streams of air quality measurements, raw API payloads frequently contain sensor anomalies, missing readings, inconsistent timestamp representations, and nested JSON structures.

This project implements an end-to-end data engineering, analytics, and machine learning system designed around core production principles:
- **Resilient Ingestion**: Bounded exponential backoff retries, explicit timeouts, and HTTP 429 rate-limit awareness (`Retry-After`).
- **Data Quality & Governance**: Strict boundary validation, timezone normalization (IST to UTC), quarantine routing for defective observations, and a zero-imputation policy for missing measurements.
- **Relational Idempotency**: Natural composite unique keys `(city, timestamp_utc)` and upsert semantics guarantee that re-running ingestion never duplicates database records.
- **SQL Trend Analytics**: Automated SQL window functions tracking city pollutant trends, diurnal distributions, and PM2.5/PM10 physical mass ratios.
- **ML Anomaly Detection**: Unsupervised `IsolationForest` model (Scikit-learn) isolating multivariate outliers, extreme spikes, and optical sensor baseline inversions.
- **Interactive Streamlit Dashboard**: Full-stack dark-mode web dashboard (`app.py`) for live monitoring, interactive map filtering, and anomaly visualization.
- **Test-Driven Architecture**: 27 automated unit and integration tests using offline mocks and sanitized fixtures, plus an optional bounded live smoke test.

---

## 2. High-Level Architecture & Workflow

```
[ Open-Meteo Air Quality REST API ] ──(Live Mode)──┐
                                                   ├──> [ Stage 1: Extract ] ──> Raw Payloads + Metadata
[ Offline JSON Fixtures (Zero Quota) ] ──(Fixture)─┘          │
                                                              ▼
                                                   [ Stage 2: Transform ]
                                                              │
                                            ┌─────────────────┴─────────────────┐
                                            ▼                                   ▼
                                     [ Valid Records ]                 [ Defective Records ]
                                            │                                   │
                                            ▼                                   ▼
                                     [ Stage 3: Load ]                  [ Quarantine Table ]
                                            │                            `aqi_quarantine`
                                            ▼
                             [ SQLite: `aqi_observations` ]
                               UNIQUE(city, timestamp_utc)
                                       │            ▲
                                       ▼            │
                         [ SQL Analytics Module ]   [ Audit: `pipeline_runs` ]
                                       │
                                       ▼
                       [ Scikit-Learn Anomaly Detection ]
                                       │
                                       ▼
                     [ Interactive Streamlit Dashboard (app.py) ]
```

### Detailed Sequence:
1. **Extract (`extract.py`)**: Fetches air quality observations for New Delhi, Mumbai, Bengaluru, Kolkata, Chennai, Hyderabad, Ahmedabad, and Lucknow. Enforces request timeouts and exponential backoff on transient errors (5xx, timeouts) while immediately aborting on permanent client errors (4xx).
2. **Transform (`transform.py`)**: Parses Indian Standard Time (IST, UTC+05:30) timestamps into ISO-8601 UTC strings. Applies physical boundary checks ($0 \le \text{PM2.5} \le 1000\,\mu\text{g/m}^3$). Segregates defective records into a quarantine list with exact rejection reasons. Preserves missing metrics as `NULL` (never replaces with `0.0`).
3. **Load (`load.py`)**: Executes an idempotent upsert (`INSERT ... ON CONFLICT DO UPDATE`) into `aqi_observations` within an atomic transaction. Logs execution metrics and status into `pipeline_runs`.
4. **Analyze (`analytics.py`)**: Executes SQL queries to compute multi-city rolling averages, PM2.5/PM10 mass ratios, and pipeline data quality health rates.
5. **Detect Anomalies (`anomaly.py`)**: Standardizes 6 atmospheric features and fits a Scikit-learn `IsolationForest` model to detect unusual multivariate pollution events and sensor glitches.
6. **Visualize (`app.py`)**: Serves an interactive Streamlit dashboard displaying geographic city maps, trend charts, and flagged anomaly scatter plots.

---

## 3. Technology Stack & Rationale

| Component | Technology | Rationale |
|:---|:---|:---|
| **Language** | Python 3.9+ | Standard language for data engineering, rich HTTP ecosystem, and native SQLite support. |
| **HTTP Client** | `requests` | Battle-tested session management, connection pooling, and header inspection. |
| **Storage** | SQLite | Lightweight, zero-configuration, self-contained relational database supporting ACID transactions and upsert syntax. |
| **Data Processing** | `pandas` | High-performance tabular data structures and window aggregation. |
| **Machine Learning**| `scikit-learn` | Unsupervised `IsolationForest` for multi-pollutant statistical anomaly detection. |
| **Web Dashboard** | `streamlit` | Reactive data dashboard visualizing maps, trends, and outliers. |
| **Visualizations** | `altair` | Declarative statistical charting for multi-pollutant correlations. |
| **Validation** | Python Dataclasses | Type-safe data containers with zero runtime framework overhead. |
| **Configuration** | `python-dotenv` | Twelve-Factor App methodology; keeps credentials and knobs outside source code. |
| **Testing** | `pytest` | Flexible test runner supporting fixtures, parametric testing, and isolated temporary directories. |
| **Terminal UI** | `rich` | Polished CLI reporting of pipeline run summaries and recent observations. |

---

## 4. Supported Data Source & API Specifications

- **Provider**: Open-Meteo Air Quality API
- **Endpoint**: `https://air-quality-api.open-meteo.com/v1/air-quality`
- **Atmospheric Model**: Copernicus Atmosphere Monitoring Service (CAMS) / ECMWF / SILAM
- **Measured Pollutants**:
  - `pm2_5`: Particulate Matter $< 2.5\,\mu\text{m}$ ($\mu\text{g/m}^3$)
  - `pm10`: Particulate Matter $< 10\,\mu\text{m}$ ($\mu\text{g/m}^3$)
  - `carbon_monoxide` (CO) ($\mu\text{g/m}^3$)
  - `nitrogen_dioxide` ($\text{NO}_2$) ($\mu\text{g/m}^3$)
  - `sulphur_dioxide` ($\text{SO}_2$) ($\mu\text{g/m}^3$)
  - `ozone` ($\text{O}_3$) ($\mu\text{g/m}^3$)
  - `us_aqi`: Provider-calculated US EPA Air Quality Index score (0–500)
- **Authentication**: None required for non-commercial free tier (up to 10,000 calls/day, 600 calls/minute). Supports optional commercial API keys via `AQI_API_KEY`.

---

## 5. Prerequisites & Quickstart

### Prerequisites
- Python 3.9 or higher (tested on Python 3.14)
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/HxWildE/AQI_India.git
cd AQI_India

# Install dependencies
python -m pip install -r requirements.txt

# Install the package in editable mode
python -m pip install -e .
```

### Environment Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|:---|:---|:---|
| `AQI_API_BASE_URL` | `https://air-quality-api.open-meteo.com/v1/air-quality` | Upstream API endpoint |
| `AQI_API_KEY` | *(empty)* | Optional commercial API key |
| `AQI_DB_PATH` | `aqi_india.db` | Destination SQLite database path |
| `AQI_TIMEOUT_SECONDS` | `10.0` | HTTP request timeout in seconds |
| `AQI_MAX_RETRIES` | `3` | Maximum retry attempts for transient errors |
| `AQI_BACKOFF_FACTOR` | `1.5` | Exponential backoff multiplier |
| `AQI_RATE_LIMIT_DELAY` | `0.2` | Polite delay between sequential city requests |
| `AQI_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `AQI_EXECUTION_MODE` | `fixture` | Default execution mode (`fixture` or `live`) |

---

## 6. Execution Commands

### 1. Launch the Interactive Streamlit Dashboard
```bash
python -m streamlit run app.py
```
Opens the interactive web dashboard displaying real-time city maps, SQL trend analytics, Scikit-learn anomaly scatter plots, and live pipeline triggers.

### 2. Run in Offline Fixture Mode (Zero Network / Zero Quota)
Ingests pre-sanitized historical observations from `tests/fixtures/batch_cities_response.json`:

```bash
python -m aqi_pipeline.pipeline --mode fixture --show-recent
```

### 3. Verify Idempotency
Execute the exact same command a second time:

```bash
python -m aqi_pipeline.pipeline --mode fixture --show-recent
```
Notice that `Database Inserts: 0` and `Database Updates: 6`. Total database rows remain unchanged.

### 4. Run in Live Mode (Real External API)
```bash
# Ingest live observations for all configured Indian cities:
python -m aqi_pipeline.pipeline --mode live --show-recent

# Ingest live observations for specific cities:
python -m aqi_pipeline.pipeline --mode live --cities "New Delhi,Mumbai" --show-recent
```

### 5. Run & Export Analytical Dataset to CSV
Export cleaned observations directly to a CSV file for analysis in Jupyter, Excel, or Tableau:

```bash
python -m aqi_pipeline.pipeline --mode fixture --export-csv "exports/clean_aqi_dataset.csv" --show-recent
```


---

## 7. Database Schema & Inspection

The pipeline automatically creates and manages three relational tables:

### 1. `aqi_observations`
Analytical table storing cleaned, validated observations:

```sql
CREATE TABLE IF NOT EXISTS aqi_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    state TEXT,
    zone TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timestamp_local TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    pm2_5 REAL,
    pm10 REAL,
    carbon_monoxide REAL,
    nitrogen_dioxide REAL,
    sulphur_dioxide REAL,
    ozone REAL,
    provider_aqi REAL,
    aqi_category TEXT NOT NULL,
    data_source TEXT NOT NULL,
    extracted_at_utc TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CONSTRAINT uq_city_timestamp UNIQUE (city, timestamp_utc)
);

CREATE INDEX IF NOT EXISTS idx_aqi_city_timestamp ON aqi_observations (city, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_aqi_category ON aqi_observations (aqi_category);
```

### 2. `aqi_quarantine`
Dead-letter audit table for defective or out-of-range sensor readings:

```sql
CREATE TABLE IF NOT EXISTS aqi_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    timestamp_local TEXT,
    rejection_reason TEXT NOT NULL,
    raw_payload_snippet TEXT,
    quarantined_at_utc TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 3. `pipeline_runs`
Audit table recording pipeline health, latency, and throughput:

```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    execution_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    records_extracted INTEGER NOT NULL DEFAULT 0,
    records_accepted INTEGER NOT NULL DEFAULT 0,
    records_quarantined INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_updated INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    elapsed_seconds REAL,
    error_message TEXT
);
```

---

## 8. Testing Strategy & Verification

The test suite covers unit logic, network failure modes, boundary validation, database idempotency, and end-to-end integration:

```bash
# Run all automated tests (offline, fast, mocked):
python -m pytest

# Run with verbose test-by-test breakdown:
python -m pytest -v

# Run optional live API smoke test against real Open-Meteo endpoint:
python -m pytest -v --run-live tests/test_live_smoke.py
```

### Verified Test Suite Breakdown (28 Automated + 1 Live Smoke):
- `tests/test_analytics.py`:
  - `test_analytics_metrics_and_summary` (SQL window aggregations, PM2.5/PM10 ratio logic, data quality health audits)
  - `test_zone_and_category_analytics_and_export` (Zonal regional metrics, AQI category breakdown, top polluted cities, and CSV dataset export)
- `tests/test_anomaly.py`:
  - `test_anomaly_detection_with_outlier` (Scikit-learn Isolation Forest multi-pollutant outlier detection)
  - `test_domain_rule_pm_inversion_detected` (Atmospheric optical sensor PM2.5 > PM10 inversion rule check)
- `tests/test_extract.py`:
  - `test_fetch_city_success_mocked` (HTTP 200 payload ingestion & metadata tagging)
  - `test_fetch_city_rate_limit_with_retry_after` (HTTP 429 backoff & header parsing)
  - `test_fetch_city_5xx_server_error_retry` (Transient 500 error backoff retries)
  - `test_fetch_city_400_client_error_aborts_immediately` (Permanent 400 error immediate abort)
  - `test_fetch_city_timeout_exhaustion` (Connection timeout retry exhaustion)
  - `test_fetch_city_invalid_json` (JSON decode error handling)
  - `test_extract_from_fixtures` (Offline fixture reading)
- `tests/test_transform.py`:
  - `test_transform_valid_observation` (Dataclass mapping & category assignment)
  - `test_timestamp_parsing_ist_and_utc` (Local IST to canonical UTC conversion)
  - `test_missing_values_preserved_as_none` (Zero-imputation prevention)
  - `test_negative_pollutant_quarantined` (Negative reading rejection)
  - `test_out_of_range_pollutant_quarantined` (Out-of-bounds rejection)
  - `test_malformed_timestamp_quarantined` (Corrupted timestamp rejection)
  - `test_empty_core_pollutants_quarantined` (All-null payload rejection)
  - `test_us_aqi_category_mapping` (US EPA category thresholds)
- `tests/test_load.py`:
  - `test_init_schema_creates_tables_and_indexes` (DDL schema generation)
  - `test_load_observations_inserts_records` (Relational insertion)
  - `test_idempotency_loading_same_record_twice` (Zero duplicates on rerun)
  - `test_load_quarantine_records` (Quarantine table insertion)
  - `test_transaction_rollback_on_failure` (Atomic rollback on error)
- `tests/test_pipeline.py`:
  - `test_full_fixture_e2e_run` (Full pipeline execution)
  - `test_e2e_idempotency_on_rerun` (End-to-end idempotency audit)
  - `test_pipeline_with_malformed_fixture_routes_to_quarantine` (Quarantine handling)
  - `test_pipeline_failure_audit_logging` (Failure state audit in `pipeline_runs`)
- `tests/test_live_smoke.py`:
  - `test_live_api_smoke_bounded` (Optional live smoke test against live Open-Meteo API)

---

## 9. Repository Structure

```
AQI_India/
├── app.py                        # Streamlit web dashboard & anomaly visualizer
├── src/
│   └── aqi_pipeline/
│       ├── __init__.py           # Package initialization
│       ├── analytics.py          # SQL analytics, zonal metrics, CSV export
│       ├── anomaly.py            # Scikit-learn IsolationForest & domain rules
│       ├── config.py             # Config, city metadata, pollutant bounds
│       ├── extract.py            # HTTP extraction, retries, backoff, fixtures
│       ├── transform.py          # Validation, IST/UTC timestamps, quarantine
│       ├── load.py               # SQLite storage, idempotency, audit logs
│       ├── pipeline.py           # Orchestrator & Rich CLI interface
│       └── logging_config.py     # Structured logging with run_id
├── tests/
│   ├── fixtures/
│   │   ├── batch_cities_response.json   # Multi-city offline test fixture
│   │   ├── live_sample_response.json    # Sanitized real API response
│   │   └── malformed_response.json      # Defective records for quarantine testing
│   ├── conftest.py               # Pytest fixtures and tmp_path setup
│   ├── test_analytics.py         # SQL analytics & reporting unit tests
│   ├── test_anomaly.py           # Isolation Forest outlier detection tests
│   ├── test_extract.py           # Extraction & network mock unit tests
│   ├── test_transform.py         # Transformation & validation unit tests
│   ├── test_load.py              # SQLite & idempotency unit tests
│   ├── test_pipeline.py          # End-to-end integration tests
│   └── test_live_smoke.py        # Optional bounded live smoke test
├── .env.example                  # Environment configuration template
├── .gitignore                    # Excludes secrets, databases, caches
├── pyproject.toml                # Build system & pytest configuration
├── requirements.txt              # Production & test dependencies
└── README.md                     # Project documentation
```

---

## 10. Current Limitations & Production Roadmap

- **Storage Engine**: SQLite provides an isolated, portable local database, but is bounded to a single concurrent writer. Migrating to PostgreSQL or Snowflake with connection pooling (`pgbouncer`) would support hundreds of concurrent writers.
- **Extraction Concurrency**: Ingestion runs sequentially across cities (~4 seconds for 8 cities). An asynchronous worker pool (`asyncio` / `aiohttp`) would scale ingestion to 5,000+ monitoring stations.
- **Calculated NAQI**: The pipeline currently stores the provider-calculated US AQI (`provider_aqi`). Calculating the official Indian Central Pollution Control Board (CPCB) National AQI requires 24-hour rolling average concentrations, which will be implemented via scheduled aggregation views.
- **Orchestration**: The pipeline is triggered via a Python CLI. In production, this command would be scheduled on an hourly cron schedule via Apache Airflow or Dagster.

---

## 11. License

This project is licensed under the MIT License.
