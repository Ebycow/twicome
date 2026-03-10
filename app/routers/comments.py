import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import text

from cache import (
    get_index_landing_cache,
    get_index_users_cache,
    get_user_meta_cache,
    set_index_landing_cache,
    set_index_users_cache,
    set_user_meta_cache,
)
from core.config import DEFAULT_LOGIN, DEFAULT_PLATFORM, FAISS_ENABLED, QUICK_LINK_LOGINS
from core.db import SessionLocal
from core.templates import templates
from services.comment_utils import (
    BODY_HTML_RENDER_VERSION,
    _build_comment_body_select_sql,
    _decorate_comment,
    _get_comment_body_html,
    _split_filter_terms,
)

router = APIRouter()

_COMMENT_BODY_SELECT_SQL = _build_comment_body_select_sql("c")
_COMMENT_BODY_SUBQUERY_SELECT_SQL = _build_comment_body_select_sql("c0")


def _fetch_user_vod_options(uid: int, owner_user_id_int: Optional[int], db) -> list[dict]:
    if owner_user_id_int is None:
        rows = db.execute(
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
        ).mappings().all()
    else:
        rows = db.execute(
            text("""
 SELECT v.vod_id, v.title, MAX(c.comment_created_at_utc) AS last_commented_at
 FROM comments c
 JOIN vods v ON v.vod_id = c.vod_id
 WHERE c.commenter_user_id = :uid AND v.owner_user_id = :owner_user_id
 GROUP BY v.vod_id, v.title
 ORDER BY last_commented_at DESC
 LIMIT 300
            """),
            {"uid": uid, "owner_user_id": owner_user_id_int},
        ).mappings().all()
    return [dict(row) for row in rows]


def _fetch_user_owner_options(uid: int, db) -> list[dict]:
    rows = db.execute(
        text("""
 SELECT DISTINCT u.user_id, u.login, u.display_name
 FROM users u
 JOIN vods v ON v.owner_user_id = u.user_id
 JOIN comments c ON c.vod_id = v.vod_id
 WHERE c.commenter_user_id = :uid
 ORDER BY u.login
        """),
        {"uid": uid},
    ).mappings().all()
    return [dict(row) for row in rows]


def _load_user_meta(login: str, uid: int, db) -> Optional[dict]:
    if login not in QUICK_LINK_LOGINS:
        return None

    cached = get_user_meta_cache(login)
    if cached is not None:
        return cached

    meta = {
        "vod_options": _fetch_user_vod_options(uid, None, db),
        "owner_options": _fetch_user_owner_options(uid, db),
    }
    set_user_meta_cache(login, meta)
    return meta


