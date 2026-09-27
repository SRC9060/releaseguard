"""
Feature Flags API routes.
Authenticated tenant-scoped endpoints:
- Environment management: POST/GET .../environments
- Flag management: POST/GET/PUT/DELETE .../flags
- Rollout configuration: PUT .../rollout
- Targeting rules: PUT .../rules
- Kill switch: POST .../kill
- Audit logs: GET .../audit-logs
- SDK evaluation: GET /api/v1/config/{project_identifier}/{environment_key} with ETag caching
"""

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.flags import evaluate_flag
from app.models import (
    Environment,
    FeatureFlag,
    FlagAuditLog,
    FlagSetting,
    Project,
    Rollout,
    TargetingRule,
    User,
)
from app.routes.tenants import get_tenant_project_or_404
from app.schemas import (
    ConfigDocumentResponse,
    EnvironmentCreate,
    EnvironmentResponse,
    FeatureFlagCreate,
    FeatureFlagResponse,
    FeatureFlagUpdate,
    FlagAuditLogResponse,
    FlagEvaluationResult,
    FlagSettingResponse,
    RolloutUpdate,
    TargetingRuleInput,
    TargetingRuleResponse,
)

router = APIRouter(tags=["feature_flags"])


def get_or_create_default_environments(project: Project, db: Session) -> list[Environment]:
    """Ensures standard environments exist for the project."""
    existing = db.query(Environment).filter(Environment.project_id == project.id).all()
    if not existing:
        defaults = [
            ("production", "Production"),
            ("staging", "Staging"),
            ("development", "Development"),
        ]
        created = []
        for key, name in defaults:
            env = Environment(project_id=project.id, key=key, name=name)
            db.add(env)
            created.append(env)
        db.commit()
        for env in created:
            db.refresh(env)
        return created
    return existing


def serialize_setting(setting: FlagSetting) -> FlagSettingResponse:
    rules = [
        TargetingRuleResponse(
            id=r.id,
            priority=r.priority,
            attribute=r.attribute,
            operator=r.operator,
            values=json.loads(r.values) if r.values else [],
            variant=r.variant,
        )
        for r in (setting.rules or [])
    ]
    return FlagSettingResponse(
        id=setting.id,
        flag_id=setting.flag_id,
        environment_id=setting.environment_id,
        environment_key=setting.environment.key if setting.environment else "",
        enabled=setting.enabled,
        default_variant=setting.default_variant,
        rollout_percentage=setting.rollout.percentage if setting.rollout else 0,
        rollout_salt=setting.rollout.salt if setting.rollout else "",
        rules=rules,
    )


def serialize_flag(flag: FeatureFlag) -> FeatureFlagResponse:
    settings = [serialize_setting(s) for s in (flag.settings or [])]
    return FeatureFlagResponse(
        id=flag.id,
        project_id=flag.project_id,
        key=flag.key,
        name=flag.name,
        description=flag.description,
        archived_at=flag.archived_at,
        created_at=flag.created_at,
        updated_at=flag.updated_at,
        settings=settings,
    )


def write_audit_log(
    flag_id: int,
    environment_id: int | None,
    actor_id: int | None,
    action: str,
    before: Any,
    after: Any,
    db: Session,
):
    audit = FlagAuditLog(
        flag_id=flag_id,
        environment_id=environment_id,
        actor_id=actor_id,
        action=action,
        before_state=json.dumps(before) if before is not None else None,
        after_state=json.dumps(after) if after is not None else None,
    )
    db.add(audit)
    db.commit()


# =========================================================================
# 1. Environment Routes
# =========================================================================

