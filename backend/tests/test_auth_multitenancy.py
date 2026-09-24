"""
Phase 7 Security Tests: Multi-Tenancy Isolation, Authentication, and Permissions.
Mandatory tests TEST A through TEST M.
"""

from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.models import ErrorEvent, Issue, Membership, Project, Tenant, TenantInvite, User


def register_user(client: TestClient, email: str, password: str = "password123", tenant_name: str | None = None):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "tenant_name": tenant_name},
    )
    assert resp.status_code == 201
    data = resp.json()
    token = data["access_token"]
    user = data["user"]

    # Get user profile with tenants
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    tenant = me["tenants"][0]
    return token, user, tenant


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# TEST A: Cross-Tenant Project Access -> 404
# =========================================================================

def test_a_user_a_cannot_access_tenant_b_project(client: TestClient):
    """TEST A: User A in Tenant A requests Tenant B project -> 404."""
    token_a, user_a, tenant_a = register_user(client, "usera@example.com", tenant_name="Tenant A")
    token_b, user_b, tenant_b = register_user(client, "userb@example.com", tenant_name="Tenant B")

    # User B creates a project in Tenant B
    p_b_resp = client.post(
        f"/api/v1/tenants/{tenant_b['id']}/projects",
        json={"name": "Tenant B Secret Core"},
        headers=auth_headers(token_b),
    )
    assert p_b_resp.status_code == 201
    project_b_id = p_b_resp.json()["id"]

    # 1. User A queries Tenant B's project via Tenant B's locator -> 404 (not a member)
    r1 = client.get(
        f"/api/v1/tenants/{tenant_b['id']}/projects/{project_b_id}",
        headers=auth_headers(token_a),
    )
    assert r1.status_code == 404

    # 2. User A queries Tenant B's project ID via Tenant A's locator -> 404 (not owned by Tenant A)
    r2 = client.get(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{project_b_id}",
        headers=auth_headers(token_a),
    )
    assert r2.status_code == 404


# =========================================================================
# TEST B: Cross-Tenant Issue Access -> 404
# =========================================================================

def test_b_user_a_cannot_access_tenant_b_issue(client: TestClient):
    """TEST B: User A requests Tenant B issue -> 404."""
    token_a, user_a, tenant_a = register_user(client, "user_a2@example.com", tenant_name="Tenant A2")
    token_b, user_b, tenant_b = register_user(client, "user_b2@example.com", tenant_name="Tenant B2")

    # Project and Issue in Tenant B
    proj_b = client.post(
        f"/api/v1/tenants/{tenant_b['id']}/projects",
        json={"name": "Project B2"},
        headers=auth_headers(token_b),
    ).json()
    pb_id = proj_b["id"]

    # Ingest error event for Project B
    ev_resp = client.post(
        f"/api/v1/projects/{pb_id}/events",
        json={"exception_type": "TenantBCrash", "message": "classified", "stack_trace": "tb"},
    )
    assert ev_resp.status_code == 201
    issue_b_id = ev_resp.json()["issue_id"]

    # User A tries to inspect Tenant B's issue -> 404
    r = client.get(
        f"/api/v1/tenants/{tenant_b['id']}/projects/{pb_id}/issues/{issue_b_id}",
        headers=auth_headers(token_a),
    )
    assert r.status_code == 404


# =========================================================================
# TEST C: Cross-Tenant Event Timeline Access -> 404
# =========================================================================

def test_c_user_a_cannot_access_tenant_b_event_timeline(client: TestClient):
    """TEST C: User A requests Tenant B event timeline -> 404."""
    token_a, _, tenant_a = register_user(client, "user_a3@example.com")
    token_b, _, tenant_b = register_user(client, "user_b3@example.com")

    proj_b = client.post(
        f"/api/v1/tenants/{tenant_b['id']}/projects",
        json={"name": "Project B3"},
        headers=auth_headers(token_b),
    ).json()
    pb_id = proj_b["id"]

    ev = client.post(
        f"/api/v1/projects/{pb_id}/events",
        json={"exception_type": "AuthCrash", "message": "unauthorized token", "stack_trace": "tb"},
    ).json()
    issue_b_id = ev["issue_id"]

    # User A tries to view Tenant B's event timeline -> 404
    r = client.get(
        f"/api/v1/tenants/{tenant_b['id']}/projects/{pb_id}/issues/{issue_b_id}/events",
        headers=auth_headers(token_a),
    )
    assert r.status_code == 404


