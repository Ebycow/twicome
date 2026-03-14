"""VOD コメント JSON ファイルを MySQL にインポートするスクリプト。"""

import argparse
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mysql.connector
from comment_body_html import BODY_HTML_RENDER_VERSION, render_comment_body_html
from dateutil import parser as dtparser
from dotenv import load_dotenv
from mysql.connector import errorcode
from mysql.connector.cursor import MySQLCursor

# -----------------------
# 設定（環境変数で上書き可）😺🦐
# -----------------------
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
ENV_PATH = Path(os.getenv("ENV_FILE", str(PROJECT_ROOT / ".env")))
if not ENV_PATH.is_absolute():
    ENV_PATH = PROJECT_ROOT / ENV_PATH
load_dotenv(str(ENV_PATH))

MYSQL_HOST = os.getenv("MYSQL_HOST", "db")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "appuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
if not MYSQL_PASSWORD:
    raise RuntimeError("MYSQL_PASSWORD is not set. Set MYSQL_PASSWORD in .env or environment variables.")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "appdb")

COMMENTS_DIR = os.getenv("COMMENTS_DIR", str(PROJECT_ROOT / "data" / "default" / "comments"))
DEFAULT_PLATFORM = os.getenv("PLATFORM", "twitch")

# ファイル名: <vodid>.json
VOD_JSON_RE = re.compile(r"^(\d+)\.json$")


