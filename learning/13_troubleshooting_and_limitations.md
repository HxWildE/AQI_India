# 13 — Troubleshooting Guide & Production Limitations

Every software engineering project has trade-offs and operational failure modes. Understanding where your system breaks and how to debug it distinguishes a junior engineer from a script runner.

---

## 1. Operational Troubleshooting Matrix

| Symptom / Error | Root Cause | Diagnosis Command | Resolution |
|:---|:---|:---|:---|
| `sqlite3.OperationalError: database is locked` | Another process is writing to `aqi_india.db` simultaneously. | Check running Python tasks or background locks. | Enable WAL mode (`PRAGMA journal_mode=WAL;`), wait for the competing process to finish, or ensure background tasks are killed. |
| `requests.exceptions.Timeout` | External API network latency exceeded `AQI_TIMEOUT_SECONDS`. | Run with `--log-level DEBUG` to inspect latency. | Increase `AQI_TIMEOUT_SECONDS=20.0` in `.env` or verify outbound internet connectivity. |
| `ExtractionError: Permanent client error HTTP 400` | Invalid coordinates passed in `config.py` or `--cities`. | Inspect log error message for API reason text. | Verify city latitude/longitude are within plausible geographic bounds (-90 to 90, -180 to 180). |
| `ExtractionError: Rate limited (429)` | Exhausted free-tier hourly or per-minute call limits. | Inspect `Retry-After` header in log output. | Increase `AQI_RATE_LIMIT_DELAY=1.0` in `.env` to pace calls, or provide commercial `AQI_API_KEY`. |
| `TransformationResult: Quarantined > 0` | Ingested sensor data contained negative values or corrupt timestamps. | Query `SELECT * FROM aqi_quarantine;` | Inspect `rejection_reason` in quarantine table. If valid extreme weather event, adjust `POLLUTANT_VALIDATION_BOUNDS` in `config.py`. |
| `Streamlit Cache Stale / Port Conflict` | Streamlit displaying old data after DB write or port 8501 occupied. | Check console error or `st.cache_data` warning. | Click "Run Pipeline Now" to trigger `st.cache_data.clear()`, or pass `--server.port 8502`. |
| `Insufficient data for ML (< 2 rows)` | Anomaly detector called on an empty or single-row database. | Inspect logs for `Insufficient observations for ML anomaly detection`. | Run pipeline in fixture or live mode first (`python -m aqi_pipeline.pipeline --mode fixture`) to seed observations. |


---

## 2. Real-World Limitations of This Prototype

To defend this project credibly in technical interviews, be completely transparent about what this prototype does **not** do:

### 1. SQLite Single-Writer Bottleneck
- **Limitation**: SQLite supports unlimited concurrent readers, but only **one single writer** at a time.
- **Production Solution**: Migrate to PostgreSQL or AWS RDS with connection pooling (`pgbouncer`), which handles hundreds of concurrent write transactions using Multi-Version Concurrency Control (MVCC).

### 2. Synchronous Sequential Extraction
- **Limitation**: `AQIExtractor.extract_all()` loops over cities synchronously. For 8 cities this takes ~4 seconds, but for 500 cities it would take several minutes.
- **Production Solution**: Implement asynchronous parallel fetching using Python's `asyncio` + `aiohttp` or worker queues (Celery / AWS SQS).

### 3. Model-Based API vs. Direct CPCB Hardware Telemetry
- **Limitation**: Open-Meteo's Air Quality API combines satellite observations (Copernicus CAMS) with atmospheric numerical models. While geographically ubiquitous and highly reliable, it is not direct ground-level telemetry from physical CPCB monitoring stations.
- **Production Solution**: Ingest directly from data.gov.in CPCB CAAQMS (Continuous Ambient Air Quality Monitoring Stations) API or OpenAQ, adding station-level metadata (sensor manufacturer, calibration dates).

### 4. Scheduler Reliance
- **Limitation**: The current codebase provides a CLI runner (`pipeline.py`) but does not include an internal daemon scheduler.
- **Production Solution**: Schedule the CLI using a Linux `cron` job, or wrap the pipeline stages into an Apache Airflow DAG or Prefect flow.

---

## 3. Production Readiness Roadmap

```
Current Prototype (V1.0)
[ Python CLI ] ──> [ Open-Meteo API ] ──> [ SQLite DB ] ──> [ Pytest Mock Suite ]

Future Production Vision (V2.0)
[ Airflow DAG ] ──> [ Async Worker Pool ] ──> [ PostgreSQL / Snowflake ] ──> [ Datadog / Grafana ]
      │                     │                           │
  Hourly Cron       Token-Bucket Limiter         dbt Silver/Gold
```

1. **Storage**: Replace SQLite with PostgreSQL / Snowflake.
2. **Orchestration**: Wrap pipeline in Apache Airflow or Dagster with automatic retries and SLA alerting.
3. **Observability**: Export metrics from `pipeline_runs` to Prometheus and visualize latency and data quality on a Grafana dashboard.
4. **Calculated Indices**: Implement 24-hour rolling averages to compute official CPCB National Air Quality Index (NAQI) sub-indices.
