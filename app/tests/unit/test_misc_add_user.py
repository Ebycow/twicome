"""POST /add_user のエラーハンドリングのテスト。

Twitch API の失敗 (トークン失効など) が 500 Internal Server Error として
漏れず、ユーザー向けメッセージ付きのリダイレクトになることを確認する。
"""

from urllib.parse import unquote

import routers.misc as misc_module
from fastapi import FastAPI
from fastapi.testclient import TestClient

from clients.twitch import TwitchApiError


def _build_client():
    app = FastAPI()
    app.include_router(misc_module.router)
    return TestClient(app)


def test_twitch_api_error_redirects_instead_of_500(monkeypatch):
    def _raise(_username):
        raise TwitchApiError("Twitch API がエラーを返しました: 401")

    monkeypatch.setattr(misc_module, "get_user_id", _raise)

    response = _build_client().post("/add_user", data={"username": "fps_shaka"}, follow_redirects=False)

    assert response.status_code == 303
    assert "Twitch との通信に失敗しました" in unquote(response.headers["location"])


def test_unknown_user_redirects_with_not_found_message(monkeypatch):
    monkeypatch.setattr(misc_module, "get_user_id", lambda _username: None)

    response = _build_client().post("/add_user", data={"username": "no_such_user"}, follow_redirects=False)

    assert response.status_code == 303
    assert "見つかりませんでした" in unquote(response.headers["location"])


def test_blank_username_redirects_with_error():
    response = _build_client().post("/add_user", data={"username": "   "}, follow_redirects=False)

    assert response.status_code == 303
    assert "ユーザ名を入力してください" in unquote(response.headers["location"])


def test_add_user_appends_to_csv_and_rejects_duplicate(monkeypatch, tmp_path):
    csv_path = tmp_path / "targetusers.csv"
    csv_path.write_text("name,id\nexisting,111\n", encoding="utf-8")
    monkeypatch.setattr(misc_module, "TARGET_USERS_CSV", csv_path)
    monkeypatch.setattr(misc_module, "get_user_id", lambda _username: "222")
    client = _build_client()

    response = client.post("/add_user", data={"username": "newone"}, follow_redirects=False)
    assert response.status_code == 303
    assert "を追加しました" in unquote(response.headers["location"])
    assert csv_path.read_text(encoding="utf-8").splitlines() == ["name,id", "existing,111", "newone,222"]

    response = client.post("/add_user", data={"username": "existing"}, follow_redirects=False)
    assert "すでに登録されています" in unquote(response.headers["location"])


def test_add_user_creates_csv_when_missing(monkeypatch, tmp_path):
    csv_path = tmp_path / "targetusers.csv"
    monkeypatch.setattr(misc_module, "TARGET_USERS_CSV", csv_path)
    monkeypatch.setattr(misc_module, "get_user_id", lambda _username: "333")

    response = _build_client().post(
        "/add_user", data={"username": "https://www.twitch.tv/someone"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert csv_path.read_text(encoding="utf-8").splitlines() == ["name,id", "someone,333"]
