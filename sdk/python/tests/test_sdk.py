"""
Unit tests for ReleaseGuard Python SDK.
Tests all requirements A through H using mocked transports.
"""

import threading
import time
from typing import Any
import pytest

import releaseguard_sdk
from releaseguard_sdk.config import Config
from releaseguard_sdk.client import ReleaseGuardClient
from releaseguard_sdk.event import Event, build_event_from_exc, build_event_from_message
from releaseguard_sdk.transport import (
    BaseTransport,
    PermanentClientError,
    TransientTransportError,
)


class MockTransport(BaseTransport):
    def __init__(self, delay: float = 0.0, error_to_raise: Exception | None = None):
        self.delay = delay
        self.error_to_raise = error_to_raise
        self.sent_events: list[Event] = []
        self.call_threads: list[str] = []
        self.attempts = 0
        self.lock = threading.Lock()

    def send_event(self, event: Event) -> dict[str, Any]:
        with self.lock:
            self.attempts += 1
            self.call_threads.append(threading.current_thread().name)
            if self.delay > 0:
                time.sleep(self.delay)

            if self.error_to_raise:
                raise self.error_to_raise

            self.sent_events.append(event)
            return {"event_id": len(self.sent_events), "status": "ok"}


def test_requirement_a_capture_exception_creates_valid_payload():
    """Requirement A: capture_exception creates an event payload."""
    event = None
    try:
        raise ValueError("Invalid configuration parameter")
    except ValueError:
        event = build_event_from_exc(release="1.0.0")

    assert event is not None
    assert event.exception_type == "ValueError"
    assert event.message == "Invalid configuration parameter"
    assert "Traceback" in event.stack_trace
    assert "test_requirement_a_capture_exception_creates_valid_payload" in event.stack_trace
    assert event.release == "1.0.0"

    event_dict = event.to_dict()
    assert event_dict["exception_type"] == "ValueError"
    assert event_dict["message"] == "Invalid configuration parameter"
    assert event_dict["release"] == "1.0.0"


def test_requirement_b_capture_exception_does_not_perform_sync_network_io():
    """Requirement B: capture_exception does not perform synchronous network I/O."""
    # Transport with an intentional 0.2s blocking delay
    slow_transport = MockTransport(delay=0.2)
    config = Config(project_id=1, flush_interval=0.01)
    client = ReleaseGuardClient(config=config, transport=slow_transport)

    main_thread_name = threading.current_thread().name

    t0 = time.perf_counter()
    try:
        raise RuntimeError("Non-blocking test error")
    except RuntimeError:
        client.capture_exception()
    t1 = time.perf_counter()

    elapsed = t1 - t0
    # Enqueue should take < 10ms, far less than the 200ms transport delay
    assert elapsed < 0.05, f"capture_exception took {elapsed*1000:.2f}ms, expected sub-millisecond execution"

    # Flush the background thread
    client.flush(timeout=1.0)
    assert len(slow_transport.sent_events) == 1

    # Network call must have happened on worker thread, NOT main thread
    assert slow_transport.call_threads[0] == "ReleaseGuardWorker"
    assert slow_transport.call_threads[0] != main_thread_name

    client.shutdown(timeout=1.0)


def test_requirement_c_background_worker_sends_event_successfully():
    """Requirement C: background worker sends an event successfully."""
    transport = MockTransport()
    config = Config(project_id=1, flush_interval=0.01)
    client = ReleaseGuardClient(config=config, transport=transport)

    try:
        raise KeyError("missing_auth_header")
    except KeyError:
        client.capture_exception()

    success = client.flush(timeout=2.0)
    assert success is True
    assert len(transport.sent_events) == 1
    assert transport.sent_events[0].exception_type == "KeyError"
    assert client.stats.sent == 1
    assert client.stats.queued == 1

    client.shutdown(timeout=1.0)


