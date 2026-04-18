"""形態素解析バッチスクリプト

morpheme-api を使って comments テーブルのコメントを形態素解析し、
結果を comment_morphemes テーブルに保存する。
未処理のコメントのみを対象にする（差分更新）。

Usage:
    python analyze_morphemes.py              # 全コメント（モード C）
    python analyze_morphemes.py --mode A     # モード A で実行
    python analyze_morphemes.py --user akio8517  # 特定ユーザのみ
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import mysql.connector
import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
ENV_PATH = Path(os.getenv("ENV_FILE", str(PROJECT_ROOT / ".env")))
if not ENV_PATH.is_absolute():
    ENV_PATH = PROJECT_ROOT / ENV_PATH
load_dotenv(str(ENV_PATH))

MORPHEME_API_URL = os.getenv("MORPHEME_API_URL", "").strip().rstrip("/")
if not MORPHEME_API_URL:
    print("MORPHEME_API_URL が設定されていません。")
    sys.exit(1)

MYSQL_HOST = os.getenv("MYSQL_HOST", "db")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "appuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
if not MYSQL_PASSWORD:
    raise RuntimeError("MYSQL_PASSWORD が設定されていません。")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "appdb")

CHUNK_SIZE = 500


def fetch_unanalyzed_ids(conn, mode: str, user_login: str | None) -> list[str]:
    """comment_morphemes に未登録のコメントIDを返す。"""
    cur = conn.cursor()
    if user_login:
        cur.execute(
            """
            SELECT c.comment_id
            FROM comments c
            JOIN users u ON u.user_id = c.commenter_user_id
            WHERE u.login = %s AND u.platform = 'twitch'
              AND c.body IS NOT NULL AND c.body != ''
              AND NOT EXISTS (
                  SELECT 1 FROM comment_morphemes m
                  WHERE m.comment_id = c.comment_id AND m.mode = %s
              )
            ORDER BY c.comment_id
            """,
            (user_login, mode),
        )
    else:
        cur.execute(
            """
            SELECT c.comment_id
            FROM comments c
            WHERE c.body IS NOT NULL AND c.body != ''
              AND NOT EXISTS (
                  SELECT 1 FROM comment_morphemes m
                  WHERE m.comment_id = c.comment_id AND m.mode = %s
              )
            ORDER BY c.comment_id
            """,
            (mode,),
        )
    ids = [row[0] for row in cur.fetchall()]
    cur.close()
    return ids


def fetch_bodies(conn, ids: list[str]) -> dict[str, str]:
    """コメントIDからbodyテキストを取得する。"""
    if not ids:
        return {}
    placeholders = ",".join(["%s"] * len(ids))
    cur = conn.cursor(dictionary=True)
    cur.execute(f"SELECT comment_id, body FROM comments WHERE comment_id IN ({placeholders})", ids)
    result = {row["comment_id"]: row["body"] for row in cur.fetchall()}
    cur.close()
    return result


def call_analyze_api(texts: list[str], mode: str) -> list[list[dict]]:
    """morpheme-api の /analyze を呼び出す。"""
    resp = requests.post(
        f"{MORPHEME_API_URL}/analyze",
        json={"texts": texts, "mode": mode},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["results"]


def insert_morphemes(conn, rows: list[tuple]) -> None:
    """comment_morphemes にバルクインサートする。rows: [(comment_id, mode, tokens_json, analyzed_at)]"""
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO comment_morphemes (comment_id, mode, tokens, analyzed_at)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE tokens = VALUES(tokens), analyzed_at = VALUES(analyzed_at)
        """,
        rows,
    )
    conn.commit()
    cur.close()


def process(conn, mode: str, user_login: str | None) -> None:
    """未解析コメントをチャンク処理する。"""
    print(f"未解析コメントIDを取得中... (mode={mode}{'、user=' + user_login if user_login else ''})")
    unanalyzed_ids = fetch_unanalyzed_ids(conn, mode, user_login)
    print(f"未解析: {len(unanalyzed_ids)} 件")

    if not unanalyzed_ids:
        print("処理対象なし、終了。")
        return

    total_chunks = (len(unanalyzed_ids) + CHUNK_SIZE - 1) // CHUNK_SIZE
    total_inserted = 0

    for i in range(0, len(unanalyzed_ids), CHUNK_SIZE):
        chunk_ids = unanalyzed_ids[i : i + CHUNK_SIZE]
        chunk_num = i // CHUNK_SIZE + 1

        bodies = fetch_bodies(conn, chunk_ids)
        ordered_ids = [cid for cid in chunk_ids if cid in bodies]
        texts = [bodies[cid] for cid in ordered_ids]

        if not texts:
            continue

        token_lists = call_analyze_api(texts, mode)

        now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S.%f")
        rows = [
            (cid, mode, json.dumps(tokens, ensure_ascii=False), now)
            for cid, tokens in zip(ordered_ids, token_lists, strict=True)
        ]
        insert_morphemes(conn, rows)
        total_inserted += len(rows)
        print(f"  チャンク {chunk_num}/{total_chunks}: +{len(rows)} 件 (合計 {total_inserted} 件)")

    print(f"\n完了: {total_inserted} 件を保存しました。")


def main() -> None:
    """形態素解析バッチのエントリーポイント。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["A", "B", "C"], default="C")
    parser.add_argument("--user", default=None, help="特定ユーザのloginに絞る")
    args = parser.parse_args()

    # morpheme-api 死活確認
    try:
        resp = requests.get(f"{MORPHEME_API_URL}/health", timeout=10)
        resp.raise_for_status()
        print(f"morpheme-api 接続確認: {resp.json()}")
    except Exception as e:
        print(f"morpheme-api に接続できません: {e}")
        sys.exit(1)

    print("MySQL 接続中...")
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )
    try:
        process(conn, args.mode, args.user)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
