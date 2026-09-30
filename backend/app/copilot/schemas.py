"""
Phase 15A — AI Incident Copilot schemas.
Defines strict, structured, provider-independent output and API schemas.
Every hypothesis must distinguish evidence from inference.
"""

from datetime import datetime
from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    source: str = Field(description="Originating source of observable evidence (e.g., error_event, release, flag_audit, timeline)")
    description: str = Field(description="Fact-based, observable data point directly from telemetry")
    confidence: Literal["high", "medium", "low"] = Field(default="high", description="Degree of certainty that the observation is factual")


class Hypothesis(BaseModel):
    id: str = Field(description="Unique hypothesis identifier, e.g. H1, H2")
    title: str = Field(description="Concise statement of the potential contributing factor or root cause")
    explanation: str = Field(description="Detailed explanation of how this factor could explain the incident symptoms")
    evidence: List[str] = Field(description="Observable facts directly from telemetry that support this hypothesis")
    inference: List[str] = Field(description="Deductions, logical reasoning, and hypotheses distinguishing from verified facts")
    likelihood: Literal["plausible", "probable", "unlikely"] = Field(description="Assessed likelihood given currently available data")


class RecentChangeItem(BaseModel):
    type: Literal["release", "feature_flag", "setting", "environment", "other"] = Field(description="Category of the recent change")
    identifier: str = Field(description="Version string, flag key, or component name")
    description: str = Field(description="Summary of the change that occurred")
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp or relative time of the change")
    potential_relevance: str = Field(description="Objective assessment of proximity or connection to incident timing")


class RecommendedAction(BaseModel):
    action_type: Literal["mitigation", "investigation", "monitoring", "communication"] = Field(description="Class of recommended action")
    priority: Literal["immediate", "secondary", "post_incident"] = Field(description="Execution priority")
    description: str = Field(description="Actionable, concrete step recommended for operator review")
    rationale: str = Field(description="Why this action is advised based on the evidence")
    risk_assessment: str = Field(description="Potential side-effects, risks, or blast radius of taking this action")
    target_flag_key: Optional[str] = Field(default=None, description="Target feature flag key if action relates to a flag mitigation")
    target_environment: Optional[str] = Field(default=None, description="Target environment if applicable")


class UncertaintyItem(BaseModel):
    area: str = Field(description="Domain or component where certainty is lacking")
    missing_information: str = Field(description="What specific data is absent or unverified")
    how_to_verify: str = Field(description="Suggested telemetry, logs, or metrics needed to eliminate uncertainty")


class CopilotAnalysisPayload(BaseModel):
    """
    Standardized payload produced by the AI model.
    Must never claim causal certainty unless explicitly confirmed by data.
    """
    summary: str = Field(description="Executive technical summary of the incident symptoms, timeline, and current state")
    recent_changes: List[RecentChangeItem] = Field(default_factory=list, description="Recent releases, flag toggles, or deployments around the incident window")
    hypotheses: List[Hypothesis] = Field(default_factory=list, description="Ranked candidate explanations, explicitly separating evidence from inference")
    recommended_actions: List[RecommendedAction] = Field(default_factory=list, description="Prioritized, safe, human-reviewed next steps")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Key observable telemetry data points")
    uncertainties: List[UncertaintyItem] = Field(default_factory=list, description="Known gaps in telemetry or unverified assumptions")


class CopilotAnalysisRequest(BaseModel):
    force_refresh: bool = Field(default=False, description="If true, bypasses the context cache and invokes provider anew")


class CopilotAnalysisResponse(BaseModel):
    id: int
    incident_id: int
    provider: str
    model: str
    cached: bool
    context_hash: str
    analysis: CopilotAnalysisPayload
    created_at: datetime


