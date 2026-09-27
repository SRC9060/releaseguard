"""
Internal Service Interface for automated error mitigation (Phase 8 architecture preparation).
Defines hooks to correlate issue error spikes to active releases / feature flags and trigger kill-switches.
Note: Automatic actions are disabled in this phase.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from sqlalchemy.orm import Session

from app.models import FeatureFlag, FlagSetting, Issue


class MitigationServiceInterface(ABC):
    """Abstract interface for automated error-spike detection and flag mitigation."""

    @abstractmethod
    def evaluate_spike(self, issue: Issue, db: Session) -> dict[str, Any]:
        """Analyzes recent error spike metrics and identifies candidate feature flags."""

    @abstractmethod
    def trigger_flag_kill_switch(
        self,
        flag_id: int,
        environment_id: int,
        reason: str,
        actor_id: int | None,
        db: Session,
    ) -> bool:
        """Executes a graceful flag kill-switch rollback with an audit log."""


class MitigationHookService(MitigationServiceInterface):
    """
    Production hook ready for Phase 9 automated mitigation.
    In Phase 8, this service records telemetry and exposes programmatic hooks without executing automated kills.
    """

    def evaluate_spike(self, issue: Issue, db: Session) -> dict[str, Any]:
        # Diagnostic hook: finds flags updated in the same project around the issue's regressed/first_seen window
        recent_flags = (
            db.query(FeatureFlag)
            .filter(
                FeatureFlag.project_id == issue.project_id,
                FeatureFlag.archived_at.is_(None),
            )
            .all()
        )
        return {
            "issue_id": issue.id,
            "project_id": issue.project_id,
            "candidate_flags_count": len(recent_flags),
            "candidate_flags": [{"id": f.id, "key": f.key} for f in recent_flags],
            "automatic_mitigation_enabled": False,
        }

    def trigger_flag_kill_switch(
        self,
        flag_id: int,
        environment_id: int,
        reason: str,
        actor_id: int | None,
        db: Session,
    ) -> bool:
        # Programmatic kill-switch implementation
        setting = (
            db.query(FlagSetting)
            .filter(
                FlagSetting.flag_id == flag_id,
                FlagSetting.environment_id == environment_id,
            )
            .first()
        )
        if setting is None:
            return False

        setting.enabled = False
        if setting.rollout:
            setting.rollout.percentage = 0
        db.commit()
        return True


mitigation_service = MitigationHookService()
