# ReleaseGuard Architecture

## 1. System Topology Overview

ReleaseGuard is a high-throughput, concurrency-safe release monitoring, error tracking, and automated mitigation platform designed for modern multi-tenant environments.

```
+-----------------------------------------------------------------------------+
|                                CLIENT TIER                                  |
|                                                                             |
|   +-----------------------+                    +------------------------+   |
|   |   React Dashboard     |                    |   Python Client App    |   |
|   |      (Vite SPA)       |                    |     (ReleaseGuard SDK) |   |
|   +-----------+-----------+                    +-----------+------------+   |
+---------------|--------------------------------------------|----------------+
                | HTTP / JWT                                 | HTTP / API Key
                v                                            v
+-----------------------------------------------------------------------------+
|                                BACKEND API                                  |
|                                                                             |
|      FastAPI ASGI Engine (Uvicorn) - Stateless, Horizontally Scalable       |
|                                                                             |
|  * Auth & RBAC (JWT HS256)           * API Key Validation                   |
|  * Multi-Tenant Isolation Scoping    * Ingestion Handler (HTTP 202)         |
|  * Config Evaluation (ETag Caching)  * Health & Readiness Probes            |
+---------------+--------------------------------------------+----------------+
                |                                            |
         SQL    |                                            | XADD Stream
                v                                            v
+-------------------------------+            +--------------------------------+
|       PERSISTENT STORE        |            |         STREAM BUFFER          |
|                               |            |                                |
|         PostgreSQL 17         |            |            Redis 7             |
|                               |            |                                |
|  * ACID Relational Schema     |            |  * Redis Streams               |
|  * Row-level concurrency lock |            |    ('events:stream')           |
|  * Unique idempotency indexes |            |  * Consumer Group              |
|  * Alembic-managed migrations |            |    ('events:group')            |
+---------------+---------------+            |  * Auth Rate Limiter Keys      |
                ^                            +---------------+----------------+
                |                                            |
                | SQL (Transactional upserts)                | XREADGROUP / XACK
                |                                            v
+---------------+-------------------------------------------------------------+
|                              ASYNC WORKER TIER                              |
|                                                                             |
|                      IngestionWorker (Python Process)                       |
|                                                                             |
|  * Multi-consumer Group Worker       * Stale Pending Entry Recovery (PEL)   |
|  * Batch Processing (XREADGROUP)     * Dead-Letter Queue (DLQ Routing)      |
|  * Idempotent Event Deduplication    * Graceful Signal Handling (SIGINT)    |
+-----------------------------------------------------------------------------+
```

---

## 2. Core Components

### 2.1 Frontend Dashboard
- **Technology**: React 18, Vite, TailwindCSS, Lucide Icons.
- **Role**: Provides operators and engineers with real-time issue exploration, event stack traces, release monitoring, deterministic rollout controls, incident command dashboards, and audit histories.
- **Production Delivery**: Pre-compiled static assets served by an optimized Nginx container with SPA routing (`try_files $uri $uri/ /index.html`), gzip compression, and HTTP security headers (`X-Frame-Options`, `X-Content-Type-Options`).
- **Configuration**: Uses dynamic backend configuration via `VITE_API_BASE_URL`.

### 2.2 Backend API
- **Technology**: FastAPI, Python 3.12, Uvicorn ASGI server, Pydantic v2, SQLAlchemy 2.0.
- **Role**: Exposes RESTful endpoints for dashboard queries, administrative mutations, and high-throughput event ingestion.
- **Stateless Execution**: The API process is completely stateless and can scale horizontally behind a load balancer. It relies on Redis for distributed rate-limiting and streams, and PostgreSQL for relational state.
- **Observability**: Exposes `/health` (liveness) and `/health/ready` (readiness verifying live PostgreSQL and Redis connections).

### 2.3 Redis Stream Buffer
- **Technology**: Redis 7.
- **Role**: Acts as the high-speed shock absorber for incoming telemetry.
- **Stream Architecture**:
  - Main Stream: `events:stream`
  - Consumer Group: `events:group`
  - Dead Letter Queue: `events:dlq`
- **Stream Retention**: Stream size is bounded using approximate trimming (`XADD MAXLEN ~ 100,000`) to prevent memory exhaustion during sustained high-throughput bursts.

### 2.4 Asynchronous Ingestion Worker
- **Technology**: Standalone Python process (`python -m app.worker`).
- **Role**: Consumes raw error payloads from Redis Streams, parses exception stack traces, derives deterministic fingerprints, and persists events and issues into PostgreSQL.
- **Reliability Features**:
  - **Stale PEL Recovery**: Polls `XPENDING` to claim abandoned messages from crashed worker instances.
  - **Dead Letter Queue (DLQ)**: Retries failed messages up to `MAX_RETRIES` (default 3); messages exceeding this threshold are routed to `events:dlq` with failure metadata.
  - **Idempotent Acknowledgment**: When encountering a duplicate `event_id`, the worker rolls back the transactional database unit-of-work and issues `XACK` to prevent pipeline stalls.

