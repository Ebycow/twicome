"""レートリミッター"""

from collections import defaultdict, deque
from threading import Lock
from time import monotonic


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
