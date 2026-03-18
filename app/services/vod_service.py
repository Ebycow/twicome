"""VOD コメント閲覧ページの業務ロジック。"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from repositories import comment_repo, vod_repo
from services.comment_utils import decorate_comment, seconds_to_hms, split_filter_terms


@dataclass
class VodCommentPage:
    """VOD コメント一覧ページのデータを保持するデータクラス。"""

    vod: dict
    comments: list[dict]
    total: int
    page: int
    pages: int
    filters: dict


def _decorate_vod(vod: dict) -> dict:
    """VOD dict にフロントエンド向けの補助フィールドを追加する。"""
    out = dict(vod)
    length = vod.get("length_seconds") or 0
    out["length_hms"] = seconds_to_hms(length) if length else None
    created = vod.get("created_at_utc")
    if created:
        from services.comment_utils import utc_to_jst

        jst_dt = utc_to_jst(created)
        out["created_at_jst"] = jst_dt.strftime("%Y-%m-%d %H:%M")
    else:
        out["created_at_jst"] = None
    return out


def fetch_vod_comment_page(
    db,
    vod_id: int,
    *,
    q: str | None = None,
    exclude_q: str | None = None,
    sort: str = "offset",
    page: int = 1,
    page_size: int = 50,
) -> VodCommentPage:
    """VOD のコメント一覧ページデータを返す。

    VOD が存在しない場合は ValueError を raise する。
    """
    vod = vod_repo.fetch_vod_by_id(db, vod_id)
    if vod is None:
        raise ValueError(f"VOD が見つかりませんでした: {vod_id}")

    vod = _decorate_vod(vod)
    exclude_terms = split_filter_terms(exclude_q)

    total = comment_repo.count_vod_comments_filtered(db, vod_id, q=q, exclude_terms=exclude_terms)
    pages = max(1, math.ceil(total / page_size)) if total > 0 else 0
    page = min(page, pages) if pages else 1
    offset = (page - 1) * page_size

    rows = comment_repo.fetch_vod_comments_filtered(
        db,
        vod_id,
        q=q,
        exclude_terms=exclude_terms,
        sort=sort,
        limit=page_size,
        offset=offset,
    )

    now = datetime.now(UTC)
    comments = [decorate_comment(row, now) for row in rows]

    return VodCommentPage(
        vod=vod,
        comments=comments,
        total=total,
        page=page,
        pages=pages,
        filters={
            "q": q,
            "exclude_q": exclude_q,
            "sort": sort,
            "page_size": page_size,
        },
    )
