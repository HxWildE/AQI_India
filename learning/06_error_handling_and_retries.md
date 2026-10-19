# 06 — Error Handling, Exponential Backoff & Resilience

Distributed systems and external APIs are inherently unreliable. Network packets drop, DNS resolution stutters, servers restart, and rate limiters trigger. A senior data engineer designs pipelines assuming failure is inevitable.

---

## 1. Transient vs. Permanent Errors

The most critical architectural decision in error handling is distinguishing between errors that can be solved by retrying and errors that cannot:

```
                      An Error Occurs
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
    [ Transient Error ]             [ Permanent Error ]
  - Connection Reset / Timeout    - HTTP 400 Bad Request
  - HTTP 429 (Rate Limit)         - HTTP 401 Unauthorized
  - HTTP 500 / 502 / 503 / 504    - HTTP 404 Not Found
            │                               │
            ▼                               ▼
   [ Retry with Backoff ]         [ Abort Immediately ]
                                  (Do NOT retry blindly)
```

### Why Indiscriminate Retrying is Harmful:
If an API endpoint returns `400 Bad Request` because a coordinate is invalid (`latitude=999.0`), retrying 5 times with backoff will never change the outcome. It wastes network bandwidth, delays the pipeline run, and can trigger security IP bans.

---

## 2. Exponential Backoff Mathematics

When an API service is temporarily overwhelmed (or rate-limited), retrying immediately with a tight loop (e.g. `while True: retry()`) creates a **thundering herd problem** that drives the remote server further into failure.

**Exponential Backoff** spaces out retry attempts geometrically:

$$\text{sleep\_time} = \text{backoff\_factor} \times 2^{\text{attempt} - 1}$$

With `backoff_factor = 1.5` and `max_retries = 3`:
- **Attempt 1 Failure**: $1.5 \times 2^0 = 1.50\text{ seconds}$
- **Attempt 2 Failure**: $1.5 \times 2^1 = 3.00\text{ seconds}$
- **Attempt 3 Failure**: $1.5 \times 2^2 = 6.00\text{ seconds}$

---

## 3. Handling HTTP 429 & The `Retry-After` Header

When an API server enforces rate limiting, standard RFC specifications allow the server to return an HTTP header named `Retry-After`:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
```

Our implementation in `src/aqi_pipeline/extract.py` explicitly inspects this header:

```python
if response.status_code == 429:
    retry_after = response.headers.get("Retry-After")
    sleep_time = (
        float(retry_after)
        if retry_after and retry_after.isdigit()
        else self.config.backoff_factor * (2 ** (attempt - 1))
    )
    self.logger.warning(
        f"Rate limited (429) for {city_name}. Backing off for {sleep_time:.2f}s..."
    )
    time.sleep(sleep_time)
    continue
```

If the header is present, the pipeline respects the provider's requested cool-down interval. If absent, it gracefully falls back to mathematical exponential backoff.

---

## 4. Explicit Network Timeouts

A common cause of hanging production jobs is calling `requests.get(url)` without a timeout parameter:

```python
# ❌ DANGEROUS: If the remote server drops the socket, this hangs INDEFINITELY:
response = requests.get(url)

# ✅ SAFE: Enforces bounded wait time (e.g. 10 seconds):
response = requests.get(url, timeout=10.0)
```

In `aqi_pipeline`, every network interaction uses `self.config.timeout_seconds` to ensure pipeline jobs terminate cleanly even during complete network partitions.
