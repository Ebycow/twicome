from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from core.config import DEFAULT_PLATFORM
from core.db import SessionLocal
from core.templates import templates
from repositories import stats_repo, user_repo
from services import stats_service

router = APIRouter()


@router.get("/u/{login}/stats", response_class=HTMLResponse)
def user_stats_page(
    request: Request,
    login: str,
    platform: str = Query(DEFAULT_PLATFORM),
):
    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)

        if not user_row:
            return templates.TemplateResponse(
                "user_stats.html",
                {
                    "request": request,
                    "error": f"ユーザが見つかりませんでした: {platform}/{login}",
                    "user": None,
                    "stats": [],
                    "owners_stats": [],
                    "owners_total_comments": 0,
                    "impact_stats": [],
                    "impact_total": None,
                    "cn_scores": None,
                    "cn_status_dist": {},
                },
                status_code=404,
            )

        uid = user_row["user_id"]
        total_comments = stats_repo.count_user_comments(db, uid)
        stats = stats_service.build_hourly_stats(db, uid)
        weekday_stats = stats_service.build_weekday_stats(db, uid)
        owners_stats = stats_service.build_owners_stats(db, uid, total_comments)
        cn_scores = stats_service.build_cn_scores(db, uid)
        cn_status_dist = stats_repo.fetch_cn_status_distribution(db, uid)
        impact_stats, impact_total = stats_service.build_impact_stats(db, uid)

    return templates.TemplateResponse(
        "user_stats.html",
        {
            "request": request,
            "error": None,
            "user": user_row,
            "stats": stats,
            "weekday_stats": weekday_stats,
            "owners_stats": owners_stats,
            "owners_total_comments": total_comments,
            "impact_stats": impact_stats,
            "impact_total": impact_total,
            "cn_scores": cn_scores,
            "cn_status_dist": cn_status_dist,
            "platform": platform,
        },
    )
