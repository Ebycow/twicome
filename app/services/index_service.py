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


def build_app_stats(db) -> dict:
    """トップページヒーロー用のアプリ統計を返す。"""
    raw = user_repo.fetch_app_stats(db)
    active_commenters = int(raw.get("active_commenters") or 0)
    total_vods = int(raw.get("total_vods") or 0)
    total_comments = int(raw.get("total_comments") or 0)
    tracked_streamers = int(raw.get("tracked_streamers") or 0)

    return {
        "items": [
            {
                "label": "コメント数",
                "value": f"{total_comments:,}",
                "suffix": "comments",
                "tone": "primary",
                "description": "収録している総コメント数",
            },
            {
                "label": "ユーザ数",
                "value": f"{active_commenters:,}",
                "suffix": "users",
                "tone": "warm",
                "description": "コメントが見つかるユーザ",
                "link": "/users",
            },
            {
                "label": "VOD数",
                "value": f"{total_vods:,}",
                "suffix": "VODs",
                "tone": "cool",
                "description": "横断検索できる配信",
                "link": "/vods",
            },
            {
                "label": "配信者数",
                "value": f"{tracked_streamers:,}",
                "suffix": "streamers",
                "tone": "neutral",
                "description": "VOD収集の対象になっている配信者",
            },
        ]
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
    app_stats = build_app_stats(db)
    placeholder_login = DEFAULT_LOGIN or "sample_user"
    placeholder_user = user_repo.find_user(db, placeholder_login, "twitch") if DEFAULT_LOGIN else None
    placeholder_display_name = (placeholder_user or {}).get("display_name") or "表示名"
    return {
        "selected_login": DEFAULT_LOGIN or "",
        "selected_login_for_links": DEFAULT_LOGIN or "",
        "login_search_placeholder": f"例: {placeholder_login} / {placeholder_display_name}",
        "popular_comments": popular_comments,
        "quick_links": landing["quick_links"],
        "streamers": landing["streamers"],
        "app_stats": app_stats,
        "data_version": data_version,
        "service_worker_cache_name": SERVICE_WORKER_CACHE_NAME,
    }
