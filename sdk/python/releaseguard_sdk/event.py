"""
Event data model and extraction helpers for ReleaseGuard SDK.
"""

from dataclasses import dataclass, field
import sys
import traceback
import uuid


@dataclass
class Event:
    exception_type: str
    message: str
    stack_trace: str
    release: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "exception_type": self.exception_type,
            "message": self.message,
            "stack_trace": self.stack_trace,
            "release": self.release,
        }


def build_event_from_exc(exc_info=None, release: str | None = None) -> Event:
    """
    Safely captures and formats the current or provided exception into an Event.
    Guaranteed not to raise an unhandled exception.
    """
    try:
        if exc_info is None:
            exc_info = sys.exc_info()

        # Handle Python 3.11+ sys.last_exc if sys.exc_info() is empty
        if exc_info is None or exc_info[0] is None:
            last_exc = getattr(sys, "last_exc", None)
            if last_exc is not None:
                exc_info = (type(last_exc), last_exc, last_exc.__traceback__)

        exc_type, exc_value, tb = exc_info if exc_info else (None, None, None)

        if exc_type is None:
            # Fallback if called outside of an active except block
            return Event(
                exception_type="UnhandledException",
                message="capture_exception called without an active exception in sys.exc_info()",
                stack_trace="".join(traceback.format_stack()),
                release=release,
            )

        type_name = getattr(exc_type, "__name__", str(exc_type))
        msg = str(exc_value) if exc_value is not None else ""

        # Format full stack trace
        formatted_lines = traceback.format_exception(exc_type, exc_value, tb)
        stack_str = "".join(formatted_lines).strip()

        return Event(
            exception_type=type_name,
            message=msg,
            stack_trace=stack_str,
            release=release,
        )
    except Exception as formatting_err:
        # Ultimate fallback if traceback formatting fails
        return Event(
            exception_type="SDKFormattingError",
            message=f"Failed to format exception: {formatting_err}",
            stack_trace="Traceback unavailable due to internal formatting error.",
            release=release,
        )


def build_event_from_message(message: str, release: str | None = None) -> Event:
    """
    Builds an event from a manual message string.
    """
    try:
        stack = "".join(traceback.format_stack()[:-1]).strip()
        return Event(
            exception_type="Message",
            message=str(message),
            stack_trace=stack or "No stack trace available.",
            release=release,
        )
    except Exception:
        return Event(
            exception_type="Message",
            message=str(message),
            stack_trace="No stack trace available.",
            release=release,
        )
