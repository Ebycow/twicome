"""形態素解析クライアント

morpheme-api サービスへのHTTP通信を担うクライアントモジュール。
MORPHEME_API_URL が未設定の場合はすべての関数が空/Falseを返す。
"""

import os

import requests
from requests import RequestException

MORPHEME_API_URL: str = os.getenv("MORPHEME_API_URL", "").strip().rstrip("/")
_REQUEST_TIMEOUT = 60


def _is_enabled() -> bool:
    return bool(MORPHEME_API_URL)


def ping_morpheme_api() -> bool:
    """morpheme-api の死活確認。接続できれば True を返す。"""
    if not _is_enabled():
        return False
    try:
        resp = requests.get(f"{MORPHEME_API_URL}/health", timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        raise RuntimeError(f"morpheme-api ({MORPHEME_API_URL}) に接続できません: {e}") from e


def analyze(texts: list[str], mode: str = "C") -> list[list[dict]] | None:
    """テキストリストを形態素解析して返す。

    mode: "A"=最小単位, "B"=中間, "C"=最大単位（デフォルト）
    Returns: [[{surface, reading, pos, pos_detail, base_form, normalized_form}, ...], ...] または None
    """
    if not _is_enabled() or not texts:
        return None
    try:
        resp = requests.post(
            f"{MORPHEME_API_URL}/analyze",
            json={"texts": texts, "mode": mode},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["results"]
    except RequestException as e:
        raise RuntimeError(f"morpheme analyze failed: {e}") from e
