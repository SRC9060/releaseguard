"""
Releases API routes.
Authenticated tenant-scoped endpoints:
- POST /api/v1/tenants/{tenant_id}/projects/{project_id}/releases (owner/admin)
- GET /api/v1/tenants/{tenant_id}/projects/{project_id}/releases (members)
- GET /api/v1/tenants/{tenant_id}/projects/{project_id}/releases/{release_id} (members)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Release, User
from app.routes.tenants import get_tenant_project_or_404
from app.schemas import ReleaseCreate, ReleaseResponse

router = APIRouter(prefix="/tenants/{tenant_id}/projects/{project_id}/releases", tags=["releases"])


@router.post(
    "",
    response_model=ReleaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_release(
    tenant_id: int,
    project_id: int,
    payload: ReleaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="admin")

    version = payload.version.strip()
    env = payload.environment.strip().lower()

    # Check for existing release with same project_id, environment, version
    existing = (
        db.query(Release)
        .filter(
            Release.project_id == project.id,
            Release.environment == env,
            Release.version == version,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Release version '{version}' already exists for environment '{env}'",
        )

    release = Release(
        project_id=project.id,
        version=version,
        commit_sha=payload.commit_sha.strip() if payload.commit_sha else None,
        environment=env,
    )
    db.add(release)
    db.commit()
    db.refresh(release)
    return release


@router.get(
    "",
    response_model=list[ReleaseResponse],
)
def list_releases(
    tenant_id: int,
    project_id: int,
    environment: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")

    query = db.query(Release).filter(Release.project_id == project.id)
    if environment:
        query = query.filter(Release.environment == environment.strip().lower())

    return query.order_by(Release.created_at.desc(), Release.id.desc()).offset(offset).limit(limit).all()


@router.get(
    "/{release_id}",
    response_model=ReleaseResponse,
)
def get_release(
    tenant_id: int,
    project_id: int,
    release_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _, project = get_tenant_project_or_404(tenant_id, project_id, current_user, db, min_role="member")

    release = (
        db.query(Release)
        .filter(Release.id == release_id, Release.project_id == project.id)
        .first()
    )
    if release is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found")

    return release
