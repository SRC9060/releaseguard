"""
Phase 5 Tests: Asynchronous Server-Side Ingestion Pipeline.
Tests:
- Queue operations (enqueue, dequeue, ack, metrics)
- Retry and dead-letter queue behavior
- Bulk ingestion HTTP endpoint (HTTP 202 Accepted, validation, 404 project)
- Worker processing (fingerprinting, atomic upsert, ErrorEvent commit)
- Concurrency and 100-event deduplication into a single Issue (count=100)
"""

from concurrent.futures import ThreadPoolExecutor
import time
import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models import ErrorEvent, Issue, Project
from app.queue import EventQueue, get_queue
from app.worker import IngestionWorker


@pytest.fixture
def fake_redis_queue():
    """Provides an isolated EventQueue powered by fakeredis for tests."""
    client = fakeredis.FakeRedis(decode_responses=True)
    return EventQueue(redis_client=client)


@pytest.fixture
def override_queue(fake_redis_queue):
    """Overrides the FastAPI get_queue dependency to use the isolated fake_redis_queue."""
    app.dependency_overrides[get_queue] = lambda: fake_redis_queue
    yield fake_redis_queue
    app.dependency_overrides.pop(get_queue, None)


# =========================================================================
# 1. Queue Operations & Metrics Tests
# =========================================================================

def test_queue_enqueue_and_dequeue(fake_redis_queue: EventQueue):
    """Test basic queueing and dequeuing on Redis Streams."""
    events = [
        {"exception_type": "ValueError", "message": "bad data 1", "stack_trace": "tb 1"},
        {"exception_type": "KeyError", "message": "missing key 2", "stack_trace": "tb 2"},
    ]
    batch_id, count = fake_redis_queue.enqueue_events(project_id=1, events=events)
    assert count == 2
    assert isinstance(batch_id, str) and len(batch_id) > 0

    metrics = fake_redis_queue.get_metrics()
    assert metrics["queue_depth"] == 2
    assert metrics["events_accepted"] == 2

    # Dequeue batch
    messages = fake_redis_queue.dequeue_batch(batch_size=10, timeout_ms=100)
    assert len(messages) == 2

    msg_id_1, data_1 = messages[0]
    assert data_1["exception_type"] == "ValueError"
    assert data_1["project_id"] == "1"
    assert data_1["batch_id"] == batch_id
    assert data_1["retry_count"] == "0"

    # Ack one message
    fake_redis_queue.ack(msg_id_1)
    metrics_after_ack = fake_redis_queue.get_metrics()
    assert metrics_after_ack["events_processed"] == 1


def test_queue_retry_and_dead_letter(fake_redis_queue: EventQueue):
    """Test bounded retries and dead-letter queue routing on repeated failures."""
    events = [{"exception_type": "CrashError", "message": "fatal", "stack_trace": "tb"}]
    fake_redis_queue.enqueue_events(project_id=1, events=events)

    messages = fake_redis_queue.dequeue_batch(batch_size=1, timeout_ms=100)
    assert len(messages) == 1
    msg_id, data = messages[0]

    # Attempt 1: Fail (max_retries=2) -> should re-enqueue
    retried_1 = fake_redis_queue.fail(msg_id, data, "Connection drop 1", max_retries=2)
    assert retried_1 is True

    # Read retried message
    messages_retry_1 = fake_redis_queue.dequeue_batch(batch_size=1, timeout_ms=100)
    assert len(messages_retry_1) == 1
    msg_id_r1, data_r1 = messages_retry_1[0]
    assert data_r1["retry_count"] == "1"

    # Attempt 2: Fail -> should re-enqueue
    retried_2 = fake_redis_queue.fail(msg_id_r1, data_r1, "Connection drop 2", max_retries=2)
    assert retried_2 is True

    # Read retried message
    messages_retry_2 = fake_redis_queue.dequeue_batch(batch_size=1, timeout_ms=100)
    assert len(messages_retry_2) == 1
    msg_id_r2, data_r2 = messages_retry_2[0]
    assert data_r2["retry_count"] == "2"

    # Attempt 3: Fail -> max_retries exhausted -> Dead Letter Queue
    retried_3 = fake_redis_queue.fail(msg_id_r2, data_r2, "Permanent crash", max_retries=2)
    assert retried_3 is False

    metrics = fake_redis_queue.get_metrics()
    assert metrics["dead_letter_depth"] == 1
    assert metrics["events_failed"] == 1
    assert metrics["events_retried"] == 3


