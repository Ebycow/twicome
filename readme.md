# Twicome

Twitch VOD コメントを収集し、検索・分析・可視化するための Web アプリケーションです。  
データ収集バッチ、MySQL 取り込み、FAISS 類似検索、コミュニティノート生成までを一体で運用できます。

## 重要な運用前提（必読）

- 更新系エンドポイント（例: `/add_user`, `/like`, `/dislike`, FAISS 更新系 API）は、インターネットへ直接公開する設計にはなっていません。
- 外部公開する場合は、以下の要素を検討してください。
  - アプリ層の認証・認可（更新系 API の保護）
  - レート制限（特に更新系・検索系 API）
  - 監査ログ/アクセスログの整備
  - ネットワーク境界（WAF/許可IP/内部APIの閉域化）の明確化

## 主な機能

- Twitch VOD コメントの自動収集（Twitch API + TwitchDownloaderCLI）
- トップページユーザー検索（login / display_name インクリメンタルサジェスト、配信者フィルター・並び替え）
- コメント一覧 UI（フィルタ、並び替え、無限スクロール、リアクション）
- 類似検索（FAISS + SentenceTransformer）
- 典型度検索（重心距離）
- 感情スライダー検索（感情アンカーの加重合成）
- コミュニティノート表示と危険度スコア表示
- 統計ページ（時間帯、曜日、配信者別活動率、影響度分析）
- コメント当てクイズ

## システム構成

- `batch/scripts/get_vod_list_batch.py`:
  - 監視対象ユーザの VOD 一覧を Twitch API から取得
- `batch/scripts/batch_download_comments.py`:
  - `library/TwitchDownloaderCLI` で VOD コメント JSON を取得
- `batch/scripts/insertdb.py`:
  - コメント JSON を `users` / `vods` / `comments` に upsert
- `batch/scripts/build_faiss_index.py`:
  - コメント埋め込みを生成し、ユーザ別 FAISS インデックスを作成
- `batch/scripts/generate_community_notes.py`:
  - dislike 閾値以上のコメントに OpenRouter 経由でノートを生成
- `app/`:
  - FastAPI + Jinja2 で検索 UI / API / 統計 UI を提供

## ディレクトリ概要

- `app/`: Web アプリ本体（FastAPI, router, template）
- `migrate/`: Alembic マイグレーション
- `batch/scripts/`: バッチ本体
- `batch/prompts/`: コミュニティノート生成プロンプト
- `util/`: Twitch トークン更新、ユーザ ID 取得などの補助スクリプト
- `data/`: 環境別の入出力データ（`development`, `honban` など）
- `library/TwitchDownloaderCLI`: コメント取得用 CLI バイナリ
- `dbschema.md`: MySQL スキーマ

## セットアップ

### 1. 前提

- Python 3.11 系
- MySQL 8 系
- Twitch API の `CLIENT_ID` / `CLIENT_SECRET` / `ACCESS_TOKEN`
- 収集を行う場合は `library/TwitchDownloaderCLI` が実行可能であること

必要なら実行権限を付与します。

```bash
chmod +x library/TwitchDownloaderCLI
```

### 2. Python 環境

`run_batch.sh` はデフォルトで `.venv/bin/python` を使うため、ルートに仮想環境を作る運用が前提です。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r app/requirements.txt -r batch/requirements.txt
```

### 3. 設定ファイル

`.env.example` と `faiss_config.json.example` をコピーして編集します。

```bash
cp .env.example .env
cp faiss_config.json.example faiss_config.json
cp batch/prompts/community_note_system_prompt.txt.example batch/prompts/community_note_system_prompt.txt
```

最低限、次の項目は設定してください。

- `DATABASE_URL`:
  - Web アプリ（SQLAlchemy）用
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`:
  - バッチ（mysql-connector-python）用
- `ACCESS_TOKEN`, `CLIENT_ID`:
  - Twitch API 用
- `FAISS_CONFIG_PATH`:
  - 既定は `./faiss_config.json`
- `OPENROUTER_API_KEY`:
  - コミュニティノート生成を使う場合のみ必須

補助設定（任意）:

- `ROOT_PATH`（既定 `/twicome`）
- `DEFAULT_LOGIN`
- `QUICK_LINK_LOGINS`
- `HOST_CHECK_ENABLED`
- `FORWARDED_ALLOW_IPS`（既定 `127.0.0.1`。リバースプロキシ経由時はプロキシIPを設定）
- `APP_ENV`, `BATCH_DATA_DIR` などのバッチ入出力先

