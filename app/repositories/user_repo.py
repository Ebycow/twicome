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
    """VOD を持つ配信者一覧（login, display_name, vod_count, comment_count）。"""
    rows = (
        db.execute(
            text("""
            SELECT
                u.login,
                u.display_name,
                u.profile_image_url,
                COUNT(v.vod_id) AS vod_count,
                COALESCE(SUM(vim.comments_ingested), 0) AS comment_count
            FROM users u
            JOIN vods v ON v.owner_user_id = u.user_id
            LEFT JOIN vod_ingest_markers vim ON vim.vod_id = v.vod_id
            WHERE u.platform = 'twitch'
            GROUP BY u.user_id, u.login, u.display_name, u.profile_image_url
            ORDER BY u.login
        """),
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_app_stats(db) -> dict:
    """トップページ向けのアプリ全体統計を返す。"""
    row = (
        db.execute(
            text("""
            SELECT
                (SELECT COUNT(*) FROM users WHERE platform = 'twitch') AS total_users,
                (
                    SELECT COUNT(*)
                    FROM users u
                    WHERE u.platform = 'twitch'
                      AND EXISTS (
                          SELECT 1
                          FROM comments c
                          WHERE c.commenter_login_snapshot = u.login
                      )
                ) AS active_commenters,
                (SELECT COUNT(*) FROM vods) AS total_vods,
                (SELECT COUNT(*) FROM comments) AS total_comments,
                (
                    SELECT COUNT(DISTINCT v.owner_user_id)
                    FROM vods v
                ) AS tracked_streamers
        """)
        )
        .mappings()
        .first()
    )
    return (
        dict(row)
        if row
        else {
            "total_users": 0,
            "active_commenters": 0,
            "total_vods": 0,
            "total_comments": 0,
            "tracked_streamers": 0,
        }
    )


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


def fetch_similar_users(db, uid: int, limit: int = 25) -> list[dict]:
    """共通視聴配信者数が多い順に類似ユーザーを返す。

    対象ユーザーが視聴した配信者セットとの共通数で類似度を測定する。
    共通配信者が2件以上のユーザーのみ対象。
    """
    rows = (
        db.execute(
            text("""
            WITH target_streamers AS (
                SELECT DISTINCT v.owner_user_id
                FROM comments c
                JOIN vods v ON v.vod_id = c.vod_id
                WHERE c.commenter_user_id = :uid
            ),
            user_shared AS (
                SELECT
                    c.commenter_user_id,
                    COUNT(DISTINCT v.owner_user_id) AS shared_count
                FROM comments c
                JOIN vods v ON v.vod_id = c.vod_id
                WHERE v.owner_user_id IN (SELECT owner_user_id FROM target_streamers)
                  AND c.commenter_user_id != :uid
                GROUP BY c.commenter_user_id
                HAVING COUNT(DISTINCT v.owner_user_id) >= 2
            )
            SELECT
                us.commenter_user_id AS user_id,
                u.login,
                u.display_name,
                u.profile_image_url,
                us.shared_count
            FROM user_shared us
            JOIN users u ON u.user_id = us.commenter_user_id
            ORDER BY us.shared_count DESC
            LIMIT :limit
        """),
            {"uid": uid, "limit": limit},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def fetch_shared_streamers(db, uid: int, other_uids: list[int]) -> dict[int, list[str]]:
    """対象ユーザーと各候補ユーザーの共通視聴配信者名を返す。

    Returns: {commenter_user_id: [streamer_display_name, ...]}
    """
    if not other_uids:
        return {}
    placeholders = ", ".join([f":other_{i}" for i in range(len(other_uids))])
    params = {"uid": uid, **{f"other_{i}": u for i, u in enumerate(other_uids)}}
    rows = (
        db.execute(
            text(f"""
            WITH target_streamers AS (
                SELECT DISTINCT v.owner_user_id
                FROM comments c
                JOIN vods v ON v.vod_id = c.vod_id
                WHERE c.commenter_user_id = :uid
            )
            SELECT
                c.commenter_user_id,
                COALESCE(owner_u.display_name, owner_u.login) AS streamer_name
            FROM comments c
            JOIN vods v ON v.vod_id = c.vod_id
            JOIN users owner_u ON owner_u.user_id = v.owner_user_id
            WHERE v.owner_user_id IN (SELECT owner_user_id FROM target_streamers)
              AND c.commenter_user_id IN ({placeholders})
            GROUP BY c.commenter_user_id, v.owner_user_id, owner_u.display_name, owner_u.login
        """),
            params,
        )
        .mappings()
        .all()
    )
    result: dict[int, list[str]] = {}
    for row in rows:
        uid_key = int(row["commenter_user_id"])
        result.setdefault(uid_key, []).append(row["streamer_name"])
    return result
