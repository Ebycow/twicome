"""
Redis キャッシュ無効化スクリプト

バッチ処理（insertdb.py）完了後に呼ばれ、
QUICK_LINK_LOGINS に含まれるユーザのコメントキャッシュを削除する。
次回アクセス時に最新データが DB から取得されキャッシュが再構築される。

REDIS_URL が未設定の場合はスキップ（エラーにしない）。
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
ENV_PATH = Path(os.getenv("ENV_FILE", str(PROJECT_ROOT / ".env")))
if not ENV_PATH.is_absolute():
    ENV_PATH = PROJECT_ROOT / ENV_PATH
load_dotenv(str(ENV_PATH))

REDIS_URL = os.getenv("REDIS_URL", "").strip()
if not REDIS_URL:
    print("REDIS_URL が設定されていません。キャッシュ無効化をスキップします。")
    sys.exit(0)

QUICK_LINK_LOGINS_RAW = os.getenv("QUICK_LINK_LOGINS", "")
logins = [lo.strip() for lo in QUICK_LINK_LOGINS_RAW.split(",") if lo.strip()]
if not logins:
    print("QUICK_LINK_LOGINS が設定されていません。スキップします。")
    sys.exit(0)

try:
    import redis

    r = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=5)
    r.ping()
except Exception as e:
    print(f"Redis 接続失敗（スキップ）: {e}")
    sys.exit(0)

keys = []
for login in logins:
    keys.append(f"twicome:comments:{login}")
    keys.append(f"twicome:meta:{login}")
deleted = r.delete(*keys)
print(f"キャッシュ無効化完了: {deleted} キー削除 ({', '.join(keys)})")