Docker Compose で動かす場合、DB 接続先はコンテナ名 `db:3306` を使います（ホストへの DB ポート公開は不要）。

### 4. MySQL マイグレーション適用

初期スキーマは Alembic で管理します。  
（`dbschema.md` は参照用、実際の適用はマイグレーションを使用）

```bash
docker compose run --rm migrate
```

### 5. 監視対象ユーザ CSV

バッチは `TARGET_USERS_CSV` を読みます。  
CSV には `name,id` 列が必要です（例: `targetusers.csv`）。

## 実行方法

### バッチ一括実行

```bash
./run_batch.sh
```

別 env ファイルを使う場合:

```bash
./run_batch.sh --env-file .env.development
```

FAISS インデックス作成をスキップする場合:

```bash
SKIP_FAISS=1 ./run_batch.sh
```

バッチの実行順序:

1. `get_vod_list_batch.py`
2. `batch_download_comments.py`
3. `insertdb.py`
4. `build_faiss_index.py`（`SKIP_FAISS!=1` のとき）
5. `generate_community_notes.py`（失敗しても非致命）

ログは既定で `data/${APP_ENV}/logs/batch_YYYYmmdd_HHMMSS.log` に出力されます。

`OPENROUTER_API_KEY` 未設定時は、`generate_community_notes.py` が警告終了します（他工程は成功扱い）。

### 既存コメント JSON だけ取り込み

```bash
./run_import_comments.sh --env-file .env.development --comments-dir data/honban/comments
```

既存 VOD を再取り込みしたい場合:

```bash
./run_import_comments.sh --env-file .env.development --comments-dir data/honban/comments --reingest-existing-vods
```

### Web アプリ起動（ローカル）

```bash
cd app
../.venv/bin/uvicorn main:app --env-file ../.env --host 0.0.0.0 --port 8000 --reload
```

`ROOT_PATH=/twicome` の場合:

- `http://localhost:8000/twicome`

`ROOT_PATH=/` の場合:

- `http://localhost:8000/`

### Docker Compose 起動

本番寄り設定（`db` + `migrate` + `app` + `batch` を同時起動）:

```bash
docker compose up --build
```

- `db`: ホストへは公開しない（`app`/`batch`/`migrate` から `db:3306` で接続）
- `app`: `http://localhost:8000/twicome`（healthcheck: `GET /health` を30秒ごとに確認）
- `batch`: 起動直後に1回実行、その後4時間ごとに定期実行
- `migrate`: 起動時に `alembic upgrade head` を実行（完了後に停止）

リバースプロキシ配下で実IPを扱う場合は、`.env` に `FORWARDED_ALLOW_IPS` を設定してください（例: `FORWARDED_ALLOW_IPS=192.168.222.112,127.0.0.1`）。

開発設定（`db` + `migrate` + `app` + `batch` を同時起動）:

```bash
docker compose -f docker-compose.dev.yml up --build
```

- `db`: ホストへは公開しない（`app`/`batch`/`migrate` から `db:3306` で接続）
- `app`: `http://localhost:8011/`（healthcheck: `GET /health` を30秒ごとに確認）
- `test`: 通常の `up` では起動しない（`test` profile 扱い）

開発 compose 上でテストを実行する場合:

```bash
docker compose -f docker-compose.dev.yml run --rm test
docker compose -f docker-compose.dev.yml run --rm test pytest tests/unit
docker compose -f docker-compose.dev.yml run --rm test pytest tests/integration
```

- `appdb_test` は `db` の healthcheck 時に自動作成・権限付与されます

`batch` / `library` のコード変更を反映するには `batch` イメージ再ビルド（`docker compose build batch`）が必要です。

`docker-compose*.yml` のボリュームは `./data/...` を参照するため、運用に合わせてパスを調整してください。

ホストから DB に直接入りたい場合は、ポート公開ではなく `docker compose exec` を使ってください。

```bash
docker compose exec db mysql -uappuser -p appdb
```

外部 DB を使いたい場合は、`COMPOSE_DATABASE_URL` と `COMPOSE_MYSQL_*` を上書きしてください。

例:

```bash
COMPOSE_DATABASE_URL="mysql+pymysql://appuser:apppass@host.docker.internal:3306/appdb?charset=utf8mb4" docker compose up --build
```

