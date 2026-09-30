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
from typing import Any, Callable, Optional, Set
import httpx
from pydantic import ValidationError

from app.copilot.providers.base import (
    BaseCopilotProvider,
    CopilotProviderError,
    CopilotResponseParseError,
    CopilotTimeoutError,
)
from app.copilot.schemas import (
    COPILOT_RESPONSE_SCHEMA,
    COPILOT_CHAT_RESPONSE_SCHEMA,
    CopilotAnalysisPayload,
    CopilotChatPayload,
)
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
        fallback_model: Optional[str] = "gemini-3.5-flash-lite",
        timeout_seconds: float = 30.0,
        max_retries: int = 1,
        fallback_max_retries: int = 0,
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
        self.fallback_max_retries = max(0, fallback_max_retries)
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

    def _parse_candidate_response(
        self,
        data: dict,
        validator: Optional[Callable[[str], Any]] = None,
    ) -> Any:
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

        val_fn = validator or CopilotAnalysisPayload.model_validate_json
        return val_fn(raw_text)

    async def _execute_model(
        self,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        deadline: float,
        model_retries: Optional[int] = None,
        response_schema: Optional[dict] = None,
        response_validator: Optional[Callable[[str], Any]] = None,
    ) -> tuple[Optional[Any], Optional[int], Optional[Exception]]:
        """
        Executes requests for a specific model with exponential backoff and jitter.
        Returns:
            (payload, last_status_code, last_exception)
        """
        schema = response_schema or COPILOT_RESPONSE_SCHEMA
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
                "response_schema": schema,
                "temperature": 0.2,
            }
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

        last_status: Optional[int] = None
        last_exc: Optional[Exception] = None
        effective_retries = self.max_retries if model_retries is None else max(0, model_retries)
        max_attempts = 1 + effective_retries

        for attempt_idx in range(max_attempts):
            retry_attempt = attempt_idx + 1
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0.01:
                last_exc = CopilotTimeoutError(f"Gemini API timed out after {self.timeout_seconds} seconds")
                break

            request_timeout = max(0.01, min(self.timeout_seconds, remaining))

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
                        result = self._parse_candidate_response(data, validator=response_validator)
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

                # Transient error: log failure for this attempt
                logger.warning(
                    "Gemini transient failure: status=%d model=%s attempt=%d/%d",
                    response.status_code,
                    model_name,
                    retry_attempt,
                    max_attempts,
                )
                last_exc = CopilotProviderError(f"Gemini API returned HTTP {response.status_code}")

                # Retry if attempts remain
                if attempt_idx < effective_retries:
                    delay = self._calculate_backoff_delay(retry_attempt)
                    remaining_after = deadline - time.monotonic()
                    if remaining_after <= delay:
                        # Cannot sleep within deadline
                        break
                    logger.info("Retrying after backoff...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    break

            except (CopilotProviderError, CopilotResponseParseError):
                # Non-transient client errors and JSON schema parse errors fail immediately
                raise
            except httpx.TimeoutException as exc:
                logger.warning(
                    "Gemini transient failure: status=timeout model=%s attempt=%d/%d",
                    model_name,
                    retry_attempt,
                    max_attempts,
                )
                last_exc = CopilotTimeoutError(f"Gemini API timed out after {self.timeout_seconds} seconds")
                if attempt_idx < effective_retries:
                    delay = self._calculate_backoff_delay(retry_attempt)
                    remaining_after = deadline - time.monotonic()
                    if remaining_after <= delay:
                        break
                    logger.info("Retrying after backoff...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    break
            except httpx.RequestError as exc:
                logger.warning(
                    "Gemini transient failure: error=%s model=%s attempt=%d/%d",
                    type(exc).__name__,
                    model_name,
                    retry_attempt,
                    max_attempts,
                )
                last_exc = CopilotProviderError(f"Network error communicating with Gemini API: {type(exc).__name__}")
                if attempt_idx < effective_retries:
                    delay = self._calculate_backoff_delay(retry_attempt)
                    remaining_after = deadline - time.monotonic()
                    if remaining_after <= delay:
                        break
                    logger.info("Retrying after backoff...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    break

        return None, last_status, last_exc

    async def _execute_with_failover(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict,
        response_validator: Callable[[str], Any],
    ) -> Any:
        """
        Shared execution engine for analysis and chat with failover policy:
        1. Attempt primary model (up to 2 total attempts: initial + 1 retry).
        2. If transient failure (503, 429, timeout, network), failover to secondary model (exactly 1 attempt).
        3. Never retry/fallback for 400, 401, 403, 404, or schema parse errors.
        4. Reserves time for fallback to prevent primary retry from consuming overall deadline.
        5. Reports the actual successful model.
        """
        if not self.api_key:
            raise CopilotProviderError("GEMINI_API_KEY is not configured on the server")

        self.model_name = self.primary_model_name
        start_time = time.monotonic()
        deadline = start_time + self.timeout_seconds

        # Reserve time for fallback attempt if a fallback model is configured
        fallback_reserve = 0.0
        if self.fallback_model and self.fallback_model != self.primary_model_name:
            fallback_reserve = min(10.0, self.timeout_seconds * 0.35)
            if self.timeout_seconds > 2.0:
                fallback_reserve = max(2.0, fallback_reserve)
                fallback_reserve = min(fallback_reserve, self.timeout_seconds - 1.0)

        primary_deadline = deadline - fallback_reserve

        # 1. Attempt primary model (with self.max_retries, default 1)
        payload, last_status, last_exc = await self._execute_model(
            model_name=self.primary_model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            deadline=primary_deadline,
            model_retries=self.max_retries,
            response_schema=response_schema,
            response_validator=response_validator,
        )

        if payload is not None:
            self.model_name = self.primary_model_name
            return payload

        # 2. Check if eligible for fallback model
        is_transient_failure = (
            last_status in self.FALLBACK_STATUS_CODES
            or isinstance(last_exc, (CopilotTimeoutError, httpx.RequestError))
            or (
                isinstance(last_exc, CopilotProviderError)
                and (
                    last_status in self.TRANSIENT_STATUS_CODES
                    or "Network error" in str(last_exc)
                )
            )
        )

        remaining_time = deadline - time.monotonic()

        if (
            self.fallback_model
            and self.fallback_model != self.primary_model_name
            and is_transient_failure
        ):
            # Fail fast if there is not enough remaining time for a fallback request
            min_fallback_time = min(0.5, self.timeout_seconds * 0.1) if self.timeout_seconds > 0.5 else 0.05
            if remaining_time < min_fallback_time:
                raise CopilotTimeoutError(f"Gemini API timed out after {self.timeout_seconds} seconds")

            logger.warning(
                "Primary model exhausted retries; trying fallback model=%s",
                self.fallback_model,
            )
            fallback_payload, fb_status, fb_exc = await self._execute_model(
                model_name=self.fallback_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                deadline=deadline,
                model_retries=self.fallback_max_retries,
                response_schema=response_schema,
                response_validator=response_validator,
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

    async def analyze(self, system_prompt: str, user_prompt: str) -> CopilotAnalysisPayload:
        return await self._execute_with_failover(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=COPILOT_RESPONSE_SCHEMA,
            response_validator=CopilotAnalysisPayload.model_validate_json,
        )

    async def chat(self, system_prompt: str, user_prompt: str) -> CopilotChatPayload:
        return await self._execute_with_failover(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=COPILOT_CHAT_RESPONSE_SCHEMA,
            response_validator=CopilotChatPayload.model_validate_json,
        )
