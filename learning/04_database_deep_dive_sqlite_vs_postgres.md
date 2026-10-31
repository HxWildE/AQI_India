# Module 04 — Database Engineering Deep Dive: SQLite vs. PostgreSQL

> **Instructor**: MIT Senior Lecturer & Principal Staff Data Engineer (15+ Years Industry Experience)  
> **Course Core**: Relational Internals, Concurrency Models, Write Contention, MVCC, and Migration Blueprints  
> **Grounded in Codebase**: [`load.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/load.py), [`analytics.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/analytics.py)

---

## 1. The Core Interview Dilemma: "Why SQLite and Not a 'Real' Database?"

In almost every data engineering interview, an interviewer will look at your SQLite database and ask:  
*"Why did you use a toy database like SQLite instead of a real database like PostgreSQL or MySQL?"*

If you reply: *"Because SQLite was easier to set up,"* you fail the senior bar.  
If you reply with the architectural analysis below, you demonstrate staff-level database knowledge.

---

## 2. Head-to-Head Architectural Comparison

| Architectural Feature | SQLite 3 (What We Used) | PostgreSQL 15+ (Production Target) |
| :--- | :--- | :--- |
| **Architecture** | **Serverless / In-Process**: Runs directly within the Python process memory space as an embedded C library. Zero network round-trips. | **Client-Server Daemon**: Standalone background process listening on TCP port 5432. Every query traverses network sockets. |
| **Concurrency & Locking** | **Database-Level Write Lock**: Only one write transaction can execute at any instant. Concurrent writers receive `sqlite3.OperationalError: database is locked`. Multiple concurrent readers allowed via WAL. | **Row-Level Locking via MVCC**: Multi-Version Concurrency Control allows thousands of concurrent transactions to read and write different rows simultaneously without blocking. |
| **Timezone & Data Types** | **Dynamic Manifest Typing**: No native `TIMESTAMPTZ`. Timestamps are stored as ISO-8601 text (`TEXT`), requiring Python application-level parsing. | **Strict Static Typing**: Native `TIMESTAMPTZ` with microsecond precision, mathematical interval arithmetic, and timezone offsets. |
| **Storage Engine** | Single B-Tree file on local disk (`aqi_india.db`). Extremely portable; zero daemon maintenance. | Page-based heap files managed by buffer pool cache, background writers, checkpoints, and write-ahead logs (WAL). |
| **Connection Overhead** | Microseconds to open file descriptor. No connection pooling required. | Expensive process-fork per connection (5-10MB RAM per client). Requires external connection pooling (**PgBouncer**). |
| **Horizontal Scaling** | Single-node only. Cannot be distributed across multiple instances. | Read replicas via streaming replication, logical replication, and distributed clustering (Citus). |
| **Hosting & Cloud Cost** | **$0.00 / month**: Runs on local machines, edge IoT devices, and free GitHub Actions CI runners. | **\$30 - \$500 / month**: AWS RDS, GCP Cloud SQL, or self-hosted EC2 instances requiring continuous maintenance. |

---

## 3. Deep Dive: SQLite Internals in This Pipeline

### 3.1 The In-Process Advantage
In [`load.py`](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/src/aqi_pipeline/load.py), when `conn.execute()` runs, Python calls the SQLite C library compiled directly into the Python binary. There is:
- **Zero network serialization**: No TCP packet headers, no socket latency, no TLS handshakes.
- **Zero infrastructure dependency**: Any developer can clone this repository, run `pytest`, and verify the entire pipeline end-to-end without installing Docker, running `docker-compose up`, or configuring database users and passwords.

### 3.2 Pragmas & Integrity Constraints
Notice our initialization logic in `load.py`:
```python
conn = sqlite3.connect(str(self.db_path))
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON;")
```
By default, SQLite disables foreign key validation for backward compatibility with 1990s designs. We explicitly turn on `PRAGMA foreign_keys = ON` to enforce relational integrity between parent and child tables.

### 3.3 The SQLite Write Lock Bottleneck
Why can SQLite NOT handle high-concurrency enterprise pipelines?
SQLite locks the **entire database file** during a write transaction. If Worker A is inserting 10,000 New Delhi records inside `BEGIN TRANSACTION`, and Worker B attempts to insert Mumbai records, Worker B must wait. If Worker B's timeout expires, it throws:
```text
sqlite3.OperationalError: database is locked
```
For our batch cron pipeline (running sequentially for 8 cities), this lock is never contested. But for 500 concurrent IoT devices streaming sub-second telemetry, SQLite falls over immediately.

---

## 4. Deep Dive: PostgreSQL Internals & MVCC

### 4.1 How PostgreSQL MVCC Solves Write Contention
PostgreSQL uses **Multi-Version Concurrency Control (MVCC)**:
- When a transaction updates a row, PostgreSQL **does not overwrite the existing disk bytes**.
- Instead, it writes a new version of the tuple (row) marked with the current transaction ID (`xmin`), and marks the old row's expiration transaction ID (`xmax`).
- **Readers never block writers, and writers never block readers.** A reader querying average PM2.5 reads the old tuple version, while a writer concurrently upserts the new tuple version.
- **Row-Level Locking**: Two concurrent workers can insert or update rows for different cities at the exact same millisecond without contention.

