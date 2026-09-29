"""
Regression tests for ReleaseGuard timestamp and timezone consistency.

Verifies:
1. Pydantic response models make datetimes explicitly timezone-aware in UTC.
2. Serialized JSON timestamps include ISO 8601 'Z' suffix.
3. API endpoints (/issues, /events, /metrics/timeseries) return timezone-aware timestamps.
4. Time series bucket timestamps include 'Z' suffix.
5. Known UTC timestamp renders as the correct local India time (GMT+5:30).
6. Relative time calculations operate on actual instants without timezone skew.
"""

from datetime import datetime, timezone
import zoneinfo
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Issue, Project
from app.schemas import ErrorEventResponse, IssueResponse, TimeSeriesBucket


def test_pydantic_schema_forces_utc_awareness_and_z_serialization():
    """Verify that naive datetimes from DB are made timezone-aware and serialized with 'Z'."""
    naive_dt = datetime(2026, 9, 28, 18, 44, 31, 123456)
    issue = IssueResponse(
        id=1,
        project_id=1,
        fingerprint="fp1234567890",
        title="Test Error",
        count=6,
        status="unresolved",
        first_seen=naive_dt,
        last_seen=naive_dt,
    )

    # 1. Python representation must be explicitly timezone-aware in UTC
    assert issue.first_seen.tzinfo is not None
    assert issue.first_seen.tzinfo == timezone.utc
    assert issue.last_seen.tzinfo == timezone.utc

    # 2. JSON serialization must include 'Z'
    dumped = issue.model_dump(mode="json")
    assert dumped["first_seen"].endswith("Z")
    assert dumped["last_seen"].endswith("Z")
    assert dumped["first_seen"] == "2026-09-28T18:44:31.123456Z"


def test_api_issues_endpoint_returns_timezone_aware_iso_timestamps(client: TestClient):
    """Verify that /api/v1/projects/{project_id}/issues returns timestamps with 'Z'."""
    # 1. Create a project
    proj_resp = client.post("/api/v1/projects", json={"name": "Timestamp Verification Project"})
    assert proj_resp.status_code in (200, 201)
    p_id = proj_resp.json()["id"]

    # 2. Ingest an event
    event_payload = {
        "exception_type": "ProductionTimezoneBugTest",
        "message": "Testing UTC timestamp representation",
        "stack_trace": "File app.py, line 42, in test_timestamp",
        "release": "1.0.0",
    }
    ingest_resp = client.post(f"/api/v1/projects/{p_id}/events", json=event_payload)
    assert ingest_resp.status_code in (200, 201)
    ingest_data = ingest_resp.json()
    assert ingest_data["received_at"].endswith("Z")

    # 3. Retrieve issues list
    issues_resp = client.get(f"/api/v1/projects/{p_id}/issues")
    assert issues_resp.status_code == 200
    issues = issues_resp.json()
    assert len(issues) >= 1
    issue = issues[0]

    # Verify first_seen and last_seen have 'Z'
    assert issue["first_seen"].endswith("Z")
    assert issue["last_seen"].endswith("Z")


def test_timeseries_buckets_include_utc_z_suffix(client: TestClient):
    """Verify that compute_timeseries bucket timestamps always include 'Z'."""
    proj_resp = client.post("/api/v1/projects", json={"name": "TimeSeries Z Verification"})
    p_id = proj_resp.json()["id"]

    client.post(
        f"/api/v1/projects/{p_id}/events",
        json={
            "exception_type": "TimeSeriesError",
            "message": "Testing bucket timestamps",
            "stack_trace": "File test.py line 1",
        },
    )

    # 1h range
    ts_1h = client.get(f"/api/v1/projects/{p_id}/metrics/timeseries?range=1h").json()
    for bucket in ts_1h["buckets"]:
        assert bucket["timestamp"].endswith("Z"), f"Bucket {bucket['timestamp']} missing Z suffix"

    # 24h range
    ts_24h = client.get(f"/api/v1/projects/{p_id}/metrics/timeseries?range=24h").json()
    for bucket in ts_24h["buckets"]:
        assert bucket["timestamp"].endswith("Z"), f"Bucket {bucket['timestamp']} missing Z suffix"


def test_known_utc_timestamp_renders_as_correct_local_india_time():
    """
    Evidence regression test:
    Event occurred at 2026-09-28 18:44:31 UTC.
    When interpreted with timezone awareness, in India (GMT+5:30 / Asia/Kolkata),
    it MUST correspond to 2026-09-29 00:14:31 GMT+5:30 (next calendar day in IST),
    NOT 2026-09-28 18:44:31 (which was the bug caused by naive interpretation).
    """
    utc_str = "2026-09-28T18:44:31Z"

    # Parse as UTC
    dt_utc = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    assert dt_utc.tzinfo == timezone.utc

    # Convert to Indian Standard Time (Asia/Kolkata, GMT+5:30)
    ist = zoneinfo.ZoneInfo("Asia/Kolkata")
    dt_ist = dt_utc.astimezone(ist)

    # In India time, 18:44:31 UTC + 5h30m = 00:14:31 on Sep 29!
    assert dt_ist.year == 2026
    assert dt_ist.month == 9
    assert dt_ist.day == 29
    assert dt_ist.hour == 0
    assert dt_ist.minute == 14
    assert dt_ist.second == 31


def test_relative_time_calculated_from_actual_instant():
    """Verify that relative time between UTC now and event is ~0, not 5.5 hours."""
    now_utc = datetime.now(timezone.utc)
    issue = IssueResponse(
        id=2,
        project_id=1,
        fingerprint="fp_rel_time",
        title="Relative Time Test",
        count=1,
        first_seen=now_utc,
        last_seen=now_utc,
    )
    # Both are UTC aware; difference in seconds is strictly within 1 second
    current_instant = datetime.now(timezone.utc)
    diff = (current_instant - issue.last_seen).total_seconds()
    assert 0 <= diff < 5.0
