import json

import app_factory


def test_render_service_worker_script_embeds_cache_name():
    script = app_factory._render_service_worker_script()

    assert app_factory.SERVICE_WORKER_CACHE_NAME_PLACEHOLDER not in script
    assert f'const CACHE_NAME = "{app_factory.SERVICE_WORKER_CACHE_NAME}";' in script


def test_service_worker_response_sets_headers():
    resp = app_factory.service_worker()

    assert resp.media_type == "application/javascript"
    assert resp.headers["Service-Worker-Allowed"] == "/"
    assert resp.headers["Cache-Control"] == "no-cache"


def test_favicon_response_points_to_icon_file():
    resp = app_factory.favicon()

    assert resp.media_type == "image/x-icon"
    assert resp.path == "static/icons/favicon.ico"


def test_pwa_manifest_uses_root_path(monkeypatch):
    monkeypatch.setattr(app_factory, "ROOT_PATH", "/twicome")

    resp = app_factory.pwa_manifest()
    body = json.loads(resp.body)

    assert resp.headers["Cache-Control"] == "no-cache"
    assert body["start_url"] == "/twicome/"
    assert body["scope"] == "/twicome/"
    assert body["icons"][0]["src"] == "/twicome/static/icons/android-chrome-36x36.png"
    assert len(body["icons"]) == 11


def test_health_returns_ok():
    resp = app_factory.health()

    assert json.loads(resp.body) == {"status": "ok"}


def test_check_faiss_api_logs_success(monkeypatch, capsys):
    monkeypatch.setattr(app_factory, "FAISS_API_URL", "http://faiss-api:8100")
    monkeypatch.setattr(app_factory, "ping_faiss_api", lambda: True)

    app_factory.check_faiss_api()

    assert "faiss-api 接続確認完了" in capsys.readouterr().out


def test_check_faiss_api_logs_warning_when_ping_fails(monkeypatch, capsys):
    def _raise():
        raise RuntimeError("backend down")

    monkeypatch.setattr(app_factory, "FAISS_API_URL", "http://faiss-api:8100")
    monkeypatch.setattr(app_factory, "ping_faiss_api", _raise)

    app_factory.check_faiss_api()

    captured = capsys.readouterr().out
    assert "Warning: backend down" in captured
    assert "埋め込み検索機能は利用できません" in captured


def test_check_faiss_api_logs_when_disabled(monkeypatch, capsys):
    monkeypatch.setattr(app_factory, "FAISS_API_URL", "")

    app_factory.check_faiss_api()

    assert "FAISS_API_URL 未設定" in capsys.readouterr().out
