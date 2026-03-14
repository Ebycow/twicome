"""ユニットテスト共通フィクスチャ"""

import os

# ユニットテストは実DBに接続しないが、app_factory のインポート時に
# DATABASE_URL が必要なためダミー値をセットする
os.environ.setdefault("DATABASE_URL", "mysql+pymysql://test:test@localhost:3306/test")