# =========================================================================
# TEST D: Cross-Tenant Status Modification -> 404
# =========================================================================

def test_d_user_a_cannot_modify_tenant_b_issue_status(client: TestClient):
    """TEST D: User A attempts to modify Tenant B issue status -> 404."""
    token_a, _, tenant_a = register_user(client, "user_a4@example.com")
    token_b, _, tenant_b = register_user(client, "user_b4@example.com")

    proj_b = client.post(
        f"/api/v1/tenants/{tenant_b['id']}/projects",
        json={"name": "Project B4"},
        headers=auth_headers(token_b),
    ).json()
    pb_id = proj_b["id"]

    ev = client.post(
        f"/api/v1/projects/{pb_id}/events",
        json={"exception_type": "Err", "message": "m", "stack_trace": "s"},
    ).json()
    issue_b_id = ev["issue_id"]

    # User A tries to resolve Tenant B issue -> 404
    r_res = client.post(
        f"/api/v1/tenants/{tenant_b['id']}/projects/{pb_id}/issues/{issue_b_id}/resolve",
        headers=auth_headers(token_a),
    )
    assert r_res.status_code == 404

    # User A tries to mute Tenant B issue -> 404
    r_mute = client.post(
        f"/api/v1/tenants/{tenant_b['id']}/projects/{pb_id}/issues/{issue_b_id}/mute",
        headers=auth_headers(token_a),
    )
    assert r_mute.status_code == 404


# =========================================================================
# TEST E: Cross-Tenant Project Creation -> Denied
# =========================================================================

def test_e_user_a_cannot_create_project_in_tenant_b(client: TestClient):
    """TEST E: User A attempts to create a project inside Tenant B -> 404 (denied)."""
    token_a, _, _ = register_user(client, "user_a5@example.com")
    _, _, tenant_b = register_user(client, "user_b5@example.com")

    r = client.post(
        f"/api/v1/tenants/{tenant_b['id']}/projects",
        json={"name": "Infiltrator Project"},
        headers=auth_headers(token_a),
    )
    assert r.status_code == 404


# =========================================================================
# TEST F: Non-Member Access Denied
# =========================================================================

def test_f_non_member_cannot_access_tenant(client: TestClient):
    """TEST F: User A is not a tenant member -> cannot access tenant -> 404."""
    token_a, _, _ = register_user(client, "user_a6@example.com")
    _, _, tenant_b = register_user(client, "user_b6@example.com")

    # Member list access denied
    r_members = client.get(
        f"/api/v1/tenants/{tenant_b['id']}/members",
        headers=auth_headers(token_a),
    )
    assert r_members.status_code == 404

    # Tenant details access denied
    r_tenant = client.get(
        f"/api/v1/tenants/{tenant_b['id']}",
        headers=auth_headers(token_a),
    )
    assert r_tenant.status_code == 404


# =========================================================================
# TEST G: Role Hierarchy Check (Admin cannot perform Owner-only action)
# =========================================================================

def test_g_admin_cannot_perform_owner_only_action(client: TestClient):
    """TEST G: Admin cannot promote/demote or remove an owner -> 403."""
    token_owner, user_owner, tenant = register_user(client, "owner_g@example.com")
    token_admin, user_admin, _ = register_user(client, "admin_g@example.com")

    # Owner invites admin_g as admin
    inv = client.post(
        f"/api/v1/tenants/{tenant['id']}/invites",
        json={"email": "admin_g@example.com", "role": "admin"},
        headers=auth_headers(token_owner),
    ).json()

    # Admin accepts invite
    acc = client.post(f"/api/v1/invites/{inv['token']}/accept", headers=auth_headers(token_admin))
    assert acc.status_code == 200

    # Admin tries to demote the Owner to member -> 403 Forbidden!
    r_demote = client.patch(
        f"/api/v1/tenants/{tenant['id']}/members/{user_owner['id']}",
        json={"role": "member"},
        headers=auth_headers(token_admin),
    )
    assert r_demote.status_code == 403

    # Admin tries to remove Owner -> 403 Forbidden!
    r_remove = client.delete(
        f"/api/v1/tenants/{tenant['id']}/members/{user_owner['id']}",
        headers=auth_headers(token_admin),
    )
    assert r_remove.status_code == 403