# Standardized OpenAPI 3.0 / Gemini structured output schema reflecting the Pydantic contract
COPILOT_RESPONSE_SCHEMA = {
    "type": "object",
    "description": "Standardized payload produced by the AI model. Must never claim causal certainty unless explicitly confirmed by data.",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Executive technical summary of the incident symptoms, timeline, and current state",
        },
        "recent_changes": {
            "type": "array",
            "description": "Recent releases, flag toggles, or deployments around the incident window",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["release", "feature_flag", "setting", "environment", "other"],
                        "description": "Category of the recent change",
                    },
                    "identifier": {
                        "type": "string",
                        "description": "Version string, flag key, or component name",
                    },
                    "description": {
                        "type": "string",
                        "description": "Summary of the change that occurred",
                    },
                    "timestamp": {
                        "type": "string",
                        "description": "ISO timestamp or relative time of the change",
                    },
                    "potential_relevance": {
                        "type": "string",
                        "description": "Objective assessment of proximity or connection to incident timing",
                    },
                },
                "required": ["type", "identifier", "description", "potential_relevance"],
            },
        },
        "hypotheses": {
            "type": "array",
            "description": "Ranked candidate explanations, explicitly separating evidence from inference",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique hypothesis identifier, e.g. H1, H2",
                    },
                    "title": {
                        "type": "string",
                        "description": "Concise statement of the potential contributing factor or root cause",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Detailed explanation of how this factor could explain the incident symptoms",
                    },
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Observable facts directly from telemetry that support this hypothesis",
                    },
                    "inference": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Deductions, logical reasoning, and hypotheses distinguishing from verified facts",
                    },
                    "likelihood": {
                        "type": "string",
                        "enum": ["plausible", "probable", "unlikely"],
                        "description": "Assessed likelihood given currently available data",
                    },
                },
                "required": ["id", "title", "explanation", "evidence", "inference", "likelihood"],
            },
        },
        "recommended_actions": {
            "type": "array",
            "description": "Prioritized, safe, human-reviewed next steps",
            "items": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "enum": ["mitigation", "investigation", "monitoring", "communication"],
                        "description": "Class of recommended action",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["immediate", "secondary", "post_incident"],
                        "description": "Execution priority",
                    },
                    "description": {
                        "type": "string",
                        "description": "Actionable, concrete step recommended for operator review",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why this action is advised based on the evidence",
                    },
                    "risk_assessment": {
                        "type": "string",
                        "description": "Potential side-effects, risks, or blast radius of taking this action",
                    },
                    "target_flag_key": {
                        "type": "string",
                        "description": "Target feature flag key if action relates to a flag mitigation",
                    },
                    "target_environment": {
                        "type": "string",
                        "description": "Target environment if applicable",
                    },
                },
                "required": ["action_type", "priority", "description", "rationale", "risk_assessment"],
            },
        },
        "evidence": {
            "type": "array",
            "description": "Key observable telemetry data points",
            "items": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Originating source of observable evidence (e.g., error_event, release, flag_audit, timeline)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Fact-based, observable data point directly from telemetry",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Degree of certainty that the observation is factual",
                    },
                },
                "required": ["source", "description"],
            },
        },
        "uncertainties": {
            "type": "array",
            "description": "Known gaps in telemetry or unverified assumptions",
            "items": {
                "type": "object",
                "properties": {
                    "area": {
                        "type": "string",
                        "description": "Domain or component where certainty is lacking",
                    },
                    "missing_information": {
                        "type": "string",
                        "description": "What specific data is absent or unverified",
                    },
                    "how_to_verify": {
                        "type": "string",
                        "description": "Suggested telemetry, logs, or metrics needed to eliminate uncertainty",
                    },
                },
                "required": ["area", "missing_information", "how_to_verify"],
            },
        },
    },
    "required": ["summary", "hypotheses", "recommended_actions", "evidence", "uncertainties"],
}


# =========================================================================
# Phase 15C — Conversational Incident Copilot Schemas
# =========================================================================

class CopilotChatEvidenceItem(BaseModel):
    source_type: Literal[
        "incident",
        "issue",
        "release",
        "feature_flag",
        "flag_audit",
        "mitigation",
        "timeline",
        "event",
    ] = Field(description="Originating category of evidence")
    source_id: Optional[Union[int, str]] = Field(default=None, description="Identifier of the source entity (e.g. issue ID, release version, flag key)")
    claim: str = Field(description="Objective factual claim supported by this source")


class CopilotChatPayload(BaseModel):
    answer: str = Field(description="Natural-language response to the user's question, grounded strictly in available incident telemetry")
    evidence: List[CopilotChatEvidenceItem] = Field(default_factory=list, description="Structured evidence references supporting the answer")
    uncertainties: List[str] = Field(default_factory=list, description="Telemetry gaps, missing data points, or unverified aspects")


class CopilotChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User question about the incident")


class CopilotChatResponse(BaseModel):
    id: int
    incident_id: int
    user_message: str
    answer: str
    model: str
    cached: bool = False
    created_at: datetime
    evidence: List[CopilotChatEvidenceItem] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)


class CopilotChatMessageResponse(BaseModel):
    id: int
    incident_id: int
    user_id: int
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime
    context_hash: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    answer: Optional[str] = None
    evidence: Optional[List[CopilotChatEvidenceItem]] = None
    uncertainties: Optional[List[str]] = None


COPILOT_CHAT_RESPONSE_SCHEMA = {
    "type": "object",
    "description": "Conversational incident investigation answer grounded in authorized telemetry.",
    "properties": {
        "answer": {
            "type": "string",
            "description": "Natural-language answer to the user's question about the incident, citing evidence and distinguishing facts from inferences.",
        },
        "evidence": {
            "type": "array",
            "description": "Structured evidence citations supporting the claims in the answer.",
            "items": {
                "type": "object",
                "properties": {
                    "source_type": {
                        "type": "string",
                        "enum": [
                            "incident",
                            "issue",
                            "release",
                            "feature_flag",
                            "flag_audit",
                            "mitigation",
                            "timeline",
                            "event",
                        ],
                        "description": "Category of evidence source",
                    },
                    "source_id": {
                        "type": "string",
                        "description": "Identifier of the source entity (e.g. '1', 'v2.4.0', 'flag_key')",
                    },
                    "claim": {
                        "type": "string",
                        "description": "Factual statement supported by the telemetry",
                    },
                },
                "required": ["source_type", "claim"],
            },
        },
        "uncertainties": {
            "type": "array",
            "description": "Specific missing data, telemetry gaps, or verification steps needed.",
            "items": {
                "type": "string",
            },
        },
    },
    "required": ["answer", "evidence", "uncertainties"],
}
