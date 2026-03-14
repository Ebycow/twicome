"""
Playwright UI テスト用フィクスチャ

【UIテストの仕組み】
  - 実際の uvicorn サーバーをバックグラウンドスレッドで起動する
  - Playwright がそのサーバーにブラウザ経由でアクセスする
  - DB は統合テストと同じ appdb_test を使い、テストごとに TRUNCATE する

【pytest-playwright の主なフィクスチャ】
  - playwright : Playwright インスタンス
  - browser    : Browser インスタンス (chromium/firefox/webkit)
  - context    : BrowserContext (ここに base_url が渡される)
  - page       : Page (1つのブラウザタブ)

  ここで base_url を定義することで、page.goto("/") が
  自動的に http://127.0.0.1:{port}/ に変換される。
"""

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import requests
import uvicorn
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── パス & 環境変数 (app のインポートより前に設定する) ────────────────────────

APP_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = APP_DIR.parent
sys.path.insert(0, str(APP_DIR))

_DEFAULT_TEST_DB = "mysql+pymysql://appuser:apppass@127.0.0.1:3306/appdb_test?charset=utf8mb4"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DB)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("FAISS_API_URL", "")
os.environ.setdefault("HOST_CHECK_ENABLED", "false")
os.environ.setdefault("ROOT_PATH", "")
os.environ.setdefault("DEFAULT_PLATFORM", "twitch")

# ── テーブル truncate 順（外部キー制約を考慮した逆順）────────────────────────

_TRUNCATE_TABLES = ["community_notes", "comments", "vods", "users"]


# ── ヘルパー ─────────────────────────────────────────────────────────────────


def _get_free_port() -> int:
    """OS が空きポートを割り当て、その番号を返す。"""
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class _UvicornServer(threading.Thread):
    """FastAPI アプリをバックグラウンドスレッドで起動する。"""

    def __init__(self, config: uvicorn.Config):
        super().__init__(daemon=True)
        self.server = uvicorn.Server(config)

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True
        self.join(timeout=5)


# ── セッションスコープのフィクスチャ ─────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """テスト用 DB に Alembic マイグレーションを一度だけ適用する。"""
    alembic_ini = REPO_ROOT / "migrate" / "alembic.ini"
    result = subprocess.run(
        ["alembic", "-c", str(alembic_ini), "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Migration failed:\n{result.stderr}\n{result.stdout}")


@pytest.fixture(scope="session")
def db_engine(apply_migrations):
    """セッションスコープの SQLAlchemy engine。"""
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True, future=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def live_server(apply_migrations):
    """
    FastAPI アプリをバックグラウンドで起動し、ベース URL を返す。

    uvicorn は static/ ディレクトリを CWD からの相対パスで探すため、
    起動前に CWD を app/ に変更している。
    """
    original_cwd = os.getcwd()
    os.chdir(str(APP_DIR))

    # app インポートはここで初めて行う（DATABASE_URL 設定後）
    from app_factory import app

    port = _get_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = _UvicornServer(config)
    server.start()

    # サーバーが応答するまで待機（最大 10 秒）
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            requests.get(f"{url}/health", timeout=0.5)
            break
        except Exception:
            time.sleep(0.2)

    yield url

    server.stop()
    os.chdir(original_cwd)


@pytest.fixture(scope="session")
def base_url(live_server: str) -> str:
    """
    pytest-playwright / pytest-base-url が使う base_url フィクスチャ。

    session スコープにする必要がある（pytest-base-url が session スコープで要求するため）。
    これを定義すると BrowserContext に base_url が渡され、
    page.goto("/") が http://127.0.0.1:{port}/ と解釈される。
    """
    return live_server


# ── テストごとのフィクスチャ ─────────────────────────────────────────────────


@pytest.fixture()
def db(db_engine):
    """
    テストごとに DB セッションを提供し、終了後に全テーブルを TRUNCATE する。

    これにより各テストが独立したデータ状態で実行される。
    """
    Session = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    yield session
    session.close()
    with db_engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in _TRUNCATE_TABLES:
            conn.execute(text(f"TRUNCATE TABLE `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()
