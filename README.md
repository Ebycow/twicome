# Twicome

Twitch VOD のコメントを検索・分析するWebアプリケーション。

[こんなことにつかえます](docs/use-cases.md)

## 機能

- **コメント検索**: VODコメントのキーワード検索・一覧表示
- **セマンティック検索**: 埋め込みベクトル（FAISS）を使った類似コメント検索
- **感情軸検索**: 喜び・信頼・驚きなど感情次元でのコメント検索
- **コメントクラスタリング**: コメントのテーマ別クラスタ可視化
- **統計ページ**: ユーザーごとのコメント頻度・傾向分析
- **コミュニティノート**: AIによるコメントへの補足情報生成（OpenRouter API）
- **クイズ**: コメントの書き方からユーザーを当てるランキングタスク
- **Best 9**: 高評価コメントのショーケース表示
- **投票システム**: コメントへのいいね/よくないね
- **PWA対応**: Service Worker によるオフラインサポート

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| バックエンド | FastAPI (Python 3.11), Uvicorn |
| DB | MySQL 8.0, SQLAlchemy 2.0, Alembic |
| キャッシュ | Redis 7 |
| 検索 | sentence-transformers, FAISS |
| フロントエンド | Jinja2, CSS, JavaScript (ES modules) |
| 外部API | Twitch API, OpenRouter API |
| コンテナ | Docker, Docker Compose |

## セットアップ

### 1. 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集して以下を設定する:

```env
# Twitch API認証情報
CLIENT_ID=
CLIENT_SECRET=
ACCESS_TOKEN=

# OpenRouter（コミュニティノート生成）
OPENROUTER_API_KEY=

# クイックアクセス対象ユーザー
QUICK_LINK_LOGINS=userid
DEFAULT_LOGIN=userid
```

DB・Redisの接続先はDocker Compose使用時はデフォルト値のままでよい。

### 2. アプリ起動（開発環境）

```bash
docker compose -f docker-compose.dev.yml up --build
```

アプリは `http://localhost:8011` で起動する。

### 3. DBマイグレーション

```bash
docker compose -f docker-compose.dev.yml run --rm migrate
```

## 開発

### lint・テストの一括実行

```bash
./run_batch.sh
```

`run_batch.sh` は `docker-compose.dev.yml` を使い、lint・テストをまとめて実行するスクリプト。

### 個別実行

```bash
# Python lint
docker compose -f docker-compose.dev.yml run --rm lint

# JavaScript lint
docker compose -f docker-compose.dev.yml run --rm lint-js

# CSS lint
docker compose -f docker-compose.dev.yml run --rm lint-css

# HTML (Jinja2) lint
docker compose -f docker-compose.dev.yml run --rm lint-html

# ユニット・インテグレーションテスト
docker compose -f docker-compose.dev.yml run --rm test

# UIテスト（Playwright）
docker compose -f docker-compose.dev.yml run --rm test-ui
```

### ローカルCIの再現

```bash
./ci-local.sh              # 全パイプライン
./ci-local.sh --skip-ui    # Playwrightスキップ
./ci-local.sh lint-py unit # ステップ指定
```

## バッチ処理

VODリストの取得・コメントダウンロード・DBインポート・FAISSインデックス構築などを実行する。

```bash
# 全バッチ実行（デフォルトは .env を参照）
./run_batch.sh

# 環境ファイル指定
./run_batch.sh --env-file .env.honban

# コメントJSONのインポート
./run_import_comments.sh --env-file .env.development --comments-dir data/honban/comments
```

バッチスクリプトの詳細は [batch/README.md](batch/README.md) を参照。

## プロジェクト構成

```
twicome/
├── app/                   # FastAPIアプリ本体
│   ├── routers/           # APIエンドポイント
│   ├── services/          # ビジネスロジック
│   ├── repositories/      # DBアクセス層
│   ├── templates/         # Jinja2テンプレート
│   ├── static/            # JS / CSS / PWAリソース
│   └── tests/             # unit / integration / ui
├── batch/                 # バッチ処理スクリプト
├── faiss-api/             # FAISSマイクロサービス
├── migrate/               # Alembicマイグレーション
├── challenge/             # クイズチャレンジAPIとベースライン
├── docker-compose.yml     # 本番設定
├── docker-compose.dev.yml # 開発・テスト設定
├── run_batch.sh           # バッチ一括実行スクリプト
└── .env.example           # 環境変数テンプレート
```

## 本番デプロイ

```bash
docker compose -f docker-compose.yml up -d
```

本番環境ではアプリは `8000` ポートで起動する。リバースプロキシ（Nginx等）経由での運用を想定している。`HOST_CHECK_ENABLED=true` の場合、IP直アクセスは拒否される。
