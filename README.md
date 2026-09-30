# ReleaseGuard — Developer Reliability & Release Protection Platform

ReleaseGuard is a developer reliability, error-tracking, and controlled mitigation platform. It bridges asynchronous high-throughput telemetry ingestion with deterministic feature flag delivery, reversible incident mitigation, and an evidence-grounded AI Incident Copilot.

---

## 1. Project Overview

Modern software teams face a critical reliability gap: error-tracking tools passively alert on crashes, but resolving incidents requires disparate dashboards, manual feature-flag toggling, risky production rollbacks, and high-stress on-call triage.

ReleaseGuard unifies this lifecycle into a single, cohesive developer platform:
- **Asynchronous Telemetry Ingestion**: High-throughput non-blocking ingestion via Redis Streams.
- **Root-Cause Deduplication**: Deterministic frame normalization and SHA-256 stack trace fingerprinting.
- **Deterministic Feature Flags**: Sub-millisecond mathematical rollouts (`CRC32 % 100`) with ETag/304 caching.
- **Reversible Incident Mitigation**: Atomic pre-mitigation state snapshots and one-click rollback.
- **AI Incident Copilot**: Grounded root-cause analysis and conversational investigation powered by Gemini with primary/fallback resiliency and strict advisory-only safety.
- **Multi-Tenant Security**: Tenant-scoped authorization, RBAC (Owner, Admin, Member), and secret-scrubbed observability.

---

## 2. Problem Statement

1. **Alert Fatigue & Duplicate Explosion**: A single distributed failure can generate 100,000 exceptions per minute. Without normalized fingerprinting, databases crash and incident queues become unreadable.
2. **High-Risk Rollbacks**: Reverting a 50-commit deployment to mitigate a minor regression introduces secondary downtime and delays un-related bug fixes.
3. **Configuration Loss During Firefights**: When an engineer disables a feature flag during an outage, the previous percentage rollout is forgotten, turning recovery into an error-prone manual reconfiguration.
4. **Autonomous AI Risk**: Naive AI agents with write permissions to production infrastructure risk catastrophic data loss. AI assistance must be strictly grounded, advisory-only, and verifiable.

---

## 3. Architecture Diagram

```
+-----------------------------------------------------------------------------+
|                                CLIENT TIER                                  |
|   +-----------------------+                    +------------------------+   |
|   |   React Dashboard     |                    |   Host Application     |   |
|   |   (Vite SPA / Vercel) |                    |   (ReleaseGuard SDK)   |   |
|   +-----------+-----------+                    +-----------+------------+   |
+---------------|--------------------------------------------|----------------+
                | HTTP / JWT                                 | HTTP / API Key
                v                                            v
+-----------------------------------------------------------------------------+
|                                BACKEND API                                  |
|      FastAPI ASGI Engine (Uvicorn) - Stateless, Horizontally Scalable       |
|                                                                             |
|  * Auth & RBAC (JWT HS256)           * API Key Validation                   |
|  * Multi-Tenant Isolation Scoping    * Ingestion Handler (HTTP 202)         |
|  * Config Evaluation (ETag Caching)  * Health & Readiness Probes            |
|  * Copilot Rate Limiter & Dedup      * Secret Scrubbing Middleware          |
+---------------+--------------------------------------------+----------------+
                |                                            |
         SQL    |                                            | XADD Stream
                v                                            v
+-------------------------------+            +--------------------------------+
|       PERSISTENT STORE        |            |         STREAM BUFFER          |
|         PostgreSQL 17         |            |            Redis 7             |
|  * Relational Schema          |            |  * Redis Streams               |
|  * Unique idempotency indexes |            |    ('events:stream')           |
|  * Persisted Copilot records  |            |  * Consumer Group              |
+---------------+---------------+            |    ('events:group')            |
                ^                            +---------------+----------------+
                |                                            |
                | SQL (Transactional upserts)                | XREADGROUP / XACK
                |                                            v
+---------------+-------------------------------------------------------------+
|                              ASYNC WORKER TIER                              |
|                      IngestionWorker (Python Process)                       |
|  * Multi-consumer Group Worker       * Stale Pending Entry Recovery (PEL)   |
|  * Batch Processing (XREADGROUP)     * Dead-Letter Queue (DLQ Routing)      |
|  * Idempotent Event Deduplication    * Graceful Signal Handling (SIGINT)    |
+-----------------------------------------------------------------------------+
```

---

## 4. Core Workflow

1. **Capture**: Client application encounters an unhandled exception; ReleaseGuard SDK captures frames non-blockingly.
2. **Ingest**: API accepts event payload (`HTTP 202 Accepted`) and appends to Redis Streams (`events:stream`) in < 25ms.
3. **Process**: Ingestion worker parses stack traces, strips memory addresses, hashes normalized frames via SHA-256, and upserts into PostgreSQL issues.
4. **Detect & Correlate**: Spike detection engine identifies anomaly clusters and links recent releases and feature flag updates.
5. **Mitigate**: Operator applies a targeted kill switch. ReleaseGuard snapshots pre-mitigation state (e.g. `rollout: 25%`) and disables the flag immediately.
6. **Investigate**: AI Incident Copilot analyzes telemetry, produces candidate hypotheses (H1, H2), and answers operator queries with grounded database citations.
7. **Recover**: Operator clicks *"Revert Mitigation"*, restoring the exact pre-incident rollout percentage instantly.

