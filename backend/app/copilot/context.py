"""
Phase 15A — AI Incident Copilot Context Builder.
Builds authorized, sanitized, secret-scrubbed context for an incident.
Guarantees tenant/project scoping and prompt-injection defense.
"""

from datetime import datetime, timedelta
import hashlib
import json
import re
from typing import Any, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import (
    Environment,
    ErrorEvent,
    FeatureFlag,
    FlagAuditLog,
    Incident,
    IncidentEvent,
    IncidentIssue,
    IncidentMitigation,
    Issue,
    Release,
)

# Regular expressions for scrubbing potential secrets and credentials from untrusted telemetry
SECRET_PATTERNS = [
    # ReleaseGuard API keys
    (re.compile(r"rg_(?:live|test)_[a-zA-Z0-9]{20,}", re.IGNORECASE), "[REDACTED_RG_KEY]"),
    # JWT tokens
    (re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+"), "[REDACTED_JWT]"),
    # Authorization header Bearer tokens
    (re.compile(r"(?:Bearer\s+)[A-Za-z0-9._-]{15,}", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    # Database connection URLs with credentials
    (re.compile(r"(?:postgresql|postgres|mysql|redis)://[^@\s]+@", re.IGNORECASE), "[REDACTED_DB_URI]@"),
    # Generic API Keys (OpenAI, AWS, Google, etc.)
    (re.compile(r"sk-[a-zA-Z0-9_-]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"AIzaSy[a-zA-Z0-9_-]{20,}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    # Common password patterns
    (re.compile(r'(?i)(password|secret|token|passwd|pwd)\s*[:=]\s*["\']?[^"\'\s,;]{4,}["\']?'), r"\1=[REDACTED]"),
]


def scrub_secrets(text: Any) -> Any:
    """
    Recursively scrubs known secret formats and credential patterns from text and data structures.
    """
    if isinstance(text, str):
        cleaned = text
        for pattern, replacement in SECRET_PATTERNS:
            cleaned = pattern.sub(replacement, cleaned)
        return cleaned
    elif isinstance(text, dict):
        return {k: scrub_secrets(v) for k, v in text.items()}
    elif isinstance(text, list):
        return [scrub_secrets(item) for item in text]
    return text


def truncate_stack_trace(stack_trace: str, max_lines: int = 25, max_chars: int = 1500) -> str:
    """
    Limits stack trace size to avoid context exhaustion while preserving critical frame information.
    """
    if not stack_trace:
        return ""
    lines = stack_trace.strip().split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... [{len(lines) - max_lines} deeper stack frames truncated]"]
    truncated = "\n".join(lines)
    if len(truncated) > max_chars:
        truncated = truncated[:max_chars] + "... [truncated]"
    return truncated


class IncidentContextBuilder:
    """
    Gathers structured telemetry strictly within the authorized project and tenant.
    Never crosses tenant boundaries.
    """

    @classmethod
    def build_context(cls, incident: Incident, db: Session) -> Dict[str, Any]:
        project_id = incident.project_id

        # 1. Incident Core Metadata
        context: Dict[str, Any] = {
            "incident": {
                "id": incident.id,
                "project_id": incident.project_id,
                "environment": incident.environment,
                "title": incident.title,
                "description": incident.description,
                "severity": incident.severity,
                "status": incident.status,
                "started_at": incident.started_at.isoformat() if incident.started_at else None,
                "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
                "created_at": incident.created_at.isoformat() if incident.created_at else None,
            }
        }

        # 2. Linked Issues and Recent Error Samples
        # Collect issue IDs from both incident_issues relation and related_issue_id
        linked_issue_ids = {link.issue_id for link in incident.linked_issues}
        if incident.related_issue_id:
            linked_issue_ids.add(incident.related_issue_id)

        linked_issues_data: List[Dict[str, Any]] = []
        if linked_issue_ids:
            issues = (
                db.query(Issue)
                .filter(Issue.id.in_(linked_issue_ids), Issue.project_id == project_id)
                .all()
            )
            for issue in issues:
                # Fetch recent error events for this issue
                recent_events = (
                    db.query(ErrorEvent)
                    .filter(ErrorEvent.issue_id == issue.id, ErrorEvent.project_id == project_id)
                    .order_by(desc(ErrorEvent.received_at))
                    .limit(3)
                    .all()
                )

                events_data = [
                    {
                        "event_id": ev.event_id,
                        "exception_type": ev.exception_type,
                        "message": ev.message,
                        "release": ev.release,
                        "received_at": ev.received_at.isoformat() if ev.received_at else None,
                        "stack_trace": truncate_stack_trace(ev.stack_trace),
                    }
                    for ev in recent_events
                ]

                linked_issues_data.append({
                    "id": issue.id,
                    "title": issue.title,
                    "fingerprint": issue.fingerprint,
                    "count": issue.count,
                    "status": issue.status,
                    "is_regression": issue.is_regression,
                    "first_seen": issue.first_seen.isoformat() if issue.first_seen else None,
                    "last_seen": issue.last_seen.isoformat() if issue.last_seen else None,
                    "recent_error_samples": events_data,
                })

        context["linked_issues"] = linked_issues_data

        # 3. Recent Releases in this Project & Environment
        # Lookback up to 48h before incident started
        lookback_start = incident.started_at - timedelta(hours=48)
        recent_releases = (
            db.query(Release)
            .filter(
                Release.project_id == project_id,
                Release.environment == incident.environment,
                Release.created_at >= lookback_start,
            )
            .order_by(desc(Release.created_at))
            .limit(5)
            .all()
        )
        context["recent_releases"] = [
            {
                "id": r.id,
                "version": r.version,
                "commit_sha": r.commit_sha,
                "environment": r.environment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent_releases
        ]

        # 4. Recent Feature Flag Changes & Audit Logs in this Project
        flag_audits = (
            db.query(FlagAuditLog, FeatureFlag)
            .join(FeatureFlag, FlagAuditLog.flag_id == FeatureFlag.id)
            .filter(
                FeatureFlag.project_id == project_id,
                FlagAuditLog.created_at >= lookback_start,
            )
            .order_by(desc(FlagAuditLog.created_at))
            .limit(10)
            .all()
        )
        context["recent_flag_mutations"] = [
            {
                "audit_id": audit.id,
                "flag_id": flag.id,
                "flag_key": flag.key,
                "action": audit.action,
                "before_state": audit.before_state,
                "after_state": audit.after_state,
                "created_at": audit.created_at.isoformat() if audit.created_at else None,
            }
            for audit, flag in flag_audits
        ]

        # 5. Existing Mitigations for this Incident
        context["existing_mitigations"] = [
            {
                "id": m.id,
                "action_type": m.action_type,
                "target_flag_id": m.target_flag_id,
                "target_flag_key": m.target_flag.key if m.target_flag else None,
                "status": m.status,
                "confidence": m.confidence,
                "reason": m.reason,
                "executed_at": m.executed_at.isoformat() if m.executed_at else None,
            }
            for m in incident.mitigations
        ]

        # 6. Incident Timeline Events
        context["incident_timeline"] = [
            {
                "id": ev.id,
                "event_type": ev.event_type,
                "message": ev.message,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
            }
            for ev in incident.events
        ]

        # Apply thorough secret scrubbing to the entire assembled context
        return scrub_secrets(context)

    @classmethod
    def compute_context_hash(cls, context: Dict[str, Any]) -> str:
        """
        Computes a deterministic SHA-256 hash of the normalized context JSON.
        Used for caching analysis results when incident telemetry has not changed.
        """
        serialized = json.dumps(context, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def format_untrusted_data_envelope(cls, context: Dict[str, Any]) -> str:
        """
        Formats the context JSON inside explicit untrusted data boundary tags
        to prevent prompt injection attacks.
        """
        data_json = json.dumps(context, indent=2, default=str)
        return (
            "<untrusted_incident_data>\n"
            f"{data_json}\n"
            "</untrusted_incident_data>"
        )


compute_context_hash = IncidentContextBuilder.compute_context_hash
format_untrusted_data_envelope = IncidentContextBuilder.format_untrusted_data_envelope
