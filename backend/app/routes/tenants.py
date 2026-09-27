from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import (
    ensure_not_last_owner,
    generate_invite_token,
    get_current_user,
    get_tenant_membership_or_404,
    hash_token,
)
from app.db import get_db
from app.models import ErrorEvent, Issue, Membership, Project, Tenant, TenantInvite, User
from app.routes.auth import generate_unique_slug
from app.routes.events import compute_timeseries
from app.schemas import (
    InviteAcceptResponse,
    InviteCreate,
    InviteResponse,
    IssueResponse,
    MembershipResponse,
    MembershipUpdate,
    PaginatedEventsResponse,
    ProjectCreate,
    ProjectResponse,
    TenantCreate,
    TenantResponse,
    TimeSeriesResponse,
)

router = APIRouter(tags=["tenants"])


# =========================================================================
# Reusable Tenant-Scoped Data Access Helpers
# =========================================================================

def get_tenant_project_or_404(
    tenant_id: int,
    project_id: int,
    user: User,
    db: Session,
    min_role: str = "member",
) -> tuple[Tenant, Project]:
    """
    Verifies user is a tenant member and looks up project strictly scoped to tenant_id.
    Returns 404 if project is missing or owned by another tenant.
    """
    tenant, _ = get_tenant_membership_or_404(tenant_id, user, db, min_role)
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.tenant_id == tenant_id)
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return tenant, project


def get_tenant_issue_or_404(
    tenant_id: int,
    project_id: int,
    issue_id: int,
    user: User,
    db: Session,
    min_role: str = "member",
) -> tuple[Tenant, Project, Issue]:
    """
    Verifies user is a tenant member, project belongs to tenant, and issue belongs to project.
    Returns 404 if any relationship is mismatched.
    """
    tenant, project = get_tenant_project_or_404(tenant_id, project_id, user, db, min_role)
    issue = (
        db.query(Issue)
        .filter(Issue.id == issue_id, Issue.project_id == project_id)
        .first()
    )
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return tenant, project, issue


# =========================================================================
# 1. Tenant Lifecycle & Listing
# =========================================================================

@router.post(
    "/tenants",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tenant(
    payload: TenantCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    slug = payload.slug.strip() if payload.slug else generate_unique_slug(name, db)

    # Check slug collision
    if db.query(Tenant).filter(Tenant.slug == slug).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant slug '{slug}' is already taken",
        )

    tenant = Tenant(name=name, slug=slug)
    db.add(tenant)
    db.flush()

    # Creator is granted Owner role
    membership = Membership(
        tenant_id=tenant.id,
        user_id=current_user.id,
        role="owner",
    )
    db.add(membership)
    db.commit()
    db.refresh(tenant)

    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        role="owner",
        created_at=tenant.created_at,
    )


