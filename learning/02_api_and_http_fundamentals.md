# 02 — API & HTTP Fundamentals for Data Engineers

In data engineering, external REST APIs are one of the most common sources of operational data. This guide covers how APIs work conceptually, how HTTP requests and responses operate, and the specifics of the Open-Meteo Air Quality API.

---

## 1. What is an API and REST?

An **API (Application Programming Interface)** is a structured contract through which two systems exchange data over a network. 

**REST (Representational State Transfer)** is an architectural style built on top of the HTTP protocol:
- **Stateless**: Each request contains all information needed to process it; the server retains no session context between calls.
- **Resource-Oriented**: Resources (e.g. weather data, air quality reports) are identified by URLs.
- **Standard HTTP Methods**:
  - `GET`: Retrieve data without altering server state (idempotent & safe).
  - `POST`: Create a new resource.
  - `PUT`/`PATCH`: Update an existing resource.
  - `DELETE`: Remove a resource.

For our ingestion pipeline, we only perform `GET` requests because we are extracting observational data.

---

## 2. Anatomy of an HTTP GET Request

When our `AQIExtractor` calls the external API, it sends an HTTP request formatted like this:

```http
GET /v1/air-quality?latitude=28.6139&longitude=77.2090&current=pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,us_aqi&timezone=Asia%2FKolkata HTTP/1.1
Host: air-quality-api.open-meteo.com
User-Agent: python-requests/2.32.5
Accept-Encoding: gzip, deflate
Accept: */*
Connection: keep-alive
```

### Components:
1. **Target Endpoint**: `https://air-quality-api.open-meteo.com/v1/air-quality`
2. **Query Parameters**: Key-value pairs after `?` separated by `&`:
   - `latitude=28.6139`, `longitude=77.2090`: Geographic coordinates for New Delhi.
   - `current=...`: Comma-separated list of pollutant metrics requested.
   - `timezone=Asia/Kolkata`: Tells the API to format timestamps in Indian Standard Time (IST, UTC+05:30).
3. **Request Headers**: Metadata about the client, accepted formats, and keep-alive preferences.

---

## 3. Anatomy of an HTTP Response

The server replies with an HTTP response containing a status code, response headers, and a JSON payload:

```http
HTTP/1.1 200 OK
Date: Thu, 15 Oct 2026 17:49:11 GMT
Content-Type: application/json; charset=utf-8
Content-Encoding: gzip

{
  "latitude": 28.599998,
  "longitude": 77.20001,
  "generationtime_ms": 0.32,
  "utc_offset_seconds": 19800,
  "timezone": "Asia/Kolkata",
  "timezone_abbreviation": "GMT+5:30",
  "elevation": 214.0,
  "current_units": {
    "time": "iso8601",
    "pm10": "μg/m³",
    "pm2_5": "μg/m³",
    "carbon_monoxide": "μg/m³",
    "nitrogen_dioxide": "μg/m³",
    "sulphur_dioxide": "μg/m³",
    "ozone": "μg/m³",
    "us_aqi": "USAQI"
  },
  "current": {
    "time": "2026-10-15T22:30",
    "interval": 3600,
    "pm10": 106.2,
    "pm2_5": 95.7,
    "carbon_monoxide": 1674.0,
    "nitrogen_dioxide": 79.5,
    "sulphur_dioxide": 41.9,
    "ozone": 27.0,
    "us_aqi": 158
  }
}
```

---

## 4. HTTP Status Codes Explained

| Status Code | Class | Meaning | Pipeline Behavior |
|:---:|:---:|:---|:---|
| **200 OK** | Success | Request succeeded; payload available. | Process and pass to Transform stage. |
| **400 Bad Request** | Client Error | Invalid parameter (e.g. `latitude=999.0`). | **Do NOT retry**. Log error immediately. |
| **401 Unauthorized** | Client Error | Missing or invalid API key. | **Do NOT retry**. Alert engineer. |
| **403 Forbidden** | Client Error | Insufficient permissions or quota blocked. | **Do NOT retry**. |
| **404 Not Found** | Client Error | Endpoint URL incorrect. | **Do NOT retry**. |
| **429 Too Many Requests** | Rate Limit | Request rate exceeded provider limits. | **Retry** with backoff or respect `Retry-After`. |
| **500 Internal Error** | Server Error | Server crashed processing request. | **Retry** with exponential backoff. |
| **502 / 503 / 504** | Gateway/Timeout | Upstream proxy or gateway timed out. | **Retry** with exponential backoff. |

---

## 5. Rate Limits & Quota Governance

The Open-Meteo Air Quality API operates on a transparent usage model:
- **Free Tier**: Up to 10,000 API calls per day, 600 calls per minute, non-commercial use. No API key required.
- **Commercial Tier**: Higher throughput, SLA guarantees, requires `apikey` query parameter.

### How Our Code Governs Rate Limits:
1. **Polite Pacing**: In `extract.py`, we inject a configurable `rate_limit_delay_seconds` (default 0.2s) between sequential city calls to prevent bursting.
2. **Retry-After Header**: When an HTTP 429 occurs, `extract.py` inspects the response headers for `Retry-After: <seconds>` and pauses execution accordingly.
