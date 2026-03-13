"""
Redis キャッシュ ユーティリティ

REDIS_URL が設定されていない場合はすべての操作が no-op になり、
呼び出し元は DB フォールバックを使う。
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REDIS_URL: str = os.getenv("REDIS_URL", "").strip()

# コメント全件キャッシュの TTL（秒）。バッチ間隔 4 時間に合わせる
COMMENTS_CACHE_TTL: int = int(os.getenv("COMMENTS_CACHE_TTL", "14400"))

DATA_VERSION_KEY = "twicome:data_version"
INDEX_LANDING_CACHE_KEY = "twicome:index:landing"
INDEX_USERS_CACHE_KEY = "twicome:index:users"
INDEX_HTML_CACHE_KEY_PREFIX = "twicome:index:html"
COMMENTS_HTML_CACHE_KEY_PREFIX = "twicome:comments:html"

_startup_data_version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _compute_render_version() -> str:
    explicit = os.getenv("APP_RENDER_VERSION", "").strip()
    if explicit:
        return explicit

    app_dir = Path(__file__).resolve().parent
    candidates = [
        app_dir / "templates",
        app_dir / "static" / "sw.js",
        app_dir / "core" / "config.py",
        app_dir / "routers" / "comments.py",
    ]
    mtimes: list[int] = []
    for candidate in candidates:
        if candidate.is_dir():
            mtimes.extend(
                int(path.stat().st_mtime_ns)
                for path in candidate.rglob("*")
                if path.is_file()
            )
        elif candidate.exists():
            mtimes.append(int(candidate.stat().st_mtime_ns))

    if mtimes:
        return str(max(mtimes))
    return _startup_data_version


_render_version = _compute_render_version()

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


def get_data_version() -> str:
    """現在の有効バージョンを返す。データ更新または描画コード更新で変わる。"""
    r = _get_redis()
    base_version = _startup_data_version
    if not r:
        return f"{base_version}:{_render_version}"
    try:
        version = r.get(DATA_VERSION_KEY)
        if version:
            base_version = version
        else:
            r.set(DATA_VERSION_KEY, _startup_data_version)
    except Exception as e:
        print(f"[cache] get_data_version error: {e}")
    return f"{base_version}:{_render_version}"


def set_data_version(version: str) -> str:
    """データバージョンを更新する。Redis 未使用時は no-op。"""
    value = str(version).strip() or _startup_data_version
    r = _get_redis()
    if not r:
        return value
    try:
        r.set(DATA_VERSION_KEY, value)
    except Exception as e:
        print(f"[cache] set_data_version error: {e}")
    return value


def get_index_html_cache(version: str) -> Optional[str]:
    """データバージョンに紐づくトップ HTML キャッシュを取得する。"""
    r = _get_redis()
    if not r:
        return None
    key = f"{INDEX_HTML_CACHE_KEY_PREFIX}:{version}"
    try:
        data = r.get(key)
        if data:
            return data
    except Exception as e:
        print(f"[cache] get_index_html_cache error: {e}")
    return None


def set_index_html_cache(version: str, html: str) -> None:
    """データバージョンに紐づくトップ HTML キャッシュを保存する。"""
    r = _get_redis()
    if not r:
        return
    key = f"{INDEX_HTML_CACHE_KEY_PREFIX}:{version}"
    try:
        r.setex(key, COMMENTS_CACHE_TTL, html)
    except Exception as e:
        print(f"[cache] set_index_html_cache error: {e}")


def _comments_html_cache_key(version: str, platform: str, login: str) -> str:
    normalized_platform = str(platform or "").strip().lower() or "twitch"
    normalized_login = str(login or "").strip().lower()
    return f"{COMMENTS_HTML_CACHE_KEY_PREFIX}:{version}:{normalized_platform}:{normalized_login}"


def get_comments_html_cache(version: str, platform: str, login: str) -> Optional[str]:
    """データバージョンに紐づく初期コメントページ HTML キャッシュを取得する。"""
    r = _get_redis()
    if not r:
        return None
    key = _comments_html_cache_key(version, platform, login)
    try:
        data = r.get(key)
        if data:
            return data
    except Exception as e:
        print(f"[cache] get_comments_html_cache error: {e}")
    return None


def set_comments_html_cache(version: str, platform: str, login: str, html: str) -> None:
    """データバージョンに紐づく初期コメントページ HTML キャッシュを保存する。"""
    r = _get_redis()
    if not r:
        return
    key = _comments_html_cache_key(version, platform, login)
    try:
        r.setex(key, COMMENTS_CACHE_TTL, html)
    except Exception as e:
        print(f"[cache] set_comments_html_cache error: {e}")


def get_index_landing_cache() -> Optional[dict]:
    """トップページ表示に必要な軽量データのキャッシュを取得する。"""
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.get(INDEX_LANDING_CACHE_KEY)
        if data:
            return json.loads(data)
    except Exception as e:
        print(f"[cache] get_index_landing_cache error: {e}")
    return None


def set_index_landing_cache(data: dict) -> None:
    """トップページ表示に必要な軽量データを Redis にキャッシュする。"""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(
            INDEX_LANDING_CACHE_KEY,
            COMMENTS_CACHE_TTL,
            json.dumps(data, default=str),
        )
    except Exception as e:
        print(f"[cache] set_index_landing_cache error: {e}")


def get_index_users_cache() -> Optional[list]:
    """トップページ検索用ユーザー一覧キャッシュを取得する。"""
    r = _get_redis()
    if not r:
        return None
    try:
        data = r.get(INDEX_USERS_CACHE_KEY)
        if data:
            return json.loads(data)
    except Exception as e:
        print(f"[cache] get_index_users_cache error: {e}")
    return None


def set_index_users_cache(users: list) -> None:
    """トップページ検索用ユーザー一覧を Redis にキャッシュする。"""
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(
            INDEX_USERS_CACHE_KEY,
            COMMENTS_CACHE_TTL,
            json.dumps(users, default=str),
        )
    except Exception as e:
        print(f"[cache] set_index_users_cache error: {e}")


def invalidate_index_cache() -> None:
    """トップページ関連キャッシュを削除する（バッチ後の無効化用）。"""
    r = _get_redis()
    if not r:
        return
    try:
        keys = [INDEX_LANDING_CACHE_KEY, INDEX_USERS_CACHE_KEY]
        html_keys = list(r.scan_iter(f"{INDEX_HTML_CACHE_KEY_PREFIX}:*"))
        if html_keys:
            keys.extend(html_keys)
        r.delete(*keys)
    except Exception as e:
        print(f"[cache] invalidate_index_cache error: {e}")
