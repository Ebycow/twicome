"""収集対象外ユーザーのデータを DB から削除する。

収集対象（QUICK_LINK_LOGINS / DEFAULT_LOGIN）から外したユーザーや、
旧バージョンで投入された全ユーザー分のコメントを掃除するために毎バッチで実行する。

- 対象外ユーザーのコメントを削除
- コメントが 1 件も無くなった VOD を削除（取り込みマーカーは CASCADE で消える）
- 対象ユーザーでもなく、VOD の配信者でもないユーザーを削除
"""

import os
from pathlib import Path

import mysql.connector
from collect_targets import load_target_logins
from dotenv import load_dotenv

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
ENV_PATH = Path(os.getenv("ENV_FILE", str(PROJECT_ROOT / ".env")))
if not ENV_PATH.is_absolute():
    ENV_PATH = PROJECT_ROOT / ENV_PATH
load_dotenv(str(ENV_PATH))

DELETE_BATCH_SIZE = 5000


def _placeholders(n: int) -> str:
    return ", ".join(["%s"] * n)


def build_prune_statements(targets: frozenset[str]) -> list[tuple[str, tuple]]:
    """実行する (SQL, params) のリストを返す。テストしやすいよう分離している。"""
    logins = tuple(sorted(targets))
    ph = _placeholders(len(logins))
    return [
        (
            # LIMIT 付きで小分けに削除し、大量削除時の undo ログ肥大とロック長期化を避ける
            f"""
            DELETE FROM comments
            WHERE commenter_login_snapshot IS NULL
               OR LOWER(commenter_login_snapshot) NOT IN ({ph})
            LIMIT {DELETE_BATCH_SIZE}
            """,
            logins,
        ),
        (
            """
            DELETE FROM vods
            WHERE NOT EXISTS (SELECT 1 FROM comments c WHERE c.vod_id = vods.vod_id)
            """,
            (),
        ),
        (
            f"""
            DELETE FROM users
            WHERE LOWER(login) NOT IN ({ph})
              AND NOT EXISTS (SELECT 1 FROM vods v WHERE v.owner_user_id = users.user_id)
            """,
            logins,
        ),
    ]


def main() -> None:
    """プルーニングを実行する。"""
    targets = load_target_logins()
    password = os.getenv("MYSQL_PASSWORD")
    if not password:
        raise RuntimeError("MYSQL_PASSWORD is not set.")
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "db"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "appuser"),
        password=password,
        database=os.getenv("MYSQL_DATABASE", "appdb"),
        autocommit=False,
    )
    try:
        cur = conn.cursor()
        (comments_sql, comments_params), *rest = build_prune_statements(targets)
        deleted_comments = 0
        while True:
            cur.execute(comments_sql, comments_params)
            conn.commit()
            deleted_comments += cur.rowcount
            if cur.rowcount < DELETE_BATCH_SIZE:
                break
        counts = []
        for sql, params in rest:
            cur.execute(sql, params)
            counts.append(cur.rowcount)
        conn.commit()
        print(f"Pruned comments={deleted_comments}, vods={counts[0]}, users={counts[1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
