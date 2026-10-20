# 07 — Architecture, Diagrams & Workflow Documentation

This document contains visual Mermaid architecture diagrams and detailed narrative explanations covering data flows, execution sequences, component dependencies, and failure handling.

---

## 1. High-Level System Architecture

```mermaid
graph TD
    subgraph External["External Layer"]
        API["Open-Meteo Air Quality API<br/>(Global Atmospheric Models)"]
        Fixtures["Offline JSON Fixtures<br/>(tests/fixtures/batch_cities_response.json)"]
    end

    subgraph Pipeline["AQI Pipeline Core (Python)"]
        CLI["CLI Entrypoint<br/>(python -m aqi_pipeline.pipeline)"]
        Config["Configuration Manager<br/>(config.py / .env)"]
        Extract["AQIExtractor<br/>(extract.py)"]
        Transform["AQITransformer<br/>(transform.py)"]
        Load["AQILoader<br/>(load.py)"]
        Log["Logging & Run Audit<br/>(logging_config.py)"]
    end

    subgraph Storage["Storage Layer (SQLite)"]
        DB_Obs[("aqi_observations<br/>(Cleaned / Unique Key)")]
        DB_Quar[("aqi_quarantine<br/>(Anomalies & Rejections)")]
        DB_Runs[("pipeline_runs<br/>(Audit Metrics & Health)")]
    end

    subgraph Intelligence["Analytics & ML Intelligence Layer"]
        Analytics["SQL Analytics<br/>(analytics.py)"]
        ML["Scikit-Learn Isolation Forest<br/>(anomaly.py)"]
        Streamlit["Interactive Web Dashboard<br/>(app.py)"]
    end

    CLI --> Config
    CLI --> Extract
    Config --> Extract
    Config --> Transform
    Config --> Load

    API -.->|Live HTTP GET| Extract
    Fixtures -.->|Offline Mode| Extract

    Extract -->|Raw Payloads + Metadata| Transform
    Transform -->|Valid ObservationRecords| Load
    Transform -->|Defective QuarantineRecords| Load

    Load -->|Idempotent Upsert| DB_Obs
    Load -->|Append Rejections| DB_Quar
    Load -->|Record Start & End| DB_Runs

    DB_Obs --> Analytics
    DB_Quar --> Analytics
    Analytics --> ML
    ML --> Streamlit
    Analytics --> Streamlit
```

### Walkthrough:
The system is divided into four integrated tiers:
1. **External Layer**: Supplies air quality observations either through the live Open-Meteo REST API or offline pre-sanitized test fixtures.
2. **Pipeline Core**: A decoupled 3-stage Python architecture orchestrated by `AQIPipeline`. Configuration and structured logging wrap all operations.
3. **Storage Layer**: An embedded SQLite relational database hosting clean analytical records (`aqi_observations`), a quarantine dead-letter repository (`aqi_quarantine`), and execution run telemetry (`pipeline_runs`).
4. **Intelligence & Presentation Layer**:
   - `analytics.py`: Executes SQL queries to compute city-level aggregates, PM2.5/PM10 mass ratios, and data quality metrics.
   - `anomaly.py`: Applies an unsupervised Scikit-learn `IsolationForest` across multi-pollutant vectors to isolate sensor anomalies and physical inversions.
   - `app.py`: An interactive, dark-mode Streamlit dashboard enabling real-time geographic map exploration, trend charting, anomaly inspection, and live pipeline triggering.

---

## 2. End-to-End Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as Engineer / Cron
    participant CLI as pipeline.py
    participant Ext as extract.py
    participant API as Open-Meteo API
    participant Trans as transform.py
    participant Load as load.py
    participant DB as SQLite Database

    User->>CLI: Execute python -m aqi_pipeline.pipeline
    CLI->>Load: record_pipeline_run_start(run_id, mode)
    Load->>DB: INSERT INTO pipeline_runs (status='STARTED')
    
    Note over CLI,API: Stage 1: Extraction
    CLI->>Ext: extract_all()
    loop Each Indian City
        Ext->>API: GET /v1/air-quality?lat=...&lon=...
        API-->>Ext: HTTP 200 OK (JSON Payload)
    end
    Ext-->>CLI: Return raw city payloads + metadata

    Note over CLI,Trans: Stage 2: Transformation & Validation
    CLI->>Trans: transform_all(raw_payloads)
    loop Each Payload
        Trans->>Trans: Parse local timestamp (IST) -> UTC
        Trans->>Trans: Validate pollutant boundaries
        alt All Rules Pass
            Trans->>Trans: Append to accepted list
        else Invalid or Out-of-Bounds
            Trans->>Trans: Append to quarantined list
        end
    end
    Trans-->>CLI: Return TransformationResult(accepted, quarantined)

    Note over CLI,DB: Stage 3: Loading & Idempotency
    CLI->>Load: load_observations(accepted)
    Load->>DB: BEGIN TRANSACTION
    loop Each Observation
        Load->>DB: INSERT INTO aqi_observations ... ON CONFLICT DO UPDATE
    end
    Load->>DB: COMMIT TRANSACTION
    
    opt Quarantined Records Exist
        CLI->>Load: load_quarantine(quarantined)
        Load->>DB: INSERT INTO aqi_quarantine ...
    end

    CLI->>Load: record_pipeline_run_completion(status='SUCCESS')
    Load->>DB: UPDATE pipeline_runs SET status='SUCCESS', elapsed=...
    CLI-->>User: Display Formatted Terminal Summary & Observations Table
