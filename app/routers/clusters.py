from datetime import UTC, datetime

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import clients.faiss as faiss_search
from core.config import DEFAULT_PLATFORM
from core.db import SessionLocal
from core.templates import templates
from repositories import comment_repo, user_repo
from services.comment_utils import decorate_comment

router = APIRouter()


class SubclusterRequest(BaseModel):
    """サブクラスタリングリクエスト（クラスタ探索ページ用）。"""

    centroid: list[float]
    n_members: int
    n_clusters: int = 4
    member_indices: list[int] | None = None


def _build_cluster_display(raw_clusters, db):
    """クラスタリスト + DB本文取得 → テンプレート用データに変換"""
    if not raw_clusters:
        return []
    all_rep_ids = [cid for cl in raw_clusters for cid in cl["representative_ids"]]
    bodies = comment_repo.fetch_comment_bodies_by_ids(db, all_rep_ids)
    result = []
    for cl in raw_clusters:
        entry: dict = {
            "size": cl["size"],
            "centroid": cl["centroid"],
            "representatives": [bodies[cid] for cid in cl["representative_ids"] if cid in bodies],
        }
        if cl.get("member_indices") is not None:
            entry["member_indices"] = cl["member_indices"]
        result.append(entry)
    return result


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
        except (RuntimeError, ValueError) as e:
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


@router.get("/u/{login}/cluster-comments", response_class=HTMLResponse)
def cluster_comments_page(
    request: Request,
    login: str,
    n_clusters: int = Query(8, ge=2, le=32),
    path: str = Query(...),
    platform: str = Query(DEFAULT_PLATFORM),
):
    """クラスタ内のコメント一覧ページ（共有可能なGET URL）

    path: カンマ区切りの0始まりインデックス列。例: "2" または "2,1"
    最初のインデックスはトップレベルクラスタ、以降はサブクラスタ（4分割固定）のインデックス。
    """
    try:
        indices = [int(x) for x in path.split(",")]
    except ValueError:
        indices = []

    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)
        comments = []
        error = None
        size = 0
        try:
            if not indices:
                raise ValueError("path が無効です")
            raw_clusters = faiss_search.get_clusters(login, n_clusters=n_clusters)
            if not raw_clusters or not (0 <= indices[0] < len(raw_clusters)):
                raise ValueError("クラスタが見つかりませんでした")
            cl = raw_clusters[indices[0]]
            centroid, size = cl["centroid"], cl["size"]
            member_indices = cl.get("member_indices")
            for idx in indices[1:]:
                subclusters = faiss_search.get_subclusters(
                    login, centroid, size, n_clusters=4, member_indices=member_indices
                )
                if not subclusters or not (0 <= idx < len(subclusters)):
                    raise ValueError("サブクラスタが見つかりませんでした")
                cl = subclusters[idx]
                centroid, size = cl["centroid"], cl["size"]
                member_indices = cl.get("member_indices")
            ids = faiss_search.get_cluster_members(login, centroid, size, member_indices=member_indices)
            if ids:
                now = datetime.now(UTC)
                raw = comment_repo.fetch_comments_by_ids(db, ids)
                comments = [decorate_comment(c, now) for c in raw]
        except (RuntimeError, ValueError) as e:
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
            "n_members": size,
            "cluster_path": path,
            "n_clusters_top": n_clusters,
        },
    )


@router.post("/u/{login}/cluster-comments", response_class=HTMLResponse)
def cluster_comments_page_post(
    request: Request,
    login: str,
    centroid: str = Form(...),
    n_members: int = Form(...),
    platform: str = Form(DEFAULT_PLATFORM),
):
    """クラスタ内のコメント一覧ページ（後方互換POST版）"""
    import json as _json

    centroid_list = _json.loads(centroid)

    with SessionLocal() as db:
        user_row = user_repo.find_user(db, login, platform)
        comments = []
        error = None
        try:
            ids = faiss_search.get_cluster_members(login, centroid_list, n_members)
            if ids:
                now = datetime.now(UTC)
                raw = comment_repo.fetch_comments_by_ids(db, ids)
                comments = [decorate_comment(c, now) for c in raw]
        except (RuntimeError, ValueError) as e:
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
            raw = faiss_search.get_subclusters(
                login, req.centroid, req.n_members, req.n_clusters, member_indices=req.member_indices
            )
            subclusters = _build_cluster_display(raw, db)
            return JSONResponse({"subclusters": subclusters})
        except (RuntimeError, ValueError) as e:
            return JSONResponse({"error": str(e)}, status_code=500)
