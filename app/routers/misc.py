import csv
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from clients.twitch import TwitchApiError, get_user_id
from core.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter()

TARGET_USERS_CSV = Path("/host/targetusers.csv")
TARGET_USERS_FIELDS = ["name", "id"]


def _read_target_users() -> list[dict]:
    """配信者 CSV（name,id）を読み込む。存在しない・空の場合は空リスト。"""
    try:
        with TARGET_USERS_CSV.open(encoding="utf-8", newline="") as f:
            return [{k: row.get(k, "") for k in TARGET_USERS_FIELDS} for row in csv.DictReader(f)]
    except FileNotFoundError:
        return []


def _write_target_users(users: list[dict]) -> None:
    """配信者 CSV を書き出す。"""
    with TARGET_USERS_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TARGET_USERS_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(users)


@router.get("/manual", response_class=HTMLResponse)
def manual_page(request: Request):
    return templates.TemplateResponse("manual.html", {"request": request})


@router.get("/add_user", response_class=HTMLResponse)
def add_user_page(request: Request, message: str | None = Query(None), error: str | None = Query(None)):
    try:
        users = _read_target_users()
    except Exception:
        users = []
    return templates.TemplateResponse(
        "add_user.html", {"request": request, "message": message, "error": error, "users": users}
    )


@router.post("/add_user")
def add_user(request: Request, username: str = Form(...)):
    username = username.strip()
    if not username:
        return RedirectResponse(
            url=str(request.url_for("add_user_page")) + "?error=ユーザ名を入力してください", status_code=303
        )

    # URLからloginを抽出
    if username.startswith("https://www.twitch.tv/"):
        match = re.match(r"https://www\.twitch\.tv/([^/?]+)", username)
        if match:
            username = match.group(1)
        else:
            return RedirectResponse(url=str(request.url_for("add_user_page")) + "?error=無効なURLです", status_code=303)

    try:
        user_id = get_user_id(username)
    except TwitchApiError:
        logger.exception("Twitch API からユーザー ID を取得できませんでした: %s", username)
        return RedirectResponse(
            url=str(request.url_for("add_user_page"))
            + "?error=Twitch との通信に失敗しました。しばらく経ってから再度お試しください",
            status_code=303,
        )
    if not user_id:
        return RedirectResponse(
            url=str(request.url_for("add_user_page")) + f"?error=ユーザ {username} が見つかりませんでした",
            status_code=303,
        )

    try:
        users = _read_target_users()
        # すでに存在するかチェック
        if any(u["name"] == username for u in users):
            return RedirectResponse(
                url=str(request.url_for("add_user_page")) + f"?error=ユーザ {username} はすでに登録されています",
                status_code=303,
            )
        users.append({"name": username, "id": user_id})
        _write_target_users(users)
        return RedirectResponse(
            url=str(request.url_for("add_user_page")) + f"?message=ユーザ {username} (ID: {user_id}) を追加しました",
            status_code=303,
        )
    except Exception:
        logger.exception("CSV書き込みエラー")
        return RedirectResponse(
            url=str(request.url_for("add_user_page"))
            + "?error=ユーザの追加に失敗しました。しばらく経ってから再度お試しください",
            status_code=303,
        )