---

## 5. Multi-Tenancy Model

ReleaseGuard enforces strict tenant isolation at every layer:
- **Hierarchical Scoping**: `Tenant` -> `Projects` -> `Issues` / `Releases` / `Flags` / `Incidents`.
- **Zero Client Trust**: Client-supplied `tenant_id` parameters in URL paths or headers are never trusted. Every request verifies authenticated JWT claims against server-side `Membership` tables.
- **Enumeration Defense**: Requests for resources outside the user's authorized tenant return `HTTP 404 Not Found` rather than `HTTP 403 Forbidden` to prevent resource probing.
- **RBAC Roles**:
  - `owner`: Full organizational control, billing, member invites, and project deletion. Protected by transactional Last-Owner safety.
  - `admin`: Operational management (feature flags, releases, incidents, mitigations).
  - `member`: Read-only telemetry inspection and comment posting.

---

## 6. Error Ingestion Pipeline

- **HTTP 202 Accepted**: Ingest endpoints decouple HTTP receipt from database persistence.
- **Payload Validation**: Strict Pydantic v2 schemas reject malformed JSON before queue admission.
- **Payload Guardrails**: Maximum payload size enforced (`413 Payload Too Large`), preventing memory saturation.
- **Non-Blocking SDK Transport**: Python SDK uses an asynchronous background worker thread with a bounded queue (`max_size=1000`) and oldest-drop backpressure policy.

---

## 7. Redis + Worker Architecture

- **Consumer Groups (`XREADGROUP`)**: Scalable horizontal consumer processing with persistent offsets.
- **Pending Entry List (`PEL`) Recovery**: Worker periodically inspects `XPENDING` to claim abandoned messages from crashed worker instances.
- **Dead-Letter Queue (`events:dlq`)**: Poison-pill messages that fail processing after 3 retries are diverted to `events:dlq` with failure metadata.
- **Stream Trimming**: Bounded Redis memory via approximate trimming (`MAXLEN ~ 100,000`).

---

## 8. Issue Fingerprinting & Deduplication

- **Frame Normalization**: Strips memory pointers (`0x7f...`), variable line numbers from minor refactors, and host-specific path prefixes (`/var/app/...` vs `C:\app\...`).
- **Cryptographic Fingerprint**: Normalized frames and exception types are concatenated and hashed via `SHA-256`.
- **Atomic Concurrency-Safe Upsert**: Uses PostgreSQL row-level locking (`SELECT ... FOR UPDATE`) and advisory locks to safely increment issue counts during concurrent ingestion spikes.
- **Regression Detection**: Re-opening an issue in `resolved` state automatically flips status to `unresolved` and increments the regression counter.

---

## 9. Feature Flags & Deterministic Rollout

- **Stateless Mathematical Distribution**: Evaluated via `CRC32(flag_key + ":" + user_id) % 100`.
- **Client Stability**: A user in a 10% canary cohort remains consistently in that cohort across devices and sessions without server database reads.
- **Sub-10ms Config Polling**: Config endpoint serves flag definitions with HTTP `ETag` and `If-None-Match` validation, responding with `304 Not Modified` in ~6ms.
- **Immutable Audit Logging**: Every status change, rollout shift, and description edit records an audit entry (`flag_audit_logs`).

---

## 10. Incident Management & Reversible Mitigation

- **Incident Lifecycle**: `open` -> `investigating` -> `monitoring` -> `mitigated` -> `resolved` -> `closed`.
- **Linked Scope**: Incidents correlate multiple linked error issues, deployments, and feature flags.
- **Atomic Pre-Mitigation Snapshots**: Applying a kill switch snapshots `previous_state: {enabled: true, rollout_percentage: 25}` into `IncidentMitigation`.
- **One-Click Reversion**: Restoring a mitigation automatically reapplies the exact historical rollout percentages without manual reconfiguration.

---

## 11. AI Incident Copilot

- **Dual-Model Resilient Architecture**: Primary model `gemini-3.8-flash` with 1 retry on transient capacity failures (`503`, `429`), followed by automated failover to `gemini-3.5-flash-lite`.
- **Strict Evidence Grounding**: Hypotheses (H1, H2) are verified against database records. Citations must match real project entities (`issue`, `release`, `feature_flag`, `mitigation`, `timeline`). Nonexistent or foreign citations are discarded into `uncertainties`.
- **Evidence vs Inference Separation**: High-contrast visual and conceptual separation between observed telemetry facts and AI deductive reasoning.
- **Hallucination Refusal**: Explicit refusal to invent missing metrics (CPU utilization, database connection pools, customer IDs, exact code lines, RPS).
- **Prompt-Injection Defense**: Untrusted error messages, stack traces, and chat inputs are enclosed in structured `DATA ENVELOPE` delimiters, remaining inert data.
- **Advisory-Only Safety**: Copilot has zero autonomous authority to modify production feature flags, execute shell/database commands, or resolve incidents.

