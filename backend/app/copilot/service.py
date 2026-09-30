"""
Phase 15A — AI Incident Copilot Service.
Orchestrates context generation, provider interaction, caching, and persistence.
Guarantees tenant isolation, safe error handling, and zero state corruption on failure.
"""

import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.config import settings
from app.copilot.context import IncidentContextBuilder, scrub_secrets
from app.copilot.prompts import (
    COPILOT_SYSTEM_PROMPT,
    COPILOT_CHAT_SYSTEM_PROMPT,
    build_copilot_user_prompt,
    build_copilot_chat_prompt,
)
from app.copilot.providers import (
    BaseCopilotProvider,
    CopilotProviderError,
    CopilotResponseParseError,
    CopilotTimeoutError,
    get_copilot_provider,
)
from app.copilot.schemas import (
    CopilotAnalysisPayload,
    CopilotAnalysisResponse,
    CopilotChatEvidenceItem,
    CopilotChatPayload,
    CopilotChatResponse,
    CopilotChatMessageResponse,
)
from app.models import Incident, IncidentCopilotAnalysis, IncidentCopilotMessage, utcnow

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

    @classmethod
    async def chat_incident(
        cls,
        incident: Incident,
        user_message: str,
        user_id: int,
        db: Session,
        provider: Optional[BaseCopilotProvider] = None,
    ) -> CopilotChatResponse:
        """
        Coordinates conversational incident investigation inquiries.
        - Scrub secrets from user message.
        - Fetch or compute incident context & context_hash.
        - Retrieve latest persisted analysis summary if available.
        - Load bounded recent chat history (COPILOT_CHAT_HISTORY_LIMIT).
        - Persist user message to IncidentCopilotMessage.
        - Envelop all data in untrusted boundaries and format chat user prompt.
        - Call provider.chat().
        - Persist assistant response to IncidentCopilotMessage.
        - Return CopilotChatResponse.
        """
        # 1. Clean user message
        clean_user_message = scrub_secrets(user_message.strip())

        # 2. Get or build authorized, sanitized incident context & hash
        context, context_hash = IncidentContextBuilder.get_or_build_context(incident, db)

        # 3. Retrieve latest analysis summary if available
        latest_analysis = cls.get_latest_analysis(incident.id, db)
        latest_summary = latest_analysis.analysis.summary if latest_analysis else None

        # 4. Load bounded chat history (configured limit, e.g. 12)
        history_limit = settings.COPILOT_CHAT_HISTORY_LIMIT
        recent_messages = (
            db.query(IncidentCopilotMessage)
            .filter(IncidentCopilotMessage.incident_id == incident.id)
            .order_by(desc(IncidentCopilotMessage.created_at), desc(IncidentCopilotMessage.id))
            .limit(history_limit)
            .all()
        )
        recent_messages = list(reversed(recent_messages))
        chat_history_dicts = []
        for m in recent_messages:
            text_content = m.content
            if m.role == "assistant":
                try:
                    parsed = json.loads(m.content)
                    if isinstance(parsed, dict) and "answer" in parsed:
                        text_content = parsed["answer"]
                except Exception:
                    pass
            chat_history_dicts.append({
                "role": m.role,
                "content": text_content,
            })

        # 5. Persist user message record
        now = utcnow()
        user_msg_record = IncidentCopilotMessage(
            incident_id=incident.id,
            user_id=user_id,
            role="user",
            content=clean_user_message,
            context_hash=context_hash,
            created_at=now,
        )
        db.add(user_msg_record)
        db.commit()
        db.refresh(user_msg_record)

        # 6. Format prompt
        envelope = IncidentContextBuilder.format_untrusted_data_envelope(context)
        user_prompt = build_copilot_chat_prompt(
            envelope=envelope,
            chat_history=chat_history_dicts,
            current_question=clean_user_message,
            latest_analysis_summary=latest_summary,
        )

        # 7. Execute model chat
        active_provider = provider or get_copilot_provider()
        logger.info(
            "Executing Copilot chat for incident #%d using provider '%s'",
            incident.id,
            active_provider.provider_name,
        )
        chat_payload = await active_provider.chat(
            system_prompt=COPILOT_CHAT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        # 8. Persist assistant message record
        assistant_now = utcnow()
        assistant_msg_record = IncidentCopilotMessage(
            incident_id=incident.id,
            user_id=user_id,
            role="assistant",
            content=chat_payload.model_dump_json(),
            context_hash=context_hash,
            model=active_provider.model_name,
            provider=active_provider.provider_name,
            created_at=assistant_now,
        )
        db.add(assistant_msg_record)
        db.commit()
        db.refresh(assistant_msg_record)

        return CopilotChatResponse(
            id=assistant_msg_record.id,
            incident_id=incident.id,
            user_message=clean_user_message,
            answer=chat_payload.answer,
            model=active_provider.model_name,
            cached=False,
            created_at=assistant_msg_record.created_at,
            evidence=chat_payload.evidence,
            uncertainties=chat_payload.uncertainties,
        )

    @classmethod
    def get_chat_history(
        cls,
        incident_id: int,
        db: Session,
        limit: int = 50,
    ) -> List[CopilotChatMessageResponse]:
        """
        Retrieves recent conversation history for an incident in ascending chronological order.
        Parses structured assistant fields when available.
        """
        records = (
            db.query(IncidentCopilotMessage)
            .filter(IncidentCopilotMessage.incident_id == incident_id)
            .order_by(desc(IncidentCopilotMessage.created_at), desc(IncidentCopilotMessage.id))
            .limit(limit)
            .all()
        )
        records = list(reversed(records))

        result: List[CopilotChatMessageResponse] = []
        for r in records:
            answer = None
            evidence = None
            uncertainties = None
            display_content = r.content

            if r.role == "assistant":
                try:
                    parsed = json.loads(r.content)
                    if isinstance(parsed, dict) and "answer" in parsed:
                        answer = parsed["answer"]
                        display_content = parsed["answer"]
                        if "evidence" in parsed and isinstance(parsed["evidence"], list):
                            evidence = [CopilotChatEvidenceItem(**ev) for ev in parsed["evidence"]]
                        if "uncertainties" in parsed and isinstance(parsed["uncertainties"], list):
                            uncertainties = parsed["uncertainties"]
                except Exception:
                    answer = r.content

            result.append(
                CopilotChatMessageResponse(
                    id=r.id,
                    incident_id=r.incident_id,
                    user_id=r.user_id,
                    role=r.role,
                    content=display_content,
                    created_at=r.created_at,
                    context_hash=r.context_hash,
                    model=r.model,
                    provider=r.provider,
                    answer=answer,
                    evidence=evidence,
                    uncertainties=uncertainties,
                )
            )

        return result