def test_requirement_d_api_unavailable_never_raises_to_host_app():
    """Requirement D: ReleaseGuard API being unavailable does not raise an exception to the host application."""
    failing_transports = [
        MockTransport(error_to_raise=TransientTransportError("Connection refused: 127.0.0.1:8000")),
        MockTransport(error_to_raise=PermanentClientError("HTTP 404 Project Not Found")),
        MockTransport(error_to_raise=TimeoutError("Request timed out")),
        MockTransport(error_to_raise=Exception("Catastrophic unexpected network failure")),
    ]

    for transport in failing_transports:
        config = Config(project_id=1, max_retries=1, retry_backoff=0.01, flush_interval=0.01)
        client = ReleaseGuardClient(config=config, transport=transport)

        # MUST NEVER raise an exception to the caller
        try:
            raise ZeroDivisionError("Crash scenario")
        except ZeroDivisionError:
            client.capture_exception()

        client.capture_message("Informational crash report")
        client.flush(timeout=0.5)
        client.shutdown(timeout=0.5)

        # Verify failed counter registered error
        assert client.stats.failed > 0


def test_requirement_e_queue_is_bounded():
    """Requirement E: queue is bounded."""
    config = Config(project_id=1, max_queue_size=42)
    client = ReleaseGuardClient(config=config, transport=MockTransport())

    assert client.worker._queue.maxsize == 42
    client.shutdown(timeout=0.5)


def test_requirement_f_queue_full_drops_oldest_event():
    """Requirement F: queue-full behavior follows the documented policy (Drop Oldest)."""
    # Transport with delay to prevent the worker from draining the queue immediately
    delayed_transport = MockTransport(delay=0.5)
    config = Config(project_id=1, max_queue_size=3, flush_interval=1.0)
    client = ReleaseGuardClient(config=config, transport=delayed_transport)

    # Pause worker consumption temporarily to inspect queue overflow
    with client.worker._lock:
        for i in range(5):
            event = Event(
                exception_type=f"Error_{i}",
                message=f"Message {i}",
                stack_trace="Traceback...",
            )
            client.worker.enqueue(event)

    # 5 events pushed into queue of capacity 3: 2 oldest dropped
    assert client.stats.dropped == 2
    assert client.stats.queued == 5

    # Check items currently in queue: must be Error_2, Error_3, Error_4 (Error_0 and Error_1 were dropped)
    remaining_events = list(client.worker._queue.queue)
    types_in_queue = [e.exception_type for e in remaining_events]
    assert "Error_0" not in types_in_queue
    assert "Error_1" not in types_in_queue
    assert "Error_4" in types_in_queue

    client.shutdown(timeout=1.0)


def test_requirement_g_retry_behavior_is_bounded():
    """Requirement G: retry behavior is bounded."""
    transport = MockTransport(
        error_to_raise=TransientTransportError("503 Service Unavailable")
    )
    # max_retries = 2 -> total attempts = 1 initial + 2 retries = 3 attempts
    config = Config(project_id=1, max_retries=2, retry_backoff=0.01, flush_interval=0.01)
    client = ReleaseGuardClient(config=config, transport=transport)

    try:
        raise ConnectionResetError("Connection lost")
    except ConnectionResetError:
        client.capture_exception()

    client.flush(timeout=1.0)

    # Must be bounded: 1 initial attempt + 2 retries = 3 total attempts
    assert transport.attempts == 3
    assert client.stats.failed == 1
    assert client.stats.sent == 0

    client.shutdown(timeout=0.5)


def test_permanent_client_error_not_retried():
    """4xx permanent errors must not be retried."""
    transport = MockTransport(
        error_to_raise=PermanentClientError("HTTP 422 Unprocessable Entity")
    )
    config = Config(project_id=1, max_retries=3, flush_interval=0.01)
    client = ReleaseGuardClient(config=config, transport=transport)

    try:
        raise ValueError("Bad data")
    except ValueError:
        client.capture_exception()

    client.flush(timeout=1.0)

    # Must NOT retry permanent client errors
    assert transport.attempts == 1
    assert client.stats.failed == 1

    client.shutdown(timeout=0.5)


def test_requirement_h_shutdown_stops_worker_cleanly():
    """Requirement H: shutdown stops the worker cleanly."""
    transport = MockTransport()
    config = Config(project_id=1)
    client = ReleaseGuardClient(config=config, transport=transport)

    worker_thread = client.worker._thread
    assert worker_thread.is_alive()

    client.shutdown(timeout=1.0)

    # Worker thread must be terminated
    assert not worker_thread.is_alive()
    assert client.worker._stopped is True

    # Subsequent enqueue must be rejected safely
    event = Event("LateError", "after shutdown", "")
    assert client.worker.enqueue(event) is False