## テスト

### テスト構成

```
app/tests/
├── unit/
│   └── test_comment_utils.py       # 純粋関数テスト（DB 不要・高速）
├── integration/
│   ├── test_user_repo.py           # user_repo の SQL 検証
│   ├── test_comment_repo.py        # comment_repo の SQL 検証
│   ├── test_http.py                # API の契約テスト（ステータス・JSON 構造）
│   └── test_html.py                # HTML レンダリング・UI 構造テスト
└── ui/
    ├── test_index_page.py          # Playwright によるトップページ UI テスト
    └── test_user_comments_page.py  # Playwright によるコメントページ UI テスト
```

テスト用 DB は `appdb_test`（本番・開発 DB とは別）を使います。
統合テストは各テスト後に全テーブルを TRUNCATE するため、テスト間の干渉はありません。

### Docker Compose でテストを実行する（推奨）

```bash
# 通常テスト（unit + integration）
docker compose -f docker-compose.dev.yml run --rm test

# unit テストのみ（DB 不要、高速）
docker compose -f docker-compose.dev.yml run --rm test pytest tests/unit

# 統合テストのみ
docker compose -f docker-compose.dev.yml run --rm test pytest tests/integration

# HTML レンダリングテストのみ
docker compose -f docker-compose.dev.yml run --rm test pytest tests/integration/test_html.py

# カバレッジ付き
docker compose -f docker-compose.dev.yml run --rm test \
  pytest --cov=. --cov-config=.coveragerc --cov-report=term-missing

# UI テスト（Playwright）
docker compose -f docker-compose.dev.yml run --rm test-ui
```

`appdb_test` は `db` サービスの healthcheck 時に自動作成・権限付与されます。
`db` サービスが起動済みであれば `test` サービスは即時実行できます。
Playwright を使う `tests/ui` は別サービス `test-ui` で実行してください。

### ローカル（仮想環境）でテストを実行する

外部 MySQL に `appdb_test` データベースと同等の権限を持つユーザーが存在する場合、
ホストから直接実行できます。

```bash
cd app
TEST_DATABASE_URL="mysql+pymysql://appuser:apppass@127.0.0.1:3306/appdb_test?charset=utf8mb4" \
  pytest tests/unit

TEST_DATABASE_URL="mysql+pymysql://appuser:apppass@127.0.0.1:3306/appdb_test?charset=utf8mb4" \
  pytest tests/integration
```

`TEST_DATABASE_URL` 未設定時は `127.0.0.1:3306/appdb_test` がデフォルトで使われます。

### CI

`.github/workflows/ci.yml` で以下を自動実行します。

1. `compile-check` ジョブ：全 Python ファイルを syntax compile して軽量な broken code detection を実行
2. `unit-test` ジョブ：DB 不要。`pytest tests/unit` を JUnit XML / coverage data 付きで実行
3. `migration` ジョブ：MySQL 起動後、`alembic upgrade head` でスキーマ適用
4. `integration-test` ジョブ：`migration` 完了後、`pytest tests/integration` を JUnit XML / coverage data 付きで実行
5. `coverage-summary` ジョブ：unit / integration の coverage data を結合し、app-only の `coverage.xml` と JUnit XML 群を artifact 化

## Web 画面

- `/`: トップ（ユーザ検索・サジェスト、配信者フィルター・並び替え、人気コメント、導線）
- `/u/{login}`: コメント一覧
- `/u/{login}/stats`: 統計
- `/u/{login}/quiz`: コメント当てクイズ
- `/add_user`: 監視対象追加
- `/manual`: 使い方ガイド

注意:

- `/add_user` は `/host/targetusers.csv` に書き込む実装です。
- Docker では `targetusers.csv` を `/host/targetusers.csv` にマウントして使ってください。

## 主要 API

- `GET /health`: ヘルスチェック（`{"status": "ok"}` を返す）
- `GET /api/u/{login}`: コメント一覧
- `GET /api/u/{login}/similar`: 類似検索
- `GET /api/u/{login}/centroid`: 典型度検索
- `GET /api/u/{login}/emotion`: 感情検索
- `GET /api/emotion_axes`: 感情軸一覧
- `GET /api/users/commenters?streamer={login}`: 指定配信者のVODにコメントしたユーザーのloginリストを返す
- `POST /like/{comment_id}?count=1`: いいね加算
- `POST /dislike/{comment_id}?count=1`: わるいね加算
- `GET /api/u/{login}/quiz/start`: クイズ問題生成

