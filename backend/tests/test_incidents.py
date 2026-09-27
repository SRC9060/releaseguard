"""
Phase 9 Tests: Incident Response, Timeline, Error Spike Detection, Release/Flag Correlation,
and Explicit Controlled Mitigation.
"""

from datetime import datetime, timedelta, timezone
import json
import uuid
import pytest
from fastapi.testclient import TestClient

from app.incidents import CorrelationService, MitigationService, SpikeDetectionService
from app.models import (
    Environment,
    ErrorEvent,
    FeatureFlag,
    FlagAuditLog,
    FlagSetting,
    Incident,
    IncidentEvent,
    IncidentMitigation,
    Issue,
    Membership,
    Project,
    Release,
    Rollout,
    User,
    utcnow,
)


def register_user(client: TestClient, email: str, password: str = "password123"):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 201
    data = resp.json()
    token = data["access_token"]
    user = data["user"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    tenant = me["tenants"][0]
    return token, user, tenant


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# 1. Incident Creation & Retrieval
# =========================================================================

def test_a_create_incident(client: TestClient):
    token, _, tenant = register_user(client, "inc_owner_a@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Billing Service"},
        headers=auth_headers(token),
    ).json()

    resp = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={
            "title": "Payment Gateway 504 Surge",
            "description": "Observed rapid spike in gateway timeout errors.",
            "severity": "high",
            "environment": "production",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Payment Gateway 504 Surge"
    assert data["severity"] == "high"
    assert data["status"] == "triggered"
    assert data["environment"] == "production"
    assert len(data["timeline"]) >= 1
    assert data["timeline"][0]["event_type"] == "incident_created"


def test_b_tenant_isolation_for_incidents(client: TestClient):
    # Tenant A creates incident
    token_a, _, tenant_a = register_user(client, "tenant_a_user@example.com")
    proj_a = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects",
        json={"name": "Tenant A Project"},
        headers=auth_headers(token_a),
    ).json()

    inc_a = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{proj_a['id']}/incidents",
        json={"title": "Internal Outage A", "severity": "critical"},
        headers=auth_headers(token_a),
    ).json()

    # Tenant B attempts access
    token_b, _, tenant_b = register_user(client, "tenant_b_user@example.com")

    # Access across tenants must return 404
    resp = client.get(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{proj_a['id']}/incidents/{inc_a['id']}",
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404

    # Using Tenant B's tenant_id with Tenant A's project_id returns 404
    resp2 = client.get(
        f"/api/v1/tenants/{tenant_b['id']}/projects/{proj_a['id']}/incidents/{inc_a['id']}",
        headers=auth_headers(token_b),
    )
    assert resp2.status_code == 404


def test_c_rbac_incident_mutations(client: TestClient, db_session):
    # Owner creates project & incident
    token_owner, owner_user, tenant = register_user(client, "inc_rbac_owner@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Auth Service"},
        headers=auth_headers(token_owner),
    ).json()

    inc = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={"title": "High Latency Incident", "severity": "medium"},
        headers=auth_headers(token_owner),
    ).json()

    # Create Member user
    token_member, member_user, _ = register_user(client, "inc_rbac_member@example.com")
    # Add member_user to tenant with role 'member'
    mem = Membership(tenant_id=tenant["id"], user_id=member_user["id"], role="member")
    db_session.add(mem)
    db_session.commit()

    # Member CAN read incident and timeline
    r_get = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}",
        headers=auth_headers(token_member),
    )
    assert r_get.status_code == 200

    # Member CANNOT update incident status (requires admin/owner)
    r_patch = client.patch(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}",
        json={"status": "resolved"},
        headers=auth_headers(token_member),
    )
    assert r_patch.status_code == 403

    # Owner CAN update incident status
    r_patch_owner = client.patch(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}",
        json={"status": "investigating"},
        headers=auth_headers(token_owner),
    )
    assert r_patch_owner.status_code == 200
    assert r_patch_owner.json()["status"] == "investigating"