@router.post(
    "/tenants/{tenant_id}/projects/{project_id}/environments",
    response_model=EnvironmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_environment(
    tenant_id: int,
    project_id: int,
    payload: EnvironmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="admin")
    key = payload.key.strip().lower()

    existing = (
        db.query(Environment)
        .filter(Environment.project_id == project.id, Environment.key == key)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Environment '{key}' already exists for this project")

    env = Environment(project_id=project.id, key=key, name=payload.name.strip())
    db.add(env)
    db.commit()
    db.refresh(env)

    # Initialize settings for existing flags
    flags = db.query(FeatureFlag).filter(FeatureFlag.project_id == project.id).all()
    for flag in flags:
        setting = FlagSetting(flag_id=flag.id, environment_id=env.id, enabled=False, default_variant="off")
        db.add(setting)
        db.flush()
        rollout = Rollout(setting_id=setting.id, flag_id=flag.id, environment_id=env.id, percentage=0, salt=secrets.token_hex(8))
        db.add(rollout)
    db.commit()

    return env


@router.get(
    "/tenants/{tenant_id}/projects/{project_id}/environments",
    response_model=list[EnvironmentResponse],
)
def list_environments(
    tenant_id: int,
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")
    envs = get_or_create_default_environments(project, db)
    return envs


# =========================================================================
# 2. Flag Management Routes
# =========================================================================

@router.post(
    "/tenants/{tenant_id}/projects/{project_id}/flags",
    response_model=FeatureFlagResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_feature_flag(
    tenant_id: int,
    project_id: int,
    payload: FeatureFlagCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="admin")
    key = payload.key.strip().lower()

    # Reject duplicate flag key in project
    existing = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.project_id == project.id, FeatureFlag.key == key)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Feature flag with key '{key}' already exists in this project",
        )

    flag = FeatureFlag(
        project_id=project.id,
        key=key,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
    )
    db.add(flag)
    db.flush()

    # Automatically initialize settings for all project environments
    envs = get_or_create_default_environments(project, db)
    for env in envs:
        setting = FlagSetting(
            flag_id=flag.id,
            environment_id=env.id,
            enabled=False,
            default_variant="off",
        )
        db.add(setting)
        db.flush()
        rollout = Rollout(
            setting_id=setting.id,
            flag_id=flag.id,
            environment_id=env.id,
            percentage=0,
            salt=secrets.token_hex(8),
        )
        db.add(rollout)

    db.commit()
    db.refresh(flag)

    write_audit_log(
        flag_id=flag.id,
        environment_id=None,
        actor_id=current_user.id,
        action="create",
        before=None,
        after={"key": flag.key, "name": flag.name},
        db=db,
    )

    return serialize_flag(flag)


@router.get(
    "/tenants/{tenant_id}/projects/{project_id}/flags",
    response_model=list[FeatureFlagResponse],
)
def list_feature_flags(
    tenant_id: int,
    project_id: int,
    include_archived: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")
    query = db.query(FeatureFlag).filter(FeatureFlag.project_id == project.id)
    if not include_archived:
        query = query.filter(FeatureFlag.archived_at.is_(None))

    flags = query.order_by(FeatureFlag.created_at.desc(), FeatureFlag.id.desc()).offset(offset).limit(limit).all()
    return [serialize_flag(f) for f in flags]


@router.get(
    "/tenants/{tenant_id}/projects/{project_id}/flags/{flag_id}",
    response_model=FeatureFlagResponse,
)
def get_feature_flag(
    tenant_id: int,
    project_id: int,
    flag_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")
    flag = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.id == flag_id, FeatureFlag.project_id == project.id)
        .first()
    )
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found")

    return serialize_flag(flag)


@router.put(
    "/tenants/{tenant_id}/projects/{project_id}/flags/{flag_id}",
    response_model=FeatureFlagResponse,
)
def update_feature_flag(
    tenant_id: int,
    project_id: int,
    flag_id: int,
    payload: FeatureFlagUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="admin")
    flag = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.id == flag_id, FeatureFlag.project_id == project.id)
        .first()
    )
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found")

    before = {"name": flag.name, "description": flag.description}
    if payload.name is not None:
        flag.name = payload.name.strip()
    if payload.description is not None:
        flag.description = payload.description.strip()

    db.commit()
    db.refresh(flag)

    write_audit_log(
        flag_id=flag.id,
        environment_id=None,
        actor_id=current_user.id,
        action="update",
        before=before,
        after={"name": flag.name, "description": flag.description},
        db=db,
    )

    return serialize_flag(flag)


@router.delete(
    "/tenants/{tenant_id}/projects/{project_id}/flags/{flag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def archive_feature_flag(
    tenant_id: int,
    project_id: int,
    flag_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="admin")
    flag = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.id == flag_id, FeatureFlag.project_id == project.id)
        .first()
    )
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found")

    before = {"archived_at": None}
    flag.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    write_audit_log(
        flag_id=flag.id,
        environment_id=None,
        actor_id=current_user.id,
        action="archive",
        before=before,
        after={"archived_at": str(flag.archived_at)},
        db=db,
    )


# =========================================================================
# 3. Environment Rollout, Rules & Kill Switch
# =========================================================================

def get_flag_setting_or_404(
    tenant_id: int,
    project_id: int,
    flag_id: int,
    environment_id: int,
    user: User,
    db: Session,
    min_role: str = "admin",
) -> tuple[FeatureFlag, FlagSetting]:
    _, project = get_tenant_project_or_404(tenant_id, project_id, user, db, min_role=min_role)
    flag = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.id == flag_id, FeatureFlag.project_id == project.id)
        .first()
    )
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found")

    setting = (
        db.query(FlagSetting)
        .filter(FlagSetting.flag_id == flag.id, FlagSetting.environment_id == environment_id)
        .first()
    )
    if not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag setting not found for environment")

    return flag, setting