def parse_dt_utc(dt_str: str | None) -> datetime | None:
    """ISO文字列をUTCのdatetime(naive)にする（MySQL DATETIME想定）😺🦐"""
    if not dt_str:
        return None
    dt = dtparser.isoparse(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt_utc = dt.astimezone(UTC)
    return dt_utc.replace(tzinfo=None)


def upsert_user(
    cur: MySQLCursor, user_id: int, login: str, display_name: str | None, profile_image_url: str | None, platform: str
) -> None:
    """Users テーブルにユーザーを upsert する。"""
    sql = """
    INSERT INTO users (user_id, login, display_name, profile_image_url, platform, created_at, updated_at)
    VALUES (%s, %s, %s, %s, %s, NOW(6), NOW(6))
    ON DUPLICATE KEY UPDATE
      login = VALUES(login),
      display_name = COALESCE(VALUES(display_name), display_name),
      profile_image_url = COALESCE(VALUES(profile_image_url), profile_image_url),
      platform = VALUES(platform),
      updated_at = NOW(6)
    """
    cur.execute(sql, (user_id, login, display_name, profile_image_url, platform))


def upsert_vod(cur: MySQLCursor, vod: dict[str, Any], streamer: dict[str, Any], platform: str) -> int:
    """Vods テーブルに VOD を upsert して vod_id を返す。"""
    vod_id = int(vod["id"])
    owner_user_id = int(streamer["id"])

    title = vod.get("title") or ""
    description = vod.get("description")
    created_at_utc = parse_dt_utc(vod.get("created_at"))

    length_seconds = vod.get("length")
    start_seconds = vod.get("start")
    end_seconds = vod.get("end")
    view_count = vod.get("viewCount")
    game_name = vod.get("game")
    url = vod.get("url")

    sql = """
    INSERT INTO vods
      (vod_id, owner_user_id, title, description, created_at_utc,
       length_seconds, start_seconds, end_seconds, view_count, game_name,
       platform, url, ingested_at)
    VALUES
      (%s, %s, %s, %s, %s,
       %s, %s, %s, %s, %s,
       %s, %s, NOW(6))
    ON DUPLICATE KEY UPDATE
      owner_user_id = VALUES(owner_user_id),
      title = VALUES(title),
      description = COALESCE(VALUES(description), description),
      created_at_utc = COALESCE(VALUES(created_at_utc), created_at_utc),
      length_seconds = COALESCE(VALUES(length_seconds), length_seconds),
      start_seconds = COALESCE(VALUES(start_seconds), start_seconds),
      end_seconds = COALESCE(VALUES(end_seconds), end_seconds),
      view_count = COALESCE(VALUES(view_count), view_count),
      game_name = COALESCE(VALUES(game_name), game_name),
      platform = VALUES(platform),
      url = COALESCE(VALUES(url), url),
      ingested_at = NOW(6)
    """
    cur.execute(
        sql,
        (
            vod_id,
            owner_user_id,
            title,
            description,
            created_at_utc,
            length_seconds,
            start_seconds,
            end_seconds,
            view_count,
            game_name,
            platform,
            url,
        ),
    )
    return vod_id


def insert_comment(cur: MySQLCursor, vod_id: int, c: dict[str, Any], platform: str) -> None:
    """Comments テーブルにコメントを upsert する。"""
    comment_id = c["_id"]
    offset_seconds = int(c.get("content_offset_seconds", 0))
    created_at_utc = parse_dt_utc(c.get("created_at"))

    commenter = c.get("commenter") or {}
    commenter_user_id = commenter.get("_id")
    commenter_user_id = int(commenter_user_id) if commenter_user_id is not None else None
    commenter_login = commenter.get("name")
    commenter_display = commenter.get("display_name")
    commenter_logo = commenter.get("logo")

    msg = c.get("message") or {}
    body = msg.get("body") or ""
    user_color = msg.get("user_color")
    bits_spent = msg.get("bits_spent")
    try:
        bits_spent = int(bits_spent) if bits_spent is not None else None
    except Exception:
        bits_spent = None

    if commenter_user_id is not None and commenter_login:
        upsert_user(cur, commenter_user_id, commenter_login, commenter_display, commenter_logo, platform)

    raw_json_str = json.dumps(c, ensure_ascii=False)
    body_html = render_comment_body_html(c, body)

    sql = """
    INSERT INTO comments
      (comment_id, vod_id, offset_seconds, comment_created_at_utc,
       commenter_user_id, commenter_login_snapshot, commenter_display_name_snapshot,
       body, body_html, body_html_version, user_color, bits_spent, raw_json, ingested_at)
    VALUES
      (%s, %s, %s, %s,
       %s, %s, %s,
       %s, %s, %s, %s, %s, CAST(%s AS JSON), NOW(6))
    ON DUPLICATE KEY UPDATE
      vod_id = VALUES(vod_id),
      offset_seconds = VALUES(offset_seconds),
      comment_created_at_utc = COALESCE(VALUES(comment_created_at_utc), comment_created_at_utc),
      commenter_user_id = COALESCE(VALUES(commenter_user_id), commenter_user_id),
      commenter_login_snapshot = COALESCE(VALUES(commenter_login_snapshot), commenter_login_snapshot),
      commenter_display_name_snapshot = COALESCE(
          VALUES(commenter_display_name_snapshot), commenter_display_name_snapshot),
      body = VALUES(body),
      body_html = VALUES(body_html),
      body_html_version = VALUES(body_html_version),
      user_color = COALESCE(VALUES(user_color), user_color),
      bits_spent = COALESCE(VALUES(bits_spent), bits_spent),
      raw_json = VALUES(raw_json),
      ingested_at = NOW(6)
    """
    cur.execute(
        sql,
        (
            comment_id,
            vod_id,
            offset_seconds,
            created_at_utc,
            commenter_user_id,
            commenter_login,
            commenter_display,
            body,
            body_html,
            BODY_HTML_RENDER_VERSION,
            user_color,
            bits_spent,
            raw_json_str,
        ),
    )


def vod_already_ingested(cur: MySQLCursor, vod_id: int) -> bool:
    """既存データ判定（主に完了マーカー未導入時のログ補助用）。"""
    cur.execute("SELECT 1 FROM vods WHERE vod_id=%s LIMIT 1", (vod_id,))
    return cur.fetchone() is not None


def compute_sha256(path: str) -> str:
    """ファイルの SHA-256 ハッシュ値を返す。"""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def get_vod_ingest_marker(cur: MySQLCursor, vod_id: int) -> tuple[str, int] | None:
    """vod_ingest_markers テーブルから取り込み完了マーカーを取得する。"""
    try:
        cur.execute(
            """
            SELECT source_file_sha256, comments_ingested
            FROM vod_ingest_markers
            WHERE vod_id=%s
            LIMIT 1
            """,
            (vod_id,),
        )
    except mysql.connector.Error as e:
        if e.errno == errorcode.ER_NO_SUCH_TABLE:
            raise RuntimeError(
                "Table `vod_ingest_markers` does not exist. Run `alembic -c app/alembic.ini upgrade head` first."
            ) from e
        raise

    row = cur.fetchone()
    if row is None:
        return None
    return row[0], int(row[1])


def upsert_vod_ingest_marker(
    cur: MySQLCursor,
    vod_id: int,
    source_filename: str,
    source_file_sha256: str,
    source_file_size: int,
    comments_ingested: int,
) -> None:
    """vod_ingest_markers テーブルに取り込み完了マーカーを upsert する。"""
    cur.execute(
        """
        INSERT INTO vod_ingest_markers
          (vod_id, source_filename, source_file_sha256, source_file_size, comments_ingested, completed_at, updated_at)
        VALUES
          (%s, %s, %s, %s, %s, NOW(6), NOW(6))
        ON DUPLICATE KEY UPDATE
          source_filename = VALUES(source_filename),
          source_file_sha256 = VALUES(source_file_sha256),
          source_file_size = VALUES(source_file_size),
          comments_ingested = VALUES(comments_ingested),
          completed_at = NOW(6),
          updated_at = NOW(6)
        """,
        (vod_id, source_filename, source_file_sha256, source_file_size, comments_ingested),
    )


def list_comment_json_files(dir_path: str) -> list[tuple[str, str, int]]:
    """ディレクトリ内のコメント JSON ファイル一覧を返す。"""
    items: list[tuple[str, str, int]] = []
    for name in sorted(os.listdir(dir_path)):
        m = VOD_JSON_RE.match(name)
        if not m:
            continue
        vod_id = int(m.group(1))
        full = os.path.join(dir_path, name)
        if os.path.isfile(full):
            items.append((full, name, vod_id))
    return items


def resolve_input_dir(raw_path: str) -> str:
    """入力ディレクトリパスを絶対パスに解決する。"""
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数をパースして返す。"""
    parser = argparse.ArgumentParser(description="Import VOD comment JSON files into MySQL.")
    parser.add_argument(
        "--comments-dir",
        default=COMMENTS_DIR,
        help="Directory that contains <vod_id>.json files (default: COMMENTS_DIR env).",
    )
    parser.add_argument(
        "--reingest-existing-vods",
        action="store_true",
        help="Re-process VODs even if they already exist in DB.",
    )
    return parser.parse_args()


def ingest_one_file(conn, json_path: str, filename: str, expected_vod_id: int) -> tuple[int, int]:
    """1 つの VOD JSON ファイルを DB に取り込む。(vod_id, comment_count) を返す。"""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    vod = data.get("video") or {}
    streamer = data.get("streamer") or {}
    comments = data.get("comments") or []

    if not vod or not streamer:
        raise ValueError(f"{filename}: JSONに video / streamer が無い😿🦐")

    platform = data.get("platform") or DEFAULT_PLATFORM

    vod_id_in_json = int(vod.get("id"))
    if vod_id_in_json != expected_vod_id:
        raise ValueError(
            f"{filename}: ファイル名vod_id({expected_vod_id})とJSON video.id({vod_id_in_json})が不一致😾🦐"
        )

    cur = conn.cursor()

    # owner user upsert 😺🦐
    owner_user_id = int(streamer["id"])
    owner_login = streamer.get("login") or streamer.get("name") or str(owner_user_id)
    owner_display = streamer.get("name")
    upsert_user(cur, owner_user_id, owner_login, owner_display, None, platform)

    # vod upsert 😸🦐
    vod_id = upsert_vod(cur, vod, streamer, platform)

    # comments insert/upsert 😺🦐
    count = 0
    for c in comments:
        content_id = c.get("content_id")
        if content_id is not None and int(content_id) != vod_id:
            continue
        insert_comment(cur, vod_id, c, platform)
        count += 1

        if count % 2000 == 0:
            conn.commit()

    return vod_id, count


def ingest_directory(dir_path: str, skip_existing_vods: bool = True) -> None:
    """ディレクトリ内の全 VOD JSON ファイルを DB に取り込む。"""
    if not os.path.isdir(dir_path):
        raise FileNotFoundError(f"COMMENTS_DIR not found: {dir_path}")

    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        autocommit=False,
    )

    total_files = 0
    skipped = 0
    ingested = 0
    total_comments = 0

    try:
        files = list_comment_json_files(dir_path)
        total_files = len(files)
        print(f"📂 COMMENTS_DIR={dir_path}")
        print(f"🧭 skip_existing_vods={skip_existing_vods}")

        for fullpath, filename, vod_id in files:
            cur = conn.cursor()
            try:
                source_file_sha256 = compute_sha256(fullpath)
                source_file_size = os.path.getsize(fullpath)

                marker = get_vod_ingest_marker(cur, vod_id)
                if skip_existing_vods and marker and marker[0] == source_file_sha256:
                    skipped += 1
                    continue

                if skip_existing_vods and marker and marker[0] != source_file_sha256:
                    print(f"♻️ {filename}: source_file_sha256 changed, re-ingesting")
                elif skip_existing_vods and marker is None and vod_already_ingested(cur, vod_id):
                    print(f"ℹ️ {filename}: VOD exists without completion marker, re-ingesting once")

                vod_done, ccount = ingest_one_file(conn, fullpath, filename, vod_id)
                upsert_vod_ingest_marker(
                    cur=cur,
                    vod_id=vod_done,
                    source_filename=filename,
                    source_file_sha256=source_file_sha256,
                    source_file_size=source_file_size,
                    comments_ingested=ccount,
                )
                conn.commit()

                ingested += 1
                total_comments += ccount
                print(f"✅ {filename}: vod_id={vod_done}, comments={ccount}")

            except Exception as e:
                conn.rollback()
                print(f"❌ {filename}: {e}")
                continue

        print(
            f"\n🎉 Done. total_files={total_files}, ingested={ingested}, skipped={skipped}, comments={total_comments}"
        )

    finally:
        conn.close()


if __name__ == "__main__":
    args = parse_args()
    comments_dir = resolve_input_dir(args.comments_dir)
    ingest_directory(comments_dir, skip_existing_vods=not args.reingest_existing_vods)
