import re
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.db import get_db
from app.models import Membership, Tenant, User
from app.schemas import (
    TenantResponse,
    TokenResponse,
    UserLogin,
    UserMeResponse,
    UserRegister,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def slugify(text: str) -> str:
    """Creates a URL-safe lowercase slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", text)


def generate_unique_slug(name: str, db: Session) -> str:
    """Generates an available unique tenant slug."""
    base_slug = slugify(name) or "org"
    slug = base_slug
    attempt = 1
    while db.query(Tenant).filter(Tenant.slug == slug).first() is not None:
        random_suffix = secrets.token_hex(2)
        slug = f"{base_slug}-{random_suffix}"
        attempt += 1
        if attempt > 10:
            slug = f"{base_slug}-{secrets.token_hex(4)}"
            break
    return slug


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if "@" not in email or len(email) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid email address is required",
        )

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    # 1. Create User
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.flush()

    # 2. Automatically create initial Tenant and assign user as Owner
    tenant_name = payload.tenant_name.strip() if payload.tenant_name else f"{email.split('@')[0].capitalize()}'s Team"
    slug = generate_unique_slug(tenant_name, db)

    tenant = Tenant(
        name=tenant_name,
        slug=slug,
    )
    db.add(tenant)
    db.flush()

    # 3. Create Owner Membership
    membership = Membership(
        tenant_id=tenant.id,
        user_id=user.id,
        role="owner",
    )
    db.add(membership)

    # 4. If Default Organization (id=1) exists and has no owner yet, grant initial user ownership
    default_tenant = db.get(Tenant, 1)
    if default_tenant and default_tenant.id != tenant.id:
        has_default_owner = (
            db.query(Membership)
            .filter(Membership.tenant_id == default_tenant.id, Membership.role == "owner")
            .first()
            is not None
        )
        if not has_default_owner:
            db.add(Membership(tenant_id=default_tenant.id, user_id=user.id, role="owner"))

    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
        ),
    )


from app.auth_limiter import auth_limiter


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()

    if auth_limiter.is_locked(email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Account temporarily locked. Please try again later.",
        )

    user = db.query(User).filter(User.email == email).first()

    if user is None or not verify_password(payload.password, user.password_hash):
        auth_limiter.record_failure(email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_limiter.reset(email)
    token = create_access_token(user.id)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
        ),
    )


@router.get(
    "/me",
    response_model=UserMeResponse,
)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Fetch all tenants the current user is a member of
    memberships = (
        db.query(Membership, Tenant)
        .join(Tenant, Membership.tenant_id == Tenant.id)
        .filter(Membership.user_id == current_user.id)
        .all()
    )

    tenants = [
        TenantResponse(
            id=t.id,
            name=t.name,
            slug=t.slug,
            role=m.role,
            created_at=t.created_at,
        )
        for m, t in memberships
    ]

    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        tenants=tenants,
    )
