from datetime import datetime, timezone
import logging
import threading
import time
from typing import Dict, Tuple
from urllib.parse import urlparse

import redis
from app.config import settings

logger = logging.getLogger("releaseguard.auth_limiter")


class AuthRateLimiter:
    """
    Tracks failed login attempts and applies temporary lockouts.
    Production mode REQUIRES Redis for distributed authentication lockout and fails explicitly if unavailable.
    In-memory fallback is strictly restricted to development/test modes.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self.max_attempts = settings.AUTH_MAX_ATTEMPTS
        self.lockout_seconds = settings.AUTH_LOCKOUT_SECONDS
        self._memory_store: Dict[str, Tuple[int, float]] = {}
        self._lock = threading.Lock()
        
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
                    f"Production mode requires an operational Redis instance for distributed authentication rate limiting, but connection to {host}:{port} failed: {exc}"
                )
            logger.warning("Redis unavailable for auth rate limiter in non-production environment; using in-memory fallback")

    def _get_key(self, identifier: str) -> str:
        return f"auth:failed:{identifier.strip().lower()}"

    def is_locked(self, identifier: str) -> bool:
        """Checks if the given identifier (email or IP) is locked out."""
        key = self._get_key(identifier)
        if settings.ENVIRONMENT == "production":
            if self.redis_client is None:
                raise RuntimeError("Production mode requires Redis for auth lockout checks, but redis_client is None.")
            try:
                attempts = self.redis_client.get(key)
                if attempts and int(attempts) >= self.max_attempts:
                    return True
                return False
            except Exception as e:
                raise RuntimeError(f"Redis error during production auth lockout check: {e}")

        # Non-production: try Redis first, fall back to in-memory store
        if self.redis_client is not None:
            try:
                attempts = self.redis_client.get(key)
                if attempts and int(attempts) >= self.max_attempts:
                    return True
                return False
            except Exception as e:
                logger.warning("Redis error checking auth lockout in dev/test: %s", e)

        with self._lock:
            if key in self._memory_store:
                attempts, expiry = self._memory_store[key]
                if time.time() > expiry:
                    del self._memory_store[key]
                    return False
                return attempts >= self.max_attempts
            return False

    def record_failure(self, identifier: str) -> int:
        """Increments failed attempt count and returns current count."""
        key = self._get_key(identifier)
        if settings.ENVIRONMENT == "production":
            if self.redis_client is None:
                raise RuntimeError("Production mode requires Redis to record auth failures, but redis_client is None.")
            try:
                pipe = self.redis_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, self.lockout_seconds)
                results = pipe.execute()
                return int(results[0])
            except Exception as e:
                raise RuntimeError(f"Redis error recording production auth failure: {e}")

        # Non-production: try Redis first, fall back to in-memory store
        if self.redis_client is not None:
            try:
                pipe = self.redis_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, self.lockout_seconds)
                results = pipe.execute()
                return int(results[0])
            except Exception as e:
                logger.warning("Redis error recording auth failure in dev/test: %s", e)

        with self._lock:
            now = time.time()
            if key in self._memory_store:
                attempts, expiry = self._memory_store[key]
                if now > expiry:
                    attempts = 1
                else:
                    attempts += 1
            else:
                attempts = 1
            self._memory_store[key] = (attempts, now + self.lockout_seconds)
            return attempts

    def reset(self, identifier: str) -> None:
        """Clears failed attempts upon successful authentication."""
        key = self._get_key(identifier)
        if settings.ENVIRONMENT == "production":
            if self.redis_client is None:
                raise RuntimeError("Production mode requires Redis to reset auth failures, but redis_client is None.")
            try:
                self.redis_client.delete(key)
                return
            except Exception as e:
                raise RuntimeError(f"Redis error resetting production auth failure: {e}")

        # Non-production: try Redis first, also clear in-memory store
        if self.redis_client is not None:
            try:
                self.redis_client.delete(key)
            except Exception as e:
                logger.warning("Redis error resetting auth limiter in dev/test: %s", e)

        with self._lock:
            self._memory_store.pop(key, None)


auth_limiter = AuthRateLimiter()
