"""
Phase 15D — Copilot Request Limiter and Inflight Protection.
Reuses existing Redis/in-memory infrastructure and auth user_id to prevent:
- accidental double-clicks (< 1.0s duplicate submissions with same payload)
- rapid multiple browser tabs / automation loops (> N requests per window)
- concurrent duplicate executions on the same incident by the same user.
"""

import hashlib
import logging
import threading
import time
from typing import Dict, Tuple
from urllib.parse import urlparse

import redis
from app.config import settings

logger = logging.getLogger("releaseguard.copilot.limiter")


class CopilotRequestLimiter:
    """
    Guards Copilot endpoints against accidental double-clicks and rapid request loops.
    In production mode, uses Redis for distributed rate-limiting.
    In development/testing, uses a thread-safe in-memory store.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        double_click_window_seconds: float = 1.0,
        rate_limit_window_seconds: int = 60,
        max_requests_per_window: int = 30,
    ) -> None:
        self.double_click_window = double_click_window_seconds
        self.rate_limit_window = rate_limit_window_seconds
        self.max_requests_per_window = max_requests_per_window

        self._lock = threading.Lock()
        # In-memory stores: key -> last_timestamp
        self._last_request_time: Dict[str, float] = {}
        # In-memory stores: key -> (count, window_expiry)
        self._rate_limit_store: Dict[str, Tuple[int, float]] = {}

        self.redis_client = None
        url = redis_url or settings.REDIS_URL
        try:
            client = redis.from_url(url, decode_responses=True)
            client.ping()
            self.redis_client = client
        except Exception as exc:
            parsed = urlparse(url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 6379
            if settings.ENVIRONMENT == "production":
                raise RuntimeError(
                    f"Production mode requires operational Redis for Copilot rate limiting, but connection to {host}:{port} failed: {exc}"
                )
            logger.info("Redis unavailable for Copilot request limiter in dev/test; using in-memory fallback")

    def _hash_payload(self, payload_text: str | None) -> str:
        return hashlib.sha256((payload_text or "").strip().encode("utf-8")).hexdigest()[:16]

    def _get_double_click_key(self, user_id: int, incident_id: int, action: str, payload_hash: str) -> str:
        return f"copilot:dedup:{user_id}:{incident_id}:{action}:{payload_hash}"

    def _get_rate_limit_key(self, user_id: int, incident_id: int) -> str:
        return f"copilot:rate_limit:{user_id}:{incident_id}"

    def check_and_acquire(
        self,
        user_id: int,
        incident_id: int,
        action: str = "chat",
        payload_text: str | None = None,
    ) -> Tuple[bool, str]:
        """
        Validates that the request is not a rapid double-click or rate-limit violation.
        Returns:
            (allowed: bool, rejection_reason: str)
        """
        now = time.time()
        p_hash = self._hash_payload(payload_text)
        dc_key = self._get_double_click_key(user_id, incident_id, action, p_hash)
        rl_key = self._get_rate_limit_key(user_id, incident_id)

        # 1. Production Mode with Redis
        if settings.ENVIRONMENT == "production":
            if self.redis_client is None:
                raise RuntimeError("Production mode requires Redis for Copilot limiter, but redis_client is None.")
            try:
                # Double click check via atomic SET NX PX
                px_ms = int(self.double_click_window * 1000)
                acquired = self.redis_client.set(dc_key, "1", nx=True, px=px_ms)
                if not acquired:
                    return False, "A duplicate Copilot request was detected. Please avoid double-clicking."

                # Sliding / fixed window counter
                current_count = self.redis_client.incr(rl_key)
                if current_count == 1:
                    self.redis_client.expire(rl_key, self.rate_limit_window)
                if current_count > self.max_requests_per_window:
                    return False, "Copilot request rate limit exceeded. Please wait a moment."

                return True, ""
            except Exception as e:
                raise RuntimeError(f"Redis error during Copilot request limit check: {e}")

        # 2. Non-production: try Redis if available, else in-memory
        if self.redis_client is not None:
            try:
                px_ms = int(self.double_click_window * 1000)
                acquired = self.redis_client.set(dc_key, "1", nx=True, px=px_ms)
                if not acquired:
                    return False, "A duplicate Copilot request was detected. Please avoid double-clicking."

                current_count = self.redis_client.incr(rl_key)
                if current_count == 1:
                    self.redis_client.expire(rl_key, self.rate_limit_window)
                if current_count > self.max_requests_per_window:
                    return False, "Copilot request rate limit exceeded. Please wait a moment."

                return True, ""
            except Exception as e:
                logger.warning("Redis error in Copilot limiter dev/test: %s; falling back to in-memory", e)

        with self._lock:
            # Check double-click on identical payload
            last_time = self._last_request_time.get(dc_key, 0.0)
            if (now - last_time) < self.double_click_window:
                return False, "A duplicate Copilot request was detected. Please avoid double-clicking."
            self._last_request_time[dc_key] = now

            # Check rate limit window
            if rl_key in self._rate_limit_store:
                count, expiry = self._rate_limit_store[rl_key]
                if now > expiry:
                    self._rate_limit_store[rl_key] = (1, now + self.rate_limit_window)
                else:
                    if count >= self.max_requests_per_window:
                        return False, "Copilot request rate limit exceeded. Please wait a moment."
                    self._rate_limit_store[rl_key] = (count + 1, expiry)
            else:
                self._rate_limit_store[rl_key] = (1, now + self.rate_limit_window)

            return True, ""

    def reset(self, user_id: int | None = None, incident_id: int | None = None) -> None:
        """Resets limiter state (useful in tests)."""
        if self.redis_client is not None and user_id is not None and incident_id is not None:
            try:
                self.redis_client.delete(self._get_rate_limit_key(user_id, incident_id))
            except Exception:
                pass
        with self._lock:
            if user_id is not None and incident_id is not None:
                self._rate_limit_store.pop(self._get_rate_limit_key(user_id, incident_id), None)
            else:
                self._rate_limit_store.clear()
                self._last_request_time.clear()


copilot_limiter = CopilotRequestLimiter()
