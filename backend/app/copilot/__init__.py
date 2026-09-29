"""
Phase 15A — AI Incident Copilot foundation package.
"""

from app.copilot.context import IncidentContextBuilder
from app.copilot.providers import (
    BaseCopilotProvider,
    CopilotProviderError,
    CopilotResponseParseError,
    CopilotTimeoutError,
    GeminiCopilotProvider,
    MockCopilotProvider,
    OpenAICopilotProvider,
    get_copilot_provider,
)
from app.copilot.schemas import (
    CopilotAnalysisPayload,
    CopilotAnalysisRequest,
    CopilotAnalysisResponse,
    EvidenceItem,
    Hypothesis,
    RecentChangeItem,
    RecommendedAction,
    UncertaintyItem,
)
from app.copilot.service import CopilotService

__all__ = [
    "BaseCopilotProvider",
    "CopilotAnalysisPayload",
    "CopilotAnalysisRequest",
    "CopilotAnalysisResponse",
    "CopilotProviderError",
    "CopilotResponseParseError",
    "CopilotService",
    "CopilotTimeoutError",
    "EvidenceItem",
    "GeminiCopilotProvider",
    "Hypothesis",
    "IncidentContextBuilder",
    "MockCopilotProvider",
    "OpenAICopilotProvider",
    "RecentChangeItem",
    "RecommendedAction",
    "UncertaintyItem",
    "get_copilot_provider",
]