## FAISS 検索について

- モデルは `cl-nagoya/sup-simcse-ja-base` を使用
- `build_faiss_index.py` がユーザ別に `.faiss` / `.meta.json` を生成
- アプリ側は `app/faiss_data` を参照
- Docker 利用時は `app/faiss_data` へインデックスディレクトリをマウントして整合を取ってください

### 埋め込みモデルの変更手順

埋め込みモデルを変更する際は、`faiss_config.json` の `embedding_model` フィールドを書き換えるだけでは**反映されません**（このフィールドは現在記録用途のみ）。以下の4箇所を変更する必要があります。

**1. `faiss-api/Dockerfile`** — ビルド時の事前ダウンロード

```dockerfile
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('新モデル名', device='cpu')"
```

**2. `docker-compose.yml` および `docker-compose.dev.yml`** — faiss-api サービスの環境変数

```yaml
faiss-api:
  environment:
    EMBEDDING_MODEL: 新モデル名
```

**3. `faiss_config.json` / `faiss_config.dev.json`** — 記録として更新

```json
"embedding_model": "新モデル名"
```

**4. 既存インデックスを削除してから再インデックス**

旧モデルで生成したインデックスは新モデルと互換性がないため、削除してから再生成が必要です。

```bash
# 旧インデックスを削除（本番の例）
rm data/honban/faiss_data/*.faiss
rm data/honban/faiss_data/*.meta.json

# イメージ再ビルド（モデルのダウンロードが走るため数分かかる）
docker compose --profile faiss build faiss-api

# 起動
docker compose --profile faiss up -d

# 再インデックス（バッチ実行）
docker compose run --rm batch python batch/scripts/build_faiss_index.py
```

## 補助スクリプト（util）

- `util/refreshtoken.py`:
  - `.env` の `ACCESS_TOKEN` 自動更新
- `util/tokens.py`:
  - クライアントクレデンシャルで token 取得
- `util/userid.py`:
  - Twitch login から user id 取得
- `util/extract_twitch_comments.py`:
  - コメント JSON から特定ユーザコメントを抽出

## ライセンスと依存関係

- TwitchDownloaderCLI の著作権表示: `library/COPYRIGHT.txt`
- TwitchDownloaderCLI のサードパーティライセンス: `library/THIRD-PARTY-LICENSES.txt`
- Python 依存関係: `app/requirements.txt`, `batch/requirements.txt`

## キャッシュ戦略

Redis（`REDIS_URL` 設定時のみ有効）を使った多段キャッシュで、頻繁にアクセスされるページの DB クエリを回避しています。Redis 未設定時はすべての操作が no-op になり、毎回 DB に直接アクセスします。

### キャッシュの種類と役割

| キャッシュ | Redis キー | 内容 | 対象 |
|---|---|---|---|
| トップ HTML | `twicome:index:html:{version}` | トップページのレンダリング済み HTML | 全ユーザ共通 |
| トップ landing データ | `twicome:index:landing` | 人気コメント等の JSON データ | 全ユーザ共通 |
| ユーザー一覧 | `twicome:index:users` | サジェスト用ユーザーリスト | 全ユーザ共通 |
| コメントページ HTML | `twicome:comments:html:{version}:{platform}:{login}` | ユーザーコメントページの初期 HTML | 全ユーザ |
| ユーザーメタ | `twicome:meta:{login}` | VOD 選択肢・配信者選択肢 | `QUICK_LINK_LOGINS` 設定ユーザのみ |

TTL はいずれも `COMMENTS_CACHE_TTL`（デフォルト 14,400秒 = 4時間）です。

### バージョンベースの自動無効化

`data_version` はキャッシュキーに埋め込まれており、バッチ更新後に値が変わると古いキャッシュキーは自然に参照されなくなります（TTL 切れを待つだけで不整合が解消されます）。

`data_version` の合成ルールは `{data_version}:{render_version}` です。

- `data_version`: Redis に保存されたバッチ更新タイムスタンプ
- `render_version`: `templates/` ・`static/sw.js` ・`routers/comments.py` のうち最も新しい mtime

テンプレートやルーターを更新してデプロイすると `render_version` が変わり、コード変更を含むページが古いキャッシュで返ることを防ぎます。

### コメントページ HTML キャッシュの適用条件

