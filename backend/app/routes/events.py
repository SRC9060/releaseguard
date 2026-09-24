from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.fingerprint import make_fingerprint
from app.models import ErrorEvent, Issue, Project
from app.schemas import ErrorEventCreate, ErrorEventResponse, IssueResponse

router = APIRouter(tags=["errors"])


@router.post(
    "/projects/{project_id}/events",
    response_model=ErrorEventResponse,
    status_code=201,
)
def ingest_event(
    project_id: int,
    payload: ErrorEventCreate,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fingerprint = make_fingerprint(payload.exception_type, payload.stack_trace)

    issue = (
        db.query(Issue)
        .filter(
            Issue.project_id == project_id,
            Issue.fingerprint == fingerprint,
        )
        .first()
    )

    created_new_issue = False

    if issue is None:
        issue = Issue(
            project_id=project_id,
            fingerprint=fingerprint,
            title=f"{payload.exception_type}: {payload.message}",
            count=1,
            first_seen=now,
            last_seen=now,
        )
        db.add(issue)
        db.flush()
        created_new_issue = True
    else:
        issue.count += 1
        issue.last_seen = now

    event = ErrorEvent(
        project_id=project_id,
        issue_id=issue.id,
        exception_type=payload.exception_type,
        message=payload.message,
        stack_trace=payload.stack_trace,
        release=payload.release,
        received_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return ErrorEventResponse(
        event_id=event.id,
        issue_id=issue.id,
        fingerprint=issue.fingerprint,
        issue_count=issue.count,
        created_new_issue=created_new_issue,
        received_at=event.received_at,
    )


@router.get(
    "/projects/{project_id}/issues",
    response_model=list[IssueResponse],
)
def list_issues(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    issues = (
        db.query(Issue)
        .filter(Issue.project_id == project_id)
        .order_by(Issue.last_seen.desc())
        .all()
    )

    return issues
