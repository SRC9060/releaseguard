from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field


# =========================================================================
# Authentication & User Schemas
# =========================================================================

class UserRegister(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    tenant_name: str | None = Field(default=None, max_length=200)


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    role: str | None = None
    created_at: datetime


class UserMeResponse(BaseModel):
    id: int
    email: str
    tenants: list[TenantResponse]


# =========================================================================
# Tenant & Membership Schemas
# =========================================================================

class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=100)


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    user_id: int
    email: str | None = None
    role: str
    created_at: datetime


class MembershipUpdate(BaseModel):
    role: str = Field(pattern="^(owner|admin|member)$")


class InviteCreate(BaseModel):
    email: str
    role: str = Field(default="member", pattern="^(owner|admin|member)$")


class InviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    email: str
    role: str
    token: str | None = None
    expires_at: datetime
    created_at: datetime


class InviteAcceptResponse(BaseModel):
    status: str = "accepted"
    tenant_id: int
    tenant_name: str
    role: str


# =========================================================================
# Project Schemas
# =========================================================================

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tenant_id: int | None = None
    api_key: str | None = None


# =========================================================================
# Error Event & Ingestion Schemas
# =========================================================================

class ErrorEventCreate(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    exception_type: str
    message: str
    stack_trace: str
    release: str | None = None


class BulkErrorEventsCreate(BaseModel):
    events: list[ErrorEventCreate] = Field(..., min_length=1, max_length=500)


class BulkIngestResponse(BaseModel):
    status: str = "accepted"
    accepted_count: int
    rejected_count: int = 0
    batch_id: str
    project_id: int


class ErrorEventResponse(BaseModel):
    event_id: int
    issue_id: int
    fingerprint: str
    issue_count: int
    created_new_issue: bool
    received_at: datetime


# =========================================================================
# Issue Schemas
# =========================================================================

class IssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    fingerprint: str
    title: str
    count: int
    status: str = "unresolved"
    resolved_at: datetime | None = None
    muted_at: datetime | None = None
    is_regression: bool = False
    regressed_at: datetime | None = None
    first_seen: datetime
    last_seen: datetime


class IssueEventItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    exception_type: str
    message: str
    stack_trace: str
    release: str | None = None
    received_at: datetime


class PaginatedEventsResponse(BaseModel):
    items: list[IssueEventItem]
    total: int
    limit: int
    offset: int
    has_more: bool


class TimeSeriesBucket(BaseModel):
    timestamp: str
    count: int


class TimeSeriesResponse(BaseModel):
    range: str
    total_events: int
    buckets: list[TimeSeriesBucket]


# =========================================================================
# Phase 8: Releases & Feature Flag Schemas
# =========================================================================

class ReleaseCreate(BaseModel):
    version: str = Field(min_length=1, max_length=100)
    commit_sha: str | None = Field(default=None, max_length=40)
    environment: str = Field(default="production", min_length=1, max_length=50)


class ReleaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    version: str
    commit_sha: str | None = None
    environment: str
    created_at: datetime


class EnvironmentCreate(BaseModel):
    key: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)


class EnvironmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    key: str
    name: str
    created_at: datetime


class FeatureFlagCreate(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class FeatureFlagUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class RolloutUpdate(BaseModel):
    percentage: int = Field(ge=0, le=100)
    salt: str | None = None


class TargetingRuleInput(BaseModel):
    priority: int = 0
    attribute: str = Field(min_length=1, max_length=50)
    operator: str = Field(min_length=1, max_length=30)
    values: list[str]
    variant: str = "on"


class TargetingRuleResponse(BaseModel):
    id: int
    priority: int
    attribute: str
    operator: str
    values: list[str]
    variant: str


class FlagSettingResponse(BaseModel):
    id: int
    flag_id: int
    environment_id: int
    environment_key: str
    enabled: bool
    default_variant: str
    rollout_percentage: int
    rollout_salt: str
    rules: list[TargetingRuleResponse] = []


class FeatureFlagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    key: str
    name: str
    description: str | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    settings: list[FlagSettingResponse] = []


class FlagAuditLogResponse(BaseModel):
    id: int
    flag_id: int
    environment_id: int | None = None
    actor_id: int | None = None
    actor_email: str | None = None
    action: str
    before_state: str | None = None
    after_state: str | None = None
    created_at: datetime


class FlagEvaluationResult(BaseModel):
    enabled: bool
    variant: str
    reason: str | None = None
    percentage: int | None = None
    salt: str | None = None


class ConfigDocumentResponse(BaseModel):
    environment: str
    flags: dict[str, FlagEvaluationResult]
