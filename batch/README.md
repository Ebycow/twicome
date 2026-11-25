# Batch scripts

`run_batch.sh` が実行するバッチ処理用スクリプトを `batch/scripts/` に集約しています。

1. `get_vod_list_batch.py` — `targetusers.csv` の配信者の VOD 一覧を取得
2. `batch_download_comments.py` — チャットをダウンロードし、収集対象ユーザーを含む VOD だけ `<vod_id>.json.gz` で保存
3. `insertdb.py` — 収集対象ユーザーのコメントだけを DB に投入
4. `prune_non_targets.py` — 対象外ユーザーのコメント、コメントの無くなった VOD、不要なユーザー行を削除

収集対象ユーザーは `QUICK_LINK_LOGINS` と `DEFAULT_LOGIN` の和集合（判定ロジックは `collect_targets.py`）。
どちらも空の場合、2〜4 はエラーで停止する。

対象ユーザーを含まない VOD は `COMMENTS_DIR/no_target_vods.tsv` に「VOD ID と判定時の対象ログイン一覧」を記録し、
次回以降はダウンロードしない。対象ユーザーを追加した場合は、その VOD を再ダウンロードして判定し直す。

`run_batch.sh` は `PROJECT_ROOT` を環境変数として渡すため、各スクリプトはカレントディレクトリに依存せず動作します。
コメントJSONだけを一括投入したい場合は、リポジトリルートの `run_import_comments.sh` を使えます。

コメント取得に使う `TwitchDownloaderCLI` は `library/TwitchDownloaderCLI` を既定で参照します。
別パスを使う場合は `TWITCH_DOWNLOADER_CLI` で上書きできます。
ライセンス情報はリポジトリルートの `COPYRIGHT.txt` と `THIRD-PARTY-LICENSES.txt` を参照してください。

## 環境ごとのデータ分離

`run_batch.sh` は `APP_ENV` と `BATCH_DATA_DIR` で入出力先を切り替えられます。
また、既定で `${PROJECT_ROOT}/.env` を読み込み、`--env-file` で別のenvファイルを指定できます。

- `APP_ENV` 既定値: `development`
- `BATCH_DATA_DIR` 既定値: `${PROJECT_ROOT}/data/${APP_ENV}`
- `TARGET_USERS_CSV`:
  - `${BATCH_DATA_DIR}/targetusers.csv` が存在すればそれを使用
  - 無ければ `${PROJECT_ROOT}/targetusers.csv` を使用（後方互換）
- `VODS_CSV` 既定値: `${BATCH_DATA_DIR}/batch_twitch_vods_all.csv`
- `COMMENTS_DIR` 既定値: `${BATCH_DATA_DIR}/comments`
- `LOG_DIR` 既定値: `${BATCH_DATA_DIR}/logs`
- `LOG_RETENTION_DAYS` 既定値: `14`（Docker の entrypoint のみ。これより古い `batch_*.log` を削除）

例:

```bash
APP_ENV=staging BATCH_DATA_DIR=/srv/twicome/staging-data ./run_batch.sh
```

```bash
./run_batch.sh --env-file .env.honban
```

```bash
ENV_FILE=.env.staging ./run_batch.sh
```

## コメントJSONの全投入（既存ファイルから）

`run_import_comments.sh` は `batch/scripts/insertdb.py` を単独実行するためのランナーです。
`data/honban/comments` のような既存コメントファイル（`.json` / `.json.gz`）から、収集対象ユーザーのコメントだけを DB へ投入できます。

例:

```bash
./run_import_comments.sh --env-file .env.development --comments-dir data/honban/comments
```

既存VODも再処理したい場合（中断復帰や再投入時）:

```bash
./run_import_comments.sh --env-file .env.development --comments-dir data/honban/comments --reingest-existing-vods
```
