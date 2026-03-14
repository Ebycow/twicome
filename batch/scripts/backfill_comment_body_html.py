"""comments.body_html をバックフィルするスクリプト。"""

import argparse
import os
from pathlib import Path

import mysql.connector
from comment_body_html import BODY_HTML_RENDER_VERSION, render_comment_body_html
from dotenv import load_dotenv

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
ENV_PATH = Path(os.getenv("ENV_FILE", str(PROJECT_ROOT / ".env")))
if not ENV_PATH.is_absolute():
    ENV_PATH = PROJECT_ROOT / ENV_PATH
load_dotenv(str(ENV_PATH))

MYSQL_HOST = os.getenv("MYSQL_HOST", "db")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "appuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "appdb")


def parse_args() -> argparse.Namespace:
    """コマンドライン引数をパースして返す。"""
    parser = argparse.ArgumentParser(
        description="Backfill comments.body_html from existing raw_json/body data.",
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="Rows to process per batch.")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max rows to update in this run. 0 means no limit.",
    )
    return parser.parse_args()


def main() -> None:
    """バックフィル処理のエントリーポイント。"""
    args = parse_args()
    if not MYSQL_PASSWORD:
        raise RuntimeError("MYSQL_PASSWORD is not set. Set MYSQL_PASSWORD in .env or environment variables.")

    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        autocommit=False,
    )

    processed = 0
    try:
        while True:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT comment_id, body, raw_json
                FROM comments
                WHERE body_html IS NULL
                   OR body_html_version <> %s
                ORDER BY comment_id
                LIMIT %s
                """,
                (BODY_HTML_RENDER_VERSION, args.batch_size),
            )
            rows = cur.fetchall()
            cur.close()

            if not rows:
                break

            updates = []
            for row in rows:
                updates.append(
                    (
                        render_comment_body_html(row["raw_json"], row["body"]),
                        BODY_HTML_RENDER_VERSION,
                        row["comment_id"],
                    )
                )

            update_cur = conn.cursor()
            update_cur.executemany(
                """
                UPDATE comments
                SET body_html = %s,
                    body_html_version = %s
                WHERE comment_id = %s
                """,
                updates,
            )
            conn.commit()
            update_cur.close()

            processed += len(updates)
            print(f"updated={processed}")

            if args.limit and processed >= args.limit:
                break
    finally:
        conn.close()


if __name__ == "__main__":
    main()