### 2.5 PostgreSQL Persistent Store
- **Technology**: PostgreSQL 17.
- **Role**: Source of truth for all structured relational data:
  - Multi-tenant workspaces (`tenants`, `users`, `memberships`)
  - Project configurations (`projects`, `environments`)
  - Telemetry (`issues`, `error_events`, `metrics`)
  - Release controls (`releases`, `feature_flags`, `rollouts`, `flag_settings`)
  - Incident management (`incidents`, `incident_events`, `incident_mitigations`)
  - Governance (`flag_audit_logs`)

---

## 3. Telemetry Ingestion Pipeline

```
1. Client App (SDK)
   |
   | POST /api/v1/projects/{project_id}/events
   | (Includes Header: X-ReleaseGuard-Key)
   v
2. FastAPI Ingestion Handler
   |
   +--> Validate API Key against database / cache
   +--> Assign UUID4 event_id if not provided
   +--> XADD to 'events:stream'
   v
3. Returns HTTP 202 Accepted {"status": "queued", "event_id": "..."}
   |
   v (Asynchronous Boundary)
4. Redis Stream Worker Process
   |
   +--> XREADGROUP / XCLAIM from 'events:stream'
   +--> Parse stack trace & derive SHA-256 fingerprint
   +--> Begin PostgreSQL Transaction:
   |      - Upsert Issue record (atomic count increment, last_seen update)
   |      - Insert ErrorEvent record (enforcing UNIQUE event_id)
   +--> Commit Transaction
   +--> XACK message to Redis
```

---

## 4. Feature Flag & Deterministic Rollout Engine

ReleaseGuard provides deterministic, zero-latency feature flag evaluations:

1. **Deterministic Hashing**:
   $$\text{Bucket} = \left( \text{CRC32}(\text{flag\_key} + \text{":"} + \text{user\_id}) \pmod{100} \right)$$
   For any given combination of user ID and flag key, the assigned bucket (0–99) is mathematically invariant.

2. **Rule Hierarchy**:
   - **Global Project Kill**: If the flag is toggled `OFF`, evaluation immediately returns `false`.
   - **Environment Specific Override**: If an environment-specific state exists (`flag_settings`), it takes precedence over the global flag state.
   - **Targeting Rules**: Specific user IDs or attributes explicitly whitelisted are evaluated first.
   - **Percentage Rollout**: If `bucket < rollout_percentage`, the flag evaluates to `true`; otherwise `false`.

3. **High-Efficiency Caching**:
   - The `/api/v1/projects/{project_id}/config` endpoint computes an MD5/SHA ETag across all active flags and rollouts.
   - Evaluators sending `If-None-Match` receive HTTP `304 Not Modified` with zero database or payload serialization overhead.

---

## 5. Incident Response & Controlled Mitigation Pipeline

```
[ Error Telemetry ] ---> [ Statistical Spike Detector ]
                                  |
                                  v (Z-Score Threshold Exceeded)
                        [ Create Incident (Status: Open) ]
                                  |
                        [ Automated Root-Cause Analysis ]
                                  |
             +--------------------+--------------------+
             |                                         |
    [ Release Correlated ]                    [ Feature Flag Correlated ]
             |                                         |
             v                                         v
    [ Generate Mitigation ]                  [ Generate Mitigation ]
    (Rollback to previous release)           (Kill feature flag to 0%)
             |                                         |
             +--------------------+--------------------+
                                  |
                                  v
                    [ Incident Command Dashboard ]
                                  |
                    [ Human-In-The-Loop Approval ]
                    (Explicit Operator Action via RBAC)
                                  |
                                  v
                    [ Atomic Mitigation Execution ]
                    (Database Transaction + Audit Log)
                                  |
                                  v
                    [ Incident Status: Mitigated / Resolved ]
```

---

## 6. Concurrency & Data Integrity Guarantees

1. **Idempotency Guarantee**:
   Every event ingested into ReleaseGuard carries a unique `event_id`. An explicit unique constraint on `error_events.event_id` guarantees that network redeliveries or worker retries cannot corrupt issue occurrence counts.

2. **Issue Aggregation Concurrency**:
   Concurrent error bursts targeting the same issue are handled via PostgreSQL row-level locks or atomic upsert statements (`INSERT ... ON CONFLICT (project_id, fingerprint) DO UPDATE`), preventing duplicate issue creation races.

3. **Multi-Tenant Row Scoping**:
   Every database query filters strictly by `tenant_id` and verified user memberships. The backend never accepts client-provided tenant identifiers without validating cryptographic JWT session context.

4. **Last-Owner Invariant**:
   Demoting or deleting tenant owners uses transactional row-locking (`SELECT ... FOR UPDATE`) to verify the remaining owner count exceeds 1, guaranteeing no tenant can ever become orphaned.