```

---

## 3. Data Flow & Schema Evolution

```mermaid
flowchart LR
    A["Raw JSON Payload<br/>{latitude: 28.6, current: {pm2_5: 95.7, time: '2026-10-15T22:30'}}"] 
    --> B["Enriched Raw Payload<br/>Adds _metadata: city, extracted_at_utc, source, mode"]
    
    B --> C{Validation Gate}
    
    C -->|Pass| D["ObservationRecord (Dataclass)<br/>- city: 'New Delhi'<br/>- timestamp_utc: '2026-10-15T17:00:00Z'<br/>- pm2_5: 95.7, aqi_category: 'Unhealthy'"]
    
    C -->|Fail| E["QuarantineRecord (Dataclass)<br/>- city: 'Bengaluru'<br/>- reason: 'pm2_5 is negative (-10)'<br/>- raw_payload_snippet"]
    
    D --> F[("Table: aqi_observations<br/>UNIQUE(city, timestamp_utc)")]
    E --> G[("Table: aqi_quarantine<br/>Audit log of rejections")]
```

---

## 4. Failure Handling & Exponential Backoff Flowchart

```mermaid
flowchart TD
    Start([Fetch City AQI]) --> Attempt[Attempt HTTP Request]
    Attempt --> CheckStatus{Inspect HTTP Status}

    CheckStatus -->|200 OK| ParseJSON[Parse JSON & Add Metadata] --> Success([Return Payload])
    
    CheckStatus -->|400, 401, 403, 404| ClientErr[Permanent Client Error] --> Abort([Raise ExtractionError - Do NOT Retry])

    CheckStatus -->|429 Rate Limit| CheckHeader{Retry-After Header?}
    CheckHeader -->|Yes| SleepHeader[Sleep Header Seconds] --> IncrementRetry
    CheckHeader -->|No| BackoffCalc[Sleep backoff_factor * 2^attempt] --> IncrementRetry

    CheckStatus -->|5xx Server Error or Timeout| IncrementRetry{Attempt < Max Retries?}
    
    IncrementRetry -->|Yes| SleepBackoff[Sleep Exponential Backoff] --> Attempt
    IncrementRetry -->|No| RetriesExhausted([Raise ExtractionError - Mark Run Failed])
```

---

## 5. Testing Architecture

```mermaid
graph TD
    subgraph Unit["Deterministic Automated Tests (Offline)"]
        TestExt["test_extract.py (7 Tests)<br/>Mocks HTTP 200, 429, 500, timeouts, bad JSON"]
        TestTrans["test_transform.py (8 Tests)<br/>Validates boundary rules, quarantine, no-zero-imputation"]
        TestLoad["test_load.py (5 Tests)<br/>Tests temporary SQLite, idempotency, transaction rollback"]
        TestPipe["test_pipeline.py (4 Tests)<br/>End-to-end fixture runs, idempotency, audit trail"]
        TestAnalytics["test_analytics.py (3 Tests)<br/>Zonal metrics, diurnal trends, CSV export"]
        TestAnomaly["test_anomaly.py (3 Tests)<br/>Isolation Forest outliers, inversion rules, safe fallback"]
    end

    subgraph LiveSmoke["Optional Live Smoke Test"]
        LiveTest["test_live_smoke.py (1 Test)<br/>Single bounded real request to Open-Meteo<br/>(Runs only with pytest --run-live)"]
    end

    Unit -->|100% Offline / Fast / Zero Quota| Passes([30 Passing Automated Tests])
    LiveSmoke -->|Verifies Real Upstream API Contract| LivePass([1 Verified Smoke Test])
```