# =========================================================================
# TEST H: Last-Owner Protection
# =========================================================================

def test_h_last_owner_cannot_demote_or_remove_themselves(client: TestClient):
    """TEST H: Sole tenant owner cannot demote or remove themselves -> 400."""
    token, user, tenant = register_user(client, "sole_owner@example.com")

    # 1. Owner attempts to demote self to member -> 400
    r_demote = client.patch(
        f"/api/v1/tenants/{tenant['id']}/members/{user['id']}",
        json={"role": "member"},
        headers=auth_headers(token),
    )
    assert r_demote.status_code == 400
    assert "last owner" in r_demote.json()["detail"].lower()

    # 2. Owner attempts to remove self leaving 0 owners -> 400
    r_remove = client.delete(
        f"/api/v1/tenants/{tenant['id']}/members/{user['id']}",
        headers=auth_headers(token),
    )
    assert r_remove.status_code == 400
    assert "last owner" in r_remove.json()["detail"].lower()


# =========================================================================
# TEST I: Project SDK Ingestion Key Isolation
# =========================================================================

def test_i_project_sdk_key_for_tenant_a_cannot_ingest_into_tenant_b(client: TestClient):
    """TEST I: Project SDK key for Tenant A cannot ingest into Tenant B -> 401."""
    token_a, _, tenant_a = register_user(client, "user_ia@example.com")
    token_b, _, tenant_b = register_user(client, "user_ib@example.com")

    # Project in Tenant A
    p_a = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects",
        json={"name": "Project A"},
        headers=auth_headers(token_a),
    ).json()
    key_a = p_a["api_key"]

    # Project in Tenant B
    p_b = client.post(
        f"/api/v1/tenants/{tenant_b['id']}/projects",
        json={"name": "Project B"},
        headers=auth_headers(token_b),
    ).json()
    pb_id = p_b["id"]

    # Attempt to ingest into Project B using Project A's secret key!
    r = client.post(
        f"/api/v1/projects/{pb_id}/events",
        json={
            "exception_type": "SpoofedEvent",
            "message": "spoof",
            "stack_trace": "trace",
        },
        headers={"X-ReleaseGuard-Key": key_a},
    )
    # Must be denied (401 Unauthorized)
    assert r.status_code == 401
    assert "Invalid ReleaseGuard project key" in r.json()["detail"]


# =========================================================================
# TEST J & K: Expired & Invalid JWT Tokens
# =========================================================================

def test_j_expired_jwt_rejected(client: TestClient):
    """TEST J: Expired JWT token is rejected -> 401."""
    # Create an expired token (expired 10 minutes ago)
    expired_token = create_access_token(user_id=1, expires_delta=timedelta(minutes=-10))

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_k_invalid_jwt_rejected(client: TestClient):
    """TEST K: Malformed or forged JWT is rejected -> 401."""
    r_garbage = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage-token-value"})
    assert r_garbage.status_code == 401

    # Token signed with wrong secret
    import jwt
    fake_token = jwt.encode({"sub": "1"}, "wrong-secret-key", algorithm="HS256")
    r_fake = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
    assert r_fake.status_code == 401


# =========================================================================
# TEST L & M: Tenant Invitation Tokens
# =========================================================================

def test_l_expired_invite_cannot_be_accepted(client: TestClient, engine):
    """TEST L: Expired invite token cannot be accepted -> 400."""
    token_owner, _, tenant = register_user(client, "owner_l@example.com")
    token_user, _, _ = register_user(client, "recipient_l@example.com")

    # Create invite
    inv = client.post(
        f"/api/v1/tenants/{tenant['id']}/invites",
        json={"email": "recipient_l@example.com", "role": "member"},
        headers=auth_headers(token_owner),
    ).json()

    # Artificially expire the invite in the database
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        db_inv = db.get(TenantInvite, inv["id"])
        db_inv.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        db.commit()

    # Recipient attempts to accept expired invite -> 400
    r = client.post(
        f"/api/v1/invites/{inv['token']}/accept",
        headers=auth_headers(token_user),
    )
    assert r.status_code == 400
    assert "expired" in r.json()["detail"].lower()


