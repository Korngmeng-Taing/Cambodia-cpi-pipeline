"""
pipeline/key_pool.py
────────────────────
Multi-Key Load Balancing Pool for Google Gemini API.
Rotates through multiple API keys from GEMINI_API_KEYS (or GEMINI_API_KEY) in .env,
providing 3x daily quota, 3x RPM throughput, and automatic 429 failover.
"""

from __future__ import annotations

import itertools
import logging
import os
import threading
import time
from typing import Callable, TypeVar, Any

log = logging.getLogger(__name__)

T = TypeVar("T")


class GeminiKeyPool:
    """Manages a pool of Gemini API keys with thread-safe round-robin rotation and failover."""

    def __init__(self, keys: list[str] | None = None) -> None:
        self._lock = threading.Lock()
        if keys:
            self.keys = [k.strip() for k in keys if k.strip()]
        else:
            raw_keys = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
            self.keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

        if not self.keys:
            log.warning("GeminiKeyPool initialized with 0 API keys. AI calls will be skipped or mocked.")
            self._key_cycle = itertools.cycle([])
        else:
            log.info("GeminiKeyPool initialized with %d active API keys.", len(self.keys))
            self._key_cycle = itertools.cycle(self.keys)

        self._cooldowns: dict[str, float] = {}
        self.cooldown_seconds: float = float(os.getenv("GEMINI_429_BACKOFF_SECONDS", "30.0"))

    def get_key_count(self) -> int:
        """Returns total configured API keys."""
        return len(self.keys)

    def get_next_key(self) -> str | None:
        """Returns the next healthy API key in round-robin fashion, skipping cooling keys."""
        with self._lock:
            if not self.keys:
                return None

            now = time.time()
            self._cooldowns = {k: exp for k, exp in self._cooldowns.items() if exp > now}

            for _ in range(len(self.keys)):
                key = next(self._key_cycle)
                if key not in self._cooldowns:
                    return key

            if self._cooldowns:
                earliest_key = min(self._cooldowns.keys(), key=lambda k: self._cooldowns[k])
                wait_time = max(0.0, self._cooldowns[earliest_key] - now)
                log.warning("All %d Gemini API keys in cooldown. Waiting %.1fs for key...", len(self.keys), wait_time)
                if wait_time > 0:
                    time.sleep(min(wait_time, 5.0))
                return earliest_key

            return self.keys[0]

    def mark_key_rate_limited(self, key: str) -> None:
        """Places a key into temporary cooldown following a 429 ResourceExhausted response."""
        with self._lock:
            self._cooldowns[key] = time.time() + self.cooldown_seconds
            masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
            log.warning("API key %s placed into %.0fs cooldown. Active keys remaining: %d",
                        masked, self.cooldown_seconds, len(self.keys) - len(self._cooldowns))

    def execute_with_retry(self, fn: Callable[[str], T], max_attempts: int = 3) -> T:
        """Executes a function requiring an API key with automatic key rotation and failover on 429."""
        last_error = None
        for attempt in range(max_attempts):
            key = self.get_next_key()
            if not key:
                raise ValueError("No Gemini API keys configured.")

            try:
                return fn(key)
            except Exception as exc:
                err_str = str(exc).lower()
                if "429" in err_str or "resourceexhausted" in err_str or "quota" in err_str:
                    log.warning("429 Rate Limit encountered on attempt %d/%d: %s", attempt + 1, max_attempts, exc)
                    self.mark_key_rate_limited(key)
                    last_error = exc
                    continue
                raise exc

        raise RuntimeError(f"All Gemini API keys in pool exhausted after {max_attempts} attempts. Last error: {last_error}")


_global_key_pool: GeminiKeyPool | None = None


def get_key_pool() -> GeminiKeyPool:
    """Returns or creates the global GeminiKeyPool singleton."""
    global _global_key_pool
    if _global_key_pool is None:
        _global_key_pool = GeminiKeyPool()
    return _global_key_pool
