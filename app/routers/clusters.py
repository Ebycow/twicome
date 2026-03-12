from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import faiss_search
from core.config import DEFAULT_PLATFORM
from core.db import SessionLocal
from core.templates import templates
from repositories import comment_repo, user_repo
from services.comment_utils import decorate_comment
from datetime import datetime, timezone

router = APIRouter()


class SubclusterRequest(BaseModel):
    centroid: list[float]
    n_members: int
    n_clusters: int = 4


def _build_cluster_display(raw_clusters, db):
    """クラスタリスト + DB本文取得 → テンプレート用データに変換"""
    if not raw_clusters:
        return []
    all_rep_ids = [cid for cl in raw_clusters for cid in cl["representative_ids"]]
    bodies = comment_repo.fetch_comment_bodies_by_ids(db, all_rep_ids)
    return [
        {
            "size": cl["size"],
            "centroid": cl["centroid"],
            "representatives": [bodies[cid] for cid in cl["representative_ids"] if cid in bodies],
        }
        for cl in raw_clusters
    ]


@router.get("/u/{login}/clusters", response_class=HTMLResponse)
def cluster_explorer(
    request: Request,
    login: str,
    platform: str = Query(DEFAULT_PLATFORM),
    n_clusters: int = Query(8, ge=2, le=32),
):
    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)
        if not user_row:
            return templates.TemplateResponse(
                "user_clusters.html",
                {
                    "request": request,
                    "error": f"ユーザが見つかりませんでした: {login}",
                    "user": None,
                    "clusters": [],
                    "n_clusters": n_clusters,
                    "login": login,
                    "platform": platform,
                },
                status_code=404,
            )

        clusters = []
        error = None
        try:
            raw = faiss_search.get_clusters(login, n_clusters=n_clusters)
            clusters = _build_cluster_display(raw, db)
        except Exception as e:
            error = str(e)

    return templates.TemplateResponse(
        "user_clusters.html",
        {
            "request": request,
            "error": error,
            "user": user_row,
            "clusters": clusters,
            "n_clusters": n_clusters,
            "login": login,
            "platform": platform,
        },
    )


@router.post("/u/{login}/cluster-comments", response_class=HTMLResponse)
def cluster_comments_page(
    request: Request,
    login: str,
    centroid: str = Form(...),
    n_members: int = Form(...),
    platform: str = Form(DEFAULT_PLATFORM),
):
    """クラスタ内のコメント一覧ページ（フォームPOSTで開く）"""
    import json as _json
    centroid_list = _json.loads(centroid)

    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)
        comments = []
        error = None
        try:
            ids = faiss_search.get_cluster_members(login, centroid_list, n_members)
            if ids:
                now = datetime.now(timezone.utc)
                raw = comment_repo.fetch_comments_by_ids(db, ids)
                comments = [decorate_comment(c, now) for c in raw]
        except Exception as e:
            error = str(e)

    return templates.TemplateResponse(
        "cluster_comments.html",
        {
            "request": request,
            "user": user_row,
            "login": login,
            "platform": platform,
            "comments": comments,
            "error": error,
            "n_members": n_members,
        },
    )


@router.post("/u/{login}/clusters/subcluster")
def subcluster_api(login: str, req: SubclusterRequest):
    """AJAX用: 親クラスタの重心からサブクラスタを返す (JSON)"""
    with SessionLocal() as db:
        try:
            raw = faiss_search.get_subclusters(login, req.centroid, req.n_members, req.n_clusters)
            subclusters = _build_cluster_display(raw, db)
            return JSONResponse({"subclusters": subclusters})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