@router.get(
    "/tenants",
    response_model=list[TenantResponse],
)
def list_user_tenants(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memberships = (
        db.query(Membership, Tenant)
        .join(Tenant, Membership.tenant_id == Tenant.id)
        .filter(Membership.user_id == current_user.id)
        .all()
    )
    return [
        TenantResponse(
            id=t.id,
            name=t.name,
            slug=t.slug,
            role=m.role,
            created_at=t.created_at,
        )
        for m, t in memberships
    ]


@router.get(
    "/tenants/{tenant_id}",
    response_model=TenantResponse,
)
def get_tenant(
    tenant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant, membership = get_tenant_membership_or_404(tenant_id, current_user, db)
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        role=membership.role,
        created_at=tenant.created_at,
    )


# =========================================================================
# 2. Member Management & Last-Owner Protection
# =========================================================================

@router.get(
    "/tenants/{tenant_id}/members",
    response_model=list[MembershipResponse],
)
def list_tenant_members(
    tenant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_tenant_membership_or_404(tenant_id, current_user, db, min_role="member")
    memberships = (
        db.query(Membership, User.email)
        .join(User, Membership.user_id == User.id)
        .filter(Membership.tenant_id == tenant_id)
        .all()
    )
    return [
        MembershipResponse(
            id=m.id,
            tenant_id=m.tenant_id,
            user_id=m.user_id,
            email=email,
            role=m.role,
            created_at=m.created_at,
        )
        for m, email in memberships
    ]


@router.patch(
    "/tenants/{tenant_id}/members/{user_id}",
    response_model=MembershipResponse,
)
def update_member_role(
    tenant_id: int,
    user_id: int,
    payload: MembershipUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Only owner or admin can modify member roles
    _, caller_membership = get_tenant_membership_or_404(tenant_id, current_user, db, min_role="admin")

    target = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    # Admins cannot demote or promote to/from owner
    if caller_membership.role == "admin" and (target.role == "owner" or payload.role == "owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant owners can promote or demote owners",
        )

    # Last-owner protection
    if target.role == "owner" and payload.role != "owner":
        ensure_not_last_owner(tenant_id, user_id, db)

    target.role = payload.role
    db.commit()
    db.refresh(target)

    user = db.get(User, user_id)
    return MembershipResponse(
        id=target.id,
        tenant_id=target.tenant_id,
        user_id=target.user_id,
        email=user.email if user else None,
        role=target.role,
        created_at=target.created_at,
    )


@router.delete(
    "/tenants/{tenant_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_tenant_member(
    tenant_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, caller_membership = get_tenant_membership_or_404(tenant_id, current_user, db, min_role="member")

    # A user can remove themselves (leave tenant), or admins/owners can remove others
    is_self = current_user.id == user_id
    if not is_self and caller_membership.role not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    target = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant_id, Membership.user_id == user_id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    # Admins cannot remove owners
    if not is_self and caller_membership.role == "admin" and target.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot remove tenant owners",
        )

    # Last-owner protection check
    if target.role == "owner":
        ensure_not_last_owner(tenant_id, user_id, db)

    db.delete(target)
    db.commit()


# =========================================================================
# 3. Tenant Invitations
# =========================================================================

@router.post(
    "/tenants/{tenant_id}/invites",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invite(
    tenant_id: int,
    payload: InviteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Only owners and admins can invite members
    get_tenant_membership_or_404(tenant_id, current_user, db, min_role="admin")

    raw_token = generate_invite_token()
    token_hash = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)

    invite = TenantInvite(
        tenant_id=tenant_id,
        email=payload.email.strip().lower(),
        role=payload.role,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    return InviteResponse(
        id=invite.id,
        tenant_id=invite.tenant_id,
        email=invite.email,
        role=invite.role,
        token=raw_token,  # returned for testing/prototype integration
        expires_at=invite.expires_at,
        created_at=invite.created_at,
    )


@router.post(
    "/invites/{token}/accept",
    response_model=InviteAcceptResponse,
)
def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token_hash = hash_token(token)
    invite = db.query(TenantInvite).filter(TenantInvite.token_hash == token_hash).first()

    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if invite.accepted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been accepted",
        )

    if invite.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    # Check if user is already a member
    existing_membership = (
        db.query(Membership)
        .filter(Membership.tenant_id == invite.tenant_id, Membership.user_id == current_user.id)
        .first()
    )
    if existing_membership is None:
        membership = Membership(
            tenant_id=invite.tenant_id,
            user_id=current_user.id,
            role=invite.role,
        )
        db.add(membership)

    invite.accepted_at = now
    db.commit()

    tenant = db.get(Tenant, invite.tenant_id)
    return InviteAcceptResponse(
        status="accepted",
        tenant_id=invite.tenant_id,
        tenant_name=tenant.name if tenant else "Unknown",
        role=invite.role,
    )


# =========================================================================
# 4. Tenant-Scoped Projects API
# =========================================================================

@router.post(
    "/tenants/{tenant_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tenant_project(
    tenant_id: int,
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Creating a project requires at least admin or owner role in the tenant
    tenant, _ = get_tenant_membership_or_404(tenant_id, current_user, db, min_role="admin")

    project = Project(
        name=payload.name.strip(),
        tenant_id=tenant.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return project


@router.get(
    "/tenants/{tenant_id}/projects",
    response_model=list[ProjectResponse],
)
def list_tenant_projects(
    tenant_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_tenant_membership_or_404(tenant_id, current_user, db, min_role="member")
    projects = (
        db.query(Project)
        .filter(Project.tenant_id == tenant_id)
        .order_by(Project.id.asc())
        .all()
    )
    return projects


@router.get(
    "/tenants/{tenant_id}/projects/{project_id}",
    response_model=ProjectResponse,
)
def get_tenant_project(
    tenant_id: int,
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db)
    return project


# =========================================================================
# 5. Tenant-Scoped Issues API
# =========================================================================

@router.get(
    "/tenants/{tenant_id}/projects/{project_id}/issues",
    response_model=list[IssueResponse],
)
def list_tenant_issues(
    tenant_id: int,
    project_id: int,
    status: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db)

    query = db.query(Issue).filter(Issue.project_id == project.id)

    if status is not None:
        valid_statuses = {"unresolved", "resolved", "muted"}
        if status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter '{status}'",
            )
        query = query.filter(Issue.status == status)

    return query.order_by(Issue.last_seen.desc()).all()


@router.get(
    "/tenants/{tenant_id}/projects/{project_id}/issues/{issue_id}",
    response_model=IssueResponse,
)
def get_tenant_issue(
    tenant_id: int,
    project_id: int,
    issue_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, _, issue = get_tenant_issue_or_404(tenant_id, project_id, issue_id, current_user, db)
    return issue


@router.post(
    "/tenants/{tenant_id}/projects/{project_id}/issues/{issue_id}/resolve",
    response_model=IssueResponse,
)
def resolve_tenant_issue(
    tenant_id: int,
    project_id: int,
    issue_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, _, issue = get_tenant_issue_or_404(tenant_id, project_id, issue_id, current_user, db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    issue.status = "resolved"
    issue.resolved_at = now
    issue.muted_at = None
    db.commit()
    db.refresh(issue)
    return issue


@router.post(
    "/tenants/{tenant_id}/projects/{project_id}/issues/{issue_id}/mute",
    response_model=IssueResponse,
)
def mute_tenant_issue(
    tenant_id: int,
    project_id: int,
    issue_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, _, issue = get_tenant_issue_or_404(tenant_id, project_id, issue_id, current_user, db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    issue.status = "muted"
    issue.muted_at = now
    issue.resolved_at = None
    db.commit()
    db.refresh(issue)
    return issue


@router.post(
    "/tenants/{tenant_id}/projects/{project_id}/issues/{issue_id}/unresolve",
    response_model=IssueResponse,
)
def unresolve_tenant_issue(
    tenant_id: int,
    project_id: int,
    issue_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, _, issue = get_tenant_issue_or_404(tenant_id, project_id, issue_id, current_user, db)
    issue.status = "unresolved"
    issue.resolved_at = None
    issue.muted_at = None
    db.commit()
    db.refresh(issue)
    return issue


# =========================================================================
# 6. Tenant-Scoped Events Timeline
# =========================================================================

@router.get(
    "/tenants/{tenant_id}/projects/{project_id}/issues/{issue_id}/events",
    response_model=PaginatedEventsResponse,
)
def list_tenant_issue_events(
    tenant_id: int,
    project_id: int,
    issue_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, _, issue = get_tenant_issue_or_404(tenant_id, project_id, issue_id, current_user, db)

    total = (
        db.query(ErrorEvent)
        .filter(ErrorEvent.project_id == project_id, ErrorEvent.issue_id == issue.id)
        .count()
    )

    events = (
        db.query(ErrorEvent)
        .filter(ErrorEvent.project_id == project_id, ErrorEvent.issue_id == issue.id)
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
# 7. Tenant-Scoped Time Series
# =========================================================================

@router.get(
    "/tenants/{tenant_id}/projects/{project_id}/metrics/issues/{issue_id}/timeseries",
    response_model=TimeSeriesResponse,
)
def get_tenant_issue_timeseries(
    tenant_id: int,
    project_id: int,
    issue_id: int,
    range: str = Query("24h"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, _, issue = get_tenant_issue_or_404(tenant_id, project_id, issue_id, current_user, db)
    return compute_timeseries(db, project_id, issue_id=issue.id, time_range=range)


@router.get(
    "/tenants/{tenant_id}/projects/{project_id}/metrics/timeseries",
    response_model=TimeSeriesResponse,
)
def get_tenant_project_timeseries(
    tenant_id: int,
    project_id: int,
    range: str = Query("24h"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db)
    return compute_timeseries(db, project.id, issue_id=None, time_range=range)


@router.get(
    "/tenants/{tenant_id}/projects/{project_id}/issues/{issue_id}/releases",
)
def get_issue_releases(
    tenant_id: int,
    project_id: int,
    issue_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Exposes release correlation for an issue based on real ErrorEvent data:
    - affected release(s)
    - first-seen release
    - most recent release
    """
    _, _, issue = get_tenant_issue_or_404(tenant_id, project_id, issue_id, current_user, db)

    release_rows = (
        db.query(ErrorEvent.release)
        .filter(ErrorEvent.issue_id == issue.id, ErrorEvent.release.isnot(None))
        .distinct()
        .all()
    )
    affected = [r[0] for r in release_rows if r[0]]

    first_event = (
        db.query(ErrorEvent.release)
        .filter(ErrorEvent.issue_id == issue.id, ErrorEvent.release.isnot(None))
        .order_by(ErrorEvent.received_at.asc(), ErrorEvent.id.asc())
        .first()
    )
    first_seen_release = first_event[0] if first_event else None

    latest_event = (
        db.query(ErrorEvent.release)
        .filter(ErrorEvent.issue_id == issue.id, ErrorEvent.release.isnot(None))
        .order_by(ErrorEvent.received_at.desc(), ErrorEvent.id.desc())
        .first()
    )
    latest_release = latest_event[0] if latest_event else None

    return {
        "issue_id": issue.id,
        "affected_releases": affected,
        "first_seen_release": first_seen_release,
        "latest_release": latest_release,
    }
