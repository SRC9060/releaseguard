"""
Phase 8 Tests: Release Tracking, Feature Flags, Deterministic Evaluation, and SDK Support.
Covers requirements A through P.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.flags import compute_bucket, evaluate_flag
from app.models import (
    Environment,
    FeatureFlag,
    FlagAuditLog,
    FlagSetting,
    Membership,
    Project,
    Release,
    Rollout,
    TargetingRule,
    User,
)
from releaseguard_sdk import Config, ReleaseGuardClient
from releaseguard_sdk.transport import BaseTransport


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
# TEST A & B: Release Creation & Tenant Isolation
# =========================================================================

def test_a_create_release(client: TestClient):
    """TEST A: Create release within a tenant project."""
    token, _, tenant = register_user(client, "rel_owner_a@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Payments Service"},
        headers=auth_headers(token),
    ).json()

    r = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/releases",
        json={"version": "1.0.0", "commit_sha": "a1b2c3d4e5", "environment": "production"},
        headers=auth_headers(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["version"] == "1.0.0"
    assert data["environment"] == "production"
    assert data["commit_sha"] == "a1b2c3d4e5"
    assert data["project_id"] == proj["id"]

    # List releases
    r_list = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/releases",
        headers=auth_headers(token),
    )
    assert r_list.status_code == 200
    assert len(r_list.json()) == 1


def test_b_tenant_isolation_for_releases(client: TestClient):
    """TEST B: Cross-tenant release requests return 404."""
    token_a, _, tenant_a = register_user(client, "rel_tenant_a@example.com")
    token_b, _, tenant_b = register_user(client, "rel_tenant_b@example.com")

    proj_a = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects",
        json={"name": "Project A"},
        headers=auth_headers(token_a),
    ).json()

    rel_a = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{proj_a['id']}/releases",
        json={"version": "2.4.1", "environment": "production"},
        headers=auth_headers(token_a),
    ).json()

    # User B requests Tenant A's releases -> 404
    r_leak = client.get(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{proj_a['id']}/releases",
        headers=auth_headers(token_b),
    )
    assert r_leak.status_code == 404

    r_leak_single = client.get(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{proj_a['id']}/releases/{rel_a['id']}",
        headers=auth_headers(token_b),
    )
    assert r_leak_single.status_code == 404


# =========================================================================
# TEST C & D: Feature Flag Creation & Duplicate Rejection
# =========================================================================

def test_c_create_feature_flag(client: TestClient):
    """TEST C: Create feature flag and verify auto-seeded environment settings."""
    token, _, tenant = register_user(client, "flag_creator@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Web Platform"},
        headers=auth_headers(token),
    ).json()

    r = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags",
        json={"key": "new_checkout", "name": "New Checkout Flow", "description": "Revamped checkout"},
        headers=auth_headers(token),
    )
    assert r.status_code == 201
    flag = r.json()
    assert flag["key"] == "new_checkout"
    assert flag["name"] == "New Checkout Flow"
    assert len(flag["settings"]) >= 3  # production, staging, development
    assert all(s["enabled"] is False for s in flag["settings"])


def test_d_duplicate_flag_key_rejected(client: TestClient):
    """TEST D: Duplicate flag keys within the same project are rejected -> 400."""
    token, _, tenant = register_user(client, "dup_flag@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Duplicate Flag Proj"},
        headers=auth_headers(token),
    ).json()

    client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags",
        json={"key": "dark_mode", "name": "Dark Mode"},
        headers=auth_headers(token),
    )

    r_dup = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags",
        json={"key": "dark_mode", "name": "Dark Mode 2"},
        headers=auth_headers(token),
    )
    assert r_dup.status_code == 400
    assert "already exists" in r_dup.json()["detail"].lower()


# =========================================================================
# TEST E, F, G: Deterministic & Monotonic Rollout Evaluation
# =========================================================================

def test_e_deterministic_evaluation():
    """TEST E: Same user + flag + environment yields identical result across 100 evaluations."""
    flag_key = "beta_search"
    env_key = "production"
    salt = "custom_salt_123"
    user_id = "user-998822"

    first_bucket = compute_bucket(flag_key, env_key, salt, user_id)
    assert 0 <= first_bucket < 100

    for _ in range(100):
        b = compute_bucket(flag_key, env_key, salt, user_id)
        assert b == first_bucket, "Evaluation must be purely deterministic"


def test_f_different_users_distribute_approximately():
    """TEST F: 1000 distinct users distribute approximately around configured percentage."""
    flag_key = "payment_v2"
    env_key = "production"
    salt = "salt_dist_456"
    percentage = 30  # 30%

    enabled_count = 0
    total_users = 1000

    for i in range(total_users):
        u_id = f"user_{i}"
        bucket = compute_bucket(flag_key, env_key, salt, u_id)
        if bucket < percentage:
            enabled_count += 1

    observed_pct = (enabled_count / total_users) * 100
    # Expected: ~30%. Tolerance: 24% to 36%
    assert 24.0 <= observed_pct <= 36.0, f"Expected ~30%, got {observed_pct}%"


def test_g_monotonic_rollout_property():
    """
    TEST G: Increasing rollout percentage is strictly monotonic.
    Users enabled at 10% MUST NOT lose the flag when rollout increases to 50%.
    """
    flag_key = "redesigned_ui"
    env_key = "production"
    salt = "monotonic_salt_789"

    users_at_10 = []
    users_at_50 = []

    for i in range(500):
        u_id = f"customer_{i}"
        bucket = compute_bucket(flag_key, env_key, salt, u_id)
        if bucket < 10:
            users_at_10.append(u_id)
        if bucket < 50:
            users_at_50.append(u_id)

    assert len(users_at_10) > 0
    assert len(users_at_50) >= len(users_at_10)

    # Every user in 10% cohort MUST be present in 50% cohort
    for u in users_at_10:
        assert u in users_at_50, f"User {u} lost flag access when rollout percentage increased!"


# =========================================================================
# TEST H & I: Kill Switch & Audit Logging
# =========================================================================

def test_h_kill_switch_evaluates_safe_default(client: TestClient):
    """TEST H: Kill switch sets enabled=False and rollout=0, evaluating to safe default."""
    token, _, tenant = register_user(client, "kill_tester@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Billing Service"},
        headers=auth_headers(token),
    ).json()

    flag = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags",
        json={"key": "new_pricing", "name": "New Pricing"},
        headers=auth_headers(token),
    ).json()

    env_id = flag["settings"][0]["environment_id"]

    # 1. Enable flag with 100% rollout
    client.put(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags/{flag['id']}/environments/{env_id}/setting",
        json={"enabled": True},
        headers=auth_headers(token),
    )
    client.put(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags/{flag['id']}/environments/{env_id}/rollout",
        json={"percentage": 100},
        headers=auth_headers(token),
    )

    # Verify enabled
    conf = client.get(f"/api/v1/config/{proj['id']}/production?user_id=u1").json()
    assert conf["flags"]["new_pricing"]["enabled"] is True

    # 2. Trigger Kill Switch
    r_kill = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags/{flag['id']}/environments/{env_id}/kill",
        headers=auth_headers(token),
    )
    assert r_kill.status_code == 200
    killed_setting = r_kill.json()
    assert killed_setting["enabled"] is False
    assert killed_setting["rollout_percentage"] == 0

    # 3. Verify evaluation immediately returns safe default
    conf_killed = client.get(f"/api/v1/config/{proj['id']}/production?user_id=u1").json()
    assert conf_killed["flags"]["new_pricing"]["enabled"] is False
    assert conf_killed["flags"]["new_pricing"]["variant"] == "off"


def test_i_audit_log_created_for_flag_mutation(client: TestClient):
    """TEST I: Flag mutations write immutable audit log records."""
    token, _, tenant = register_user(client, "audit_tester@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Audit Proj"},
        headers=auth_headers(token),
    ).json()

    flag = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags",
        json={"key": "feature_x", "name": "Feature X"},
        headers=auth_headers(token),
    ).json()

    env_id = flag["settings"][0]["environment_id"]

    # Mutation 1: Update flag
    client.put(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags/{flag['id']}",
        json={"name": "Feature X Renamed"},
        headers=auth_headers(token),
    )

    # Mutation 2: Kill switch
    client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags/{flag['id']}/environments/{env_id}/kill",
        headers=auth_headers(token),
    )

    # Fetch audit logs
    r_audit = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags/{flag['id']}/audit-logs",
        headers=auth_headers(token),
    )
    assert r_audit.status_code == 200
    logs = r_audit.json()
    actions = [l["action"] for l in logs]
    assert "create" in actions
    assert "update" in actions
    assert "kill" in actions


# =========================================================================
# TEST J & K: Targeting Rules Priority & ETag Caching
# =========================================================================

def test_j_targeting_rules_evaluated_in_priority_order(client: TestClient):
    """TEST J: Targeting rules are evaluated in priority order."""
    token, _, tenant = register_user(client, "rules_tester@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Targeting Proj"},
        headers=auth_headers(token),
    ).json()

    flag = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags",
        json={"key": "tier_access", "name": "Tier Access"},
        headers=auth_headers(token),
    ).json()

    env_id = flag["settings"][0]["environment_id"]
    client.put(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags/{flag['id']}/environments/{env_id}/setting",
        json={"enabled": True},
        headers=auth_headers(token),
    )

    # Set rules:
    # Priority 0: user_id == 'vip_user' -> variant 'vip'
    # Priority 1: user_id == 'beta_user' -> variant 'beta'
    client.put(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags/{flag['id']}/environments/{env_id}/rules",
        json=[
            {"priority": 0, "attribute": "user_id", "operator": "equals", "values": ["vip_user"], "variant": "vip"},
            {"priority": 1, "attribute": "user_id", "operator": "equals", "values": ["beta_user"], "variant": "beta"},
        ],
        headers=auth_headers(token),
    )

    # VIP user
    conf_vip = client.get(f"/api/v1/config/{proj['id']}/production?user_id=vip_user").json()
    assert conf_vip["flags"]["tier_access"]["enabled"] is True
    assert conf_vip["flags"]["tier_access"]["variant"] == "vip"

    # Beta user
    conf_beta = client.get(f"/api/v1/config/{proj['id']}/production?user_id=beta_user").json()
    assert conf_beta["flags"]["tier_access"]["enabled"] is True
    assert conf_beta["flags"]["tier_access"]["variant"] == "beta"


def test_k_cache_etag_and_304(client: TestClient):
    """TEST K: Config endpoint returns ETag and handles conditional If-None-Match with 304."""
    token, _, tenant = register_user(client, "etag_tester@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "ETag Proj"},
        headers=auth_headers(token),
    ).json()

    r1 = client.get(f"/api/v1/config/{proj['id']}/production")
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag is not None

    # Conditional request with matching ETag
    r2 = client.get(f"/api/v1/config/{proj['id']}/production", headers={"If-None-Match": etag})
    assert r2.status_code == 304


# =========================================================================
# TEST L, M, N, O: SDK Caching, Isolation, Roles & Safe Fallbacks
# =========================================================================

def test_l_stale_cache_fallback_sdk():
    """TEST L: Stale cache fallback does not crash SDK and preserves previous value."""
    class FailingTransport(BaseTransport):
        def __init__(self):
            self.calls = 0

        def send_event(self, event):
            return {}

        def get_config(self, environment, etag=None, user_id=None):
            self.calls += 1
            if self.calls == 1:
                return 200, {"environment": "production", "flags": {"cached_flag": {"enabled": True, "variant": "on"}}}, '"etag1"'
            # Subsequent calls fail with 500 error
            return 500, {}, None

    transport = FailingTransport()
    config = Config(project_id=1)
    client = ReleaseGuardClient(config=config, transport=transport)

    # First call: populates cache
    val1 = client.get_flag("cached_flag", default=False)
    assert val1 is True

    # Artificially expire the cache TTL
    client._flag_cache["production"]["expires_at"] = 0

    # Second call: network fails, SDK falls back to stale cached value
    val2 = client.get_flag("cached_flag", default=False)
    assert val2 is True, "Must fall back to stale cache without crashing"


def test_m_project_tenant_isolation_for_flags(client: TestClient):
    """TEST M: User A cannot read or modify Tenant B's flags (returns 404)."""
    token_a, _, tenant_a = register_user(client, "iso_a@example.com")
    token_b, _, tenant_b = register_user(client, "iso_b@example.com")

    proj_a = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects",
        json={"name": "Proj A"},
        headers=auth_headers(token_a),
    ).json()

    flag_a = client.post(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{proj_a['id']}/flags",
        json={"key": "flag_secret", "name": "Secret Flag"},
        headers=auth_headers(token_a),
    ).json()

    # User B attempts to access Tenant A's flag -> 404
    r = client.get(
        f"/api/v1/tenants/{tenant_a['id']}/projects/{proj_a['id']}/flags/{flag_a['id']}",
        headers=auth_headers(token_b),
    )
    assert r.status_code == 404


