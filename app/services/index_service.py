"""トップページのデータ組み立てロジック。

comments.py ルーターから抽出したもの。
"""

from core.config import DEFAULT_LOGIN, QUICK_LINK_LOGINS, SERVICE_WORKER_CACHE_NAME
from repositories import comment_repo, user_repo
from services.comment_utils import get_comment_body_html


def build_quick_links(db) -> list[dict]:
    """QUICK_LINK_LOGINS に基づくクイックリンク一覧。"""
    if not QUICK_LINK_LOGINS:
        return []
    rows = user_repo.fetch_quick_links(db, QUICK_LINK_LOGINS)
    quick_link_by_login = {row["login"]: row for row in rows}

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


def build_landing_data(db) -> dict:
    """クイックリンクと配信者一覧（キャッシュ対象の軽量データ）。"""
    return {
        "quick_links": build_quick_links(db),
        "streamers": user_repo.fetch_streamers(db),
    }


def build_popular_comments(db) -> list[dict]:
    """人気コメントランキング（HTML キャッシュに含める）。"""
    rows = comment_repo.fetch_popular_comments(db, limit=20)
    result = []
    for row in rows:
        r = dict(row)
        r["body_html"] = get_comment_body_html(r)
        r.pop("raw_json", None)
        r.pop("body_html_version", None)
        result.append(r)
    return result


def build_index_context(db, data_version: str) -> dict:
    """トップページテンプレートに渡すコンテキスト全体。"""
    landing = build_landing_data(db)
    popular_comments = build_popular_comments(db)
    return {
        "selected_login": DEFAULT_LOGIN or "",
        "selected_login_for_links": "__LOGIN_PLACEHOLDER__",
        "popular_comments": popular_comments,
        "quick_links": landing["quick_links"],
        "streamers": landing["streamers"],
        "data_version": data_version,
        "service_worker_cache_name": SERVICE_WORKER_CACHE_NAME,
    }
