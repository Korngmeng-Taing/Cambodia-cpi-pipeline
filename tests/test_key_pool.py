import time
import pytest
from pipeline.key_pool import GeminiKeyPool


def test_key_pool_round_robin():
    pool = GeminiKeyPool(keys=["key_a", "key_b", "key_c"])
    assert pool.get_key_count() == 3

    # Verify round-robin sequence
    assert pool.get_next_key() == "key_a"
    assert pool.get_next_key() == "key_b"
    assert pool.get_next_key() == "key_c"
    assert pool.get_next_key() == "key_a"


def test_key_pool_cooldown_and_failover():
    pool = GeminiKeyPool(keys=["key_1", "key_2", "key_3"])
    pool.cooldown_seconds = 2.0

    # Mark key_1 as rate limited (429)
    pool.mark_key_rate_limited("key_1")

    # Next key should automatically skip key_1 and give key_2
    next_key = pool.get_next_key()
    assert next_key in ("key_2", "key_3")


def test_key_pool_execute_with_retry_failover():
    pool = GeminiKeyPool(keys=["bad_key", "good_key"])
    pool.cooldown_seconds = 1.0

    call_count = 0

    def mock_api_call(key: str) -> str:
        nonlocal call_count
        call_count += 1
        if key == "bad_key":
            raise RuntimeError("429 ResourceExhausted: rate limit exceeded")
        return f"success_with_{key}"

    result = pool.execute_with_retry(mock_api_call, max_attempts=3)
    assert result == "success_with_good_key"
    assert call_count >= 2
