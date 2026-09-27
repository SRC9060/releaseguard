import contextvars
import json
import logging
import re
from typing import Any

# Context variables for tracing requests across logs
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
tenant_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="")
project_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("project_id", default="")

# Regex pattern for sensitive patterns (passwords, api keys, bearer tokens)
SENSITIVE_PATTERNS = [
    re.compile(r'("?(?:password|password_hash|secret|token|api_key|authorization|bearer)"?\s*[:=]\s*["\'])([^"\']+)("?)', re.IGNORECASE),
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-_\.]+", re.IGNORECASE),
    re.compile(r"(rg_live_)[a-f0-9]+", re.IGNORECASE),
]


def redact_sensitive(text: str) -> str:
    """Masks secret, API key, password, and token values in log text."""
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        if "Bearer" in pattern.pattern:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        elif "rg_live_" in pattern.pattern:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub(r"\1[REDACTED]\3", redacted)
    return redacted


class StructuredLogFormatter(logging.Formatter):
    """
    Log formatter that includes request/tenant/project context and
    automatically redacts sensitive credentials.
    """

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        redacted_msg = redact_sensitive(msg)
        
        req_id = request_id_ctx.get("")
        t_id = tenant_id_ctx.get("")
        p_id = project_id_ctx.get("")

        context_parts = []
        if req_id:
            context_parts.append(f"req={req_id}")
        if t_id:
            context_parts.append(f"tenant={t_id}")
        if p_id:
            context_parts.append(f"project={p_id}")

        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""

        asctime = self.formatTime(record, self.datefmt)
        formatted = f"{asctime} [{record.levelname}] {record.name}{context_str}: {redacted_msg}"

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                formatted += "\n" + redact_sensitive(record.exc_text)

        return formatted


def configure_logging(level: int = logging.INFO) -> None:
    """Configures structured, sanitized root logging."""
    handler = logging.StreamHandler()
    formatter = StructuredLogFormatter(
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    
    root = logging.getLogger()
    root.setLevel(level)
    # Clear existing handlers to prevent duplicate lines
    root.handlers.clear()
    root.addHandler(handler)

    # Ensure releaseguard loggers inherit this configuration
    for name in ["releaseguard", "releaseguard.worker", "releaseguard.queue", "uvicorn.access"]:
        logger = logging.getLogger(name)
        logger.setLevel(level)
