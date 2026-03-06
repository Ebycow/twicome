from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.config import FAISS_API_URL, ROOT_PATH
from core.middleware import CSRFProtectionMiddleware, HostCheckMiddleware, SecurityHeadersMiddleware
from faiss_search import ping_faiss_api
from routers import ALL_ROUTERS

app = FastAPI(root_path=ROOT_PATH)
app.add_middleware(CSRFProtectionMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(HostCheckMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    response = FileResponse("static/sw.js", media_type="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("static/icons/favicon.ico", media_type="image/x-icon")


@app.get("/manifest.json", include_in_schema=False)
def pwa_manifest():
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
