#!/usr/bin/env bash
#
# 本番環境のデータベースを mysqldump でバックアップする。
# 出力先: backup/db/twicome_db_backup_YYYYMMDD_HHMMSS.sql
#
# DB はホストへ公開されていないため、docker-compose.yml の db サービス内で
# mysqldump を実行してダンプを取得する。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${ROOT_DIR}/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"
BACKUP_DIR="${BACKUP_DIR:-${ROOT_DIR}/backup/db}"

usage() {
    cat <<'EOF'
Usage: ./backup_db.sh [--env-file PATH]

本番環境(docker-compose.yml の db サービス)のデータベースをバックアップする。
出力先: backup/db/twicome_db_backup_YYYYMMDD_HHMMSS.sql

Options:
  --env-file PATH   DB 接続情報を読み込む env ファイル (既定: ./.env)
  -h, --help        このヘルプを表示
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --env-file)
            if [ -z "${2:-}" ]; then
                echo "Error: --env-file requires a path" >&2
                exit 1
            fi
            ENV_FILE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: unknown argument: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [ "${ENV_FILE#/}" = "${ENV_FILE}" ]; then
    ENV_FILE="${ROOT_DIR}/${ENV_FILE}"
fi

if [ ! -f "${ENV_FILE}" ]; then
    echo "Error: env file not found: ${ENV_FILE}" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

# docker-compose.yml の既定値に合わせてフォールバックする
MYSQL_USER="${COMPOSE_MYSQL_USER:-${MYSQL_USER:-appuser}}"
MYSQL_PASSWORD="${COMPOSE_MYSQL_PASSWORD:-${MYSQL_PASSWORD:-apppass}}"
MYSQL_DATABASE="${COMPOSE_MYSQL_DATABASE:-${MYSQL_DATABASE:-appdb}}"

mkdir -p "${BACKUP_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_FILE="${BACKUP_DIR}/twicome_db_backup_${TIMESTAMP}.sql"

echo "Backing up database '${MYSQL_DATABASE}' to ${OUTPUT_FILE} ..."

# db コンテナ内で mysqldump を実行。--no-tty で TTY 割り当てを避け、出力を直接ファイルへ。
if ! docker compose -f "${COMPOSE_FILE}" exec -T \
    -e MYSQL_PWD="${MYSQL_PASSWORD}" \
    db \
    mysqldump \
        --single-transaction \
        --quick \
        --routines \
        --triggers \
        --no-tablespaces \
        --default-character-set=utf8mb4 \
        -u"${MYSQL_USER}" \
        "${MYSQL_DATABASE}" \
    > "${OUTPUT_FILE}"; then
    echo "Error: mysqldump failed" >&2
    rm -f "${OUTPUT_FILE}"
    exit 1
fi

echo "Backup completed: ${OUTPUT_FILE} ($(du -h "${OUTPUT_FILE}" | cut -f1))"
