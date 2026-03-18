"""FastAPI アプリケーションファクトリ"""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from routers import ALL_ROUTERS

from core.config import FAISS_API_URL, ROOT_PATH, SERVICE_WORKER_CACHE_NAME
from core.middleware import CSRFProtectionMiddleware, HostCheckMiddleware, SecurityHeadersMiddleware
from faiss_search import ping_faiss_api

_STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(root_path=ROOT_PATH)
app.add_middleware(CSRFProtectionMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(HostCheckMiddleware)

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

SERVICE_WORKER_CACHE_NAME_PLACEHOLDER = "__TWICOME_CACHE_NAME__"


def _render_service_worker_script() -> str:
    sw_path = Path(__file__).resolve().parent / "static" / "sw.js"
    script = sw_path.read_text(encoding="utf-8")
    return script.replace(
        SERVICE_WORKER_CACHE_NAME_PLACEHOLDER,
        json.dumps(SERVICE_WORKER_CACHE_NAME),
    )


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """Service Worker JS を返す。"""
    response = Response(_render_service_worker_script(), media_type="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Favicon を返す。"""
    return FileResponse(str(_STATIC_DIR / "icons" / "favicon.ico"), media_type="image/x-icon")


@app.get("/manifest.json", include_in_schema=False)
def pwa_manifest():
    """PWA マニフェスト JSON を返す。"""
    base = ROOT_PATH  # e.g. "" (dev) or "/twicome" (prod)
    icons_base = f"{base}/static/icons"
    sizes = [36, 48, 72, 96, 128, 144, 152, 192, 256, 384, 512]
    return JSONResponse(
        {
            "name": "ツイコメ - Twicome",
            "short_name": "ツイコメ",
            "description": "Twitch VOD コメント検索・分析ツール",
            "start_url": f"{base}/",
            "scope": f"{base}/",
            "display": "standalone",
            "background_color": "#0e0e10",
            "theme_color": "#9147ff",
            "lang": "ja",
            "icons": [
                {
                    "src": f"{icons_base}/android-chrome-{s}x{s}.png",
                    "sizes": f"{s}x{s}",
                    "type": "image/png",
                }
                for s in sizes
            ],
        },
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/health")
def health():
    """ヘルスチェックエンドポイント。"""
    return JSONResponse({"status": "ok"})


@app.on_event("startup")
def check_faiss_api():
    """起動時に faiss-api への接続確認"""
    if FAISS_API_URL:
        try:
            ping_faiss_api()
            print(f"[faiss] faiss-api 接続確認完了: {FAISS_API_URL}")
        except Exception as e:
            print(f"[faiss] Warning: {e}")
            print("[faiss] 埋め込み検索機能は利用できません")
    else:
        print("[faiss] FAISS_API_URL 未設定 - 埋め込み検索機能は無効")


for router in ALL_ROUTERS:
    app.include_router(router)
