"""
Base provider interface and exception hierarchy for AI Copilot.
"""

from abc import ABC, abstractmethod
from app.copilot.schemas import CopilotAnalysisPayload, CopilotChatPayload


class CopilotProviderError(Exception):
    """Base exception for all Copilot provider errors."""
    pass


class CopilotTimeoutError(CopilotProviderError):
    """Raised when the LLM provider times out."""
    pass


class CopilotResponseParseError(CopilotProviderError):
    """Raised when the LLM response cannot be parsed into the expected schema."""
    pass


class BaseCopilotProvider(ABC):
    """
    Abstract interface for AI analysis providers.
    All providers must implement `analyze` returning a validated CopilotAnalysisPayload,
    and `chat` returning a validated CopilotChatPayload.
    """

    def __init__(self, model_name: str, timeout_seconds: float = 30.0) -> None:
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the canonical provider identifier (e.g., 'gemini', 'openai', 'mock')."""
        pass

    @abstractmethod
    async def analyze(self, system_prompt: str, user_prompt: str) -> CopilotAnalysisPayload:
        """
        Executes an analysis request against the underlying model.
        Returns a validated CopilotAnalysisPayload or raises CopilotProviderError.
        """
        pass

    @abstractmethod
    async def chat(self, system_prompt: str, user_prompt: str) -> CopilotChatPayload:
        """
        Executes a conversational inquiry request against the underlying model.
        Returns a validated CopilotChatPayload or raises CopilotProviderError.
        """
        pass
