# 09 — Testing Strategy & Quality Assurance

In data engineering, automated testing is essential to prevent silent data corruption. A broken pipeline is bad, but a pipeline that silently writes invalid data into production tables is catastrophic.

---

## 1. The Data Engineering Testing Pyramid

```
                / \
               /   \      Live API Smoke Tests (1 Test)
              /     \     - Bounded, optional, manually triggered
             /───────\
            /         \   End-to-End Integration Tests (4 Tests)
           /           \  - Uses offline fixtures, temporary SQLite DBs, idempotency verification
          /─────────────\
         /               \ Unit & Component Tests (26 Tests)
        /                 \ - Isolated, mocked network calls, SQL analytics, ML anomaly detection
       /───────────────────\
```

---

## 2. Why Automated Tests Must NEVER Depend on Live APIs

Automated CI/CD pipelines and local test runners must never make unmocked calls to external APIs:
1. **Flakiness**: An upstream network hiccup or temporary maintenance window will cause CI test suites to fail randomly even when the pipeline code is completely correct.
2. **Rate Limits & Costs**: Automated test suites executed across multiple branches or commits would rapidly exhaust free-tier API quotas.
3. **Determinism**: Live weather and pollution metrics change every hour. An assertion like `assert response["pm2_5"] == 95.7` will fail the next hour when air quality shifts.
4. **Offline Capability**: Engineers should be able to run `python -m pytest` on a laptop with zero internet access (e.g. while traveling or in isolated development environments).

---

## 3. Mocking Network Calls in `test_extract.py`

In `tests/test_extract.py`, we use Python's `unittest.mock.patch` to simulate HTTP behavior:

### Example: Testing HTTP 429 Rate Limiting & Recovery
```python
def test_fetch_city_rate_limit_with_retry_after(test_config, sample_live_response_payload):
    extractor = AQIExtractor(test_config)

    # First call returns 429 Rate Limit; Second call returns 200 OK
    resp_429 = MagicMock(status_code=429, headers={"Retry-After": "0"})
    resp_200 = MagicMock(status_code=200, json=lambda: sample_live_response_payload)
    resp_200.raise_for_status.return_value = None

    with patch.object(extractor.session, "get", side_effect=[resp_429, resp_200]) as mock_get:
        result = extractor.fetch_city_data("Mumbai", 19.0760, 72.8777)
        assert mock_get.call_count == 2
        assert result["_metadata"]["city"] == "Mumbai"
```

---

## 4. Testing Idempotency in `test_load.py` & `test_pipeline.py`

Idempotency is verified programmatically by executing the load stage twice with identical input data:

```python
def test_idempotency_loading_same_record_twice(test_config, sample_record):
    loader = AQILoader(test_config)

    # First load: Record should be inserted
    ins1, upd1 = loader.load_observations([sample_record])
    assert ins1 == 1
    assert upd1 == 0
    assert loader.get_total_observations_count() == 1

    # Second load: Same record should be updated, NOT inserted
    ins2, upd2 = loader.load_observations([sample_record])
    assert ins2 == 0
    assert upd2 == 1

    # Total rows in the database MUST remain exactly 1
    assert loader.get_total_observations_count() == 1
```

---

## 5. Testing Transaction Rollback on Failure

To prove that partial failures never leave corrupt data in the database, `test_load.py` simulates a mid-transaction crash:

```python
def test_transaction_rollback_on_failure(test_config):
    loader = AQILoader(test_config)

    with loader.get_connection() as conn:
        with pytest.raises(Exception):
            with conn:
                conn.execute("INSERT INTO aqi_observations (city) VALUES ('Partial');")
                raise sqlite3.OperationalError("Simulated crash mid-transaction")

    # The transaction rolled back: total rows must be 0
    assert loader.get_total_observations_count() == 0
```

---

## 6. Testing SQL Analytics & Dataset Export in `test_analytics.py`

In `tests/test_analytics.py`, we seed the temporary SQLite test database via `AQIPipeline.run(mode="fixture")` and verify analytical aggregations:

```python
def test_zone_and_category_analytics_and_export(test_config, tmp_path):
    pipeline = AQIPipeline(test_config)
    pipeline.run(mode="fixture")

    analytics = AQIAnalytics(test_config)

    # 1. Test Zone aggregation
    zone_df = analytics.get_zone_summary_metrics()
    assert not zone_df.empty
    assert "zone" in zone_df.columns
    assert "avg_aqi" in zone_df.columns

    # 2. Test Category breakdown
    cat_df = analytics.get_aqi_category_breakdown()
    assert not cat_df.empty
    assert "aqi_category" in cat_df.columns

    # 3. Test CSV Export
    csv_dest = tmp_path / "exports" / "test_observations.csv"
    res_path = analytics.export_observations_to_csv(csv_dest)
    assert res_path.exists()
    assert res_path.stat().st_size > 0
```

---

## 7. Testing Scikit-Learn Anomaly Detection in `test_anomaly.py`

In `tests/test_anomaly.py`, we test Isolation Forest unsupervised detection and physical rule validation against synthetic baselines:

```python
def test_anomaly_detection_with_outlier():
    detector = AQIAnomalyDetector(contamination=0.2, random_state=42)
    # 5 baseline cities + 1 artificial extreme multi-pollutant spike
    df = pd.DataFrame(data_with_outlier)
    scored = detector.detect_anomalies(df)

    outlier = scored[scored["city"] == "OutlierCity"].iloc[0]
    assert outlier["is_anomaly"] == True
    assert outlier["anomaly_score"] > 0.5


def test_domain_rule_pm_inversion_detected():
    detector = AQIAnomalyDetector(contamination=0.1)
    # PM2.5 = 90.0 > PM10 = 30.0 (physically impossible optical inversion)
    scored = detector.detect_anomalies(df_inverted)
    inv = scored[scored["city"] == "InvertedCity"].iloc[0]
    assert inv["is_anomaly"] == True
    assert "PM2.5 > PM10" in inv["anomaly_reason"]
```

---

## 8. The Optional Live Smoke Test

While automated regression tests use mocks, we provide a dedicated live smoke test in `tests/test_live_smoke.py`:
- Marked with `@pytest.mark.live`.
- By default, `python -m pytest` **skips** this test cleanly.
- To execute against the real live API:
  ```powershell
  python -m pytest --run-live tests/test_live_smoke.py
  ```
- It makes a single, bounded request for New Delhi, validates the live schema, and verifies that the live payload passes through `AQITransformer` successfully.

