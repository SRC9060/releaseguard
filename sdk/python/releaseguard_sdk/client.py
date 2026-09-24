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