コメントページの HTML は **初期表示リクエスト**（フィルタなし・page=1・page_size=50・sort=created_at・cursor なし）のみキャッシュされます。フィルタや並び替えを変えたリクエストは毎回 DB から取得します。

### バッチ後のキャッシュ更新フロー

```
insertdb.py 完了
  → invalidate_cache.py
      - 古い HTML キャッシュを削除
      - QUICK_LINK_LOGINS のメタキャッシュを削除
      - data_version を現在時刻に更新
  → prewarm_index_cache.py
      - app の / に内部 GET を送信
      - 新バージョンのトップ HTML を Redis に事前構築
      - 次の実ユーザアクセス時はキャッシュヒットで即返却
```

`prewarm_index_cache.py` はバッチ完了直後にキャッシュを温めておくことで、バッチ直後のアクセスで DB への集中クエリが発生するのを防ぎます。

### Redis 未使用時の動作

`REDIS_URL` を設定しない場合、すべてのキャッシュ関数は no-op です。毎回 DB クエリが走るため、アクセス頻度が低い個人用途であれば Redis なしでも動作します。ただしバッチ直後のトップページ表示など重いクエリは毎回実行されます。

### ブラウザ側の先読み（Service Worker Prefetch）

サーバー側のキャッシュに加え、ブラウザの Service Worker（`static/sw.js`）がページ遷移前にコメントページ HTML を事前取得することで、クリックからページ表示までの待ち時間をほぼゼロにします。

**先読みのトリガー（複数条件）:**

| トリガー | タイミング | 対象 |
|---|---|---|
| ページロード時のアイドル処理 | `requestIdleCallback`（未対応環境は 150ms 後）| `QUICK_LINK_LOGINS` に設定された全ユーザ |
| クイックリンクへのホバー | `pointerenter` イベント | ホバーしたユーザ |
| クイックリンクへのフォーカス | `focus` イベント | フォーカスしたユーザ |
| 入力フォームでユーザが解決した時 | `input` / `focus` イベント後に解決できた場合 | 入力値に一致したユーザ |
| オンライン復帰時 | `online` イベント | `QUICK_LINK_LOGINS` に設定された全ユーザ |

**Service Worker 側のキャッシュ戦略（リクエスト種別ごと）:**

| リクエスト | 戦略 | 挙動 |
|---|---|---|
| トップページ (`/`) | キャッシュファースト + バックグラウンド再検証 | キャッシュを即返し、`data_version` が変わっていれば裏でフェッチして差し替え |
| コメントページ (`/u/{login}`) | キャッシュファースト + バックグラウンド更新 | キャッシュを即返し、裏で最新版を取得してキャッシュを更新 |
| ユーザー一覧 API | ネットワークファースト + キャッシュ保存 | 常にネットワーク取得し、失敗時はキャッシュ |
| 静的ファイル / Twitch CDN 画像 | キャッシュファースト | オフラインでも表示 |
| `/api/` 系 API | キャッシュなし | 常にネットワーク |

**先読みの実行フロー（ページロード時）:**

```
トップページ表示
  → Service Worker 登録
  → requestIdleCallback でプリフェッチキューを積む
  → Service Worker に twicome-prefetch-comments メッセージを送信
  → SW が /u/{login} を fetch して Cache API に保存
  → ユーザがリンクをクリック → Cache API ヒット → 即座に表示
```

Service Worker が利用できない環境では `server-warm-only` モードに自動フォールバックし（Redis 側のキャッシュのみ活用）、処理は中断しません。

### PWA 対応

`static/manifest.json` と Service Worker の組み合わせにより、モバイル・デスクトップ問わずホーム画面へのインストールが可能です。

| 設定項目 | 値 |
|---|---|
| アプリ名 | ツイコメ / Twicome |
| display | standalone（ブラウザ UI なし） |
| theme_color | `#9147ff`（Twitch 紫） |
| background_color | `#0e0e10`（Twitch 黒） |
| アイコン | 36px〜512px（Android / iOS / Windows タイル用） |

Service Worker の `install` イベントで `offline.html` とトップページを事前キャッシュするため、インストール直後からオフラインフォールバックが機能します。

### オフラインアクセス

一度アクセスしたページは Service Worker の Cache API に保存されるため、ネットワーク不通時でも閲覧できます。さらに「どのユーザのどのページを閲覧済みか」を `localStorage` に記録し、トップページの UI をオフライン状態に合わせて切り替えます。

