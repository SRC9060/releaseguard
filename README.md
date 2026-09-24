# ReleaseGuard v0.1

ReleaseGuard is a developer reliability platform for:
- capturing application errors
- grouping duplicate failures into issues
- tracking releases
- later: deterministic feature flags, multi-tenancy, mitigation, and AI incident assistance

## Core Invariant

> **`(project_id, fingerprint)` must identify exactly one issue.**
> 
> 1,000 identical error events should become 1 issue with count=1,000.

## Why PostgreSQL is Used

In the initial development slice, SQLite was used as an ephemeral prototype. However, SQLite lacks true multi-writer concurrency and relies on database-level locks, leading to lock contention under simultaneous ingestion requests. 

PostgreSQL is now used as the primary persistence layer to provide:
- Robust multi-client concurrency with row- and tuple-level locking
- Strong transactional isolation
- Database-enforced correctness through native upsert (`ON CONFLICT`) operations
- Scalable connection pooling for high-throughput ingestion

## Concurrency & Race Condition Prevention

### Why Select-Then-Insert Was Unsafe

The previous implementation used a check-then-act pattern:
```
1. SELECT issue WHERE project_id = X AND fingerprint = Y
2. If issue is None:
       INSERT issue
   Else:
       UPDATE issue SET count = count + 1
```

Under concurrent traffic (e.g. 50–100 simultaneous requests for the same error):
1. Multiple worker processes or threads execute Step 1 concurrently before any transaction commits.
2. All concurrent threads observe that no issue exists (`issue is None`).
3. All threads attempt Step 2 (`INSERT`).
4. Without database constraints, duplicate issues would be created. With a `UNIQUE` constraint, all but the first thread crash with unique constraint violation errors (`IntegrityError`).

### How the New Implementation Guarantees Correctness

The ingestion pipeline now uses PostgreSQL's native atomic upsert statement:

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

## Configuration & Run

### 1. Configuration

Copy the example environment configuration:
```bash
cp .env.example .env
```

Set your PostgreSQL connection string in `.env`:
```env
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/releaseguard
```

### 2. Install & Run

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:
- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/health

### 3. Run Tests

Run the test suite (including the 100-request concurrency test):
```bash
pytest -v
```
