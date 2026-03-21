"""Twicome MCP Server

Twicome の HTTP API を MCP ツールとして公開する。

環境変数:
    TWICOME_BASE_URL: Twicome API のベース URL (デフォルト: http://localhost:8000/twicome)
    CF_CLIENT_ID: Cloudflare Access サービストークンのクライアント ID (任意)
    CF_CLIENT_SECRET: Cloudflare Access サービストークンのシークレット (任意)
"""

import os

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
                raise ValueError(body.get("error", "not_found")) from e
            except Exception as parse_err:
                raise ValueError("not_found") from parse_err
        raise RuntimeError(f"API error: {e.response.status_code} {e.response.text}") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"接続エラー: {e}。TWICOME_BASE_URL={BASE_URL} を確認してください。") from e


def _format_comment(item: dict, score: float | None = None, score_label: str = "スコア") -> str:
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

    # FAISS スコア
    if score is not None:
        lines.append(f"  {score_label}: {score:.4f}")

    lines.append(f"  comment_id: {item.get('comment_id', '')}")
    return "\n".join(lines)


@mcp.tool()
def get_user_comments(
    login: str,
    q: str | None = None,
    exclude_q: str | None = None,
    vod_id: str | None = None,
    owner_user_id: str | None = None,
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


@mcp.tool()
def similar_search_comments(
    login: str,
    q: str,
    top_k: int = 20,
    diversity: float | None = None,
) -> str:
    """意味的に類似したコメントを埋め込みベクトルで検索する（FAISS）。

    テキストの意味・文脈が近いコメントを見つける。キーワード検索では拾えない
    言い換えや類義語でのコメントも検索できる。

    Args:
        login: コメンターのログイン名 (例: "username123")
        q: 意味検索クエリ (例: "プレイが上手い", "笑える場面")
        top_k: 取得件数 (1〜100、デフォルト: 20)
        diversity: MMR 多様性パラメータ (0.0〜1.0)。
                   None=通常検索、0.5=バランス良く多様、1.0=最大多様性

    Returns:
        類似度スコア付きコメント一覧。FAISS インデックスが未作成の場合はエラー。
    """
    params: dict = {"q": q, "top_k": top_k}
    if diversity is not None:
        params["diversity"] = diversity

    data = _request(f"/api/u/{login}/similar", params)

    user = data.get("user", {})
    total = data.get("total", 0)
    items = data.get("items", [])

    lines = [
        f"ユーザー: {user.get('display_name', login)} (@{user.get('login', login)})",
        f"検索クエリ: 「{q}」",
        f"類似コメント: {total} 件",
        "",
    ]

    if not items:
        lines.append("該当するコメントが見つかりませんでした。")
    else:
        for item in items:
            score = item.get("similarity_score")
            lines.append(_format_comment(item, score=score, score_label="類似度"))
            lines.append("")

    return "\n".join(lines)


@mcp.tool()
def centroid_search_comments(
    login: str,
    position: float = 0.5,
    top_k: int = 50,
) -> str:
    """重心距離でコメントを検索する（FAISS）。

    ユーザーの全コメントの重心（平均ベクトル）からの距離でソートし、
    そのユーザーにとって「典型的」または「珍しい」コメントを見つける。

    Args:
        login: コメンターのログイン名 (例: "username123")
        position: 重心距離のパーセンタイル (0.0〜1.0)。
                  0.0=最も典型的なコメント、0.5=中間、1.0=最も珍しいコメント
        top_k: 取得件数 (1〜100、デフォルト: 50)

    Returns:
        典型度スコア付きコメント一覧。FAISS インデックスが未作成の場合はエラー。
    """
    data = _request(f"/api/u/{login}/centroid", {"position": position, "top_k": top_k})

    user = data.get("user", {})
    total = data.get("total", 0)
    items = data.get("items", [])

    if position <= 0.3:
        label = "典型的なコメント"
    elif position >= 0.7:
        label = "珍しいコメント"
    else:
        label = "中間的なコメント"

    lines = [
        f"ユーザー: {user.get('display_name', login)} (@{user.get('login', login)})",
        f"重心位置: {position} ({label})",
        f"取得件数: {total} 件",
        "",
    ]

    if not items:
        lines.append("該当するコメントが見つかりませんでした。")
    else:
        for item in items:
            score = item.get("similarity_score")
            lines.append(_format_comment(item, score=score, score_label="重心類似度"))
            lines.append("")

    return "\n".join(lines)


@mcp.tool()
def emotion_search_comments(
    login: str,
    joy: float = 0.0,
    surprise: float = 0.0,
    admiration: float = 0.0,
    anger: float = 0.0,
    sadness: float = 0.0,
    cheer: float = 0.0,
    top_k: int = 50,
    diversity: float | None = None,
) -> str:
    """感情スライダーでコメントを検索する（FAISS）。

    各感情の重みを指定して、その感情に近いコメントをベクトル検索する。
    複数の感情を同時に指定することも可能。全て 0.0 の場合は結果なし。

    Args:
        login: コメンターのログイン名 (例: "username123")
        joy: 喜び・楽しさの強度 (0.0〜1.0)
        surprise: 驚きの強度 (0.0〜1.0)
        admiration: 称賛・感動の強度 (0.0〜1.0)
        anger: 怒り・批判の強度 (0.0〜1.0)
        sadness: 悲しみの強度 (0.0〜1.0)
        cheer: 応援・チアの強度 (0.0〜1.0)
        top_k: 取得件数 (1〜100、デフォルト: 50)
        diversity: MMR 多様性パラメータ (0.0〜1.0)。
                   None=通常検索、0.5=バランス良く多様、1.0=最大多様性

    Returns:
        感情スコア付きコメント一覧。FAISS インデックスが未作成の場合はエラー。
    """
    params: dict = {
        "joy": joy,
        "surprise": surprise,
        "admiration": admiration,
        "anger": anger,
        "sadness": sadness,
        "cheer": cheer,
        "top_k": top_k,
    }
    if diversity is not None:
        params["diversity"] = diversity

    data = _request(f"/api/u/{login}/emotion", params)

    user = data.get("user", {})
    total = data.get("total", 0)
    items = data.get("items", [])
    weights = data.get("weights", {})

    active_emotions = [f"{k}={v}" for k, v in weights.items() if v > 0]
    emotion_str = ", ".join(active_emotions) if active_emotions else "（指定なし）"

    lines = [
        f"ユーザー: {user.get('display_name', login)} (@{user.get('login', login)})",
        f"感情設定: {emotion_str}",
        f"取得件数: {total} 件",
        "",
    ]

    if not items:
        lines.append("該当するコメントが見つかりませんでした。")
    else:
        for item in items:
            score = item.get("similarity_score")
            lines.append(_format_comment(item, score=score, score_label="感情スコア"))
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
