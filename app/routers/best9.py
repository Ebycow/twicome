import base64
import zlib
from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from core.db import SessionLocal
from core.templates import templates
from services.comment_utils import BODY_HTML_RENDER_VERSION, _build_comment_body_select_sql, decorate_comment

router = APIRouter()
_COMMENT_BODY_SELECT_SQL = _build_comment_body_select_sql("c")


def _decompress_ids(z: str) -> list[str]:
    """deflate-raw + base64url で圧縮された ID リストを復元"""
    pad = (4 - len(z) % 4) % 4
    data = base64.urlsafe_b64decode(z + "=" * pad)
    decompressed = zlib.decompress(data, wbits=-15)
    return [i.strip() for i in decompressed.decode("utf-8").split(",") if i.strip()][:9]


@router.get("/best9", response_class=HTMLResponse)
def best9_page(
    request: Request,
    z: str | None = Query(None),    # 圧縮版（新形式）
    ids: str | None = Query(None),  # レガシー互換
    login: str | None = Query(None),
):
    if z:
        try:
            id_list = _decompress_ids(z)
        except Exception:
            return HTMLResponse("URLが壊れています", status_code=400)
    elif ids:
        id_list = [i.strip() for i in ids.split(",") if i.strip()][:9]
    else:
        return HTMLResponse("IDが指定されていません", status_code=400)

    if not id_list:
        return HTMLResponse("IDが指定されていません", status_code=400)

    placeholders = ", ".join([f":id_{i}" for i in range(len(id_list))])
    params = {f"id_{i}": cid for i, cid in enumerate(id_list)}

    with SessionLocal() as db:
        rows = db.execute(
            text(f"""
                SELECT
                    c.comment_id,
                    c.vod_id,
                    c.offset_seconds,
                    c.comment_created_at_utc,
                    c.commenter_login_snapshot,
                    c.commenter_display_name_snapshot,
                    {_COMMENT_BODY_SELECT_SQL},
                    c.user_color,
                    c.bits_spent,
                    c.twicome_likes_count,
                    c.twicome_dislikes_count,
                    v.title AS vod_title,
                    v.url AS vod_url,
                    v.youtube_url AS youtube_url,
                    v.created_at_utc AS vod_created_at_utc,
                    u.login AS owner_login,
                    u.display_name AS owner_display_name
                FROM comments c
                JOIN vods v ON v.vod_id = c.vod_id
                JOIN users u ON u.user_id = v.owner_user_id
                WHERE c.comment_id IN ({placeholders})
            """),
            {**params, "body_html_version": BODY_HTML_RENDER_VERSION},
        ).mappings().all()

    now = datetime.utcnow()
    comment_map = {r["comment_id"]: decorate_comment(r, now) for r in rows}
    # id_list の順番を維持
    comments = [comment_map[cid] for cid in id_list if cid in comment_map]

    commenter_login = login or (comments[0]["commenter_login_snapshot"] if comments else "unknown")

    return templates.TemplateResponse(
        "best9.html",
        {
            "request": request,
            "comments": comments,
            "commenter_login": commenter_login,
            "root_path": request.scope.get("root_path", ""),
        },
    )
