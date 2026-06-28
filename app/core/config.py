"""アプリケーション設定・環境変数"""

import os
import secrets
import subprocess
import time

# 例: mysql+pymysql://user:password@dbhost:3306/appdb?charset=utf8mb4
DATABASE_URL = os.getenv("DATABASE_URL", "")


def get_database_url() -> str:
    """DATABASE_URL を返す。未設定の場合は RuntimeError。"""
    url = os.getenv("DATABASE_URL", DATABASE_URL)
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Set DATABASE_URL in .env or environment variables.")
    return url


DEFAULT_PLATFORM = os.getenv("DEFAULT_PLATFORM", "twitch")
ROOT_PATH = os.getenv("ROOT_PATH", "/twicome").rstrip("/")
DEFAULT_LOGIN = os.getenv("DEFAULT_LOGIN", "").strip()
SERVICE_WORKER_CACHE_NAME = "twicome-v15"


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_csv_env(name: str):
    raw = os.getenv(name, "")
    items = []
    seen = set()
    for token in raw.split(","):
        value = token.strip()
        if not value or value in seen:
            continue
        items.append(value)
        seen.add(value)
    return items


# .env 例: QUICK_LINK_LOGINS=userloginid
QUICK_LINK_LOGINS = _parse_csv_env("QUICK_LINK_LOGINS")

# .env 例: HOST_CHECK_ENABLED=true
HOST_CHECK_ENABLED = _parse_bool_env("HOST_CHECK_ENABLED", True)

# レート制限のクライアント識別に使う「信頼境界が付与するヘッダ」名。
# 例: Cloudflare 配下なら CF-Connecting-IP、nginx が X-Real-IP を設定するなら X-Real-IP。
# 未設定時は接続元IP(request.client.host)を使う。プロキシ背後では接続元が常に同一になり
# 全員が同一バケットへ落ちる（＝全体で過剰に絞られる）ため、プロキシ配下では必ず設定すること。
# X-Forwarded-For の先頭はクライアントが詐称可能なので採用しない（末尾＝信頼境界が追記した値を使う）。
RATE_LIMIT_CLIENT_IP_HEADER: str = os.getenv("RATE_LIMIT_CLIENT_IP_HEADER", "").strip()

# .env 例: FAISS_API_URL=http://faiss-api:8100
# 未設定の場合は埋め込み検索機能が無効化される
FAISS_API_URL: str = os.getenv("FAISS_API_URL", "").strip().rstrip("/")
FAISS_ENABLED: bool = bool(FAISS_API_URL)

# .env 例: REDIS_URL=redis://redis:6379/0
# 未設定の場合はキャッシュ無効（DB に直接アクセス）
REDIS_URL: str = os.getenv("REDIS_URL", "").strip()


def _get_static_version() -> str:
    """静的ファイルのキャッシュバスティング用バージョン文字列を返す。

    STATIC_VERSION 環境変数 > git short hash > 起動時タイムスタンプ の順で決定する。
    """
    env_ver = os.getenv("STATIC_VERSION", "").strip()
    if env_ver:
        return env_ver
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return str(int(time.time()))


STATIC_VERSION: str = _get_static_version()

# クイズタスク API のトークン署名キー
# 環境変数未設定時はプロセス起動ごとにランダム生成（同一プロセス内でのみ有効）
QUIZ_SECRET_KEY: str = os.getenv("QUIZ_SECRET_KEY") or secrets.token_hex(32)
