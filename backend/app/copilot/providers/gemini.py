"""
Gemini LLM Provider implementation using Google's Generative Language REST API.
Operates via async httpx without third-party heavy dependencies.
Enforces strict structured JSON output and timeout protections.
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
from app.copilot.schemas import CopilotAnalysisPayload

logger = logging.getLogger("releaseguard.copilot.gemini")


class GeminiCopilotProvider(BaseCopilotProvider):
    """
    Production-ready Gemini API provider.
    Uses Google's generateContent REST endpoint with structured JSON mode.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.5-flash",
        timeout_seconds: float = 30.0,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        super().__init__(model_name=model_name, timeout_seconds=timeout_seconds)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def analyze(self, system_prompt: str, user_prompt: str) -> CopilotAnalysisPayload:
        if not self.api_key:
            raise CopilotProviderError("GEMINI_API_KEY is not configured on the server")

        endpoint = f"{self.base_url}/models/{self.model_name}:generateContent"

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    endpoint,
                    params={"key": self.api_key},
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code != 200:
                    # Sanitize error detail to prevent key leakage
                    err_msg = f"Gemini API returned HTTP {response.status_code}: {response.text[:200]}"
                    logger.error(err_msg.replace(self.api_key, "[REDACTED]"))
                    raise CopilotProviderError(f"Gemini API returned HTTP {response.status_code}")

                data = response.json()

        except httpx.TimeoutException as exc:
            raise CopilotTimeoutError(f"Gemini API timed out after {self.timeout_seconds} seconds") from exc
        except httpx.RequestError as exc:
            raise CopilotProviderError(f"Network error communicating with Gemini API: {type(exc).__name__}") from exc
        except json.JSONDecodeError as exc:
            raise CopilotResponseParseError("Gemini API returned unparseable response") from exc

        # Extract generated content
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                raise CopilotResponseParseError("Gemini API returned no completion candidates")

            content_parts = candidates[0].get("content", {}).get("parts", [])
            if not content_parts or "text" not in content_parts[0]:
                raise CopilotResponseParseError("Gemini candidate did not contain text content")

            raw_text = content_parts[0]["text"].strip()

            # Handle possible markdown fencing from LLMs
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            return CopilotAnalysisPayload.model_validate_json(raw_text)

        except (ValidationError, KeyError, IndexError) as exc:
            logger.error("Failed to parse Gemini structured response: %s", exc)
            raise CopilotResponseParseError(f"Model response did not adhere to required analysis schema: {exc}") from exc
