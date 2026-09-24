from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


import uuid


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
