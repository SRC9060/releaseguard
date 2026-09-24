# ReleaseGuard v0.1

ReleaseGuard is a developer reliability platform for:
- capturing application errors
- grouping duplicate failures into issues
- tracking releases
- high-throughput asynchronous ingestion pipeline
- later: deterministic feature flags, multi-tenancy, mitigation, and AI incident assistance

---

## Core Invariant

> **`(project_id, fingerprint)` must identify exactly one issue.**
> 
> 1,000 identical error events should become 1 issue with `count=1,000`.

---

## Phase 5 Architecture — Asynchronous Ingestion Pipeline

```
Application
    ↓ (non-blocking)
ReleaseGuard Python SDK (in-memory batching)
    ↓ HTTP POST /api/v1/projects/{project_id}/events/bulk
Bulk Ingestion API
    ↓ Enqueue events into Redis Stream (O(1))
    ↓ Return HTTP 202 Accepted
Redis Queue (releaseguard:events:stream)
    ↓ Dequeue batch via Consumer Group (releaseguard:workers)
Background Ingestion Worker
    ↓ Calculate fingerprint (SHA-256 normalized frames)
    ↓ PostgreSQL Atomic Upsert & ErrorEvent persistence
    ↓ Commit atomically in single transaction
    ↓ Acknowledge message (XACK)
PostgreSQL Database
```

### Why the Bulk API Returns HTTP 202 Accepted
In high-throughput distributed systems, an application should never be subjected to database latency, lock contention, or transient database outages during error ingestion. 

When the bulk API receives a batch of events:
1. It validates the project ID and schema structure.
2. It pushes the events into a durable **Redis Stream** (`releaseguard:events:stream`).
3. It immediately returns **HTTP 202 Accepted** with a `batch_id` and `accepted_count`.

The API request path does **not** write to PostgreSQL, calculate fingerprints, or acquire database locks. This decouples client response latency (~15–30 ms) from database processing throughput.

### Why Grouping is Performed Asynchronously
Issue grouping requires:
- Normalizing stack frames and stripping UUIDs, memory addresses, and line numbers
- Generating cryptographic fingerprints
- Executing an atomic database upsert with row locks (`ON CONFLICT (project_id, fingerprint) DO UPDATE`)
- Inserting raw `ErrorEvent` audit rows

Executing these steps synchronously inside the HTTP handler creates lock serialization bottlenecks under bursts (e.g. 5,000 concurrent crashes). By deferring grouping to dedicated background workers:
- Ingestion remains responsive even during database spikes or vacuum operations.
- Multiple worker processes can consume from Redis concurrently using Consumer Groups without head-of-line blocking.
- Worker throughput is optimized through batch database transactions.

### End-to-End Event Idempotency
Redis Streams provide at-least-once delivery. PostgreSQL `event_id` idempotency prevents a redelivered message from being counted twice.

If the worker commits the PostgreSQL transaction and crashes before `XACK`, Redis redelivers the same message:
1. **Stable Identifier**: Every SDK event generates a stable, unique `event_id` (UUID) upon creation. Retrying transport attempts, in-memory batching, and flush cycles preserve this exact ID.
2. **Atomic Conflict Check**: The worker executes the issue upsert, followed by an idempotent event insertion:
   ```sql
   INSERT INTO error_events (event_id, project_id, issue_id, ...)
   VALUES (:event_id, :project_id, :issue_id, ...)
   ON CONFLICT (event_id) DO NOTHING
   RETURNING id;
   ```
3. **Rollback on Duplicate**: If `RETURNING id` produces no row, the worker recognizes that this exact `event_id` was already committed. It rolls back the transaction (`db.rollback()`), preventing the `Issue.count` from incrementing twice, and acknowledges (`XACK`) the duplicate Redis message.
4. **Atomic Commit on Fresh**: If `RETURNING id` yields a row, both the issue upsert and error event insert commit atomically before the Redis message is acknowledged.

### Why Fakeredis is Test-Only
In normal application execution (production and local deployment), `REDIS_URL` must point to an active, real Redis instance. If Redis is unavailable, startup or ingestion fails immediately and explicitly. The server will **never** return `HTTP 202 Accepted` while silently storing events in a non-persistent in-memory fake queue.

`fakeredis` is strictly test-only: it is explicitly injected into test suites via FastAPI dependency injection (`app.dependency_overrides[get_queue]`), allowing the test suite to remain completely self-contained without requiring a manually running Redis daemon.

---

## Concurrency & Race Condition Prevention

The ingestion pipeline uses PostgreSQL's native atomic upsert statement:

```sql
INSERT INTO issues (project_id, fingerprint, title, count, first_seen, last_seen)
VALUES (:project_id, :fingerprint, :title, 1, :now, :now)
ON CONFLICT (project_id, fingerprint)
DO UPDATE SET
    count = issues.count + 1,
    last_seen = :now
RETURNING issues.id, issues.count;
```

- **Database-Enforced Atomicity**: PostgreSQL checks the `uq_project_fingerprint` unique constraint at the index level. Competing concurrent insertions are serialized at the row lock.
- **Conflict Handling**: Exactly one transaction inserts the row (returning `count = 1`), while all concurrent and subsequent transactions take the `DO UPDATE` branch, safely incrementing `count` and updating `last_seen`.
- **Zero Race Window**: The entire check, create-or-increment, and ID retrieval occurs in a single atomic database statement, guaranteeing that 100 concurrent requests result in exactly 1 issue row with `count = 100`.

---

## Configuration & Run

### 1. Configuration

Copy the example environment configuration:
```bash
cp .env.example .env
```

Configure your PostgreSQL and Redis connection strings in `.env`:
```env
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/releaseguard
REDIS_URL=redis://127.0.0.1:6379/0
```

*(Note: If a live Redis server is not present locally on Windows, the application and test suites seamlessly use in-memory `fakeredis`.)*

### 2. Install & Run

```bash
# Setup Python virtualenv
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install redis fakeredis

# Start FastAPI API Server
uvicorn app.main:app --reload

# Start Background Ingestion Worker (in a separate terminal)
python -m app.worker
```

Open:
- API Documentation: http://127.0.0.1:8000/docs
- Health Check: http://127.0.0.1:8000/health

### 3. Run Tests

Run the complete test suite (26 passing tests covering backend, PostgreSQL concurrency, pipeline, worker retries, and SDK):
```bash
pytest -v
```

### 4. Run Benchmarks

Run the pipeline latency and worker throughput benchmark:
```bash
python benchmarks/benchmark_pipeline.py
```
