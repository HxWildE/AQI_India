# 03 — ETL Architecture from Scratch

Data engineering is fundamentally about moving data reliably from where it is generated to where it can be queried and analyzed. This guide explores the core concepts of ETL and contrasts them with modern ELT paradigms.

---

## 1. ETL vs. ELT: Conceptual Differences

```
Traditional ETL:
[ Source ] ──> [ Extract ] ──> [ Transform (in Python memory) ] ──> [ Load (Clean data into DB) ]

Modern ELT:
[ Source ] ──> [ Extract ] ──> [ Load (Raw JSON into Data Lake/Warehouse) ] ──> [ Transform (via dbt/SQL) ]
```

### Why We Chose ETL for This Project
1. **Source Protection & Database Integrity**: Raw public API responses contain nested JSON structures, missing fields, and potential sensor anomalies. Cleaning and validating *before* loading ensures our relational database only stores verified observations.
2. **Lightweight & Self-Contained**: Storing raw untyped JSON blobs in an SQLite database would shift the transformation burden onto analytical queries, degrading performance on resource-constrained embedded systems.
3. **Data Quality Gatekeeping**: ETL creates a clear boundary: defective records are rejected *before* they pollute analytical tables.

---

## 2. Deep Dive: The Three Stages

### Stage 1: Extract (`src/aqi_pipeline/extract.py`)
- **Single Responsibility**: Communicating with external providers (or local fixture files), handling network transport failures, and acquiring raw data.
- **Output**: A raw dictionary or list of dictionaries directly reflecting provider schema, augmented with provenance metadata:
  ```python
  payload["_metadata"] = {
      "city": "New Delhi",
      "extracted_at_utc": "2026-10-15T18:00:00Z",
      "source": "open-meteo-air-quality-api",
      "execution_mode": "live",
  }
  ```

### Stage 2: Transform (`src/aqi_pipeline/transform.py`)
- **Single Responsibility**: Business logic, schema mapping, boundary validation, and sanitization.
- **Key Actions**:
  - Unnesting deep JSON dictionaries (`payload["current"]["pm2_5"]`).
  - Parsing local timestamps into consistent ISO UTC format.
  - Rejecting anomalous or impossible values (e.g. negative PM2.5 or PM10 > 2000 µg/m³).
  - Splitting records into two distinct streams: `accepted` (valid `ObservationRecord`s) and `quarantined` (defective `QuarantineRecord`s).
- **Zero-Imputation Policy**: Missing values stay `None` (SQL `NULL`). They are **never** replaced with `0.0`.

### Stage 3: Load (`src/aqi_pipeline/load.py`)
- **Single Responsibility**: Persisting data into relational storage (SQLite), maintaining unique constraints, and recording audit metrics.
- **Key Actions**:
  - Creating tables and indexes if they do not exist.
  - Performing atomic upserts (`INSERT ... ON CONFLICT DO UPDATE`).
  - Managing transactional boundaries (`BEGIN`, `COMMIT`, `ROLLBACK`).
  - Auditing pipeline runs in `pipeline_runs`.

---

## 3. Decoupling and Single Responsibility Principle (SRP)

Notice how cleanly separated these stages are:
- `AQIExtractor` does not know SQLite exists.
- `AQILoader` does not know whether data came from HTTP, a CSV file, or a mock fixture.
- `AQITransformer` is purely deterministic business logic: given an input dictionary, it outputs dataclass records without performing any network or database I/O.

This makes unit testing straightforward: we can test `AQITransformer` with zero mocks, and test `AQIExtractor` by mocking only HTTP responses!

---

## 4. Downstream Consumption: From Storage to Analytics, ML & Dashboard

Loading data into SQLite is not the end of the data engineering lifecycle—it is the foundation for downstream consumption:

1. **SQL Analytics Engine (`src/aqi_pipeline/analytics.py`)**: Executes window queries and aggregations over `aqi_observations` to calculate city metrics, PM2.5/PM10 ratio physics, regional zonal comparisons, and AQI category breakdowns.
2. **ML Anomaly Detection Engine (`src/aqi_pipeline/anomaly.py`)**: Consumes cleaned tabular observations and applies an unsupervised Scikit-learn `IsolationForest` across 6 features to isolate multivariate outliers and atmospheric sensor inversions.
3. **Interactive Streamlit Dashboard (`app.py`)**: Renders real-time KPIs, geographic maps, dynamic health advisory banners, and enables users to download filtered datasets as CSV.

