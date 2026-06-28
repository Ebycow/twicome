"""レートリミッター"""

from collections import defaultdict, deque
from threading import Lock
from time import monotonic


def resolve_client_ip(headers, fallback_host: str | None, trusted_header: str | None = None) -> str:
    """レート制限のキーに使うクライアント IP を解決する。

    trusted_header: 運用者が宣言した「信頼境界（リバースプロキシ等）が付与するヘッダ」名。
      - 例: Cloudflare 配下なら ``CF-Connecting-IP``、nginx が設定するなら ``X-Real-IP``。
      - 値がカンマ区切り（X-Forwarded-For 等）の場合は **末尾要素**を採用する。先頭はクライアントが
        自由に詰められるため決して使わない（信頼境界は自分が見た送信元を末尾に追記する）。
      - 未指定 or 値が空のときは fallback_host（接続元 IP）に倒す（fail-closed）。

    headers は大文字小文字を区別しない get() を持つこと（Starlette の Headers 等）。
    """
    if trusted_header:
        raw = (headers.get(trusted_header) or "").strip()
        if raw:
            candidate = raw.split(",")[-1].strip() if "," in raw else raw
            if candidate:
                return candidate
    host = (fallback_host or "").strip()
    return host or "unknown"


class InMemoryRateLimiter:
    """Simple per-key sliding-window rate limiter."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = int(limit)
        self.window_seconds = int(window_seconds)
        self._events = defaultdict(deque)
        self._lock = Lock()
        self._last_sweep = monotonic()

    def _sweep(self, cutoff: float) -> None:
        """全イベントがウィンドウ外になったキーを削除する（ロック保持中に呼ぶこと）。

        allow() 内の per-key プルーニングだけではアクセスが途絶えたキーの deque が
        永久に残りメモリが単調増加するため、定期的に空キーを掃除する。
        """
        stale_keys = [key for key, bucket in self._events.items() if not bucket or bucket[-1] <= cutoff]
        for key in stale_keys:
            del self._events[key]

    def allow(self, key: str) -> bool:
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            # ウィンドウ経過ごとに 1 度、アクセスが途絶えたキーをまとめて掃除する。
            if now - self._last_sweep >= self.window_seconds:
                self._sweep(cutoff)
                self._last_sweep = now

            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True
