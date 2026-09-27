"""
ReleaseGuard Deterministic Demo & Seed Script
Creates realistic, idempotent sample data for live demonstrations and testing:
- Demo Organization: Acme Corp (slug: acme-corp)
- Demo User: demo@releaseguard.dev (password: DemoPassword123!)
- Project: Checkout Service
- Environments: development, staging, production
- Releases: 1.0.0, 1.1.0, 1.2.0
- Feature Flags: new_checkout, new_payment_flow, experimental_dashboard
- Issues: DatabaseConnectionTimeout, PaymentGatewayError, AuthenticationError
- Incidents: Payment Gateway Surge, Database Error Spike with advisory mitigations
"""

from datetime import datetime, timedelta, timezone
import json
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.auth import hash_password
from app.db import SessionLocal
from app.fingerprint import make_fingerprint
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
    Tenant,
    User,
)


def seed_demo():
    print("=" * 70)
    print("ReleaseGuard - Deterministic Demo Data Seeding")
    print("=" * 70)

    db = SessionLocal()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        # 1. Tenant: Acme Corp
        tenant = db.query(Tenant).filter(Tenant.slug == "acme-corp").first()
        if not tenant:
            tenant = Tenant(name="Acme Corp", slug="acme-corp", created_at=now, updated_at=now)
            db.add(tenant)
            db.flush()
            print("[+] Created Demo Organization: Acme Corp (acme-corp)")
        else:
            print("[*] Demo Organization Acme Corp already exists.")

        # 2. User: demo@releaseguard.dev
        user = db.query(User).filter(User.email == "demo@releaseguard.dev").first()
        if not user:
            user = User(
                email="demo@releaseguard.dev",
                password_hash=hash_password("DemoPassword123!"),
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            db.add(user)
            db.flush()
            print("[+] Created Demo User: demo@releaseguard.dev (Password: DemoPassword123!)")
        else:
            print("[*] Demo User demo@releaseguard.dev already exists.")

        # 3. Membership: Owner
        membership = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant.id, Membership.user_id == user.id)
            .first()
        )
        if not membership:
            membership = Membership(tenant_id=tenant.id, user_id=user.id, role="owner", created_at=now)
            db.add(membership)
            db.flush()
            print("[+] Assigned Owner role to demo@releaseguard.dev in Acme Corp.")

        # 4. Project: Checkout Service
        project = (
            db.query(Project)
            .filter(Project.tenant_id == tenant.id, Project.name == "Checkout Service")
            .first()
        )
        if not project:
            project = Project(
                name="Checkout Service",
                tenant_id=tenant.id,
                api_key="rg_live_demo_checkout_service_key_99",
            )
            db.add(project)
            db.flush()
            print("[+] Created Project: Checkout Service (Key: rg_live_demo_checkout_service_key_99)")
        else:
            print("[*] Project Checkout Service already exists.")

        # 5. Environments
        env_specs = [
            ("development", "Development"),
            ("staging", "Staging"),
            ("production", "Production"),
        ]
        envs = {}
        for key, name in env_specs:
            env = (
                db.query(Environment)
                .filter(Environment.project_id == project.id, Environment.key == key)
                .first()
            )
            if not env:
                env = Environment(project_id=project.id, key=key, name=name, created_at=now)
                db.add(env)
                db.flush()
                print(f"[+] Created Environment: {name} ({key})")
            envs[key] = env

        # 6. Releases
        release_specs = [
            ("1.0.0", "a1b2c3d4e5f67890123456789012345678901234", "production"),
            ("1.1.0", "b2c3d4e5f6a17890123456789012345678901234", "production"),
            ("1.2.0", "c3d4e5f6a1b27890123456789012345678901234", "production"),
        ]
        releases = {}
        for version, commit_sha, env_name in release_specs:
            rel = (
                db.query(Release)
                .filter(
                    Release.project_id == project.id,
                    Release.version == version,
                    Release.environment == env_name,
                )
                .first()
            )
            if not rel:
                rel = Release(
                    project_id=project.id,
                    version=version,
                    commit_sha=commit_sha,
                    environment=env_name,
                    created_at=now - timedelta(days=3 if version == "1.0.0" else (1 if version == "1.1.0" else 0)),
                )
                db.add(rel)
                db.flush()
                print(f"[+] Created Release: {version} in {env_name}")
            releases[version] = rel

        # 7. Feature Flags
        flag_specs = [
            (
                "new_checkout",
                "New Checkout Experience",
                "Multi-step frictionless checkout redesign with modern payment widgets.",
                50,
                True,
            ),
            (
                "new_payment_flow",
                "New Payment Gateway Flow",
                "Direct API routing through high-speed Stripe European cluster.",
                0,
                False,
            ),
            (
                "experimental_dashboard",
                "Experimental Merchant Dashboard",
                "Real-time analytics and telemetry for merchant transactions.",
                100,
                True,
            ),
        ]
        flags = {}
        for key, name, desc, pct, enabled in flag_specs:
            flag = (
                db.query(FeatureFlag)
                .filter(FeatureFlag.project_id == project.id, FeatureFlag.key == key)
                .first()
            )
            if not flag:
                flag = FeatureFlag(
                    project_id=project.id,
                    key=key,
                    name=name,
                    description=desc,
                    created_at=now,
                    updated_at=now,
                )
                db.add(flag)
                db.flush()

                # Add setting & rollout for production
                prod_env = envs["production"]
                setting = FlagSetting(
                    flag_id=flag.id,
                    environment_id=prod_env.id,
                    enabled=enabled,
                    default_variant="on" if enabled else "off",
                    created_at=now,
                    updated_at=now,
                )
                db.add(setting)
                db.flush()

                rollout = Rollout(
                    setting_id=setting.id,
                    flag_id=flag.id,
                    environment_id=prod_env.id,
                    percentage=pct,
                    salt="demo_salt_checkout",
                    updated_at=now,
                )
                db.add(rollout)

                audit = FlagAuditLog(
                    flag_id=flag.id,
                    environment_id=prod_env.id,
                    actor_id=user.id,
                    action="create",
                    before_state=None,
                    after_state=json.dumps({"enabled": enabled, "percentage": pct}),
                    created_at=now,
                )
                db.add(audit)
                print(f"[+] Created Feature Flag: {key} (Enabled: {enabled}, Rollout: {pct}%)")
            flags[key] = flag

        # 8. Sample Issues & Events
        issue_specs = [
            (
                "DatabaseConnectionTimeout",
                "Connection to PostgreSQL primary pool timed out after 30000ms",
                'File "/app/services/checkout.py", line 142, in process_cart\n  db.connect()\nTimeoutError: Pool connection exhausted',
                142,
                "unresolved",
                "1.2.0",
            ),
            (
                "PaymentGatewayError",
                "HTTP 502 Bad Gateway from Stripe endpoint /v1/charges",
                'File "/app/payments/gateway.py", line 88, in charge_token\n  res = http.post("https://api.stripe.com/v1/charges")\nGatewayResponseError: 502 Bad Gateway',
                89,
                "unresolved",
                "1.2.0",
            ),
            (
                "AuthenticationError",
                "InvalidSignatureError: JWT signature expired or verification failed",
                'File "/app/auth/verifier.py", line 55, in verify_token\n  jwt.decode(token, secret)\nInvalidSignatureError: Signature verification failed',
                24,
                "resolved",
                "1.1.0",
            ),
        ]
        issues = {}
        for ex_type, msg, tb, cnt, stat, rel in issue_specs:
            fp = make_fingerprint(ex_type, tb)
            issue = (
                db.query(Issue)
                .filter(Issue.project_id == project.id, Issue.fingerprint == fp)
                .first()
            )
            if not issue:
                issue = Issue(
                    project_id=project.id,
                    fingerprint=fp,
                    title=f"{ex_type}: {msg}",
                    count=cnt,
                    status=stat,
                    resolved_at=now - timedelta(hours=6) if stat == "resolved" else None,
                    is_regression=False,
                    first_seen=now - timedelta(days=2),
                    last_seen=now - timedelta(minutes=10),
                )
                db.add(issue)
                db.flush()

                # Add sample ErrorEvents
                for i in range(min(cnt, 5)):
                    ev = ErrorEvent(
                        event_id=f"demo_ev_{ex_type[:6]}_{i}_{issue.id}",
                        project_id=project.id,
                        issue_id=issue.id,
                        exception_type=ex_type,
                        message=msg,
                        stack_trace=tb,
                        release=rel,
                        received_at=now - timedelta(minutes=(i * 15)),
                    )
                    db.add(ev)
                print(f"[+] Created Issue: {ex_type} (Count: {cnt}, Status: {stat})")
            issues[ex_type] = issue

        # 9. Incidents & Mitigation
        incidents = [
            (
                "Payment Gateway Surge",
                "Elevated 502 Bad Gateway responses detected on checkout charge requests after v1.2.0 rollout.",
                "critical",
                "investigating",
                issues["PaymentGatewayError"].id,
                releases["1.2.0"].id,
                flags["new_payment_flow"].id,
            ),
            (
                "Database Error Spike",
                "Connection timeout spike on primary checkout database cluster.",
                "high",
                "mitigated",
                issues["DatabaseConnectionTimeout"].id,
                releases["1.2.0"].id,
                None,
            ),
        ]
        for title, desc, sev, stat, iss_id, rel_id, flag_id in incidents:
            inc = (
                db.query(Incident)
                .filter(Incident.project_id == project.id, Incident.title == title)
                .first()
            )
            if not inc:
                inc = Incident(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    environment="production",
                    title=title,
                    description=desc,
                    severity=sev,
                    status=stat,
                    related_issue_id=iss_id,
                    related_release_id=rel_id,
                    related_feature_flag_id=flag_id,
                    created_by=user.id,
                    assigned_to=user.id,
                    started_at=now - timedelta(hours=1),
                    mitigated_at=now - timedelta(minutes=20) if stat == "mitigated" else None,
                    created_at=now - timedelta(hours=1),
                    updated_at=now,
                )
                db.add(inc)
                db.flush()

                # Timeline events
                e1 = IncidentEvent(
                    incident_id=inc.id,
                    actor_id=user.id,
                    event_type="incident_created",
                    message=f"Incident '{title}' triggered with {sev.upper()} severity.",
                    metadata_json=json.dumps({"environment": "production", "severity": sev}),
                    created_at=now - timedelta(hours=1),
                )
                db.add(e1)

                if flag_id:
                    # Advisory mitigation
                    mit = IncidentMitigation(
                        incident_id=inc.id,
                        action_type="disable_feature_flag",
                        target_flag_id=flag_id,
                        target_environment_id=envs["production"].id,
                        reason="Automated advisory recommendation: Disabling 'new_payment_flow' stops bad gateway routing.",
                        confidence=0.95,
                        status="pending_approval",
                        created_at=now - timedelta(minutes=45),
                        updated_at=now - timedelta(minutes=45),
                    )
                    db.add(mit)

                print(f"[+] Created Incident: {title} (Severity: {sev}, Status: {stat})")

        db.commit()
        print("=" * 70)
        print("Demo seed completed successfully!")
        print(f"Login: demo@releaseguard.dev | Password: DemoPassword123!")
        print("=" * 70)

    except Exception as exc:
        db.rollback()
        print(f"[-] Error during demo seeding: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo()