def test_d_incident_filtering(client: TestClient):
    token, _, tenant = register_user(client, "inc_filter@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Reporting Service"},
        headers=auth_headers(token),
    ).json()

    client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={"title": "Prod Critical", "severity": "critical", "environment": "production"},
        headers=auth_headers(token),
    )
    client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={"title": "Staging Minor", "severity": "low", "environment": "staging"},
        headers=auth_headers(token),
    )

    # Filter by environment
    prod_only = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents?environment=production",
        headers=auth_headers(token),
    ).json()
    assert len(prod_only) == 1
    assert prod_only[0]["title"] == "Prod Critical"

    # Filter by severity
    crit_only = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents?severity=critical",
        headers=auth_headers(token),
    ).json()
    assert len(crit_only) == 1
    assert crit_only[0]["title"] == "Prod Critical"


def test_e_lifecycle_transitions(client: TestClient):
    token, _, tenant = register_user(client, "inc_lifecycle@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Order Service"},
        headers=auth_headers(token),
    ).json()

    inc = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={"title": "Deadlock Surge", "severity": "high"},
        headers=auth_headers(token),
    ).json()
    assert inc["status"] == "triggered"

    # 1. Investigating
    r1 = client.patch(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}",
        json={"status": "investigating"},
        headers=auth_headers(token),
    ).json()
    assert r1["status"] == "investigating"

    # 2. Resolved
    r2 = client.patch(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}",
        json={"status": "resolved"},
        headers=auth_headers(token),
    ).json()
    assert r2["status"] == "resolved"
    assert r2["resolved_at"] is not None

    # 3. Closed
    r3 = client.patch(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}",
        json={"status": "closed"},
        headers=auth_headers(token),
    ).json()
    assert r3["status"] == "closed"
    assert r3["closed_at"] is not None


def test_f_timeline_note_creation(client: TestClient):
    token, _, tenant = register_user(client, "inc_timeline@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Search API"},
        headers=auth_headers(token),
    ).json()

    inc = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={"title": "Slow Query Outage", "severity": "medium"},
        headers=auth_headers(token),
    ).json()

    # Add note
    r_note = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/timeline",
        json={"message": "Identified database locking on users table", "event_type": "note_added"},
        headers=auth_headers(token),
    )
    assert r_note.status_code == 201

    timeline = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc['id']}/timeline",
        headers=auth_headers(token),
    ).json()
    assert len(timeline) >= 2
    types = [t["event_type"] for t in timeline]
    assert "incident_created" in types
    assert "note_added" in types


# =========================================================================
# 2. Error Spike Detection & Duplicate Prevention
# =========================================================================

def test_g_spike_detection_service(client: TestClient, db_session):
    token, _, tenant = register_user(client, "spike_user@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Worker Node"},
        headers=auth_headers(token),
    ).json()

    now = utcnow()
    # Create Issue
    issue = Issue(
        project_id=proj["id"],
        fingerprint="fp_spike_test",
        title="NullPointer in OrderProcessor",
        count=11,
        status="unresolved",
        first_seen=now - timedelta(minutes=45),
        last_seen=now,
    )
    db_session.add(issue)
    db_session.commit()

    # Add 1 event in baseline window (30m ago)
    ev_baseline = ErrorEvent(
        event_id=str(uuid.uuid4()),
        project_id=proj["id"],
        issue_id=issue.id,
        exception_type="NullPointerException",
        message="baseline error",
        stack_trace="trace",
        received_at=now - timedelta(minutes=30),
    )
    db_session.add(ev_baseline)

    # Add 10 events in current window (last 10m)
    for _ in range(10):
        ev = ErrorEvent(
            event_id=str(uuid.uuid4()),
            project_id=proj["id"],
            issue_id=issue.id,
            exception_type="NullPointerException",
            message="spike error",
            stack_trace="trace",
            received_at=now - timedelta(minutes=2),
        )
        db_session.add(ev)
    db_session.commit()

    res = SpikeDetectionService.detect_spike(
        issue_id=issue.id,
        project_id=proj["id"],
        environment="production",
        current_window_minutes=15,
        baseline_window_minutes=60,
        min_current_events=5,
        spike_ratio_threshold=2.0,
        now=now,
        db=db_session,
    )

    assert res["is_spike"] is True
    assert res["current_count"] == 10
    assert res["baseline_count"] == 1
    assert res["spike_ratio"] > 2.0


