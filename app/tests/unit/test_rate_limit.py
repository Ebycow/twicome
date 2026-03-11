from services.rate_limit import InMemoryRateLimiter


def test_rate_limiter_blocks_after_limit_within_window():
    limiter = InMemoryRateLimiter(limit=2, window_seconds=60)

    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is True
    assert limiter.allow("ip") is False


def test_rate_limiter_is_per_key():
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60)

    assert limiter.allow("ip1") is True
    assert limiter.allow("ip2") is True