---

## 12. Security Model

- **Authentication**: JWT tokens signed via `HS256` with expiration and user session verification.
- **Header-Based AI Auth**: External Gemini requests strictly pass API keys via `x-goog-api-key` headers; URL query parameters are forbidden.
- **Secret Scrubbing Filter**: Regex sanitization scrubs passwords, bearer tokens, and Google API keys from logs and outbound AI context envelopes.
- **Rate Limiting & Lockout**: Redis sliding-window limiter on login endpoints triggers account lockout after consecutive failures. Copilot requests enforce double-click deduplication (< 1.0s) and burst limits (30 req/min).

---

## 13. Deployment Architecture

- **Backend API & Worker**: Hosted on Render as containerized Web Service and Background Worker instances.
- **Database**: Managed PostgreSQL 17 with connection pooling and automated backups.
- **Queue / Cache**: Managed Redis 7 instance.
- **Frontend Dashboard**: Deployed as an optimized static SPA on Vercel with HTTPS edge caching.

---

## 14. Local Development Setup

### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL 17
- Redis 7

### Backend Setup
```bash
# 1. Clone repository
git clone https://github.com/your-org/releaseguard.git
cd releaseguard

# 2. Set up virtual environment
python -m venv .venv
.\.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# 3. Install dependencies
pip install -r backend/requirements.txt
pip install -e sdk/python

# 4. Configure environment
cp backend/.env.example backend/.env

# 5. Run migrations
cd backend
alembic upgrade head

# 6. Start API server & worker
uvicorn app.main:app --reload --port 8000
python -m app.worker
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## 15. Environment Variables

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Runtime environment (`development`, `test`, `production`) | `development` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@localhost:5432/releaseguard` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `JWT_SECRET` | Secret key for signing JWT tokens | *(secure random secret)* |
| `JWT_EXPIRY_MINUTES` | Token lifetime in minutes | `1440` (24 hours) |
| `GEMINI_API_KEY` | Google Gemini API key for Incident Copilot | *(optional; defaults to mock provider if empty)* |
| `COPILOT_PROVIDER` | AI provider implementation (`gemini`, `mock`) | `gemini` |
| `COPILOT_MODEL` | Primary AI model name | `gemini-3.8-flash` |
| `COPILOT_FALLBACK_MODEL` | Failover AI model name | `gemini-3.5-flash-lite` |
| `VITE_API_BASE_URL` | Frontend API backend target | `http://localhost:8000` |

---

## 16. Testing

ReleaseGuard maintains comprehensive test coverage:

```bash
# 1. Backend & SDK test suite (220 tests)
pytest -q backend sdk/python/tests

# 2. Frontend test suite (50 tests)
cd frontend
npm test

# 3. Frontend production build validation
npm run build

# 4. Database migration check
alembic check
```

---

## 17. Production Deployment

- **Production API URL**: `https://releaseguard-api-0jbc.onrender.com`
- **Production Dashboard**: `https://releaseguard-two.vercel.app`
- **Health Probes**:
  - `GET /health`: Liveness probe (`HTTP 200 OK`).
  - `GET /health/ready`: Readiness probe verifying PostgreSQL and Redis connections.

---

## 18. Example API Flow

### Ingest Error Event
```bash
curl -X POST https://releaseguard-api-0jbc.onrender.com/api/v1/projects/1/events \
  -H "Content-Type: application/json" \
  -H "X-ReleaseGuard-Key: rg_live_demo_checkout_service_key_99" \
  -d '{
    "exception_type": "PaymentGatewayTimeout",
    "message": "Stripe timeout after 3000ms",
    "stack_trace": "File \"/app/checkout.py\", line 142\n  raise PaymentGatewayTimeout()",
    "environment": "production",
    "release": "v2.4.1"
  }'
```
**Response (`HTTP 202 Accepted`)**:
```json
{
  "status": "queued",
  "event_id": "018f3a9b-4b3c-7192-802a-9e1284560123",
  "fingerprint": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

### Evaluate Feature Flag
```bash
curl -s "https://releaseguard-api-0jbc.onrender.com/api/v1/projects/1/config?environment=production" \
  -H "If-None-Match: \"a1b2c3d4\""
```
**Response (`HTTP 304 Not Modified` or `HTTP 200 OK`)**:
```json
{
  "environment": "production",
  "flags": {
    "new_checkout_flow": {
      "enabled": true,
      "rollout_percentage": 25
    }
  }
}
```

---

## 19. Limitations & Technical Debt

1. **Vite Bundle Splitting**: The main frontend bundle is ~887 kB. While fully functional, dynamic route-based imports (`React.lazy`) can further optimize initial chunk size in future milestones.
2. **Horizontal Redis Scaling**: Ingestion uses a single Redis stream. For ultra-high scale (> 100k events/sec), partitioned stream keys (`events:stream:{shard}`) can be implemented.
3. **Multi-Region Latency**: The primary PostgreSQL cluster is centralized; client edge evaluations currently rely on HTTP ETag caching rather than edge KV replication.
