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


def get_user_meta_cache(login: str) -> Optional[dict]:
    """vod_options / owner_options のキャッシュを取得する。未ヒット時は None。"""
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.get(f"twicome:meta:{login}")
        if data:
            return json.loads(data)
    except Exception as e:
        print(f"[cache] get_user_meta_cache error: {e}")
    return None


def set_user_meta_cache(login: str, meta: dict) -> None:
    """vod_options / owner_options を Redis にキャッシュする。"""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(
            f"twicome:meta:{login}",
            COMMENTS_CACHE_TTL,
            json.dumps(meta, default=str),
        )
    except Exception as e:
        print(f"[cache] set_user_meta_cache error: {e}")

def get_index_cache() -> Optional[dict]:
    """トップページの重いクエリ結果キャッシュを取得する。未ヒット時は None。"""
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.get("twicome:index")
        if data:
            return json.loads(data)
    except Exception as e:
        print(f"[cache] get_index_cache error: {e}")
    return None


def set_index_cache(data: dict) -> None:
    """トップページのクエリ結果を Redis にキャッシュする。"""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(
            "twicome:index",
            COMMENTS_CACHE_TTL,
            json.dumps(data, default=str),
        )
    except Exception as e:
        print(f"[cache] set_index_cache error: {e}")


def invalidate_index_cache() -> None:
    """トップページキャッシュを削除する（バッチ後の無効化用）。"""
    r = _get_redis()
    if not r:
        return
    try:
        r.delete("twicome:index")
    except Exception as e:
        print(f"[cache] invalidate_index_cache error: {e}")
