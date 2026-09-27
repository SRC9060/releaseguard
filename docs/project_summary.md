# ReleaseGuard: Technical Engineering Summary

ReleaseGuard is a production-grade, multi-tenant release reliability and error tracking platform with deterministic feature flagging and controlled incident mitigation.

---

## 1. System Architecture

ReleaseGuard decouples high-throughput telemetry ingestion from persistence and query workloads using an asynchronous stream architecture:

- **Frontend**: React 18, Vite, TailwindCSS SPA served via Alpine Nginx with client-side SPA routing and security headers.
- **Backend API**: Stateless FastAPI engine running on Uvicorn ASGI; exposes authenticated multi-tenant management endpoints and high-throughput ingestion handlers.
- **Buffer / Queue**: Redis 7 Redis Streams (`events:stream`) with persistent consumer groups (`events:group`), pending entry list (PEL) tracking, and dead-letter queues (`events:dlq`).
- **Persistence**: PostgreSQL 17 relational database enforcing ACID compliance, transactional row locking, and Alembic-managed migrations.
- **Worker**: Autonomous Python consumer process executing transactional batch consumption, stack trace parsing, fingerprint derivation, and idempotent persistence.

---

## 2. Hardest Engineering Problems Solved

### A. Idempotent Ingestion Under Unreliable Network Conditions
- **The Challenge**: At-least-once message delivery in distributed systems (network retries, worker restarts, delayed Redis acks) inherently risks duplicate event insertion and corrupted issue counters.
- **The Solution**: ReleaseGuard mandates a client- or server-assigned UUID4 `event_id` enforced with a database-level `UNIQUE` constraint on `error_events.event_id`. When the worker detects an `IntegrityError` on `event_id`, it rolls back the active transaction, identifies the redelivery, logs the duplicate gracefully, and sends an immediate `XACK` to Redis, preventing queue stalls and double-counting.

### B. High-Concurrency Issue Aggregation
- **The Challenge**: During an outage, hundreds of identical errors strike the API simultaneously. Naive `SELECT ... IF NOT EXISTS ... INSERT` sequences cause race conditions and unique constraint violations on `(project_id, fingerprint)`.
- **The Solution**: PostgreSQL atomic upsert statements with row-level locking serialize concurrent issue updates without deadlocks. Issue counters are incremented atomically (`count = count + 1`), updating `last_seen` timestamps in a single atomic round-trip.

### C. Zero-Degradation Worker Crash Recovery
- **The Challenge**: If a background worker terminates midway through processing a Redis stream batch, consumed events remain trapped in the Redis Pending Entries List (PEL), never reaching the database.
- **The Solution**: The worker implements a proactive PEL recovery loop utilizing `XPENDING` and `XCLAIM`. Messages pending beyond a configurable idle threshold (e.g. 60,000ms) are reclaimed by surviving worker nodes. If a poisoned payload fails `MAX_RETRIES` times, it is safely diverted to `events:dlq`.

### D. Concurrency-Safe Last-Owner Retention in Multi-Tenancy
- **The Challenge**: In multi-tenant organizations, two concurrent administrative requests can simultaneously observe `owner_count == 2` and both delete or demote themselves, leaving an orphaned tenant with zero owners.
- **The Solution**: Enforced pessimistic row-level locking (`SELECT ... FOR UPDATE`) across tenant memberships during role mutations, guaranteeing strict serializability and preserving the invariant that every tenant must retain at least one Owner.

### E. Deterministic, Zero-Latency Feature Rollouts
- **The Challenge**: Client applications need real-time feature flag evaluation without making synchronous database queries on every user interaction.
- **The Solution**: Feature rollouts use mathematically invariant hashing:
  $$\text{bucket} = \text{CRC32}(\text{flag\_key} + \text{":"} + \text{user\_id}) \pmod{100}$$
  The config endpoint hashes the entire flagset into an HTTP `ETag`, allowing clients to receive `304 Not Modified` with zero database or JSON parsing overhead.

### F. Human-in-the-Loop Incident Mitigation
- **The Challenge**: Autonomous systems that automatically kill feature flags or rollback releases risk cascading false-positive outages.
- **The Solution**: ReleaseGuard computes automated correlation between error spikes, releases, and feature flags, generating advisory mitigation strategies. Mitigation execution requires explicit, authenticated human approval with strict RBAC validation and an immutable audit trail (`flag_audit_logs`).

---

## 3. Verified Local Benchmark Results

All benchmarks were locally measured on a Windows development host running Python 3.12, FastAPI/Uvicorn, PostgreSQL 17, and Redis 7 (via `backend/scripts/run_benchmarks.py`):

| Endpoint / Operation | Sample Count | Mean Latency | Median Latency | P95 Latency |
| :--- | :--- | :--- | :--- | :--- |
| **Config Evaluation Endpoint (ETag cached)** | 50 | **6.64 ms** | **6.58 ms** | **7.68 ms** |
| **Paginated Issue Query (`limit=20`)** | 50 | **15.64 ms** | **15.50 ms** | **16.92 ms** |
| **Paginated Event Query (`limit=20`)** | 50 | **22.01 ms** | **19.76 ms** | **22.92 ms** |
| **Authenticated API Request (JWT validation + DB query)** | 50 | **19.45 ms** | **19.34 ms** | **22.50 ms** |
| **Bulk Event Ingestion (`25 events / HTTP 202`)** | 50 | **23.74 ms** | **23.65 ms** | **27.44 ms** |
| **Worker Batch Processing (`10 events / parsing + upserts`)**| 25 | **103.57 ms**| **101.72 ms**| **114.00 ms**|

*Note: Latency measurements are local baseline figures; production capacity will scale horizontally with additional API and worker replicas.*

---

## 4. Key Security & Reliability Invariants

- **Zero Client Trust**: Client-supplied `tenant_id` headers or URL segments are cross-checked against authenticated JWT claims and server-side membership records. Non-existent or inaccessible tenant resources return `404 Not Found` to prevent resource enumeration.
- **Strict Rate Limiting**: Distributed Redis rate limiter on `/auth/login` triggers account lockout after 5 consecutive failures, with strict production enforcement (fails closed if Redis is down).
- **Zero Log Leakage**: Structured logging automatically sanitizes passwords, bearer tokens, API keys, and authorization headers using a custom `RedactingFormatter`.
