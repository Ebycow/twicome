import services.rate_limit as rate_limit_module
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


def test_rate_limiter_evicts_stale_keys(monkeypatch):
    """アクセスが途絶えたキーがウィンドウ経過後の掃除で削除される。"""
    fake_now = [1000.0]
    monkeypatch.setattr(rate_limit_module, "monotonic", lambda: fake_now[0])

    limiter = InMemoryRateLimiter(limit=5, window_seconds=60)

    # 大量のユニークキーでアクセス（=詐称 IP のばらまきを模す）
    for i in range(100):
        assert limiter.allow(f"ip-{i}") is True
    assert len(limiter._events) == 100

    # ウィンドウ経過後に別キーでアクセスすると、古いキーが一括で掃除される
    fake_now[0] += 61
    assert limiter.allow("fresh") is True
    assert len(limiter._events) == 1
    assert "fresh" in limiter._events


def test_rate_limiter_keeps_active_keys_during_sweep(monkeypatch):
    """掃除が走っても、まだウィンドウ内のイベントを持つキーは削除されない。"""
    fake_now = [1000.0]
    monkeypatch.setattr(rate_limit_module, "monotonic", lambda: fake_now[0])

    limiter = InMemoryRateLimiter(limit=2, window_seconds=60)

    assert limiter.allow("active") is True

    # ウィンドウ経過直前に "active" を再アクセスし、新しいイベントを積む
    fake_now[0] += 30
    assert limiter.allow("active") is True

    # 最初の sweep から window 経過したタイミングで掃除が発火する
    fake_now[0] += 31  # 合計 61 秒経過
    # "active" の最新イベントは 31 秒前でまだウィンドウ内なので削除されない
    assert limiter.allow("other") is True
    assert "active" in limiter._events