**訪問履歴の記録（`offline-access.js`）:**

各ページを開くと `TwicomeOfflineAccess.markVisited()` が呼ばれ、ユーザー login とページ種別を `localStorage` に保存します。

| ページ | 保存されるルート種別 |
|---|---|
| `/u/{login}` コメント一覧 | `comments` |
| `/u/{login}/stats` 統計 | `stats` |
| `/u/{login}/quiz` クイズ | `quiz` |

保存先キー: `twicome:offline-accessible-routes:v1:{rootPath}`

**オフライン時のトップページの挙動:**

- `navigator.onLine === false` または `offline` イベントで `offlineMode = true` に切り替え
- 入力フォームの候補を「閲覧済みユーザのみ」に絞り込む
- 閲覧済みユーザ数を「オフライン中です。閲覧済みの N ユーザのみ候補に表示します。」と表示
- オンライン復帰（`online` イベント）でステータス表示を消してフル候補に戻す

**キャッシュ未ヒット時のフォールバック:**

Cache API にもないページ（一度も開いていないページ）にオフラインでアクセスすると、`static/offline.html` が表示されます。

### 投票カウントの遅延ロード

コメントページ HTML にはいいね・わるいねの件数が含まれており、そのままではキャッシュしたHTMLの内容が古くなります。そこで初期 HTML にはカウントを `0` で埋め込んでキャッシュを有効にしておき、ページ表示後に `POST /api/comments/votes` で現在のカウントを一括取得して DOM を書き換えます。

```
キャッシュ済みHTML を即返却（カウントは0表示）
  → DOMContentLoaded 後に /api/comments/votes へ POST（表示コメントIDを一括送信）
  → 取得した実カウントで DOM を差し替え
```

これにより「HTML キャッシュは常に有効」かつ「投票数は常に最新」という両立を実現しています。

## 大規模配信者データ取り込み時の考察

### 現在の運用規模（2026年3月時点の実測値）

| 指標 | 実測値 |
|---|---|
| 監視対象配信者数 | 31名 |
| 総 VOD 数 | 1,317本 |
| 総コメント数 | 約88万件 |
| comments テーブル（data）| 1,812MB |
| comments テーブル（index）| 730MB |
| comments テーブル合計 | **約2.5GB** |
| 1コメントあたり raw_json | 平均971バイト |
| 1コメントあたり body | 平均42バイト |
| 1コメントあたり body_html | 平均190バイト |

**コンテナメモリ使用量（docker stats 実測）:**

| コンテナ | 使用メモリ |
|---|---|
| app (FastAPI + Uvicorn) | 159MB |
| faiss-api (モデル + インデックス含む) | 499MB |
| db (MySQL 8.0) | 481MB |
| redis | 15MB |

### Twitch コメント量の目安

配信規模によるコメント数の概算（8時間配信の場合）:

| 同時視聴者数 | 1配信あたりコメント数 | 備考 |
|---|---|---|
| 〜500人 | 数千〜1万件 | 本システム監視対象の標準規模 |
| 1,000〜5,000人 | 1〜5万件 | 中規模 |
| 1万〜5万人 | 5〜30万件 | 大規模（国内有名配信者） |
| 10万人以上 | 50万〜数百万件 | 超大規模（海外有名配信者） |

現在の最多コメント保有ユーザは **90,533件**、最多 VOD 保有配信者は **220,228コメント / 118 VOD** です。

### クエリ性能の実測（最多コメンター: 90,533件）

| クエリ | 実測時間 | 判定 |
|---|---|---|
| 初期表示（サブクエリ最適化版）| **2ms** | ✅ 問題なし |
| `COUNT(*)` 単純 | 42ms | ✅ 問題なし |
| `COUNT(*)` + owner フィルタ | 50ms | ✅ 問題なし |
| `ORDER BY RAND() LIMIT 1` | 61ms | ✅ 問題なし |
| `COUNT(*) + LIKE '%草%'` | **2.4秒** | ⚠️ 遅い |

テキスト検索（`LIKE '%q%'`）がボトルネックです。現状90,533件で2.4秒かかるため、コメント数が多い著名配信者のファン（コメント数が数十万件規模）を検索すると、体感できる遅延や HTTP タイムアウトが発生します。

### FAISS インデックスの実測

現在インデックス済みは1ユーザ（13,074件）のみです。

