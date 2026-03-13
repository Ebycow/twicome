"""
コメント関連のデータアクセス層。
WHERE 句・ORDER BY 句の構築を含む SQL を封じ込める。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from services.comment_utils import BODY_HTML_RENDER_VERSION, build_comment_body_select_sql

_BODY_SELECT = build_comment_body_select_sql("c")
_BODY_SUBQUERY_SELECT = build_comment_body_select_sql("c0")

# 全コメントページで使うカラムリスト（JOIN 済みの c に対して）
_COL_LIST = f"""
    c.comment_id, c.vod_id, c.offset_seconds, c.comment_created_at_utc,
    c.commenter_login_snapshot, c.commenter_display_name_snapshot,
    {_BODY_SELECT},
    c.user_color, c.bits_spent,
    c.twicome_likes_count, c.twicome_dislikes_count,
    cn.note AS community_note_body, cn.eligible AS cn_eligible,
    cn.status AS cn_status, cn.verifiability AS cn_verifiability,
    cn.harm_risk AS cn_harm_risk, cn.exaggeration AS cn_exaggeration,
    cn.evidence_gap AS cn_evidence_gap, cn.subjectivity AS cn_subjectivity,
    cn.issues AS cn_issues, cn.ask AS cn_ask,
    v.title AS vod_title, v.url AS vod_url, v.youtube_url AS youtube_url,
    v.created_at_utc AS vod_created_at_utc,
    u.login AS owner_login, u.display_name AS owner_display_name
"""


def _build_where(
    uid: int,
    vod_id: Optional[int],
    owner_user_id: Optional[int],
    q: Optional[str],
    exclude_terms: list[str],
    date_from_utc: Optional[datetime] = None,
    date_to_utc: Optional[datetime] = None,
) -> tuple[str, dict]:
    """WHERE 句の SQL 文字列とパラメータを返す。"""
    where = ["c.commenter_user_id = :uid"]
    params: dict = {"uid": uid}

    if vod_id is not None:
        where.append("c.vod_id = :vod_id")
        params["vod_id"] = vod_id

    if owner_user_id is not None:
        where.append("v.owner_user_id = :owner_user_id")
        params["owner_user_id"] = owner_user_id

    if q:
        where.append("c.body LIKE :q_like")
        params["q_like"] = f"%{q}%"

    for idx, term in enumerate(exclude_terms):
        key = f"exclude_q_like_{idx}"
        where.append(f"c.body NOT LIKE :{key}")
        params[key] = f"%{term}%"

    if date_from_utc is not None:
        where.append("c.comment_created_at_utc >= :date_from_utc")
        params["date_from_utc"] = date_from_utc

    if date_to_utc is not None:
        where.append("c.comment_created_at_utc < :date_to_utc")
        params["date_to_utc"] = date_to_utc

    return " AND ".join(where), params


def _build_order(sort: str) -> str:
    """ORDER BY 句の SQL 文字列を返す。"""
    if sort == "created_at":
        return "ORDER BY c.comment_created_at_utc DESC, c.vod_id DESC, c.offset_seconds DESC"
    if sort == "likes":
        return "ORDER BY c.twicome_likes_count DESC, c.vod_id DESC, c.offset_seconds DESC"
    if sort == "dislikes":
        return "ORDER BY c.twicome_dislikes_count DESC, c.vod_id DESC, c.offset_seconds DESC"
    if sort == "community_note":
        return "ORDER BY cn.created_at_utc DESC, c.vod_id DESC, c.offset_seconds DESC"
    if sort == "danger":
        return "ORDER BY COALESCE((cn.harm_risk + cn.exaggeration + cn.evidence_gap + cn.subjectivity), 0) DESC, c.vod_id DESC, c.offset_seconds DESC"
    if sort == "random":
        return "ORDER BY RAND()"
    return "ORDER BY c.vod_id DESC, c.offset_seconds DESC"


def count_comments(
    db,
    uid: int,
    *,
    vod_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    q: Optional[str] = None,
    exclude_terms: Optional[list[str]] = None,
    date_from_utc: Optional[datetime] = None,
    date_to_utc: Optional[datetime] = None,
) -> int:
    """フィルタ条件に合うコメント数を返す。"""
    where_sql, params = _build_where(
        uid, vod_id, owner_user_id, q, exclude_terms or [],
        date_from_utc=date_from_utc, date_to_utc=date_to_utc,
    )
    # owner_user_id フィルター時のみ vods JOIN が必要
    count_from = (
        "FROM comments c JOIN vods v ON v.vod_id = c.vod_id"
        if owner_user_id is not None
        else "FROM comments c"
    )
    row = db.execute(
        text(f"SELECT COUNT(*) AS cnt {count_from} WHERE {where_sql}"),
        params,
    ).mappings().first()
    return int(row["cnt"])


def count_comments_in_vod(db, vod_id: int) -> int:
    """VOD 内のコメント総数。"""
    row = db.execute(
        text("SELECT COUNT(*) AS cnt FROM comments c WHERE c.vod_id = :vod_id"),
        {"vod_id": vod_id},
    ).mappings().first()
    return int(row["cnt"])


def fetch_comments(
    db,
    uid: int,
    *,
    vod_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    q: Optional[str] = None,
    exclude_terms: Optional[list[str]] = None,
    sort: str = "created_at",
    limit: int = 50,
    offset: int = 0,
    date_from_utc: Optional[datetime] = None,
    date_to_utc: Optional[datetime] = None,
) -> list[dict]:
    """
    フィルタ・ソート・ページネーションを適用してコメントを取得する。
    sort=created_at かつフィルタなしの場合、サブクエリ最適化を使用する。
    """
    where_sql, params = _build_where(
        uid, vod_id, owner_user_id, q, exclude_terms or [],
        date_from_utc=date_from_utc, date_to_utc=date_to_utc,
    )
    order_sql = _build_order(sort)
    params.update({"limit": limit, "offset": offset, "body_html_version": BODY_HTML_RENDER_VERSION})

    use_subquery = (
        sort == "created_at"
        and vod_id is None
        and owner_user_id is None
        and not q
        and not (exclude_terms or [])
        and date_from_utc is None
        and date_to_utc is None
    )

    if use_subquery:
        rows = db.execute(
            text(f"""
                SELECT {_COL_LIST}
                FROM (
                    SELECT comment_id, vod_id, offset_seconds, comment_created_at_utc,
                           commenter_login_snapshot, commenter_display_name_snapshot,
                           {_BODY_SUBQUERY_SELECT},
                           user_color, bits_spent,
                           twicome_likes_count, twicome_dislikes_count
                    FROM comments c0
                    WHERE commenter_user_id = :uid
                    ORDER BY comment_created_at_utc DESC, vod_id DESC, offset_seconds DESC
                    LIMIT :limit OFFSET :offset
                ) c
                JOIN vods v ON v.vod_id = c.vod_id
                JOIN users u ON u.user_id = v.owner_user_id
                LEFT JOIN community_notes cn ON cn.comment_id = c.comment_id
            """),
            params,
        ).mappings().all()
    else:
        rows = db.execute(
            text(f"""
                SELECT {_COL_LIST}
                FROM comments c
                JOIN vods v ON v.vod_id = c.vod_id
                JOIN users u ON u.user_id = v.owner_user_id
                LEFT JOIN community_notes cn ON cn.comment_id = c.comment_id
                WHERE {where_sql}
                {order_sql}
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()

    return [dict(row) for row in rows]


