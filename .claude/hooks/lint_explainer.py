#!/usr/bin/env python3
"""
lint_explainer.py  <linter>
  stdin : linter の JSON 出力 (ruff/eslint/stylelint) or テキスト (djlint)
  stdout: ERROR/WHY/FIX/EXAMPLE を付加した整形済み出力

使い方例:
  ruff check --output-format json file.py | python3 lint_explainer.py ruff
"""

import json
import re
import sys
from pathlib import Path


RULES_FILE = Path(__file__).parent.parent / "lint-rules.json"
SEVERITY_LABEL = {"error": "ERROR", "warning": "WARN ", 1: "WARN ", 2: "ERROR"}


def load_rules(linter: str) -> dict:
    if RULES_FILE.exists():
        data = json.loads(RULES_FILE.read_text())
        return data.get(linter, {})
    return {}


def format_explanation(rule: dict) -> list[str]:
    lines = []
    if why := rule.get("why"):
        lines.append(f"  WHY:     {why}")
    if fix := rule.get("fix"):
        lines.append(f"  FIX:     {fix}")
    if adr := rule.get("adr"):
        lines.append(f"  ADR:     {adr}")
    if example := rule.get("example"):
        lines.append("  EXAMPLE:")
        for ex in example.split("\n"):
            lines.append(f"    {ex}")
    return lines


def explain_ruff(raw: str, rules: dict) -> bool:
    """ruff --output-format json を整形して出力。エラーあれば True を返す"""
    try:
        issues = json.loads(raw)
    except json.JSONDecodeError:
        print(raw)
        return False

    if not issues:
        print("  ruff: All checks passed!")
        return False

    for issue in issues:
        code = issue.get("code", "?")
        msg = issue.get("message", "")
        loc = issue.get("location", {})
        row, col = loc.get("row", "?"), loc.get("column", "?")
        print(f"  ERROR: [{code}] line {row}:{col}  {msg}")
        if rule := rules.get(code):
            for line in format_explanation(rule):
                print(line)
        print()

    return True


def explain_eslint(raw: str, rules: dict) -> bool:
    """eslint --format json を整形して出力。エラーあれば True を返す"""
    try:
        files = json.loads(raw)
    except json.JSONDecodeError:
        print(raw)
        return False

    has_issues = False
    for file_result in files:
        for msg in file_result.get("messages", []):
            rule_id = msg.get("ruleId", "?")
            severity = msg.get("severity", 1)
            text = msg.get("message", "")
            line, col = msg.get("line", "?"), msg.get("column", "?")
            label = SEVERITY_LABEL.get(severity, "WARN ")
            print(f"  {label}: [{rule_id}] line {line}:{col}  {text}")
            if rule := rules.get(rule_id):
                for expl in format_explanation(rule):
                    print(expl)
            print()
            has_issues = True

    if not has_issues:
        print("  eslint: All checks passed!")

    return has_issues


def explain_stylelint(raw: str, rules: dict) -> bool:
    """stylelint --formatter json を整形して出力。エラーあれば True を返す"""
    try:
        files = json.loads(raw)
    except json.JSONDecodeError:
        print(raw)
        return False

    has_issues = False
    for file_result in files:
        for warn in file_result.get("warnings", []):
            rule_id = warn.get("rule", "?")
            severity = warn.get("severity", "warning")
            text = warn.get("text", "").removesuffix(f" ({rule_id})")
            line, col = warn.get("line", "?"), warn.get("column", "?")
            label = "ERROR" if severity == "error" else "WARN "
            print(f"  {label}: [{rule_id}] line {line}:{col}  {text}")
            if rule := rules.get(rule_id):
                for expl in format_explanation(rule):
                    print(expl)
            print()
            has_issues = True

    if not has_issues:
        print("  stylelint: All checks passed!")

    return has_issues


def explain_djlint(raw: str, rules: dict) -> bool:
    """djlint のテキスト出力をパースして整形。エラーあれば True を返す"""
    # djlint 出力例: "W019 1:1 Some message."
    pattern = re.compile(r"^([A-Z]\d+)\s+(\d+):(\d+)\s+(.*)$")
    has_issues = False

    for line in raw.splitlines():
        m = pattern.match(line.strip())
        if not m:
            if line.strip():
                print(f"  {line}")
            continue

        code, row, col, msg = m.groups()
        severity = "WARN " if code.startswith("W") else "ERROR"
        print(f"  {severity}: [{code}] line {row}:{col}  {msg}")
        if rule := rules.get(code):
            for expl in format_explanation(rule):
                print(expl)
        print()
        has_issues = True

    if not has_issues:
        print("  djlint: All checks passed!")

    return has_issues


def main():
    linter = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    rules = load_rules(linter)
    raw = sys.stdin.read()

    dispatch = {
        "ruff": explain_ruff,
        "eslint": explain_eslint,
        "stylelint": explain_stylelint,
        "djlint": explain_djlint,
    }

    fn = dispatch.get(linter)
    if fn:
        fn(raw, rules)
    else:
        print(raw)


if __name__ == "__main__":
    main()
