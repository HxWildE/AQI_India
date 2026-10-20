# 01 — Setup, Execution & Verification Guide

This tutorial walks through setting up the Python environment, executing both fixture-based offline runs and real-time live API runs, exporting analytical datasets to CSV, launching the interactive Streamlit dashboard, inspecting SQLite database tables, and verifying the test suite.

---

## 1. Prerequisites & Environment Check

The pipeline requires **Python 3.9+** (tested and verified on Python 3.14). Verify your local runtime:

```powershell
python --version
pip --version
```

---

## 2. Installation

Install dependencies and register the `aqi_pipeline` package in editable mode:

```powershell
# 1. Install dependencies from requirements.txt
python -m pip install -r requirements.txt

# 2. Install the package in editable mode (links src/ to active Python environment)
python -m pip install -e .
```

---

## 3. Running in Offline Fixture Mode

Fixture mode uses pre-sanitized historical observations stored in `tests/fixtures/batch_cities_response.json`. It requires **zero external network access** and consumes **zero API quota**.

Run the complete pipeline:

```powershell
python -m aqi_pipeline.pipeline --mode fixture --show-recent
```

### Expected Output

```text
[INFO] [run:init] aqi_pipeline: =================================================================
[INFO] [run:init] aqi_pipeline: STARTING AQI ETL PIPELINE [Run ID: run_20261019_...]
[INFO] [run:init] aqi_pipeline: Execution Mode: FIXTURE | DB Path: .../aqi_india.db
[INFO] [run:init] aqi_pipeline: =================================================================
[INFO] [run:init] aqi_pipeline.extract: Loaded 6 city fixture records
[INFO] [run:init] aqi_pipeline: Stage 1/3 (Extract) finished: 6 raw payloads acquired
[INFO] [run:init] aqi_pipeline.transform: Transformation complete. Accepted: 6, Quarantined: 0
[INFO] [run:init] aqi_pipeline: Stage 2/3 (Transform) finished: 6 valid records, 0 quarantined
[INFO] [run:init] aqi_pipeline.load: Loaded observations: 6 inserted, 0 updated
[INFO] [run:init] aqi_pipeline: Stage 3/3 (Load) finished: 6 new, 0 updated, 0 quarantined logged
[INFO] [run:init] aqi_pipeline: ETL RUN SUCCESSFUL in 0.05s
```

---

## 4. Verifying Idempotency

Execute the exact same command a second time:

```powershell
python -m aqi_pipeline.pipeline --mode fixture --show-recent
```

Observe the difference in the load summary:
- **First run**: `Loaded observations: 6 inserted, 0 updated`
- **Second run**: `Loaded observations: 0 inserted, 6 updated`

Because `(city, timestamp_utc)` is defined as a natural unique constraint in the SQLite schema, the upsert logic updates existing timestamps rather than duplicating rows. The total row count in `aqi_observations` remains exactly 6!

---

## 5. Running in Live Mode (Real API)

To ingest live, real-time air quality data for Indian cities from Open-Meteo:

```powershell
# Run for all configured cities:
python -m aqi_pipeline.pipeline --mode live --show-recent

# Or run for a bounded subset of cities:
python -m aqi_pipeline.pipeline --mode live --cities "New Delhi,Mumbai" --show-recent
```

---

## 6. Running with CSV Dataset Export

Export the cleaned, validated observations directly to a standardized CSV file:

```powershell
python -m aqi_pipeline.pipeline --mode fixture --export-csv "exports/clean_observations.csv" --show-recent
```

---

## 7. Launching the Interactive Streamlit Dashboard

Launch the full-stack web dashboard:

```powershell
python -m streamlit run app.py
```

Features accessible in your browser (`http://localhost:8501`):
1. **Live Triggering**: Execute live or fixture ETL runs directly from the sidebar.
2. **Top Metric Cards**: Clean Observations, Clean Data Rate %, Peak Recorded AQI, ML Outliers.
3. **Dynamic Health Advisory**: Color-coded banners reflecting peak AQI levels.
4. **Tab 1 — City Observations & Map**: Interactive geographic map, city cards, temporal trends, and CSV dataset download.
5. **Tab 2 — SQL Trend Analysis**: City AQI comparisons, PM2.5/PM10 ratio scatter plots, regional zonal insights, and category distributions.
6. **Tab 3 — Scikit-Learn Anomaly Detection**: 2D scatter plot highlighting multivariate outliers, with individual observation scores and reasons.
7. **Tab 4 — Data Quality & Quarantine**: Data quality rejection breakdowns and real-time execution audit logs.

---

## 8. Inspecting Database Records Programmatically

You can query the generated SQLite database using standard Python one-liners or via our analytical API:

### View Recent Clean Observations
```powershell
python -c "
import sqlite3
conn = sqlite3.connect('aqi_india.db')
cursor = conn.cursor()
cursor.execute('SELECT city, timestamp_local, pm2_5, pm10, provider_aqi, aqi_category FROM aqi_observations ORDER BY timestamp_utc DESC LIMIT 5;')
for row in cursor.fetchall():
    print(row)
"
```

### View SQL Analytics Programmatically
```powershell
python -c "
from aqi_pipeline.analytics import AQIAnalytics
analytics = AQIAnalytics()
print('--- ZONAL SUMMARY ---')
print(analytics.get_zone_summary_metrics())
print('--- CATEGORY BREAKDOWN ---')
print(analytics.get_aqi_category_breakdown())
"
```

### View Pipeline Audit Logs
```powershell
python -c "
import sqlite3
conn = sqlite3.connect('aqi_india.db')
cursor = conn.cursor()
cursor.execute('SELECT run_id, execution_mode, status, records_extracted, records_inserted, records_updated, elapsed_seconds FROM pipeline_runs ORDER BY started_at DESC LIMIT 5;')
for row in cursor.fetchall():
    print(row)
"
```

---

## 9. Running the Automated Test Suite

```powershell
# Run all unit and integration tests (30 automated tests, offline, fast, mocked):
python -m pytest

# Run the test suite with coverage/verbosity:
python -m pytest -v

# Run the optional bounded live smoke test against the live API:
python -m pytest -v --run-live tests/test_live_smoke.py
```
