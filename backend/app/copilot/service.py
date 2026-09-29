"""
Phase 15A — AI Incident Copilot Service.
Orchestrates context generation, provider interaction, caching, and persistence.
Guarantees tenant isolation, safe error handling, and zero state corruption on failure.
"""

import json
import logging
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.copilot.context import IncidentContextBuilder
from app.copilot.prompts import COPILOT_SYSTEM_PROMPT, build_copilot_user_prompt
from app.copilot.providers import (
    BaseCopilotProvider,
    CopilotProviderError,
    CopilotResponseParseError,
    CopilotTimeoutError,
    get_copilot_provider,
)
from app.copilot.schemas import CopilotAnalysisPayload, CopilotAnalysisResponse
from app.models import Incident, IncidentCopilotAnalysis, utcnow

logger = logging.getLogger("releaseguard.copilot.service")


class CopilotService:
    """
    Coordinates incident analysis workflows.
    Reuses existing models and services, respects RBAC, and caches results by context hash.
    """

    @classmethod
    async def analyze_incident(
        cls,
        incident: Incident,
        db: Session,
        force_refresh: bool = False,
        provider: Optional[BaseCopilotProvider] = None,
    ) -> CopilotAnalysisResponse:
        """
        Generates or retrieves a cached AI analysis for a given incident.
        Guarantees that provider failures do not alter or damage the incident record.
        """
        # 1. Build authorized, sanitized context
        context = IncidentContextBuilder.build_context(incident, db)
        context_hash = IncidentContextBuilder.compute_context_hash(context)

        # 2. Check for matching cached analysis if force_refresh is not requested
        if not force_refresh:
            cached_record = (
                db.query(IncidentCopilotAnalysis)
                .filter(
                    IncidentCopilotAnalysis.incident_id == incident.id,
                    IncidentCopilotAnalysis.context_hash == context_hash,
                )
                .order_by(desc(IncidentCopilotAnalysis.created_at))
                .first()
            )
            if cached_record is not None:
                try:
                    payload = CopilotAnalysisPayload.model_validate_json(cached_record.analysis_json)
                    return CopilotAnalysisResponse(
                        id=cached_record.id,
                        incident_id=incident.id,
                        provider=cached_record.provider,
                        model=cached_record.model,
                        cached=True,
                        context_hash=context_hash,
                        analysis=payload,
                        created_at=cached_record.created_at,
                    )
                except Exception as exc:
                    logger.warning("Cached copilot analysis #%d failed validation; re-running: %s", cached_record.id, exc)

        # 3. Resolve LLM provider
        active_provider = provider or get_copilot_provider()

        # 4. Envelop untrusted context into prompts
        envelope = IncidentContextBuilder.format_untrusted_data_envelope(context)
        user_prompt = build_copilot_user_prompt(envelope)

        # 5. Execute model analysis
        logger.info("Executing Copilot analysis for incident #%d using provider '%s'", incident.id, active_provider.provider_name)
        analysis_payload = await active_provider.analyze(
            system_prompt=COPILOT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        # 6. Persist generated analysis
        now = utcnow()
        analysis_record = IncidentCopilotAnalysis(
            incident_id=incident.id,
            provider=active_provider.provider_name,
            model=active_provider.model_name,
            analysis_json=analysis_payload.model_dump_json(),
            context_hash=context_hash,
            created_at=now,
        )
        db.add(analysis_record)
        db.commit()
        db.refresh(analysis_record)

        return CopilotAnalysisResponse(
            id=analysis_record.id,
            incident_id=incident.id,
            provider=analysis_record.provider,
            model=analysis_record.model,
            cached=False,
            context_hash=context_hash,
            analysis=analysis_payload,
            created_at=analysis_record.created_at,
        )

    @classmethod
    def get_latest_analysis(
        cls,
        incident_id: int,
        db: Session,
    ) -> Optional[CopilotAnalysisResponse]:
        """
        Retrieves the most recent persisted analysis for an incident, if one exists.
        """
        record = (
            db.query(IncidentCopilotAnalysis)
            .filter(IncidentCopilotAnalysis.incident_id == incident_id)
            .order_by(desc(IncidentCopilotAnalysis.created_at))
            .first()
        )
        if record is None:
            return None

        try:
            payload = CopilotAnalysisPayload.model_validate_json(record.analysis_json)
            return CopilotAnalysisResponse(
                id=record.id,
                incident_id=incident_id,
                provider=record.provider,
                model=record.model,
                cached=True,
                context_hash=record.context_hash,
                analysis=payload,
                created_at=record.created_at,
            )
        except Exception as exc:
            logger.error("Failed to parse persisted analysis #%d: %s", record.id, exc)
            return None