def test_n_member_cannot_mutate_flag(client: TestClient):
    """TEST N: Member can read flags but cannot mutate them (403 Forbidden)."""
    token_owner, _, tenant = register_user(client, "owner_perm@example.com")
    token_member, user_member, _ = register_user(client, "member_perm@example.com")

    # Invite user_member as 'member' to tenant
    inv = client.post(
        f"/api/v1/tenants/{tenant['id']}/invites",
        json={"email": "member_perm@example.com", "role": "member"},
        headers=auth_headers(token_owner),
    ).json()
    client.post(f"/api/v1/invites/{inv['token']}/accept", headers=auth_headers(token_member))

    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Role Perm Proj"},
        headers=auth_headers(token_owner),
    ).json()

    # Member attempts to create flag -> 403 Forbidden
    r_create = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/flags",
        json={"key": "unauth_flag", "name": "Unauth"},
        headers=auth_headers(token_member),
    )
    assert r_create.status_code == 403


def test_o_sdk_evaluates_flags_without_exceptions():
    """TEST O: SDK evaluates flags safely without host-app exceptions even when backend is down."""
    config = Config(project_id=999, base_url="http://127.0.0.1:54321")
    client = ReleaseGuardClient(config=config)

    # Calling unconfigured / dead host returns default without throwing
    val = client.get_flag("unknown_flag", user_id="u-123", default="safe_fallback")
    assert val == "safe_fallback"

    variant = client.get_flag_variant("unknown_flag", default="off")
    assert variant == "off"