| 指標 | 実測値 |
|---|---|
| インデックスファイルサイズ | 52MB / 13,074件（≈4KB/件） |
| faiss-api 内部の検索レイテンシ | **3〜7ms** |

ファイルサイズから外挿すると、コメント数とインデックスサイズの関係は以下の通りです。
faiss-api は起動時にインデックスをすべてメモリに展開します。

| コメント数 | インデックスファイルサイズ目安 | faiss-api 追加メモリ目安 |
|---|---|---|
| 1万件 | 約40MB | 約40MB |
| 10万件 | 約400MB | 約400MB |
| 50万件 | 約2GB | 約2GB |
| 全ユーザ合計（現在の88万件規模）| 約3.5GB | 約3.5GB |

現在の faiss-api は 499MB（うちモデルが約300MB 程度）で動作しています。インデックス済みユーザが増えるほどメモリ使用量は線形に増加します。

検索レイテンシは `IndexFlatIP` の全件スキャンのため O(n) です。13,074件で 3〜7ms なので、件数が10倍になれば30〜70ms が目安です。

### 有名配信者を追加した場合のシミュレーション

例として「1万同接クラスの配信者を1名追加（1配信10万コメント × 30 VOD = 300万コメント）」を想定すると：

| 影響 | 試算 |
|---|---|
| DB 追加容量 | 300万 × 971B ≈ 約3GB |
| insertdb.py 処理時間（1 VOD 10万件）| 現状 1万件/分の処理速度と仮定すると約10分/VOD |
| FAISS インデックスサイズ（300万件）| 約12GB（faiss-api に12GB以上の空きメモリが必要） |
| LIKE テキスト検索レイテンシ | 90,533件で2.4秒 → 300万件で約80秒（タイムアウト） |

この規模になると `LIKE '%q%'` 検索と FAISS の `IndexFlatIP` が現実的に使えなくなります。

### 判断基準と測定方法

定期的に以下を確認することで、限界に近づく前に対処できます。

**DB の状況確認:**

```sql
-- テーブルサイズと行数
SELECT table_name,
  table_rows,
  ROUND(data_length / 1024 / 1024, 1) AS data_MB,
  ROUND(index_length / 1024 / 1024, 1) AS index_MB
FROM information_schema.tables
WHERE table_schema = 'appdb'
ORDER BY (data_length + index_length) DESC;

-- コメントが多いユーザー TOP10
SELECT commenter_login_snapshot, COUNT(*) AS cnt
FROM comments
GROUP BY commenter_login_snapshot
ORDER BY cnt DESC LIMIT 10;

-- LIKE 検索の実測（対象ユーザの user_id を入れて計測）
SET profiling = 1;
SELECT COUNT(*) FROM comments
WHERE commenter_user_id = <uid> AND body LIKE '%草%';
SHOW PROFILES;
```

**FAISS の状況確認:**

```bash
# インデックスファイルサイズ
docker compose exec faiss-api du -sh /app/data/faiss_data/

# faiss-api のメモリ使用量
docker stats --no-stream twicome-faiss-api-1
```

**対処のトリガー目安:**

| 指標 | 閾値 | 対処 |
|---|---|---|
| LIKE テキスト検索 | > 3秒 | MySQL 全文検索（FULLTEXT INDEX）への移行を検討 |
| FAISS 検索レイテンシ | > 200ms | `IndexIVFFlat` への移行を検討 |
| faiss-api メモリ | > 利用可能 RAM の 60% | インデックス対象ユーザを絞るか、メモリ増強 |
| comments テーブル合計 | > 20GB | `raw_json` カラムの削除または別テーブル分離を検討 |
| insertdb.py（1 VOD）| > 4時間 | バッチ間隔の見直しまたは並列化を検討 |

#### 有名配信者を追加する前のチェックリスト

- [ ] 対象配信者の過去 VOD 本数と平均コメント数を事前に把握する
- [ ] `raw_json` 容量影響をストレージ残量と比較する（1コメント≈1KB として試算）
- [ ] 全 VOD の初回取り込みは `insertdb.py` を別途手動実行し、完了を確認してからバッチに組み込む
- [ ] `build_faiss_index.py` 後に faiss-api のメモリ使用量が想定範囲内か `docker stats` で確認する
- [ ] 追加後に対象コメンターへの LIKE 検索レイテンシを実測する

## 開発メモ

このプロジェクトは、Kilo / Claude Code / Codex CLI を含む LLM を活用して開発されています。
