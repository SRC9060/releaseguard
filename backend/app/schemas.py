from datetime import datetime, timezone
import uuid

from pydantic import (
    BaseModel as _PydanticBaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)


class BaseModel(_PydanticBaseModel):
    """
    ReleaseGuard base model ensuring all datetimes are explicitly timezone-aware
    in UTC and serialized to ISO 8601 with the 'Z' suffix.
    """

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def _ensure_utc_aware(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        return v

    @field_serializer("*", when_used="always", check_fields=False)
    def _serialize_utc_datetime(self, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            else:
                v = v.astimezone(timezone.utc)
            return v.isoformat().replace("+00:00", "Z")
        return v


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


class TenantUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


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


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tenant_id: int | None = None
    api_key: str | None = None
    issues_count: int | None = None
    releases_count: int | None = None
    environments_count: int | None = None
    recent_release: str | None = None


class ProjectKeyResponse(BaseModel):
    project_id: int
    api_key: str


class TestEventResponse(BaseModel):
    status: str
    event_id: str
    issue_id: int | None = None
    timestamp: datetime | str | None = None
    message: str


# =========================================================================
# Error Event & Ingestion Schemas
# =========================================================================

class ErrorEventCreate(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=64)
    exception_type: str = Field(min_length=1, max_length=256)
    message: str = Field(..., max_length=2000)
    stack_trace: str = Field(..., max_length=100000)
    release: str | None = Field(default=None, max_length=100)


class BulkErrorEventsCreate(BaseModel):
    events: list[ErrorEventCreate] = Field(..., min_length=1, max_length=100)


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


# =========================================================================
# Phase 9: Incident Response & Controlled Mitigation Schemas
# =========================================================================

class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    environment: str = "production"
    severity: str = "medium"  # low, medium, high, critical
    related_issue_id: int | None = None
    related_release_id: int | None = None
    related_feature_flag_id: int | None = None
    assigned_to: int | None = None


class IncidentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    severity: str | None = None
    status: str | None = None  # triggered, investigating, mitigated, resolved, closed
    assigned_to: int | None = None
    related_issue_id: int | None = None
    related_release_id: int | None = None
    related_feature_flag_id: int | None = None


class IncidentEventCreate(BaseModel):
    event_type: str = "note_added"
    message: str = Field(min_length=1)
    metadata: dict | None = None


class IncidentEventResponse(BaseModel):
    id: int
    incident_id: int
    actor_id: int | None = None
    actor_email: str | None = None
    event_type: str
    message: str
    metadata: dict | None = None
    created_at: datetime


class IncidentMitigationResponse(BaseModel):
    id: int
    incident_id: int
    action_type: str
    target_flag_id: int | None = None
    target_flag_key: str | None = None
    target_environment_id: int | None = None
    target_environment_key: str | None = None
    reason: str
    confidence: float
    status: str
    approved_by: int | None = None
    approved_by_email: str | None = None
    approved_at: datetime | None = None
    executed_at: datetime | None = None
    execution_result: dict | None = None
    created_at: datetime
    updated_at: datetime


class CorrelatedChange(BaseModel):
    type: str  # "release" or "feature_flag"
    item_id: int
    title: str
    description: str | None = None
    relationship: str  # "correlated release", "recent flag change", "possible contributor"
    changed_at: datetime
    metadata: dict = {}


class IncidentResponse(BaseModel):
    id: int
    tenant_id: int
    project_id: int
    environment: str
    title: str
    description: str | None = None
    severity: str
    status: str
    related_issue_id: int | None = None
    related_issue_title: str | None = None
    related_release_id: int | None = None
    related_release_version: str | None = None
    related_feature_flag_id: int | None = None
    related_feature_flag_key: str | None = None
    created_by: int | None = None
    created_by_email: str | None = None
    assigned_to: int | None = None
    assigned_to_email: str | None = None
    started_at: datetime
    mitigated_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    timeline: list[IncidentEventResponse] = []
    mitigations: list[IncidentMitigationResponse] = []
    correlated_changes: list[CorrelatedChange] = []


class SpikeDetectionResult(BaseModel):
    is_spike: bool
    issue_id: int
    environment: str
    current_count: int
    baseline_count: int
    current_rate: float
    baseline_rate: float
    spike_ratio: float
    threshold: float
    incident_created: bool = False
    incident_id: int | None = None
    reason: str | None = None

