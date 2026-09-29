"""
Gemini LLM Provider implementation using Google's Generative Language REST API.
Operates via async httpx without third-party heavy dependencies.
Enforces strict structured JSON output, transient failure retries with exponential backoff & jitter,
bounded execution time, optional fallback model support, and secure header-based authentication.
"""

import asyncio
import json
import logging
import random
import time
from typing import Optional, Set
import httpx
from pydantic import ValidationError

from app.copilot.providers.base import (
    BaseCopilotProvider,
    CopilotProviderError,
    CopilotResponseParseError,
    CopilotTimeoutError,
)
from app.copilot.schemas import CopilotAnalysisPayload
from app.logging import redact_sensitive

logger = logging.getLogger("releaseguard.copilot.gemini")


class GeminiCopilotProvider(BaseCopilotProvider):
    """
    Production-ready resilient Gemini API provider.
    Uses Google's generateContent REST endpoint with structured JSON mode.
    Retries transient failures (503, 429, 408, network timeouts) with exponential backoff and jitter.
    Optionally falls back to a secondary model if the primary exhausts retries on transient errors.
    """

    TRANSIENT_STATUS_CODES: Set[int] = {408, 429, 500, 502, 503, 504}
    FALLBACK_STATUS_CODES: Set[int] = {429, 503}

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.8-flash",
        fallback_model: Optional[str] = "gemini-3.7-flash",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 1.0,
        retry_max_delay_seconds: float = 8.0,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        super().__init__(model_name=model_name, timeout_seconds=timeout_seconds)
        self.api_key = api_key
        self.primary_model_name = model_name
        self.fallback_model = self._clean_model_name(fallback_model)
        if self.fallback_model == self.primary_model_name:
            self.fallback_model = None

        self.max_retries = max(0, max_retries)
        self.retry_base_delay_seconds = max(0.0, retry_base_delay_seconds)
        self.retry_max_delay_seconds = max(0.0, retry_max_delay_seconds)
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _clean_model_name(val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        cleaned = val.strip()
        if cleaned.lower() in ("", "none", "disabled", "false", "null"):
            return None
        return cleaned

    @property
    def provider_name(self) -> str:
        return "gemini"

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calculates exponential backoff delay with small random jitter.
        attempt 1 -> base * 2^0 = base (~1s)
        attempt 2 -> base * 2^1 = base * 2 (~2s)
        attempt 3 -> base * 2^2 = base * 4 (~4s)
        """
        delay = self.retry_base_delay_seconds * (2 ** (attempt - 1))
        delay = min(delay, self.retry_max_delay_seconds)
        jitter = random.uniform(0.0, min(0.25, 0.15 * delay) if delay > 0 else 0.0)
        return delay + jitter

    def _parse_candidate_response(self, data: dict) -> CopilotAnalysisPayload:
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

    async def _execute_model(
        self,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        deadline: float,
    ) -> tuple[Optional[CopilotAnalysisPayload], Optional[int], Optional[Exception]]:
        """
        Executes requests for a specific model with exponential backoff and jitter.
        Returns:
            (payload, last_status_code, last_exception)
        """
        endpoint = f"{self.base_url}/models/{model_name}:generateContent"
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
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        last_status: Optional[int] = None
        last_exc: Optional[Exception] = None
        max_attempts = 1 + self.max_retries

        for attempt_idx in range(max_attempts):
            retry_attempt = attempt_idx + 1
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0:
                raise CopilotTimeoutError(f"Gemini API timed out after {self.timeout_seconds} seconds")

            request_timeout = min(self.timeout_seconds, remaining)

            try:
                async with httpx.AsyncClient(timeout=request_timeout) as client:
                    response = await client.post(
                        endpoint,
                        json=payload,
                        headers=headers,
                    )

                if response.status_code == 200:
                    try:
                        data = response.json()
                        result = self._parse_candidate_response(data)
                        return result, None, None
                    except (ValidationError, KeyError, IndexError, json.JSONDecodeError) as exc:
                        logger.error("Failed to parse Gemini structured response: %s", exc)
                        raise CopilotResponseParseError(
                            f"Model response did not adhere to required analysis schema: {exc}"
                        ) from exc

                last_status = response.status_code

                # Non-transient errors: Do NOT retry (400, 401, 403, 404, etc.)
                if response.status_code not in self.TRANSIENT_STATUS_CODES:
                    clean_text = redact_sensitive(response.text[:200]).replace(self.api_key, "[REDACTED]")
                    logger.error(
                        "Gemini API returned HTTP %d for model %s: %s",
                        response.status_code,
                        model_name,
                        clean_text,
                    )
                    raise CopilotProviderError(f"Gemini API returned HTTP {response.status_code}")

                # Transient error: retry if attempts remain
                if attempt_idx < self.max_retries:
                    logger.warning(
                        "Gemini transient failure: status=%d model=%s attempt=%d/%d",
                        response.status_code,
                        model_name,
                        retry_attempt,
                        self.max_retries,
                    )
                    logger.info("Retrying after backoff...")
                    delay = self._calculate_backoff_delay(retry_attempt)
                    remaining_after = deadline - time.monotonic()
                    if remaining_after <= delay:
                        raise CopilotTimeoutError(f"Gemini API timed out after {self.timeout_seconds} seconds")
                    await asyncio.sleep(delay)
                    continue
                else:
                    last_exc = CopilotProviderError(f"Gemini API returned HTTP {response.status_code}")
                    break

            except (CopilotProviderError, CopilotResponseParseError, CopilotTimeoutError):
                raise
            except httpx.TimeoutException as exc:
                last_exc = CopilotTimeoutError(f"Gemini API timed out after {self.timeout_seconds} seconds")
                if attempt_idx < self.max_retries:
                    logger.warning(
                        "Gemini transient failure: status=timeout model=%s attempt=%d/%d",
                        model_name,
                        retry_attempt,
                        self.max_retries,
                    )
                    logger.info("Retrying after backoff...")
                    delay = self._calculate_backoff_delay(retry_attempt)
                    remaining_after = deadline - time.monotonic()
                    if remaining_after <= delay:
                        raise CopilotTimeoutError(f"Gemini API timed out after {self.timeout_seconds} seconds") from exc
                    await asyncio.sleep(delay)
                    continue
                else:
                    break
            except httpx.RequestError as exc:
                last_exc = CopilotProviderError(f"Network error communicating with Gemini API: {type(exc).__name__}")
                if attempt_idx < self.max_retries:
                    logger.warning(
                        "Gemini transient failure: error=%s model=%s attempt=%d/%d",
                        type(exc).__name__,
                        model_name,
                        retry_attempt,
                        self.max_retries,
                    )
                    logger.info("Retrying after backoff...")
                    delay = self._calculate_backoff_delay(retry_attempt)
                    remaining_after = deadline - time.monotonic()
                    if remaining_after <= delay:
                        raise CopilotTimeoutError(f"Gemini API timed out after {self.timeout_seconds} seconds") from exc
                    await asyncio.sleep(delay)
                    continue
                else:
                    break

        return None, last_status, last_exc

    async def analyze(self, system_prompt: str, user_prompt: str) -> CopilotAnalysisPayload:
        if not self.api_key:
            raise CopilotProviderError("GEMINI_API_KEY is not configured on the server")

        self.model_name = self.primary_model_name
        deadline = time.monotonic() + self.timeout_seconds

        # 1. Attempt primary model
        payload, last_status, last_exc = await self._execute_model(
            model_name=self.primary_model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            deadline=deadline,
        )

        if payload is not None:
            self.model_name = self.primary_model_name
            return payload

        # 2. Check if eligible for fallback model
        if (
            self.fallback_model
            and self.fallback_model != self.primary_model_name
            and last_status in self.FALLBACK_STATUS_CODES
            and (deadline - time.monotonic()) > 0
        ):
            logger.warning(
                "Primary model exhausted retries; trying fallback model=%s",
                self.fallback_model,
            )
            fallback_payload, fb_status, fb_exc = await self._execute_model(
                model_name=self.fallback_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                deadline=deadline,
            )
            if fallback_payload is not None:
                self.model_name = self.fallback_model
                return fallback_payload

            if fb_exc:
                raise fb_exc
            raise CopilotProviderError(f"Gemini API returned HTTP {fb_status or last_status or 503}")

        # No fallback or not eligible for fallback
        if last_exc:
            raise last_exc
        raise CopilotProviderError(f"Gemini API returned HTTP {last_status or 503}")
