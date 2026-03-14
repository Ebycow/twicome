"""ユーザー関連のデータアクセス層。

SQL を封じ込め、呼び出し元には dict / list[dict] / str のリストを返す。
"""

from sqlalchemy import text


def find_user(db, login: str, platform: str) -> dict | None:
    """Login + platform でユーザーを1件取得。存在しなければ None。"""
    row = (
        db.execute(
            text("""
            SELECT user_id, login, display_name, profile_image_url
            FROM users
            WHERE platform = :platform AND login = :login
            LIMIT 1
        """),
            {"platform": platform, "login": login},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def fetch_index_users(db) -> list[dict]:
    """トップページ検索用のユーザー一覧（コメント数・最終コメント日時付き）。"""
    rows = (
        db.execute(
            text("""
            SELECT
                u.login,
                u.display_name,
                u.profile_image_url,
                COALESCE(stats.comment_count, 0) AS comment_count,
                stats.last_comment_at
            FROM users u
            LEFT JOIN (
                SELECT commenter_login_snapshot,
                       COUNT(*) AS comment_count,
                       MAX(comment_created_at_utc) AS last_comment_at
                FROM comments
                GROUP BY commenter_login_snapshot
            ) stats ON stats.commenter_login_snapshot = u.login
            WHERE u.platform = 'twitch'
            ORDER BY u.login
        """)
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_quick_links(db, logins: list[str]) -> list[dict]:
    """QUICK_LINK_LOGINS に含まれるユーザーのプロフィール情報を返す。"""
    if not logins:
        return []
    placeholders = ", ".join([f":login_{i}" for i in range(len(logins))])
    params = {f"login_{i}": login for i, login in enumerate(logins)}
    rows = (
        db.execute(
            text(f"""
            SELECT login, display_name, profile_image_url
            FROM users
            WHERE platform = 'twitch' AND login IN ({placeholders})
        """),
            params,
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_streamers(db) -> list[dict]:
    """VOD を持つ配信者一覧（login, display_name）。"""
    rows = (
        db.execute(
            text("""
            SELECT u.login, u.display_name
            FROM users u
            JOIN vods v ON v.owner_user_id = u.user_id
            WHERE u.platform = 'twitch'
            GROUP BY u.user_id, u.login, u.display_name
            ORDER BY u.login
        """),
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_commenters_for_streamer(db, streamer_login: str) -> list[str]:
    """指定した配信者の VOD にコメントしたユーザーの login リスト。"""
    rows = db.execute(
        text("""
            SELECT DISTINCT c.commenter_login_snapshot
            FROM comments c
            JOIN vods v ON v.vod_id = c.vod_id
            JOIN users u ON u.user_id = v.owner_user_id
            WHERE u.login = :streamer
              AND u.platform = 'twitch'
              AND c.commenter_login_snapshot IS NOT NULL
        """),
        {"streamer": streamer_login},
    ).fetchall()
    return [r[0] for r in rows]


def fetch_user_vod_options(db, uid: int, owner_user_id: int | None) -> list[dict]:
    """ユーザーがコメントした VOD の選択肢（owner でフィルタ可能）。"""
    if owner_user_id is None:
        rows = (
            db.execute(
                text("""
                SELECT v.vod_id, v.title, sub.last_commented_at
                FROM (
                    SELECT c.vod_id, MAX(c.comment_created_at_utc) AS last_commented_at
                    FROM comments c
                    WHERE c.commenter_user_id = :uid
                    GROUP BY c.vod_id
                ) sub
                JOIN vods v ON v.vod_id = sub.vod_id
                ORDER BY sub.last_commented_at DESC
                LIMIT 300
            """),
                {"uid": uid},
            )
            .mappings()
            .all()
        )
    else:
        rows = (
            db.execute(
                text("""
                SELECT v.vod_id, v.title, MAX(c.comment_created_at_utc) AS last_commented_at
                FROM comments c
                JOIN vods v ON v.vod_id = c.vod_id
                WHERE c.commenter_user_id = :uid AND v.owner_user_id = :owner_user_id
                GROUP BY v.vod_id, v.title
                ORDER BY last_commented_at DESC
                LIMIT 300
            """),
                {"uid": uid, "owner_user_id": owner_user_id},
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def fetch_user_owner_options(db, uid: int) -> list[dict]:
    """ユーザーがコメントした配信者の選択肢。"""
    rows = (
        db.execute(
            text("""
            SELECT DISTINCT u.user_id, u.login, u.display_name
            FROM users u
            JOIN vods v ON v.owner_user_id = u.user_id
            JOIN comments c ON c.vod_id = v.vod_id
            WHERE c.commenter_user_id = :uid
            ORDER BY u.login
        """),
            {"uid": uid},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]
