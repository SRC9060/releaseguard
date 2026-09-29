"""
Phase 14 Tests: Production-Grade Incident Management & Mitigation Workflow.
Covers:
- Incident creation with open/monitoring/resolved status and project scoping
- Multi-tenancy and project isolation guarantees
- RBAC enforcement (member read-only, admin/owner mutations)
- Status and severity transitions, including resolve endpoint
- Incident ↔ Issue linking, unlinking, duplicate prevention, and cross-project rejection
- Incident timeline/activity audit trail
- Mitigation execution: flag kill-switch (enabled=False, rollout=0%) and reversible rollback
- Mitigation audit logging and previous_state restoration
"""

import json
import pytest
from fastapi.testclient import TestClient

from app.models import FeatureFlag, FlagAuditLog, FlagSetting, Issue, Membership, Rollout, utcnow


def register_user(client: TestClient, email: str, password: str = "password123"):
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201
    data = resp.json()
    token = data["access_token"]
    user = data["user"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    tenant = me["tenants"][0]
    return token, user, tenant


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def setup_project(client: TestClient, db_session):
    owner_token, owner_user, tenant = register_user(client, "phase14_owner@example.com")
    member_token, member_user, _ = register_user(client, "phase14_member@example.com")

    # Add member_user directly to tenant with role="member"
    mem = Membership(tenant_id=tenant["id"], user_id=member_user["id"], role="member")
    db_session.add(mem)
    db_session.commit()

    # Create project
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Core Payments Service"},
        headers=auth_headers(owner_token),
    ).json()

    return owner_token, member_token, tenant, proj


def test_incident_creation_and_project_scoping(client: TestClient, db_session):
    owner_token, _, tenant, proj = setup_project(client, db_session)

    resp = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={
            "title": "Payment Processing Degradation",
            "description": "High failure rate on Stripe webhook processor.",
            "severity": "high",
            "status": "open",
            "environment": "production",
        },
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Payment Processing Degradation"
    assert data["severity"] == "high"
    assert data["status"] == "open"
    assert data["project_id"] == proj["id"]
    assert data["tenant_id"] == tenant["id"]
    assert data["started_at"] is not None
    assert data["resolved_at"] is None
    assert len(data["timeline"]) >= 1
    assert data["timeline"][0]["event_type"] == "incident_created"


def test_tenant_and_project_isolation(client: TestClient, db_session):
    token_a, _, tenant_a = register_user(client, "phase14_iso_a@example.com")
    token_b, _, tenant_b = register_user(client, "phase14_iso_b@example.com")

    proj_a = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects",
        json={"name": "Project Alpha"},
        headers=auth_headers(token_a),
    ).json()

    proj_b = client.post(
        f"/api/v1/tenants/{tenant_b['id']}/projects",
        json={"name": "Project Beta"},
        headers=auth_headers(token_b),
    ).json()

    inc_a = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{proj_a['id']}/incidents",
        json={"title": "Alpha Incident", "severity": "medium", "status": "open"},
        headers=auth_headers(token_a),
    ).json()

    # User B in Tenant B attempts to read Incident A -> 404 or 403 Forbidden
    res = client.get(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{proj_a['id']}/incidents/{inc_a['id']}",
        headers=auth_headers(token_b),
    )
    assert res.status_code in [403, 404]

    # User A cannot link a non-existent or other project's issue to Incident A
    link_res = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{proj_a['id']}/incidents/{inc_a['id']}/issues",
        json={"issue_id": 999999},
        headers=auth_headers(token_a),
    )
    assert link_res.status_code == 404


def test_rbac_incident_mutations(client: TestClient, db_session):
    owner_token, member_token, tenant, proj = setup_project(client, db_session)

    # Owner creates incident
    inc = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={"title": "Database Read Lock Contention", "severity": "critical", "status": "open"},
        headers=auth_headers(owner_token),
    ).json()

    # Member CAN read incident
    get_res = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}",
        headers=auth_headers(member_token),
    )
    assert get_res.status_code == 200

    # Member CANNOT patch incident -> 403 Forbidden
    patch_res = client.patch(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}",
        json={"severity": "low"},
        headers=auth_headers(member_token),
    )
    assert patch_res.status_code == 403

    # Member CANNOT resolve incident -> 403 Forbidden
    resolve_res = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/resolve",
        headers=auth_headers(member_token),
    )
    assert resolve_res.status_code == 403


def test_status_transitions_and_resolution(client: TestClient, db_session):
    owner_token, _, tenant, proj = setup_project(client, db_session)

    inc = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={"title": "Checkout Latency Spike", "severity": "high", "status": "open"},
        headers=auth_headers(owner_token),
    ).json()
    assert inc["status"] == "open"
    assert inc["resolved_at"] is None

    # Transition to monitoring
    m_res = client.patch(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}",
        json={"status": "monitoring"},
        headers=auth_headers(owner_token),
    )
    assert m_res.status_code == 200
    assert m_res.json()["status"] == "monitoring"

    # Explicit resolve endpoint
    r_res = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/resolve",
        headers=auth_headers(owner_token),
    )
    assert r_res.status_code == 200
    r_data = r_res.json()
    assert r_data["status"] == "resolved"
    assert r_data["resolved_at"] is not None

    # Verify timeline event
    tl = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/timeline",
        headers=auth_headers(owner_token),
    ).json()
    event_types = [e["event_type"] for e in tl]
    assert "incident_resolved" in event_types


