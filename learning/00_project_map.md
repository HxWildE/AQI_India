# 00 — Project Map & Learning Navigation Guide

Welcome to the **AQI India End-to-End ETL Pipeline, Analytics & Machine Learning** learning curriculum! This document serves as your central index and roadmap for mastering every architectural, engineering, and interview concept in this codebase.

---

## 1. What This Project Is

This project is a modular, production-patterned data engineering, analytics, and machine learning platform built in Python. It ingests hourly air quality observations across major Indian metropolitan areas (New Delhi, Mumbai, Bengaluru, Kolkata, Chennai, Hyderabad, Ahmedabad, Lucknow) from the Open-Meteo Air Quality API, validates and sanitizes incoming measurements, persists them into a structured SQLite database with guaranteed **idempotency** and **quarantine auditability**, computes SQL trend analytics, detects multi-pollutant sensor anomalies using Scikit-learn, and visualizes real-time metrics through an interactive Streamlit dashboard.

```
[ Open-Meteo Air Quality API ] 
              │  (HTTP GET / Exponential Backoff / Retries)
              ▼
    [ Extract Stage ]  ──> Raw Payloads + Provenance Metadata
              │
              ▼
   [ Transform Stage ] ──> Schema Validation, IST/UTC Normalization, Quality Bounds
        │        │
 (Valid)│        │(Invalid: Negative values, bad timestamps)
        ▼        ▼
 [ Load Stage ] [ Quarantine Table ] ──> `aqi_quarantine`
        │
        ▼
[ SQLite DB: `aqi_observations` ] ──> Idempotent Upsert `(city, timestamp_utc)`
        │            ▲
        │            │
        │     [ Audit Log: `pipeline_runs` ] ──> Run ID, record counts, latency, status
        ▼
 [ SQL Analytics Engine (`analytics.py`) ] ──> Zonal Trends, AQI Categories & CSV Export
        │
        ▼
 [ Scikit-Learn Anomaly Detection (`anomaly.py`) ] ──> Isolation Forest Outlier Scores
        │
        ▼
 [ Streamlit Intelligence Dashboard (`app.py`) ] ──> Interactive Map, Trends & Health Alerts
```

---

## 2. Recommended Learning Sequence

Follow this sequential reading order to build from fundamental concepts to defensible interview expertise:

| Step | Document | Purpose & Focus |
|:---:|:---|:---|
| **1** | [00_project_map.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/00_project_map.md) | High-level roadmap, glossary, architecture index |
| **2** | [01_setup_and_first_run.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/01_setup_and_first_run.md) | Environment setup, fixture & live runs, Streamlit dashboard, CSV export |
| **3** | [02_api_and_http_fundamentals.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/02_api_and_http_fundamentals.md) | REST APIs, HTTP methods, headers, status codes, query parameters, Open-Meteo |
| **4** | [03_etl_from_scratch.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/03_etl_from_scratch.md) | ETL vs ELT, stage responsibilities, decoupled architectural design |
| **5** | [04_data_quality_and_validation.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/04_data_quality_and_validation.md) | Data hygiene, quarantine pattern, timezone math (IST/UTC), zero-imputation fallacy |
| **6** | [05_sqlite_and_idempotency.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/05_sqlite_and_idempotency.md) | Relational modeling, composite natural keys, upserts, ACID transactions |
| **7** | [06_error_handling_and_retries.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/06_error_handling_and_retries.md) | Transient vs permanent errors, exponential backoff, rate limiting (HTTP 429) |
| **8** | [07_architecture_and_data_flow.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/07_architecture_and_data_flow.md) | Mermaid sequence diagrams, data flow diagrams, module dependencies |
| **9** | [08_codebase_walkthrough.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/08_codebase_walkthrough.md) | Tour of `config.py`, `extract.py`, `transform.py`, `load.py`, `analytics.py`, `anomaly.py`, `pipeline.py`, `app.py` |
| **10** | [09_testing_strategy.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/09_testing_strategy.md) | Pytest pyramid, 28 automated tests, mocking network calls, testing idempotency |
| **11** | [10_job_description_mapping.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/10_job_description_mapping.md) | Mapping code artifacts to Junior Data Engineer & Analytics roles |
| **12** | [11_interview_questions.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/11_interview_questions.md) | Question bank with 60s pitch, 2min architecture, and senior interview defenses |
| **13** | [12_two_layer_deep_dive.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/12_two_layer_deep_dive.md) | Two-level follow-up questions probing edge cases, concurrency, and ML anomaly detection |
| **14** | [13_troubleshooting_and_limitations.md](file:///c:/Users/harsh/OneDrive/Documents/Desktop/MYwebDEvprojects/AQI_India_ETL_Pipeline/learning/13_troubleshooting_and_limitations.md) | Real-world trade-offs, debugging scenarios, and production scaling roadmap |

---

## 3. Key Vocabulary & Concepts

Before reading further, familiarize yourself with these core industry terms:

- **ETL (Extract, Transform, Load)**: Data integration paradigm where data is extracted from source systems, transformed (cleaned/validated) in an application layer, and loaded into a destination database.
- **Idempotency**: The property where an operation can be applied multiple times without changing the result beyond the initial application. In data engineering, running an ingestion job twice with the same raw data must NOT produce duplicate database records.
- **Natural Key**: A business-meaningful attribute (or set of attributes) that uniquely identifies a record. In our pipeline, `(city, timestamp_utc)` is the natural unique key.
- **Surrogate Key**: An artificially generated integer or UUID (`id INTEGER PRIMARY KEY`) used internally by the database engine.
- **Data Quarantine / Dead-Letter Queue (DLQ)**: An isolated storage table or topic where malformed, invalid, or out-of-range records are routed so pipeline execution is not halted, while preserving records for data quality auditing.
- **Exponential Backoff**: An algorithm that exponentially increases the wait time between retry attempts (e.g. 1.5s, 3.0s, 6.0s) to prevent overwhelming an already struggling external service.
- **Isolation Forest**: An unsupervised tree-based ensemble algorithm that isolates anomalies instead of profiling normal data points, making it highly effective for multi-pollutant sensor outlier detection.
- **Physical Mass Ratio (PM2.5/PM10)**: The atmospheric ratio of fine particulate matter to total particulate matter. In nature, it sits between 0.3 and 0.8. Ratios $> 1.0$ indicate optical sensor drift or calibration errors.
- **Mocking**: Simulating external dependencies (such as HTTP endpoints or disk I/O) in automated tests so tests run quickly, reliably, deterministically, and offline.
