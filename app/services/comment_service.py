"""コメント閲覧・ページネーションの業務ロジック。

user_comments_page（HTML）と user_comments_api（JSON）の両ハンドラが fetch_user_comment_page() を共有する。
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

from repositories import comment_repo, user_repo
from services.comment_utils import decorate_comment, split_filter_terms

JST = timezone(timedelta(hours=9))
_EXPORT_LIMIT = 5000


def _parse_jst_date_to_utc_range(
    date_from: str | None,
    date_to: str | None,
) -> tuple[datetime | None, datetime | None]:
    """YYYY-MM-DD (JST) の日付文字列を UTC datetime の範囲に変換する。

    date_from → その日の 00:00:00 JST (= UTC -9h)
    date_to   → 翌日の 00:00:00 JST (exclusive, = UTC -9h)
    """
    date_from_utc: datetime | None = None
    date_to_utc: datetime | None = None
    if date_from:
        try:
            d = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=JST)
            date_from_utc = d.astimezone(UTC).replace(tzinfo=None)
        except ValueError:
            pass
    if date_to:
        try:
            d = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=JST)
            date_to_utc = (d + timedelta(days=1)).astimezone(UTC).replace(tzinfo=None)
        except ValueError:
            pass
    return date_from_utc, date_to_utc


@dataclass
class CommentPage:
    """コメント一覧ページのデータを保持するデータクラス。"""

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
    user: dict | None = None,
    vod_id: int | None = None,
    owner_user_id: int | None = None,
    q: str | None = None,
    exclude_q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "created_at",
    cursor: str | None = None,
    load_meta: bool = False,
) -> CommentPage:
    """ユーザーのコメント一覧ページデータを返す。

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
    date_from_utc, date_to_utc = _parse_jst_date_to_utc_range(date_from, date_to)

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
            rows = comment_repo.fetch_comments_in_vod(db, cursor_vod_id, limit=page_size, offset=offset)
            pages = 0  # カーソルモードではページ数を返さない
        else:
            # カーソルが見つからない場合はフォールバック
            total = comment_repo.count_comments(
                db,
                uid,
                vod_id=vod_id,
                owner_user_id=owner_user_id,
                q=q,
                exclude_terms=exclude_terms,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
            )
            offset = 0
            pages = max(1, math.ceil(total / page_size)) if total > 0 else 0
            rows = comment_repo.fetch_comments(
                db,
                uid,
                vod_id=vod_id,
                owner_user_id=owner_user_id,
                q=q,
                exclude_terms=exclude_terms,
                sort=sort,
                limit=page_size,
                offset=offset,
                date_from_utc=date_from_utc,
                date_to_utc=date_to_utc,
            )
    else:
        # ── 通常ページネーション ─────────────────────────────────────────────
        total = comment_repo.count_comments(
            db,
            uid,
            vod_id=vod_id,
            owner_user_id=owner_user_id,
            q=q,
            exclude_terms=exclude_terms,
            date_from_utc=date_from_utc,
            date_to_utc=date_to_utc,
        )
        pages = max(1, math.ceil(total / page_size)) if total > 0 else 0
        page = min(page, pages) if pages else 1
        offset = (page - 1) * page_size
        rows = comment_repo.fetch_comments(
            db,
            uid,
            vod_id=vod_id,
            owner_user_id=owner_user_id,
            q=q,
            exclude_terms=exclude_terms,
            sort=sort,
            limit=page_size,
            offset=offset,
            date_from_utc=date_from_utc,
            date_to_utc=date_to_utc,
        )

    now = datetime.now(UTC)
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
            "date_from": date_from,
            "date_to": date_to,
            "page_size": page_size,
            "sort": sort,
            "cursor": cursor,
        },
    )


def export_user_comments(
    db,
    login: str,
    platform: str,
    *,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    exclude_q: str | None = None,
    owner_user_id: int | None = None,
    vod_id: int | None = None,
) -> list[dict]:
    """エクスポート用にコメントを最大 _EXPORT_LIMIT 件取得する。

    date を指定すると date_from/date_to より優先して単日フィルタになる。
    """
    user = user_repo.find_user(db, login, platform)
    if user is None:
        raise ValueError(f"ユーザが見つかりませんでした: {platform}/{login}")

    uid = user["user_id"]
    exclude_terms = split_filter_terms(exclude_q)

    # date は単日指定 → date_from/to に展開
    effective_from = date if date else date_from
    effective_to = date if date else date_to
    date_from_utc, date_to_utc = _parse_jst_date_to_utc_range(effective_from, effective_to)

    rows = comment_repo.fetch_comments(
        db,
        uid,
        vod_id=vod_id,
        owner_user_id=owner_user_id,
        q=q,
        exclude_terms=exclude_terms,
        sort="created_at",
        limit=_EXPORT_LIMIT,
        offset=0,
        date_from_utc=date_from_utc,
        date_to_utc=date_to_utc,
    )
    now = datetime.now(UTC)
    return [decorate_comment(row, now) for row in rows]
