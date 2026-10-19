# 04 — Data Quality, Validation & Quarantine Patterns

"Garbage in, garbage out" is the central hazard of data engineering. In real-world sensor networks, monitors frequently lose calibration, report negative numbers, freeze timestamps, or drop connectivity. This guide details how our pipeline validates incoming data and manages defective records.

---

## 1. Physical Boundary Rules

Air pollutants represent mass concentrations per volume of air (typically micrograms per cubic meter, $\mu\text{g/m}^3$). Negative values are physically impossible, and values above known atmospheric extremes reflect sensor short-circuits.

In `src/aqi_pipeline/config.py`, we define explicit physical thresholds:

```python
POLLUTANT_VALIDATION_BOUNDS = {
    "pm2_5": {"min": 0.0, "max": 1000.0, "unit": "μg/m³"},
    "pm10": {"min": 0.0, "max": 2000.0, "unit": "μg/m³"},
    "carbon_monoxide": {"min": 0.0, "max": 50000.0, "unit": "μg/m³"},
    "nitrogen_dioxide": {"min": 0.0, "max": 1000.0, "unit": "μg/m³"},
    "sulphur_dioxide": {"min": 0.0, "max": 1000.0, "unit": "μg/m³"},
    "ozone": {"min": 0.0, "max": 1000.0, "unit": "μg/m³"},
    "us_aqi": {"min": 0.0, "max": 500.0, "unit": "USAQI"},
}
```

---

## 2. The Cardinal Sin: Silent Zero-Imputation

A common novice mistake in ETL pipelines is filling missing values (`None` or `null`) with `0.0`:

```python
# ❌ NEVER DO THIS IN DATA ENGINEERING:
pm2_5 = current.get("pm2_5") or 0.0
```

### Why Silent Zero Imputation is Catastrophic:
1. **0.0 is a Meaningful Number**: In air quality monitoring, a PM2.5 of `0.0` represents pure, pristine air (AQI = 0). If a monitoring station in New Delhi drops offline during a severe winter smog episode and reports `null`, replacing it with `0.0` distorts citywide rolling averages and misleads public health advisories.
2. **Loss of Diagnostic Visibility**: An analyst querying `WHERE pm2_5 IS NULL` can see that sensor data was missing. Once transformed to `0.0`, missing data is indistinguishable from genuine clean air.
3. **Correct Pattern**:
   ```python
   # ✅ PRESERVE MISSING READINGS AS SQL NULL:
   if raw_value is None:
       return True, None, None
   ```

---

## 3. The Quarantine Design Pattern

When an incoming observation fails data quality checks, what should the pipeline do?
- **Option A: Crash the pipeline (`raise Exception`)**: Unacceptable. One malfunctioning sensor in Lucknow should not stop ingestion for Delhi, Mumbai, and Bengaluru.
- **Option B: Silently drop the bad record (`pass`)**: Unacceptable. Downstream engineers will have no record that data arrived, failed, or why.
- **Option C: The Quarantine Pattern (Implemented)**: Divert the defective record into a dedicated `aqi_quarantine` table with an audit trail, while allowing valid records to proceed.

```
Incoming Record
      │
      ▼
Is Valid? 
   ├── YES ──> Insert into `aqi_observations`
   │
   └── NO  ──> Divert to `aqi_quarantine` (stores city, reason, raw JSON snippet, timestamp)
```

### Schema of `aqi_quarantine`:
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

---

## 4. Timezone Math: IST vs. UTC

In India, civil timestamps are reported in **Indian Standard Time (IST)**, which is UTC+05:30 with no daylight saving time (DST).

### Why Store Both Local and UTC?
- `timestamp_local`: Preserves the civil hour (e.g. `2026-10-15T22:30:00+05:30`) which analysts need for diurnal pollution pattern analysis (rush hour peaks, evening inversions).
- `timestamp_utc`: Normalized standard (`2026-10-15T17:00:00+00:00`) used for database indexing, cross-region temporal joins, and unambiguous ordering.

---

## 5. Physical Atmospheric Consistency & Sensor Inversion Rules

Boundary validation checks individual columns independently ($0 \le PM_{2.5} \le 1000$). However, multi-column physical relationships are equally critical:

### The PM2.5 / PM10 Physical Mass Constraint
Particulate matter with aerodynamic diameter $< 2.5\,\mu\text{m}$ ($PM_{2.5}$) is a **physical subset** of particulate matter $< 10\,\mu\text{m}$ ($PM_{10}$). In clean ambient air and normal urban atmospheres:
$$0.3 \le \frac{PM_{2.5}}{PM_{10}} \le 0.8$$

### Optical Sensor Inversion
Low-cost optical particle counters use light scattering. During high humidity or optical chamber contamination, sensors can report $PM_{2.5} > PM_{10}$, which violates the laws of physics:
- Our SQL analytics module (`src/aqi_pipeline/analytics.py`) calculates this ratio via `get_pm_ratio_analysis()`.
- Our ML anomaly module (`src/aqi_pipeline/anomaly.py`) flags any observation where $PM_{2.5} > 1.05 \times PM_{10}$ (when $PM_{2.5} > 20\,\mu\text{g/m}^3$) as a **Sensor Inversion Malfunction**.

