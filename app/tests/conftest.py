"""
pytest 共通設定

unit テストは DB 不要。DB 依存フィクスチャは tests/integration/conftest.py に定義。
"""

import os
import sys
from pathlib import Path

# app/ ディレクトリを sys.path に追加（conftest.py は app/tests/ 内）
APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("FAISS_API_URL", "")
os.environ.setdefault("HOST_CHECK_ENABLED", "false")
os.environ.setdefault("ROOT_PATH", "")
os.environ.setdefault("DEFAULT_PLATFORM", "twitch")
