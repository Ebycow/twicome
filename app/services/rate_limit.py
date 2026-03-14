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

    def allow(self, key: str) -> bool:
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True
