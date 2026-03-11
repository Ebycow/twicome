from typing import Optional

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from cache import (
    get_data_version,
    get_index_html_cache,
    get_index_landing_cache,
    get_index_users_cache,
    get_user_meta_cache,
    set_index_html_cache,
    set_index_landing_cache,
    set_index_users_cache,
    set_user_meta_cache,
)
from core.config import DEFAULT_PLATFORM, FAISS_ENABLED, QUICK_LINK_LOGINS
from core.db import SessionLocal
from core.templates import templates
from repositories import user_repo, vote_repo
from services.comment_service import fetch_user_comment_page
from services.index_service import build_index_context, build_landing_data

router = APIRouter()


# ── ヘルパー ─────────────────────────────────────────────────────────────────

def _parse_int(value: Optional[str]) -> Optional[int]:
    if value and value.strip():
        try:
            return int(value)
        except ValueError:
            pass
    return None


def _load_index_landing() -> dict:
    cached = get_index_landing_cache()
    if cached is not None:
        return cached
    with SessionLocal() as db:
        data = build_landing_data(db)
    set_index_landing_cache(data)
    return data


def _load_index_users() -> list[dict]:
    cached = get_index_users_cache()
    if cached is not None:
        return cached
    with SessionLocal() as db:
        users = user_repo.fetch_index_users(db)
    set_index_users_cache(users)
    return users


def _render_index_html(context: dict) -> str:
    return templates.env.get_template("index.html").render(context)


def _load_user_meta(login: str, uid: int, db) -> Optional[dict]:
    if login not in QUICK_LINK_LOGINS:
        return None
    cached = get_user_meta_cache(login)
    if cached is not None:
        return cached
    meta = {
        "vod_options": user_repo.fetch_user_vod_options(db, uid, None),
        "owner_options": user_repo.fetch_user_owner_options(db, uid),
    }
    set_user_meta_cache(login, meta)
    return meta


# ── インデックスページ ────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    data_version = get_data_version()
    headers = {"X-Twicome-Data-Version": data_version, "Cache-Control": "no-store"}
    cached_html = get_index_html_cache(data_version)
    if cached_html is not None:
        return HTMLResponse(cached_html, headers=headers)
    with SessionLocal() as db:
        context = build_index_context(db, data_version)
    html = _render_index_html(context)
    set_index_html_cache(data_version, html)
    return HTMLResponse(html, headers=headers)


@router.get("/api/meta/data-version", response_class=JSONResponse)
def api_data_version():
    data_version = get_data_version()
    return JSONResponse(
        {"data_version": data_version},
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "X-Twicome-Data-Version": data_version,
        },
    )


@router.get("/api/users/index", response_class=JSONResponse)
def api_users_index():
    return {"users": _load_index_users()}


@router.get("/api/users/commenters", response_class=JSONResponse)
def api_users_commenters(streamer: str = Query(...)):
    with SessionLocal() as db:
        logins = user_repo.fetch_commenters_for_streamer(db, streamer)
    return {"logins": logins}


@router.post("/go")
def go(request: Request, login: str = Form(...), platform: str = Form(DEFAULT_PLATFORM)):
    login = login.strip()
    platform = platform.strip() or DEFAULT_PLATFORM
    target = request.url_for("user_comments_page", login=login)
    return RedirectResponse(url=f"{target}?platform={platform}", status_code=303)


# ── ユーザーコメント一覧 ──────────────────────────────────────────────────────

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
    sort: str = Query("created_at"),
    cursor: Optional[str] = Query(None),
):
    vod_id_int = _parse_int(vod_id)
    owner_user_id_int = _parse_int(owner_user_id)

    with SessionLocal() as db:
        user_row_raw = user_repo.find_user(db, login, platform)
        cached_meta = _load_user_meta(login, user_row_raw["user_id"], db) if user_row_raw else None

        try:
            page_data = fetch_user_comment_page(
                db, login, platform,
                vod_id=vod_id_int, owner_user_id=owner_user_id_int,
                q=q, exclude_q=exclude_q, page=page, page_size=page_size,
                sort=sort, cursor=cursor,
                load_meta=(cached_meta is None),
            )
        except ValueError as e:
            return templates.TemplateResponse(
                "user_comments.html",
                {
                    "request": request,
                    "error": str(e),
                    "user": {"login": login, "display_name": None},
                    "comments": [],
                    "vod_options": [],
                    "owner_options": [],
                    "page": page, "pages": 0, "total": 0,
                    "page_title": "コメント一覧",
                    "filters": {
                        "platform": platform, "vod_id": vod_id_int,
                        "owner_user_id": owner_user_id_int, "q": q,
                        "exclude_q": exclude_q, "page_size": page_size, "sort": sort,
                    },
                    "root_path": request.scope.get("root_path", ""),
                    "faiss_enabled": FAISS_ENABLED,
                },
                status_code=404,
            )

    vod_options = (
        cached_meta["vod_options"] if cached_meta and owner_user_id_int is None
        else page_data.vod_options
    )
    owner_options = cached_meta["owner_options"] if cached_meta else page_data.owner_options

    return templates.TemplateResponse(
        "user_comments.html",
        {
            "request": request,
            "error": None,
            "user": page_data.user,
            "comments": page_data.comments,
            "vod_options": vod_options,
            "owner_options": owner_options,
            "page": page_data.page,
            "pages": page_data.pages,
            "total": page_data.total,
            "filters": page_data.filters,
            "root_path": request.scope.get("root_path", ""),
            "page_title": page_data.page_title,
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
    sort: str = Query("created_at"),
    cursor: Optional[str] = Query(None),
):
    vod_id_int = _parse_int(vod_id)
    owner_user_id_int = _parse_int(owner_user_id)

    with SessionLocal() as db:
        try:
            page_data = fetch_user_comment_page(
                db, login, platform,
                vod_id=vod_id_int, owner_user_id=owner_user_id_int,
                q=q, exclude_q=exclude_q, page=page, page_size=page_size,
                sort=sort, cursor=cursor,
            )
        except ValueError:
            return JSONResponse({"error": "user_not_found"}, status_code=404)

    return {
        "user": page_data.user,
        "total": page_data.total,
        "page": page_data.page,
        "page_size": page_size,
        "items": page_data.comments,
    }


# ── 投票 ──────────────────────────────────────────────────────────────────────

@router.post("/like/{comment_id}")
def like_comment(comment_id: str, count: int = Query(1, ge=1, le=100)):
    with SessionLocal() as db:
        vote_repo.increment_like(db, comment_id, count)
    return {"status": "ok", "added": count}


@router.post("/dislike/{comment_id}")
def dislike_comment(comment_id: str, count: int = Query(1, ge=1, le=100)):
    with SessionLocal() as db:
        vote_repo.increment_dislike(db, comment_id, count)
    return {"status": "ok", "added": count}
