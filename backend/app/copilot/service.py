"""
Phase 15A — AI Incident Copilot Service.
Orchestrates context generation, provider interaction, caching, and persistence.
Guarantees tenant isolation, safe error handling, and zero state corruption on failure.
"""

import json
import logging
import time
from typing import List, Optional, Tuple
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
from app.models import (
    ErrorEvent,
    FeatureFlag,
    Incident,
    IncidentCopilotAnalysis,
    IncidentCopilotMessage,
    IncidentEvent,
    IncidentMitigation,
    Issue,
    Release,
    utcnow,
)

logger = logging.getLogger("releaseguard.copilot.service")


class CopilotService:
    """
    Coordinates incident analysis workflows.
    Reuses existing models and services, respects RBAC, and caches results by context hash.
    """

    @classmethod
    def validate_evidence_integrity(
        cls,
        evidence_items: List[CopilotChatEvidenceItem],
        incident: Incident,
        db: Session,
    ) -> Tuple[List[CopilotChatEvidenceItem], List[str]]:
        """
        Validates that every evidence citation returned by Copilot corresponds to
        an authentic entity within the current authorized project and tenant.
        Discards unverified citations and returns discarded notes to append to uncertainties.
        """
        valid_items: List[CopilotChatEvidenceItem] = []
        discarded_notes: List[str] = []

        project_id = incident.project_id
        tenant_id = incident.tenant_id

        for item in evidence_items:
            source_type = (item.source_type or "").strip().lower()
            source_id = item.source_id
            is_valid = False

            if source_type == "incident":
                try:
                    inc_id = int(source_id)
                    inc = (
                        db.query(Incident)
                        .filter(
                            Incident.id == inc_id,
                            Incident.project_id == project_id,
                            Incident.tenant_id == tenant_id,
                        )
                        .first()
                    )
                    is_valid = inc is not None
                except (ValueError, TypeError):
                    is_valid = False

            elif source_type == "issue":
                try:
                    iss_id = int(source_id)
                    iss = (
                        db.query(Issue)
                        .filter(Issue.id == iss_id, Issue.project_id == project_id)
                        .first()
                    )
                    is_valid = iss is not None
                except (ValueError, TypeError):
                    is_valid = False

            elif source_type == "release":
                try:
                    rel = (
                        db.query(Release)
                        .filter(
                            (Release.id == int(source_id)) if str(source_id).isdigit() else (Release.version == str(source_id)),
                            Release.project_id == project_id,
                        )
                        .first()
                    )
                    is_valid = rel is not None
                except Exception:
                    is_valid = False

            elif source_type in ("feature_flag", "flag_audit"):
                try:
                    flag = (
                        db.query(FeatureFlag)
                        .filter(
                            (FeatureFlag.id == int(source_id)) if str(source_id).isdigit() else (FeatureFlag.key == str(source_id)),
                            FeatureFlag.project_id == project_id,
                        )
                        .first()
                    )
                    is_valid = flag is not None
                except Exception:
                    is_valid = False

            elif source_type == "mitigation":
                try:
                    mit_id = int(source_id)
                    mit = (
                        db.query(IncidentMitigation)
                        .join(Incident, IncidentMitigation.incident_id == Incident.id)
                        .filter(
                            IncidentMitigation.id == mit_id,
                            Incident.project_id == project_id,
                        )
                        .first()
                    )
                    is_valid = mit is not None
                except (ValueError, TypeError):
                    is_valid = False

            elif source_type in ("timeline", "event"):
                try:
                    ev = (
                        db.query(IncidentEvent)
                        .filter(
                            IncidentEvent.id == int(source_id),
                            IncidentEvent.incident_id == incident.id,
                        )
                        .first()
                    )
                    if not ev and isinstance(source_id, str):
                        ev = (
                            db.query(ErrorEvent)
                            .filter(
                                ErrorEvent.event_id == source_id,
                                ErrorEvent.project_id == project_id,
                            )
                            .first()
                        )
                    is_valid = ev is not None
                except Exception:
                    is_valid = False

            if is_valid:
                valid_items.append(item)
            else:
                logger.warning(
                    "Copilot cited unverified evidence: source_type=%s source_id=%s for incident #%d in project #%d",
                    item.source_type,
                    item.source_id,
                    incident.id,
                    project_id,
                )
                discarded_notes.append(
                    f"Unverified evidence citation discarded: '{item.source_type}' reference '{item.source_id}' does not exist in authorized project #{project_id}."
                )

        return valid_items, discarded_notes

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
        start_time = time.monotonic()
        # 1. Build authorized, sanitized context
        t0 = time.monotonic()
        context = IncidentContextBuilder.build_context(incident, db)
        context_hash = IncidentContextBuilder.compute_context_hash(context)
        context_build_ms = round((time.monotonic() - t0) * 1000, 2)

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
                    total_request_ms = round((time.monotonic() - start_time) * 1000, 2)
                    logger.info(
                        "Copilot analysis metrics: context_build_ms=%.2f provider_request_ms=0.00 total_request_ms=%.2f model_used=%s provider_used=%s cache_hit=True fallback_used=False",
                        context_build_ms,
                        total_request_ms,
                        cached_record.model,
                        cached_record.provider,
                    )
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
        t1 = time.monotonic()
        analysis_payload = await active_provider.analyze(
            system_prompt=COPILOT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        provider_request_ms = round((time.monotonic() - t1) * 1000, 2)
        total_request_ms = round((time.monotonic() - start_time) * 1000, 2)
        fallback_used = (
            getattr(active_provider, "model_name", None) == getattr(active_provider, "fallback_model", None)
            and getattr(active_provider, "fallback_model", None) is not None
        )
        logger.info(
            "Copilot analysis metrics: context_build_ms=%.2f provider_request_ms=%.2f total_request_ms=%.2f model_used=%s provider_used=%s cache_hit=False fallback_used=%s",
            context_build_ms,
            provider_request_ms,
            total_request_ms,
            active_provider.model_name,
            active_provider.provider_name,
            fallback_used,
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
        tenant_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> Optional[CopilotAnalysisResponse]:
        """
        Retrieves the most recent persisted analysis for an incident, if one exists.
        Guarantees tenant and project isolation when tenant_id or project_id are provided.
        """
        query = (
            db.query(IncidentCopilotAnalysis)
            .join(Incident, IncidentCopilotAnalysis.incident_id == Incident.id)
            .filter(IncidentCopilotAnalysis.incident_id == incident_id)
        )
        if tenant_id is not None:
            query = query.filter(Incident.tenant_id == tenant_id)
        if project_id is not None:
            query = query.filter(Incident.project_id == project_id)

        record = query.order_by(
            desc(IncidentCopilotAnalysis.created_at),
            desc(IncidentCopilotAnalysis.id),
        ).first()

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
        - Retrieve latest persisted analysis if available (scoped by tenant and project).
        - Load bounded recent chat history (COPILOT_CHAT_HISTORY_LIMIT).
        - Persist user message to IncidentCopilotMessage.
        - Envelop all data in untrusted boundaries and format chat user prompt.
        - Call provider.chat().
        - Persist assistant response to IncidentCopilotMessage.
        - Return CopilotChatResponse.
        """
        # 1. Clean user message
        start_time = time.monotonic()
        clean_user_message = scrub_secrets(user_message.strip())

        # 2. Get or build authorized, sanitized incident context & hash
        t0 = time.monotonic()
        context, context_hash = IncidentContextBuilder.get_or_build_context(incident, db)
        context_build_ms = round((time.monotonic() - t0) * 1000, 2)

        # 3. Retrieve latest analysis if available (strictly tenant and project scoped)
        latest_analysis = cls.get_latest_analysis(
            incident_id=incident.id,
            db=db,
            tenant_id=incident.tenant_id,
            project_id=incident.project_id,
        )
        persisted_analysis_envelope = None
        if latest_analysis and latest_analysis.analysis:
            persisted_analysis_envelope = IncidentContextBuilder.format_persisted_analysis_envelope(
                latest_analysis.analysis
            )
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
                "content": scrub_secrets(text_content),
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
            persisted_analysis_envelope=persisted_analysis_envelope,
            latest_analysis_summary=latest_summary,
        )

        # 7. Execute model chat
        active_provider = provider or get_copilot_provider()
        logger.info(
            "Executing Copilot chat for incident #%d using provider '%s'",
            incident.id,
            active_provider.provider_name,
        )
        t1 = time.monotonic()
        chat_payload = await active_provider.chat(
            system_prompt=COPILOT_CHAT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        provider_request_ms = round((time.monotonic() - t1) * 1000, 2)
        total_request_ms = round((time.monotonic() - start_time) * 1000, 2)
        fallback_used = (
            getattr(active_provider, "model_name", None) == getattr(active_provider, "fallback_model", None)
            and getattr(active_provider, "fallback_model", None) is not None
        )
        logger.info(
            "Copilot chat metrics: context_build_ms=%.2f provider_request_ms=%.2f total_request_ms=%.2f model_used=%s provider_used=%s cache_hit=False fallback_used=%s",
            context_build_ms,
            provider_request_ms,
            total_request_ms,
            active_provider.model_name,
            active_provider.provider_name,
            fallback_used,
        )

        # Validate evidence citations against current authorized project & tenant
        validated_evidence, discarded_notes = cls.validate_evidence_integrity(
            evidence_items=chat_payload.evidence,
            incident=incident,
            db=db,
        )
        chat_payload.evidence = validated_evidence
        if discarded_notes:
            chat_payload.uncertainties.extend(discarded_notes)

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
