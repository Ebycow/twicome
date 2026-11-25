# Twicome

Twitch VOD のコメントのうち、**収集対象ユーザーのコメントだけ**を集めてタイムライン表示する軽量 Web アプリケーション。

## 収集対象ユーザー

`.env` の `QUICK_LINK_LOGINS` と `DEFAULT_LOGIN` に書いたログイン名（の和集合）が収集対象ユーザー。

- DB には収集対象ユーザーのコメントだけを保存する。他のユーザーはコメントもユーザー情報も保存しない
  （VOD の外部キーのため、配信者のユーザー行だけは保存する）
- チャットの生 JSON は、収集対象ユーザーが 1 件でもコメントした VOD だけを `<vod_id>.json.gz` で保存する。
  含まない VOD はダウンロード後すぐに破棄し、`comments/no_target_vods.tsv` に記録して再ダウンロードしない
- 収集対象ユーザーを追加すると、台帳に記録済みの VOD も追加ユーザーについて再判定される
- 収集対象から外したユーザーのデータは、次回バッチの `prune_non_targets.py` が DB から削除する

## 機能

- **コメント TL**: 収集対象ユーザーのコメント一覧（キーワード・VOD・配信者・期間で絞り込み、エクスポート）
- **VOD / 配信者一覧**: 収録済み VOD と収集対象の配信者
- **Best 9**: お気に入りコメントのショーケース表示
- **投票システム**: コメントへのいいね/よくないね
- **PWA対応**: Service Worker によるオフラインサポート

軽量化のため、FAISS 類似検索・感情検索・クラスタ探索・統計・クイズ・コミュニティノート・形態素解析・Redis キャッシュは廃止した。

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| バックエンド | FastAPI (Python 3.11), Uvicorn |
| DB | MySQL 8.0, SQLAlchemy 2.0, Alembic |
| フロントエンド | Jinja2, CSS, JavaScript (ES modules) |
| 外部API | Twitch API |
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

# 収集対象ユーザー（カンマ区切り）
QUICK_LINK_LOGINS=userid
DEFAULT_LOGIN=userid
```

VOD を収集する配信者は `data/<APP_ENV>/targetusers.csv`（`name,id` 形式）に書く。`/add_user` 画面からも追加できる。

DB の接続先は Docker Compose 使用時はデフォルト値のままでよい。

### 2. アプリ起動（開発）

```bash
docker compose -f docker-compose.dev.yml up --build
```

アプリは `http://localhost:8011` で起動する。

## 開発

### lint・テストの一括実行

```bash
./ci-local.sh
```

`ci-local.sh` は `docker-compose.dev.yml` を使い、GitHub Actions CI と同じ lint・テストをまとめて実行するスクリプト。

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

VOD リストの取得 → チャットのダウンロードと収集対象ユーザーでの絞り込み → DB インポート → 対象外データの削除、の順に実行する。
Docker の `batch` サービスは起動直後に 1 回実行し、以降は 4 時間ごとに繰り返す。

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
├── app/                    # FastAPIアプリ本体
│   ├── core/               # 設定・DB・キャッシュ・ミドルウェア
│   ├── clients/            # 外部サービスクライアント（Twitch）
│   ├── routers/            # APIエンドポイント
│   ├── services/           # ビジネスロジック
│   ├── repositories/       # DBアクセス層
│   ├── templates/          # Jinja2テンプレート
│   ├── static/             # JS / CSS / PWAリソース
│   └── tests/              # unit / integration / ui
├── batch/                  # バッチ処理スクリプト（VOD取得・コメントDL・DBインポート・対象外データ削除）
├── migrate/                # Alembicマイグレーション
├── twicome-mcp-server/     # Twicome HTTP API を公開するMCPサーバー
├── util/                   # Twitch API補助スクリプト（トークン取得等）
├── library/                # 同梱バイナリ（TwitchDownloaderCLI）
├── ci/                     # CI補助スクリプト（クローン検出等）
├── docs/                   # 調査・設計ドキュメント
├── docker-compose.yml      # 本番設定
├── docker-compose.dev.yml  # 開発・テスト設定
├── ci-local.sh             # ローカルCI一括実行スクリプト
├── run_batch.sh            # バッチ一括実行スクリプト
└── .env.example            # 環境変数テンプレート
```

## 本番デプロイ

```bash
docker compose -f docker-compose.yml up -d
```

本番構成は `db`（MySQL、バッファプール 64MB・performance_schema 無効・バイナリログ無効の省メモリ設定）、`migrate`、`app`、`batch` の 4 サービス。
各コンテナのログは 10MB × 3 ファイルにローテーションされ、バッチログは `LOG_RETENTION_DAYS`（既定 14 日）を過ぎると削除される。

本番環境ではアプリは `8000` ポートで起動する。リバースプロキシ（Nginx等）経由での運用を想定している。`HOST_CHECK_ENABLED=true` の場合、IP直アクセスは拒否される。
