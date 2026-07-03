"""AST 正規化ハッシュによる Python 関数クローンの棚卸しツール（non-blocking）。

同名 grep ベースの CI ガード（check-duplication.sh 予定）が捕まえられない
「改名クローン」も含めて検出する。月次棚卸し用であり、CI を fail させない。
使い方・位置づけは docs/duplication-verification-and-critique.md §2 を参照。

    python3 ci/clone_scan.py [走査ルート ...]
"""

import ast
import collections
import hashlib
import os
import sys

DEFAULT_ROOTS = [
    "app",
    "batch",
    "util",
    "migrate",
    "morpheme-sample",
    "faiss-api",
    "morpheme-api",
    "twicome-mcp-server",
    "challenge",
]

# 外部コード・生成物は対象外（.venv は challenge/ 配下等ルート直下以外にもある）
EXCLUDED_DIR_NAMES = {".git", ".venv", "node_modules", "__pycache__", "versions"}

# この文数未満の関数は定型文とみなして無視（偽陽性抑制）
MIN_BODY_STATEMENTS = 4


class _Normalizer(ast.NodeTransformer):
    """識別子と文字列リテラルを匿名化し、構造だけを残す。"""

    def visit_Name(self, node: ast.Name) -> ast.Name:
        node.id = "_N_"
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = "_A_"
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if isinstance(node.value, str) and node.value:
            node.value = "_S_"
        return node


def _iter_python_files(roots: list[str]):
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIR_NAMES]
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


def _function_hash(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    body = ast.Module(body=node.body, type_ignores=[])
    normalized = _Normalizer().visit(ast.parse(ast.unparse(body)))
    return hashlib.md5(ast.dump(normalized).encode()).hexdigest()[:10]


def scan(roots: list[str]) -> tuple[int, dict[str, list[tuple[str, str, int]]]]:
    """指定ルート以下の全 Python 関数を正規化ハッシュでグループ化して返す。"""
    groups: dict[str, list[tuple[str, str, int]]] = collections.defaultdict(list)
    scanned = 0
    for path in _iter_python_files(roots):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except (SyntaxError, UnicodeDecodeError) as exc:
            print(f"parse fail: {path}: {exc}", file=sys.stderr)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and len(node.body) >= MIN_BODY_STATEMENTS:
                scanned += 1
                groups[_function_hash(node)].append((path, node.name, node.lineno))
    return scanned, groups


def main() -> None:
    """走査を実行し、2ファイル以上にまたがるクローングループを一覧表示する。"""
    roots = sys.argv[1:] or [r for r in DEFAULT_ROOTS if os.path.isdir(r)]
    scanned, groups = scan(roots)
    print(f"scanned {scanned} functions (>= {MIN_BODY_STATEMENTS} statements) under: {' '.join(roots)}")
    found = 0
    for items in sorted(groups.values()):
        files = {p for p, _, _ in items}
        if len(files) < 2:
            continue
        names = {n for _, n, _ in items}
        tag = "RENAMED" if len(names) > 1 else "same-name"
        found += 1
        print(f"[{tag}]")
        for path, name, lineno in items:
            print(f"   {path}:{lineno} {name}")
    print(f"{found} cross-file clone group(s) found")


if __name__ == "__main__":
    main()
