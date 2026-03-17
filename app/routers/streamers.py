"""配信者一覧ルーター。"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.db import SessionLocal
from core.templates import templates
from repositories import user_repo

router = APIRouter()


@router.get("/streamers", response_class=HTMLResponse)
def streamers_page(request: Request):
    with SessionLocal() as db:
        streamers = user_repo.fetch_streamers(db)
    return templates.TemplateResponse(
        "streamers.html",
        {
            "request": request,
            "streamers": streamers,
        },
    )