def test_h_duplicate_incident_prevention(client: TestClient, db_session):
    token, _, tenant = register_user(client, "dup_prevent@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Inventory Service"},
        headers=auth_headers(token),
    ).json()

    now = utcnow()
    issue = Issue(
        project_id=proj["id"],
        fingerprint="fp_dup_test",
        title="OutOfMemoryError in CachingLayer",
        count=1,
        status="unresolved",
        first_seen=now,
        last_seen=now,
    )
    db_session.add(issue)
    db_session.commit()

    # Initially not duplicate
    is_dup1 = SpikeDetectionService.is_duplicate_incident(
        issue_id=issue.id,
        project_id=proj["id"],
        environment="production",
        cooldown_minutes=60,
        now=now,
        db=db_session,
    )
    assert is_dup1 is False

    # Create active incident
    inc = Incident(
        tenant_id=tenant["id"],
        project_id=proj["id"],
        environment="production",
        title="OOM Incident",
        severity="critical",
        status="triggered",
        related_issue_id=issue.id,
        started_at=now,
        created_at=now,
    )
    db_session.add(inc)
    db_session.commit()

    # Now within cooldown it must report duplicate
    is_dup2 = SpikeDetectionService.is_duplicate_incident(
        issue_id=issue.id,
        project_id=proj["id"],
        environment="production",
        cooldown_minutes=60,
        now=now + timedelta(minutes=10),
        db=db_session,
    )
    assert is_dup2 is True


# =========================================================================
# 3. Release & Flag Correlation
# =========================================================================

def test_i_release_correlation(client: TestClient, db_session):
    token, _, tenant = register_user(client, "correlate_rel@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Gateway Service"},
        headers=auth_headers(token),
    ).json()

    now = utcnow()
    # Create recent release
    rel = Release(
        project_id=proj["id"],
        version="3.1.0",
        commit_sha="c0ffee123",
        environment="production",
        created_at=now - timedelta(hours=2),
    )
    db_session.add(rel)

    # Create issue with error event matching version 3.1.0
    issue = Issue(
        project_id=proj["id"],
        fingerprint="fp_gateway_timeout",
        title="ConnectionResetError",
        count=1,
        status="unresolved",
        first_seen=now,
        last_seen=now,
    )
    db_session.add(issue)
    db_session.flush()

    ev = ErrorEvent(
        event_id=str(uuid.uuid4()),
        project_id=proj["id"],
        issue_id=issue.id,
        exception_type="ConnectionResetError",
        message="connection reset by peer",
        stack_trace="trace",
        release="3.1.0",
        received_at=now,
    )
    db_session.add(ev)
    db_session.commit()

    changes = CorrelationService.find_correlated_changes(
        project_id=proj["id"],
        environment="production",
        reference_time=now,
        lookback_hours=24,
        issue_id=issue.id,
        db=db_session,
    )

    assert len(changes) >= 1
    rel_change = next(c for c in changes if c["type"] == "release")
    assert rel_change["metadata"]["version"] == "3.1.0"
    assert "correlated release" in rel_change["relationship"]
    assert rel_change["metadata"]["matched_in_error_events"] is True


def test_j_flag_correlation(client: TestClient, db_session):
    token, _, tenant = register_user(client, "correlate_flag@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Checkout API"},
        headers=auth_headers(token),
    ).json()

    now = utcnow()
    # Create Flag
    flag = FeatureFlag(
        project_id=proj["id"],
        key="v2_crypto_payments",
        name="V2 Crypto Payments",
        created_at=now - timedelta(hours=3),
    )
    db_session.add(flag)
    db_session.flush()

    # Create FlagAuditLog representing a recent rollout increase
    audit = FlagAuditLog(
        flag_id=flag.id,
        environment_id=None,
        action="update_rollout",
        before_state=json.dumps({"rollout_percentage": 0}),
        after_state=json.dumps({"rollout_percentage": 50}),
        created_at=now - timedelta(hours=1),
    )
    db_session.add(audit)
    db_session.commit()

    changes = CorrelationService.find_correlated_changes(
        project_id=proj["id"],
        environment="production",
        reference_time=now,
        lookback_hours=24,
        db=db_session,
    )

    flag_change = next(c for c in changes if c["type"] == "feature_flag")
    assert flag_change["metadata"]["flag_key"] == "v2_crypto_payments"
    assert "possible contributor" in flag_change["relationship"] or "recent flag change" in flag_change["relationship"]


