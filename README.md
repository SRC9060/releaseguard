# ReleaseGuard v0.1 — Production Hardening & Reliability

ReleaseGuard is a developer reliability and error-tracking SaaS platform providing:
- High-throughput asynchronous error event ingestion
- Deterministic cryptographic fingerprinting and atomic PostgreSQL issue grouping
- Multi-tenancy with Role-Based Access Control (Owner, Admin, Member) and Last-Owner protection
- Release tracking and incident response with automated advisory recommendations
- Controlled incident mitigation requiring explicit human approval
- Deterministic feature flag evaluation with environment-level rollout rules and ETag/304 caching
- React web dashboard and Python SDK

---

## Core System Principles & Invariants

1. **PostgreSQL is the Persistent Database**: All state (tenants, memberships, projects, issues, error events, releases, flags, incidents, mitigations, audit logs) is durably stored with strict ACID guarantees, foreign keys, and indexes. Schema evolution is managed via Alembic migrations.
2. **Redis Streams is the Asynchronous Queue**: Ingestion is decoupled from PostgreSQL writes. Ingestion endpoints return `HTTP 202 Accepted` in ~15ms by pushing events onto Redis Streams (`releaseguard:events:stream`). A background worker group consumes batches with dead-letter queue (DLQ) routing, `XAUTOCLAIM` stale pending entry recovery, and stream trimming (`MAXLEN ~ 100000`).
3. **The Python SDK Sends Events Asynchronously**: The SDK buffers events in an in-memory bounded queue and transmits them via a background daemon thread. It never executes synchronous network I/O in the application's critical path.
4. **Feature Flags are Evaluated Deterministically**: For a given `(user, flag, environment)` triplet, evaluation is pure and deterministic using integer hashing and rollout thresholds.
5. **Mitigation Requires Explicit Human Approval**: Incident mitigations (e.g. flag kill switches, rollback) are advisory. They require explicit authenticated user approval before execution; autonomous destructive mutations are forbidden.
6. **End-to-End Event Idempotency**: Each event carries a stable UUID `event_id`. If a network retry or redelivery occurs, the worker uses PostgreSQL `ON CONFLICT (event_id) DO NOTHING`. If a duplicate is detected, the transaction rolls back without incrementing issue counts or falsely triggering regressions.

---

## Architecture Overview

```
                      +---------------------------------------+
                      |       Host Application / Client       |
                      +---------------------------------------+
                                          |
                      (non-blocking queue)| (async HTTP)
                                          v
                      +---------------------------------------+
                      |      ReleaseGuard Python SDK          |
                      +---------------------------------------+
                                          |
                                          | POST /api/v1/projects/{id}/events/bulk
                                          v
+-----------------------------------------------------------------------------+
|                          FastAPI API Service                                |
|  - Correlation ID Middleware (X-Request-ID)                                 |
|  - Security Headers (nosniff, DENY, strict-origin)                          |
|  - Payload Size Limiter (413 Payload Too Large)                             |
|  - Auth Rate Limiter & Lockout (429 Too Many Requests)                      |
|  - JWT Authentication & RBAC Enforcement                                    |
|  - Separation: Liveness (/health) & Readiness (/health/ready)               |
+-----------------------------------------------------------------------------+
            |                                           |
    (enqueue events)                               (read state)
            v                                           v
+-------------------------------+           +---------------------------------+
|   Redis Streams Event Queue   |           |    PostgreSQL Persistent DB     |
|  - Stream: events:stream      |           |  - Managed via Alembic          |
|  - Consumer: releaseguard:wrk |           |  - Concurrency-safe Upserts     |
|  - Stale PEL Recovery         |           |  - Strict Tenant Scoping        |
|  - Trimming (MAXLEN ~100000)  |           |  - Connection Pooling           |
+-------------------------------+           +---------------------------------+
            |                                           ^
            | (batch dequeue)                           | (atomic transaction)
            v                                           |
+-------------------------------------------------------+                     |
|           Background Ingestion Worker (worker.py)     |---------------------+
|  - Frame Normalization & SHA-256 Fingerprinting       |
|  - Idempotent Event Insert & Regression Detection     |
|  - Exponential Reconnect Backoff & Stale PEL Recovery |
+-------------------------------------------------------+
```

