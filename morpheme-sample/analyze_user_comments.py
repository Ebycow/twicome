"""指定ユーザのコメントを形態素解析して標準出力に表示するサンプル

DBへの書き込みは行わない。

Usage:
    python analyze_user_comments.py --user <username>
    python analyze_user_comments.py --user <username> --mode A --limit 20
    python analyze_user_comments.py --user <username> --limit 5 --output json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import mysql.connector
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env.development"
load_dotenv(str(ENV_PATH))

MORPHEME_API_URL = os.getenv("MORPHEME_API_URL", "http://localhost:8200").rstrip("/")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "appuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "apppass")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "appdb_dev")

CHUNK_SIZE = 100


def fetch_comments(conn, user_login: str, limit: int | None) -> list[dict]:
    """指定ユーザのコメントをDBから取得する。"""
    cur = conn.cursor(dictionary=True)
    query = """
        SELECT c.comment_id, c.body, c.comment_created_at_utc
        FROM comments c
        JOIN users u ON u.user_id = c.commenter_user_id
        WHERE u.login = %s AND u.platform = 'twitch'
          AND c.body IS NOT NULL AND c.body != ''
        ORDER BY c.comment_created_at_utc DESC
    """
    params: list = [user_login]
    if limit:
        query += " LIMIT %s"
        params.append(limit)
    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def call_analyze_api(texts: list[str], mode: str) -> list[list[dict]]:
    """morpheme-api の /analyze を呼び出す。"""
    resp = requests.post(
        f"{MORPHEME_API_URL}/analyze",
        json={"texts": texts, "mode": mode},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["results"]


def print_text(comments: list[dict], results: list[list[dict]]) -> None:
    """形態素解析結果をテキスト形式で出力する。"""
    for comment, morphemes in zip(comments, results, strict=True):
        print(f"\n--- [{comment['comment_created_at_utc']}] {comment['comment_id']} ---")
        print(f"本文: {comment['body']}")
        print("形態素:")
        for m in morphemes:
            line = (
                f"  {m['surface']!r:16s}  品詞={m['pos']}({m['pos_detail']})"
                f"  読み={m['reading']}  基本形={m['base_form']}"
            )
            print(line)


def print_json(comments: list[dict], results: list[list[dict]]) -> None:
    """形態素解析結果を JSON 形式で出力する。"""
    output = []
    for comment, morphemes in zip(comments, results, strict=True):
        output.append(
            {
                "comment_id": comment["comment_id"],
                "created_at": str(comment["comment_created_at_utc"]),
                "body": comment["body"],
                "morphemes": morphemes,
            }
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


def main() -> None:
    """エントリーポイント。"""
    parser = argparse.ArgumentParser(description="指定ユーザのコメントを形態素解析して表示する")
    parser.add_argument("--user", required=True, help="Twitch ログイン名")
    parser.add_argument("--mode", choices=["A", "B", "C"], default="C", help="分割モード (default: C)")
    parser.add_argument("--limit", type=int, default=None, help="取得件数 (default: 全件)")
    parser.add_argument(
        "--output", choices=["text", "json"], default=None, help="形態素を出力する場合に指定 (text or json)"
    )
    args = parser.parse_args()

    try:
        resp = requests.get(f"{MORPHEME_API_URL}/health", timeout=10)
        resp.raise_for_status()
        print(f"morpheme-api: {resp.json()}", file=sys.stderr)
    except Exception as e:
        print(f"morpheme-api に接続できません ({MORPHEME_API_URL}): {e}", file=sys.stderr)
        sys.exit(1)

    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )
    try:
        comments = fetch_comments(conn, args.user, args.limit)
    finally:
        conn.close()

    if not comments:
        print(f"ユーザ '{args.user}' のコメントが見つかりません。", file=sys.stderr)
        sys.exit(0)

    print(f"{len(comments)} 件取得 (user={args.user}, mode={args.mode})", file=sys.stderr)

    all_morphemes: list[list[dict]] = []
    t_start = time.perf_counter()
    for i in range(0, len(comments), CHUNK_SIZE):
        chunk = comments[i : i + CHUNK_SIZE]
        texts = [c["body"] for c in chunk]
        all_morphemes.extend(call_analyze_api(texts, args.mode))
        elapsed = time.perf_counter() - t_start
        done = i + len(chunk)
        print(f"  {done}/{len(comments)} 件解析済み ({elapsed:.1f}s)", file=sys.stderr)

    total = time.perf_counter() - t_start
    print(
        f"完了: {len(comments)} 件 / {total:.2f}s ({len(comments) / total:.1f} 件/s)",
        file=sys.stderr,
    )

    if args.output == "json":
        print_json(comments, all_morphemes)
    elif args.output == "text":
        print_text(comments, all_morphemes)


if __name__ == "__main__":
    main()
