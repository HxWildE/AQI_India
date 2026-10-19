# 12 — Two-Layer Deep Dive: Hard Technical Probing

This document simulates rigorous, senior-level interviewer grilling. When an interviewer suspects you memorized high-level answers, they will probe two to three layers deeper into edge cases, concurrency, failure modes, and architectural trade-offs.

---

## Deep Dive 1: Concurrency & Database Locking

### Primary Question:
> *"What happens if your hourly cron job overlaps with a manual backfill job, and both try to write to SQLite simultaneously?"*

### Level 1 Follow-Up:
> *"SQLite is file-based. How does it handle multiple processes writing at once, and what exact error does Python throw?"*
- **Defensible Answer**:
  SQLite uses database-level locks for write operations. When Process A begins a write transaction (`BEGIN IMMEDIATE` or `BEGIN TRANSACTION`), it places a reserved/exclusive lock on the database file. If Process B attempts to write while that lock is held, SQLite will wait for a short busy-timeout period (default 5 seconds). If the lock is not released within that window, Python's `sqlite3` driver raises `sqlite3.OperationalError: database is locked`.

### Level 2 Follow-Up:
> *"How would you architect a solution to prevent this failure mode without migrating to PostgreSQL immediately?"*
- **Defensible Answer**:
  Three concrete solutions:
  1. **SQLite WAL Mode (Write-Ahead Logging)**: Execute `PRAGMA journal_mode = WAL;`. In WAL mode, readers do not block writers, and writers do not block readers, significantly reducing lock contention.
  2. **File Locking / Job Mutex**: Use a file lock (e.g. `fasteners` or OS-level `flock`) or a database advisory lock so the pipeline CLI refuses to run if an instance is already active.
  3. **Decouple Ingestion from Loading via Staging**: Have workers dump validated parquet/json files to a staging directory, and have a single dedicated worker thread or process handle database writes sequentially.

---

## Deep Dive 2: Upstream Schema Drift & Provider Outages

### Primary Question:
> *"What happens if Open-Meteo silently changes the key `pm2_5` to `pm25` or starts returning pollutant values in parts-per-billion (ppb) instead of µg/m³?"*

### Level 1 Follow-Up:
> *"Walk me through the exact line of code that encounters this, and what the database records."*
- **Defensible Answer**:
  In `transform.py`, the loop `for field_name in pollutant_fields:` looks up `current.get('pm2_5')`. If Open-Meteo renamed it to `pm25`, `get('pm2_5')` returns `None`. 
  Next, our check:
  ```python
  core_pollutants = [cleaned_values["pm2_5"], cleaned_values["pm10"], cleaned_values["us_aqi"]]
  if all(v is None for v in core_pollutants):
      return None, QuarantineRecord(...)
  ```
  evaluates to `True`. The record is **not** inserted into `aqi_observations`. Instead, it is routed to `aqi_quarantine` with the rejection reason: `"Empty observation: all core pollutants are missing"`. The pipeline run completes with 0 inserts and $N$ quarantined records.

### Level 2 Follow-Up:
> *"How would an on-call engineer know this happened at 3:00 AM without reading terminal logs?"*
- **Defensible Answer**:
  Through **run-level telemetry and alerting**:
  In `pipeline_runs`, the completion record logs `records_accepted = 0` and `records_quarantined = N`. In production, a metric check (or Datadog alert) triggers when `records_quarantined / records_extracted > 0.2` (greater than 20% quarantine rate). The alert sends a high-priority PagerDuty notification indicating upstream schema deviation.

---

## Deep Dive 3: Scaling from 8 Cities to 5,000 Stations

### Primary Question:
> *"Right now you fetch 8 cities sequentially. How would you scale this to ingest from 5,000 continuous monitoring stations across India every 15 minutes?"*

### Level 1 Follow-Up:
> *"What becomes your immediate bottleneck: CPU, memory, disk I/O, or network?"*
- **Defensible Answer**:
  The immediate bottleneck is **network I/O latency**. 5,000 sequential HTTP requests with an average latency of 300ms would take $5,000 \times 0.3 = 1,500\text{ seconds}$ (25 minutes), exceeding the 15-minute ingestion window. Memory and CPU usage remain minimal because each JSON payload is only ~1 KB.

