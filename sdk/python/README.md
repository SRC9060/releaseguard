# ReleaseGuard Python SDK (`releaseguard-sdk`)

The official Python client library for the **ReleaseGuard Developer Reliability Platform**.

ReleaseGuard captures runtime exceptions, generates stable fingerprints, clusters duplicate failures into distinct issues, and tracks release regressions.

---

## The Core Guarantee

> **ReleaseGuard failure must not become the application's failure.**
>
> If ReleaseGuard is slow, unreachable, rate-limited, or completely offline:
> - Your application continues executing normally.
> - `capture_exception()` never blocks your thread for network I/O.
> - SDK internal failures never bubble up to crash your host application.
> - Memory usage is strictly bounded.

---

## Architecture

```
Application Thread
        ↓
capture_exception() [Non-blocking: constructs Event & enqueues in <0.1ms]
        ↓
Bounded Queue (default 1,000 items; drops oldest on overflow)
        ↓
Background Worker (Daemon thread consuming queue)
        ↓
HTTP Ingestion (Batch/retry loop with exponential backoff)
        ↓
ReleaseGuard Backend (POST /api/v1/projects/{project_id}/events)
```

---

## Installation

```bash
pip install ./sdk/python
```

*Note: The SDK relies solely on Python's standard library (`urllib`, `threading`, `queue`, `traceback`) with zero third-party dependencies, guaranteeing no dependency version conflicts.*

---

## Quickstart

```python
import releaseguard_sdk

# 1. Initialize once at application startup
releaseguard_sdk.init(
    project_id=1,
    base_url="http://127.0.0.1:8000",
    release="1.0.0",
    environment="production",
)

# 2. Capture exceptions seamlessly
try:
    1 / 0
except Exception:
    releaseguard_sdk.capture_exception()

# 3. Clean shutdown (optional; registered automatically via atexit)
releaseguard_sdk.shutdown(timeout=2.0)
```

---

## Configuration Reference

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `project_id` | `int` | *Required* | The ReleaseGuard project ID. |
| `base_url` | `str` | `"http://127.0.0.1:8000"` | Base URL of the ReleaseGuard backend. |
| `api_key` | `str` | `""` | Optional API ingest key (forward compatibility). |
| `release` | `str \| None` | `None` | Version/tag of your application release. |
| `environment` | `str` | `"production"` | Deployment environment name. |
| `max_queue_size`| `int` | `1000` | Maximum events buffered in memory. |
| `flush_interval`| `float` | `0.5` | Max seconds background worker waits before flushing batch. |
| `batch_size` | `int` | `20` | Max events processed per worker iteration. |
| `max_retries` | `int` | `3` | Max retries for transient HTTP errors (5xx/timeouts). |
| `retry_backoff`| `float` | `0.1` | Initial exponential backoff delay in seconds. |
| `timeout` | `float` | `5.0` | Network request timeout in seconds. |
| `debug` | `bool` | `False` | Enables internal SDK debug logging. |

---

## Key Behaviors

### 1. Non-Blocking Execution
`capture_exception()` parses the active exception from `sys.exc_info()`, formats the traceback, and pushes an `Event` to the bounded queue. It performs **no network I/O** on the calling thread, completing in microseconds.

### 2. Bounded Queue & Overflow Policy
If the host application produces an unexpected flood of errors and the worker cannot transmit fast enough, the queue hits `max_queue_size`.
- **Policy**: **Drop Oldest**.
- The oldest un-sent error in the queue is evicted to make room for the new error event.
- Your application's memory is capped and never leaks.
- Internal counter `stats.dropped` increments.

### 3. Bounded Retries & Backoff
- **Transient Failures (5xx, Network Errors, Timeouts)**: Retried up to `max_retries` times with exponential backoff (`backoff * 2^attempt`).
- **Permanent Client Errors (4xx)**: Discarded immediately without retry.
- After retry exhaustion, the event is dropped and `stats.failed` increments.

### 4. Process Exit & Shutdown
The SDK automatically registers an `atexit` hook that attempts to flush remaining queued events for up to 1.5 seconds. You can also explicitly call:
```python
releaseguard_sdk.flush(timeout=2.0)
releaseguard_sdk.shutdown(timeout=2.0)
```
Shutdown logic enforces a hard timeout and will never cause your application process to hang indefinitely.

---

## Internal Telemetry Counters

You can inspect the client's internal telemetry at any time:

```python
client = releaseguard_sdk.get_client()
if client:
    print(client.stats)
    # WorkerStats(queued=100, sent=98, dropped=0, failed=2)
```