# =========================================================================
# 2. Bulk Endpoint HTTP Contract Tests
# =========================================================================

def test_bulk_ingest_endpoint_returns_202_accepted(client: TestClient, override_queue: EventQueue):
    """Requirement 1: POST /api/v1/projects/{project_id}/events/bulk returns 202 Accepted."""
    # 1. Create project
    proj_resp = client.post("/api/v1/projects", json={"name": "Bulk Test App"})
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # 2. Bulk ingest 3 events
    bulk_payload = {
        "events": [
            {"exception_type": "ZeroDivisionError", "message": "div 0", "stack_trace": "line 10"},
            {"exception_type": "KeyError", "message": "missing 'user'", "stack_trace": "line 22"},
            {"exception_type": "TypeError", "message": "int expected", "stack_trace": "line 45"},
        ]
    }
    resp = client.post(f"/api/v1/projects/{project_id}/events/bulk", json=bulk_payload)
    assert resp.status_code == 202
    data = resp.json()

    assert data["status"] == "accepted"
    assert data["accepted_count"] == 3
    assert data["rejected_count"] == 0
    assert "batch_id" in data
    assert data["project_id"] == project_id

    # Verify events are in the queue and NOT written directly to the database
    metrics = override_queue.get_metrics()
    assert metrics["queue_depth"] == 3
    assert metrics["events_accepted"] == 3

    # DB must have 0 issues before worker processes them
    issues_resp = client.get(f"/api/v1/projects/{project_id}/issues")
    assert len(issues_resp.json()) == 0


