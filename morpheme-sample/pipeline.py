"""コメント数上位 N ユーザの形態素集計 → SQLite 保存 → 語彙類似度グラフ構築

処理済みユーザは SQLite にキャッシュされるため、途中で中断しても再実行時はスキップされる。

Usage:
    python pipeline.py --top-users 50
    python pipeline.py --top-users 100 --mode A --sim-threshold 0.15
    python pipeline.py --top-users 50 --rebuild   # キャッシュ無視して再処理
"""

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

import mysql.connector
import numpy as np
import pandas as pd
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
DB_PATH = EXPORTS_DIR / "morphemes.db"
CHUNK_SIZE = 100
DEFAULT_POS = ["名詞", "動詞", "形容詞", "副詞"]


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


def open_db(rebuild: bool) -> sqlite3.Connection:
    """SQLite を開いてテーブルを初期化する。rebuild=True の場合は既存ファイルを削除する。"""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if rebuild and DB_PATH.exists():
        DB_PATH.unlink()
        print("SQLite を再構築します。", file=sys.stderr)
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS processed_users (
            user_login   TEXT    NOT NULL,
            mode         TEXT    NOT NULL,
            comment_count INTEGER NOT NULL,
            processed_at TEXT    NOT NULL,
            PRIMARY KEY (user_login, mode)
        );
        CREATE TABLE IF NOT EXISTS user_word_counts (
            user_login TEXT    NOT NULL,
            mode       TEXT    NOT NULL,
            base_form  TEXT    NOT NULL,
            count      INTEGER NOT NULL,
            PRIMARY KEY (user_login, mode, base_form)
        );
    """)
    db.commit()
    return db


def already_processed(db: sqlite3.Connection, user_login: str, mode: str) -> bool:
    """指定ユーザ・モードが処理済みかどうかを返す。"""
    row = db.execute(
        "SELECT 1 FROM processed_users WHERE user_login = ? AND mode = ?",
        (user_login, mode),
    ).fetchone()
    return row is not None


def save_user_words(
    db: sqlite3.Connection, user_login: str, mode: str, comment_count: int, word_counts: dict[str, int]
) -> None:
    """ユーザの単語カウントを SQLite に保存し、処理済みとしてマークする。"""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT OR REPLACE INTO processed_users VALUES (?, ?, ?, ?)",
        (user_login, mode, comment_count, now),
    )
    db.executemany(
        "INSERT OR REPLACE INTO user_word_counts VALUES (?, ?, ?, ?)",
        [(user_login, mode, word, cnt) for word, cnt in word_counts.items()],
    )
    db.commit()


# ---------------------------------------------------------------------------
# MySQL
# ---------------------------------------------------------------------------


def fetch_top_users(conn, n: int) -> list[dict]:
    """コメント数上位 N ユーザを返す。"""
    cur = conn.cursor(dictionary=True)
    # コメント数で集計してから絞る（2M行 GROUP BY のため数十秒かかる場合がある）
    cur.execute(
        """
        SELECT u.login AS user_login, COUNT(c.comment_id) AS comment_count
        FROM comments c
        JOIN users u ON u.user_id = c.commenter_user_id
        WHERE u.platform = 'twitch'
          AND c.body IS NOT NULL AND c.body != ''
        GROUP BY u.user_id, u.login
        ORDER BY comment_count DESC
        LIMIT %s
    """,
        (n,),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def fetch_comments(conn, user_login: str) -> list[str]:
    """指定ユーザの全コメント本文を返す。"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.body
        FROM comments c
        JOIN users u ON u.user_id = c.commenter_user_id
        WHERE u.login = %s AND u.platform = 'twitch'
          AND c.body IS NOT NULL AND c.body != ''
        ORDER BY c.comment_created_at_utc
    """,
        (user_login,),
    )
    rows = [row[0] for row in cur.fetchall()]
    cur.close()
    return rows


# ---------------------------------------------------------------------------
# Morpheme API
# ---------------------------------------------------------------------------


def call_analyze_api(texts: list[str], mode: str) -> list[list[dict]]:
    """morpheme-api の /analyze を呼び出してトークンリストを返す。"""
    resp = requests.post(
        f"{MORPHEME_API_URL}/analyze",
        json={"texts": texts, "mode": mode},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["results"]


def count_words(morpheme_lists: list[list[dict]], pos_filter: list[str]) -> dict[str, int]:
    """形態素リストから品詞フィルタを適用して基本形の出現回数を集計する。"""
    counts: dict[str, int] = {}
    for morphemes in morpheme_lists:
        for m in morphemes:
            if m["pos"] not in pos_filter:
                continue
            word = m["base_form"].strip()
            if not word:
                continue
            counts[word] = counts.get(word, 0) + 1
    return counts


def analyze_user(conn, user_login: str, mode: str, pos_filter: list[str]) -> dict[str, int]:
    """ユーザの全コメントを形態素解析して単語カウントを返す。"""
    bodies = fetch_comments(conn, user_login)
    all_morphemes: list[list[dict]] = []
    for i in range(0, len(bodies), CHUNK_SIZE):
        chunk = bodies[i : i + CHUNK_SIZE]
        all_morphemes.extend(call_analyze_api(chunk, mode))
    return count_words(all_morphemes, pos_filter)


# ---------------------------------------------------------------------------
# グラフ構築
# ---------------------------------------------------------------------------


def build_graph(db: sqlite3.Connection, mode: str, sim_threshold: float, min_df: int) -> None:
    """SQLite の集計データから語彙類似度グラフを構築して CSV に出力する。"""
    df = pd.read_sql_query(
        "SELECT user_login, base_form, count FROM user_word_counts WHERE mode = ?",
        db,
        params=(mode,),
    )
    if df.empty:
        print("グラフ構築: データなし。", file=sys.stderr)
        return

    # min_df: N ユーザ未満にしか出現しない語彙は類似度に寄与しないため除外する
    user_freq = df.groupby("base_form")["user_login"].nunique()
    valid_vocab = user_freq[user_freq >= min_df].index
    df = df[df["base_form"].isin(valid_vocab)]
    print(f"語彙フィルタ: {len(user_freq)} 語 → {len(valid_vocab)} 語 (min_df={min_df})", file=sys.stderr)

    # ユーザー × 単語 の出現頻度行列
    matrix = df.pivot_table(index="user_login", columns="base_form", values="count", fill_value=0)
    users = matrix.index.tolist()
    n = len(users)
    print(f"グラフ構築: {n} ユーザ × {len(matrix.columns)} 語彙", file=sys.stderr)

    # TF-IDF
    tf = matrix.div(matrix.sum(axis=1), axis=0)
    idf = np.log((n + 1) / ((matrix > 0).sum(axis=0) + 1))
    tfidf = tf * idf

    # コサイン類似度
    vals = tfidf.values.astype(np.float32)
    norms = np.linalg.norm(vals, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = vals / norms
    sim = normalized @ normalized.T  # (n, n)

    # ノード情報（次数・強度）
    meta = pd.read_sql_query(
        "SELECT user_login, comment_count FROM processed_users WHERE mode = ?",
        db,
        params=(mode,),
    )
    meta = meta.set_index("user_login")

    node_rows = []
    for i, u in enumerate(users):
        mask = np.arange(n) != i
        neighbors = sim[i][mask]
        degree = int((neighbors >= sim_threshold).sum())
        strength = float(neighbors[neighbors >= sim_threshold].sum())
        node_rows.append(
            {
                "user_login": u,
                "comment_count": int(meta.loc[u, "comment_count"]) if u in meta.index else 0,
                "degree": degree,
                "strength": round(strength, 4),
            }
        )
    nodes_df = pd.DataFrame(node_rows).sort_values("strength", ascending=False)

    # エッジ（上三角のみ、threshold 以上）
    edge_rows = []
    for i in range(n):
        for j in range(i + 1, n):
            w = float(sim[i, j])
            if w >= sim_threshold:
                edge_rows.append({"source": users[i], "target": users[j], "weight": round(w, 4)})
    edges_df = pd.DataFrame(edge_rows).sort_values("weight", ascending=False)

    nodes_path = EXPORTS_DIR / f"graph_nodes_{mode}.csv"
    edges_path = EXPORTS_DIR / f"graph_edges_{mode}.csv"
    nodes_df.to_csv(nodes_path, index=False, encoding="utf-8-sig")
    edges_df.to_csv(edges_path, index=False, encoding="utf-8-sig")

    print(f"ノード: {nodes_path} ({len(nodes_df)} 件)", file=sys.stderr)
    print(f"エッジ: {edges_path} ({len(edges_df)} 件, threshold={sim_threshold})", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """エントリーポイント。"""
    parser = argparse.ArgumentParser(description="上位 N ユーザの形態素集計 → グラフ構築")
    parser.add_argument(
        "--top-users", type=int, default=50, metavar="N", help="コメント数上位 N ユーザを対象にする (default: 50)"
    )
    parser.add_argument("--mode", choices=["A", "B", "C"], default="C", help="SudachiPy 分割モード (default: C)")
    parser.add_argument(
        "--pos", nargs="+", default=DEFAULT_POS, help=f"集計対象品詞 (default: {' '.join(DEFAULT_POS)})"
    )
    parser.add_argument(
        "--sim-threshold", type=float, default=0.1, help="グラフエッジとして採用するコサイン類似度の下限 (default: 0.1)"
    )
    parser.add_argument(
        "--min-df",
        type=int,
        default=2,
        help="語彙行列に含める最低ユーザ数（これ未満のユーザにしか出現しない語を除外）(default: 2)",
    )
    parser.add_argument("--rebuild", action="store_true", help="SQLite キャッシュを削除して全ユーザを再処理する")
    parser.add_argument(
        "--collect-only", action="store_true", help="形態素解析・SQLite 保存のみ行い、グラフ構築はスキップする"
    )
    parser.add_argument("--graph-only", action="store_true", help="形態素解析をスキップしてグラフ構築のみ実行する")
    args = parser.parse_args()

    # morpheme-api 死活確認
    try:
        resp = requests.get(f"{MORPHEME_API_URL}/health", timeout=10)
        resp.raise_for_status()
        print(f"morpheme-api: {resp.json()}", file=sys.stderr)
    except Exception as e:
        if not args.graph_only:
            print(f"morpheme-api に接続できません: {e}", file=sys.stderr)
            sys.exit(1)

    db = open_db(args.rebuild)

    if not args.graph_only:
        print("MySQL 接続中...", file=sys.stderr)
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
        )
        try:
            print(f"上位 {args.top_users} ユーザ取得中... (2M行 GROUP BY のため数十秒かかります)", file=sys.stderr)
            users = fetch_top_users(conn, args.top_users)
            print(f"対象: {len(users)} ユーザ", file=sys.stderr)

            t_total = time.perf_counter()
            for idx, row in enumerate(users, 1):
                login = row["user_login"]
                comment_count = row["comment_count"]

                if already_processed(db, login, args.mode):
                    print(f"  [{idx}/{len(users)}] {login} — スキップ (キャッシュ済み)", file=sys.stderr)
                    continue

                print(f"  [{idx}/{len(users)}] {login} ({comment_count} 件) 解析中...", file=sys.stderr)
                t0 = time.perf_counter()
                word_counts = analyze_user(conn, login, args.mode, args.pos)
                elapsed = time.perf_counter() - t0
                save_user_words(db, login, args.mode, comment_count, word_counts)
                print(f"    → {len(word_counts)} 語 / {elapsed:.1f}s", file=sys.stderr)

            print(f"\n集計完了 ({time.perf_counter() - t_total:.1f}s)", file=sys.stderr)
        finally:
            conn.close()

    if not args.collect_only:
        print("\nグラフ構築中...", file=sys.stderr)
        build_graph(db, args.mode, args.sim_threshold, args.min_df)
    db.close()


if __name__ == "__main__":
    main()
