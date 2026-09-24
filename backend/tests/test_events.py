import concurrent.futures


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_project_creation(client):
    response = client.post("/api/v1/projects", json={"name": "ReleaseGuard Core"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "ReleaseGuard Core"
    assert "id" in data


def test_new_error_creates_one_issue(client):
    # 1. Create project
    project_resp = client.post("/api/v1/projects", json={"name": "Service A"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    # 2. Ingest error event
    event_payload = {
        "exception_type": "ZeroDivisionError",
        "message": "division by zero",
        "stack_trace": "Traceback (most recent call last):\n  File \"calc.py\", line 10, in div\nZeroDivisionError: division by zero",
        "release": "1.0.0",
    }
    event_resp = client.post(f"/api/v1/projects/{project_id}/events", json=event_payload)
    assert event_resp.status_code == 201
    event_data = event_resp.json()

    assert event_data["created_new_issue"] is True
    assert event_data["issue_count"] == 1
    assert "fingerprint" in event_data
    assert "issue_id" in event_data

    # 3. List issues and verify single issue created
    issues_resp = client.get(f"/api/v1/projects/{project_id}/issues")
    assert issues_resp.status_code == 200
    issues = issues_resp.json()

    assert len(issues) == 1
    issue = issues[0]
    assert issue["id"] == event_data["issue_id"]
    assert issue["fingerprint"] == event_data["fingerprint"]
    assert issue["count"] == 1
    assert issue["title"] == "ZeroDivisionError: division by zero"
    assert issue["project_id"] == project_id


def test_same_error_twice_creates_one_issue_with_count_two(client):
    # 1. Create project
    project_resp = client.post("/api/v1/projects", json={"name": "Service B"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    event_payload = {
        "exception_type": "ValueError",
        "message": "invalid literal for int()",
        "stack_trace": "Traceback (most recent call last):\n  File \"parser.py\", line 42, in parse\nValueError",
        "release": "1.0.0",
    }

    # 2. First ingestion
    first_resp = client.post(f"/api/v1/projects/{project_id}/events", json=event_payload)
    assert first_resp.status_code == 201
    first_data = first_resp.json()
    assert first_data["created_new_issue"] is True
    assert first_data["issue_count"] == 1

    # 3. Second identical ingestion
    second_resp = client.post(f"/api/v1/projects/{project_id}/events", json=event_payload)
    assert second_resp.status_code == 201
    second_data = second_resp.json()
    assert second_data["created_new_issue"] is False
    assert second_data["issue_count"] == 2
    assert second_data["issue_id"] == first_data["issue_id"]
    assert second_data["fingerprint"] == first_data["fingerprint"]

    # 4. List issues: should still be exactly 1 issue with count=2
    issues_resp = client.get(f"/api/v1/projects/{project_id}/issues")
    assert issues_resp.status_code == 200
    issues = issues_resp.json()

    assert len(issues) == 1
    assert issues[0]["id"] == first_data["issue_id"]
    assert issues[0]["count"] == 2


def test_different_errors_create_different_issues(client):
    # 1. Create project
    project_resp = client.post("/api/v1/projects", json={"name": "Service C"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    event_a = {
        "exception_type": "ValueError",
        "message": "value is invalid",
        "stack_trace": "Traceback:\n  File \"app/a.py:10:1\"\nValueError: value is invalid",
        "release": "1.0.0",
    }
    event_b = {
        "exception_type": "KeyError",
        "message": "'missing_key'",
        "stack_trace": "Traceback:\n  File \"app/b.py:25:2\"\nKeyError: 'missing_key'",
        "release": "1.0.0",
    }

    # Ingest error A
    resp_a = client.post(f"/api/v1/projects/{project_id}/events", json=event_a)
    assert resp_a.status_code == 201
    data_a = resp_a.json()
    assert data_a["created_new_issue"] is True
    assert data_a["issue_count"] == 1

    # Ingest error B
    resp_b = client.post(f"/api/v1/projects/{project_id}/events", json=event_b)
    assert resp_b.status_code == 201
    data_b = resp_b.json()
    assert data_b["created_new_issue"] is True
    assert data_b["issue_count"] == 1

    # Fingerprints and issue IDs must differ
    assert data_a["fingerprint"] != data_b["fingerprint"]
    assert data_a["issue_id"] != data_b["issue_id"]

    # Listing issues should show both issues
    issues_resp = client.get(f"/api/v1/projects/{project_id}/issues")
    assert issues_resp.status_code == 200
    issues = issues_resp.json()

    assert len(issues) == 2
    issue_ids = {issue["id"] for issue in issues}
    assert data_a["issue_id"] in issue_ids
    assert data_b["issue_id"] in issue_ids


def test_fingerprint_normalization_across_dynamic_data(client):
    project_resp = client.post("/api/v1/projects", json={"name": "Service D"})
    project_id = project_resp.json()["id"]

    # Two traces with different line numbers, UUIDs, and memory addresses
    trace_1 = (
        "Traceback:\n"
        "  File \"service.py:100:15\"\n"
        "Object at 0x7ffd98b0 with id 123e4567-e89b-12d3-a456-426614174000 failed"
    )
    trace_2 = (
        "Traceback:\n"
        "  File \"service.py:350:8\"\n"
        "Object at 0x7ffd11aa with id 987fcdeb-51a2-43d7-9012-345678901234 failed"
    )

    event_1 = {
        "exception_type": "ConnectionError",
        "message": "failed to connect",
        "stack_trace": trace_1,
    }
    event_2 = {
        "exception_type": "ConnectionError",
        "message": "failed to connect",
        "stack_trace": trace_2,
    }

    resp_1 = client.post(f"/api/v1/projects/{project_id}/events", json=event_1)
    resp_2 = client.post(f"/api/v1/projects/{project_id}/events", json=event_2)

    assert resp_1.status_code == 201
    assert resp_2.status_code == 201

    assert resp_1.json()["fingerprint"] == resp_2.json()["fingerprint"]
    assert resp_2.json()["created_new_issue"] is False
    assert resp_2.json()["issue_count"] == 2


def test_project_not_found(client):
    # Ingest event for non-existent project
    resp = client.post(
        "/api/v1/projects/99999/events",
        json={
            "exception_type": "RuntimeError",
            "message": "boom",
            "stack_trace": "boom",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"

    # List issues for non-existent project
    resp = client.get("/api/v1/projects/99999/issues")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


def test_concurrent_identical_error_events_create_single_issue(client):
    # 1. Create project
    project_resp = client.post("/api/v1/projects", json={"name": "Concurrency App"})
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]

    event_payload = {
        "exception_type": "DatabaseConnectionTimeout",
        "message": "Connection to replica pool timed out after 3000ms",
        "stack_trace": "Traceback (most recent call last):\n  File \"db/pool.py:88:12\"\nTimeoutError",
        "release": "2.0.0",
    }

    num_concurrent_requests = 100

    def send_event(_):
        return client.post(f"/api/v1/projects/{project_id}/events", json=event_payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        responses = list(executor.map(send_event, range(num_concurrent_requests)))

    # 1. Verify all responses succeeded
    status_codes = [r.status_code for r in responses]
    assert all(code == 201 for code in status_codes), f"Not all requests returned 201: {status_codes}"

    # 2. Verify all successful events point to that exact same issue
    issue_ids = {r.json()["issue_id"] for r in responses}
    assert len(issue_ids) == 1, f"Expected 1 unique issue ID, got: {issue_ids}"
    shared_issue_id = issue_ids.pop()

    # 3. Verify exactly one issue exists in the database
    issues_resp = client.get(f"/api/v1/projects/{project_id}/issues")
    assert issues_resp.status_code == 200
    issues = issues_resp.json()

    assert len(issues) == 1, "There must be exactly one issue row in the database"
    issue = issues[0]
    assert issue["id"] == shared_issue_id

    # 4. Verify issue occurrence count equals the number of successful events
    assert issue["count"] == num_concurrent_requests

    # 5. Verify created_new_issue was True exactly once
    new_issue_flags = [r.json()["created_new_issue"] for r in responses]
    assert new_issue_flags.count(True) == 1
    assert new_issue_flags.count(False) == num_concurrent_requests - 1