def test_m_invite_cannot_be_accepted_twice(client: TestClient):
    """TEST M: Single-use invite token cannot be accepted twice -> 400."""
    token_owner, _, tenant = register_user(client, "owner_m@example.com")
    token_user, _, _ = register_user(client, "recipient_m@example.com")

    inv = client.post(
        f"/api/v1/tenants/{tenant['id']}/invites",
        json={"email": "recipient_m@example.com", "role": "member"},
        headers=auth_headers(token_owner),
    ).json()

    # First accept: succeeds
    r1 = client.post(
        f"/api/v1/invites/{inv['token']}/accept",
        headers=auth_headers(token_user),
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "accepted"

    # Second accept: fails!
    r2 = client.post(
        f"/api/v1/invites/{inv['token']}/accept",
        headers=auth_headers(token_user),
    )
    assert r2.status_code == 400
    assert "already been accepted" in r2.json()["detail"].lower()


# =========================================================================
# Concurrency Safety & Migration Regression Tests
# =========================================================================

def test_concurrent_last_owner_removal_prevents_zero_owners(client: TestClient, engine):
    """
    Verifies that two concurrent requests attempting to remove/demote the last two owners
    are serialized via database row-locking (with_for_update), ensuring that exactly one
    succeeds and at least one owner ALWAYS remains.
    """
    import threading
    from sqlalchemy.orm import sessionmaker

    token_owner1, user1, tenant = register_user(client, "owner1_conc@example.com")
    token_owner2, user2, _ = register_user(client, "owner2_conc@example.com")

    # Add user2 as a second owner of the tenant
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        m2 = Membership(
            tenant_id=tenant["id"],
            user_id=user2["id"],
            role="owner",
        )
        db.add(m2)
        db.commit()

    # Verify initial state: exactly 2 owners
    with SessionLocal() as db:
        initial_owners = db.query(Membership).filter(
            Membership.tenant_id == tenant["id"],
            Membership.role == "owner",
        ).count()
        assert initial_owners == 2

    barrier = threading.Barrier(2)
    results = []

    def remove_owner(token, target_id):
        # Create a fresh TestClient for each thread to ensure independent request context
        thread_client = TestClient(client.app)
        try:
            barrier.wait(timeout=5)
            r = thread_client.delete(
                f"/api/v1/tenants/{tenant['id']}/members/{target_id}",
                headers=auth_headers(token),
            )
            results.append((target_id, r.status_code, r.text))
        except Exception as e:
            results.append((target_id, 500, str(e)))

    t1 = threading.Thread(target=remove_owner, args=(token_owner1, user1["id"]))
    t2 = threading.Thread(target=remove_owner, args=(token_owner2, user2["id"]))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Assert results: exactly one 204 (success) and one 400 (blocked by last-owner protection)
    status_codes = sorted([r[1] for r in results])
    assert status_codes == [204, 400], f"Expected [204, 400], got {status_codes}. Details: {results}"

    # Verify final database state: exactly 1 owner remains
    with SessionLocal() as db:
        remaining_owners = db.query(Membership).filter(
            Membership.tenant_id == tenant["id"],
            Membership.role == "owner",
        ).count()
        assert remaining_owners == 1


def test_legacy_project_migration_and_access(client: TestClient, engine):
    """
    Verifies that a legacy project created before Phase 7 (backfilled to tenant_id=1)
    remains accessible to an authorized developer user and is protected against
    unauthorized cross-tenant access.
    """
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine)
    # Seed default tenant and a legacy project with tenant_id=1
    with SessionLocal() as db:
        default_tenant = db.get(Tenant, 1)
        if default_tenant is None:
            default_tenant = Tenant(id=1, name="Default Organization", slug="default")
            db.add(default_tenant)
            db.commit()

        legacy_proj = Project(
            name="Legacy Pre-Phase-7 Project",
            tenant_id=1,
            api_key="rg_live_legacy_secret_key",
        )
        db.add(legacy_proj)
        db.commit()
        db.refresh(legacy_proj)
        legacy_id = legacy_proj.id

    # Register initial developer user -> automatically inherits owner access to Default Organization
    token_dev, dev_user, _ = register_user(client, "dev_legacy_admin@example.com")

    # Verify authorized access via tenant route
    r_tenant = client.get(
        f"/api/v1/tenants/1/projects/{legacy_id}",
        headers=auth_headers(token_dev),
    )
    assert r_tenant.status_code == 200
    assert r_tenant.json()["id"] == legacy_id
    assert r_tenant.json()["name"] == "Legacy Pre-Phase-7 Project"

    # Verify authorized access via legacy project route
    r_proj = client.get(
        f"/api/v1/projects/{legacy_id}",
        headers=auth_headers(token_dev),
    )
    assert r_proj.status_code == 200
    assert r_proj.json()["id"] == legacy_id

    # Register an unauthorized user (belonging only to their own separate tenant)
    token_other, _, _ = register_user(client, "other_unrelated_user@example.com")

    # Unauthorized access must return 404
    r_unauth_tenant = client.get(
        f"/api/v1/tenants/1/projects/{legacy_id}",
        headers=auth_headers(token_other),
    )
    assert r_unauth_tenant.status_code == 404

    r_unauth_proj = client.get(
        f"/api/v1/projects/{legacy_id}",
        headers=auth_headers(token_other),
    )
    assert r_unauth_proj.status_code == 404


