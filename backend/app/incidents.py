"""
Phase 9 — Incident Response & Controlled Mitigation Services.
Includes:
1. SpikeDetectionService: deterministic window calculation, rate comparison, and duplicate incident prevention.
2. CorrelationService: inspects recent releases and feature flag mutations around incident creation.
3. MitigationService: advisory mitigation recommendations and explicit, idempotent mitigation approval execution.
"""

from datetime import datetime, timedelta, timezone
import json
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import (
    Incident,
    IncidentEvent,
    IncidentMitigation,
    ErrorEvent,
    Release,
    FeatureFlag,
    FlagSetting,
    FlagAuditLog,
    Environment,
    Issue,
    User,
    utcnow,
)


class SpikeDetectionService:
    """
    Deterministic error spike detection comparing a recent window to a baseline window.
    No machine learning or non-deterministic anomaly claims.
    """

    @staticmethod
    def detect_spike(
        issue_id: int,
        project_id: int,
        environment: str = "production",
        current_window_minutes: int = 15,
        baseline_window_minutes: int = 60,
        min_current_events: int = 5,
        spike_ratio_threshold: float = 2.0,
        now: datetime | None = None,
        db: Session | None = None,
    ) -> dict[str, Any]:
        if now is None:
            now = utcnow()

        current_start = now - timedelta(minutes=current_window_minutes)
        baseline_start = current_start - timedelta(minutes=baseline_window_minutes)

        # Query events in current window
        current_events_query = db.query(ErrorEvent).filter(
            ErrorEvent.issue_id == issue_id,
            ErrorEvent.project_id == project_id,
            ErrorEvent.received_at >= current_start,
            ErrorEvent.received_at <= now,
        )
        current_count = current_events_query.count()

        # Query events in baseline window
        baseline_events_query = db.query(ErrorEvent).filter(
            ErrorEvent.issue_id == issue_id,
            ErrorEvent.project_id == project_id,
            ErrorEvent.received_at >= baseline_start,
            ErrorEvent.received_at < current_start,
        )
        baseline_count = baseline_events_query.count()

        current_rate = float(current_count) / float(current_window_minutes)
        baseline_rate = float(baseline_count) / float(baseline_window_minutes)

        # Handle zero baseline gracefully by using floor of 1 event across baseline window
        if baseline_rate <= 0.0:
            effective_baseline_rate = 1.0 / float(baseline_window_minutes)
        else:
            effective_baseline_rate = baseline_rate

        spike_ratio = current_rate / effective_baseline_rate

        is_spike = (current_count >= min_current_events) and (spike_ratio >= spike_ratio_threshold)

        return {
            "is_spike": is_spike,
            "issue_id": issue_id,
            "project_id": project_id,
            "environment": environment,
            "current_count": current_count,
            "baseline_count": baseline_count,
            "current_rate": round(current_rate, 4),
            "baseline_rate": round(baseline_rate, 4),
            "spike_ratio": round(spike_ratio, 2),
            "threshold": spike_ratio_threshold,
            "min_events_required": min_current_events,
            "evaluated_at": now.isoformat(),
        }

    @staticmethod
    def is_duplicate_incident(
        issue_id: int,
        project_id: int,
        environment: str = "production",
        cooldown_minutes: int = 60,
        now: datetime | None = None,
        db: Session | None = None,
    ) -> bool:
        """
        Prevents repeated duplicate incidents for the same issue/environment/time window.
        """
        if now is None:
            now = utcnow()

        cooldown_start = now - timedelta(minutes=cooldown_minutes)

        existing = (
            db.query(Incident)
            .filter(
                Incident.project_id == project_id,
                Incident.related_issue_id == issue_id,
                Incident.environment == environment,
                Incident.status.in_(["triggered", "investigating", "mitigated"]),
                Incident.created_at >= cooldown_start,
            )
            .first()
        )
        return existing is not None


