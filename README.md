# ReleaseGuard v0.1 — Production-Hardened Release Reliability Platform

ReleaseGuard is a developer reliability, error-tracking, and controlled mitigation platform. It bridges continuous telemetry ingestion with deterministic feature flag delivery and human-in-the-loop incident mitigation.

---

## 1. Project Overview

ReleaseGuard provides a modern, full-stack reliability engineering toolkit:
- High-throughput asynchronous error event ingestion via Redis Streams.
- Frame normalization, cryptographic stack trace fingerprinting, and concurrency-safe PostgreSQL issue aggregation.
- Multi-tenancy with Role-Based Access Control (Owner, Admin, Member) and transactional Last-Owner protection.
- Deterministic feature flag delivery with percentage-based rollouts and ETag/304 caching.
- Automated anomaly detection correlating error spikes to recent deployments and feature flags.
- Controlled incident mitigation requiring explicit authenticated human approval.
- Full audit logging tracking every flag change, rollout shift, and mitigation action.

---

## 2. Architecture

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
|  - Distributed Auth Rate Limiter & Lockout (429 Too Many Requests)          |
|  - JWT Authentication (HS256) & RBAC Enforcement                            |
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

## 3. Main Capabilities

- **Asynchronous Telemetry Ingestion**: Ingest endpoints respond in under 25ms (`HTTP 202 Accepted`), queuing payloads onto Redis Streams (`events:stream`).
- **End-to-End Idempotency**: Stable UUID4 `event_id` enforced by PostgreSQL unique constraints. Re-delivered messages are safely rolled back and acknowledged via `XACK` without corrupting counts.
- **Deterministic Feature Rollouts**: Rollout buckets are calculated via `CRC32(flag_key + ":" + user_id) % 100`. For any user and flag, evaluation results are mathematically stable.
- **Issue Grouping & Regression Detection**: Resolving an issue transitions it to `resolved`. New occurrences automatically trigger regression detection, returning the issue to `unresolved`.
- **Advisory Mitigation with Human-in-the-Loop**: Spikes produce actionable root-cause recommendations (kill feature flag or rollback release). Destructive mitigations require explicit human approval and record an immutable audit trail.
- **Multi-Tenant Data Scoping**: Client requests cannot forge tenant identity; row-level query scoping prevents cross-tenant data leakage.

---

## 4. Tech Stack

- **Backend API**: Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic v2, PyJWT, bcrypt.
- **Persistent Database**: PostgreSQL 17.
- **Queue / Cache**: Redis 7 (Redis Streams, Consumer Groups, Distributed Keys).
- **Database Migrations**: Alembic.
- **Frontend Dashboard**: React 18, Vite, TailwindCSS, Lucide Icons.
- **Frontend Web Server**: Nginx (Alpine).
- **Client SDK**: Python SDK with non-blocking worker thread and bounded queue.

---

## 5. Repository Structure

```
releaseguard_v0_1/
├── backend/
│   ├── alembic.ini                   # Alembic configuration
│   ├── Dockerfile                    # Production backend container definition
│   ├── migrations/                   # Alembic database migrations
│   │   ├── env.py
│   │   └── versions/
│   ├── app/                          # FastAPI application core
│   │   ├── auth.py                   # JWT & password hashing
│   │   ├── auth_limiter.py           # Distributed Redis auth rate limiter
│   │   ├── config.py                 # Pydantic environment settings
│   │   ├── db.py                     # SQLAlchemy session & engine
│   │   ├── models.py                 # SQLAlchemy database models
│   │   ├── queue.py                  # Redis Streams event queue
│   │   ├── worker.py                 # Autonomous ingestion worker
│   │   ├── routers/                  # API endpoints
│   │   │   ├── auth.py
│   │   │   ├── events.py
│   │   │   ├── flags.py
│   │   │   ├── incidents.py
│   │   │   ├── issues.py
│   │   │   ├── metrics.py
│   │   │   ├── releases.py
│   │   │   └── tenants.py
│   │   └── main.py                   # Application entrypoint & middleware
│   ├── scripts/                      # Operational scripts
│   │   ├── run_benchmarks.py         # Performance benchmark suite
│   │   ├── seed_demo.py              # Deterministic demo data seeder
│   │   └── verify_migration_equivalence.py
│   └── tests/                        # Backend test suite (pytest)
├── frontend/
│   ├── Dockerfile                    # Production frontend container
│   ├── nginx.conf                    # Nginx SPA & security config
│   ├── src/                          # React application code
│   │   ├── components/               # UI components
│   │   ├── context/                  # React Auth & Project Context
│   │   ├── pages/                    # Route pages
│   │   └── services/                 # API client layer (api.js)
│   └── package.json
├── sdk/
│   └── python/                       # ReleaseGuard Python SDK
│       ├── releaseguard/
│       └── tests/
├── docs/                             # Documentation
│   ├── architecture.md
│   ├── deployment.md
│   ├── demo.md
│   ├── project_summary.md
│   └── security_audit.md
├── docker-compose.yml                # Production staging orchestration
├── .env.example                      # Production environment template
└── README.md
```

---

## 6. Local Setup

### Prerequisites
- Python 3.11+
- Node.js 20+ (with npm)
- PostgreSQL 16+ running on `localhost:5432`
- Redis 6.2+ running on `localhost:6379`

### Environment File Setup
Copy the example environment template:
```bash
cp .env.example .env
```

---

## 7. PostgreSQL Setup