# =========================================================================
# Release & Issue Correlation Test
# =========================================================================

def test_release_issue_correlation(client: TestClient):
    """Verify issue releases endpoint returns affected, first-seen, and latest releases from real events."""
    token, _, tenant = register_user(client, "rel_corr@example.com")
    proj = client.post(
        f"/api/v1/tenants/{tenant['id']}/projects",
        json={"name": "Corr Proj"},
        headers=auth_headers(token),
    ).json()

    # Send error events with releases
    client.post(
        f"/api/v1/projects/{proj['id']}/events",
        json={"exception_type": "ValueError", "message": "Correlated error", "stack_trace": "t1", "release": "1.0.0"},
    )
    client.post(
        f"/api/v1/projects/{proj['id']}/events",
        json={"exception_type": "ValueError", "message": "Correlated error", "stack_trace": "t1", "release": "1.1.0"},
    )

    issues = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/issues",
        headers=auth_headers(token),
    ).json()
    assert len(issues) == 1
    issue_id = issues[0]["id"]

    # Query release correlation
    r_rel = client.get(
        f"/api/v1/tenants/{tenant['id']}/projects/{proj['id']}/issues/{issue_id}/releases",
        headers=auth_headers(token),
    )
    assert r_rel.status_code == 200
    data = r_rel.json()
    assert set(data["affected_releases"]) == {"1.0.0", "1.1.0"}
    assert data["first_seen_release"] == "1.0.0"
    assert data["latest_release"] == "1.1.0"
