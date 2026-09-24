from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user_optional
from app.db import get_db
from app.models import Membership, Project, Tenant, User
from app.schemas import ProjectCreate, ProjectResponse

router = APIRouter(tags=["projects"])


def get_or_create_default_tenant(db: Session) -> Tenant:
    """Ensures a deterministic fallback default tenant exists for development/legacy tests."""
    tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
    if tenant is None:
        tenant = Tenant(name="Default Organization", slug="default")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
    return tenant


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user:
        # If authenticated, associate project with user's primary/first tenant
        membership = (
            db.query(Membership)
            .filter(Membership.user_id == current_user.id)
            .order_by(Membership.id.asc())
            .first()
        )
        tenant_id = membership.tenant_id if membership else get_or_create_default_tenant(db).id
    else:
        tenant = get_or_create_default_tenant(db)
        tenant_id = tenant.id

    project = Project(name=payload.name, tenant_id=tenant_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    if current_user:
        # Return projects belonging to tenants the user is a member of
        tenant_ids = [
            m.tenant_id
            for m in db.query(Membership.tenant_id).filter(Membership.user_id == current_user.id).all()
        ]
        return (
            db.query(Project)
            .filter(Project.tenant_id.in_(tenant_ids))
            .order_by(Project.id.asc())
            .all()
        )

    # Legacy/test mode: list all projects
    return db.query(Project).order_by(Project.id.asc()).all()


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    current_user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if current_user:
        # Verify user is a member of the project's tenant
        is_member = (
            db.query(Membership)
            .filter(
                Membership.tenant_id == project.tenant_id,
                Membership.user_id == current_user.id,
            )
            .first()
            is not None
        )
        if not is_member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    return project
