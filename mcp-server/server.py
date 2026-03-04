"""Twicome MCP Server

Twicome の HTTP API を MCP ツールとして公開する。

環境変数:
    TWICOME_BASE_URL: Twicome API のベース URL (デフォルト: http://localhost:8000/twicome)
    CF_CLIENT_ID: Cloudflare Access サービストークンのクライアント ID (任意)
    CF_CLIENT_SECRET: Cloudflare Access サービストークンのシークレット (任意)
"""

import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.getenv("TWICOME_BASE_URL", "http://localhost:8000/twicome").rstrip("/")

_cf_client_id = os.getenv("CF_CLIENT_ID", "")
_cf_client_secret = os.getenv("CF_CLIENT_SECRET", "")

_HEADERS: dict = {}
if _cf_client_id and _cf_client_secret:
    _HEADERS["CF-Access-Client-Id"] = _cf_client_id
    _HEADERS["CF-Access-Client-Secret"] = _cf_client_secret

mcp = FastMCP("twicome")


def _request(path: str, params: dict) -> dict:
    """Twicome API に GET リクエストを送信する。"""
    # None 値のパラメータを除去
    clean_params = {k: v for k, v in params.items() if v is not None}
    try:
        resp = httpx.get(f"{BASE_URL}{path}", params=clean_params, headers=_HEADERS, timeout=30.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            try:
                body = e.response.json()
                raise ValueError(body.get("error", "not_found"))
            except Exception:
                raise ValueError("not_found")
        raise RuntimeError(f"API error: {e.response.status_code} {e.response.text}")
    except httpx.RequestError as e:
        raise RuntimeError(f"接続エラー: {e}。TWICOME_BASE_URL={BASE_URL} を確認してください。")


def _format_comment(item: dict) -> str:
    """コメント1件をテキスト形式に整形する。"""
    lines = []
    # タイムスタンプと配信者
    created = item.get("comment_created_at_utc", "")
    if created:
        created = created.replace("T", " ").replace("Z", "") + " UTC"
    owner = item.get("owner_display_name") or item.get("owner_login", "")
    vod_title = item.get("vod_title", "")
    offset = item.get("offset_hms") or ""

    lines.append(f"[{created}] @{owner} の配信「{vod_title}」 ({offset})")
    lines.append(f"  {item.get('body', '')}")

    # いいね/低評価
    likes = item.get("twicome_likes_count", 0)
    dislikes = item.get("twicome_dislikes_count", 0)
    if likes or dislikes:
        lines.append(f"  👍 {likes}  👎 {dislikes}")

    # Community Note
    cn_body = item.get("community_note_body")
    if cn_body:
        lines.append(f"  [Community Note] {cn_body}")

    lines.append(f"  comment_id: {item.get('comment_id', '')}")
    return "\n".join(lines)


@mcp.tool()
def get_user_comments(
    login: str,
    q: Optional[str] = None,
    exclude_q: Optional[str] = None,
    vod_id: Optional[str] = None,
    owner_user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "created_at",
) -> str:
    """Twicome ユーザーのコメントを検索・取得する。

    Args:
        login: コメンターのログイン名 (例: "username123")
        q: テキスト検索クエリ。コメント本文の部分一致検索 (例: "草")
        exclude_q: 除外キーワード。カンマ区切りで複数指定可 (例: "広告,宣伝")
        vod_id: 特定の VOD ID でフィルタ
        owner_user_id: 配信者の user_id でフィルタ
        page: ページ番号 (1以上)
        page_size: 1ページのコメント数 (10〜200、デフォルト: 50)
        sort: ソート順。"created_at" | "likes" | "dislikes" | "community_note" | "danger" | "random"

    Returns:
        ユーザー情報とコメント一覧のテキスト
    """
    data = _request(
        f"/api/u/{login}",
        {
            "q": q,
            "exclude_q": exclude_q,
            "vod_id": vod_id,
            "owner_user_id": owner_user_id,
            "page": page,
            "page_size": page_size,
            "sort": sort,
        },
    )

    user = data.get("user", {})
    total = data.get("total", 0)
    items = data.get("items", [])

    lines = [
        f"ユーザー: {user.get('display_name', login)} (@{user.get('login', login)})",
        f"総コメント数: {total} 件 (ページ {page}、{len(items)} 件表示)",
        "",
    ]

    if not items:
        lines.append("コメントが見つかりませんでした。")
    else:
        for item in items:
            lines.append(_format_comment(item))
            lines.append("")

    return "\n".join(lines)


@mcp.tool()
def get_commenters_for_streamer(streamer: str) -> str:
    """配信者の VOD にコメントしたユーザー一覧を取得する。

    Args:
        streamer: 配信者のログイン名 (例: "streamer_login")

    Returns:
        コメンターのログイン名リスト
    """
    data = _request("/api/users/commenters", {"streamer": streamer})
    logins = data.get("logins", [])

    if not logins:
        return f"@{streamer} の配信にコメントしたユーザーが見つかりませんでした。"

    lines = [f"@{streamer} の配信のコメンター ({len(logins)} 人):"]
    lines.extend(f"  - {login}" for login in logins)
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