Create a database dedicated to ReleaseGuard:
```sql
CREATE DATABASE releaseguard;
CREATE USER postgres WITH ENCRYPTED PASSWORD 'postgres';
GRANT ALL PRIVILEGES ON DATABASE releaseguard TO postgres;
```

---

## 8. Redis Setup

Ensure Redis is installed and running on port `6379`:
```bash
redis-cli ping
# Expected response: PONG
```

---

## 9. Environment Variables

Configure `.env` with required parameters:
```env
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/releaseguard
REDIS_URL=redis://127.0.0.1:6379/0
JWT_SECRET=your-32-byte-hex-secret-must-be-secure
JWT_EXPIRATION_MINUTES=1440
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
FRONTEND_URL=http://localhost:5173
MAX_PAYLOAD_SIZE=1048576
MAX_BULK_PAYLOAD_SIZE=5242880
MAX_BULK_EVENTS=100
AUTH_MAX_ATTEMPTS=5
AUTH_LOCKOUT_SECONDS=900
```

---

## 10. Alembic Migrations

All schema changes are tracked and applied through Alembic:
```bash
cd backend
alembic upgrade head
```

---

## 11. Backend Startup

To run the backend in production mode without reload:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
For development with hot reloading:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 12. Worker Startup

Run the Redis Streams ingestion worker in an independent process:
```bash
python -m app.worker
```
The worker will automatically create consumer groups, process queued events, handle stale PEL entries, and route toxic events to `events:dlq`.

---

## 13. Frontend Startup

For local development:
```bash
cd frontend
npm install
npm run dev
```
For production build:
```bash
cd frontend
npm run build
```

---

## 14. Test Commands

Run the full automated test suite (98 tests across backend and SDK):
```bash
pytest -v backend sdk/python/tests
```

---

## 15. Seed / Demo Data

To populate deterministic sample data for demonstrations:
```bash
python backend/scripts/seed_demo.py
```
This idempotently creates:
- **Organization**: Acme Corp
- **User**: `demo@releaseguard.dev` / `DemoPassword123!`
- **Project**: Checkout Service
- **Environments**: development, staging, production
- **Releases**: `1.0.0`, `1.1.0`, `1.2.0`
- **Feature Flags**: `new_checkout`, `new_payment_flow`, `experimental_dashboard`
- **Sample Issues**: `DatabaseConnectionTimeout`, `PaymentGatewayError`, `AuthenticationError`
- **Incidents**: `Payment Gateway Surge`, `Database Error Spike`

---

## 16. Deployment Architecture

In production, ReleaseGuard deploys as isolated containers:
1. **Frontend**: Static bundle served via Alpine Nginx.
2. **API**: FastAPI running under Uvicorn ASGI behind a load balancer.
3. **Worker**: Standalone background Python consumer.
4. **PostgreSQL**: Managed persistent relational cluster.
5. **Redis**: Managed Redis cluster with persistence enabled.

Refer to [`docs/deployment.md`](file:///d:/releaseguard_v0_1/docs/deployment.md) for full instructions and Kubernetes/Docker specifications.

---

## 17. Health & Readiness Checks

- **Liveness Probe**: `GET /health` -> `{"status": "ok", "service": "releaseguard-api"}`
- **Readiness Probe**: `GET /health/ready` -> Verifies active PostgreSQL and Redis connectivity:
  ```json
  {
    "status": "ready",
    "checks": {
      "database": "connected",
      "redis": "connected"
    }
  }
  ```

---

## 18. Example ReleaseGuard Workflow

See [`docs/demo.md`](file:///d:/releaseguard_v0_1/docs/demo.md) for the complete 18-step interactive scenario covering:
1. Release deployment (`v1.3.0`)
2. Feature flag rollout (`25%`)
3. SDK error telemetry ingestion
4. Asynchronous worker ingestion & issue deduplication
5. Anomaly detection & incident triggering
6. Automated correlation with release & flag
7. Human-approved mitigation (flag kill-switch)
8. Audit trail verification and incident resolution

---

## 19. Known Limitations

- **Stateless JWT Blacklisting**: Revoking a compromised token before expiration requires token expiration or client-side storage clearance.
- **Worker Scale Group Coordination**: Workers coordinate via Redis consumer groups; duplicate worker identifiers within the same consumer group must be avoided.
- **Telemetry Throttling**: Ingestion rate limits rely on upstream reverse proxies (Nginx / Cloudflare) to protect the edge API from massive volumetric DDoS.

---

## 20. Benchmark Methodology

Benchmarks are executed via `backend/scripts/run_benchmarks.py` using statistical sampling across 50 iterations:

| Metric | Sample Size | Mean | Median | P95 |
| :--- | :--- | :--- | :--- | :--- |
| **Config Evaluation (ETag Cached)** | 50 | **6.64 ms** | **6.58 ms** | **7.68 ms** |
| **Paginated Issue Query (`limit=20`)** | 50 | **15.64 ms** | **15.50 ms** | **16.92 ms** |
| **Paginated Event Query (`limit=20`)** | 50 | **22.01 ms** | **19.76 ms** | **22.92 ms** |
| **Authenticated API Request** | 50 | **19.45 ms** | **19.34 ms** | **22.50 ms** |
| **Bulk Event Ingestion (`25 events`)** | 50 | **23.74 ms** | **23.65 ms** | **27.44 ms** |
| **Worker Batch Processing (`10 events`)** | 25 | **103.57 ms**| **101.72 ms**| **114.00 ms**|

*Measurements conducted locally on Windows 11, Python 3.12, PostgreSQL 17, Redis 7.*
