# 10 — Resume Bullet Points, Job Description Mapping & Competency Evidence

This document maps your exact resume bullets directly to concrete code artifacts in this repository, providing you with interview defense scripts and proof points.

---

## 0. Your Resume Bullets & Implementation Proof

Here are your exact 3 resume bullets, paired with the exact files, algorithms, and interview talking points:

### Resume Bullet 1:
> **"Built an ETL pipeline to extract AQI data, validate pollutant readings, and store records in SQLite."**

- **Code Evidence**:
  - Extract: [`src/aqi_pipeline/extract.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/extract.py) (handles bounded retries, exponential backoff, HTTP 429 rate limits, and offline fixtures).
  - Transform: [`src/aqi_pipeline/transform.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/transform.py) (validates physical bounds, normalizes IST to UTC, prevents zero-imputation, and routes invalid records to quarantine).
  - Load: [`src/aqi_pipeline/load.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/load.py) (executes atomic SQLite transactions and idempotent upserts via natural key `(city, timestamp_utc)`).
- **Interview Defense (30 Seconds)**:
  *"I architected a decoupled Python ETL pipeline ingesting multi-pollutant measurements across major Indian cities. The pipeline features bounded exponential backoff retries with HTTP 429 header awareness. It cleanses data by converting local IST timestamps to canonical UTC, filters invalid readings into a dead-letter quarantine table without crashing the pipeline, and idempotently upserts records into a relational SQLite database using composite unique constraints to prevent data duplication."*

---

### Resume Bullet 2:
> **"Analyzed pollutant trends across cities and monitoring stations using SQL and data-quality checks."**

- **Code Evidence**:
  - Analytics Module: [`src/aqi_pipeline/analytics.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/analytics.py)
  - Functions: `get_city_summary_metrics()`, `get_pm_ratio_analysis()`, `get_zone_summary_metrics()`, `get_aqi_category_breakdown()`, `get_top_polluted_cities()`, `get_data_quality_report()`, `export_observations_to_csv()`.
- **Key SQL Patterns Used**:
  - Window functions and aggregations: `AVG(pm2_5)`, `MAX(provider_aqi)`, `GROUP BY city`, `GROUP BY zone`.
  - Conditional ratio logic: `CASE WHEN pm10 > 0 THEN ROUND(pm2_5 / pm10, 3) ELSE NULL END`.
  - Categorical distribution: `COUNT(*) * 100.0 / (SELECT COUNT(*) FROM aqi_observations)`.
  - Data quality audits: Comparing valid observations in `aqi_observations` against rejected records in `aqi_quarantine` to compute a live Clean Data Rate percentage.
  - Analytical dataset exports: Automated dumping of clean observations to CSV for downstream data science workflows.
- **Interview Defense (30 Seconds)**:
  *"I developed a SQL-driven analytics module that executes aggregated window queries to track diurnal trends, regional zonal metrics across Indian geography, and peak pollutant concentrations across urban centers. I implemented atmospheric science checks like PM2.5/PM10 mass ratio distributions to detect physical sensor baseline drift, and built automated data-quality audits that track quarantine rates and rejection frequencies across pipeline runs, complete with automated CSV export capabilities."*

---

### Resume Bullet 3:
> **"Applied anomaly detection with Scikit-learn and developed a Streamlit dashboard to visualize unusual readings."**

- **Code Evidence**:
  - Anomaly Detection: [`src/aqi_pipeline/anomaly.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/anomaly.py) using `sklearn.ensemble.IsolationForest`.
  - Streamlit Dashboard: [`app.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/app.py) (run via `streamlit run app.py`).
- **Technical Implementation**:
  - **Isolation Forest**: Fits an unsupervised multi-pollutant feature matrix (`pm2_5`, `pm10`, `carbon_monoxide`, `nitrogen_dioxide`, `sulphur_dioxide`, `ozone`), standardizing features and isolating unusual atmospheric episodes or sensor glitches without needing pre-labeled training data.
  - **Atmospheric Rule Inversion**: Flags physically impossible sensor states (e.g. `PM2.5 > PM10`, since PM2.5 is physically a subset of PM10).
  - **Interactive Dashboard**: A modern, dark-mode Streamlit dashboard featuring geographic city maps, live time-series trend lines (Altair), an interactive Scikit-learn anomaly scatter plot (highlighting outliers in red), dynamic health advisory alert banners based on EPA breakpoints, one-click CSV dataset export, and a live quarantine table inspector.
- **Interview Defense (30 Seconds)**:
  *"To catch subtle sensor malfunctions that pass simple threshold filters, I trained a Scikit-learn Isolation Forest model across a 6-pollutant feature vector. The model detects multivariate outliers and flags atmospheric anomalies like PM2.5/PM10 ratio inversions. I then built a full-stack Streamlit dashboard that visualizes real-time city trends, highlights ML anomalies with interactive scatter plots, issues dynamic public health advisories, and provides live pipeline execution controls."*


---