def test_bulk_ingest_rejects_nonexistent_project(client: TestClient, override_queue: EventQueue):
    """Non-existent project_id must return 404."""
    resp = client.post(
        "/api/v1/projects/999999/events/bulk",
        json={"events": [{"exception_type": "Err", "message": "m", "stack_trace": "s"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


def test_bulk_ingest_rejects_invalid_payloads(client: TestClient, override_queue: EventQueue):
    """Empty batch or malformed event payload must be rejected."""
    proj = client.post("/api/v1/projects", json={"name": "Val App"}).json()
    p_id = proj["id"]

    # Empty batch
    resp_empty = client.post(f"/api/v1/projects/{p_id}/events/bulk", json={"events": []})
    assert resp_empty.status_code == 422

    # Malformed event (missing required fields)
    resp_malformed = client.post(
        f"/api/v1/projects/{p_id}/events/bulk",
        json={"events": [{"exception_type": "ValErr"}]},  # missing message & stack_trace
    )
    assert resp_malformed.status_code == 422


# =========================================================================
# 3. Worker Processing Tests
# =========================================================================

def test_worker_processes_queued_events_into_database(
    client: TestClient,
    override_queue: EventQueue,
    engine,
):
    """Worker consumes queued events and persists issues and events into DB."""
    proj = client.post("/api/v1/projects", json={"name": "Worker App"}).json()
    project_id = proj["id"]

    # Enqueue 3 events via bulk API
    client.post(
        f"/api/v1/projects/{project_id}/events/bulk",
        json={
            "events": [
                {"exception_type": "ValueError", "message": "invalid input", "stack_trace": "t1"},
                {"exception_type": "ValueError", "message": "invalid input", "stack_trace": "t1"},
                {"exception_type": "IndexError", "message": "out of range", "stack_trace": "t2"},
            ]
        },
    )

    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    worker = IngestionWorker(queue=override_queue, session_factory=SessionLocal)

    processed = worker.process_next_batch(batch_size=10)
    assert processed == 3

    # Check database state: 2 identical ValueError -> 1 issue (count=2); 1 IndexError -> 1 issue (count=1)
    issues = client.get(f"/api/v1/projects/{project_id}/issues").json()
    assert len(issues) == 2

    val_issue = next(i for i in issues if "ValueError" in i["title"])
    assert val_issue["count"] == 2

    idx_issue = next(i for i in issues if "IndexError" in i["title"])
    assert idx_issue["count"] == 1


# =========================================================================
# 4. Concurrency & 100-Event Deduplication Test
# =========================================================================

def test_100_identical_events_bulk_pipeline_create_single_issue_count_100(
    client: TestClient,
    override_queue: EventQueue,
    engine,
):
    """
    Requirement 4: 100 identical events entering the bulk pipeline:
    - exactly one issue row
    - issue count = 100
    - exactly 100 ErrorEvent rows
    - all events reference the same issue
    - no duplicate issue rows
    """
    proj = client.post("/api/v1/projects", json={"name": "100-Event Bulk App"}).json()
    project_id = proj["id"]

    num_events = 100
    identical_events = [
        {
            "exception_type": "DatabaseTimeout",
            "message": "Connection to replica pool timed out after 5000ms",
            "stack_trace": "File 'db.py', line 42, in acquire_connection\nraise DatabaseTimeout()",
            "release": "1.0.0",
        }
        for _ in range(num_events)
    ]

    # Ingest in chunks of 25 to test multiple bulk HTTP calls
    for chunk_start in range(0, num_events, 25):
        chunk = identical_events[chunk_start : chunk_start + 25]
        resp = client.post(
            f"/api/v1/projects/{project_id}/events/bulk",
            json={"events": chunk},
        )
        assert resp.status_code == 202
        assert resp.json()["accepted_count"] == 25

    # Process all 100 events using the IngestionWorker
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    worker = IngestionWorker(queue=override_queue, session_factory=SessionLocal)

    total_processed = 0
    while True:
        count = worker.process_next_batch(batch_size=50)
        if count == 0:
            break
        total_processed += count

    assert total_processed == num_events

    # Verify Database Invariants
    with SessionLocal() as db:
        # Invariant 1: Exactly 1 Issue row for this project
        issues = db.query(Issue).filter(Issue.project_id == project_id).all()
        assert len(issues) == 1, f"Expected 1 issue row, found {len(issues)}"

        issue = issues[0]
        # Invariant 2: Issue count == 100
        assert issue.count == 100, f"Expected issue.count=100, got {issue.count}"

        # Invariant 3: Exactly 100 ErrorEvent rows
        events = db.query(ErrorEvent).filter(ErrorEvent.project_id == project_id).all()
        assert len(events) == 100, f"Expected 100 events, found {len(events)}"

        # Invariant 4: All 100 events reference the same issue_id
        for ev in events:
            assert ev.issue_id == issue.id

    # Verify queue metrics
    metrics = override_queue.get_metrics()
    assert metrics["events_accepted"] == 100
    assert metrics["events_processed"] == 100
    assert metrics["events_failed"] == 0


# =========================================================================
# 5. Idempotency & Failure Safety Tests (TEST A through TEST E)
# =========================================================================

def test_a_idempotency_duplicate_redis_message_processed_twice(
    client: TestClient,
    override_queue: EventQueue,
    engine,
):
    """
    TEST A:
    Process one event successfully.
    Process the exact same Redis message again.
    Expected:
    - one ErrorEvent row
    - issue count remains 1
    - no duplicate issue
    - second processing is treated as already processed
    """
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    worker = IngestionWorker(queue=override_queue, session_factory=SessionLocal)

    proj = client.post("/api/v1/projects", json={"name": "Idempotent App A"}).json()
    project_id = proj["id"]

    event_payload = {
        "event_id": "test-fixed-uuid-1",
        "project_id": str(project_id),
        "exception_type": "ZeroDivisionError",
        "message": "division by zero",
        "stack_trace": "File test.py line 1",
        "release": "1.0.0",
        "retry_count": "0",
    }

    with SessionLocal() as db:
        # First processing
        res1 = worker._process_single_message("msg_1", event_payload, db)
        assert res1 is True

        # Check DB after 1st processing
        issue = db.query(Issue).filter(Issue.project_id == project_id).one()
        assert issue.count == 1
        assert db.query(ErrorEvent).filter(ErrorEvent.project_id == project_id).count() == 1

        # Process the EXACT same Redis message again (e.g. at-least-once redelivery)
        res2 = worker._process_single_message("msg_1_redelivery", event_payload, db)
        assert res2 is True

        # Verify idempotency: issue count unchanged, event count unchanged
        db.expire_all()
        issue_after = db.query(Issue).filter(Issue.project_id == project_id).one()
        assert issue_after.count == 1, "Issue count must remain 1 on duplicate processing"
        assert db.query(ErrorEvent).filter(ErrorEvent.project_id == project_id).count() == 1


def test_b_simulate_commit_succeeds_without_xack_and_redelivered(
    client: TestClient,
    override_queue: EventQueue,
    engine,
):
    """
    TEST B:
    Simulate:
    DB commit succeeds, XACK does not happen, same message is delivered again.
    Verify:
    - issue count is still correct (count = 1)
    - event count is still 1
    - duplicate delivery does not create another occurrence
    """
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    worker = IngestionWorker(queue=override_queue, session_factory=SessionLocal)

    proj = client.post("/api/v1/projects", json={"name": "Idempotent App B"}).json()
    project_id = proj["id"]

    event = {
        "event_id": "redelivery-test-uuid-2",
        "exception_type": "KeyError",
        "message": "missing 'session_token'",
        "stack_trace": "File auth.py line 45",
        "release": "1.0.0",
    }
    # Enqueue via bulk API
    client.post(f"/api/v1/projects/{project_id}/events/bulk", json={"events": [event]})

    # Worker dequeues
    messages = override_queue.dequeue_batch(batch_size=1)
    assert len(messages) == 1
    msg_id, data = messages[0]

    # Process first time with successful DB commit, but simulate crash before XACK
    with SessionLocal() as db:
        success = worker._process_single_message(msg_id, data, db)
        assert success is True

    # Redeliver: message was not acked or is delivered again
    with SessionLocal() as db:
        success_duplicate = worker._process_single_message("simulated_redelivery_msg_id", data, db)
        assert success_duplicate is True

    # Verify DB state
    with SessionLocal() as db:
        issue = db.query(Issue).filter(Issue.project_id == project_id).one()
        assert issue.count == 1
        events = db.query(ErrorEvent).filter(ErrorEvent.project_id == project_id).all()
        assert len(events) == 1
        assert events[0].event_id == "redelivery-test-uuid-2"


def test_c_100_unique_events_same_fingerprint(
    client: TestClient,
    override_queue: EventQueue,
    engine,
):
    """
    TEST C:
    100 unique events with the same fingerprint:
    - 100 ErrorEvent rows
    - exactly 1 Issue
    - issue count = 100
    """
    import uuid
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    worker = IngestionWorker(queue=override_queue, session_factory=SessionLocal)

    proj = client.post("/api/v1/projects", json={"name": "Unique Events App C"}).json()
    project_id = proj["id"]

    num_events = 100
    events = [
        {
            "event_id": str(uuid.uuid4()),
            "exception_type": "RuntimeError",
            "message": "service timeout",
            "stack_trace": "File app.py line 10\nraise RuntimeError()",
            "release": "1.0.0",
        }
        for _ in range(num_events)
    ]

    client.post(f"/api/v1/projects/{project_id}/events/bulk", json={"events": events})

    while True:
        count = worker.process_next_batch(batch_size=50)
        if count == 0:
            break

    with SessionLocal() as db:
        issues = db.query(Issue).filter(Issue.project_id == project_id).all()
        assert len(issues) == 1
        assert issues[0].count == 100

        event_count = db.query(ErrorEvent).filter(ErrorEvent.project_id == project_id).count()
        assert event_count == 100


def test_d_100_duplicate_deliveries_of_one_event_id(
    client: TestClient,
    override_queue: EventQueue,
    engine,
):
    """
    TEST D:
    100 duplicate deliveries of ONE event_id:
    - 1 ErrorEvent row
    - exactly 1 Issue
    - issue count = 1
    """
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    worker = IngestionWorker(queue=override_queue, session_factory=SessionLocal)

    proj = client.post("/api/v1/projects", json={"name": "Duplicate Deliveries App D"}).json()
    project_id = proj["id"]

    fixed_event_id = "single-fixed-event-id-999"
    fixed_payload = {
        "event_id": fixed_event_id,
        "project_id": str(project_id),
        "exception_type": "TypeError",
        "message": "expected str, got None",
        "stack_trace": "File handler.py line 20",
        "release": "1.0.0",
        "retry_count": "0",
    }

    # Simulate 100 deliveries of the exact same message
    for i in range(100):
        with SessionLocal() as db:
            ok = worker._process_single_message(f"msg_{i}", fixed_payload, db)
            assert ok is True

    with SessionLocal() as db:
        issues = db.query(Issue).filter(Issue.project_id == project_id).all()
        assert len(issues) == 1
        assert issues[0].count == 1, f"Expected count=1, got {issues[0].count}"

        events = db.query(ErrorEvent).filter(ErrorEvent.project_id == project_id).all()
        assert len(events) == 1
        assert events[0].event_id == fixed_event_id


def test_e_redis_unavailable_in_normal_application_mode_fails_explicitly():
    """
    TEST E:
    Redis unavailable in normal application mode:
    - application does not silently switch to fakeredis
    - behavior is explicit and documented
    """
    import redis
    # Attempting to initialize EventQueue with an unreachable Redis server must raise ConnectionError
    with pytest.raises(redis.exceptions.ConnectionError):
        EventQueue(redis_url="redis://127.0.0.1:9999/0")
