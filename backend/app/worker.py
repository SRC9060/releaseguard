"""
Server-Side Background Worker for ReleaseGuard Ingestion Pipeline.
Consumes error events from Redis queue, computes fingerprints, performs
PostgreSQL atomic issue upsert, records ErrorEvent rows, and handles retries.
"""

from datetime import datetime, timezone
import logging
import signal
import sys
import threading
import time
from typing import Any, Callable
import uuid

from sqlalchemy.orm import Session, sessionmaker

from app.db import SessionLocal, engine
from app.fingerprint import make_fingerprint
from app.models import ErrorEvent, Issue
from app.queue import EventQueue, get_queue

logger = logging.getLogger("releaseguard.worker")


class IngestionWorker:
    """
    Dedicated worker that processes enqueued error events asynchronously from Redis.
    Guarantees atomic issue upsert and acknowledgment only after DB commit.
    """

    def __init__(
        self,
        queue: EventQueue | None = None,
        session_factory: Callable[[], Session] | None = None,
        max_retries: int = 3,
        batch_size: int = 50,
        consumer_name: str = "worker_1",
    ):
        self.queue = queue or get_queue()
        self.session_factory = session_factory or SessionLocal
        self.max_retries = max_retries
        self.batch_size = batch_size
        self.consumer_name = consumer_name
        self.stop_event = threading.Event()

    def _process_single_message(
        self, msg_id: str, data: dict[str, str], db: Session
    ) -> bool:
        """
        Processes a single queued event:
        1. Calculates fingerprint
        2. Performs atomic PostgreSQL upsert on Issue (project_id, fingerprint)
        3. Inserts ErrorEvent referencing issue_id
        4. Commits atomically
        5. Acknowledges message in Redis only after successful DB commit
        """
        try:
            event_id = data.get("event_id") or uuid.uuid4().hex
            project_id = int(data["project_id"])
            exception_type = data.get("exception_type", "UnknownError")
            message = data.get("message", "")
            stack_trace = data.get("stack_trace", "")
            release = data.get("release") or None

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            fingerprint = make_fingerprint(exception_type, stack_trace)

            dialect_name = db.bind.dialect.name if db.bind else "postgresql"
            if dialect_name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as upsert
            else:
                from sqlalchemy.dialects.sqlite import insert as upsert

            from sqlalchemy import case

            # Step 1: Atomic Issue upsert: creates or increments issue with regression detection
            stmt_issue = (
                upsert(Issue)
                .values(
                    project_id=project_id,
                    fingerprint=fingerprint,
                    title=f"{exception_type}: {message}",
                    count=1,
                    status="unresolved",
                    is_regression=False,
                    first_seen=now,
                    last_seen=now,
                )
                .on_conflict_do_update(
                    index_elements=["project_id", "fingerprint"],
                    set_={
                        "count": Issue.count + 1,
                        "last_seen": now,
                        "status": case(
                            (Issue.status == "resolved", "unresolved"),
                            else_=Issue.status,
                        ),
                        "is_regression": case(
                            (Issue.status == "resolved", True),
                            else_=Issue.is_regression,
                        ),
                        "regressed_at": case(
                            (Issue.status == "resolved", now),
                            else_=Issue.regressed_at,
                        ),
                    },
                )
                .returning(Issue.id, Issue.count)
            )

            result_issue = db.execute(stmt_issue).one()
            issue_id = result_issue[0]

            # Step 2: Insert ErrorEvent using ON CONFLICT (event_id) DO NOTHING
            stmt_event = (
                upsert(ErrorEvent)
                .values(
                    event_id=event_id,
                    project_id=project_id,
                    issue_id=issue_id,
                    exception_type=exception_type,
                    message=message,
                    stack_trace=stack_trace,
                    release=release,
                    received_at=now,
                )
                .on_conflict_do_nothing(index_elements=["event_id"])
                .returning(ErrorEvent.id)
            )
            event_result = db.execute(stmt_event).first()

            if event_result is None:
                # Step 3: Event was ALREADY PROCESSED previously!
                # Rollback transaction so the Issue count is NOT incremented!
                db.rollback()
                logger.info(
                    "Duplicate event_id '%s' detected (idempotent redelivery). "
                    "Rolled back transaction and acknowledging Redis message.",
                    event_id,
                )
                self.queue.ack(msg_id)
                return True

            # Step 4: Event is fresh -> Commit both issue upsert and error event atomically
            db.commit()

            # Step 5: Acknowledge queue message only after successful DB commit
            self.queue.ack(msg_id)
            return True

        except Exception as exc:
            db.rollback()
            logger.exception("Error processing event %s: %s", msg_id, exc)
            self.queue.fail(msg_id, data, str(exc), max_retries=self.max_retries)
            return False

    def process_next_batch(
        self, batch_size: int | None = None, timeout_ms: int = 500
    ) -> int:
        """
        Dequeues and processes one batch of events.
        Returns the number of successfully processed events.
        """
        limit = batch_size or self.batch_size
        messages = self.queue.dequeue_batch(
            batch_size=limit,
            timeout_ms=timeout_ms,
            consumer_name=self.consumer_name,
        )

        if not messages:
            return 0

        processed = 0
        db = self.session_factory()
        try:
            for msg_id, data in messages:
                success = self._process_single_message(msg_id, data, db)
                if success:
                    processed += 1
        finally:
            db.close()

        return processed

    def run(self, poll_interval: float = 0.05) -> None:
        """Continuously processes events until stop_event is set."""
        logger.info(
            "ReleaseGuard IngestionWorker '%s' started. Polling Redis stream...",
            self.consumer_name,
        )
        while not self.stop_event.is_set():
            count = self.process_next_batch(timeout_ms=500)
            if count == 0 and not self.stop_event.is_set():
                time.sleep(poll_interval)

        logger.info("ReleaseGuard IngestionWorker '%s' stopped cleanly.", self.consumer_name)

    def stop(self) -> None:
        """Signals the worker loop to terminate."""
        self.stop_event.set()


def run_worker() -> None:
    """CLI entrypoint for running the worker process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    worker = IngestionWorker()

    def handle_exit(signum, frame):
        logger.info("Termination signal received. Shutting down worker...")
        worker.stop()

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    worker.run()


if __name__ == "__main__":
    run_worker()
