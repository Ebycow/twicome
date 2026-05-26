"""指定ユーザのコメントを形態素解析し、頻出単語ランキングを CSV に出力する

DBへの書き込みは行わない。
出力先: morpheme-sample/exports/{user}_{mode}_ranking.csv

Usage:
    python word_ranking.py --user <username>
    python word_ranking.py --user <username> --mode A --top 200
    python word_ranking.py --user <username> --pos 名詞 動詞
"""

import argparse
import csv
import os
import sys
import time
from collections import Counter
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

EXPORTS_DIR = Path(__file__).parent / "exports"
CHUNK_SIZE = 100

DEFAULT_POS = ["名詞", "動詞", "形容詞", "副詞"]


def fetch_comments(conn, user_login: str, limit: int | None) -> list[dict]:
    """指定ユーザのコメントをDBから取得する。"""
    cur = conn.cursor(dictionary=True)
    query = """
        SELECT c.comment_id, c.body
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


def count_words(morpheme_lists: list[list[dict]], pos_filter: list[str]) -> Counter:
    """形態素リストから基本形で単語を集計する。"""
    counter: Counter = Counter()
    for morphemes in morpheme_lists:
        for m in morphemes:
            if m["pos"] not in pos_filter:
                continue
            word = m["base_form"].strip()
            if not word:
                continue
            counter[word] += 1
    return counter


def write_csv(path: Path, counter: Counter, top: int | None) -> None:
    """頻出単語ランキングを CSV に書き出す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    ranking = counter.most_common(top)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "word", "count"])
        for rank, (word, count) in enumerate(ranking, start=1):
            writer.writerow([rank, word, count])


def main() -> None:
    """エントリーポイント。"""
    parser = argparse.ArgumentParser(description="頻出単語ランキングを CSV に出力する")
    parser.add_argument("--user", required=True, help="Twitch ログイン名")
    parser.add_argument("--mode", choices=["A", "B", "C"], default="C", help="分割モード (default: C)")
    parser.add_argument("--limit", type=int, default=None, help="取得件数 (default: 全件)")
    parser.add_argument("--top", type=int, default=None, help="上位 N 件のみ出力 (default: 全単語)")
    parser.add_argument(
        "--pos",
        nargs="+",
        default=DEFAULT_POS,
        help=f"集計対象の品詞 (default: {' '.join(DEFAULT_POS)})",
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

    counter = count_words(all_morphemes, args.pos)
    out_path = EXPORTS_DIR / f"{args.user}_{args.mode}_ranking.csv"
    write_csv(out_path, counter, args.top)

    top_label = f"上位 {args.top} 件" if args.top else f"全 {len(counter)} 種"
    print(f"CSV 出力: {out_path} ({top_label})", file=sys.stderr)


if __name__ == "__main__":
    main()
