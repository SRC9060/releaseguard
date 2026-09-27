"""
ReleaseGuard Python SDK.

Developer reliability platform for automatic failure capture and grouping.
Key Guarantee: ReleaseGuard failure must never become the host application's failure.
"""

from typing import Any

from releaseguard_sdk.client import ReleaseGuardClient
from releaseguard_sdk.config import Config
from releaseguard_sdk.event import Event
from releaseguard_sdk.transport import BaseTransport, HttpTransport
from releaseguard_sdk.worker import WorkerStats

__version__ = "0.1.0"
__all__ = [
    "init",
    "capture_exception",
    "capture_message",
    "flush",
    "shutdown",
    "get_client",
    "get_flag",
    "get_flag_variant",
    "ReleaseGuardClient",
    "Config",
    "Event",
    "BaseTransport",
    "WorkerStats",
]

_global_client: ReleaseGuardClient | None = None


def init(
    project_id: int,
    base_url: str = "http://127.0.0.1:8000",
    api_key: str = "",
    release: str | None = None,
    environment: str = "production",
    max_queue_size: int = 1000,
    flush_interval: float = 0.5,
    batch_size: int = 20,
    max_retries: int = 3,
    retry_backoff: float = 0.1,
    timeout: float = 5.0,
    debug: bool = False,
    transport: BaseTransport | None = None,
) -> ReleaseGuardClient:
    """
    Initializes the global ReleaseGuard SDK client.
    """
    global _global_client

    if _global_client is not None:
        try:
            _global_client.shutdown(timeout=1.0)
        except Exception:
            pass

    config = Config(
        project_id=project_id,
        base_url=base_url,
        api_key=api_key,
        release=release,
        environment=environment,
        max_queue_size=max_queue_size,
        flush_interval=flush_interval,
        batch_size=batch_size,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
        timeout=timeout,
        debug=debug,
    )

    _global_client = ReleaseGuardClient(config=config, transport=transport)
    return _global_client


def get_client() -> ReleaseGuardClient | None:
    """
    Returns the currently active global ReleaseGuard client, if initialized.
    """
    return _global_client


def capture_exception(exc_info: Any = None) -> None:
    """
    Captures an active exception and enqueues it for asynchronous delivery.
    Non-blocking. Never raises exceptions back to the caller.
    """
    if _global_client is not None:
        _global_client.capture_exception(exc_info=exc_info)


def capture_message(message: str) -> None:
    """
    Captures an informational message and enqueues it for delivery.
    Non-blocking. Never raises exceptions back to the caller.
    """
    if _global_client is not None:
        _global_client.capture_message(message=message)


def flush(timeout: float | None = 2.0) -> bool:
    """
    Waits for all enqueued events to be processed up to the timeout.
    """
    if _global_client is not None:
        return _global_client.flush(timeout=timeout)
    return True


def shutdown(timeout: float | None = 2.0) -> None:
    """
    Flushes and terminates the global ReleaseGuard client.
    """
    global _global_client
    if _global_client is not None:
        _global_client.shutdown(timeout=timeout)
        _global_client = None


def get_flag(
    key: str,
    user_id: str | None = None,
    environment: str = "production",
    default: Any = False,
) -> Any:
    """
    Evaluates a feature flag locally using cached environment configuration.
    """
    if _global_client is not None:
        return _global_client.get_flag(key=key, user_id=user_id, environment=environment, default=default)
    return default


def get_flag_variant(
    key: str,
    user_id: str | None = None,
    environment: str = "production",
    default: str = "off",
) -> str:
    """
    Returns the evaluated variant string for a flag.
    """
    if _global_client is not None:
        return _global_client.get_flag_variant(key=key, user_id=user_id, environment=environment, default=default)
    return default
