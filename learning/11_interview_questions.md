# 11 — Interview Preparation & Question Bank

This document is your master interview preparation guide. It contains your 60-second pitch, 2-minute architecture explanation, the lifecycle journey of a single record, and a multi-level question bank grounded in the actual codebase.

---

## 1. The 60-Second Elevator Pitch

> "I built an end-to-end data engineering, analytics, and machine learning platform in Python that ingests air quality and pollutant observations across major Indian metropolitan cities from the Open-Meteo REST API into a structured SQLite database. 
> 
> Rather than just making an API call, I engineered production data pipeline patterns: bounded exponential backoff retries with HTTP 429 rate-limit handling, strict schema validation and quarantine routing for corrupted sensor data without silent zero-imputation, and guaranteed database idempotency using composite natural keys on city and UTC timestamp. 
> 
> Downstream, I built a SQL analytics engine tracking zonal trends and PM mass ratios, a Scikit-learn Isolation Forest model detecting multivariate sensor anomalies, and an interactive Streamlit dashboard with dynamic public health advisories and CSV export. The codebase is tested with a 30-test pytest suite using offline mocks, and includes a zero-dependency fixture mode so anyone can verify it end-to-end without an API key."

---

## 2. The Two-Minute Architecture Walkthrough

> "The pipeline follows a decoupled 4-tier architecture:
> 
> First, the **Extract Stage** queries the Open-Meteo Air Quality endpoint for configured Indian cities like Delhi, Mumbai, and Bengaluru. It uses explicit HTTP timeouts and bounded exponential backoff retries. If the server responds with HTTP 429 Too Many Requests, it inspects the `Retry-After` header to avoid overwhelming the provider. For permanent 4xx errors, it fails fast without retrying. It enriches raw payloads with ingestion metadata like UTC timestamps and provenance source.
> 
> Second, the **Transform Stage** acts as a data quality gatekeeper. It parses local Indian Standard Time (IST) timestamps into canonical ISO-8601 UTC strings. It applies physical boundary checks—such as ensuring PM2.5 is between 0 and 1,000 µg/m³. If a record contains negative values or unparseable timestamps, it doesn't crash the pipeline; instead, it diverts the record into a `QuarantineRecord`. Crucially, missing values remain `None`—they are never zero-imputed.
> 
> Third, the **Load Stage** persists accepted records into SQLite. It enforces idempotency using a composite unique constraint on `(city, timestamp_utc)`. Running the pipeline twice on the same data performs an `ON CONFLICT DO UPDATE` upsert, updating existing records instead of creating duplicates. All batch writes run inside an atomic transaction, rolling back on failure. Finally, run-level metrics—records extracted, accepted, quarantined, and inserted—are committed to a `pipeline_runs` audit table.
> 
> Fourth, the **Intelligence & Analytics Tier** consumes clean observations: `analytics.py` executes SQL window queries for regional zonal metrics and PM mass ratios, `anomaly.py` applies an unsupervised Scikit-learn `IsolationForest` across 6 pollutant features to detect multivariate outliers, and `app.py` serves an interactive Streamlit dashboard with dynamic health alert banners and dataset CSV downloads."


---

## 3. Step-by-Step Explanation: The Journey of One Real Record

Let's trace **New Delhi** through the pipeline:

1. **Extraction**:
   - `fetch_city_data("New Delhi", 28.6139, 77.2090)` calls Open-Meteo.
   - Response payload arrives: `{"current": {"time": "2026-10-15T22:30", "pm2_5": 95.7, "pm10": 106.2, "us_aqi": 158}}`.
   - Extractor wraps this into `_metadata`: `extracted_at_utc = "2026-10-15T17:00:00Z"`.
2. **Transformation**:
   - `parse_timestamp("2026-10-15T22:30")` determines IST (+05:30) and calculates UTC: `2026-10-15T17:00:00+00:00`.
   - `validate_pollutant("pm2_5", 95.7)` verifies $0.0 \le 95.7 \le 1000.0$.
   - `get_us_aqi_category(158)` classifies the AQI as `"Unhealthy"`.
   - Emits an `ObservationRecord(city="New Delhi", timestamp_utc="2026-10-15T17:00:00+00:00", pm2_5=95.7, ...)`.
