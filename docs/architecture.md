# ReleaseGuard Architecture Specification (v1.0.0)

## 1. System Topology Overview

ReleaseGuard is a high-throughput, concurrency-safe release monitoring, error tracking, and automated mitigation platform designed for modern multi-tenant environments.

```
+-----------------------------------------------------------------------------+
|                                CLIENT TIER                                  |
|                                                                             |
|   +-----------------------+                    +------------------------+   |
|   |   React Dashboard     |                    |   Host Application     |   |
|   |   (Vite SPA / Vercel) |                    |   (ReleaseGuard SDK)   |   |
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
|  * Copilot Rate Limiting & Dedup     * Secret Scrubbing Middleware          |
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
|  * Persisted Copilot records  |            |  * Copilot Request Limiter     |
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

## 2. Ingestion & Incident Investigation Pipeline

```
External Application
        ↓  (Exceptions / Crashes)
ReleaseGuard Python SDK
        ↓  (POST /api/v1/projects/{id}/events/bulk)
ReleaseGuard Ingestion API (HTTP 202 Accepted)
        ↓  (XADD events:stream)
Redis Streams Buffer
        ↓  (XREADGROUP)
Background Ingestion Worker (worker.py)
        ↓  (Normalize stack traces & compute SHA-256 fingerprint)
Issue Deduplication & Event Persistence (PostgreSQL)
        ↓  (Spike Detection & Correlation Service)
Incident Creation & Issue Association
        ↓  (Advisory Kill-Switch Recommendation)
Controlled Reversible Mitigation (Human-in-the-Loop)
        ↓  (Incident Context Aggregation & Secret Scrubbing)
AI Incident Copilot (Gemini Primary / Fallback)
        ↓  (Grounded Analysis & Conversational Investigation)