def test_sdk_api_key_ingestion_scenarios(client: TestClient):
    """
    Verifies SDK API key validation across all ingestion patterns:
    - valid key -> succeeds
    - wrong key -> rejected (401)
    - project A key + project B project ID -> rejected (401)
    """
    token_a, _, tenant_a = register_user(client, "sdk_owner_a@example.com")
    token_b, _, tenant_b = register_user(client, "sdk_owner_b@example.com")

    proj_a = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects",
        json={"name": "Project A"},
        headers=auth_headers(token_a),
    ).json()

    proj_b = client.post(
        f"/api/v1/tenants/{tenant_b['id']}/projects",
        json={"name": "Project B"},
        headers=auth_headers(token_b),
    ).json()

    import fakeredis
    from app.queue import EventQueue, get_queue
    fake_q = EventQueue(redis_client=fakeredis.FakeRedis(decode_responses=True))
    client.app.dependency_overrides[get_queue] = lambda: fake_q

    try:
        key_a = proj_a["api_key"]
        key_b = proj_b["api_key"]

        # 1. Single-event ingestion with valid key -> 201
        r_valid_single = client.post(
            f"/api/v1/projects/{proj_a['id']}/events",
            json={
                "exception_type": "ValueError",
                "message": "Valid key event",
                "stack_trace": "line 1 in file.py",
            },
            headers={"X-ReleaseGuard-Key": key_a},
        )
        assert r_valid_single.status_code == 201

        # 2. Single-event ingestion with wrong key -> 401
        r_wrong_single = client.post(
            f"/api/v1/projects/{proj_a['id']}/events",
            json={
                "exception_type": "ValueError",
                "message": "Wrong key event",
                "stack_trace": "line 1 in file.py",
            },
            headers={"X-ReleaseGuard-Key": "rg_live_invalid_garbage_key"},
        )
        assert r_wrong_single.status_code == 401

        # 3. Bulk ingestion with valid key -> 202
        r_valid_bulk = client.post(
            f"/api/v1/projects/{proj_a['id']}/events/bulk",
            json={
                "events": [
                    {
                        "exception_type": "KeyError",
                        "message": "Bulk valid event",
                        "stack_trace": "line 10 in worker.py",
                    }
                ]
            },
            headers={"X-ReleaseGuard-Key": key_a},
        )
        assert r_valid_bulk.status_code == 202

        # 4. Bulk ingestion with wrong key -> 401
        r_wrong_bulk = client.post(
            f"/api/v1/projects/{proj_a['id']}/events/bulk",
            json={
                "events": [
                    {
                        "exception_type": "KeyError",
                        "message": "Bulk wrong key",
                        "stack_trace": "line 10 in worker.py",
                    }
                ]
            },
            headers={"X-ReleaseGuard-Key": "rg_live_wrong_key"},
        )
        assert r_wrong_bulk.status_code == 401

        # 5. Project A key + Project B project ID -> 401
        r_cross_proj = client.post(
            f"/api/v1/projects/{proj_b['id']}/events",
            json={
                "exception_type": "RuntimeError",
                "message": "Cross-project spoof",
                "stack_trace": "line 5 in spoof.py",
            },
            headers={"X-ReleaseGuard-Key": key_a},
        )
        assert r_cross_proj.status_code == 401
    finally:
        client.app.dependency_overrides.pop(get_queue, None)