class CorrelationService:
    """
    Inspects recent releases and feature flag mutations around incident creation.
    Adheres strictly to cautious advisory correlation language:
    - 'correlated release'
    - 'recent flag change'
    - 'possible contributor'
    """

    @staticmethod
    def find_correlated_changes(
        project_id: int,
        environment: str,
        reference_time: datetime | None = None,
        lookback_hours: int = 24,
        issue_id: int | None = None,
        db: Session | None = None,
    ) -> list[dict[str, Any]]:
        if reference_time is None:
            reference_time = utcnow()

        window_start = reference_time - timedelta(hours=lookback_hours)
        correlated: list[dict[str, Any]] = []

        # 1. Inspect recent Releases
        releases = (
            db.query(Release)
            .filter(
                Release.project_id == project_id,
                Release.environment == environment,
                Release.created_at >= window_start,
                Release.created_at <= reference_time,
            )
            .order_by(desc(Release.created_at))
            .all()
        )

        # Check if any error events for this issue matched a specific release version
        matched_release_versions = set()
        if issue_id is not None:
            events_with_release = (
                db.query(ErrorEvent.release)
                .filter(
                    ErrorEvent.issue_id == issue_id,
                    ErrorEvent.release.isnot(None),
                )
                .distinct()
                .all()
            )
            matched_release_versions = {r[0] for r in events_with_release if r[0]}

        for rel in releases:
            is_in_stack = rel.version in matched_release_versions
            rel_type = (
                "correlated release (version observed in error payload)"
                if is_in_stack
                else "correlated release"
            )
            correlated.append({
                "type": "release",
                "item_id": rel.id,
                "title": f"Release v{rel.version}",
                "description": f"Deployed commit {rel.commit_sha or 'unknown'} to {rel.environment}",
                "relationship": rel_type,
                "changed_at": rel.created_at,
                "metadata": {
                    "version": rel.version,
                    "commit_sha": rel.commit_sha,
                    "environment": rel.environment,
                    "matched_in_error_events": is_in_stack,
                },
            })

        # 2. Inspect recent Feature Flag mutations
        env_obj = (
            db.query(Environment)
            .filter(Environment.project_id == project_id, Environment.key == environment)
            .first()
        )
        env_id = env_obj.id if env_obj else None

        flag_logs_query = (
            db.query(FlagAuditLog, FeatureFlag)
            .join(FeatureFlag, FlagAuditLog.flag_id == FeatureFlag.id)
            .filter(
                FeatureFlag.project_id == project_id,
                FlagAuditLog.created_at >= window_start,
                FlagAuditLog.created_at <= reference_time,
            )
        )
        if env_id:
            flag_logs_query = flag_logs_query.filter(
                (FlagAuditLog.environment_id == env_id) | (FlagAuditLog.environment_id.is_(None))
            )

        flag_logs = flag_logs_query.order_by(desc(FlagAuditLog.created_at)).all()

        for audit, flag in flag_logs:
            relationship = "recent flag change"
            if audit.action in ["update_rollout", "create", "update_setting"]:
                relationship = "possible contributor"

            correlated.append({
                "type": "feature_flag",
                "item_id": flag.id,
                "title": f"Flag '{flag.key}' {audit.action.replace('_', ' ')}",
                "description": f"Mutation '{audit.action}' performed on flag {flag.name}",
                "relationship": relationship,
                "changed_at": audit.created_at,
                "metadata": {
                    "flag_id": flag.id,
                    "flag_key": flag.key,
                    "action": audit.action,
                    "environment": environment,
                    "before_state": audit.before_state,
                    "after_state": audit.after_state,
                },
            })

        # Sort combined timeline by changed_at descending
        correlated.sort(key=lambda x: x["changed_at"], reverse=True)
        return correlated


