"""
Isolated Redis Queue Service for ReleaseGuard Server-Side Ingestion.
Uses Redis Streams for durable queuing, consumer groups, and atomic acknowledgment.
"""

from datetime import datetime, timezone
import logging
import os
from typing import Any
import uuid
from urllib.parse import urlparse

import redis

logger = logging.getLogger("releaseguard.queue")

DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
STREAM_KEY = "releaseguard:events:stream"
GROUP_NAME = "releaseguard:workers"
DEAD_LETTER_KEY = "releaseguard:events:dead_letter"

COUNTER_ACCEPTED = "releaseguard:counters:accepted"
COUNTER_PROCESSED = "releaseguard:counters:processed"
COUNTER_FAILED = "releaseguard:counters:failed"
COUNTER_RETRIED = "releaseguard:counters:retried"


class EventQueue:
    """
    Manages queueing, dequeuing, retries, and dead-lettering of error events using Redis Streams.
    """

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        redis_url: str | None = None,
        stream_name: str = STREAM_KEY,
        group_name: str = GROUP_NAME,
        dead_letter_stream: str = DEAD_LETTER_KEY,
    ):
        self.stream_name = stream_name
        self.group_name = group_name
        self.dead_letter_stream = dead_letter_stream

        if redis_client is not None:
            self.client = redis_client
        else:
            url = redis_url or os.getenv("REDIS_URL") or DEFAULT_REDIS_URL
            client = redis.from_url(url, decode_responses=True)
            # Must verify connection; fail immediately if Redis is unreachable
            client.ping()
            self.client = client
            parsed = urlparse(url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 6379
            logger.info("Connected to Redis at %s:%s", host, port)

        self._ensure_consumer_group()

    def _ensure_consumer_group(self) -> None:
        """Ensures the consumer group exists for the stream."""
        try:
            self.client.xgroup_create(
                self.stream_name,
                self.group_name,
                id="0",
                mkstream=True,
            )
        except redis.exceptions.ResponseError as err:
            if "BUSYGROUP" not in str(err):
                logger.warning("Error creating Redis consumer group: %s", err)
        except Exception as exc:
            logger.warning("Unexpected error creating consumer group: %s", exc)

    def enqueue_events(
        self, project_id: int, events: list[dict[str, Any]]
    ) -> tuple[str, int]:
        """
        Enqueues a batch of events onto the Redis stream.
        Returns (batch_id, accepted_count).
        """
        batch_id = uuid.uuid4().hex
        now_iso = datetime.now(timezone.utc).isoformat()
        pipe = self.client.pipeline()

        for event in events:
            event_id = str(event.get("event_id") or uuid.uuid4())
            fields = {
                "event_id": event_id,
                "project_id": str(project_id),
                "batch_id": batch_id,
                "exception_type": str(event.get("exception_type", "UnknownError")),
                "message": str(event.get("message", "")),
                "stack_trace": str(event.get("stack_trace", "")),
                "release": str(event.get("release") or ""),
                "retry_count": "0",
                "enqueued_at": now_iso,
            }
            pipe.xadd(self.stream_name, fields, maxlen=100000, approximate=True)

        pipe.incrby(COUNTER_ACCEPTED, len(events))
        pipe.execute()

        logger.debug(
            "Enqueued %d events for project %d under batch %s",
            len(events),
            project_id,
            batch_id,
        )
        return batch_id, len(events)

    def dequeue_batch(
        self,
        batch_size: int = 50,
        timeout_ms: int = 1000,
        consumer_name: str = "worker_1",
    ) -> list[tuple[str, dict[str, str]]]:
        """
        Reads pending messages from the stream using consumer group.
        Returns a list of (message_id, fields_dict).
        """
        self._ensure_consumer_group()
        try:
            results = self.client.xreadgroup(
                self.group_name,
                consumer_name,
                {self.stream_name: ">"},
                count=batch_size,
                block=timeout_ms,
            )
        except Exception as exc:
            logger.error("Error reading from Redis stream: %s", exc)
            return []

        if not results:
            return []

        messages: list[tuple[str, dict[str, str]]] = []
        for stream, msgs in results:
            for msg_id, data in msgs:
                decoded_data = {
                    k if isinstance(k, str) else k.decode(): v
                    if isinstance(v, str)
                    else v.decode()
                    for k, v in data.items()
                }
                messages.append(
                    (
                        msg_id if isinstance(msg_id, str) else msg_id.decode(),
                        decoded_data,
                    )
                )

        return messages

    def recover_stale_pending(
        self,
        min_idle_time_ms: int = 30000,
        count: int = 50,
        consumer_name: str = "worker_recovery",
    ) -> list[tuple[str, dict[str, str]]]:
        """
        Recovers stale pending entries from the PEL (from dead/crashed workers)
        using XAUTOCLAIM or XPENDING + XCLAIM.
        """
        self._ensure_consumer_group()
        try:
            # Redis 6.2+ xautoclaim returns (next_start_id, messages, deleted_ids)
            res = self.client.xautoclaim(
                self.stream_name,
                self.group_name,
                consumer_name,
                min_idle_time=min_idle_time_ms,
                start_id="0-0",
                count=count,
            )
            raw_messages = res[1] if isinstance(res, (list, tuple)) and len(res) > 1 else []
            recovered: list[tuple[str, dict[str, str]]] = []
            for msg_id, data in raw_messages:
                decoded_data = {
                    k if isinstance(k, str) else k.decode(): v
                    if isinstance(v, str)
                    else v.decode()
                    for k, v in data.items()
                }
                recovered.append(
                    (
                        msg_id if isinstance(msg_id, str) else msg_id.decode(),
                        decoded_data,
                    )
                )
            if recovered:
                logger.info("Recovered %d stale pending messages via XAUTOCLAIM", len(recovered))
            return recovered
        except Exception as exc:
            # Fallback to XPENDING + XCLAIM
            try:
                pending_entries = self.client.xpending_range(
                    self.stream_name,
                    self.group_name,
                    min="-",
                    max="+",
                    count=count,
                )
                stale_ids = [
                    p["message_id"] for p in pending_entries
                    if p.get("idle", 0) >= min_idle_time_ms
                ]
                if not stale_ids:
                    return []
                claimed = self.client.xclaim(
                    self.stream_name,
                    self.group_name,
                    consumer_name,
                    min_idle_time=min_idle_time_ms,
                    message_ids=stale_ids,
                )
                recovered = []
                for msg_id, data in claimed:
                    decoded_data = {
                        k if isinstance(k, str) else k.decode(): v
                        if isinstance(v, str)
                        else v.decode()
                        for k, v in data.items()
                    }
                    recovered.append(
                        (
                            msg_id if isinstance(msg_id, str) else msg_id.decode(),
                            decoded_data,
                        )
                    )
                if recovered:
                    logger.info("Recovered %d stale pending messages via XCLAIM fallback", len(recovered))
                return recovered
            except Exception as inner_exc:
                logger.debug("Stale PEL recovery error: %s", inner_exc)
                return []

    def ack(self, message_id: str) -> None:
        """Acknowledges successful processing of a message."""
        pipe = self.client.pipeline()
        pipe.xack(self.stream_name, self.group_name, message_id)
        pipe.incrby(COUNTER_PROCESSED, 1)
        pipe.execute()

    def fail(
        self,
        message_id: str,
        data: dict[str, str],
        error_msg: str,
        max_retries: int = 3,
    ) -> bool:
        """
        Handles failed processing.
        If retry_count < max_retries: re-enqueues message with incremented retry count.
        Else: routes message to dead letter queue.
        Always acknowledges the original message ID.
        Returns True if retried, False if dead-lettered.
        """
        current_retries = int(data.get("retry_count", 0)) + 1
        pipe = self.client.pipeline()
        pipe.incrby(COUNTER_RETRIED, 1)

        if current_retries <= max_retries:
            # Re-enqueue for retry
            retry_data = dict(data)
            retry_data["retry_count"] = str(current_retries)
            retry_data["last_error"] = str(error_msg)[:500]
            pipe.xadd(self.stream_name, retry_data, maxlen=100000, approximate=True)
            pipe.xack(self.stream_name, self.group_name, message_id)
            pipe.execute()
            logger.warning(
                "Event %s failed (%s). Retrying (attempt %d/%d)",
                message_id,
                error_msg,
                current_retries,
                max_retries,
            )
            return True
        else:
            # Max retries exceeded -> Dead Letter Queue
            dead_data = dict(data)
            dead_data["retry_count"] = str(current_retries)
            dead_data["final_error"] = str(error_msg)[:1000]
            dead_data["failed_at"] = datetime.now(timezone.utc).isoformat()
            dead_data["original_msg_id"] = message_id

            pipe.xadd(self.dead_letter_stream, dead_data, maxlen=50000, approximate=True)
            pipe.xack(self.stream_name, self.group_name, message_id)
            pipe.incrby(COUNTER_FAILED, 1)
            pipe.execute()
            logger.error(
                "Event %s exceeded max retries (%d). Routed to dead letter queue: %s",
                message_id,
                max_retries,
                error_msg,
            )
            return False

    def get_health(self) -> dict[str, Any]:
        """Returns comprehensive queue health status."""
        try:
            self.client.ping()
            connected = True
        except Exception:
            connected = False

        if not connected:
            return {
                "status": "degraded",
                "redis_connected": False,
                "stream_depth": 0,
                "pel_count": 0,
            }

        try:
            depth = self.client.xlen(self.stream_name)
        except Exception:
            depth = 0

        pel_count = 0
        try:
            pending_info = self.client.xpending(self.stream_name, self.group_name)
            if pending_info:
                pel_count = pending_info.get("pending", 0) if isinstance(pending_info, dict) else pending_info[0]
        except Exception:
            pel_count = 0

        return {
            "status": "healthy",
            "redis_connected": True,
            "stream_name": self.stream_name,
            "stream_depth": depth,
            "pel_count": pel_count,
        }

    def get_metrics(self) -> dict[str, int]:
        """Returns internal queue observability counters and stream depths."""
        try:
            depth = self.client.xlen(self.stream_name)
        except Exception:
            depth = 0

        try:
            dl_depth = self.client.xlen(self.dead_letter_stream)
        except Exception:
            dl_depth = 0

        def get_int(key: str) -> int:
            try:
                val = self.client.get(key)
                return int(val) if val else 0
            except Exception:
                return 0

        return {
            "queue_depth": depth,
            "dead_letter_depth": dl_depth,
            "events_accepted": get_int(COUNTER_ACCEPTED),
            "events_processed": get_int(COUNTER_PROCESSED),
            "events_failed": get_int(COUNTER_FAILED),
            "events_retried": get_int(COUNTER_RETRIED),
        }

    def clear(self) -> None:
        """Cleans up streams and counters (useful in tests)."""
        keys = [
            self.stream_name,
            self.dead_letter_stream,
            COUNTER_ACCEPTED,
            COUNTER_PROCESSED,
            COUNTER_FAILED,
            COUNTER_RETRIED,
        ]
        self.client.delete(*keys)
        self._ensure_consumer_group()


# Global default instance
_queue_instance: EventQueue | None = None


def get_queue() -> EventQueue:
    """FastAPI dependency for obtaining the EventQueue instance."""
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = EventQueue()
    return _queue_instance
