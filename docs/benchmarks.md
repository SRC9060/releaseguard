# ReleaseGuard Benchmark & Performance Log

This document records the empirical latency and throughput measurements produced during development and verification.

> [!IMPORTANT]
> All figures in this document represent **local and isolated environment baselines**. They demonstrate the algorithmic efficiency and resource costs of the system under controlled conditions. They must **not** be construed as multi-region production cloud throughput, which depends on network topology, database instance sizing, and horizontal replica counts.

---

## 1. Verified Local API & Pipeline Benchmarks

### Benchmark Run Metadata
- **Date**: September 2026
- **Environment**: Local Development Host (Windows 11 x64, Python 3.12, PostgreSQL 17, Redis 7)
- **Measurement Harness**: `backend/scripts/run_benchmarks.py` using `time.perf_counter` with 5 warm-up iterations prior to measurement.
- **Client**: FastAPI `TestClient` (in-process ASGI execution to measure pure framework/DB latency excluding external network transit).

### Measurement Results

| Operation / Endpoint | Methodology | Sample Size | Mean Latency | Median Latency | P95 Latency | Observed Result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Config Evaluation Endpoint** (`/config?env=production`) | Client GET with ETag checking against seeded flags and rollouts | 50 iterations | **6.64 ms** | **6.58 ms** | **7.68 ms** | Sub-10ms response; highly suitable for high-frequency client flag polling |
| **Paginated Issue Query** (`/issues?limit=20&offset=0`) | SQL query with indexed filtering across 50 issues | 50 iterations | **15.64 ms** | **15.50 ms** | **16.92 ms** | Deterministic pagination with bounded latency |
| **Authenticated API Request** (`/tenants/{id}/projects/{id}`) | Full JWT decode, tenant membership verification, and project query | 50 iterations | **19.45 ms** | **19.34 ms** | **22.50 ms** | Clean multi-tenant security verification under 20ms |
| **Paginated Event Query** (`/issues/{id}/events?limit=20`) | Query across 100 historical error events with stack traces | 50 iterations | **22.01 ms** | **19.76 ms** | **22.92 ms** | Smooth dashboard event inspection |
| **Bulk Event Ingestion** (`/events/bulk`) | POST batch of 25 error events via API key, queuing to Redis stream | 50 iterations | **23.74 ms** | **23.65 ms** | **27.44 ms** | High-throughput non-blocking HTTP 202 response |
| **Worker Batch Processing** (`worker.process_batch`) | Dequeue 10 events, normalize stack traces, compute SHA-256, execute DB upsert | 25 iterations | **103.57 ms** | **101.72 ms** | **114.00 ms** | Asynchronous batch throughput of ~100 events/sec per worker process |

---

## 2. Python SDK Client-Side Benchmark

### Benchmark Run Metadata
- **Date**: September 2026
- **Environment**: Python 3.12 SDK runtime
- **Harness**: `sdk/examples/benchmark.py`

### SDK Performance Results
- **Direct Exception Capture Overhead**: < 0.05 ms per captured exception.
- **Bounded Buffer Behavior**: When background network transport is delayed or severed, SDK worker safely buffers events up to `max_queue_size=1000` without blocking the host application request loop.
- **Drop Policy Under Extreme Backpressure**: When queue overflows, the SDK drops oldest events with an atomic counter log, guaranteeing zero host process memory leak.

---

## 3. AI Incident Copilot Deadline & Failover Timing

### Provider Benchmark Metadata
- **Date**: September 2026
- **Test Harness**: `backend/tests/test_phase15a_copilot.py`, `backend/tests/test_phase15c_copilot_chat.py`
- **Methodology**: Evaluates upstream Gemini provider timeout and fallback latency budgets.

### Measured Timing Properties
- **Overall Hard Deadline**: Bounded at **25.0 seconds** total execution window.
- **Primary Model Budget (`gemini-3.8-flash`)**: 1 retry attempt on transient HTTP 503/429 with 1.0s base backoff + random jitter.
- **Fallback Switch Latency (`gemini-3.5-flash-lite`)**: Instant failover upon primary retry exhaustion, executing with 0 retries to prevent gateway timeout cascading.
- **Deterministic Cache Evaluation**: < 5 ms for identical incident context hashes, bypassing upstream LLM calls entirely.

---

## 4. Benchmark Limitations & Considerations

1. **Local vs Cloud Network Latency**: In-process measurements exclude WAN latency (typical 20–80 ms for client-to-cloud connections).
2. **Single Database Node**: Baseline was recorded on a single PostgreSQL instance; production database performance is enhanced by read replicas for dashboard queries.
3. **Mock Provider Testing**: Automated unit tests execute using `MockCopilotProvider` to guarantee deterministic CI execution without consuming upstream Gemini token quotas or introducing external network variance.
