"""
Background worker and bounded in-memory queue for ReleaseGuard SDK.
"""

from dataclasses import dataclass
import logging
import queue
import threading
import time
from typing import List

from releaseguard_sdk.config import Config
from releaseguard_sdk.event import Event
from releaseguard_sdk.transport import (
    BaseTransport,
    PermanentClientError,
    TransientTransportError,
)

logger = logging.getLogger("releaseguard_sdk")


@dataclass
class WorkerStats:
    queued: int = 0
    sent: int = 0
    dropped: int = 0
    failed: int = 0


class BackgroundWorker:
    """
    Asynchronous background worker that transmits events from a bounded queue.
    Ensures the host application thread is never blocked by HTTP transmission.
    """

    def __init__(self, config: Config, transport: BaseTransport):
        self.config = config
        self.transport = transport
        self.stats = WorkerStats()

        self._queue: queue.Queue[Event] = queue.Queue(maxsize=config.max_queue_size)
        self._stopped = False
        self._shutdown_event = threading.Event()
        self._lock = threading.RLock()

        self._thread = threading.Thread(
            target=self._run,
            name="ReleaseGuardWorker",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, event: Event) -> bool:
        """
        Puts an event onto the bounded queue without blocking.
        Policy on queue full: Drop the oldest queued event to make room for the fresh event.
        """
        if self._stopped:
            if self.config.debug:
                logger.debug("Event discarded: SDK worker is stopped.")
            return False

        with self._lock:
            if self._queue.full():
                try:
                    # Drop oldest event to bound memory and preserve fresh errors
                    self._queue.get_nowait()
                    self._queue.task_done()
                    self.stats.dropped += 1
                    if self.config.debug:
                        logger.debug("ReleaseGuard queue full: dropped oldest event.")
                except queue.Empty:
                    pass

            try:
                self._queue.put_nowait(event)
                self.stats.queued += 1
                return True
            except queue.Full:
                self.stats.dropped += 1
                return False

    def _send_with_retry(self, event: Event) -> bool:
        """
        Sends an event with exponential backoff for transient errors.
        Permanent client errors (4xx) are discarded immediately without retry.
        """
        for attempt in range(self.config.max_retries + 1):
            if self._shutdown_event.is_set():
                break

            try:
                self.transport.send_event(event)
                self.stats.sent += 1
                if self.config.debug:
                    logger.debug(
                        "Successfully sent event: %s", event.exception_type
                    )
                return True
            except PermanentClientError as p_err:
                self.stats.failed += 1
                if self.config.debug:
                    logger.warning("Permanent client error sending event: %s", p_err)
                return False
            except TransientTransportError as t_err:
                if attempt < self.config.max_retries:
                    backoff = self.config.retry_backoff * (2**attempt)
                    if self.config.debug:
                        logger.debug(
                            "Transient transport error (%s). Retrying in %.2fs (attempt %d/%d)",
                            t_err,
                            backoff,
                            attempt + 1,
                            self.config.max_retries,
                        )
                    # Check shutdown flag during backoff sleep
                    self._shutdown_event.wait(timeout=backoff)
                else:
                    self.stats.failed += 1
                    if self.config.debug:
                        logger.error(
                            "Exhausted retries sending event (%s): %s",
                            event.exception_type,
                            t_err,
                        )
                    return False
            except Exception as unhandled:
                self.stats.failed += 1
                if self.config.debug:
                    logger.error("Unhandled worker error sending event: %s", unhandled)
                return False

    def _send_batch_with_retry(self, batch: List[Event]) -> bool:
        """
        Sends a batch of events with exponential backoff for transient errors.
        Permanent client errors (4xx) are discarded immediately without retry.
        """
        count = len(batch)
        for attempt in range(self.config.max_retries + 1):
            if self._shutdown_event.is_set():
                break

            try:
                self.transport.send_batch(batch)
                self.stats.sent += count
                if self.config.debug:
                    logger.debug("Successfully sent batch of %d events", count)
                return True
            except PermanentClientError as p_err:
                self.stats.failed += count
                if self.config.debug:
                    logger.warning("Permanent client error sending batch: %s", p_err)
                return False
            except TransientTransportError as t_err:
                if attempt < self.config.max_retries:
                    backoff = self.config.retry_backoff * (2**attempt)
                    if self.config.debug:
                        logger.debug(
                            "Transient transport error (%s). Retrying batch in %.2fs (attempt %d/%d)",
                            t_err,
                            backoff,
                            attempt + 1,
                            self.config.max_retries,
                        )
                    self._shutdown_event.wait(timeout=backoff)
                else:
                    self.stats.failed += count
                    if self.config.debug:
                        logger.error(
                            "Exhausted retries sending batch of %d events: %s",
                            count,
                            t_err,
                        )
                    return False
            except Exception as unhandled:
                self.stats.failed += count
                if self.config.debug:
                    logger.error("Unhandled worker error sending batch: %s", unhandled)
                return False

        return False

    def _run(self) -> None:
        """
        Main worker execution loop.
        Collects events from the queue and transmits them in batches.
        """
        while not self._shutdown_event.is_set():
            batch = self._collect_batch()
            if not batch:
                continue
            try:
                self._send_batch_with_retry(batch)
            finally:
                for _ in batch:
                    self._queue.task_done()

        # Drain remaining events on shutdown
        drain_batch: List[Event] = []
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                drain_batch.append(event)
            except queue.Empty:
                break

        if drain_batch:
            try:
                self.transport.send_batch(drain_batch)
                self.stats.sent += len(drain_batch)
            except Exception:
                self.stats.failed += len(drain_batch)
            finally:
                for _ in drain_batch:
                    self._queue.task_done()

    def _collect_batch(self) -> List[Event]:
        """
        Collects up to `batch_size` events, waiting up to `flush_interval`.
        """
        batch: List[Event] = []
        deadline = time.time() + self.config.flush_interval

        while len(batch) < self.config.batch_size:
            remaining = max(0.01, deadline - time.time())
            try:
                event = self._queue.get(timeout=remaining)
                batch.append(event)
            except queue.Empty:
                break
            if time.time() >= deadline:
                break

        return batch

    def flush(self, timeout: float | None = 2.0) -> bool:
        """
        Blocks until all items currently in the queue have been processed,
        up to the specified timeout.
        """
        start = time.time()
        max_wait = timeout if timeout is not None else 2.0

        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks > 0:
                elapsed = time.time() - start
                remaining = max_wait - elapsed
                if remaining <= 0:
                    return False
                self._queue.all_tasks_done.wait(timeout=remaining)

        return True

    def shutdown(self, timeout: float | None = 2.0) -> None:
        """
        Stops accepting new events, flushes queued events, and terminates the worker.
        """
        with self._lock:
            self._stopped = True

        # Allow queue to drain within timeout
        self.flush(timeout=timeout)

        # Signal shutdown and join thread
        self._shutdown_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)
