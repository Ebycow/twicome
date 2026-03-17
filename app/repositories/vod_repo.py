"""VOD 関連のデータアクセス層。"""

from sqlalchemy import text


def fetch_vod_by_id(db, vod_id: int) -> dict | None:
    """VOD ID で VOD を1件取得。存在しなければ None。"""
    row = (
        db.execute(
            text("""
            SELECT
                v.vod_id, v.title, v.description, v.created_at_utc,
                v.length_seconds, v.view_count, v.game_name, v.url, v.youtube_url,
                u.login AS owner_login, u.display_name AS owner_display_name,
                u.user_id AS owner_user_id,
                COALESCE(cc.comment_count, 0) AS comment_count
            FROM vods v
            JOIN users u ON u.user_id = v.owner_user_id
            LEFT JOIN (
                SELECT vod_id, COUNT(*) AS comment_count
                FROM comments
                GROUP BY vod_id
            ) cc ON cc.vod_id = v.vod_id
            WHERE v.vod_id = :vod_id
            LIMIT 1
        """),
            {"vod_id": vod_id},
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def count_vods(db, *, q: str | None = None, owner_login: str | None = None) -> int:
    """フィルタ条件に合う VOD 数を返す。"""
    where, params = _build_vod_where(q=q, owner_login=owner_login)
    row = (
        db.execute(
            text(f"""
            SELECT COUNT(*) AS cnt
            FROM vods v
            JOIN users u ON u.user_id = v.owner_user_id
            WHERE {where}
        """),
            params,
        )
        .mappings()
        .first()
    )
    return int(row["cnt"])


def search_vods(
    db,
    *,
    q: str | None = None,
    owner_login: str | None = None,
    sort: str = "created_at",
    limit: int = 40,
    offset: int = 0,
) -> list[dict]:
    """VOD を検索して返す。コメント数付き。"""
    where, params = _build_vod_where(q=q, owner_login=owner_login)
    order_sql = _build_vod_list_order(sort)
    params.update({"limit": limit, "offset": offset})
    rows = (
        db.execute(
            text(f"""
            SELECT
                v.vod_id, v.title, v.created_at_utc,
                v.length_seconds, v.view_count, v.game_name, v.url,
                u.login AS owner_login, u.display_name AS owner_display_name,
                COALESCE(cc.comment_count, 0) AS comment_count
            FROM vods v
            JOIN users u ON u.user_id = v.owner_user_id
            LEFT JOIN (
                SELECT vod_id, COUNT(*) AS comment_count
                FROM comments
                GROUP BY vod_id
            ) cc ON cc.vod_id = v.vod_id
            WHERE {where}
            {order_sql}
            LIMIT :limit OFFSET :offset
        """),
            params,
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def _build_vod_where(*, q: str | None, owner_login: str | None) -> tuple[str, dict]:
    """WHERE 句の SQL 文字列とパラメータを返す。"""
    where = ["1=1"]
    params: dict = {}

    if q:
        where.append("v.title LIKE :q_like")
        params["q_like"] = f"%{q}%"

    if owner_login:
        where.append("u.login = :owner_login")
        params["owner_login"] = owner_login

    return " AND ".join(where), params


def _build_vod_list_order(sort: str) -> str:
    if sort == "comment_count":
        return "ORDER BY COALESCE(cc.comment_count, 0) DESC, v.created_at_utc DESC"
    return "ORDER BY v.created_at_utc DESC"
