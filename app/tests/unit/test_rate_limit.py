from starlette.datastructures import Headers

import services.rate_limit as rate_limit_module
from services.rate_limit import InMemoryRateLimiter, resolve_client_ip


def _headers(d):
    """大文字小文字を区別しない Starlette Headers を生成する（本番の request.headers と同等）。"""
    return Headers(d)


def test_resolve_client_ip_prefers_trusted_header():
    """信頼ヘッダ指定時はその値を採用する（接続元IPやXFFより優先）。"""
    headers = _headers({"CF-Connecting-IP": "203.0.113.7", "X-Forwarded-For": "10.0.0.9"})
    assert resolve_client_ip(headers, "172.19.0.1", "CF-Connecting-IP") == "203.0.113.7"


def test_resolve_client_ip_header_lookup_is_case_insensitive():
    headers = _headers({"cf-connecting-ip": "203.0.113.7"})
    assert resolve_client_ip(headers, "172.19.0.1", "CF-Connecting-IP") == "203.0.113.7"


def test_resolve_client_ip_ignores_spoofed_xff_leftmost():
    """攻撃者が詰めた X-Forwarded-For 先頭は無視され、信頼ヘッダが採用される。"""
    headers = _headers(
        {
            # 先頭が攻撃者の詐称値、末尾が信頼境界の追記値
            "X-Forwarded-For": "1.1.1.1, 172.26.0.3, 203.0.113.7",
            "CF-Connecting-IP": "203.0.113.7",
        }
    )
    assert resolve_client_ip(headers, "172.19.0.1", "CF-Connecting-IP") == "203.0.113.7"


def test_resolve_client_ip_xff_uses_rightmost_not_leftmost():
    """信頼ヘッダに XFF を指定した場合は末尾（信頼境界が追記した値）を使う。先頭詐称は効かない。"""
    headers = _headers({"X-Forwarded-For": "1.1.1.1, 172.26.0.3, 203.0.113.7"})
    assert resolve_client_ip(headers, "172.19.0.1", "X-Forwarded-For") == "203.0.113.7"


def test_resolve_client_ip_falls_back_to_host_when_header_absent():
    """信頼ヘッダが無い/空なら接続元IPに倒す（fail-closed）。"""
    headers = _headers({"X-Forwarded-For": "1.1.1.1"})
    # CF-Connecting-IP が無いので XFF 先頭(1.1.1.1)は採用せず接続元へ
    assert resolve_client_ip(headers, "172.19.0.1", "CF-Connecting-IP") == "172.19.0.1"


def test_resolve_client_ip_no_trusted_header_uses_host():
    """trusted_header 未設定（デフォルト）なら、いかなる転送ヘッダも信用せず接続元IPを使う。"""
    headers = _headers({"X-Forwarded-For": "1.1.1.1", "CF-Connecting-IP": "2.2.2.2"})
    assert resolve_client_ip(headers, "172.19.0.1", None) == "172.19.0.1"
    assert resolve_client_ip(headers, "172.19.0.1", "") == "172.19.0.1"


def test_resolve_client_ip_unknown_when_no_host_and_no_header():
    assert resolve_client_ip(_headers({}), None, "CF-Connecting-IP") == "unknown"


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
