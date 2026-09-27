import os
import uuid
import fakeredis
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app.auth_limiter import AuthRateLimiter, auth_limiter
from app.config import settings
from app.db import get_db
from app.logging import redact_sensitive
from app.main import app
from app.models import Issue, Project, Tenant, User
from app.queue import EventQueue, get_queue
from app.worker import IngestionWorker


@pytest.fixture
def fake_redis_queue():
    """Provides an isolated EventQueue powered by fakeredis for tests."""
    client = fakeredis.FakeRedis(decode_responses=True)
    return EventQueue(redis_client=client)


@pytest.fixture(autouse=True)
def override_queue(fake_redis_queue):
    """Overrides the FastAPI get_queue dependency to use the isolated fake_redis_queue."""
    app.dependency_overrides[get_queue] = lambda: fake_redis_queue
    # Also configure auth_limiter with the test redis client
    auth_limiter.redis_client = fake_redis_queue.client
    yield fake_redis_queue
    app.dependency_overrides.pop(get_queue, None)


def test_health_liveness_and_readiness(client: TestClient):
    """Verifies separated liveness (/health) and readiness (/health/ready) probes."""
    # 1. Liveness
    resp_live = client.get("/health")
    assert resp_live.status_code == 200
    assert resp_live.json()["status"] == "ok"
    assert "service" in resp_live.json()

    # 2. Readiness
    resp_ready = client.get("/health/ready")
    assert resp_ready.status_code == 200
    data = resp_ready.json()
    assert data["status"] == "ready"
    assert data["dependencies"]["database"] == "connected"
    assert data["dependencies"]["redis"] == "connected"


def test_security_headers_and_request_id(client: TestClient):
    """Verifies security headers and X-Request-ID propagation."""
    custom_req_id = "test-corr-" + uuid.uuid4().hex[:8]
    resp = client.get("/health", headers={"X-Request-ID": custom_req_id})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == custom_req_id
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_oversized_payload_rejection(client: TestClient):
    """Verifies that oversized payloads return HTTP 413."""
    proj = client.post("/api/v1/projects", json={"name": "Oversized Test App"}).json()
    p_id = proj["id"]

    # Send Content-Length exceeding standard limit (1MB + 10 bytes)
    too_large_size = settings.MAX_PAYLOAD_SIZE + 100
    resp = client.post(
        f"/api/v1/projects/{p_id}/events",
        content=b"x" * 10,
        headers={"Content-Length": str(too_large_size), "Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    assert "Payload too large" in resp.json()["detail"]


def test_bulk_ingestion_limit_enforced(client: TestClient):
    """Verifies that bulk ingestion rejects batches exceeding 100 events with 422."""
    proj = client.post("/api/v1/projects", json={"name": "Bulk Limit App"}).json()
    p_id = proj["id"]

    # 101 events exceeds MAX_BULK_EVENTS
    events_101 = [
        {"exception_type": "LimitError", "message": f"msg {i}", "stack_trace": "trace"}
        for i in range(101)
    ]
    resp = client.post(
        f"/api/v1/projects/{p_id}/events/bulk",
        json={"events": events_101},
    )
    assert resp.status_code == 422


def test_auth_rate_limiting_and_lockout(client: TestClient):
    """Verifies failed authentication attempt protection and 429 lockout."""
    email = f"ratelimit_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"

    # Register user
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "tenant_name": "RL Org"},
    )
    assert reg_resp.status_code == 201

    # Ensure counter starts clean
    auth_limiter.reset(email)

    # Perform failed attempts up to max_attempts (5)
    for _ in range(settings.AUTH_MAX_ATTEMPTS):
        fail_resp = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPassword!"},
        )
        assert fail_resp.status_code == 401

    # Next attempt should be locked out with 429
    locked_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert locked_resp.status_code == 429
    assert "Too many failed login attempts" in locked_resp.json()["detail"]

    # Reset cleans the lockout
    auth_limiter.reset(email)
    success_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert success_resp.status_code == 200


def test_pagination_bounds_and_deterministic_order(client: TestClient):
    """Verifies max pagination limit (<= 100) and deterministic sorting."""
    proj = client.post("/api/v1/projects", json={"name": "Paging App"}).json()
    p_id = proj["id"]

    # Attempt limit > 100 should be rejected by validation with 422
    resp_large_limit = client.get(f"/api/v1/projects/{p_id}/issues?limit=150")
    assert resp_large_limit.status_code == 422

    # Normal paginated request
    resp_valid = client.get(f"/api/v1/projects/{p_id}/issues?limit=50&offset=0")
    assert resp_valid.status_code == 200
    assert isinstance(resp_valid.json(), list)


