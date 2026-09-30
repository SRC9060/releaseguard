"""
OpenAI-compatible LLM Provider implementation.
Operates via async httpx against any standard /v1/chat/completions endpoint.
"""

import json
import logging
from typing import Optional
import httpx
from pydantic import ValidationError

from app.copilot.providers.base import (
    BaseCopilotProvider,
    CopilotProviderError,
    CopilotResponseParseError,
    CopilotTimeoutError,
)
from app.copilot.schemas import CopilotAnalysisPayload, CopilotChatPayload

logger = logging.getLogger("releaseguard.copilot.openai")


class OpenAICopilotProvider(BaseCopilotProvider):
    """
    OpenAI-compatible provider.
    Supports official OpenAI API or any proxy/compatible endpoint (e.g. vLLM, Ollama, Azure).
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-4o-mini",
        timeout_seconds: float = 30.0,
        base_url: Optional[str] = None,
    ) -> None:
        super().__init__(model_name=model_name, timeout_seconds=timeout_seconds)
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    @property
    def provider_name(self) -> str:
        return "openai"

    async def analyze(self, system_prompt: str, user_prompt: str) -> CopilotAnalysisPayload:
        if not self.api_key:
            raise CopilotProviderError("OPENAI_API_KEY is not configured on the server")

        endpoint = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code != 200:
                    err_msg = f"OpenAI API returned HTTP {response.status_code}: {response.text[:200]}"
                    logger.error(err_msg.replace(self.api_key, "[REDACTED]"))
                    raise CopilotProviderError(f"OpenAI API returned HTTP {response.status_code}")

                data = response.json()

        except httpx.TimeoutException as exc:
            raise CopilotTimeoutError(f"OpenAI API timed out after {self.timeout_seconds} seconds") from exc
        except httpx.RequestError as exc:
            raise CopilotProviderError(f"Network error communicating with OpenAI API: {type(exc).__name__}") from exc
        except json.JSONDecodeError as exc:
            raise CopilotResponseParseError("OpenAI API returned unparseable JSON response") from exc

        try:
            choices = data.get("choices", [])
            if not choices:
                raise CopilotResponseParseError("OpenAI API returned no completion choices")

            raw_text = choices[0].get("message", {}).get("content", "").strip()
            return CopilotAnalysisPayload.model_validate_json(raw_text)

        except (ValidationError, KeyError, IndexError) as exc:
            logger.error("Failed to parse OpenAI structured response: %s", exc)
            raise CopilotResponseParseError(f"Model response did not adhere to required analysis schema: {exc}") from exc

    async def chat(self, system_prompt: str, user_prompt: str) -> CopilotChatPayload:
        if not self.api_key:
            raise CopilotProviderError("OPENAI_API_KEY is not configured on the server")

        endpoint = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code != 200:
                    err_msg = f"OpenAI API returned HTTP {response.status_code}: {response.text[:200]}"
                    logger.error(err_msg.replace(self.api_key, "[REDACTED]"))
                    raise CopilotProviderError(f"OpenAI API returned HTTP {response.status_code}")

                data = response.json()

        except httpx.TimeoutException as exc:
            raise CopilotTimeoutError(f"OpenAI API timed out after {self.timeout_seconds} seconds") from exc
        except httpx.RequestError as exc:
            raise CopilotProviderError(f"Network error communicating with OpenAI API: {type(exc).__name__}") from exc
        except json.JSONDecodeError as exc:
            raise CopilotResponseParseError("OpenAI API returned unparseable JSON response") from exc

        try:
            choices = data.get("choices", [])
            if not choices:
                raise CopilotResponseParseError("OpenAI API returned no completion choices")

            raw_text = choices[0].get("message", {}).get("content", "").strip()
            return CopilotChatPayload.model_validate_json(raw_text)

        except (ValidationError, KeyError, IndexError) as exc:
            logger.error("Failed to parse OpenAI structured chat response: %s", exc)
            raise CopilotResponseParseError(f"Model response did not adhere to required chat schema: {exc}") from exc