class MockBatchTransport(BaseTransport):
    def __init__(self):
        self.batches: list[list[Event]] = []
        self.sent_events: list[Event] = []

    def send_event(self, event: Event) -> dict[str, Any]:
        self.sent_events.append(event)
        return {"status": "ok"}

    def send_batch(self, events: list[Event]) -> dict[str, Any]:
        self.batches.append(events)
        self.sent_events.extend(events)
        return {"status": "accepted", "accepted_count": len(events)}


def test_sdk_batch_transmission():
    """Validates that SDK worker flushes events in batches to bulk endpoint."""
    transport = MockBatchTransport()
    config = Config(project_id=1, batch_size=5, flush_interval=0.05)
    client = ReleaseGuardClient(config=config, transport=transport)

    for i in range(10):
        client.capture_message(f"Test message {i}")

    client.flush(timeout=1.0)
    assert len(transport.sent_events) == 10
    assert len(transport.batches) >= 2
    assert client.stats.sent == 10
    client.shutdown(timeout=0.5)


def test_sdk_event_id_generated_once_and_stable():
    """Verify event_id is generated once and remains stable across serializations."""
    event = None
    try:
        raise ValueError("Testing event_id stability")
    except ValueError:
        event = build_event_from_exc(release="1.0.0")

    assert event is not None
    assert event.event_id is not None
    assert len(event.event_id) >= 32

    # Multiple to_dict() calls must yield identical event_id
    dict1 = event.to_dict()
    dict2 = event.to_dict()
    assert dict1["event_id"] == event.event_id
    assert dict2["event_id"] == event.event_id


def test_sdk_retry_preserves_event_id():
    """Verify that retrying transport sends the exact same event_id without re-generating."""
    class FailOnceBatchTransport(BaseTransport):
        def __init__(self):
            self.attempts = 0
            self.delivered_event_ids = []

        def send_event(self, event: Event) -> dict[str, Any]:
            return {}

        def send_batch(self, events: list[Event]) -> dict[str, Any]:
            self.attempts += 1
            # Record the event_ids sent in this batch attempt
            self.delivered_event_ids.append([e.event_id for e in events])
            if self.attempts == 1:
                raise TransientTransportError("503 Service Temporarily Unavailable")
            return {"status": "accepted", "accepted_count": len(events)}

    transport = FailOnceBatchTransport()
    config = Config(project_id=1, max_retries=2, retry_backoff=0.01, flush_interval=0.01)
    client = ReleaseGuardClient(config=config, transport=transport)

    try:
        raise RuntimeError("Transient failure with stable ID")
    except RuntimeError:
        client.capture_exception()

    client.flush(timeout=1.0)
    assert transport.attempts == 2
    # Verify both attempts contained the EXACT same event_id
    attempt_1_ids = transport.delivered_event_ids[0]
    attempt_2_ids = transport.delivered_event_ids[1]
    assert attempt_1_ids == attempt_2_ids
    assert len(attempt_1_ids) == 1
    client.shutdown(timeout=0.5)


def test_sdk_http_transport_sends_api_key_header():
    """Verify that HttpTransport attaches X-ReleaseGuard-Key header when api_key is configured."""
    from unittest.mock import patch, MagicMock
    from releaseguard_sdk.transport import HttpTransport

    config_with_key = Config(project_id=42, api_key="rg_live_test_api_key_123")
    transport = HttpTransport(config_with_key)

    captured_requests = []

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value.read.return_value = b'{"status": "ok"}'
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        # 1. Single event
        event = build_event_from_message("Single test", release="1.0.0")
        transport.send_event(event)

        # 2. Batch event
        transport.send_batch([event])

    assert len(captured_requests) == 2

    # Check single event request headers
    single_req = captured_requests[0]
    assert single_req.get_header("X-releaseguard-key") == "rg_live_test_api_key_123"

    # Check batch event request headers
    batch_req = captured_requests[1]
    assert batch_req.get_header("X-releaseguard-key") == "rg_live_test_api_key_123"