def _fetch_index_users(db) -> list[dict]:
    rows = db.execute(
        text(
            """
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
            """
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _fetch_index_quick_links(db) -> list[dict]:
    if not QUICK_LINK_LOGINS:
        return []

    placeholders = ", ".join([f":login_{i}" for i in range(len(QUICK_LINK_LOGINS))])
    params = {f"login_{i}": login for i, login in enumerate(QUICK_LINK_LOGINS)}
    rows = db.execute(
        text(f"""
            SELECT login, display_name, profile_image_url
            FROM users
            WHERE platform = 'twitch' AND login IN ({placeholders})
        """),
        params,
    ).mappings().all()
    quick_link_by_login = {row["login"]: dict(row) for row in rows}

    quick_links = []
    for login in QUICK_LINK_LOGINS:
        row = quick_link_by_login.get(login)
        if not row:
            continue
        display_name = row.get("display_name") or row["login"]
        quick_links.append(
            {
                "login": row["login"],
                "platform": "twitch",
                "profile_image_url": row.get("profile_image_url"),
                "alt": display_name,
                "label": f"{display_name}をみるならここ",
            }
        )
    return quick_links


def _fetch_index_streamers(db) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT u.login, u.display_name
            FROM users u
            JOIN vods v ON v.owner_user_id = u.user_id
            WHERE u.platform = 'twitch'
            GROUP BY u.user_id, u.login, u.display_name
            ORDER BY u.login
        """),
    ).mappings().all()
    return [dict(row) for row in rows]


def _load_index_landing() -> dict:
    cached = get_index_landing_cache()
    if cached is not None:
        return cached

    with SessionLocal() as db:
        data = {
            "quick_links": _fetch_index_quick_links(db),
            "streamers": _fetch_index_streamers(db),
        }

    set_index_landing_cache(data)
    return data


def _load_index_users() -> list[dict]:
    cached = get_index_users_cache()
    if cached is not None:
        return cached

    with SessionLocal() as db:
        users = _fetch_index_users(db)

    set_index_users_cache(users)
    return users


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    landing = _load_index_landing()
    quick_links_out = landing["quick_links"]
    streamers = landing["streamers"]
    selected_login = DEFAULT_LOGIN or ""
    selected_login_for_links = "__LOGIN_PLACEHOLDER__"

    # 人気コメントランキングはキャッシュしない（いいね数が動的に変わる）
    with SessionLocal() as db:
        popular_comments = db.execute(
            text(f"""
                SELECT
                    c.comment_id,
                    {_COMMENT_BODY_SELECT_SQL},
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
                LIMIT 20
            """),
            {"body_html_version": BODY_HTML_RENDER_VERSION},
        ).mappings().all()

    popular_comments_out = []
    for row in popular_comments:
        r = dict(row)
        r["body_html"] = _get_comment_body_html(r)
        r.pop("raw_json", None)
        r.pop("body_html_version", None)
        popular_comments_out.append(r)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "selected_login": selected_login,
            "selected_login_for_links": selected_login_for_links,
            "popular_comments": popular_comments_out,
            "quick_links": quick_links_out,
            "streamers": streamers,
        },
    )


@router.get("/api/users/index", response_class=JSONResponse)
def api_users_index():
    """トップページ検索用のユーザー一覧を返す。"""
    return {"users": _load_index_users()}


@router.get("/api/users/commenters", response_class=JSONResponse)
def api_users_commenters(streamer: str = Query(...)):
    """指定した配信者のVODにコメントしたユーザーのloginリストを返す"""
    with SessionLocal() as db:
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
            {"streamer": streamer},
        ).fetchall()
    return {"logins": [r[0] for r in rows]}


@router.post("/go")
def go(request: Request, login: str = Form(...), platform: str = Form(DEFAULT_PLATFORM)):
    login = login.strip()
    platform = platform.strip() or DEFAULT_PLATFORM
    target = request.url_for("user_comments_page", login=login)  # root_path込みになる
    return RedirectResponse(url=f"{target}?platform={platform}", status_code=303)


@router.get("/u/{login}", response_class=HTMLResponse)
def user_comments_page(
    request: Request,
    login: str,
    platform: str = Query(DEFAULT_PLATFORM),
    vod_id: Optional[str] = Query(None),
    owner_user_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    exclude_q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
    sort: str = Query("created_at"),  # vod_time | created_at | likes | dislikes | random
    cursor: Optional[str] = Query(None),
):
    # Convert vod_id to int if possible
    vod_id_int = None
    if vod_id and vod_id.strip():
        try:
            vod_id_int = int(vod_id)
        except ValueError:
            vod_id_int = None

    # Convert owner_user_id to int if possible
    owner_user_id_int = None
    if owner_user_id and owner_user_id.strip():
        try:
            owner_user_id_int = int(owner_user_id)
        except ValueError:
            owner_user_id_int = None

    exclude_terms = _split_filter_terms(exclude_q)
    # print(
    #     f"DEBUG: vod_id={vod_id}, vod_id_int={vod_id_int}, owner_user_id={owner_user_id}, "
    #     f"owner_user_id_int={owner_user_id_int}, q={q}, exclude_q={exclude_q}"
    # )
    page_title = "コメント一覧"
    with SessionLocal() as db:
        # 1) user lookup
        user_row = db.execute(
            text("""
                SELECT user_id, login, display_name
                FROM users
                WHERE platform = :platform AND login = :login
                LIMIT 1
            """),
            {"platform": platform, "login": login},
        ).mappings().first()

        if not user_row:
            return templates.TemplateResponse(
                "user_comments.html",
                {
                    "request": request,
                    "error": f"ユーザが見つかりませんでした: {platform}/{login}",
                    "user": None,
                    "comments": [],
                    "vod_options": [],
                    "owner_options": [],
                    "page": page,
                    "pages": 0,
                    "total": 0,
                    "filters": {
                        "platform": platform,
                        "vod_id": vod_id_int,
                        "owner_user_id": owner_user_id_int,
                        "q": q,
                        "exclude_q": exclude_q,
                        "page_size": page_size,
                        "sort": sort,
                    },
                    "root_path": request.scope.get("root_path", ""),
                    "faiss_enabled": FAISS_ENABLED,
                },
                status_code=404,
            )

        uid = user_row["user_id"]
        cached_meta = _load_user_meta(login, uid, db)
        if owner_user_id_int is None and cached_meta is not None:
            vod_options = cached_meta["vod_options"]
        else:
            vod_options = _fetch_user_vod_options(uid, owner_user_id_int, db)
        if cached_meta is not None:
            owner_options = cached_meta["owner_options"]
        else:
            owner_options = _fetch_user_owner_options(uid, db)

        # 3) build WHERE
        where = ["c.commenter_user_id = :uid"]
        params = {"uid": uid}

        if vod_id_int is not None:
            where.append("c.vod_id = :vod_id")
            params["vod_id"] = vod_id_int

        if owner_user_id_int is not None:
            where.append("v.owner_user_id = :owner_user_id")
            params["owner_user_id"] = owner_user_id_int

        if q:
            where.append("c.body LIKE :q_like")
            params["q_like"] = f"%{q}%"

        for idx, term in enumerate(exclude_terms):
            key = f"exclude_q_like_{idx}"
            where.append(f"c.body NOT LIKE :{key}")
            params[key] = f"%{term}%"

        where_sql = " AND ".join(where)

        # 4) sort
        if sort == "created_at":
            # NULLがあり得るので、vod_timeにフォールバック
            order_sql = "ORDER BY c.comment_created_at_utc DESC, c.vod_id DESC, c.offset_seconds DESC"
        elif sort == "likes":
            order_sql = "ORDER BY c.twicome_likes_count DESC, c.vod_id DESC, c.offset_seconds DESC"
        elif sort == "dislikes":
            order_sql = "ORDER BY c.twicome_dislikes_count DESC, c.vod_id DESC, c.offset_seconds DESC"
        elif sort == "community_note":
            order_sql = "ORDER BY cn.created_at_utc DESC, c.vod_id DESC, c.offset_seconds DESC"
        elif sort == "danger":
            order_sql = "ORDER BY COALESCE((cn.harm_risk + cn.exaggeration + cn.evidence_gap + cn.subjectivity), 0) DESC, c.vod_id DESC, c.offset_seconds DESC"
        elif sort == "random":
            order_sql = "ORDER BY RAND()"
        else:
            order_sql = "ORDER BY c.vod_id DESC, c.offset_seconds DESC"

        # 5) count
        # community_notes は COUNT に不要。vods は owner_user_id フィルター時のみ必要
        if owner_user_id_int is not None:
            count_from = "FROM comments c JOIN vods v ON v.vod_id = c.vod_id"
        else:
            count_from = "FROM comments c"
        total = db.execute(
            text(f"SELECT COUNT(*) AS cnt {count_from} WHERE {where_sql}"),
            params,
        ).mappings().first()["cnt"]

        if cursor:
            # Cursor-based pagination
            # If cursor is provided, show all comments from the VOD containing the cursor comment
            cursor_row = db.execute(
                text("SELECT vod_id, body, comment_created_at_utc, offset_seconds, twicome_likes_count, twicome_dislikes_count FROM comments WHERE comment_id = :cursor"),
                {"cursor": cursor},
            ).mappings().first()
            if cursor_row:
                vod_id = cursor_row["vod_id"]
                cursor_body = cursor_row["body"]
                page_title = f"{cursor_body[:20]}{'...' if len(cursor_body) > 20 else ''} の個別ページ"
                # Override filters to show all comments from this VOD
                where_sql = "c.vod_id = :vod_id"
                params = {"vod_id": vod_id}
                # Recalculate total for this VOD
                total = db.execute(
                    text("SELECT COUNT(*) AS cnt FROM comments c WHERE c.vod_id = :vod_id"),
                    {"vod_id": vod_id},
                ).mappings().first()["cnt"]
                # Find the position of the cursor comment based on actual sort order
                c_created_at = cursor_row["comment_created_at_utc"]
                c_offset = cursor_row["offset_seconds"]
                c_likes = cursor_row["twicome_likes_count"] or 0
                c_dislikes = cursor_row["twicome_dislikes_count"] or 0
                if sort == "created_at":
                    cursor_pos = db.execute(
                        text("""
                            SELECT COUNT(*) AS pos FROM comments c
                            WHERE c.vod_id = :vod_id AND (
                                c.comment_created_at_utc > :c_created_at
                                OR (c.comment_created_at_utc = :c_created_at AND c.offset_seconds > :c_offset)
                            )
                        """),
                        {"vod_id": vod_id, "c_created_at": c_created_at, "c_offset": c_offset},
                    ).mappings().first()["pos"]
                elif sort == "likes":
                    cursor_pos = db.execute(
                        text("""
                            SELECT COUNT(*) AS pos FROM comments c
                            WHERE c.vod_id = :vod_id AND c.twicome_likes_count > :c_likes
                        """),
                        {"vod_id": vod_id, "c_likes": c_likes},
                    ).mappings().first()["pos"]
                elif sort == "dislikes":
                    cursor_pos = db.execute(
                        text("""
                            SELECT COUNT(*) AS pos FROM comments c
                            WHERE c.vod_id = :vod_id AND c.twicome_dislikes_count > :c_dislikes
                        """),
                        {"vod_id": vod_id, "c_dislikes": c_dislikes},
                    ).mappings().first()["pos"]
                else:
                    # vod_time / その他: offset_seconds DESC
                    cursor_pos = db.execute(
                        text("""
                            SELECT COUNT(*) AS pos FROM comments c
                            WHERE c.vod_id = :vod_id AND c.offset_seconds > :c_offset
                        """),
                        {"vod_id": vod_id, "c_offset": c_offset},
                    ).mappings().first()["pos"]
            else:
                # Cursor not found, fallback
                cursor_pos = 0

            # Get half page_size before and after
            half = page_size // 2
            offset = max(0, cursor_pos - half)
            limit = page_size
            page = (offset // page_size) + 1  # For compatibility, calculate approximate page
        else:
            pages = max(1, math.ceil(total / page_size)) if total > 0 else 0
            page = min(page, pages) if pages else 1
            offset = (page - 1) * page_size
            limit = page_size

        # 6) fetch page
        # created_at ソートかつフィルターなしの場合: サブクエリで comments を先に LIMIT してから JOIN
        # (idx_comments_user_created_sort を使って filesort を回避)
        _col_list = f"""
                    c.comment_id, c.vod_id, c.offset_seconds, c.comment_created_at_utc,
                    c.commenter_login_snapshot, c.commenter_display_name_snapshot,
                    {_COMMENT_BODY_SELECT_SQL},
                    c.user_color, c.bits_spent,
                    c.twicome_likes_count, c.twicome_dislikes_count,
                    cn.note AS community_note_body, cn.eligible AS cn_eligible,
                    cn.status AS cn_status, cn.verifiability AS cn_verifiability,
                    cn.harm_risk AS cn_harm_risk, cn.exaggeration AS cn_exaggeration,
                    cn.evidence_gap AS cn_evidence_gap, cn.subjectivity AS cn_subjectivity,
                    cn.issues AS cn_issues, cn.ask AS cn_ask,
                    v.title AS vod_title, v.url AS vod_url, v.youtube_url AS youtube_url,
                    v.created_at_utc AS vod_created_at_utc,
                    u.login AS owner_login, u.display_name AS owner_display_name"""
        if (
            sort == "created_at"
            and vod_id_int is None
            and owner_user_id_int is None
            and not q
            and not exclude_terms
            and not cursor
        ):
            rows = db.execute(
                text(f"""
                    SELECT {_col_list}
                    FROM (
                        SELECT comment_id, vod_id, offset_seconds, comment_created_at_utc,
                               commenter_login_snapshot, commenter_display_name_snapshot,
                               {_COMMENT_BODY_SUBQUERY_SELECT_SQL},
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
                {"uid": uid, "limit": limit, "offset": offset, "body_html_version": BODY_HTML_RENDER_VERSION},
            ).mappings().all()
        else:
            rows = db.execute(
                text(f"""
                    SELECT {_col_list}
                    FROM comments c
                    JOIN vods v ON v.vod_id = c.vod_id
                    JOIN users u ON u.user_id = v.owner_user_id
                    LEFT JOIN community_notes cn ON cn.comment_id = c.comment_id
                    WHERE {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """),
                {**params, "limit": limit, "offset": offset, "body_html_version": BODY_HTML_RENDER_VERSION},
            ).mappings().all()

        now = datetime.utcnow()
        comments = [_decorate_comment(r, now) for r in rows]

        return templates.TemplateResponse(
            "user_comments.html",
            {
                "request": request,
                "error": None,
                "user": dict(user_row),
                "comments": comments,
                "vod_options": [dict(x) for x in vod_options],
                "owner_options": [dict(x) for x in owner_options],
                "page": page,
                "pages": pages if not cursor else 0,
                "total": total,
                "filters": {
                    "platform": platform,
                    "vod_id": vod_id_int,
                    "owner_user_id": owner_user_id_int,
                    "q": q,
                    "exclude_q": exclude_q,
                    "page_size": page_size,
                    "sort": sort,
                    "cursor": cursor,
                },
                "root_path": request.scope.get("root_path", ""),
                "page_title": page_title,
                "faiss_enabled": FAISS_ENABLED,
            },
        )


@router.get("/api/u/{login}")
def user_comments_api(
    login: str,
    platform: str = Query(DEFAULT_PLATFORM),
    vod_id: Optional[str] = Query(None),
    owner_user_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    exclude_q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
    sort: str = Query("created_at"),  # vod_time | created_at | likes | dislikes | random
    cursor: Optional[str] = Query(None),
):
    # Convert vod_id to int if possible
    vod_id_int = None
    if vod_id and vod_id.strip():
        try:
            vod_id_int = int(vod_id)
        except ValueError:
            vod_id_int = None

    # Convert owner_user_id to int if possible
    owner_user_id_int = None
    if owner_user_id and owner_user_id.strip():
        try:
            owner_user_id_int = int(owner_user_id)
        except ValueError:
            owner_user_id_int = None

    exclude_terms = _split_filter_terms(exclude_q)

    with SessionLocal() as db:
        user_row = db.execute(
            text("""
                SELECT user_id, login, display_name
                FROM users
                WHERE platform = :platform AND login = :login
                LIMIT 1
            """),
            {"platform": platform, "login": login},
        ).mappings().first()
        if not user_row:
            return JSONResponse({"error": "user_not_found"}, status_code=404)

        uid = user_row["user_id"]

        # 3) build WHERE
        where = ["c.commenter_user_id = :uid"]
        params = {"uid": uid}

        if vod_id_int is not None:
            where.append("c.vod_id = :vod_id")
            params["vod_id"] = vod_id_int

        if owner_user_id_int is not None:
            where.append("v.owner_user_id = :owner_user_id")
            params["owner_user_id"] = owner_user_id_int

        if q:
            where.append("c.body LIKE :q_like")
            params["q_like"] = f"%{q}%"

        for idx, term in enumerate(exclude_terms):
            key = f"exclude_q_like_{idx}"
            where.append(f"c.body NOT LIKE :{key}")
            params[key] = f"%{term}%"

        where_sql = " AND ".join(where)

        # 4) sort
        if sort == "created_at":
            # NULLがあり得るので、vod_timeにフォールバック
            order_sql = "ORDER BY c.comment_created_at_utc DESC, c.vod_id DESC, c.offset_seconds DESC"
        elif sort == "likes":
            order_sql = "ORDER BY c.twicome_likes_count DESC, c.vod_id DESC, c.offset_seconds DESC"
        elif sort == "dislikes":
            order_sql = "ORDER BY c.twicome_dislikes_count DESC, c.vod_id DESC, c.offset_seconds DESC"
        elif sort == "community_note":
            order_sql = "ORDER BY cn.created_at_utc DESC, c.vod_id DESC, c.offset_seconds DESC"
        elif sort == "danger":
            order_sql = "ORDER BY COALESCE((cn.harm_risk + cn.exaggeration + cn.evidence_gap + cn.subjectivity), 0) DESC, c.vod_id DESC, c.offset_seconds DESC"
        elif sort == "random":
            order_sql = "ORDER BY RAND()"
        else:
            order_sql = "ORDER BY c.vod_id DESC, c.offset_seconds DESC"

        # 5) count
        # community_notes は COUNT に不要。vods は owner_user_id フィルター時のみ必要
        if owner_user_id_int is not None:
            count_from = "FROM comments c JOIN vods v ON v.vod_id = c.vod_id"
        else:
            count_from = "FROM comments c"
        total = db.execute(
            text(f"SELECT COUNT(*) AS cnt {count_from} WHERE {where_sql}"),
            params,
        ).mappings().first()["cnt"]

        if cursor:
            # Cursor-based pagination
            # If cursor is provided, show all comments from the VOD containing the cursor comment
            cursor_row = db.execute(
                text("SELECT vod_id, comment_created_at_utc, offset_seconds, twicome_likes_count, twicome_dislikes_count FROM comments WHERE comment_id = :cursor"),
                {"cursor": cursor},
            ).mappings().first()
            if cursor_row:
                vod_id = cursor_row["vod_id"]
                # Override filters to show all comments from this VOD
                where_sql = "c.vod_id = :vod_id"
                params = {"vod_id": vod_id}
                # Recalculate total for this VOD
                total = db.execute(
                    text("SELECT COUNT(*) AS cnt FROM comments c WHERE c.vod_id = :vod_id"),
                    {"vod_id": vod_id},
                ).mappings().first()["cnt"]
                # Find the position of the cursor comment based on actual sort order
                c_created_at = cursor_row["comment_created_at_utc"]
                c_offset = cursor_row["offset_seconds"]
                c_likes = cursor_row["twicome_likes_count"] or 0
                c_dislikes = cursor_row["twicome_dislikes_count"] or 0
                if sort == "created_at":
                    pos_row = db.execute(
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
                    pos_row = db.execute(
                        text("""
                            SELECT COUNT(*) AS pos FROM comments c
                            WHERE c.vod_id = :vod_id AND c.twicome_likes_count > :c_likes
                        """),
                        {"vod_id": vod_id, "c_likes": c_likes},
                    ).mappings().first()
                elif sort == "dislikes":
                    pos_row = db.execute(
                        text("""
                            SELECT COUNT(*) AS pos FROM comments c
                            WHERE c.vod_id = :vod_id AND c.twicome_dislikes_count > :c_dislikes
                        """),
                        {"vod_id": vod_id, "c_dislikes": c_dislikes},
                    ).mappings().first()
                else:
                    # vod_time / その他: offset_seconds DESC
                    pos_row = db.execute(
                        text("""
                            SELECT COUNT(*) AS pos FROM comments c
                            WHERE c.vod_id = :vod_id AND c.offset_seconds > :c_offset
                        """),
                        {"vod_id": vod_id, "c_offset": c_offset},
                    ).mappings().first()
                cursor_pos = pos_row["pos"] if pos_row else 0
                half = page_size // 2
                offset = max(0, cursor_pos - half)
                limit = page_size
                page = (offset // page_size) + 1  # For compatibility
            else:
                # Cursor not found, fallback
                offset = 0
                limit = page_size
                page = 1
        else:
            offset = (page - 1) * page_size
            limit = page_size

        _col_list = f"""
                    c.comment_id, c.vod_id, c.offset_seconds, c.comment_created_at_utc,
                    c.commenter_login_snapshot, c.commenter_display_name_snapshot,
                    {_COMMENT_BODY_SELECT_SQL},
                    c.user_color, c.bits_spent,
                    c.twicome_likes_count, c.twicome_dislikes_count,
                    cn.note AS community_note_body, cn.eligible AS cn_eligible,
                    cn.status AS cn_status, cn.verifiability AS cn_verifiability,
                    cn.harm_risk AS cn_harm_risk, cn.exaggeration AS cn_exaggeration,
                    cn.evidence_gap AS cn_evidence_gap, cn.subjectivity AS cn_subjectivity,
                    cn.issues AS cn_issues, cn.ask AS cn_ask,
                    v.title AS vod_title, v.url AS vod_url, v.youtube_url AS youtube_url,
                    v.created_at_utc AS vod_created_at_utc,
                    u.login AS owner_login, u.display_name AS owner_display_name"""
        if (
            sort == "created_at"
            and vod_id_int is None
            and owner_user_id_int is None
            and not q
            and not exclude_terms
            and not cursor
        ):
            rows = db.execute(
                text(f"""
                    SELECT {_col_list}
                    FROM (
                        SELECT comment_id, vod_id, offset_seconds, comment_created_at_utc,
                               commenter_login_snapshot, commenter_display_name_snapshot,
                               {_COMMENT_BODY_SUBQUERY_SELECT_SQL},
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
                {"uid": uid, "limit": limit, "offset": offset, "body_html_version": BODY_HTML_RENDER_VERSION},
            ).mappings().all()
        else:
            rows = db.execute(
                text(f"""
                    SELECT {_col_list}
                    FROM comments c
                    JOIN vods v ON v.vod_id = c.vod_id
                    JOIN users u ON u.user_id = v.owner_user_id
                    LEFT JOIN community_notes cn ON cn.comment_id = c.comment_id
                    WHERE {where_sql}
                    {order_sql}
                    LIMIT :limit OFFSET :offset
                """),
                {**params, "limit": limit, "offset": offset, "body_html_version": BODY_HTML_RENDER_VERSION},
            ).mappings().all()

        now = datetime.utcnow()
        comments = [_decorate_comment(r, now) for r in rows]

        return {"user": dict(user_row), "total": total, "page": page, "page_size": page_size, "items": comments}



@router.post("/like/{comment_id}")
def like_comment(comment_id: str, count: int = Query(1, ge=1, le=100)):
    """いいねを追加（countで複数回分をまとめて送信可能、最大100）"""
    with SessionLocal() as db:
        db.execute(
            text("UPDATE comments SET twicome_likes_count = twicome_likes_count + :count WHERE comment_id = :cid"),
            {"cid": comment_id, "count": count}
        )
        db.commit()
    return {"status": "ok", "added": count}


@router.post("/dislike/{comment_id}")
def dislike_comment(comment_id: str, count: int = Query(1, ge=1, le=100)):
    """dislikeを追加（countで複数回分をまとめて送信可能、最大100）"""
    with SessionLocal() as db:
        db.execute(
            text("UPDATE comments SET twicome_dislikes_count = twicome_dislikes_count + :count WHERE comment_id = :cid"),
            {"cid": comment_id, "count": count}
        )
        db.commit()
    return {"status": "ok", "added": count}


