from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_api_key() -> str:
    return f"rg_live_{uuid.uuid4().hex}"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    memberships = relationship("Membership", back_populates="tenant", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="tenant", cascade="all, delete-orphan")
    invites = relationship("TenantInvite", back_populates="tenant", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),
        Index("ix_memberships_tenant_user", "tenant_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")  # owner, admin, member
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="memberships")
    user = relationship("User", back_populates="memberships")


class TenantInvite(Base):
    __tablename__ = "tenant_invites"
    __table_args__ = (
        Index("ix_tenant_invites_tenant_email", "tenant_id", "email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="invites")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False, default=generate_api_key)

    tenant = relationship("Tenant", back_populates="projects")
    issues = relationship("Issue", back_populates="project", cascade="all, delete-orphan")
    events = relationship("ErrorEvent", back_populates="project", cascade="all, delete-orphan")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("project_id", "fingerprint", name="uq_project_fingerprint"),
        Index("ix_issues_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unresolved")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    muted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_regression: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regressed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    project = relationship("Project", back_populates="issues")
    events = relationship("ErrorEvent", back_populates="issue", cascade="all, delete-orphan")


class ErrorEvent(Base):
    __tablename__ = "error_events"
    __table_args__ = (
        Index("ix_error_events_issue_received", "issue_id", "received_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    exception_type: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    stack_trace: Mapped[str] = mapped_column(Text, nullable=False)
    release: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    project = relationship("Project", back_populates="events")
    issue = relationship("Issue", back_populates="events")


# =========================================================================
# Phase 8: Releases & Feature Flags
# =========================================================================

class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("project_id", "environment", "version", name="uq_project_env_version"),
        Index("ix_releases_project_env", "project_id", "environment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False, default="production")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", backref="releases")


class Environment(Base):
    __tablename__ = "environments"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_project_env_key"),
        Index("ix_environments_project", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", backref="environments")


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_project_flag_key"),
        Index("ix_feature_flags_project", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    project = relationship("Project", backref="feature_flags")
    settings = relationship("FlagSetting", back_populates="flag", cascade="all, delete-orphan")


class FlagSetting(Base):
    __tablename__ = "flag_settings"
    __table_args__ = (
        UniqueConstraint("flag_id", "environment_id", name="uq_flag_env_setting"),
        Index("ix_flag_settings_env", "environment_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flag_id: Mapped[int] = mapped_column(ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_variant: Mapped[str] = mapped_column(String(50), default="off", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    flag = relationship("FeatureFlag", back_populates="settings")
    environment = relationship("Environment")
    rollout = relationship("Rollout", back_populates="setting", uselist=False, cascade="all, delete-orphan")
    rules = relationship("TargetingRule", back_populates="setting", cascade="all, delete-orphan", order_by="TargetingRule.priority.asc()")


class Rollout(Base):
    __tablename__ = "rollouts"
    __table_args__ = (
        UniqueConstraint("flag_id", "environment_id", name="uq_flag_env_rollout"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setting_id: Mapped[int] = mapped_column(ForeignKey("flag_settings.id", ondelete="CASCADE"), nullable=False)
    flag_id: Mapped[int] = mapped_column(ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), nullable=False)
    percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    salt: Mapped[str] = mapped_column(String(32), default=lambda: secrets.token_hex(8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    setting = relationship("FlagSetting", back_populates="rollout")


class TargetingRule(Base):
    __tablename__ = "targeting_rules"
    __table_args__ = (
        Index("ix_targeting_rules_setting", "setting_id", "priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setting_id: Mapped[int] = mapped_column(ForeignKey("flag_settings.id", ondelete="CASCADE"), nullable=False)
    flag_id: Mapped[int] = mapped_column(ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False)
    environment_id: Mapped[int] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attribute: Mapped[str] = mapped_column(String(50), nullable=False)
    operator: Mapped[str] = mapped_column(String(30), nullable=False)
    values: Mapped[str] = mapped_column(Text, nullable=False)
    variant: Mapped[str] = mapped_column(String(50), default="on", nullable=False)

    setting = relationship("FlagSetting", back_populates="rules")


class FlagAuditLog(Base):
    __tablename__ = "flag_audit_logs"
    __table_args__ = (
        Index("ix_flag_audit_logs_flag", "flag_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flag_id: Mapped[int] = mapped_column(ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False)
    environment_id: Mapped[int | None] = mapped_column(ForeignKey("environments.id", ondelete="SET NULL"), nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    before_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    flag = relationship("FeatureFlag")
    environment = relationship("Environment")
    actor = relationship("User")