### Level 2 Follow-Up:
> *"How would you restructure the extraction architecture to complete within 2 minutes while respecting API rate limits?"*
- **Defensible Answer**:
  1. **Asynchronous Concurrent I/O (`aiohttp` / `asyncio` or `ThreadPoolExecutor`)**: Group requests into a worker pool bounded to, say, 20 concurrent connections. 5,000 requests divided across 20 workers would complete in $\approx 75\text{ seconds}$.
  2. **Token Bucket Rate Limiter**: Use a distributed token bucket (e.g. backed by Redis) to ensure aggregate requests across all workers never exceed the provider's rate limit (e.g. 100 requests/sec).
  3. **Batch Endpoints**: If the provider supports multi-coordinate batch requests (`latitude=lat1,lat2&longitude=lon1,lon2`), batch stations into chunks of 50 per call, reducing total network roundtrips from 5,000 to 100.

---

## Deep Dive 4: Provider AQI vs. Indian CPCB NAQI Methodology

### Primary Question:
> *"Why did you store the provider's AQI as `provider_aqi` instead of calculating the official Indian National AQI yourself?"*

### Level 1 Follow-Up:
> *"What is the difference between US EPA AQI and India's CPCB (Central Pollution Control Board) NAQI?"*
- **Defensible Answer**:
  1. **Averaging Windows**: CPCB NAQI strictly requires **24-hour rolling average concentrations** for PM2.5, PM10, NO2, and SO2, and **8-hour rolling averages** for CO and O3. Real-time API calls only provide instantaneous 1-hour readings. Calculating an Indian AQI on a 1-hour snapshot is scientifically invalid and violates the official CPCB (2014) standard.
  2. **Breakpoint Scales**: India has much stricter and different concentration breakpoints reflecting local climatic conditions. For example, a PM2.5 concentration of $60\,\mu\text{g/m}^3$ is categorized as "Satisfactory" (AQI 51–100) under CPCB NAQI, whereas under US EPA AQI it is categorized as "Unhealthy" (AQI > 150).

### Level 2 Follow-Up:
> *"If your business stakeholder demanded official CPCB NAQI, how would you re-engineer the database and pipeline?"*
- **Defensible Answer**:
  We would treat this as a **two-tier data modeling architecture**:
  1. **Bronze/Silver Tier (`aqi_observations`)**: Ingest and store hourly raw pollutant concentrations in native physical units ($\mu\text{g/m}^3$).
  2. **Gold Tier (`daily_cpcb_aqi`)**: Run a scheduled SQL aggregation job that computes a 24-hour rolling window (`AVG(pm2_5) OVER (PARTITION BY city ORDER BY timestamp_utc ROWS BETWEEN 23 PRECEDING AND CURRENT ROW)`). Only when at least 16 hours of data are present (CPCB's 75% data sufficiency rule) would we calculate the piecewise linear sub-indices for each pollutant and take the maximum sub-index as the official Indian NAQI score.

---

## Deep Dive 5: Unsupervised Anomaly Detection vs. Rule-Based Quality Filters

### Primary Question:
> *"You have boundary checks in `transform.py` that reject corrupt numbers. Why do you also need a Scikit-Learn Isolation Forest in `anomaly.py`?"*

### Level 1 Follow-Up:
> *"What kind of real-world anomaly slips right through `transform.py` boundary filters but gets caught by the Isolation Forest?"*
- **Defensible Answer**:
  Boundary checks evaluate columns in isolation (univariate): $0 \le PM_{2.5} \le 1000$ and $0 \le CO \le 50000$. A corrupt sensor reading of $PM_{2.5} = 280\,\mu\text{g/m}^3$ accompanied by $CO = 15\,\mu\text{g/m}^3$ and $NO_2 = 2\,\mu\text{g/m}^3$ passes every univariate threshold. However, in reality, combustion generating $280\,\mu\text{g/m}^3$ of $PM_{2.5}$ must co-emit substantial $CO$ and $NO_2$. The **multivariate** Isolation Forest analyzes the joint distribution across all 6 features simultaneously, immediately isolating this point as an atmospheric impossibility.

### Level 2 Follow-Up:
> *"How do you prevent false positives during legitimate extreme pollution events, like Diwali fireworks or post-monsoon stubble burning in Delhi?"*
- **Defensible Answer**:
  Three robust safeguards:
  1. **Multivariate Co-Emission**: Real combustion episodes exhibit concurrent spikes across PM2.5, PM10, CO, and SO2. Because the entire pollutant vector elevates together, the data point clusters along the combustion manifold rather than appearing as an isolated point in orthogonal space.
  2. **Domain-Rule Separation**: We explicitly distinguish physical sensor failures (like optical inversion $PM_{2.5} > 1.05 \times PM_{10}$) with explicit `anomaly_reason` tags, distinct from general multivariate outliers.
  3. **Contamination Tuning & Regional Stratification**: Setting the contamination parameter based on domain reality (e.g. 10–15%) and fitting Isolation Forests partitioned by regional zones prevents high-baseline northern cities from skewing southern coastal baselines.

