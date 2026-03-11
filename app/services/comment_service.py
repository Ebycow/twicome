"""
コメント閲覧・ページネーションの業務ロジック。

user_comments_page（HTML）と user_comments_api（JSON）の両ハンドラが
fetch_user_comment_page() を共有する。
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from repositories import comment_repo, user_repo
from services.comment_utils import decorate_comment, split_filter_terms


@dataclass
class CommentPage:
    user: dict
    comments: list[dict]
    total: int
    page: int
    pages: int
    page_title: str
    filters: dict
    vod_options: list[dict] = field(default_factory=list)
    owner_options: list[dict] = field(default_factory=list)


def fetch_user_comment_page(
    db,
    login: str,
    platform: str,
    *,
    user: Optional[dict] = None,
    vod_id: Optional[int] = None,
    owner_user_id: Optional[int] = None,
    q: Optional[str] = None,
    exclude_q: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "created_at",
    cursor: Optional[str] = None,
    load_meta: bool = False,
) -> CommentPage:
    """
    ユーザーのコメント一覧ページデータを返す。
    user が存在しない場合は ValueError を raise する。

    user を渡すと find_user クエリをスキップできる（ルーター側で取得済みの場合）。
    load_meta=True のとき vod_options / owner_options を取得する（HTML ページ用）。
    """
    if user is None:
        user = user_repo.find_user(db, login, platform)
    if user is None:
        raise ValueError(f"ユーザが見つかりませんでした: {platform}/{login}")

    uid = user["user_id"]
    exclude_terms = split_filter_terms(exclude_q)
    page_title = "コメント一覧"

    # ── メタ情報（HTML ページのみ）───────────────────────────────────────────
    vod_options: list[dict] = []
    owner_options: list[dict] = []
    if load_meta:
        vod_options = user_repo.fetch_user_vod_options(db, uid, owner_user_id)
        owner_options = user_repo.fetch_user_owner_options(db, uid)

    # ── カーソルページネーション ─────────────────────────────────────────────
    if cursor:
        cursor_row = comment_repo.find_comment_by_id(db, cursor)
        if cursor_row:
            cursor_vod_id = cursor_row["vod_id"]
            cursor_body = cursor_row.get("body", "")
            page_title = f"{cursor_body[:20]}{'...' if len(cursor_body) > 20 else ''} の個別ページ"
            total = comment_repo.count_comments_in_vod(db, cursor_vod_id)
            cursor_pos = comment_repo.get_cursor_position(db, cursor_vod_id, sort, cursor_row)
            half = page_size // 2
            offset = max(0, cursor_pos - half)
            page = (offset // page_size) + 1
            rows = comment_repo.fetch_comments_in_vod(
                db, cursor_vod_id, sort=sort, limit=page_size, offset=offset
            )
            pages = 0  # カーソルモードではページ数を返さない
        else:
            # カーソルが見つからない場合はフォールバック
            total = comment_repo.count_comments(
                db, uid, vod_id=vod_id, owner_user_id=owner_user_id,
                q=q, exclude_terms=exclude_terms,
            )
            offset = 0
            pages = max(1, math.ceil(total / page_size)) if total > 0 else 0
            rows = comment_repo.fetch_comments(
                db, uid, vod_id=vod_id, owner_user_id=owner_user_id,
                q=q, exclude_terms=exclude_terms, sort=sort,
                limit=page_size, offset=offset,
            )
    else:
        # ── 通常ページネーション ─────────────────────────────────────────────
        total = comment_repo.count_comments(
            db, uid, vod_id=vod_id, owner_user_id=owner_user_id,
            q=q, exclude_terms=exclude_terms,
        )
        pages = max(1, math.ceil(total / page_size)) if total > 0 else 0
        page = min(page, pages) if pages else 1
        offset = (page - 1) * page_size
        rows = comment_repo.fetch_comments(
            db, uid, vod_id=vod_id, owner_user_id=owner_user_id,
            q=q, exclude_terms=exclude_terms, sort=sort,
            limit=page_size, offset=offset,
        )

    now = datetime.now(timezone.utc)
    comments = [decorate_comment(row, now) for row in rows]

    return CommentPage(
        user=user,
        comments=comments,
        total=total,
        page=page,
        pages=pages,
        page_title=page_title,
        vod_options=vod_options,
        owner_options=owner_options,
        filters={
            "platform": platform,
            "vod_id": vod_id,
            "owner_user_id": owner_user_id,
            "q": q,
            "exclude_q": exclude_q,
            "page_size": page_size,
            "sort": sort,
            "cursor": cursor,
        },
    )
