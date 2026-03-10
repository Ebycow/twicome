"""
Redis キャッシュ ユーティリティ

REDIS_URL が設定されていない場合はすべての操作が no-op になり、
呼び出し元は DB フォールバックを使う。
"""
import json
import os
from typing import Optional

REDIS_URL: str = os.getenv("REDIS_URL", "").strip()

# コメント全件キャッシュの TTL（秒）。バッチ間隔 4 時間に合わせる
COMMENTS_CACHE_TTL: int = int(os.getenv("COMMENTS_CACHE_TTL", "14400"))

_redis_client = None


def _get_redis():
    global _redis_client
    if not REDIS_URL:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception as e:
        print(f"[cache] Redis 接続失敗 (DB フォールバックを使用): {e}")
        return None


def get_comments_cache(login: str) -> Optional[list]:
    """QUICK_LINK ユーザのコメント全件キャッシュを取得する。未ヒット時は None。"""
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.get(f"twicome:comments:{login}")
        if data:
            return json.loads(data)
    except Exception as e:
        print(f"[cache] get_comments_cache error: {e}")
    return None


def set_comments_cache(login: str, comments: list) -> None:
    """コメント全件リストを Redis にキャッシュする。"""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(
            f"twicome:comments:{login}",
            COMMENTS_CACHE_TTL,
            json.dumps(comments, default=str),
        )
    except Exception as e:
        print(f"[cache] set_comments_cache error: {e}")


def invalidate_comments_cache(login: str) -> None:
    """指定ユーザのコメントキャッシュを削除する（バッチ後の無効化用）。"""
    r = _get_redis()
    if not r:
        return
    try:
        r.delete(f"twicome:comments:{login}")
    except Exception as e:
        print(f"[cache] invalidate_comments_cache error: {e}")
