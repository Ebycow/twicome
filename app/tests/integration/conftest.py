"""
統合テスト用フィクスチャ

テスト用データベース: appdb_test（本番/開発 DBとは別）
- セッション開始時に Alembic マイグレーションを適用
- 各統合テスト後に全テーブルを TRUNCATE してクリーンアップ

環境変数:
  TEST_DATABASE_URL: テスト用DB URL（デフォルト: appuser/apppass@127.0.0.1:3306/appdb_test）
  CI 環境では GitHub Actions の mysql サービスが 127.0.0.1:3306 で起動している前提
  ローカルでは docker compose run --rm test pytest で実行
"""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

APP_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = APP_DIR.parent

_DEFAULT_TEST_DB = "mysql+pymysql://appuser:apppass@127.0.0.1:3306/appdb_test?charset=utf8mb4"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DB)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL

# ── テーブル truncate 順（外部キー制約を考慮した逆順）───────────────────────
_TRUNCATE_TABLES = [
    "community_notes",
    "comments",
    "vods",
    "users",
]


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """テスト用 DB にマイグレーションを一度だけ適用する。"""
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
def db_engine():
    """セッションスコープの SQLAlchemy engine。"""
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(db_engine):
    """テストごとにセッションを提供し、終了後に全テーブルを TRUNCATE する。"""
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


@pytest.fixture()
def client(db_engine):
    """
    FastAPI TestClient。
    SessionLocal を差し替えてテスト用 DB を指すようにする。
    """
    import core.db as db_module
    original_engine = db_module.engine
    original_session_local = db_module.SessionLocal

    db_module.engine = db_engine
    db_module.SessionLocal = sessionmaker(
        bind=db_engine, autoflush=False, autocommit=False, future=True
    )

    from fastapi.testclient import TestClient

    from app_factory import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    db_module.engine = original_engine
    db_module.SessionLocal = original_session_local