## 1. Junior Data Engineer Competency Matrix

| JD Requirement / Responsibility | How Implemented in AQI India ETL | Relevant Source Files | Boundary (What is Implemented vs. Future Scale) |
|:---|:---|:---|:---|
| **Python Programming & Scripting** | Clean modular package, type hints (`typing`), dataclasses, exception hierarchy, OOP design. | `src/aqi_pipeline/*.py` | Implemented in standard Python 3.9+; no distributed Spark/PySpark needed for this prototype scale. |
| **Data Ingestion & REST APIs** | HTTP client with connection sessions, bounded retries, exponential backoff, rate-limit awareness (`Retry-After`), offline fixture fallback. | [`extract.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/extract.py) | Synchronous batch requests with polite pacing. Asynchronous or message-queue ingestion (Kafka) would be used for sub-second streaming. |
| **Data Cleaning & Validation** | Physical boundary validation (negative values, extreme spikes), quarantine dead-letter pattern, no silent zero-imputation. | [`transform.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/transform.py) | Custom Python validation rules. In large enterprises, Great Expectations or Soda would be integrated. |
| **Timezone & Data Normalization** | Parsing local IST timestamps (UTC+05:30), generating ISO-8601 UTC timestamps for chronological database consistency. | [`transform.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/transform.py#L60-L80) | Handles fixed IST offset. Cross-day historical backfill scripts would handle arbitrary historical ranges. |
| **Relational Database Design & SQL** | Normalized SQLite schema, composite unique constraints, indexes on query predicates, parameterized queries. | [`load.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/load.py#L22-L70), [`analytics.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/analytics.py) | SQLite used for local embedded prototype; same DDL principles transfer directly to PostgreSQL/Snowflake. |
| **Idempotency & Deduplication** | `ON CONFLICT(city, timestamp_utc) DO UPDATE` ensures re-running pipeline does not create duplicate observations. | [`load.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/load.py#L90-L135) | Natural key upsert implemented at database level. Distributed deduplication would use Redis or watermark windows. |
| **Machine Learning & Anomaly Detection** | Scikit-learn `IsolationForest` across 6 atmospheric pollutants to isolate anomalous sensor spikes and physical inversions. | [`anomaly.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/anomaly.py) | Unsupervised ML running in Python; scalable via batch feature store in production. |
| **Data Visualization & Dashboards** | Interactive multi-tab Streamlit dashboard with Altair visualizations, geographic maps, and live pipeline triggers. | [`app.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/app.py) | Lightweight Streamlit web application. In enterprise, Tableau/PowerBI or Superset would be used. |
| **Transaction Management & ACID** | Explicit transaction boundaries (`BEGIN TRANSACTION`, `COMMIT`, `ROLLBACK`) ensuring atomic batch writes. | [`load.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/load.py#L120-L140) | SQLite single-file lock; production enterprise databases use multi-version concurrency control (MVCC). |
| **Observability & Auditing** | `pipeline_runs` table records run ID, status, record counts, and elapsed latency. Structured logging with run context. | [`logging_config.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/logging_config.py), [`load.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/load.py#L180-L230) | Local database table and stdout logging; enterprise production would ship logs to Datadog or Prometheus/Grafana. |
| **Testing & Quality Assurance** | Pytest suite covering mocking (`unittest.mock`), schema validation, boundary conditions, idempotency, analytics, and ML anomaly tests. | `tests/test_*.py` | 27 automated unit/integration tests passing offline; 1 optional live smoke test. |

---

## 2. Implemented Skills vs. Conceptual Knowledge

When presenting this project to interviewers, be completely honest about what is running in the codebase versus what you know conceptually:

### What is Actually Implemented & Verifiable in Code:
- A fully functioning Python ETL pipeline with CLI execution and Streamlit dashboard.
- Real HTTP extraction against Open-Meteo's live air quality API.
- Offline deterministic execution using sanitized fixtures.
- Strict data quality validation and quarantine table routing.
- Database idempotency via composite unique key `(city, timestamp_utc)`.
- ACID transaction rollback handling.
- SQL trend analytics and PM2.5/PM10 ratio calculations.
- Scikit-learn Isolation Forest anomaly detection for sensor spikes.
- Full-stack Streamlit web dashboard.
- Automated pytest suite with 27 offline tests and 1 live smoke test.

### What is Conceptual Knowledge (Future Production Work):
- **Distributed Processing (Apache Spark)**: Not used here because air quality data for 8-50 cities is small-scale (kilobytes to megabytes), where Spark's JVM overhead would be inefficient.
- **Workflow Orchestration (Apache Airflow / Dagster)**: The pipeline currently uses a Python CLI / Streamlit trigger. In production, this would be scheduled by an Airflow DAG on an hourly cron schedule.
- **Data Warehousing (Snowflake / BigQuery)**: SQLite was chosen for a self-contained, zero-cost, portable prototype. The SQL schema and upsert logic map directly to Snowflake or BigQuery.
