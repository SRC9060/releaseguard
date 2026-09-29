"""
Copilot Provider factory and registry.
"""

from typing import Optional
from app.config import settings
from app.copilot.providers.base import (
    BaseCopilotProvider,
    CopilotProviderError,
    CopilotResponseParseError,
    CopilotTimeoutError,
)
from app.copilot.providers.gemini import GeminiCopilotProvider
from app.copilot.providers.mock import MockCopilotProvider
from app.copilot.providers.openai import OpenAICopilotProvider

__all__ = [
    "BaseCopilotProvider",
    "CopilotProviderError",
    "CopilotTimeoutError",
    "CopilotResponseParseError",
    "GeminiCopilotProvider",
    "MockCopilotProvider",
    "OpenAICopilotProvider",
    "get_copilot_provider",
]


def get_copilot_provider(provider_name: Optional[str] = None) -> BaseCopilotProvider:
    """
    Instantiates the configured Copilot provider.
    Selection precedence:
    1. Explicit provider_name argument
    2. settings.COPILOT_PROVIDER
    Falls back safely to MockCopilotProvider when running in development/test without credentials.
    """
    target = (provider_name or settings.COPILOT_PROVIDER or "gemini").lower().strip()

    if target == "mock":
        return MockCopilotProvider(
            model_name=settings.COPILOT_MODEL or "mock-model-v1",
            timeout_seconds=settings.COPILOT_TIMEOUT_SECONDS,
        )

    if target == "gemini":
        if settings.GEMINI_API_KEY:
            return GeminiCopilotProvider(
                api_key=settings.GEMINI_API_KEY,
                model_name=settings.COPILOT_MODEL or "gemini-2.5-flash",
                timeout_seconds=settings.COPILOT_TIMEOUT_SECONDS,
            )
        # Fallback to mock in dev/test if key not configured
        return MockCopilotProvider(
            model_name="mock-gemini-fallback",
            timeout_seconds=settings.COPILOT_TIMEOUT_SECONDS,
        )

    if target == "openai":
        if settings.OPENAI_API_KEY:
            return OpenAICopilotProvider(
                api_key=settings.OPENAI_API_KEY,
                model_name=settings.COPILOT_MODEL or "gpt-4o-mini",
                timeout_seconds=settings.COPILOT_TIMEOUT_SECONDS,
                base_url=settings.OPENAI_BASE_URL,
            )
        return MockCopilotProvider(
            model_name="mock-openai-fallback",
            timeout_seconds=settings.COPILOT_TIMEOUT_SECONDS,
        )

    raise CopilotProviderError(f"Unsupported copilot provider: '{target}'. Supported: gemini, openai, mock.")
