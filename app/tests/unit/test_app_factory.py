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
    assert resp.path.endswith("static/icons/favicon.ico")


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
