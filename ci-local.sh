#!/usr/bin/env bash
# ci-local.sh - GitHub Actions CI をローカルで再現するスクリプト
#
# 使い方:
#   ./ci-local.sh                 全ステップを実行
#   ./ci-local.sh --fail-fast     最初の失敗で即停止
#   ./ci-local.sh --skip-ui       UI テスト (Playwright) をスキップ
#   ./ci-local.sh compile lint-py 指定したステップのみ実行
#
# 利用可能なステップ名:
#   compile, lint-py, lint-format, lint-html, lint-js,
#   db-migrate, unit, integration, ui
#
# 環境:
#   docker compose -f docker-compose.dev.yml が前提
#   DB は自動起動される（既存の dev DB があれば共用）

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DC="docker compose -f docker-compose.dev.yml"

# ── オプション解析 ────────────────────────────────────────────────────────
FAIL_FAST=0
SKIP_UI=0
FILTER=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--fail-fast) FAIL_FAST=1 ;;
        --skip-ui)      SKIP_UI=1 ;;
        -h|--help)
            sed -n 's/^# //p' "$0" | head -20
            exit 0
            ;;
        -*) echo "不明なオプション: $1" >&2; exit 1 ;;
        *)  FILTER+=("$1") ;;
    esac
    shift
done

# ── カラー定義 ────────────────────────────────────────────────────────────
R='\033[0;31m' G='\033[0;32m' B='\033[0;34m' W='\033[1m' N='\033[0m'

# ── 結果トラッキング ──────────────────────────────────────────────────────
NAMES=()
declare -A ST SEC
T0=$(date +%s)

_should_run() {
    [[ ${#FILTER[@]} -eq 0 ]] && return 0
    for f in "${FILTER[@]}"; do [[ "$1" == "$f" ]] && return 0; done
    return 1
}

step() {
    local name=$1; shift
    _should_run "$name" || return 0
    NAMES+=("$name")
    echo -e "\n${W}${B}▶ [$name]${N}"
    local t; t=$(date +%s)
    if "$@"; then
        SEC[$name]=$(( $(date +%s) - t ))
        ST[$name]=OK
        echo -e "${G}✓ $name (${SEC[$name]}s)${N}"
    else
        SEC[$name]=$(( $(date +%s) - t ))
        ST[$name]=NG
        echo -e "${R}✗ $name (${SEC[$name]}s)${N}"
        if [[ $FAIL_FAST -eq 1 ]]; then
            _summary
            exit 1
        fi
    fi
}

_summary() {
    local total=$(( $(date +%s) - T0 ))
    echo -e "\n${W}==${N}"
    echo -e "${W}  CI ローカル サマリー  (合計: ${total}s)${N}"
    echo -e "${W}==${N}"
    local ok=1
    for n in "${NAMES[@]}"; do
        if [[ "${ST[$n]}" == OK ]]; then
            printf "  ${G}✓${N}  %-28s %ss\n" "$n" "${SEC[$n]}"
        else
            printf "  ${R}✗${N}  %-28s %ss\n" "$n" "${SEC[$n]}"
            ok=0
        fi
    done
    echo ""
    if [[ $ok -eq 1 ]]; then
        echo -e "${G}${W}  All checks passed!${N}"
    else
        echo -e "${R}${W}  Some checks failed.${N}"
        return 1
    fi
}

# ── Step 実装 ─────────────────────────────────────────────────────────────

do_compile() {
    python3 - <<'PY'
from pathlib import Path
roots = ["app", "batch", "migrate", "util", "mcp-server", "faiss-api"]
count, errors = 0, []
for r in roots:
    p = Path(r)
    if not p.exists():
        continue
    for f in p.rglob("*.py"):
        count += 1
        try:
            compile(f.read_text(encoding="utf-8"), str(f), "exec")
        except Exception as e:
            errors.append(f"{f}: {e}")
if errors:
    raise SystemExit("\n".join(errors))
print(f"syntax compile ok: {count} files")
PY
}

do_lint_py() {
    $DC --profile lint run --rm lint
}

do_lint_format() {
    $DC --profile lint run --rm lint ruff format . --check
}

do_lint_html() {
    $DC --profile lint run --rm lint-html
}

do_lint_js() {
    $DC --profile lint run --rm lint-js
}

do_db_migrate() {
    echo "DB 起動 + appdb_dev マイグレーション..."
    # migrate サービスが depends_on で db を待ってから実行される
    $DC run --rm migrate

    echo "appdb_test マイグレーション..."
    # db の healthcheck が appdb_test を作成済み; migrate は冪等
    $DC run --rm \
        -e DATABASE_URL="mysql+pymysql://appuser:apppass@db:3306/appdb_test?charset=utf8mb4" \
        migrate
}

do_unit() {
    $DC --profile test run --rm \
        -e COVERAGE_FILE=.coverage.unit \
        test pytest tests/unit -v
}

do_integration() {
    $DC --profile test run --rm \
        -e COVERAGE_FILE=.coverage.integration \
        test pytest tests/integration -v
}

do_ui() {
    $DC --profile test-ui run --rm test-ui
}

# ── 実行 ──────────────────────────────────────────────────────────────────

step compile      do_compile
step lint-py      do_lint_py
step lint-format  do_lint_format
step lint-html    do_lint_html
step lint-js      do_lint_js
step db-migrate   do_db_migrate
step unit         do_unit
step integration  do_integration
[[ $SKIP_UI -eq 0 ]] && step ui do_ui

_summary
