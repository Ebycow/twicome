"""トップページ HTML キャッシュの事前生成スクリプト。

invalidate_cache.py による data_version 更新直後に app へ内部 GET を送り、
/ の SSR と Redis HTML キャッシュを先に構築する。
"""

import os
import sys
import time
from urllib.parse import urljoin

import requests

APP_INTERNAL_BASE_URL = os.getenv("APP_INTERNAL_BASE_URL", "http://app:8000").strip()
INDEX_PREWARM_URL = os.getenv("INDEX_PREWARM_URL", "").strip()
DATA_VERSION_URL = os.getenv("DATA_VERSION_URL", "").strip()
INDEX_PREWARM_TIMEOUT = float(os.getenv("INDEX_PREWARM_TIMEOUT", "20"))
INDEX_PREWARM_RETRIES = max(1, int(os.getenv("INDEX_PREWARM_RETRIES", "5")))
INDEX_PREWARM_RETRY_SLEEP = max(0.0, float(os.getenv("INDEX_PREWARM_RETRY_SLEEP", "2")))


def _build_default_url(path: str) -> str:
    base = APP_INTERNAL_BASE_URL.rstrip("/") + "/"
    return urljoin(base, path.lstrip("/"))


def _fetch_expected_version(session: requests.Session, url: str) -> str | None:
    response = session.get(
        url,
        headers={"Accept": "application/json"},
        timeout=INDEX_PREWARM_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    version = payload.get("data_version")
    return version if isinstance(version, str) and version else None


def main() -> int:
    """トップページ HTML キャッシュを事前生成するエントリーポイント。"""
    if not os.getenv("REDIS_URL", "").strip():
        print("REDIS_URL が設定されていません。トップHTML prewarm をスキップします。")
        return 0

    prewarm_url = INDEX_PREWARM_URL or _build_default_url("/")
    data_version_url = DATA_VERSION_URL or _build_default_url("/api/meta/data-version")

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "text/html",
            "Cache-Control": "no-cache",
            "User-Agent": "twicome-batch-prewarm/1.0",
        }
    )

    expected_version = None
    try:
        expected_version = _fetch_expected_version(session, data_version_url)
        print(f"prewarm 対象バージョン: {expected_version}")
    except Exception as exc:
        print(f"Warning: data-version 取得失敗 ({data_version_url}): {exc}")

    last_error = None
    for attempt in range(1, INDEX_PREWARM_RETRIES + 1):
        try:
            response = session.get(prewarm_url, timeout=INDEX_PREWARM_TIMEOUT, allow_redirects=True)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                raise RuntimeError(f"unexpected content-type: {content_type}")

            response_version = response.headers.get("X-Twicome-Data-Version", "").strip() or "-"
            if expected_version and response_version != "-" and response_version != expected_version:
                print(
                    "Warning: prewarm 応答バージョンが期待値と一致しません "
                    f"(expected={expected_version}, actual={response_version})"
                )

            print(
                "トップHTML prewarm 完了: "
                f"status={response.status_code} version={response_version} "
                f"bytes={len(response.content)} url={response.url}"
            )
            return 0
        except Exception as exc:
            last_error = exc
            print(f"prewarm 試行 {attempt}/{INDEX_PREWARM_RETRIES} 失敗: {exc}")
            if attempt < INDEX_PREWARM_RETRIES:
                time.sleep(INDEX_PREWARM_RETRY_SLEEP)

    print(f"トップHTML prewarm 失敗: {last_error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