class MitigationService:
    """
    Produces advisory mitigation recommendations and provides safe, idempotent,
    authorized approval execution.
    Initially supports exclusively: kill switch / rollout 0% on feature flags.
    """

    @staticmethod
    def recommend_mitigation(
        incident: Incident,
        db: Session,
    ) -> list[IncidentMitigation]:
        """
        Analyzes recent flag activity and returns advisory mitigation recommendations.
        """
        env_obj = (
            db.query(Environment)
            .filter(
                Environment.project_id == incident.project_id,
                Environment.key == incident.environment,
            )
            .first()
        )
        if not env_obj:
            return []

        # Find active flag settings that were modified recently or are enabled
        active_settings = (
            db.query(FlagSetting, FeatureFlag)
            .join(FeatureFlag, FlagSetting.flag_id == FeatureFlag.id)
            .filter(
                FeatureFlag.project_id == incident.project_id,
                FlagSetting.environment_id == env_obj.id,
                FlagSetting.enabled.is_(True),
                FeatureFlag.archived_at.is_(None),
            )
            .all()
        )

        recommendations: list[IncidentMitigation] = []
        now = utcnow()

        for setting, flag in active_settings:
            # Check recent mutations
            recent_audit = (
                db.query(FlagAuditLog)
                .filter(
                    FlagAuditLog.flag_id == flag.id,
                    FlagAuditLog.environment_id == env_obj.id,
                    FlagAuditLog.created_at >= incident.started_at - timedelta(hours=24),
                )
                .order_by(desc(FlagAuditLog.created_at))
                .first()
            )

            rollout_pct = setting.rollout.percentage if setting.rollout else 100

            # Compute advisory confidence based on proximity to incident start
            if recent_audit:
                time_diff_hours = abs((incident.started_at - recent_audit.created_at).total_seconds()) / 3600.0
                if time_diff_hours <= 2.0:
                    confidence = 0.85
                elif time_diff_hours <= 6.0:
                    confidence = 0.70
                else:
                    confidence = 0.55
                reason = (
                    f"Feature flag '{flag.key}' underwent mutation '{recent_audit.action}' "
                    f"approximately {round(time_diff_hours, 1)}h before/around the incident start. "
                    f"Current rollout is {rollout_pct}%. Disabling this flag will safely isolate possible regressions."
                )
            else:
                confidence = 0.40
                reason = (
                    f"Feature flag '{flag.key}' is currently enabled ({rollout_pct}% rollout) in {incident.environment}. "
                    f"It represents a candidate contributor. Disabling it will revert to safe default."
                )

            # Check if this mitigation was already recorded for this incident
            existing = (
                db.query(IncidentMitigation)
                .filter(
                    IncidentMitigation.incident_id == incident.id,
                    IncidentMitigation.target_flag_id == flag.id,
                    IncidentMitigation.target_environment_id == env_obj.id,
                )
                .first()
            )

            if not existing:
                mitigation = IncidentMitigation(
                    incident_id=incident.id,
                    action_type="kill_feature_flag",
                    target_flag_id=flag.id,
                    target_environment_id=env_obj.id,
                    reason=reason,
                    confidence=confidence,
                    status="pending",
                )
                db.add(mitigation)
                recommendations.append(mitigation)
            else:
                recommendations.append(existing)

        db.commit()
        return recommendations

    @staticmethod
    def approve_and_execute_mitigation(
        incident_id: int,
        mitigation_id: int,
        actor_id: int,
        db: Session,
    ) -> dict[str, Any]:
        """
        Executes explicit, authenticated mitigation approval.
        Guarantees:
        - Transactional safety
        - Idempotency (repeated approval of already executed mitigation is safe)
        - Kill-switch execution on target feature flag (enabled=False, percentage=0)
        - Flag audit row generation
        - Incident status update to 'mitigated'
        - Timeline event recording
        """
        mitigation = (
            db.query(IncidentMitigation)
            .filter(
                IncidentMitigation.id == mitigation_id,
                IncidentMitigation.incident_id == incident_id,
            )
            .first()
        )
        if not mitigation:
            raise ValueError(f"Mitigation #{mitigation_id} not found for incident #{incident_id}")

        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            raise ValueError(f"Incident #{incident_id} not found")

        actor = db.query(User).filter(User.id == actor_id).first()
        actor_email = actor.email if actor else f"user_{actor_id}"

        # IDEMPOTENCY CHECK: If already executed, return safe success without re-executing
        if mitigation.status == "executed":
            return {
                "idempotent": True,
                "status": "executed",
                "mitigation_id": mitigation.id,
                "incident_id": incident.id,
                "message": "Mitigation was previously approved and executed safely.",
                "executed_at": mitigation.executed_at.isoformat() if mitigation.executed_at else None,
                "approved_by": mitigation.approved_by,
            }

        if mitigation.action_type != "kill_feature_flag":
            raise ValueError(f"Unsupported mitigation action '{mitigation.action_type}'. Only 'kill_feature_flag' is permitted.")

        # Execute safe feature flag kill switch
        target_flag = db.query(FeatureFlag).filter(FeatureFlag.id == mitigation.target_flag_id).first()
        if not target_flag:
            raise ValueError(f"Target feature flag #{mitigation.target_flag_id} no longer exists")

        flag_setting = (
            db.query(FlagSetting)
            .filter(
                FlagSetting.flag_id == target_flag.id,
                FlagSetting.environment_id == mitigation.target_environment_id,
            )
            .first()
        )
        if not flag_setting:
            raise ValueError(f"Flag setting for flag #{target_flag.id} and environment #{mitigation.target_environment_id} not found")

        # Snapshot before state
        before_state = {
            "enabled": flag_setting.enabled,
            "default_variant": flag_setting.default_variant,
            "rollout_percentage": flag_setting.rollout.percentage if flag_setting.rollout else 0,
        }

        # Apply safe kill switch
        flag_setting.enabled = False
        if flag_setting.rollout:
            flag_setting.rollout.percentage = 0

        after_state = {
            "enabled": False,
            "default_variant": flag_setting.default_variant,
            "rollout_percentage": 0,
            "killed_by_incident": incident.id,
            "mitigation_id": mitigation.id,
        }

        # Record Flag Audit Log
        audit_log = FlagAuditLog(
            flag_id=target_flag.id,
            environment_id=mitigation.target_environment_id,
            actor_id=actor_id,
            action="kill",
            before_state=json.dumps(before_state),
            after_state=json.dumps(after_state),
            created_at=utcnow(),
        )
        db.add(audit_log)

        now = utcnow()
        # Update mitigation record
        mitigation.status = "executed"
        mitigation.approved_by = actor_id
        mitigation.approved_at = now
        mitigation.executed_at = now
        mitigation.previous_state = json.dumps(before_state)
        mitigation.execution_result = json.dumps({
            "status": "success",
            "action": "kill_feature_flag",
            "flag_id": target_flag.id,
            "flag_key": target_flag.key,
            "environment_id": mitigation.target_environment_id,
            "killed_at": now.isoformat(),
            "message": f"Successfully killed feature flag '{target_flag.key}'. Enabled set to false, rollout set to 0%.",
        })

        # Update Incident status
        incident.status = "mitigated"
        incident.mitigated_at = now
        incident.updated_at = now

        # Add Timeline events
        timeline_approval = IncidentEvent(
            incident_id=incident.id,
            actor_id=actor_id,
            event_type="mitigation_approved",
            message=f"Mitigation #{mitigation.id} ({mitigation.action_type}) approved by {actor_email}.",
            metadata_json=json.dumps({
                "mitigation_id": mitigation.id,
                "action_type": mitigation.action_type,
                "target_flag_key": target_flag.key,
            }),
            created_at=now,
        )
        db.add(timeline_approval)

        timeline_execution = IncidentEvent(
            incident_id=incident.id,
            actor_id=actor_id,
            event_type="mitigation_executed",
            message=f"Safe mitigation executed: Feature flag '{target_flag.key}' killed. Rollout reset to 0%, flag disabled.",
            metadata_json=json.dumps({
                "mitigation_id": mitigation.id,
                "action_type": mitigation.action_type,
                "target_flag_id": target_flag.id,
                "target_flag_key": target_flag.key,
            }),
            created_at=now,
        )
        db.add(timeline_execution)

        db.commit()

        return {
            "idempotent": False,
            "status": "executed",
            "mitigation_id": mitigation.id,
            "incident_id": incident.id,
            "flag_key": target_flag.key,
            "message": f"Feature flag '{target_flag.key}' successfully killed.",
            "executed_at": now.isoformat(),
            "approved_by": actor_id,
        }

    @staticmethod
    def apply_mitigation(
        incident_id: int,
        target_flag_id: int,
        target_environment_id: int | None,
        reason: str | None,
        actor_id: int,
        db: Session,
    ) -> dict[str, Any]:
        """
        Directly applies a feature-flag kill mitigation to an incident.
        Captures previous state, disables flag, sets rollout to 0%,
        records flag audit log and incident activity timeline event.
        """
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            raise ValueError(f"Incident #{incident_id} not found")

        actor = db.query(User).filter(User.id == actor_id).first()
        actor_email = actor.email if actor else f"user_{actor_id}"

        target_flag = (
            db.query(FeatureFlag)
            .filter(FeatureFlag.id == target_flag_id, FeatureFlag.project_id == incident.project_id)
            .first()
        )
        if not target_flag:
            raise ValueError(f"Target feature flag #{target_flag_id} not found in this project")

        if target_environment_id is not None:
            env_obj = (
                db.query(Environment)
                .filter(Environment.id == target_environment_id, Environment.project_id == incident.project_id)
                .first()
            )
        else:
            env_obj = (
                db.query(Environment)
                .filter(Environment.key == incident.environment, Environment.project_id == incident.project_id)
                .first()
            )

        if not env_obj:
            raise ValueError("Target environment not found for this project")

        flag_setting = (
            db.query(FlagSetting)
            .filter(FlagSetting.flag_id == target_flag.id, FlagSetting.environment_id == env_obj.id)
            .first()
        )
        if not flag_setting:
            raise ValueError(f"Flag setting for flag '{target_flag.key}' in environment '{env_obj.key}' not found")

        now = utcnow()
        before_state = {
            "enabled": flag_setting.enabled,
            "default_variant": flag_setting.default_variant,
            "rollout_percentage": flag_setting.rollout.percentage if flag_setting.rollout else 0,
        }

        # Apply kill switch
        flag_setting.enabled = False
        if flag_setting.rollout:
            flag_setting.rollout.percentage = 0

        # Record Flag Audit Log
        audit_log = FlagAuditLog(
            flag_id=target_flag.id,
            environment_id=env_obj.id,
            actor_id=actor_id,
            action="kill",
            before_state=json.dumps(before_state),
            after_state=json.dumps({"enabled": False, "rollout_percentage": 0, "killed_by_incident": incident.id}),
            created_at=now,
        )
        db.add(audit_log)

        # Create or update mitigation record
        mitigation = IncidentMitigation(
            incident_id=incident.id,
            action_type="kill_feature_flag",
            target_flag_id=target_flag.id,
            target_environment_id=env_obj.id,
            reason=reason or f"Emergency mitigation for incident #{incident.id}: Flag '{target_flag.key}' disabled.",
            confidence=1.0,
            status="executed",
            approved_by=actor_id,
            approved_at=now,
            executed_at=now,
            previous_state=json.dumps(before_state),
            execution_result=json.dumps({
                "status": "success",
                "action": "kill_feature_flag",
                "flag_id": target_flag.id,
                "flag_key": target_flag.key,
                "environment_id": env_obj.id,
                "killed_at": now.isoformat(),
            }),
            created_at=now,
            updated_at=now,
        )
        db.add(mitigation)

        # Update Incident status
        incident.status = "mitigated"
        if not incident.mitigated_at:
            incident.mitigated_at = now
        incident.updated_at = now

        # Add Timeline event
        timeline_event = IncidentEvent(
            incident_id=incident.id,
            actor_id=actor_id,
            event_type="mitigation_applied",
            message=f"Mitigation applied: Feature flag '{target_flag.key}' killed (disabled, 0% rollout) by {actor_email}.",
            metadata_json=json.dumps({
                "flag_id": target_flag.id,
                "flag_key": target_flag.key,
                "environment": env_obj.key,
                "previous_state": before_state,
            }),
            created_at=now,
        )
        db.add(timeline_event)

        db.commit()

        return {
            "idempotent": False,
            "status": "executed",
            "mitigation_id": mitigation.id,
            "incident_id": incident.id,
            "flag_key": target_flag.key,
            "message": f"Feature flag '{target_flag.key}' successfully killed.",
            "executed_at": now.isoformat(),
            "approved_by": actor_id,
            "previous_state": before_state,
        }

    @staticmethod
    def revert_mitigation(
        incident_id: int,
        mitigation_id: int,
        actor_id: int,
        db: Session,
    ) -> dict[str, Any]:
        """
        Reverts an executed feature-flag mitigation. Restores flag enabled state
        and rollout percentage to their exact pre-mitigation values.
        """
        mitigation = (
            db.query(IncidentMitigation)
            .filter(
                IncidentMitigation.id == mitigation_id,
                IncidentMitigation.incident_id == incident_id,
            )
            .first()
        )
        if not mitigation:
            raise ValueError(f"Mitigation #{mitigation_id} not found for incident #{incident_id}")

        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            raise ValueError(f"Incident #{incident_id} not found")

        actor = db.query(User).filter(User.id == actor_id).first()
        actor_email = actor.email if actor else f"user_{actor_id}"

        if mitigation.status == "reverted":
            return {
                "idempotent": True,
                "status": "reverted",
                "mitigation_id": mitigation.id,
                "incident_id": incident.id,
                "message": "Mitigation was already reverted.",
            }

        if mitigation.status != "executed":
            raise ValueError(f"Cannot revert mitigation #{mitigation_id} in '{mitigation.status}' status (must be executed).")

        target_flag = db.query(FeatureFlag).filter(FeatureFlag.id == mitigation.target_flag_id).first()
        if not target_flag:
            raise ValueError(f"Target flag #{mitigation.target_flag_id} no longer exists")

        flag_setting = (
            db.query(FlagSetting)
            .filter(
                FlagSetting.flag_id == target_flag.id,
                FlagSetting.environment_id == mitigation.target_environment_id,
            )
            .first()
        )
        if not flag_setting:
            raise ValueError("Flag setting no longer exists")

        # Parse pre-mitigation state
        prev_state = None
        if mitigation.previous_state:
            try:
                prev_state = json.loads(mitigation.previous_state)
            except Exception:
                pass

        if not prev_state:
            # Fallback to flag audit log
            audit = (
                db.query(FlagAuditLog)
                .filter(
                    FlagAuditLog.flag_id == target_flag.id,
                    FlagAuditLog.environment_id == mitigation.target_environment_id,
                    FlagAuditLog.action == "kill",
                )
                .order_by(desc(FlagAuditLog.created_at))
                .first()
            )
            if audit and audit.before_state:
                try:
                    prev_state = json.loads(audit.before_state)
                except Exception:
                    pass

        restored_enabled = prev_state.get("enabled", True) if prev_state else True
        restored_rollout = prev_state.get("rollout_percentage", 100) if prev_state else 100

        before_revert = {
            "enabled": flag_setting.enabled,
            "rollout_percentage": flag_setting.rollout.percentage if flag_setting.rollout else 0,
        }

        # Restore setting and rollout
        flag_setting.enabled = restored_enabled
        if flag_setting.rollout:
            flag_setting.rollout.percentage = restored_rollout

        now = utcnow()

        # Audit log for restoration
        db.add(
            FlagAuditLog(
                flag_id=target_flag.id,
                environment_id=mitigation.target_environment_id,
                actor_id=actor_id,
                action="revert_mitigation",
                before_state=json.dumps(before_revert),
                after_state=json.dumps({
                    "enabled": restored_enabled,
                    "rollout_percentage": restored_rollout,
                    "reverted_by_incident": incident.id,
                    "mitigation_id": mitigation.id,
                }),
                created_at=now,
            )
        )

        mitigation.status = "reverted"
        mitigation.updated_at = now

        # Add Timeline event
        db.add(
            IncidentEvent(
                incident_id=incident.id,
                actor_id=actor_id,
                event_type="mitigation_reverted",
                message=f"Mitigation #{mitigation.id} reverted by {actor_email}: Flag '{target_flag.key}' restored to previous state (enabled={restored_enabled}, rollout={restored_rollout}%).",
                metadata_json=json.dumps({
                    "mitigation_id": mitigation.id,
                    "target_flag_id": target_flag.id,
                    "target_flag_key": target_flag.key,
                    "restored_state": {
                        "enabled": restored_enabled,
                        "rollout_percentage": restored_rollout,
                    },
                }),
                created_at=now,
            )
        )

        db.commit()

        return {
            "idempotent": False,
            "status": "reverted",
            "mitigation_id": mitigation.id,
            "incident_id": incident.id,
            "flag_key": target_flag.key,
            "restored_state": {
                "enabled": restored_enabled,
                "rollout_percentage": restored_rollout,
            },
            "message": f"Feature flag '{target_flag.key}' restored to previous state.",
            "reverted_at": now.isoformat(),
            "reverted_by": actor_id,
        }

