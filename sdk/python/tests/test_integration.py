"""
End-to-End Integration test for ReleaseGuard Python SDK.
Tests Requirement I: Repeated identical exceptions are delivered to the
backend and grouped into 1 issue with count=100.
"""

import time
from typing import Any
import pytest
from fastapi.testclient import TestClient

from app.main import app
import releaseguard_sdk
from releaseguard_sdk.transport import BaseTransport, PermanentClientError, TransientTransportError
from releaseguard_sdk.event import Event


class AppTestClientTransport(BaseTransport):
    """
    Direct transport adapter to FastAPI TestClient for end-to-end integration testing.
    Validates full serialization, HTTP routing, PostgreSQL upsert, and grouping.
    """

    def __init__(self, test_client: TestClient, project_id: int):
        self.test_client = test_client
        self.project_id = project_id

    def send_event(self, event: Event) -> dict[str, Any]:
        resp = self.test_client.post(
            f"/api/v1/projects/{self.project_id}/events",
            json=event.to_dict(),
        )
        if resp.status_code == 201:
            return resp.json()
        elif 400 <= resp.status_code < 500:
            raise PermanentClientError(f"HTTP {resp.status_code}: {resp.text}")
        else:
            raise TransientTransportError(f"HTTP {resp.status_code}: {resp.text}")

    def send_batch(self, events: list[Event]) -> dict[str, Any]:
        resp = self.test_client.post(
            f"/api/v1/projects/{self.project_id}/events/bulk",
            json={"events": [e.to_dict() for e in events]},
        )
        if resp.status_code in (200, 201, 202):
            return resp.json()
        elif 400 <= resp.status_code < 500:
            raise PermanentClientError(f"HTTP {resp.status_code}: {resp.text}")
        else:
            raise TransientTransportError(f"HTTP {resp.status_code}: {resp.text}")


@pytest.fixture
def override_test_queue():
    import fakeredis
    from app.queue import EventQueue, get_queue
    fake_client = fakeredis.FakeRedis(decode_responses=True)
    test_queue = EventQueue(redis_client=fake_client)
    app.dependency_overrides[get_queue] = lambda: test_queue
    yield test_queue
    app.dependency_overrides.pop(get_queue, None)


def test_requirement_i_sdk_groups_repeated_identical_exceptions_into_single_issue(client, override_test_queue):
    """
    Requirement I: 100 identical exceptions captured via the SDK must result
    in exactly 1 issue with count = 100 in ReleaseGuard backend.
    """
    # 1. Create a project in the backend
    proj_resp = client.post("/api/v1/projects", json={"name": "SDK Integration Test App"})
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # 2. Initialize the SDK with the integration transport
    transport = AppTestClientTransport(client, project_id)
    sdk_client = releaseguard_sdk.init(
        project_id=project_id,
        release="2.0.0",
        flush_interval=0.02,
        batch_size=20,
        transport=transport,
    )

    num_exceptions = 100

    def trigger_error():
        raise TimeoutError("inventory lock acquisition timeout")

    # 3. Simulate application capturing 100 identical exceptions
    for i in range(num_exceptions):
        try:
            trigger_error()
        except TimeoutError:
            releaseguard_sdk.capture_exception()

    # 4. Flush the background worker
    flushed = releaseguard_sdk.flush(timeout=5.0)
    assert flushed is True

    # 4b. Run server-side IngestionWorker to process Redis stream events into PostgreSQL
    from app.worker import IngestionWorker
    server_worker = IngestionWorker(queue=override_test_queue)
    while True:
        processed = server_worker.process_next_batch(batch_size=50)
        if processed == 0:
            break

    # 5. Verify SDK counters
    stats = sdk_client.stats
    assert stats.queued == num_exceptions
    assert stats.sent == num_exceptions
    assert stats.dropped == 0
    assert stats.failed == 0

    # 6. Verify backend database state
    issues_resp = client.get(f"/api/v1/projects/{project_id}/issues")
    assert issues_resp.status_code == 200
    issues = issues_resp.json()

    # Invariant: 100 identical errors -> exactly 1 issue with count=100
    assert len(issues) == 1, f"Expected 1 grouped issue, found {len(issues)}"
    issue = issues[0]
    assert issue["count"] == num_exceptions
    assert "TimeoutError" in issue["title"]

    releaseguard_sdk.shutdown(timeout=1.0)
