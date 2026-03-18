#!/usr/bin/env bash
# PostToolUse hook: run lint on the file just written/edited by Claude

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
EXPLAINER="$ROOT/.claude/hooks/lint_explainer.py"

# Parse file_path from stdin JSON
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('file_path', ''))
" 2>/dev/null)

# Skip if no file path
if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Convert relative path to absolute
if [[ "$FILE_PATH" != /* ]]; then
    FILE_PATH="$ROOT/$FILE_PATH"
fi

# Skip if outside project
if [[ "$FILE_PATH" != "$ROOT"* ]]; then
    exit 0
fi

EXT="${FILE_PATH##*.}"
REL_PATH="${FILE_PATH#$ROOT/}"

# run_and_explain: linter errors go to stderr (exit 2) so Claude receives them as feedback
run_and_explain() {
    local linter="$1"; shift
    local output exit_code
    output=$("$@" 2>&1)
    exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo "$output" | python3 "$EXPLAINER" "$linter" >&2
        return 2
    else
        echo "$output" | python3 "$EXPLAINER" "$linter"
        return 0
    fi
}

case "$EXT" in
    py)
        echo "[lint] ruff: $REL_PATH" >&2
        run_and_explain ruff \
            "$ROOT/.venv/bin/ruff" check --no-cache --output-format json "$FILE_PATH"
        ;;
    html)
        echo "[lint] djlint: $REL_PATH" >&2
        output=$("$ROOT/.venv/bin/djlint" "$FILE_PATH" --lint --warn 2>&1)
        exit_code=$?
        if [ $exit_code -ne 0 ]; then
            echo "$output" | python3 "$EXPLAINER" djlint >&2
            exit 2
        else
            echo "$output" | python3 "$EXPLAINER" djlint
        fi
        ;;
    js)
        echo "[lint] eslint: $REL_PATH" >&2
        cd "$ROOT"
        run_and_explain eslint \
            ./node_modules/.bin/eslint --format json "$REL_PATH"
        ;;
    css)
        echo "[lint] stylelint: $REL_PATH" >&2
        cd "$ROOT"
        run_and_explain stylelint \
            ./node_modules/.bin/stylelint --formatter json "$REL_PATH"
        ;;
    *)
        exit 0
        ;;
esac