```mermaid
graph TD
    subgraph SQLite["SQLite Concurrency (Single File Lock)"]
        W1["Worker 1 (Upserting Delhi)"] -->|Acquires Exclusive Lock| DB_FILE[("Single aqi_india.db File")]
        W2["Worker 2 (Upserting Mumbai)"] -->|BLOCKED / Waits or Crashes| DB_FILE
    end

    subgraph Postgres["PostgreSQL Concurrency (MVCC & Row Locks)"]
        PW1["Worker 1 (Upserting Delhi)"] -->|Row Lock on Delhi Tuple| PG_HEAP[("Postgres Heap & Shared Buffers")]
        PW2["Worker 2 (Upserting Mumbai)"] -->|Row Lock on Mumbai Tuple| PG_HEAP
        PR1["Dashboard Reader (SELECT AVG)"] -->|Reads Tuple Snapshot via xmin/xmax| PG_HEAP
    end
```

### 4.2 Vacuuming & Maintenance: SQLite `VACUUM` vs PostgreSQL `autovacuum`
- **SQLite**: When rows are deleted or updated, the unused disk space remains inside the `.db` file as empty pages (free list). To reclaim disk space, you must execute `VACUUM;`, which rewrites the entire database file to a temporary copy.
- **PostgreSQL**: MVCC leaves dead tuples behind. PostgreSQL runs a continuous background daemon called `autovacuum` that scans pages, reclaims dead tuples, and updates query planner statistics (`ANALYZE`).

---

## 5. PostgreSQL & TimescaleDB Migration Blueprint

When our air quality platform scales past 1,000 IoT sensors, here is the production migration plan.

### 5.1 DDL Translation: SQLite to PostgreSQL
Notice how our SQLite DDL maps directly to PostgreSQL DDL with typed enhancements:

```sql
-- PostgreSQL Production Schema
CREATE TABLE IF NOT EXISTS aqi_observations (
    id BIGSERIAL PRIMARY KEY,
    city VARCHAR(64) NOT NULL,
    state VARCHAR(64),
    zone VARCHAR(32),
    latitude NUMERIC(8, 4) NOT NULL,
    longitude NUMERIC(8, 4) NOT NULL,
    timestamp_local TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    pm2_5 NUMERIC(6, 2),
    pm10 NUMERIC(6, 2),
    carbon_monoxide NUMERIC(8, 2),
    nitrogen_dioxide NUMERIC(6, 2),
    sulphur_dioxide NUMERIC(6, 2),
    ozone NUMERIC(6, 2),
    provider_aqi NUMERIC(5, 1),
    aqi_category VARCHAR(32) NOT NULL,
    data_source VARCHAR(64) NOT NULL,
    extracted_at_utc TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_city_timestamp UNIQUE (city, timestamp_utc)
);

-- Compound Index for chronological city time-series lookups
CREATE INDEX idx_obs_city_time ON aqi_observations (city, timestamp_utc DESC);
CREATE INDEX idx_obs_zone_time ON aqi_observations (zone, timestamp_utc DESC);
```

### 5.2 The TimescaleDB Time-Series Extension
For billion-row time-series environmental data, standard PostgreSQL tables degrade as B-Tree indexes exceed RAM cache. We convert the table into a **TimescaleDB hypertable**:

```sql
-- Convert standard table to TimescaleDB Hypertable partitioned by 7-day chunks
SELECT create_hypertable('aqi_observations', 'timestamp_utc', chunk_time_interval => INTERVAL '7 days');

-- Automatic Compression Policy for data older than 30 days (10x disk savings)
ALTER TABLE aqi_observations SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'city,zone'
);
SELECT add_compression_policy('aqi_observations', INTERVAL '30 days');
```

---

## 6. How to Defend the Database Choice in an Interview

### Question: *"Why didn't you just deploy PostgreSQL in a Docker container for this project?"*

### The Master Answer Script:
> *"I chose SQLite intentionally because engineering design is about matching architectural tools to the operational constraints of the problem. 
> 
> Our workload is an embedded batch ETL pipeline ingesting hourly observations across 8 metropolitan cities. Total write throughput is 8 transactions per hour—a workload that causes virtually zero lock contention. 
> 
> Using SQLite made the platform zero-cost, self-contained, and perfectly deterministic for our 31-test offline pytest suite, allowing any engineer or CI runner to verify the code without spinning up a Docker daemon or managing hosted cloud database credentials. 
> 
> However, because our schema enforces standard ANSI SQL DDL, atomic transactions, and composite unique constraints on `(city, timestamp_utc)`, the data layer is decoupled: we can swap `sqlite3` for a PostgreSQL connection pool with PgBouncer and TimescaleDB hypertables simply by updating our database connection string, without rewriting our transformation or analytical SQL logic."*

