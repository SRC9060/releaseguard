"""
Phase 6 Tests: Issue Investigation, Event Analytics, Status Lifecycle, and Regression.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient


# =========================================================================
# Part 1: Event Timeline & Pagination Tests
# =========================================================================

def test_event_timeline_returns_real_events(client: TestClient):
    """Requirement 1: Timeline returns real ErrorEvent records with required fields."""
    proj = client.post("/api/v1/projects", json={"name": "Timeline App"}).json()
    p_id = proj["id"]

    # Ingest 2 events
    resp1 = client.post(
        f"/api/v1/projects/{p_id}/events",
        json={
            "event_id": "evt-uuid-001",
            "exception_type": "ZeroDivisionError",
            "message": "division by zero in worker",
            "stack_trace": "File calc.py line 12",
            "release": "v1.0.0",
        },
    )
    assert resp1.status_code == 201
    issue_id = resp1.json()["issue_id"]

    resp2 = client.post(
        f"/api/v1/projects/{p_id}/events",
        json={
            "event_id": "evt-uuid-002",
            "exception_type": "ZeroDivisionError",
            "message": "division by zero in worker",
            "stack_trace": "File calc.py line 12",
            "release": "v1.0.1",
        },
    )
    assert resp2.status_code == 201

    # Fetch event timeline
    timeline_resp = client.get(f"/api/v1/projects/{p_id}/issues/{issue_id}/events")
    assert timeline_resp.status_code == 200
    data = timeline_resp.json()

    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["has_more"] is False

    # Newest events first: evt-uuid-002 before evt-uuid-001
    assert data["items"][0]["event_id"] == "evt-uuid-002"
    assert data["items"][0]["release"] == "v1.0.1"
    assert data["items"][0]["exception_type"] == "ZeroDivisionError"
    assert data["items"][0]["message"] == "division by zero in worker"
    assert "calc.py" in data["items"][0]["stack_trace"]
    assert "received_at" in data["items"][0]

    assert data["items"][1]["event_id"] == "evt-uuid-001"
    assert data["items"][1]["release"] == "v1.0.0"


def test_event_pagination_works(client: TestClient):
    """Requirement 2: Limit, offset, total, and has_more behave correctly."""
    proj = client.post("/api/v1/projects", json={"name": "Pagination App"}).json()
    p_id = proj["id"]

    # Ingest 5 events
    issue_id = None
    for i in range(5):
        resp = client.post(
            f"/api/v1/projects/{p_id}/events",
            json={
                "event_id": f"page-evt-{i}",
                "exception_type": "TimeoutError",
                "message": f"timeout number {i}",
                "stack_trace": "File conn.py line 45",
            },
        )
        assert resp.status_code == 201
        issue_id = resp.json()["issue_id"]

    # Page 1: limit=2, offset=0
    p1 = client.get(f"/api/v1/projects/{p_id}/issues/{issue_id}/events?limit=2&offset=0").json()
    assert p1["total"] == 5
    assert len(p1["items"]) == 2
    assert p1["limit"] == 2
    assert p1["offset"] == 0
    assert p1["has_more"] is True
    assert p1["items"][0]["event_id"] == "page-evt-4"
    assert p1["items"][1]["event_id"] == "page-evt-3"

    # Page 2: limit=2, offset=2
    p2 = client.get(f"/api/v1/projects/{p_id}/issues/{issue_id}/events?limit=2&offset=2").json()
    assert p2["total"] == 5
    assert len(p2["items"]) == 2
    assert p2["offset"] == 2
    assert p2["has_more"] is True
    assert p2["items"][0]["event_id"] == "page-evt-2"
    assert p2["items"][1]["event_id"] == "page-evt-1"

    # Page 3: limit=2, offset=4
    p3 = client.get(f"/api/v1/projects/{p_id}/issues/{issue_id}/events?limit=2&offset=4").json()
    assert p3["total"] == 5
    assert len(p3["items"]) == 1
    assert p3["offset"] == 4
    assert p3["has_more"] is False
    assert p3["items"][0]["event_id"] == "page-evt-0"


def test_project_issue_mismatch_returns_404(client: TestClient):
    """Requirement 3: Cross-project access or non-existent IDs return 404."""
    p1 = client.post("/api/v1/projects", json={"name": "Project Alpha"}).json()["id"]
    p2 = client.post("/api/v1/projects", json={"name": "Project Beta"}).json()["id"]

    # Create issue in Project Alpha
    ev = client.post(
        f"/api/v1/projects/{p1}/events",
        json={
            "exception_type": "AlphaErr",
            "message": "err",
            "stack_trace": "trace",
        },
    ).json()
    issue_p1 = ev["issue_id"]

    # 1. Access issue_p1 via Project Beta -> 404
    resp = client.get(f"/api/v1/projects/{p2}/issues/{issue_p1}/events")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Issue not found"

    # 2. Access via non-existent project -> 404
    resp = client.get(f"/api/v1/projects/999999/issues/{issue_p1}/events")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"

    # 3. Status mutation on mismatched project/issue -> 404
    resp = client.post(f"/api/v1/projects/{p2}/issues/{issue_p1}/resolve")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Issue not found"


# =========================================================================
# Part 2: Issue Status APIs (Resolve, Mute, Unresolve)
# =========================================================================

def test_resolve_mute_unresolve_lifecycle(client: TestClient):
    """Requirements 4, 5, 6: Status transitions persist correctly with timestamps."""
    proj = client.post("/api/v1/projects", json={"name": "Lifecycle App"}).json()
    p_id = proj["id"]

    ev = client.post(
        f"/api/v1/projects/{p_id}/events",
        json={"exception_type": "KeyError", "message": "'key'", "stack_trace": "tb"},
    ).json()
    issue_id = ev["issue_id"]

    # Initial state: unresolved
    issue = client.get(f"/api/v1/projects/{p_id}/issues/{issue_id}").json()
    assert issue["status"] == "unresolved"
    assert issue["resolved_at"] is None
    assert issue["muted_at"] is None
    assert issue["is_regression"] is False

    # Resolve issue
    resolve_resp = client.post(f"/api/v1/projects/{p_id}/issues/{issue_id}/resolve")
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()
    assert res_data["status"] == "resolved"
    assert res_data["resolved_at"] is not None
    assert res_data["muted_at"] is None

    # Mute issue
    mute_resp = client.post(f"/api/v1/projects/{p_id}/issues/{issue_id}/mute")
    assert mute_resp.status_code == 200
    mute_data = mute_resp.json()
    assert mute_data["status"] == "muted"
    assert mute_data["muted_at"] is not None
    assert mute_data["resolved_at"] is None

    # Unresolve issue
    unresolve_resp = client.post(f"/api/v1/projects/{p_id}/issues/{issue_id}/unresolve")
    assert unresolve_resp.status_code == 200
    unres_data = unresolve_resp.json()
    assert unres_data["status"] == "unresolved"
    assert unres_data["resolved_at"] is None
    assert unres_data["muted_at"] is None


# =========================================================================
# Part 4: Issue List Status Filter
# =========================================================================

def test_status_filter_works(client: TestClient):
    """Requirement 7: ?status= filter works for unresolved, resolved, muted, and rejects invalid."""
    proj = client.post("/api/v1/projects", json={"name": "Filter App"}).json()
    p_id = proj["id"]

    # Create 3 distinct issues
    e1 = client.post(
        f"/api/v1/projects/{p_id}/events",
        json={"exception_type": "Err1", "message": "m1", "stack_trace": "t1"},
    ).json()
    e2 = client.post(
        f"/api/v1/projects/{p_id}/events",
        json={"exception_type": "Err2", "message": "m2", "stack_trace": "t2"},
    ).json()
    e3 = client.post(
        f"/api/v1/projects/{p_id}/events",
        json={"exception_type": "Err3", "message": "m3", "stack_trace": "t3"},
    ).json()

    id1, id2, id3 = e1["issue_id"], e2["issue_id"], e3["issue_id"]

    # id1 remains unresolved
    # id2 -> resolve
    client.post(f"/api/v1/projects/{p_id}/issues/{id2}/resolve")
    # id3 -> mute
    client.post(f"/api/v1/projects/{p_id}/issues/{id3}/mute")

    # All issues (no filter)
    all_issues = client.get(f"/api/v1/projects/{p_id}/issues").json()
    assert len(all_issues) == 3

    # Filter: unresolved
    unres = client.get(f"/api/v1/projects/{p_id}/issues?status=unresolved").json()
    assert len(unres) == 1
    assert unres[0]["id"] == id1

    # Filter: resolved
    res = client.get(f"/api/v1/projects/{p_id}/issues?status=resolved").json()
    assert len(res) == 1
    assert res[0]["id"] == id2

    # Filter: muted
    muted = client.get(f"/api/v1/projects/{p_id}/issues?status=muted").json()
    assert len(muted) == 1
    assert muted[0]["id"] == id3

    # Reject invalid status
    invalid = client.get(f"/api/v1/projects/{p_id}/issues?status=bogus")
    assert invalid.status_code == 400
    assert "Invalid status filter" in invalid.json()["detail"]


# =========================================================================
# Part 3: Regression Detection & Idempotency
# =========================================================================

def test_resolved_issue_becomes_unresolved_on_new_matching_event(client: TestClient):
    """Requirement 8: Resolved issue transitions to unresolved with is_regression=True on new event."""
    proj = client.post("/api/v1/projects", json={"name": "Regression App"}).json()
    p_id = proj["id"]

    trace = "File auth.py line 99 in verify\nValueError: token expired"

    # Event 1: First occurrence
    r1 = client.post(
        f"/api/v1/projects/{p_id}/events",
        json={
            "event_id": "reg-evt-001",
            "exception_type": "ValueError",
            "message": "token expired",
            "stack_trace": trace,
        },
    ).json()
    issue_id = r1["issue_id"]

    # Mark issue as resolved
    client.post(f"/api/v1/projects/{p_id}/issues/{issue_id}/resolve")
    resolved_issue = client.get(f"/api/v1/projects/{p_id}/issues/{issue_id}").json()
    assert resolved_issue["status"] == "resolved"
    assert resolved_issue["is_regression"] is False

    # Event 2: NEW event (new event_id, same stack trace / fingerprint)
    r2 = client.post(
        f"/api/v1/projects/{p_id}/events",
        json={
            "event_id": "reg-evt-002",
            "exception_type": "ValueError",
            "message": "token expired",
            "stack_trace": trace,
        },
    )
    assert r2.status_code == 201

    # Verify Issue has automatically regressed!
    regressed_issue = client.get(f"/api/v1/projects/{p_id}/issues/{issue_id}").json()
    assert regressed_issue["status"] == "unresolved"
    assert regressed_issue["is_regression"] is True
    assert regressed_issue["regressed_at"] is not None
    assert regressed_issue["count"] == 2


def test_same_event_id_redelivery_does_not_trigger_regression(client: TestClient):
    """Requirement 9: Same event_id redelivery is idempotent and does NOT trigger false regression."""
    proj = client.post("/api/v1/projects", json={"name": "Idempotent Regression App"}).json()
    p_id = proj["id"]

    fixed_event_id = "stable-uuid-999"
    trace = "File queue.py line 20\nRuntimeError: queue stall"

    # Event 1: First ingestion
    r1 = client.post(
        f"/api/v1/projects/{p_id}/events",
        json={
            "event_id": fixed_event_id,
            "exception_type": "RuntimeError",
            "message": "queue stall",
            "stack_trace": trace,
        },
    ).json()
    issue_id = r1["issue_id"]

    # Mark issue as resolved
    client.post(f"/api/v1/projects/{p_id}/issues/{issue_id}/resolve")
    resolved_issue = client.get(f"/api/v1/projects/{p_id}/issues/{issue_id}").json()
    assert resolved_issue["status"] == "resolved"
    assert resolved_issue["count"] == 1

    # Redeliver the exact same event_id
    r_dup = client.post(
        f"/api/v1/projects/{p_id}/events",
        json={
            "event_id": fixed_event_id,
            "exception_type": "RuntimeError",
            "message": "queue stall",
            "stack_trace": trace,
        },
    )
    assert r_dup.status_code == 201
    dup_data = r_dup.json()
    assert dup_data["created_new_issue"] is False

    # Verify Issue remains resolved, count remains 1, no false regression!
    issue_after = client.get(f"/api/v1/projects/{p_id}/issues/{issue_id}").json()
    assert issue_after["status"] == "resolved"
    assert issue_after["is_regression"] is False
    assert issue_after["regressed_at"] is None
    assert issue_after["count"] == 1


# =========================================================================
# Part 5: Time Series Analytics Tests
# =========================================================================

def test_issue_specific_timeseries_returns_correct_bucket_counts(client: TestClient):
    """Requirement 10: Issue-specific time series aggregates in PostgreSQL and returns buckets."""
    proj = client.post("/api/v1/projects", json={"name": "TimeSeries Issue App"}).json()
    p_id = proj["id"]

    # Ingest 3 events for this issue
    issue_id = None
    for i in range(3):
        res = client.post(
            f"/api/v1/projects/{p_id}/events",
            json={
                "event_id": f"ts-evt-{i}",
                "exception_type": "TypeError",
                "message": "type error",
                "stack_trace": "File ts.py line 5",
            },
        ).json()
        issue_id = res["issue_id"]

    # Query 1h range
    ts_1h = client.get(f"/api/v1/projects/{p_id}/metrics/issues/{issue_id}/timeseries?range=1h")
    assert ts_1h.status_code == 200
    data_1h = ts_1h.json()
    assert data_1h["range"] == "1h"
    assert data_1h["total_events"] == 3
    assert len(data_1h["buckets"]) == 60  # 60 1-minute buckets
    # Sum of counts across all buckets matches total_events
    assert sum(b["count"] for b in data_1h["buckets"]) == 3

    # Query 24h range
    ts_24h = client.get(f"/api/v1/projects/{p_id}/metrics/issues/{issue_id}/timeseries?range=24h")
    assert ts_24h.status_code == 200
    data_24h = ts_24h.json()
    assert data_24h["range"] == "24h"
    assert data_24h["total_events"] == 3
    assert len(data_24h["buckets"]) == 24  # 24 1-hour buckets
    assert sum(b["count"] for b in data_24h["buckets"]) == 3

    # Query 7d range
    ts_7d = client.get(f"/api/v1/projects/{p_id}/metrics/issues/{issue_id}/timeseries?range=7d")
    assert ts_7d.status_code == 200
    data_7d = ts_7d.json()
    assert data_7d["range"] == "7d"
    assert data_7d["total_events"] == 3
    assert len(data_7d["buckets"]) == 7  # 7 1-day buckets
    assert sum(b["count"] for b in data_7d["buckets"]) == 3

    # Reject invalid range
    invalid = client.get(f"/api/v1/projects/{p_id}/metrics/issues/{issue_id}/timeseries?range=30d")
    assert invalid.status_code == 400


def test_project_timeseries_aggregates_across_issues(client: TestClient):
    """Requirement 11: Project-level time series aggregates across all issues in the project."""
    proj = client.post("/api/v1/projects", json={"name": "TimeSeries Project App"}).json()
    p_id = proj["id"]

    # Ingest 2 events for Issue A
    client.post(
        f"/api/v1/projects/{p_id}/events",
        json={"exception_type": "ErrA", "message": "mA", "stack_trace": "tA"},
    )
    client.post(
        f"/api/v1/projects/{p_id}/events",
        json={"exception_type": "ErrA", "message": "mA", "stack_trace": "tA"},
    )

    # Ingest 3 events for Issue B
    for _ in range(3):
        client.post(
            f"/api/v1/projects/{p_id}/events",
            json={"exception_type": "ErrB", "message": "mB", "stack_trace": "tB"},
        )

    # Project time series should have total_events = 5
    resp = client.get(f"/api/v1/projects/{p_id}/metrics/timeseries?range=24h")
    assert resp.status_code == 200
    data = resp.json()
    assert data["range"] == "24h"
    assert data["total_events"] == 5
    assert sum(b["count"] for b in data["buckets"]) == 5
