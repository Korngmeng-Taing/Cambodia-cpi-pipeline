"""
pipeline/retry.py
─────────────────
Transaction retry utilities with exponential backoff and randomized jitter
for high-concurrency PostgreSQL operations in the Cambodia CPI Pipeline.

Protects against:
  - Lock deadlocks (SQLSTATE 40P01 / psycopg2.errors.DeadlockDetected)
  - Serialization failures (SQLSTATE 40001 / psycopg2.errors.SerializationFailure)
  - Lock timeouts (SQLSTATE 55P03, 57014)
  - Transient network connection drops (psycopg2.OperationalError)
"""

from __future__ import annotations

import functools
import logging
import random
import time
from typing import Any, Callable, Sequence, TypeVar

import psycopg2
import psycopg2.errors

log = logging.getLogger("pipeline.retry")

# Default transient PostgreSQL error classes to retry
TRANSIENT_POSTGRES_EXCEPTIONS: tuple[type[Exception], ...] = (
    psycopg2.errors.DeadlockDetected,      # SQLSTATE 40P01
    psycopg2.errors.SerializationFailure,  # SQLSTATE 40001
    psycopg2.errors.LockNotAvailable,      # SQLSTATE 55P03
    psycopg2.OperationalError,             # Transient connection drop / server reload
)

T = TypeVar("T")


def calculate_backoff_delay(
    attempt: int,
    initial_delay: float = 0.1,
    max_delay: float = 3.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
) -> float:
    """
    Computes exponential backoff with full jitter (AWS Full Jitter pattern):
        sleep = random.uniform(0, min(max_delay, initial_delay * (backoff_factor ** attempt)))
    """
    max_backoff = min(max_delay, initial_delay * (backoff_factor ** attempt))
    if jitter:
        return random.uniform(0.0, max_backoff)
    return max_backoff


def retry_db_transaction(
    max_retries: int = 4,
    initial_delay: float = 0.1,
    max_delay: float = 3.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retry_exceptions: Sequence[type[Exception]] = TRANSIENT_POSTGRES_EXCEPTIONS,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that retries database operations when encountering transient
    concurrency conflicts (e.g. deadlocks, serialization failures, lock timeouts).

    Usage:
        @retry_db_transaction(max_retries=3)
        def write_records(conn, records):
            with conn.cursor() as cur:
                cur.execute(...)
            conn.commit()
    """
    tuple_exceptions = tuple(retry_exceptions)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        func_name = getattr(func, "__qualname__", getattr(func, "__name__", str(func)))

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except tuple_exceptions as exc:
                    attempt += 1
                    if attempt > max_retries:
                        log.error(
                            "Database operation '%s' failed after %d retries. Fatal exception: %s",
                            func_name,
                            max_retries,
                            exc,
                            exc_info=True,
                        )
                        raise

                    delay = calculate_backoff_delay(
                        attempt=attempt - 1,
                        initial_delay=initial_delay,
                        max_delay=max_delay,
                        backoff_factor=backoff_factor,
                        jitter=jitter,
                    )
                    log.warning(
                        "Transient DB conflict [%s] in '%s' (attempt %d/%d). Retrying in %.3fs... Detail: %s",
                        type(exc).__name__,
                        func_name,
                        attempt,
                        max_retries,
                        delay,
                        exc,
                    )
                    # If any connection argument was passed, roll it back to reset transaction state
                    for arg in list(args) + list(kwargs.values()):
                        if hasattr(arg, "rollback") and callable(arg.rollback):
                            try:
                                arg.rollback()
                            except Exception:
                                pass
                    time.sleep(delay)

        return wrapper

    return decorator
