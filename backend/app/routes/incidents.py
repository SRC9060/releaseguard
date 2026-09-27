"""
Phase 9 — Incidents & Mitigation API routes.
Authenticated tenant-scoped endpoints:
- POST   /api/v1/tenants/{tenant_id}/projects/{project_id}/incidents
- GET    /api/v1/tenants/{tenant_id}/projects/{project_id}/incidents
- GET    /api/v1/tenants/{tenant_id}/projects/{project_id}/incidents/{incident_id}
- PATCH  /api/v1/tenants/{tenant_id}/projects/{project_id}/incidents/{incident_id}
- GET    /api/v1/tenants/{tenant_id}/projects/{project_id}/incidents/{incident_id}/timeline
- POST   /api/v1/tenants/{tenant_id}/projects/{project_id}/incidents/{incident_id}/timeline
- POST   /api/v1/tenants/{tenant_id}/projects/{project_id}/incidents/{incident_id}/mitigations/{mitigation_id}/approve
- POST   /api/v1/tenants/{tenant_id}/projects/{project_id}/incidents/detect-spike
"""

from datetime import datetime
import json
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.auth import get_current_user
from app.db import get_db
from app.incidents import CorrelationService, MitigationService, SpikeDetectionService
from app.models import (
    Incident,
    IncidentEvent,
    IncidentMitigation,
    Issue,
    Release,
    FeatureFlag,
    User,
    utcnow,
)
from app.routes.tenants import get_tenant_project_or_404
from app.schemas import (
    CorrelatedChange,
    IncidentCreate,
    IncidentEventCreate,
    IncidentEventResponse,
    IncidentMitigationResponse,
    IncidentResponse,
    IncidentUpdate,
    SpikeDetectionResult,
)

router = APIRouter(prefix="/tenants/{tenant_id}/projects/{project_id}/incidents", tags=["incidents"])


def _format_incident_response(
    incident: Incident,
    include_details: bool = False,
    db: Session | None = None,
) -> IncidentResponse:
    related_issue_title = incident.related_issue.title if incident.related_issue else None
    related_release_version = incident.related_release.version if incident.related_release else None
    related_flag_key = incident.related_feature_flag.key if incident.related_feature_flag else None
    creator_email = incident.creator.email if incident.creator else None
    assignee_email = incident.assignee.email if incident.assignee else None

    timeline_items: list[IncidentEventResponse] = []
    mitigation_items: list[IncidentMitigationResponse] = []
    correlated_changes: list[CorrelatedChange] = []

    if include_details and db is not None:
        # 1. Timeline
        for event in incident.events:
            meta = None
            if event.metadata_json:
                try:
                    meta = json.loads(event.metadata_json)
                except Exception:
                    meta = {"raw": event.metadata_json}

            timeline_items.append(
                IncidentEventResponse(
                    id=event.id,
                    incident_id=event.incident_id,
                    actor_id=event.actor_id,
                    actor_email=event.actor.email if event.actor else None,
                    event_type=event.event_type,
                    message=event.message,
                    metadata=meta,
                    created_at=event.created_at,
                )
            )

        # 2. Mitigations
        for m in incident.mitigations:
            exec_res = None
            if m.execution_result:
                try:
                    exec_res = json.loads(m.execution_result)
                except Exception:
                    exec_res = {"raw": m.execution_result}

            mitigation_items.append(
                IncidentMitigationResponse(
                    id=m.id,
                    incident_id=m.incident_id,
                    action_type=m.action_type,
                    target_flag_id=m.target_flag_id,
                    target_flag_key=m.target_flag.key if m.target_flag else None,
                    target_environment_id=m.target_environment_id,
                    target_environment_key=m.target_environment.key if m.target_environment else None,
                    reason=m.reason,
                    confidence=m.confidence,
                    status=m.status,
                    approved_by=m.approved_by,
                    approved_by_email=m.approver.email if m.approver else None,
                    approved_at=m.approved_at,
                    executed_at=m.executed_at,
                    execution_result=exec_res,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                )
            )

        # 3. Correlated Changes
        correlated = CorrelationService.find_correlated_changes(
            project_id=incident.project_id,
            environment=incident.environment,
            reference_time=incident.started_at,
            lookback_hours=24,
            issue_id=incident.related_issue_id,
            db=db,
        )
        correlated_changes = [CorrelatedChange(**c) for c in correlated]

    return IncidentResponse(
        id=incident.id,
        tenant_id=incident.tenant_id,
        project_id=incident.project_id,
        environment=incident.environment,
        title=incident.title,
        description=incident.description,
        severity=incident.severity,
        status=incident.status,
        related_issue_id=incident.related_issue_id,
        related_issue_title=related_issue_title,
        related_release_id=incident.related_release_id,
        related_release_version=related_release_version,
        related_feature_flag_id=incident.related_feature_flag_id,
        related_feature_flag_key=related_flag_key,
        created_by=incident.created_by,
        created_by_email=creator_email,
        assigned_to=incident.assigned_to,
        assigned_to_email=assignee_email,
        started_at=incident.started_at,
        mitigated_at=incident.mitigated_at,
        resolved_at=incident.resolved_at,
        closed_at=incident.closed_at,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        timeline=timeline_items,
        mitigations=mitigation_items,
        correlated_changes=correlated_changes,
    )


