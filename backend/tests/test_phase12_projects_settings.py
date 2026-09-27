"""
Phase 12 Tests: Projects, Settings, Credential Security, RBAC, and Real Pipeline Verification.
"""

from unittest.mock import MagicMock
import uuid
import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.auth import create_access_token, hash_password
from app.db import Base, engine, get_db
from app.main import app
from app.models import Environment, ErrorEvent, Issue, Membership, Project, Release, Tenant, User
from app.queue import EventQueue, get_queue
from app.worker import IngestionWorker


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def fake_redis_queue():
    """Provides an isolated EventQueue powered by fakeredis for tests."""
    client = fakeredis.FakeRedis(decode_responses=True)
    return EventQueue(redis_client=client)


@pytest.fixture
def override_queue(fake_redis_queue):
    """Overrides FastAPI get_queue dependency to use the isolated fake_redis_queue."""
    app.dependency_overrides[get_queue] = lambda: fake_redis_queue
    yield fake_redis_queue
    app.dependency_overrides.pop(get_queue, None)


def test_phase12_projects_stats_and_rbac(client: TestClient, db_session: Session):
    owner = User(email=f"p12_owner_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    admin = User(email=f"p12_admin_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    member = User(email=f"p12_member_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    db_session.add_all([owner, admin, member])
    db_session.flush()

    tenant_a = Tenant(name="Acme Corp", slug=f"acme-p12-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant_a)
    db_session.flush()

    db_session.add(Membership(tenant_id=tenant_a.id, user_id=owner.id, role="owner"))
    db_session.add(Membership(tenant_id=tenant_a.id, user_id=admin.id, role="admin"))
    db_session.add(Membership(tenant_id=tenant_a.id, user_id=member.id, role="member"))
    
    project_a = Project(name="Backend Service", tenant_id=tenant_a.id, api_key="rg_live_testkey123456789012")
    db_session.add(project_a)
    db_session.flush()

    env = Environment(project_id=project_a.id, key="production", name="Production")
    rel = Release(project_id=project_a.id, version="v1.0.0", environment="production")
    db_session.add_all([env, rel])
    db_session.commit()

    token_owner = create_access_token(owner.id)
    token_admin = create_access_token(admin.id)
    token_member = create_access_token(member.id)

    headers_owner = {"Authorization": f"Bearer {token_owner}"}
    headers_admin = {"Authorization": f"Bearer {token_admin}"}
    headers_member = {"Authorization": f"Bearer {token_member}"}

    # 1. Member can list projects and receive enriched summary stats
    res = client.get(f"/api/v1/tenants/{tenant_a.id}/projects", headers=headers_member)
    assert res.status_code == 200, res.text
    projects = res.json()
    assert len(projects) >= 1
    target = next(p for p in projects if p["id"] == project_a.id)
    assert target["name"] == "Backend Service"
    assert target["environments_count"] == 1
    assert target["releases_count"] == 1
    assert target["recent_release"] == "v1.0.0"
    assert target["issues_count"] == 0

    # 2. Member CANNOT update project name (requires admin/owner)
    res_member_patch = client.patch(
        f"/api/v1/tenants/{tenant_a.id}/projects/{project_a.id}",
        json={"name": "Hacked Name"},
        headers=headers_member,
    )
    assert res_member_patch.status_code == 403

    # 3. Admin CAN update project name
    res_admin_patch = client.patch(
        f"/api/v1/tenants/{tenant_a.id}/projects/{project_a.id}",
        json={"name": "Backend Core Service"},
        headers=headers_admin,
    )
    assert res_admin_patch.status_code == 200
    assert res_admin_patch.json()["name"] == "Backend Core Service"

    # 4. Admin CAN update tenant name
    res_tenant_patch = client.patch(
        f"/api/v1/tenants/{tenant_a.id}",
        json={"name": "Acme Global"},
        headers=headers_admin,
    )
    assert res_tenant_patch.status_code == 200
    assert res_tenant_patch.json()["name"] == "Acme Global"


def test_phase12_project_credential_security_rbac(client: TestClient, db_session: Session):
    """
    Test Project Ingestion Credential Security:
    - Member sees masked key in project responses.
    - Member receives 403 Forbidden when attempting to fetch raw key.
    - Admin and Owner can retrieve the real plaintext key.
    - Outsiders receive 403/404.
    """
    owner = User(email=f"cred_owner_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    admin = User(email=f"cred_admin_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    member = User(email=f"cred_member_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    outsider = User(email=f"cred_outsider_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    db_session.add_all([owner, admin, member, outsider])
    db_session.flush()

    tenant = Tenant(name="Cred Security Inc", slug=f"cred-sec-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    db_session.flush()

    db_session.add(Membership(tenant_id=tenant.id, user_id=owner.id, role="owner"))
    db_session.add(Membership(tenant_id=tenant.id, user_id=admin.id, role="admin"))
    db_session.add(Membership(tenant_id=tenant.id, user_id=member.id, role="member"))

    raw_api_key = f"rg_live_secret_{uuid.uuid4().hex}"
    project = Project(name="Protected Service", tenant_id=tenant.id, api_key=raw_api_key)
    db_session.add(project)
    db_session.commit()

    headers_owner = {"Authorization": f"Bearer {create_access_token(owner.id)}"}
    headers_admin = {"Authorization": f"Bearer {create_access_token(admin.id)}"}
    headers_member = {"Authorization": f"Bearer {create_access_token(member.id)}"}
    headers_outsider = {"Authorization": f"Bearer {create_access_token(outsider.id)}"}

    # 1. Member GET /projects: key must be masked, plaintext secret NOT exposed
    res_list = client.get(f"/api/v1/tenants/{tenant.id}/projects", headers=headers_member)
    assert res_list.status_code == 200
    listed_proj = next(p for p in res_list.json() if p["id"] == project.id)
    assert raw_api_key not in listed_proj["api_key"]
    assert "•" in listed_proj["api_key"]

    # 2. Member GET /projects/{id}: key must be masked
    res_get = client.get(f"/api/v1/tenants/{tenant.id}/projects/{project.id}", headers=headers_member)
    assert res_get.status_code == 200
    assert raw_api_key not in res_get.json()["api_key"]
    assert "•" in res_get.json()["api_key"]

    # 3. Member GET /projects/{id}/key: permission denied (403 Forbidden)
    res_member_key = client.get(f"/api/v1/tenants/{tenant.id}/projects/{project.id}/key", headers=headers_member)
    assert res_member_key.status_code == 403
    assert any(term in res_member_key.text.lower() for term in ("admin", "role", "permission", "insufficient"))

    # 4. Outsider GET /projects/{id}/key: permission denied (403 or 404)
    res_outsider_key = client.get(f"/api/v1/tenants/{tenant.id}/projects/{project.id}/key", headers=headers_outsider)
    assert res_outsider_key.status_code in (403, 404)

    # 5. Admin GET /projects/{id}/key: succeeds with real plaintext key
    res_admin_key = client.get(f"/api/v1/tenants/{tenant.id}/projects/{project.id}/key", headers=headers_admin)
    assert res_admin_key.status_code == 200
    assert res_admin_key.json()["api_key"] == raw_api_key
    assert res_admin_key.json()["project_id"] == project.id

    # 6. Owner GET /projects/{id}/key: succeeds with real plaintext key
    res_owner_key = client.get(f"/api/v1/tenants/{tenant.id}/projects/{project.id}/key", headers=headers_owner)
    assert res_owner_key.status_code == 200
    assert res_owner_key.json()["api_key"] == raw_api_key
    assert res_owner_key.json()["project_id"] == project.id


def test_phase12_test_event_real_pipeline(
    client: TestClient,
    override_queue: EventQueue,
    db_session: Session,
):
    """
    Test real asynchronous pipeline verification:
    - POST test-event returns 202 Accepted with pending status and stable event_id.
    - Does NOT directly create ErrorEvent or Issue in DB.
    - Event is actually present in Redis stream.
    - Status endpoint GET returns pending.
    - Duplicate status polling is safe.
    - Worker consumes from Redis stream and persists Issue + ErrorEvent.
    - Status endpoint GET then transitions to completed with issue_id.
    - Duplicate Redis message redelivery is idempotent and does not double-count.
    - Redis outage explicitly fails with 503.
    - Cross-tenant requests fail.
    """
    user = User(email=f"pipeline_user_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    db_session.add(user)
    db_session.flush()

    tenant = Tenant(name="Pipeline Tenant", slug=f"pipe-tenant-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    db_session.flush()

    db_session.add(Membership(tenant_id=tenant.id, user_id=user.id, role="member"))
    project = Project(name="Async Project", tenant_id=tenant.id, api_key="rg_live_asynckey123")
    db_session.add(project)
    db_session.commit()

    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    # 1. Dispatch test event -> returns 202 Accepted with pending status
    res_post = client.post(
        f"/api/v1/tenants/{tenant.id}/projects/{project.id}/test-event",
        headers=headers,
    )
    assert res_post.status_code == 202, res_post.text
    post_data = res_post.json()
    assert post_data["status"] == "pending"
    assert post_data["event_id"] is not None
    assert post_data["issue_id"] is None
    event_id = post_data["event_id"]

    # 2. Verify event is NOT in the database yet
    db_event_before = db_session.query(ErrorEvent).filter(ErrorEvent.event_id == event_id).first()
    assert db_event_before is None

    # 3. Verify event IS in the Redis stream
    metrics = override_queue.get_metrics()
    assert metrics["queue_depth"] == 1

    # 4. Status endpoint returns pending initially
    res_status_1 = client.get(
        f"/api/v1/tenants/{tenant.id}/projects/{project.id}/test-event/{event_id}",
        headers=headers,
    )
    assert res_status_1.status_code == 200
    assert res_status_1.json()["status"] == "pending"
    assert res_status_1.json()["issue_id"] is None

    # Duplicate polling is safe
    res_status_dup = client.get(
        f"/api/v1/tenants/{tenant.id}/projects/{project.id}/test-event/{event_id}",
        headers=headers,
    )
    assert res_status_dup.status_code == 200
    assert res_status_dup.json()["status"] == "pending"

    # 5. Worker processes the Redis message
    from app.db import SessionLocal
    worker = IngestionWorker(queue=override_queue, session_factory=SessionLocal)
    processed = worker.process_next_batch(batch_size=10)
    assert processed == 1

    # 6. Verify worker persisted ErrorEvent and Issue in PostgreSQL
    db_session.expire_all()
    db_event_after = db_session.query(ErrorEvent).filter(ErrorEvent.event_id == event_id).first()
    assert db_event_after is not None
    assert db_event_after.project_id == project.id
    assert db_event_after.issue_id is not None
    issue_id = db_event_after.issue_id

    # 7. Status endpoint now returns completed with issue_id
    res_status_2 = client.get(
        f"/api/v1/tenants/{tenant.id}/projects/{project.id}/test-event/{event_id}",
        headers=headers,
    )
    assert res_status_2.status_code == 200
    status_data = res_status_2.json()
    assert status_data["status"] == "completed"
    assert status_data["issue_id"] == issue_id
    assert status_data["event_id"] == event_id

    # Duplicate completed polling is safe
    res_status_completed_dup = client.get(
        f"/api/v1/tenants/{tenant.id}/projects/{project.id}/test-event/{event_id}",
        headers=headers,
    )
    assert res_status_completed_dup.status_code == 200
    assert res_status_completed_dup.json()["status"] == "completed"

    # 8. Duplicate Redis message redelivery is idempotent (does not double-count)
    override_queue.enqueue_events(project.id, [{
        "event_id": event_id,
        "exception_type": "ReleaseGuardVerificationEvent",
        "message": "Integration verification test event successfully received.",
        "stack_trace": "tb",
    }])
    processed_dup = worker.process_next_batch(batch_size=10)
    assert processed_dup == 1

    # Issue count remains 1
    db_session.expire_all()
    issue = db_session.query(Issue).filter(Issue.id == issue_id).first()
    assert issue.count == 1

    # 9. Redis outage fails explicitly with 503
    mock_broken_queue = MagicMock()
    mock_broken_queue.enqueue_events.side_effect = ConnectionError("Redis connection lost")
    app.dependency_overrides[get_queue] = lambda: mock_broken_queue
    try:
        res_outage = client.post(
            f"/api/v1/tenants/{tenant.id}/projects/{project.id}/test-event",
            headers=headers,
        )
        assert res_outage.status_code == 503
        assert "unavailable" in res_outage.text.lower()
    finally:
        app.dependency_overrides[get_queue] = lambda: override_queue

    # 10. Cross-tenant access remains isolated
    other_tenant = Tenant(name="Other Tenant", slug=f"other-{uuid.uuid4().hex[:6]}")
    db_session.add(other_tenant)
    db_session.flush()
    other_proj = Project(name="Other Project", tenant_id=other_tenant.id, api_key="rg_live_other")
    db_session.add(other_proj)
    db_session.commit()

    res_cross = client.post(
        f"/api/v1/tenants/{other_tenant.id}/projects/{other_proj.id}/test-event",
        headers=headers,
    )
    assert res_cross.status_code in (403, 404)


def test_phase12_last_owner_and_key_isolation(client: TestClient, db_session: Session):
    solo_owner = User(email=f"solo_owner_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    team_member = User(email=f"team_member_{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("Pass123!"))
    db_session.add_all([solo_owner, team_member])
    db_session.flush()

    tenant = Tenant(name="Security Tenant", slug=f"sec-tenant-{uuid.uuid4().hex[:6]}")
    db_session.add(tenant)
    db_session.flush()

    db_session.add(Membership(tenant_id=tenant.id, user_id=solo_owner.id, role="owner"))
    db_session.add(Membership(tenant_id=tenant.id, user_id=team_member.id, role="member"))

    project1 = Project(name="Project One", tenant_id=tenant.id, api_key="rg_live_proj1_key")
    project2 = Project(name="Project Two", tenant_id=tenant.id, api_key="rg_live_proj2_key")
    db_session.add_all([project1, project2])
    db_session.commit()

    token_owner = create_access_token(solo_owner.id)
    headers_owner = {"Authorization": f"Bearer {token_owner}"}

    # 1. Last owner invariant: Owner cannot demote self if sole owner
    res_demote = client.patch(
        f"/api/v1/tenants/{tenant.id}/members/{solo_owner.id}",
        json={"role": "member"},
        headers=headers_owner,
    )
    assert res_demote.status_code == 400
    assert "last owner" in res_demote.text.lower() or "sole owner" in res_demote.text.lower() or "owner" in res_demote.text.lower()

    # 2. Key isolation: project1 key cannot be used against project2
    event_payload = {
        "event_id": uuid.uuid4().hex,
        "exception_type": "SecurityCheckError",
        "message": "Testing cross project key ingestion",
        "stack_trace": "None",
    }
    res_bad_key = client.post(
        f"/api/v1/projects/{project2.id}/events",
        json=event_payload,
        headers={"X-ReleaseGuard-Key": "rg_live_proj1_key"},
    )
    assert res_bad_key.status_code == 401
