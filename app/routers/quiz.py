import random

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from core.config import DEFAULT_PLATFORM
from core.db import SessionLocal
from core.templates import templates
from repositories import comment_repo, user_repo
from services.comment_utils import get_comment_body_html

router = APIRouter()


@router.get("/u/{login}/quiz", response_class=HTMLResponse)
def quiz_page(
    request: Request,
    login: str,
    platform: str = Query(DEFAULT_PLATFORM),
):
    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)
        if not user_row:
            return templates.TemplateResponse(
                "quiz.html",
                {
                    "request": request,
                    "error": "ユーザが見つかりませんでした",
                    "user": None,
                    "comment_count": 0,
                    "platform": platform,
                },
                status_code=404,
            )
        comment_count = comment_repo.count_comments(db, user_row["user_id"])

    return templates.TemplateResponse(
        "quiz.html",
        {
            "request": request,
            "error": None,
            "user": user_row,
            "comment_count": comment_count,
            "platform": platform,
        },
    )


@router.get("/api/u/{login}/quiz/start")
def quiz_start_api(
    login: str,
    platform: str = Query(DEFAULT_PLATFORM),
    count: int = Query(30, ge=10, le=100),
):
    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)
        if not user_row:
            return JSONResponse({"error": "user_not_found"}, status_code=404)

        uid = user_row["user_id"]
        target_count = count // 2
        other_count = count - target_count

        target_comments = comment_repo.fetch_quiz_target_comments(db, uid, target_count)
        other_comments = comment_repo.fetch_quiz_other_comments(db, uid, other_count)

        questions = []
        for r in target_comments:
            questions.append(
                {
                    "body": r["body"],
                    "body_html": get_comment_body_html(r),
                    "is_target": True,
                    "actual_commenter_display_name": r["commenter_display_name_snapshot"]
                    or r["commenter_login_snapshot"],
                    "vod_title": r["vod_title"],
                    "user_color": r["user_color"],
                }
            )
        for r in other_comments:
            questions.append(
                {
                    "body": r["body"],
                    "body_html": get_comment_body_html(r),
                    "is_target": False,
                    "actual_commenter_display_name": r["commenter_display_name_snapshot"]
                    or r["commenter_login_snapshot"],
                    "vod_title": r["vod_title"],
                    "user_color": r["user_color"],
                }
            )

        random.shuffle(questions)

    return {
        "user": user_row,
        "total": len(questions),
        "questions": questions,
    }
