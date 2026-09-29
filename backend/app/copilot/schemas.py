"""
Phase 15A — AI Incident Copilot schemas.
Defines strict, structured, provider-independent output and API schemas.
Every hypothesis must distinguish evidence from inference.
"""

from datetime import datetime
from typing import List, Literal, Optional
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
