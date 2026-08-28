"""
scrapers/_http.py
─────────────────
Shared HTTP client for all scrapers.

Provides:
  • RateLimiter     – thread-safe per-host min-interval throttle
  • http_get        – GET via curl_cffi (Chrome impersonation) w/ retry + throttle
  • http_post       – POST analogue
  • with_retries    – generic exponential-backoff wrapper
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import requests

try:
    from curl_cffi import requests as cffi_requests

    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
DEFAULT_ATTEMPTS = 5
DEFAULT_BACKOFF_BASE = 1.5
DEFAULT_MAX_CONSECUTIVE_ERRORS = 3


class RateLimiter:
    """Thread-safe per-host minimum-interval throttle."""

    def __init__(self, default_min_interval: float = 0.0):
        self._default_min_interval = default_min_interval
        self._lock = threading.Lock()
        self._last_call: dict[str, float] = {}

    def wait(self, host: str, min_interval: float | None = None) -> None:
        interval = self._default_min_interval if min_interval is None else min_interval
        if interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            last = self._last_call.get(host, 0.0)
            delay = interval - (now - last)
            if delay > 0:
                time.sleep(delay)
            self._last_call[host] = time.monotonic()

    @staticmethod
    def host_of(url: str) -> str:
        try:
            from urllib.parse import urlparse

            return urlparse(url).netloc or url
        except Exception:
            return url


_limiter = RateLimiter(default_min_interval=float(__import__("os").environ.get("SCRAPER_THROTTLE_DELAY", "0.5")))


def with_retries(
    fn: Callable[..., Any],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    max_consecutive_errors: int = DEFAULT_MAX_CONSECUTIVE_ERRORS,
    on_error: Callable[[int, BaseException], None] | None = None,
) -> Any:
    """
    Call `fn()` with exponential backoff. Stops after `attempts` failures OR
    after `max_consecutive_errors` consecutive failures (used by paginated
    scrapers to break a dead loop).
    Returns the first successful value; raises the last exception if exhausted.
    """
    last_err: BaseException | None = None
    consecutive_errors = 0
    for attempt in range(attempts):
        try:
            result = fn()
            return result
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            consecutive_errors += 1
            if on_error is not None:
                on_error(attempt, exc)
            if consecutive_errors >= max_consecutive_errors:
                log.warning(
                    "with_retries: %d consecutive errors reached limit; aborting early.",
                    consecutive_errors,
                )
                break
            if attempt < attempts - 1:
                import random

                delay = (backoff_base ** (attempt + 1)) + random.uniform(0.1, 0.7)
                time.sleep(delay)  # Exponential with jitter
    assert last_err is not None
    raise last_err


def http_get(url: str, *, throttle_host: bool = True, **kwargs: Any) -> requests.Response:
    """GET via curl_cffi with Chrome TLS impersonation; falls back to requests."""
    if throttle_host:
        _limiter.wait(RateLimiter.host_of(url))
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    if HAS_CURL_CFFI:
        return cffi_requests.get(url, impersonate="chrome", timeout=timeout, **kwargs)
    return requests.get(url, timeout=timeout, **kwargs)


def http_post(url: str, *, throttle_host: bool = True, **kwargs: Any) -> requests.Response:
    if throttle_host:
        _limiter.wait(RateLimiter.host_of(url))
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    if HAS_CURL_CFFI:
        return cffi_requests.post(url, impersonate="chrome", timeout=timeout, **kwargs)
    return requests.post(url, timeout=timeout, **kwargs)