Operator Dashboard (Evidence Badges, Uncertainties, Reversible Rollback)
```

---

## 3. Core Architectural Decisions & Rationale

### 3.1 Why Redis Streams?
- **Decoupled Telemetry Ingestion**: When production applications crash, they burst telemetry simultaneously. Direct database writes during an incident cause connection pool starvation and database CPU saturation.
- **Microsecond Ingestion Latency**: The API acknowledges events with `HTTP 202 Accepted` in ~23ms by appending to Redis via `XADD`.
- **Consumer Group Semantics**: Redis Streams provide built-in consumer group coordination (`XREADGROUP`), persistent offsets, and automatic Pending Entries List (`PEL`) tracking without requiring heavyweight message broker infrastructure (like Apache Kafka).
- **Stream Trimming**: Bounded memory footprint via approximate stream trimming (`MAXLEN ~ 100,000`).

### 3.2 Why a Background Worker Process?
- **CPU-Intensive Normalization**: Parsing multi-frame stack traces, extracting absolute paths, scrubbing memory addresses, and computing cryptographic SHA-256 hashes consumes CPU cycles that should not block asynchronous HTTP request loops.
- **Transactional Batch Upserts**: The worker batches up to 50 events per tick, deduplicating them into single transactional database operations with row-level advisory locking.
- **Crash Resilience**: If a worker node crashes mid-batch, the unacknowledged messages remain in the Redis PEL and are reclaimed by peer workers after the visibility timeout.

### 3.3 Why Stack Trace Fingerprinting?
- **Root-Cause Deduplication**: Without fingerprinting, 100,000 instances of the same bug create 100,000 database issues, blinding on-call engineers.
- **Deterministic Frame Normalization**: File paths (e.g. `/usr/src/app/checkout.py` vs `C:\app\checkout.py`), memory pointers (`0x7f8a1c02e8`), and transient line shifts are normalized before hashing.
- **Regression Detection**: When an issue marked `resolved` reappears with the same fingerprint, ReleaseGuard atomically transitions it back to `unresolved` and increments the regression counter.

### 3.4 Why Idempotent Event IDs?
- **Network Retries & Duplicates**: Distributed networks inevitably produce duplicate HTTP dispatches from retry policies or SDK buffer flushes.
- **Zero Double-Counting**: Every event carries a client-generated UUID4 `event_id`. The database schema enforces a unique constraint on `(project_id, event_id)`.
- **Clean Acknowledgment**: When the worker encounters a duplicate `IntegrityError`, it rolls back the transaction and immediately calls `XACK` on Redis to discard the redundant stream entry without failing the batch.

### 3.5 Why Strict Tenant Scoping?
- **Multi-Tenant Security Invariant**: Enterprise SaaS requires absolute data isolation between competing organizations.
- **Zero Client Trust**: Client-supplied `tenant_id` parameters in URL paths or headers are never trusted. Every request verifies authenticated JWT claims against server-side `Membership` tables.
- **Cross-Tenant Sanitization**: Attempting to query or modify resources belonging to another tenant returns `HTTP 404 Not Found` (rather than 403) to prevent resource existence enumeration.

### 3.6 Why Deterministic Feature Flag Evaluation?
- **Consistent User Experience**: A user assigned to a 10% canary rollout must experience the same variant across repeated page loads, different browser sessions, and mobile devices without storing server-side state.
- **Mathematical Uniformity**: Evaluated via `CRC32(flag_key + ":" + user_id) % 100`. Rollout distribution is uniform, reproducible, and stateless.
- **Sub-Millisecond Evaluation**: Flag configurations are cached client-side with ETag/304 validation, responding in ~6ms.

### 3.7 Why Reversible Mitigation?
- **Blast Radius Containment**: Disabling a newly deployed feature flag is the fastest way to stop an error spike without triggering a high-risk production code rollback.
- **Zero Configuration Loss**: When a kill switch is applied, ReleaseGuard atomically snapshots the flag's pre-mitigation state (e.g., `enabled: true, rollout_percentage: 25%`) into `IncidentMitigation.previous_state`.
- **One-Click Reversion**: Once the underlying bug is resolved, operators click *"Revert Mitigation"*, which restores the exact pre-incident rollout percentages without manual re-configuration.

### 3.8 Why AI Incident Copilot is Advisory-Only?
- **Strict Human-in-the-Loop Safety**: AI models must never possess direct authority to alter production feature flags, execute database commands, revert releases, or resolve incidents autonomously.
- **Hallucination Containment**: All AI hypotheses (H1, H2) are grounded strictly in database telemetry facts. The model is forced to cite verifiable entity IDs (`issue`, `release`, `feature_flag`, `mitigation`, `timeline`). Any unverified citation is stripped and logged under `uncertainties`.
- **Data Boundary**: AI prompts treat all untrusted incident telemetry, error messages, and chat history strictly as inert data envelopes (`DATA ENVELOPE`), preventing adversarial prompt injection from bypassing authorization.

---

## 4. AI Copilot Multi-Tier Provider Architecture

```
                      +-----------------------------+
                      |   Incident Copilot Request  |
                      +-----------------------------+
                                     |
                         (Double-click dedup & 429)
                                     v
                      +-----------------------------+
                      |   Copilot Request Limiter   |
                      +-----------------------------+
                                     |
                          (Deterministic Hash)
                                     v
                      +-----------------------------+
                      |    Context Cache Check      |
                      +-----------------------------+
                               /           \
                 (Cache Hit)  /             \  (Cache Miss / Refresh)
                             v               v
                +-----------------+   +-----------------------------+
                | Persisted Store |   |   Context Builder & Secret  |
                +-----------------+   |     Scrubbing Pipeline      |
                                      +-----------------------------+
                                                     |
                                      +--------------v--------------+
                                      |   Primary Model Evaluation  |
                                      |     (gemini-3.8-flash)      |
                                      +-----------------------------+
                                             /               \
                              (HTTP 200)    /                 \  (503 / 429 / Timeout)
                                           v                   v
                        +----------------------+    +----------------------+
                        |   Schema Validation  |    |  Exponential Backoff |
                        +----------------------+    |       (1 Retry)      |
                                                            +----------------------+
                                                                       |
                                                               (Still failing)
                                                                       v
                                                            +----------------------+
                                                            |   Fallback Model     |
                                                            | (gemini-3.5-flash)   |
                                                            +----------------------+
                                                                       |
                                                            +----------v-----------+
                                                            |  Evidence Integrity  |
                                                            |     Verification     |
                                                            +----------------------+
                                                                       |
                                                            +----------v-----------+
                                                            |   Persist Analysis   |
                                                            +----------------------+
```

---

## 5. Security & Observability Architecture

- **Secret Scrubbing Middleware**: Regex pattern matching sanitizes Google API keys (`AIzaSy...`), bearer tokens, passwords, and private tokens from logs and outgoing AI context envelopes.
- **Header Authentication**: External AI provider requests strictly pass authentication via `x-goog-api-key` request headers; query string parameters are forbidden to prevent proxy URL leakage.
- **Safe Structured Observability**: AI requests log high-cardinality execution metrics (`context_build_ms`, `provider_request_ms`, `total_request_ms`, `model_used`, `cache_hit`, `fallback_used`) while suppressing raw prompts, user messages, and secret values.
- **Production Liveness Probes**: Dual-probe architecture:
  - `/health`: Lightweight ASGI liveness check for container orchestrators.
  - `/health/ready`: Deep dependency check verifying live PostgreSQL transactions and Redis ping.