# =========================================================================
# 4. Mitigation Recommendation & Controlled Approval
# =========================================================================

def test_k_mitigation_recommendation_and_approval(client: TestClient, db_session):
    token, owner_user, tenant = register_user(client, "mitig_approval@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Recommendation Service"},
        headers=auth_headers(token),
    ).json()

    # 1. Setup Environment
    env = Environment(project_id=proj["id"], key="production", name="Production")
    db_session.add(env)
    db_session.flush()

    # 2. Setup Flag with active Rollout
    flag = FeatureFlag(project_id=proj["id"], key="new_recs_algo", name="New Recommendations")
    db_session.add(flag)
    db_session.flush()

    setting = FlagSetting(flag_id=flag.id, environment_id=env.id, enabled=True, default_variant="off")
    db_session.add(setting)
    db_session.flush()

    rollout = Rollout(setting_id=setting.id, flag_id=flag.id, environment_id=env.id, percentage=75)
    db_session.add(rollout)

    # Audit log 30m ago
    audit = FlagAuditLog(
        flag_id=flag.id,
        environment_id=env.id,
        actor_id=owner_user["id"],
        action="update_rollout",
        created_at=utcnow() - timedelta(minutes=30),
    )
    db_session.add(audit)
    db_session.commit()

    # 3. Create Incident
    inc_resp = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents",
        json={
            "title": "Recs Latency Spike",
            "severity": "high",
            "environment": "production",
            "related_feature_flag_id": flag.id,
        },
        headers=auth_headers(token),
    )
    assert inc_resp.status_code == 201
    inc_data = inc_resp.json()

    # Advisory recommendation must be present
    assert len(inc_data["mitigations"]) >= 1
    mitig = inc_data["mitigations"][0]
    assert mitig["action_type"] == "kill_feature_flag"
    assert mitig["target_flag_key"] == "new_recs_algo"
    assert mitig["status"] == "pending"
    assert mitig["confidence"] >= 0.70

    # 4. Member CANNOT approve mitigation (HTTP 403)
    token_member, member_user, _ = register_user(client, "mitig_member_unauth@example.com")
    db_session.add(Membership(tenant_id=tenant["id"], user_id=member_user["id"], role="member"))
    db_session.commit()

    r_unauth = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc_data['id']}/mitigations/{mitig['id']}/approve",
        headers=auth_headers(token_member),
    )
    assert r_unauth.status_code == 403

    # 5. Owner APPROVES mitigation
    r_approve = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc_data['id']}/mitigations/{mitig['id']}/approve",
        headers=auth_headers(token),
    )
    assert r_approve.status_code == 200
    exec_data = r_approve.json()
    assert exec_data["status"] == "executed"
    assert exec_data["idempotent"] is False

    # Verify Flag Setting was killed safely
    db_session.expire_all()
    updated_setting = db_session.query(FlagSetting).filter(FlagSetting.id == setting.id).first()
    assert updated_setting.enabled is False
    assert updated_setting.rollout.percentage == 0

    # Verify Flag Audit Log record created
    kill_audit = (
        db_session.query(FlagAuditLog)
        .filter(FlagAuditLog.flag_id == flag.id, FlagAuditLog.action == "kill")
        .first()
    )
    assert kill_audit is not None
    assert kill_audit.actor_id == owner_user["id"]

    # Verify Incident status is 'mitigated'
    updated_inc = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc_data['id']}",
        headers=auth_headers(token),
    ).json()
    assert updated_inc["status"] == "mitigated"
    assert updated_inc["mitigated_at"] is not None

    # 6. IDEMPOTENCY: Repeated approval does not re-execute or fail
    r_repeat = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/incidents/{inc_data['id']}/mitigations/{mitig['id']}/approve",
        headers=auth_headers(token),
    )
    assert r_repeat.status_code == 200
    repeat_data = r_repeat.json()
    assert repeat_data["status"] == "executed"
    assert repeat_data["idempotent"] is True
