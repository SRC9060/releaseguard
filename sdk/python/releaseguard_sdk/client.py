"""
ReleaseGuard Client implementation.
Provides fail-safe exception capture and coordination with worker and transport.
"""

import atexit
import logging
from typing import Any

from releaseguard_sdk.config import Config
from releaseguard_sdk.event import build_event_from_exc, build_event_from_message
from releaseguard_sdk.transport import BaseTransport, HttpTransport
from releaseguard_sdk.worker import BackgroundWorker, WorkerStats

logger = logging.getLogger("releaseguard_sdk")


class ReleaseGuardClient:
    """
    Main client instance for ReleaseGuard SDK.
    Guaranteed never to crash the host application.
    """

    def __init__(
        self,
        config: Config,
        transport: BaseTransport | None = None,
    ):
        self.config = config
        self.transport = transport or HttpTransport(config)
        self.worker = BackgroundWorker(self.config, self.transport)
        self._flag_cache: dict[str, dict[str, Any]] = {}

        # Register exit hook for clean termination
        self._atexit_registered = False
        self._register_atexit()

    def _register_atexit(self) -> None:
        if not self._atexit_registered:
            atexit.register(self.shutdown, timeout=1.5)
            self._atexit_registered = True

    def capture_exception(self, exc_info: Any = None) -> None:
        """
        Captures an exception and enqueues it for asynchronous transmission.
        NEVER raises an exception back into the host application.
        """
        try:
            event = build_event_from_exc(
                exc_info=exc_info,
                release=self.config.release,
            )
            self.worker.enqueue(event)
        except Exception as internal_err:
            if self.config.debug:
                logger.error(
                    "ReleaseGuard SDK failed to capture exception: %s",
                    internal_err,
                    exc_info=True,
                )

    def capture_message(self, message: str) -> None:
        """
        Captures a message event and enqueues it for asynchronous transmission.
        NEVER raises an exception back into the host application.
        """
        try:
            event = build_event_from_message(
                message=message,
                release=self.config.release,
            )
            self.worker.enqueue(event)
        except Exception as internal_err:
            if self.config.debug:
                logger.error(
                    "ReleaseGuard SDK failed to capture message: %s",
                    internal_err,
                    exc_info=True,
                )

    def flush(self, timeout: float | None = 2.0) -> bool:
        """
        Waits up to timeout seconds for queued events to be transmitted.
        """
        try:
            return self.worker.flush(timeout=timeout)
        except Exception as err:
            if self.config.debug:
                logger.warning("ReleaseGuard SDK flush failed: %s", err)
            return False

    def shutdown(self, timeout: float | None = 2.0) -> None:
        """
        Flushes and stops the background worker.
        """
        try:
            self.worker.shutdown(timeout=timeout)
        except Exception as err:
            if self.config.debug:
                logger.warning("ReleaseGuard SDK shutdown failed: %s", err)

    @property
    def stats(self) -> WorkerStats:
        """
        Returns internal telemetry counters (queued, sent, dropped, failed).
        """
        return self.worker.stats

    def get_flag(
        self,
        key: str,
        user_id: str | None = None,
        environment: str | None = None,
        default: Any = False,
    ) -> Any:
        """
        Evaluates a feature flag locally using cached environment configuration.
        Caches document with short TTL (15s) and ETag revalidation.
        Falls back safely to stale cache or default on network error.
        NEVER raises an exception to the host application.
        """
        import time
        try:
            env = environment or self.config.environment or "production"
            now = time.time()
            cached = self._flag_cache.get(env)

            # If cache missing or expired, attempt refresh
            if not cached or now >= cached.get("expires_at", 0):
                cached_etag = cached.get("etag") if cached else None
                status_code, data, new_etag = self.transport.get_config(
                    environment=env,
                    etag=cached_etag,
                )
                if status_code == 200:
                    self._flag_cache[env] = {
                        "expires_at": now + 15.0,  # 15s TTL
                        "etag": new_etag,
                        "doc": data,
                    }
                elif status_code == 304 and cached:
                    cached["expires_at"] = now + 15.0

            # Evaluate locally from cache
            current_cache = self._flag_cache.get(env)
            if current_cache and "doc" in current_cache:
                flags = current_cache["doc"].get("flags", {})
                if key in flags:
                    flag_info = flags[key]
                    if not flag_info.get("enabled", False):
                        return default
                    pct = flag_info.get("percentage")
                    salt = flag_info.get("salt")
                    if pct is not None and user_id:
                        if pct <= 0:
                            return False
                        if pct >= 100:
                            return True
                        import zlib
                        b = zlib.crc32(f"{key}:{env}:{salt}:{user_id}".encode("utf-8")) % 100
                        return b < pct
                    return flag_info.get("enabled", default)

            return default
        except Exception as err:
            if self.config.debug:
                logger.warning("ReleaseGuard SDK failed to evaluate flag '%s': %s", key, err)
            return default

    def get_flag_variant(
        self,
        key: str,
        user_id: str | None = None,
        environment: str | None = None,
        default: str = "off",
    ) -> str:
        """
        Returns the evaluated variant string for a flag.
        """
        import time
        try:
            env = environment or self.config.environment or "production"
            now = time.time()
            cached = self._flag_cache.get(env)

            if not cached or now >= cached.get("expires_at", 0):
                cached_etag = cached.get("etag") if cached else None
                status_code, data, new_etag = self.transport.get_config(
                    environment=env,
                    etag=cached_etag,
                    user_id=user_id,
                )
                if status_code == 200:
                    self._flag_cache[env] = {
                        "expires_at": now + 15.0,
                        "etag": new_etag,
                        "doc": data,
                    }
                elif status_code == 304 and cached:
                    cached["expires_at"] = now + 15.0

            current_cache = self._flag_cache.get(env)
            if current_cache and "doc" in current_cache:
                flags = current_cache["doc"].get("flags", {})
                if key in flags:
                    return flags[key].get("variant", default)

            return default
        except Exception as err:
            if self.config.debug:
                logger.warning("ReleaseGuard SDK failed to evaluate flag variant '%s': %s", key, err)
            return default