---

## Local Setup & Prerequisites

### 1. Requirements
- Python 3.11+
- Node.js 20+ (with npm)
- PostgreSQL 16+ running on `localhost:5432`
- Redis 6.2+ running on `localhost:6379`

### 2. Environment Configuration

Copy the example environment configuration to `.env`:
```bash
cp .env.example .env
```

Review and adjust variables in `.env`:
```env
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/releaseguard
REDIS_URL=redis://127.0.0.1:6379/0
JWT_SECRET=your-secure-random-32-byte-hex-string
JWT_EXPIRATION_MINUTES=1440
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
MAX_PAYLOAD_SIZE=1048576
MAX_BULK_PAYLOAD_SIZE=5242880
MAX_BULK_EVENTS=100
AUTH_MAX_ATTEMPTS=5
AUTH_LOCKOUT_SECONDS=900
```

---

## Database Migrations (Alembic)

ReleaseGuard uses Alembic for persistent database schema management.

### Migration Commands

```bash
cd backend

# View current database revision
alembic current

# Apply all pending migrations to head
alembic upgrade head

# Stamp existing development database at head (without re-creating existing tables)
alembic stamp head

# Downgrade one revision
alembic downgrade -1
```

> **Note**: In production mode (`ENVIRONMENT=production`), the application startup never creates or drops database tables. Tables must be migrated explicitly with `alembic upgrade head`.

---

## Running the Application

### 1. Start FastAPI Backend

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Endpoints available:
- **API Documentation**: http://127.0.0.1:8000/docs
- **Liveness Probe**: http://127.0.0.1:8000/health
- **Readiness Probe**: http://127.0.0.1:8000/health/ready

### 2. Start Background Ingestion Worker

In a separate terminal:
```bash
cd backend
python -m app.worker
```

The worker connects to Redis Streams, processes batches, executes PostgreSQL atomic upserts, handles stale pending recovery, and gracefully backs off if Redis is temporarily unreachable.

### 3. Start Frontend Dashboard

In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```

The React dashboard opens at http://localhost:5173.

---

## Testing & Quality Assurance

### Run Full Test Suite

```bash
pytest -v backend sdk/python/tests
```

All 96 automated tests run against PostgreSQL, Redis Streams (using isolated test queues), and the Python SDK.

### Build Frontend Production Bundle

```bash
cd frontend
npm run build
```

---

## Practical Local Performance Benchmarks

Run the benchmark measurement script:
```bash
python backend/scripts/run_benchmarks.py
```

Measured on Windows 11, Python 3.12, PostgreSQL 17:
- **Paginated Issue Query (`limit=20`)**: Mean 16.13ms | Median 15.71ms | P95 20.72ms
- **Paginated Event Query (`limit=20`)**: Mean 19.24ms | Median 16.39ms | P95 25.83ms
- **Config Evaluation Endpoint**: Mean 4.85ms | Median 4.68ms | P95 5.92ms
- **Authenticated API Request**: Mean 15.66ms | Median 15.44ms | P95 19.98ms
- **Bulk Event Ingestion (`25 events`)**: Mean 18.58ms | Median 17.15ms | P95 26.86ms
- **Hardened Worker Batch (`10 events`)**: Mean 80.76ms | Median 81.61ms | P95 96.26ms

---

## Basic Troubleshooting

| Symptom | Cause | Solution |
| :--- | :--- | :--- |
| `GET /health/ready` returns 503 | PostgreSQL or Redis is unreachable | Check PostgreSQL (`psql -U postgres`) and Redis (`redis-cli ping`). |
| Ingestion returns 413 | Request payload exceeds size limit | Reduce batch size or raise `MAX_BULK_PAYLOAD_SIZE`. |
| Login returns 429 | More than 5 failed login attempts | Wait 15 minutes or reset lockout in Redis (`DEL auth:failed:<email>`). |
| Worker warns about duplicate event | Redelivery of already-committed event | Normal idempotent behavior. Transaction is safely rolled back. |
| Alembic revision mismatch | Database is unversioned | Run `alembic stamp head` on existing databases or `alembic upgrade head` on clean databases. |