def test_issue_linking_unlinking_and_duplicate_prevention(client: TestClient, db_session):
    owner_token, _, tenant, proj = setup_project(client, db_session)

    now = utcnow()
    # Create dummy issue directly in project
    issue = Issue(
        project_id=proj["id"],
        title="NullPointerException in OrderSync",
        fingerprint="fp_order_sync_123",
        status="unresolved",
        first_seen=now,
        last_seen=now,
    )
    db_session.add(issue)
    db_session.commit()
    db_session.refresh(issue)

    inc = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={"title": "Order Sync Failure", "severity": "critical", "status": "open"},
        headers=auth_headers(owner_token),
    ).json()
    assert inc["linked_issue_count"] == 0

    # 1. Link issue
    link_res = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/issues",
        json={"issue_id": issue.id},
        headers=auth_headers(owner_token),
    )
    assert link_res.status_code == 201
    updated_inc = link_res.json()
    assert updated_inc["linked_issue_count"] == 1
    assert updated_inc["linked_issues"][0]["issue_id"] == issue.id
    assert updated_inc["linked_issues"][0]["title"] == "NullPointerException in OrderSync"

    # 2. Duplicate link prevention (must return 400 Bad Request)
    dup_res = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/issues",
        json={"issue_id": issue.id},
        headers=auth_headers(owner_token),
    )
    assert dup_res.status_code == 400
    assert "already linked" in dup_res.json()["detail"].lower()

    # Verify timeline recorded issue_linked
    tl = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/timeline",
        headers=auth_headers(owner_token),
    ).json()
    assert any(e["event_type"] == "issue_linked" for e in tl)

    # 3. Unlink issue
    unlink_res = client.delete(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/issues/{issue.id}",
        headers=auth_headers(owner_token),
    )
    assert unlink_res.status_code == 200
    unlinked_inc = unlink_res.json()
    assert unlinked_inc["linked_issue_count"] == 0

    # Verify original issue is UNCHANGED in database
    db_session.refresh(issue)
    assert issue.id is not None
    assert issue.title == "NullPointerException in OrderSync"


def test_mitigation_apply_and_revert_with_audit_trail(client: TestClient, db_session):
    owner_token, member_token, tenant, proj = setup_project(client, db_session)

    # Get environment
    env_res = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/environments",
        headers=auth_headers(owner_token),
    ).json()
    prod_env = next(e for e in env_res if e["key"] == "production")

    # Create Feature Flag with enabled=True and rollout=75%
    flag = FeatureFlag(
        project_id=proj["id"],
        key="new_checkout_flow",
        name="New Checkout Flow",
    )
    db_session.add(flag)
    db_session.flush()

    setting = FlagSetting(
        flag_id=flag.id,
        environment_id=prod_env["id"],
        enabled=True,
        default_variant="on",
    )
    db_session.add(setting)
    db_session.flush()

    rollout = Rollout(
        setting_id=setting.id,
        flag_id=flag.id,
        environment_id=prod_env["id"],
        percentage=75,
    )
    db_session.add(rollout)
    db_session.commit()

    # Create Incident
    inc = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={"title": "High Cart Abandonment Rate", "severity": "high", "status": "open"},
        headers=auth_headers(owner_token),
    ).json()

    # Member CANNOT apply mitigation -> 403 Forbidden
    member_apply = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/mitigations",
        json={"target_flag_id": flag.id, "target_environment_id": prod_env["id"]},
        headers=auth_headers(member_token),
    )
    assert member_apply.status_code == 403

    # Owner applies mitigation
    apply_res = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/mitigations",
        json={"target_flag_id": flag.id, "target_environment_id": prod_env["id"], "reason": "Checkout regression"},
        headers=auth_headers(owner_token),
    )
    assert apply_res.status_code == 200
    mitigation_data = apply_res.json()
    assert mitigation_data["status"] == "executed"
    mitigation_id = mitigation_data["mitigation_id"]

    # Verify Flag Setting is actually disabled and rollout percentage is 0
    db_session.refresh(setting)
    db_session.refresh(rollout)
    assert setting.enabled is False
    assert rollout.percentage == 0

    # Verify FlagAuditLog was created with action="kill"
    audit = (
        db_session.query(FlagAuditLog)
        .filter(FlagAuditLog.flag_id == flag.id, FlagAuditLog.action == "kill")
        .first()
    )
    assert audit is not None
    before_state = json.loads(audit.before_state)
    assert before_state["enabled"] is True
    assert before_state["rollout_percentage"] == 75

    # Member CANNOT revert mitigation -> 403 Forbidden
    member_revert = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/mitigations/{mitigation_id}/revert",
        headers=auth_headers(member_token),
    )
    assert member_revert.status_code == 403

    # Owner reverts mitigation
    revert_res = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/mitigations/{mitigation_id}/revert",
        headers=auth_headers(owner_token),
    )
    assert revert_res.status_code == 200
    assert revert_res.json()["status"] == "reverted"

    # Verify Flag Setting and Rollout restored to exact pre-mitigation state
    db_session.refresh(setting)
    db_session.refresh(rollout)
    assert setting.enabled is True
    assert rollout.percentage == 75

    # Verify Revert FlagAuditLog was created
    revert_audit = (
        db_session.query(FlagAuditLog)
        .filter(FlagAuditLog.flag_id == flag.id, FlagAuditLog.action == "revert_mitigation")
        .first()
    )
    assert revert_audit is not None
    restored_after = json.loads(revert_audit.after_state)
    assert restored_after["enabled"] is True
    assert restored_after["rollout_percentage"] == 75