def fetch_comments_in_vod(
    db,
    vod_id: int,
    *,
    sort: str = "created_at",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """カーソルページネーション用：VOD 内の全コメントをソート順で取得。"""
    order_sql = _build_order(sort)
    rows = db.execute(
        text(f"""
            SELECT {_COL_LIST}
            FROM comments c
            JOIN vods v ON v.vod_id = c.vod_id
            JOIN users u ON u.user_id = v.owner_user_id
            LEFT JOIN community_notes cn ON cn.comment_id = c.comment_id
            WHERE c.vod_id = :vod_id
            {order_sql}
            LIMIT :limit OFFSET :offset
        """),
        {"vod_id": vod_id, "limit": limit, "offset": offset,
         "body_html_version": BODY_HTML_RENDER_VERSION},
    ).mappings().all()
    return [dict(row) for row in rows]


def find_comment_by_id(db, comment_id: str) -> Optional[dict]:
    """コメント ID でコメントを1件取得。カーソル解決用。"""
    row = db.execute(
        text("""
            SELECT vod_id, body, comment_created_at_utc,
                   offset_seconds, twicome_likes_count, twicome_dislikes_count
            FROM comments
            WHERE comment_id = :comment_id
        """),
        {"comment_id": comment_id},
    ).mappings().first()
    return dict(row) if row else None


def fetch_comment_vote_counts(db, comment_ids: list[str]) -> dict[str, dict]:
    """コメント ID ごとの like / dislike 件数を返す。"""
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for comment_id in comment_ids:
        value = str(comment_id or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized_ids.append(value)

    if not normalized_ids:
        return {}

    placeholders = ", ".join(f":comment_id_{idx}" for idx in range(len(normalized_ids)))
    params = {f"comment_id_{idx}": comment_id for idx, comment_id in enumerate(normalized_ids)}
    rows = db.execute(
        text(f"""
            SELECT comment_id, twicome_likes_count, twicome_dislikes_count
            FROM comments
            WHERE comment_id IN ({placeholders})
        """),
        params,
    ).mappings().all()

    return {
        row["comment_id"]: {
            "twicome_likes_count": int(row["twicome_likes_count"] or 0),
            "twicome_dislikes_count": int(row["twicome_dislikes_count"] or 0),
        }
        for row in rows
    }


def get_cursor_position(db, vod_id: int, sort: str, cursor_row: dict) -> int:
    """
    指定ソート順でカーソルコメントより前にある行数を返す。
    offset = max(0, cursor_pos - page_size // 2) の計算に使う。
    """
    c_created_at = cursor_row.get("comment_created_at_utc")
    c_offset = cursor_row.get("offset_seconds", 0)
    c_likes = cursor_row.get("twicome_likes_count") or 0
    c_dislikes = cursor_row.get("twicome_dislikes_count") or 0

    if sort == "created_at":
        row = db.execute(
            text("""
                SELECT COUNT(*) AS pos FROM comments c
                WHERE c.vod_id = :vod_id AND (
                    c.comment_created_at_utc > :c_created_at
                    OR (c.comment_created_at_utc = :c_created_at AND c.offset_seconds > :c_offset)
                )
            """),
            {"vod_id": vod_id, "c_created_at": c_created_at, "c_offset": c_offset},
        ).mappings().first()
    elif sort == "likes":
        row = db.execute(
            text("""
                SELECT COUNT(*) AS pos FROM comments c
                WHERE c.vod_id = :vod_id AND c.twicome_likes_count > :c_likes
            """),
            {"vod_id": vod_id, "c_likes": c_likes},
        ).mappings().first()
    elif sort == "dislikes":
        row = db.execute(
            text("""
                SELECT COUNT(*) AS pos FROM comments c
                WHERE c.vod_id = :vod_id AND c.twicome_dislikes_count > :c_dislikes
            """),
            {"vod_id": vod_id, "c_dislikes": c_dislikes},
        ).mappings().first()
    else:
        row = db.execute(
            text("""
                SELECT COUNT(*) AS pos FROM comments c
                WHERE c.vod_id = :vod_id AND c.offset_seconds > :c_offset
            """),
            {"vod_id": vod_id, "c_offset": c_offset},
        ).mappings().first()

    return int(row["pos"]) if row else 0


def fetch_comments_by_ids(db, comment_ids: list[str]) -> list[dict]:
    """コメントIDリストに対応するコメント詳細（本文・VOD・日時）を返す。"""
    if not comment_ids:
        return []
    placeholders = ", ".join(f":id_{i}" for i in range(len(comment_ids)))
    params = {f"id_{i}": cid for i, cid in enumerate(comment_ids)}
    params["body_html_version"] = BODY_HTML_RENDER_VERSION
    _body = build_comment_body_select_sql("c")
    rows = db.execute(
        text(f"""
            SELECT c.comment_id, {_body},
                   c.comment_created_at_utc, c.offset_seconds,
                   c.vod_id,
                   v.title AS vod_title, v.url AS vod_url,
                   u.login AS owner_login, u.display_name AS owner_display_name
            FROM comments c
            JOIN vods v ON v.vod_id = c.vod_id
            JOIN users u ON u.user_id = v.owner_user_id
            WHERE c.comment_id IN ({placeholders})
            ORDER BY c.comment_created_at_utc DESC
        """),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def fetch_comment_bodies_by_ids(db, comment_ids: list[str]) -> dict[str, str]:
    """コメントIDリストに対応する body テキストを {comment_id: body} で返す。"""
    if not comment_ids:
        return {}
    placeholders = ", ".join(f":id_{i}" for i in range(len(comment_ids)))
    params = {f"id_{i}": cid for i, cid in enumerate(comment_ids)}
    rows = db.execute(
        text(f"SELECT comment_id, body FROM comments WHERE comment_id IN ({placeholders})"),
        params,
    ).mappings().all()
    return {row["comment_id"]: row["body"] for row in rows}


def fetch_popular_comments(db, limit: int = 20) -> list[dict]:
    """いいね・dislike の合計が多い順でコメントを取得（トップページ用）。"""
    from services.comment_utils import build_comment_body_select_sql
    body_select = build_comment_body_select_sql("c")
    rows = db.execute(
        text(f"""
            SELECT
                c.comment_id,
                {body_select},
                c.twicome_likes_count,
                c.twicome_dislikes_count,
                (c.twicome_likes_count + c.twicome_dislikes_count) AS score,
                c.commenter_login_snapshot,
                c.commenter_display_name_snapshot,
                v.title AS vod_title,
                u.login AS owner_login,
                u.display_name AS owner_display_name
            FROM comments c
            JOIN vods v ON v.vod_id = c.vod_id
            JOIN users u ON u.user_id = v.owner_user_id
            WHERE (c.twicome_likes_count + c.twicome_dislikes_count) > 0
            ORDER BY (c.twicome_likes_count + c.twicome_dislikes_count) DESC
            LIMIT :limit
        """),
        {"limit": limit, "body_html_version": BODY_HTML_RENDER_VERSION},
    ).mappings().all()
    return [dict(row) for row in rows]
