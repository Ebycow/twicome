"""VOD 検索・VOD コメント一覧ルーター。"""

import math

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from core.db import SessionLocal
from core.templates import templates
from repositories import user_repo, vod_repo
from services.vod_service import fetch_vod_comment_page

router = APIRouter()


def _parse_int(value: str | None) -> int | None:
    if value and value.strip():
        try:
            return int(value)
        except ValueError:
            pass
    return None


# ── VOD 一覧ページ ────────────────────────────────────────────────────────────


@router.get("/vods", response_class=HTMLResponse)
def vods_page(request: Request):
    with SessionLocal() as db:
        streamers = user_repo.fetch_streamers(db)
    return templates.TemplateResponse(
        "vods.html",
        {
            "request": request,
            "streamers": streamers,
        },
    )


# ── VOD 一覧 API ──────────────────────────────────────────────────────────────


@router.get("/api/vods", response_class=JSONResponse)
def api_vods(
    q: str | None = Query(None),
    owner_login: str | None = Query(None),
    sort: str = Query("created_at"),
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=10, le=200),
):
    offset = (page - 1) * page_size
    with SessionLocal() as db:
        total = vod_repo.count_vods(db, q=q, owner_login=owner_login)
        items = vod_repo.search_vods(db, q=q, owner_login=owner_login, sort=sort, limit=page_size, offset=offset)

    pages = max(1, math.ceil(total / page_size)) if total > 0 else 0
    # datetime を JST 文字列に変換（JSON シリアライズ用）
    from services.comment_utils import utc_to_jst

    for item in items:
        raw_dt = item.get("created_at_utc")
        if raw_dt:
            try:
                jst_dt = utc_to_jst(raw_dt)
                item["created_at_jst"] = jst_dt.strftime("%Y年%-m月%-d日")
            except Exception:
                item["created_at_jst"] = str(raw_dt)
            item["created_at_utc"] = str(raw_dt)
        else:
            item["created_at_jst"] = None
        if item.get("comment_count") is not None:
            item["comment_count"] = int(item["comment_count"])

    return {
        "total": total,
        "page": page,
        "pages": pages,
        "page_size": page_size,
        "items": items,
    }


# ── VOD コメント一覧ページ ────────────────────────────────────────────────────


@router.get("/vods/{vod_id}", response_class=HTMLResponse)
def vod_comments_page(
    request: Request,
    vod_id: int,
    q: str | None = Query(None),
    exclude_q: str | None = Query(None),
    sort: str = Query("offset"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
):
    with SessionLocal() as db:
        try:
            page_data = fetch_vod_comment_page(
                db,
                vod_id,
                q=q,
                exclude_q=exclude_q,
                sort=sort,
                page=page,
                page_size=page_size,
            )
        except ValueError as e:
            return templates.TemplateResponse(
                "vod_comments.html",
                {
                    "request": request,
                    "vod": None,
                    "comments": [],
                    "page": 1,
                    "pages": 0,
                    "total": 0,
                    "filters": {"q": q, "exclude_q": exclude_q, "sort": sort, "page_size": page_size},
                    "error": str(e),
                },
                status_code=404,
            )

    return templates.TemplateResponse(
        "vod_comments.html",
        {
            "request": request,
            "vod": page_data.vod,
            "comments": page_data.comments,
            "page": page_data.page,
            "pages": page_data.pages,
            "total": page_data.total,
            "filters": page_data.filters,
            "error": None,
        },
    )