@router.put(
    "/tenants/{tenant_id}/projects/{project_id}/flags/{flag_id}/environments/{environment_id}/setting",
    response_model=FlagSettingResponse,
)
def update_flag_setting(
    tenant_id: int,
    project_id: int,
    flag_id: int,
    environment_id: int,
    payload: dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    flag, setting = get_flag_setting_or_404(tenant_id, project_id, flag_id, environment_id, current_user, db, "admin")

    before = {"enabled": setting.enabled, "default_variant": setting.default_variant}
    if "enabled" in payload:
        setting.enabled = bool(payload["enabled"])
    if "default_variant" in payload:
        setting.default_variant = str(payload["default_variant"]).strip()

    db.commit()
    db.refresh(setting)

    write_audit_log(
        flag_id=flag.id,
        environment_id=environment_id,
        actor_id=current_user.id,
        action="setting_change",
        before=before,
        after={"enabled": setting.enabled, "default_variant": setting.default_variant},
        db=db,
    )

    return serialize_setting(setting)


@router.put(
    "/tenants/{tenant_id}/projects/{project_id}/flags/{flag_id}/environments/{environment_id}/rollout",
    response_model=FlagSettingResponse,
)
def update_rollout(
    tenant_id: int,
    project_id: int,
    flag_id: int,
    environment_id: int,
    payload: RolloutUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    flag, setting = get_flag_setting_or_404(tenant_id, project_id, flag_id, environment_id, current_user, db, "admin")

    if not setting.rollout:
        rollout = Rollout(
            setting_id=setting.id,
            flag_id=flag.id,
            environment_id=environment_id,
            percentage=payload.percentage,
            salt=payload.salt or secrets.token_hex(8),
        )
        db.add(rollout)
        before = {"percentage": 0}
    else:
        before = {"percentage": setting.rollout.percentage, "salt": setting.rollout.salt}
        setting.rollout.percentage = payload.percentage
        if payload.salt:
            setting.rollout.salt = payload.salt

    db.commit()
    db.refresh(setting)

    write_audit_log(
        flag_id=flag.id,
        environment_id=environment_id,
        actor_id=current_user.id,
        action="rollout_change",
        before=before,
        after={"percentage": setting.rollout.percentage, "salt": setting.rollout.salt},
        db=db,
    )

    return serialize_setting(setting)


@router.put(
    "/tenants/{tenant_id}/projects/{project_id}/flags/{flag_id}/environments/{environment_id}/rules",
    response_model=FlagSettingResponse,
)
def set_targeting_rules(
    tenant_id: int,
    project_id: int,
    flag_id: int,
    environment_id: int,
    rules: list[TargetingRuleInput],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    flag, setting = get_flag_setting_or_404(tenant_id, project_id, flag_id, environment_id, current_user, db, "admin")

    before_rules = [
        {"attribute": r.attribute, "operator": r.operator, "values": r.values, "variant": r.variant}
        for r in setting.rules
    ]

    # Delete existing rules
    for r in list(setting.rules):
        db.delete(r)
    db.flush()

    # Insert new rules with priorities
    for idx, rule_input in enumerate(rules):
        new_rule = TargetingRule(
            setting_id=setting.id,
            flag_id=flag.id,
            environment_id=environment_id,
            priority=rule_input.priority if rule_input.priority else idx,
            attribute=rule_input.attribute.strip(),
            operator=rule_input.operator.strip().lower(),
            values=json.dumps(rule_input.values),
            variant=rule_input.variant.strip(),
        )
        db.add(new_rule)

    db.commit()
    db.refresh(setting)

    after_rules = [
        {"attribute": r.attribute, "operator": r.operator, "values": r.values, "variant": r.variant}
        for r in setting.rules
    ]

    write_audit_log(
        flag_id=flag.id,
        environment_id=environment_id,
        actor_id=current_user.id,
        action="rule_change",
        before=before_rules,
        after=after_rules,
        db=db,
    )

    return serialize_setting(setting)


@router.post(
    "/tenants/{tenant_id}/projects/{project_id}/flags/{flag_id}/environments/{environment_id}/kill",
    response_model=FlagSettingResponse,
)
def kill_flag(
    tenant_id: int,
    project_id: int,
    flag_id: int,
    environment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    True kill switch:
    - enabled = False
    - rollout.percentage = 0
    - writes audit log
    - evaluates to safe default
    Does not delete the flag.
    """
    flag, setting = get_flag_setting_or_404(tenant_id, project_id, flag_id, environment_id, current_user, db, "admin")

    before = {
        "enabled": setting.enabled,
        "rollout_percentage": setting.rollout.percentage if setting.rollout else 0,
    }

    setting.enabled = False
    if setting.rollout:
        setting.rollout.percentage = 0

    db.commit()
    db.refresh(setting)

    write_audit_log(
        flag_id=flag.id,
        environment_id=environment_id,
        actor_id=current_user.id,
        action="kill",
        before=before,
        after={"enabled": False, "rollout_percentage": 0},
        db=db,
    )

    return serialize_setting(setting)


@router.get(
    "/tenants/{tenant_id}/projects/{project_id}/flags/{flag_id}/audit-logs",
    response_model=list[FlagAuditLogResponse],
)
def get_flag_audit_logs(
    tenant_id: int,
    project_id: int,
    flag_id: int,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")
    flag = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.id == flag_id, FeatureFlag.project_id == project.id)
        .first()
    )
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature flag not found")

    logs = (
        db.query(FlagAuditLog, User.email)
        .outerjoin(User, FlagAuditLog.actor_id == User.id)
        .filter(FlagAuditLog.flag_id == flag.id)
        .order_by(FlagAuditLog.created_at.desc(), FlagAuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        FlagAuditLogResponse(
            id=log.id,
            flag_id=log.flag_id,
            environment_id=log.environment_id,
            actor_id=log.actor_id,
            actor_email=email,
            action=log.action,
            before_state=log.before_state,
            after_state=log.after_state,
            created_at=log.created_at,
        )
        for log, email in logs
    ]


# =========================================================================
# 4. Evaluation & Config Document API (SDK & Edge Delivery)
# =========================================================================

@router.get(
    "/config/{project_identifier}/{environment_key}",
    response_model=ConfigDocumentResponse,
)
def get_configuration_document(
    project_identifier: str,
    environment_key: str,
    response: Response,
    user_id: str | None = Query(default=None),
    if_none_match: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """
    Evaluates all active feature flags for the specified project and environment.
    Designed for high-speed SDK evaluation with ETag and Cache-Control headers.
    """
    # 1. Resolve project by id (int) or api_key (str)
    project = None
    if project_identifier.isdigit():
        project = db.get(Project, int(project_identifier))
    if project is None:
        project = db.query(Project).filter(Project.api_key == project_identifier).first()

    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # 2. Resolve environment
    env = (
        db.query(Environment)
        .filter(
            Environment.project_id == project.id,
            Environment.key == environment_key.strip().lower(),
        )
        .first()
    )
    if env is None:
        envs = get_or_create_default_environments(project, db)
        env = next((e for e in envs if e.key == environment_key.strip().lower()), None)

    if env is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Environment '{environment_key}' not found")

    # 3. Query all flags and their setting for this environment
    flags = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.project_id == project.id, FeatureFlag.archived_at.is_(None))
        .all()
    )

    evaluated_flags: dict[str, FlagEvaluationResult] = {}
    timestamps: list[str] = [str(env.created_at)]

    for flag in flags:
        timestamps.append(str(flag.updated_at))
        setting = (
            db.query(FlagSetting)
            .filter(FlagSetting.flag_id == flag.id, FlagSetting.environment_id == env.id)
            .first()
        )
        if setting:
            timestamps.append(str(setting.updated_at))
            if setting.rollout:
                timestamps.append(str(setting.rollout.updated_at))
            res = evaluate_flag(
                flag_key=flag.key,
                environment_key=env.key,
                setting=setting,
                user_id=user_id,
            )
            evaluated_flags[flag.key] = FlagEvaluationResult(
                enabled=res["enabled"],
                variant=res["variant"],
                reason=res.get("reason"),
                percentage=setting.rollout.percentage if setting.rollout else 0,
                salt=setting.rollout.salt if setting.rollout else "",
            )
        else:
            evaluated_flags[flag.key] = FlagEvaluationResult(
                enabled=False,
                variant="off",
                reason="no_setting",
                percentage=0,
                salt="",
            )

    # 4. Generate ETag based on timestamps + user_id
    raw_hash = hashlib.sha256(f"{':'.join(timestamps)}:{user_id or ''}".encode("utf-8")).hexdigest()
    etag = f'"{raw_hash[:16]}"'

    # Check ETag conditional request
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag, "Cache-Control": "public, max-age=10"})

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=10"

    return ConfigDocumentResponse(
        environment=env.key,
        flags=evaluated_flags,
    )