@router.post("", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    tenant_id: int,
    project_id: int,
    payload: IncidentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a new incident scoped to a project and environment.
    Automatically logs initial timeline event and analyzes recent flag/release changes.
    """
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")

    env = payload.environment.strip().lower()

    # Validate optional links
    if payload.related_issue_id:
        issue = db.query(Issue).filter(Issue.id == payload.related_issue_id, Issue.project_id == project.id).first()
        if not issue:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Related issue not found for this project")

    if payload.related_release_id:
        release = db.query(Release).filter(Release.id == payload.related_release_id, Release.project_id == project.id).first()
        if not release:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Related release not found for this project")

    if payload.related_feature_flag_id:
        flag = db.query(FeatureFlag).filter(FeatureFlag.id == payload.related_feature_flag_id, FeatureFlag.project_id == project.id).first()
        if not flag:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Related feature flag not found for this project")

    incident = Incident(
        tenant_id=tenant_id,
        project_id=project.id,
        environment=env,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        severity=payload.severity.strip().lower(),
        status="triggered",
        related_issue_id=payload.related_issue_id,
        related_release_id=payload.related_release_id,
        related_feature_flag_id=payload.related_feature_flag_id,
        created_by=current_user.id,
        assigned_to=payload.assigned_to,
        started_at=utcnow(),
    )
    db.add(incident)
    db.flush()

    # Write initial timeline event
    initial_event = IncidentEvent(
        incident_id=incident.id,
        actor_id=current_user.id,
        event_type="incident_created",
        message=f"Incident '{incident.title}' was triggered with {incident.severity.upper()} severity.",
        metadata_json=json.dumps({"environment": env, "severity": incident.severity}),
        created_at=utcnow(),
    )
    db.add(initial_event)

    # Automatically generate advisory recommendations if related flag / issue exists
    MitigationService.recommend_mitigation(incident, db)

    db.commit()
    db.refresh(incident)

    return _format_incident_response(incident, include_details=True, db=db)


@router.get("", response_model=list[IncidentResponse])
def list_incidents(
    tenant_id: int,
    project_id: int,
    status_filter: str | None = Query(None, alias="status"),
    severity_filter: str | None = Query(None, alias="severity"),
    environment_filter: str | None = Query(None, alias="environment"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lists all incidents for a project with optional status, severity, and environment filters.
    """
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")

    query = db.query(Incident).filter(
        Incident.tenant_id == tenant_id,
        Incident.project_id == project.id,
    )

    if status_filter:
        query = query.filter(Incident.status == status_filter.strip().lower())
    if severity_filter:
        query = query.filter(Incident.severity == severity_filter.strip().lower())
    if environment_filter:
        query = query.filter(Incident.environment == environment_filter.strip().lower())

    incidents = query.order_by(desc(Incident.created_at)).all()
    return [_format_incident_response(inc, include_details=False, db=db) for inc in incidents]


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(
    tenant_id: int,
    project_id: int,
    incident_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves full incident details, timeline, mitigations, and correlated changes.
    """
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")

    incident = (
        db.query(Incident)
        .filter(
            Incident.id == incident_id,
            Incident.project_id == project.id,
            Incident.tenant_id == tenant_id,
        )
        .first()
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    return _format_incident_response(incident, include_details=True, db=db)


@router.patch("/{incident_id}", response_model=IncidentResponse)
def update_incident(
    tenant_id: int,
    project_id: int,
    incident_id: int,
    payload: IncidentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Updates incident metadata and manages lifecycle status transitions.
    Requires owner or admin permissions.
    """
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="admin")

    incident = (
        db.query(Incident)
        .filter(
            Incident.id == incident_id,
            Incident.project_id == project.id,
            Incident.tenant_id == tenant_id,
        )
        .first()
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    now = utcnow()

    if payload.title is not None:
        incident.title = payload.title.strip()
    if payload.description is not None:
        incident.description = payload.description.strip()
    if payload.severity is not None:
        old_sev = incident.severity
        incident.severity = payload.severity.strip().lower()
        if old_sev != incident.severity:
            db.add(
                IncidentEvent(
                    incident_id=incident.id,
                    actor_id=current_user.id,
                    event_type="severity_changed",
                    message=f"Severity updated from {old_sev.upper()} to {incident.severity.upper()}.",
                    created_at=now,
                )
            )

    if payload.assigned_to is not None:
        incident.assigned_to = payload.assigned_to
        assignee = db.query(User).filter(User.id == payload.assigned_to).first()
        assignee_email = assignee.email if assignee else f"User #{payload.assigned_to}"
        db.add(
            IncidentEvent(
                incident_id=incident.id,
                actor_id=current_user.id,
                event_type="assigned",
                message=f"Incident assigned to {assignee_email}.",
                created_at=now,
            )
        )

    if payload.status is not None:
        new_status = payload.status.strip().lower()
        if new_status != incident.status:
            old_status = incident.status
            incident.status = new_status
            if new_status == "mitigated" and not incident.mitigated_at:
                incident.mitigated_at = now
            elif new_status == "resolved" and not incident.resolved_at:
                incident.resolved_at = now
            elif new_status == "closed" and not incident.closed_at:
                incident.closed_at = now

            db.add(
                IncidentEvent(
                    incident_id=incident.id,
                    actor_id=current_user.id,
                    event_type="status_changed",
                    message=f"Status changed from '{old_status}' to '{new_status}'.",
                    created_at=now,
                )
            )

    incident.updated_at = now
    db.commit()
    db.refresh(incident)

    return _format_incident_response(incident, include_details=True, db=db)


@router.get("/{incident_id}/timeline", response_model=list[IncidentEventResponse])
def get_incident_timeline(
    tenant_id: int,
    project_id: int,
    incident_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns complete chronological event timeline for the incident.
    """
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")

    incident = (
        db.query(Incident)
        .filter(
            Incident.id == incident_id,
            Incident.project_id == project.id,
            Incident.tenant_id == tenant_id,
        )
        .first()
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    events = (
        db.query(IncidentEvent)
        .filter(IncidentEvent.incident_id == incident.id)
        .order_by(IncidentEvent.created_at.asc())
        .all()
    )

    items = []
    for ev in events:
        meta = None
        if ev.metadata_json:
            try:
                meta = json.loads(ev.metadata_json)
            except Exception:
                meta = {"raw": ev.metadata_json}

        items.append(
            IncidentEventResponse(
                id=ev.id,
                incident_id=ev.incident_id,
                actor_id=ev.actor_id,
                actor_email=ev.actor.email if ev.actor else None,
                event_type=ev.event_type,
                message=ev.message,
                metadata=meta,
                created_at=ev.created_at,
            )
        )
    return items


@router.post("/{incident_id}/timeline", response_model=IncidentEventResponse, status_code=status.HTTP_201_CREATED)
def add_incident_timeline_note(
    tenant_id: int,
    project_id: int,
    incident_id: int,
    payload: IncidentEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Adds an investigation note or update to the incident timeline.
    Accessible to team members, admins, and owners.
    """
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")

    incident = (
        db.query(Incident)
        .filter(
            Incident.id == incident_id,
            Incident.project_id == project.id,
            Incident.tenant_id == tenant_id,
        )
        .first()
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    meta_json = json.dumps(payload.metadata) if payload.metadata else None

    ev = IncidentEvent(
        incident_id=incident.id,
        actor_id=current_user.id,
        event_type=payload.event_type or "note_added",
        message=payload.message.strip(),
        metadata_json=meta_json,
        created_at=utcnow(),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)

    return IncidentEventResponse(
        id=ev.id,
        incident_id=ev.incident_id,
        actor_id=ev.actor_id,
        actor_email=current_user.email,
        event_type=ev.event_type,
        message=ev.message,
        metadata=payload.metadata,
        created_at=ev.created_at,
    )


@router.post("/{incident_id}/mitigations/{mitigation_id}/approve", status_code=status.HTTP_200_OK)
def approve_mitigation(
    tenant_id: int,
    project_id: int,
    incident_id: int,
    mitigation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Explicit mitigation approval endpoint.
    Guarantees:
    - Only authorized admin or owner can execute (members get 403 Forbidden).
    - Safe feature-flag kill-switch execution (rollout to 0%, flag disabled).
    - Idempotent: repeated approvals do not double execute.
    - Transactional audit log and incident timeline updates.
    """
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="admin")

    incident = (
        db.query(Incident)
        .filter(
            Incident.id == incident_id,
            Incident.project_id == project.id,
            Incident.tenant_id == tenant_id,
        )
        .first()
    )
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    try:
        result = MitigationService.approve_and_execute_mitigation(
            incident_id=incident.id,
            mitigation_id=mitigation_id,
            actor_id=current_user.id,
            db=db,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/detect-spike", response_model=SpikeDetectionResult)
def detect_spike_endpoint(
    tenant_id: int,
    project_id: int,
    issue_id: int = Query(...),
    environment: str = Query("production"),
    auto_create_incident: bool = Query(True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Evaluates issue error spike using deterministic rate comparison.
    If spike detected and auto_create_incident is True, creates an incident unless cooldown applies.
    """
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")

    issue = db.query(Issue).filter(Issue.id == issue_id, Issue.project_id == project.id).first()
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    now = utcnow()
    eval_result = SpikeDetectionService.detect_spike(
        issue_id=issue.id,
        project_id=project.id,
        environment=environment,
        now=now,
        db=db,
    )

    incident_created = False
    incident_id = None
    reason = None

    if eval_result["is_spike"]:
        # Check duplicate incident cooldown
        is_dup = SpikeDetectionService.is_duplicate_incident(
            issue_id=issue.id,
            project_id=project.id,
            environment=environment,
            cooldown_minutes=60,
            now=now,
            db=db,
        )

        if is_dup:
            reason = "Spike confirmed, but an active incident already exists within the cooldown period."
        elif auto_create_incident:
            # Create Incident automatically
            new_inc = Incident(
                tenant_id=tenant_id,
                project_id=project.id,
                environment=environment,
                title=f"Error Spike: {issue.title[:80]}",
                description=(
                    f"Automated spike detector observed {eval_result['current_count']} events "
                    f"in the last 15m ({eval_result['spike_ratio']}x baseline velocity)."
                ),
                severity="high" if eval_result["spike_ratio"] >= 4.0 else "medium",
                status="triggered",
                related_issue_id=issue.id,
                created_by=current_user.id,
                started_at=now,
            )
            db.add(new_inc)
            db.flush()

            # Add creation timeline event
            db.add(
                IncidentEvent(
                    incident_id=new_inc.id,
                    actor_id=current_user.id,
                    event_type="incident_created",
                    message=f"Incident triggered by error spike ({eval_result['spike_ratio']}x baseline).",
                    metadata_json=json.dumps(eval_result),
                    created_at=now,
                )
            )

            # Generate advisory recommendations
            MitigationService.recommend_mitigation(new_inc, db)

            db.commit()
            incident_created = True
            incident_id = new_inc.id
            reason = f"Incident #{new_inc.id} created from confirmed error velocity spike."
    else:
        reason = "Error velocity remains within normal baseline thresholds."

    return SpikeDetectionResult(
        is_spike=eval_result["is_spike"],
        issue_id=issue.id,
        environment=environment,
        current_count=eval_result["current_count"],
        baseline_count=eval_result["baseline_count"],
        current_rate=eval_result["current_rate"],
        baseline_rate=eval_result["baseline_rate"],
        spike_ratio=eval_result["spike_ratio"],
        threshold=eval_result["threshold"],
        incident_created=incident_created,
        incident_id=incident_id,
        reason=reason,
    )
