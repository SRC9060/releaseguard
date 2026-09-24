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

    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as upsert
    else:
        from sqlalchemy.dialects.sqlite import insert as upsert

    stmt = (
        upsert(Issue)
        .values(
            project_id=project_id,
            fingerprint=fingerprint,
            title=f"{payload.exception_type}: {payload.message}",
            count=1,
            first_seen=now,
            last_seen=now,
        )
        .on_conflict_do_update(
            index_elements=["project_id", "fingerprint"],
            set_={
                "count": Issue.count + 1,
                "last_seen": now,
            },
        )
        .returning(Issue.id, Issue.count)
    )
    result = db.execute(stmt).one()
    issue_id, issue_count = result[0], result[1]
    created_new_issue = (issue_count == 1)

    event = ErrorEvent(
        project_id=project_id,
        issue_id=issue_id,
        exception_type=payload.exception_type,
        message=payload.message,
        stack_trace=payload.stack_trace,
        release=payload.release,
        received_at=now,
    )
    db.add(event)
    db.flush()
    event_id = event.id
    db.commit()

    return ErrorEventResponse(
        event_id=event_id,
        issue_id=issue_id,
        fingerprint=fingerprint,
        issue_count=issue_count,
        created_new_issue=created_new_issue,
        received_at=now,
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


@router.get(
    "/projects/{project_id}/issues/{issue_id}",
    response_model=IssueResponse,
)
def get_issue(project_id: int, issue_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    issue = (
        db.query(Issue)
        .filter(Issue.project_id == project_id, Issue.id == issue_id)
        .first()
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")

    return issue

