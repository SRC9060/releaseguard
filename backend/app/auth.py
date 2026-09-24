import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Membership, Tenant, User

JWT_SECRET = os.getenv("JWT_SECRET", "releaseguard-super-secret-jwt-key-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "1440"))  # 24 hours

security_bearer = HTTPBearer(auto_error=False)

ROLE_HIERARCHY = {
    "owner": 3,
    "admin": 2,
    "member": 1,
}


def hash_password(password: str) -> str:
    """Hashes plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies plaintext password against stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def hash_token(token: str) -> str:
    """Hashes token with SHA-256 for secure DB storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_invite_token() -> str:
    """Generates a secure random URL-safe token."""
    return secrets.token_urlsafe(32)


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """Generates a signed JWT access token containing user_id and expiration."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=JWT_EXPIRATION_MINUTES))
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodes and validates JWT token."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency: Authenticates user via Bearer JWT token.
    Raises 401 if missing, expired, or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Security(security_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """Optional authentication for backwards-compatible or public endpoints."""
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.get(User, int(user_id))
    except Exception:
        return None


def get_tenant_membership_or_404(
    tenant_id: int,
    user: User,
    db: Session,
    min_role: str = "member",
) -> tuple[Tenant, Membership]:
    """
    Verifies that the authenticated user belongs to the specified tenant with sufficient permissions.
    Returns 404 rather than 403 when the tenant/membership does not exist to avoid resource existence leakage.
    """
    membership = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant_id, Membership.user_id == user.id)
        .first()
    )
    if membership is None:
        # Return 404 so caller cannot infer whether tenant_id exists
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    user_level = ROLE_HIERARCHY.get(membership.role, 0)
    required_level = ROLE_HIERARCHY.get(min_role, 1)
    if user_level < required_level:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Action requires at least '{min_role}' role in this tenant",
        )

    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    return tenant, membership


def ensure_not_last_owner(tenant_id: int, target_user_id: int, db: Session) -> None:
    """
    Guarantees a tenant cannot be left with zero owners.
    Uses database row locking on the parent Tenant row to serialize concurrent owner changes.
    Raises 400 if removing or demoting target_user_id would leave 0 owners.
    """
    # 1. Acquire an exclusive row lock on the parent Tenant row.
    # In PostgreSQL, with_for_update() blocks concurrent transactions targeting the same tenant
    # until this transaction commits or rolls back, serializing all owner count checks.
    if db.bind and db.bind.dialect.name == "postgresql":
        tenant = (
            db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .with_for_update()
            .first()
        )
    else:
        tenant = db.get(Tenant, tenant_id)

    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    target_membership = (
        db.query(Membership)
        .filter(Membership.tenant_id == tenant_id, Membership.user_id == target_user_id)
        .first()
    )
    if target_membership and target_membership.role == "owner":
        owner_count = (
            db.query(Membership)
            .filter(Membership.tenant_id == tenant_id, Membership.role == "owner")
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove or demote the last owner of the tenant",
            )
