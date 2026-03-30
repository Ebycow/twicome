from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

import clients.faiss as faiss_search
from core.config import DEFAULT_PLATFORM
from core.db import SessionLocal
from core.templates import templates
from repositories import comment_repo, stats_repo, user_repo
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
                    "platform": platform,
                    "stats": [],
                    "weekday_stats": [],
                    "owners_stats": [],
                    "owners_total_comments": 0,
                    "impact_stats": [],
                    "impact_total": None,
                    "cn_scores": None,
                    "cn_status_dist": {},
                    "comment_clusters": None,
                    "recent_broadcaster_stats": None,
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
        recent_broadcaster_stats = stats_service.build_recent_broadcaster_stats(db, uid)

        # FAISSクラスタ（インデックスがない場合はNone）
        comment_clusters = None
        try:
            raw_clusters = faiss_search.get_clusters(login, n_clusters=8)
            if raw_clusters:
                all_rep_ids = [cid for cl in raw_clusters for cid in cl["representative_ids"]]
                bodies = comment_repo.fetch_comment_bodies_by_ids(db, all_rep_ids)
                comment_clusters = [
                    {
                        "size": cl["size"],
                        "representatives": [bodies[cid] for cid in cl["representative_ids"] if cid in bodies],
                    }
                    for cl in raw_clusters
                ]
        except Exception:
            pass

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
            "comment_clusters": comment_clusters,
            "recent_broadcaster_stats": recent_broadcaster_stats,
        },
    )
