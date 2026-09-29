"""Twitch API クライアント"""

import logging
import os
import threading
import time
from urllib.parse import quote

import requests

_TWITCH_API_TIMEOUT = 10
_TOKEN_ENDPOINT = "https://id.twitch.tv/oauth2/token"
_TOKEN_REQUEST_TIMEOUT = 20
# 失効間際のトークンを掴まないための安全マージン (秒)
_TOKEN_EXPIRY_MARGIN = 60

logger = logging.getLogger(__name__)

_token_lock = threading.Lock()
_cached_token: str | None = None
_cached_token_expires_at: float = 0.0


class TwitchApiError(RuntimeError):
    """Twitch API への問い合わせが失敗したことを表す。"""


def _mint_app_access_token(client_id: str, client_secret: str) -> tuple[str, float]:
    """client_credentials でアプリアクセストークンを新規取得する。

    .env の静的な ACCESS_TOKEN に依存すると失効時に 401 で落ち続けるため、
    バッチ (batch/scripts/get_vod_list_batch.py) と同じく実行時に取得する。
    """
    try:
        response = requests.post(
            _TOKEN_ENDPOINT,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            timeout=_TOKEN_REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise TwitchApiError(f"アプリアクセストークンの取得に失敗しました: {exc}") from exc

    if response.status_code != 200:
        raise TwitchApiError(f"アプリアクセストークンの取得に失敗しました: {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise TwitchApiError("アプリアクセストークンのレスポンスが JSON ではありません") from exc

    token = payload.get("access_token")
    if not token:
        raise TwitchApiError("アプリアクセストークンのレスポンスに access_token がありません")

    # expires_in が無い/壊れている場合はキャッシュせず毎回取り直す
    try:
        expires_in = float(payload.get("expires_in", 0))
    except (TypeError, ValueError):
        expires_in = 0.0

    return token, time.monotonic() + max(expires_in - _TOKEN_EXPIRY_MARGIN, 0.0)


def _get_access_token(*, force_refresh: bool = False) -> str:
    """API 呼び出しに使うアクセストークンを返す。

    CLIENT_SECRET があれば実行時に取得したアプリトークン (プロセス内キャッシュ) を
    優先し、無い場合のみ .env の ACCESS_TOKEN にフォールバックする。
    """
    global _cached_token, _cached_token_expires_at

    client_id = os.getenv("CLIENT_ID")
    client_secret = os.getenv("CLIENT_SECRET")

    if client_secret:
        with _token_lock:
            if force_refresh:
                _cached_token = None
                _cached_token_expires_at = 0.0
            if _cached_token and time.monotonic() < _cached_token_expires_at:
                return _cached_token
            token, expires_at = _mint_app_access_token(client_id or "", client_secret)
            _cached_token = token
            _cached_token_expires_at = expires_at
            return token

    access_token = os.getenv("ACCESS_TOKEN")
    if not access_token:
        raise TwitchApiError("ACCESS_TOKEN が .env に無い or 読めてないよ (CLIENT_SECRET も未設定)")
    return access_token


def _can_refresh_token() -> bool:
    """401 を受けてトークンを取り直せる (CLIENT_SECRET がある) かどうか。"""
    return bool(os.getenv("CLIENT_SECRET"))


def get_user_id(username: str) -> str | None:
    """Twitch API でユーザー名からユーザー ID を取得する。

    ユーザーが存在しない場合は None を返し、API 呼び出し自体に失敗した場合は
    TwitchApiError を投げる。
    """
    client_id = os.getenv("CLIENT_ID")
    if not client_id:
        raise TwitchApiError("CLIENT_ID が .env に無い or 読めてないよ")

    url = f"https://api.twitch.tv/helix/users?login={quote(username)}"

    response = None
    for attempt in (1, 2):
        access_token = _get_access_token(force_refresh=attempt == 2)
        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {access_token}",
        }
        try:
            response = requests.get(url, headers=headers, timeout=_TWITCH_API_TIMEOUT)
        except requests.RequestException as exc:
            raise TwitchApiError(f"Twitch API への接続に失敗しました: {exc}") from exc

        # トークン失効時は取り直して 1 度だけ再試行する
        if response.status_code == 401 and attempt == 1 and _can_refresh_token():
            logger.warning("Twitch API が 401 を返したためアクセストークンを取り直します")
            continue
        break

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise TwitchApiError(f"Twitch API がエラーを返しました: {response.status_code}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise TwitchApiError("Twitch API のレスポンスが JSON ではありません") from exc

    if "data" in data and len(data["data"]) > 0:
        return data["data"][0]["id"]
    return None