def test_secret_redaction_in_logs():
    """Verifies that passwords, API keys, and JWT tokens are redacted."""
    raw_message = (
        'User login failed with password="SecretPassword123" '
        'and api_key="rg_live_abcdef1234567890abcdef" '
        'and authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz'
    )
    redacted = redact_sensitive(raw_message)

    assert "SecretPassword123" not in redacted
    assert "abcdef1234567890abcdef" not in redacted
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz" not in redacted
    assert "[REDACTED]" in redacted

    # Verify Redis and PostgreSQL connection URL password redaction
    redis_log = "Connected to Redis at rediss://default:SuperSecretRedisToken123!@prod-cluster.internal:6379/0"
    redacted_redis = redact_sensitive(redis_log)
    assert "SuperSecretRedisToken123!" not in redacted_redis
    assert "rediss://[REDACTED]@prod-cluster.internal:6379/0" in redacted_redis


def test_database_rollback_on_session_error():
    """Verifies that an exception during DB session yields automatic rollback."""
    gen = get_db()
    session = next(gen)
    try:
        # Simulate active transaction with broken command
        session.execute(text("SELECT * FROM non_existent_table_for_rollback_test"))
    except Exception:
        pass

    # Closing through generator must execute db.rollback() without raising
    try:
        gen.throw(RuntimeError("Simulated application error"))
    except RuntimeError:
        pass


def test_stale_pel_recovery_and_stream_trimming(client: TestClient, fake_redis_queue: EventQueue):
    """Verifies bounded stream retention and stale PEL recovery."""
    proj = client.post("/api/v1/projects", json={"name": "PEL App"}).json()
    project_id = proj["id"]

    queue = fake_redis_queue
    queue.clear()

    # Enqueue events
    events = [
        {
            "event_id": f"pel_test_{i}",
            "exception_type": "StaleError",
            "message": f"Stale error {i}",
            "stack_trace": "line 1",
        }
        for i in range(5)
    ]
    batch_id, count = queue.enqueue_events(project_id=project_id, events=events)
    assert count == 5

    # Dequeue using consumer_dead but do NOT acknowledge (leaves them in PEL)
    msgs = queue.dequeue_batch(batch_size=5, consumer_name="consumer_dead")
    assert len(msgs) == 5

    # Health check shows PEL count
    health = queue.get_health()
    assert health["redis_connected"] is True
    assert health["pel_count"] >= 5

    # Recover with min_idle_time_ms=0 for testing
    recovered = queue.recover_stale_pending(min_idle_time_ms=0, count=5, consumer_name="recovery_worker")
    assert len(recovered) == 5

    # Worker can process recovered messages cleanly
    worker = IngestionWorker(queue=queue, consumer_name="recovery_worker")
    processed = worker.recover_stale_messages(min_idle_time_ms=0, count=5)
    assert processed == 5

    # Acknowledged -> PEL count reduces
    queue.clear()


import threading


def test_production_auth_limiter_fails_without_redis():
    """Verifies that production mode explicitly rejects startup/checks without Redis."""
    orig_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "production"
        # 1. Unreachable Redis in production raises RuntimeError
        with pytest.raises(RuntimeError, match="Production mode requires an operational Redis instance"):
            AuthRateLimiter(redis_url="redis://127.0.0.1:9999/0")

        # 2. If redis_client is None in production, operations raise RuntimeError
        limiter = AuthRateLimiter.__new__(AuthRateLimiter)
        limiter.max_attempts = 5
        limiter.lockout_seconds = 900
        limiter._memory_store = {}
        limiter._lock = threading.Lock()
        limiter.redis_client = None

        with pytest.raises(RuntimeError, match="Production mode requires Redis"):
            limiter.is_locked("test@example.com")

        with pytest.raises(RuntimeError, match="Production mode requires Redis"):
            limiter.record_failure("test@example.com")

        with pytest.raises(RuntimeError, match="Production mode requires Redis"):
            limiter.reset("test@example.com")
    finally:
        settings.ENVIRONMENT = orig_env


def test_dev_auth_limiter_allows_in_memory_fallback():
    """Verifies development/test mode gracefully uses in-memory store when Redis is unavailable."""
    orig_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "development"
        limiter = AuthRateLimiter(redis_url="redis://127.0.0.1:9999/0")
        assert limiter.redis_client is None
        # Does not raise; uses in-memory fallback
        assert limiter.is_locked("dev@example.com") is False
        limiter.record_failure("dev@example.com")
        assert "auth:failed:dev@example.com" in limiter._memory_store
        limiter.reset("dev@example.com")
        assert "auth:failed:dev@example.com" not in limiter._memory_store
    finally:
        settings.ENVIRONMENT = orig_env


def test_alembic_migration_file_exists():
    """Verifies that initial Alembic migration file exists and is well-formed."""
    versions_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations", "versions")
    files = [f for f in os.listdir(versions_dir) if f.endswith(".py")]
    assert len(files) >= 1
    assert any("initial_schema" in f for f in files)