3. **Loading**:
   - Loader inspects `aqi_observations` for `('New Delhi', '2026-10-15T17:00:00+00:00')`.
   - If not found: inserts new row (`records_inserted += 1`).
   - If found: executes upsert update (`records_updated += 1`).
   - Commits transaction to SQLite.
4. **Audit**:
   - `pipeline_runs` logs run completion with status `SUCCESS`.

---

## 4. Multi-Level Interview Question Bank

### Q1: Why did you choose ETL instead of ELT for this project?
- **Concise Answer**: I chose ETL because we are ingesting from an external public API where raw payloads can have schema anomalies and sensor errors. Validating and cleaning in Python before loading prevents corrupting our relational analytical tables.
- **Detailed Explanation**: In ELT, raw data is loaded into a cloud warehouse (like Snowflake) and transformed via SQL/dbt. However, on an embedded or operational system using SQLite, storing raw unvalidated JSON Blobs degrades query performance and shifts validation logic to every analytical query. ETL provides a clean, validated boundary.
- **Source Code**: [`src/aqi_pipeline/transform.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/transform.py)
- **Follow-Up 1**: *When would you transition this pipeline to an ELT architecture?*
  - **Answer**: If we scaled to thousands of monitoring stations across the country with high ingestion velocity, and were loading into BigQuery or Snowflake. In that case, we'd land raw JSON into an S3/GCS data lake (the "Bronze" layer) and use dbt to transform into Silver and Gold layers.
- **Follow-Up 2**: *If you move to ELT, how would you prevent bad data from reaching downstream dashboards?*
  - **Answer**: By implementing data tests using dbt tests or Great Expectations on the Silver layer, and configuring pipeline alerts that halt downstream Gold table updates if anomaly thresholds are breached.

---

### Q2: How did you implement idempotency, and why is it critical?
- **Concise Answer**: Idempotency ensures that re-running the pipeline with the same data produces the same database state without duplicates. I implemented it using a composite unique constraint on `(city, timestamp_utc)` and SQLite's `INSERT ... ON CONFLICT DO UPDATE` upsert syntax.
- **Detailed Explanation**: Scheduled batch jobs often fail mid-run or get re-triggered manually by on-call engineers. Without idempotency, every re-run duplicates rows, distorting averages and metrics. In `load.py`, we check existence prior to upserting so our audit log accurately distinguishes between new inserts and updated rows.
- **Source Code**: [`src/aqi_pipeline/load.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/load.py#L90-L135)
- **Follow-Up 1**: *Why did you pick `(city, timestamp_utc)` instead of the auto-increment `id` or local timestamp?*
  - **Answer**: The auto-increment `id` is a surrogate key generated by the DB engine; it cannot detect that two incoming payloads represent the same physical event. The local timestamp (`timestamp_local`) could cause ambiguities if data crossed timezone boundaries. The UTC timestamp represents an absolute physical instant in time.
- **Follow-Up 2**: *What happens if two concurrent pipeline workers attempt to upsert the same city and timestamp simultaneously in SQLite?*
  - **Answer**: SQLite uses database-level locking for writes. One process will acquire the write lock while the other receives a `sqlite3.OperationalError: database is locked`. In PostgreSQL, row-level locks on the unique index handle concurrent upserts smoothly.

---

### Q3: Why is silently replacing missing pollutant readings with 0.0 considered a serious bug?
- **Concise Answer**: In environmental data, `0.0` represents completely clean, pristine air. If a sensor fails or drops offline, replacing `null` with `0.0` creates fake data, lowers regional pollution averages, and misinforms public health advisories.
- **Detailed Explanation**: Data engineers must preserve the semantics of missing data. An SQL `NULL` explicitly communicates that no observation was recorded, enabling aggregate queries like `AVG(pm2_5)` to correctly ignore missing measurements rather than dividing by an artificially inflated count with zero values.
- **Source Code**: [`src/aqi_pipeline/transform.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/transform.py#L82-L105)
- **Follow-Up 1**: *How does your transform stage handle a payload where all pollutant values are null?*
  - **Answer**: In `transform_single`, if all core pollutants (PM2.5, PM10, AQI) are null, it rejects the record and sends it to `QuarantineRecord` with the reason `"Empty observation: all core pollutants are missing"`.
- **Follow-Up 2**: *How do you query quarantined records to monitor data quality?*
  - **Answer**: We query the `aqi_quarantine` table: `SELECT rejection_reason, COUNT(*) FROM aqi_quarantine GROUP BY rejection_reason`. This reveals recurring sensor anomalies.

---

### Q4: How do you handle transient network failures vs permanent API errors?
- **Concise Answer**: I use exponential backoff retries for transient errors (HTTP 5xx, timeouts, network resets, HTTP 429) and immediately fail without retrying for permanent client errors (HTTP 400, 401, 403, 404).
- **Detailed Explanation**: Permanent errors represent invalid requests or bad credentials; retrying them repeatedly is futile and wastes quotas. Transient errors indicate temporary load or connectivity hiccups. For HTTP 429, we check the `Retry-After` header to pause for the exact duration requested by the server.
- **Source Code**: [`src/aqi_pipeline/extract.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/extract.py#L38-L95)
- **Follow-Up 1**: *What formula is used for exponential backoff?*
  - **Answer**: $\text{sleep\_time} = \text{backoff\_factor} \times 2^{\text{attempt} - 1}$. With factor 1.5, attempt 1 sleeps 1.5s, attempt 2 sleeps 3.0s, attempt 3 sleeps 6.0s.
- **Follow-Up 2**: *What is jitter, and why might you add it to exponential backoff?*
  - **Answer**: Jitter adds random noise (e.g. $\pm 0.5\text{s}$) to retry intervals. When dozens of distributed workers fail simultaneously, jitter prevents them from retrying at the exact same sub-second interval, breaking the "thundering herd" cycle.

---

### Q5: How do you test this pipeline without consuming live API quotas or risking flaky CI runs?
- **Concise Answer**: I separated the test suite into 30 deterministic automated tests using mocked HTTP responses and local fixtures, and 1 separate bounded live smoke test that only runs when explicitly requested.
- **Detailed Explanation**: In `test_extract.py`, we use `unittest.mock.patch` on `requests.Session.get` to simulate 200 OK, 429 Rate Limits, 500 Server Errors, timeouts, and corrupted JSON. The entire suite runs in under 3 seconds offline. For end-to-end integration, we load pre-sanitized fixtures from `tests/fixtures/batch_cities_response.json` into an isolated temporary SQLite database created by pytest's `tmp_path`. We also test SQL aggregations, zonal metrics, CSV export, and Isolation Forest outliers.
- **Source Code**: `tests/conftest.py`, `tests/test_extract.py`, `tests/test_pipeline.py`, `tests/test_analytics.py`, `tests/test_anomaly.py`
- **Follow-Up 1**: *How do you prevent the live smoke test from executing during standard CI runs?*
  - **Answer**: In `tests/conftest.py`, we use `pytest_collection_modifyitems` to automatically apply `pytest.mark.skip` to any test marked `@pytest.mark.live` unless the `--run-live` CLI flag is explicitly passed.
- **Follow-Up 2**: *What does the live smoke test verify that mocked tests cannot?*
  - **Answer**: It verifies the "contract" with the external provider: that the live endpoint URL is still active, that Open-Meteo has not changed its JSON schema or parameter names, and that real network DNS and TLS resolution function properly.

---

### Q6: How did you implement anomaly detection on multi-pollutant data, and how does Isolation Forest work?
- **Concise Answer**: I implemented an unsupervised Scikit-learn `IsolationForest` across 6 simultaneous pollutant features, combined with domain-specific atmospheric rules to flag optical sensor inversions.
- **Detailed Explanation**: Unlike traditional distance-based outlier methods that profile "normal" clusters, Isolation Forest isolates anomalies by randomly partitioning feature space with decision trees. Outliers require significantly fewer splits to isolate and appear near the root. We standardize features with `StandardScaler`, impute missing features via median, and normalize decision scores to `[0, 1]`. Additionally, we check the physical constraint: if $PM_{2.5} > 1.05 \times PM_{10}$, the sensor has suffered an optical baseline drift.
- **Source Code**: [`src/aqi_pipeline/anomaly.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/anomaly.py)
- **Follow-Up 1**: *Why use an unsupervised model instead of a supervised classifier like Random Forest or XGBoost?*
  - **Answer**: Real sensor streams lack ground-truth anomaly labels. Malfunctions, localized fire episodes, and calibration drifts are unlabelled in raw telemetry, making unsupervised density/isolation modeling the only viable production approach.

---

### Q7: How does your SQL analytics module track atmospheric science consistency?
- **Concise Answer**: It executes SQL queries computing the PM2.5/PM10 mass concentration ratio and regional zonal aggregations across Indian geography.
- **Detailed Explanation**: In atmospheric science, $PM_{2.5}$ particles are physically contained within the $PM_{10}$ fraction. Our SQL module runs `CASE WHEN pm10 > 0 THEN ROUND(pm2_5 / pm10, 3) ELSE NULL END`. Ratios typically range between 0.3 and 0.8. A ratio $> 1.0$ flags hardware anomalies. Furthermore, `get_zone_summary_metrics()` groups observations by geographical zone (North, South, East, West) to highlight regional seasonal smog disparities.
- **Source Code**: [`src/aqi_pipeline/analytics.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/analytics.py)

---

### Q8: How does the Streamlit dashboard communicate public health risk dynamically?
- **Concise Answer**: It evaluates the maximum recorded AQI among selected cities and dynamically renders color-coded health advisory banners with actionable guidance based on US EPA breakpoints.
- **Detailed Explanation**: In `app.py`, the peak AQI triggers tailored alert banners (Green for Good, Yellow for Moderate, Orange for Sensitive Groups, Red for Unhealthy, Purple for Very Unhealthy, Maroon for Hazardous). It also provides an interactive geographic map, Altair temporal trends, an Isolation Forest outlier scatter plot, and a one-click CSV dataset download button.
- **Source Code**: [`app.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/app.py)

---

## 5. Questions You Must Be Able to Answer Without Looking at Code

1. What are the natural unique key columns in the SQLite database?
   *(Answer: `city` and `timestamp_utc`)*
2. What HTTP status code signifies rate limiting, and what header might accompany it?
   *(Answer: `HTTP 429 Too Many Requests`, accompanied by `Retry-After`)*
3. What happens if an observation has a negative PM2.5 value?
   *(Answer: It is quarantined into `aqi_quarantine` with a rejection reason; the pipeline does not crash)*
4. What timezone does Open-Meteo return when requested with `timezone=Asia/Kolkata`?
   *(Answer: Indian Standard Time, UTC+05:30)*
5. How is idempotency tested?
   *(Answer: By running the pipeline twice on the same fixture data and asserting that total rows in DB remain constant while `records_updated` increases on run 2)*
6. What machine learning model is used for sensor anomaly detection, and why?
   *(Answer: Scikit-learn's Isolation Forest, because it is unsupervised, computationally lightweight, and isolates outliers in multi-dimensional space without requiring pre-labeled training data)*
7. What physical rule is checked between PM2.5 and PM10?
   *(Answer: In nature PM2.5 is a subset of PM10; if PM2.5 > PM10, it flags an optical sensor baseline drift or hardware glitch)*
8. What new capability allows users to export data from the CLI and Streamlit UI?
   *(Answer: The `--export-csv` CLI flag and the `st.download_button` in Tab 1 of the Streamlit dashboard)*

---

## 6. Self-Assessment Checklist Before Your Interview

- [ ] Can I explain the difference between ETL and ELT in 30 seconds?
- [ ] Can I write the SQLite upsert syntax (`ON CONFLICT DO UPDATE`) on a whiteboard?
- [ ] Can I explain why `pm2_5 = raw.get('pm2_5') or 0.0` is an anti-pattern?
- [ ] Can I describe how `unittest.mock.patch` works to mock an HTTP 429 response?
- [ ] Can I explain why `(city, timestamp_utc)` is better than using `id` for deduplication?
- [ ] Can I explain how Scikit-learn's Isolation Forest isolates atmospheric outliers?
- [ ] Can I articulate what parts of this project are currently implemented vs. what would change in a 100,000-records/sec enterprise deployment?

