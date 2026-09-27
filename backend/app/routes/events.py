from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db import get_db
from app.fingerprint import make_fingerprint
from app.models import ErrorEvent, Issue, Project
from app.queue import EventQueue, get_queue
from app.schemas import (
    BulkErrorEventsCreate,
    BulkIngestResponse,
    ErrorEventCreate,
    ErrorEventResponse,
    IssueEventItem,
    IssueResponse,
    PaginatedEventsResponse,
    TimeSeriesBucket,
    TimeSeriesResponse,
)

router = APIRouter(tags=["errors"])

VALID_STATUSES = {"unresolved", "resolved", "muted"}


def get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def get_issue_or_404(db: Session, project_id: int, issue_id: int) -> Issue:
    get_project_or_404(db, project_id)
    issue = (
        db.query(Issue)
        .filter(Issue.project_id == project_id, Issue.id == issue_id)
        .first()
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


def compute_timeseries(
    db: Session,
    project_id: int,
    issue_id: int | None,
    time_range: str,
) -> TimeSeriesResponse:
    """
    Computes time-series aggregation directly in the database engine using date_trunc.
    Produces zero-filled continuous buckets for seamless dashboard and detail charts:
    - 1h: 60 one-minute buckets
    - 24h: 24 one-hour buckets
    - 7d: 7 one-day buckets
    """
    if time_range not in ("1h", "24h", "7d"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid range '{time_range}'. Allowed values: 1h, 24h, 7d",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if time_range == "1h":
        granularity = "minute"
        bucket_count = 60
        step = timedelta(minutes=1)
        end_time = now.replace(second=0, microsecond=0)
        start_time = end_time - timedelta(minutes=bucket_count - 1)
        fmt = "%Y-%m-%dT%H:%M:00"
    elif time_range == "24h":
        granularity = "hour"
        bucket_count = 24
        step = timedelta(hours=1)
        end_time = now.replace(minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(hours=bucket_count - 1)
        fmt = "%Y-%m-%dT%H:00:00"
    else:  # "7d"
        granularity = "day"
        bucket_count = 7
        step = timedelta(days=1)
        end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_time = end_time - timedelta(days=bucket_count - 1)
        fmt = "%Y-%m-%dT00:00:00"

    buckets_dict: dict[str, int] = {}
    for i in range(bucket_count):
        t = start_time + i * step
        buckets_dict[t.strftime(fmt)] = 0

    dialect_name = db.bind.dialect.name if db.bind else "postgresql"
    if dialect_name == "postgresql":
        bucket_expr = func.date_trunc(granularity, ErrorEvent.received_at)
    else:
        bucket_expr = ErrorEvent.received_at

    query = (
        db.query(
            bucket_expr.label("bucket"),
            func.count(ErrorEvent.id).label("count"),
        )
        .filter(
            ErrorEvent.project_id == project_id,
            ErrorEvent.received_at >= start_time,
        )
    )
    if issue_id is not None:
        query = query.filter(ErrorEvent.issue_id == issue_id)

    db_results = query.group_by(bucket_expr).all()

    for row in db_results:
        bucket_val = row[0]
        cnt = row[1]
        if isinstance(bucket_val, datetime):
            key = bucket_val.strftime(fmt)
        else:
            key = str(bucket_val)
        if key in buckets_dict:
            buckets_dict[key] += cnt
        else:
            buckets_dict[key] = cnt

    bucket_items = [
        TimeSeriesBucket(timestamp=ts, count=cnt)
        for ts, cnt in sorted(buckets_dict.items())
    ]
    total_events = sum(b.count for b in bucket_items)

    return TimeSeriesResponse(
        range=time_range,
        total_events=total_events,
        buckets=bucket_items,
    )


# =========================================================================
# Ingestion Endpoints (Bulk Async + Single Sync)
# =========================================================================

@router.post(
    "/projects/{project_id}/events/bulk",
    response_model=BulkIngestResponse,
    status_code=202,
)
def ingest_events_bulk(
    project_id: int,
    payload: BulkErrorEventsCreate,
    request: Request,
    db: Session = Depends(get_db),
    queue: EventQueue = Depends(get_queue),
):
    project = get_project_or_404(db, project_id)

    client_key = request.headers.get("X-ReleaseGuard-Key")
    if client_key is not None:
        if project.api_key != client_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid ReleaseGuard project key for this project",
            )

    events_data = [e.model_dump() for e in payload.events]
    batch_id, accepted_count = queue.enqueue_events(project_id, events_data)

    return BulkIngestResponse(
        status="accepted",
        accepted_count=accepted_count,
        rejected_count=0,
        batch_id=batch_id,
        project_id=project_id,
    )


@router.get(
    "/projects/{project_id}/queue/stats",
)
def get_queue_stats(
    project_id: int,
    db: Session = Depends(get_db),
    queue: EventQueue = Depends(get_queue),
):
    get_project_or_404(db, project_id)
    return queue.get_metrics()


@router.post(
    "/projects/{project_id}/events",
    response_model=ErrorEventResponse,
    status_code=201,
)
def ingest_event(
    project_id: int,
    payload: ErrorEventCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)

    client_key = request.headers.get("X-ReleaseGuard-Key")
    if client_key is not None:
        if project.api_key != client_key:
            raise HTTPException(
                status_code=401,
                detail="Invalid ReleaseGuard project key for this project",
            )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fingerprint = make_fingerprint(payload.exception_type, payload.stack_trace)

    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as upsert
    else:
        from sqlalchemy.dialects.sqlite import insert as upsert

    # Step 1: Upsert Issue with automatic regression detection
    stmt_issue = (
        upsert(Issue)
        .values(
            project_id=project_id,
            fingerprint=fingerprint,
            title=f"{payload.exception_type}: {payload.message}",
            count=1,
            status="unresolved",
            is_regression=False,
            first_seen=now,
            last_seen=now,
        )
        .on_conflict_do_update(
            index_elements=["project_id", "fingerprint"],
            set_={
                "count": Issue.count + 1,
                "last_seen": now,
                "status": case(
                    (Issue.status == "resolved", "unresolved"),
                    else_=Issue.status,
                ),
                "is_regression": case(
                    (Issue.status == "resolved", True),
                    else_=Issue.is_regression,
                ),
                "regressed_at": case(
                    (Issue.status == "resolved", now),
                    else_=Issue.regressed_at,
                ),
            },
        )
        .returning(Issue.id, Issue.count)
    )
    result_issue = db.execute(stmt_issue).one()
    issue_id, issue_count = result_issue[0], result_issue[1]
    created_new_issue = (issue_count == 1)

    # Step 2: Insert ErrorEvent using ON CONFLICT (event_id) DO NOTHING
    stmt_event = (
        upsert(ErrorEvent)
        .values(
            event_id=payload.event_id,
            project_id=project_id,
            issue_id=issue_id,
            exception_type=payload.exception_type,
            message=payload.message,
            stack_trace=payload.stack_trace,
            release=payload.release,
            received_at=now,
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(ErrorEvent.id)
    )
    event_result = db.execute(stmt_event).first()

    if event_result is None:
        # Event was ALREADY PROCESSED previously (idempotent redelivery).
        # Rollback so Issue count is NOT incremented and regression is NOT falsely triggered.
        db.rollback()
        existing_event = (
            db.query(ErrorEvent)
            .filter(ErrorEvent.event_id == payload.event_id)
            .first()
        )
        existing_issue = db.get(Issue, existing_event.issue_id) if existing_event else None
        return ErrorEventResponse(
            event_id=existing_event.id if existing_event else 0,
            issue_id=existing_event.issue_id if existing_event else issue_id,
            fingerprint=fingerprint,
            issue_count=existing_issue.count if existing_issue else issue_count,
            created_new_issue=False,
            received_at=existing_event.received_at if existing_event else now,
        )

    db.commit()
    event_id = event_result[0]

    return ErrorEventResponse(
        event_id=event_id,
        issue_id=issue_id,
        fingerprint=fingerprint,
        issue_count=issue_count,
        created_new_issue=created_new_issue,
        received_at=now,
    )


# =========================================================================
# Issue Endpoints (List with filter, Detail, Status Actions)
# =========================================================================

@router.get(
    "/projects/{project_id}/issues",
    response_model=list[IssueResponse],
)
def list_issues(
    project_id: int,
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)

    query = db.query(Issue).filter(Issue.project_id == project_id)

    if status is not None:
        if status not in VALID_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status filter '{status}'. Allowed values: {', '.join(sorted(VALID_STATUSES))}",
            )
        query = query.filter(Issue.status == status)

    issues = query.order_by(Issue.last_seen.desc(), Issue.id.desc()).offset(offset).limit(limit).all()
    return issues


@router.get(
    "/projects/{project_id}/issues/{issue_id}",
    response_model=IssueResponse,
)
def get_issue(project_id: int, issue_id: int, db: Session = Depends(get_db)):
    return get_issue_or_404(db, project_id, issue_id)


@router.post(
    "/projects/{project_id}/issues/{issue_id}/resolve",
    response_model=IssueResponse,
)
def resolve_issue(
    project_id: int,
    issue_id: int,
    db: Session = Depends(get_db),
):
    issue = get_issue_or_404(db, project_id, issue_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    issue.status = "resolved"
    issue.resolved_at = now
    issue.muted_at = None
    db.commit()
    db.refresh(issue)
    return issue


@router.post(
    "/projects/{project_id}/issues/{issue_id}/mute",
    response_model=IssueResponse,
)
def mute_issue(
    project_id: int,
    issue_id: int,
    db: Session = Depends(get_db),
):
    issue = get_issue_or_404(db, project_id, issue_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    issue.status = "muted"
    issue.muted_at = now
    issue.resolved_at = None
    db.commit()
    db.refresh(issue)
    return issue


@router.post(
    "/projects/{project_id}/issues/{issue_id}/unresolve",
    response_model=IssueResponse,
)
def unresolve_issue(
    project_id: int,
    issue_id: int,
    db: Session = Depends(get_db),
):
    issue = get_issue_or_404(db, project_id, issue_id)
    issue.status = "unresolved"
    issue.resolved_at = None
    issue.muted_at = None
    db.commit()
    db.refresh(issue)
    return issue


# =========================================================================
# Event Timeline API (Paginated)
# =========================================================================

@router.get(
    "/projects/{project_id}/issues/{issue_id}/events",
    response_model=PaginatedEventsResponse,
)
def list_issue_events(
    project_id: int,
    issue_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    get_issue_or_404(db, project_id, issue_id)

    total = (
        db.query(func.count(ErrorEvent.id))
        .filter(ErrorEvent.project_id == project_id, ErrorEvent.issue_id == issue_id)
        .scalar()
        or 0
    )

    events = (
        db.query(ErrorEvent)
        .filter(ErrorEvent.project_id == project_id, ErrorEvent.issue_id == issue_id)
        .order_by(ErrorEvent.received_at.desc(), ErrorEvent.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    has_more = (offset + len(events)) < total

    return PaginatedEventsResponse(
        items=events,
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


# =========================================================================
# Time Series Analytics Endpoints
# =========================================================================

@router.get(
    "/projects/{project_id}/metrics/issues/{issue_id}/timeseries",
    response_model=TimeSeriesResponse,
)
def get_issue_timeseries(
    project_id: int,
    issue_id: int,
    range: str = Query("24h"),
    db: Session = Depends(get_db),
):
    get_issue_or_404(db, project_id, issue_id)
    return compute_timeseries(db, project_id, issue_id=issue_id, time_range=range)


@router.get(
    "/projects/{project_id}/metrics/timeseries",
    response_model=TimeSeriesResponse,
)
def get_project_timeseries(
    project_id: int,
    range: str = Query("24h"),
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)
    return compute_timeseries(db, project_id, issue_id=None, time_range=range)
