from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.middleware as middleware_module


def _build_host_app():
    app = FastAPI()
    app.add_middleware(middleware_module.HostCheckMiddleware)

    @app.get("/ping")
    def ping():
        return {"status": "ok"}

    return app


def _build_security_app():
    app = FastAPI()
    app.add_middleware(middleware_module.SecurityHeadersMiddleware)

    @app.get("/ping")
    def ping():
        return {"status": "ok"}

    return app


def _build_csrf_app():
    app = FastAPI()
    app.add_middleware(middleware_module.CSRFProtectionMiddleware)

    @app.get("/ping")
    def ping():
        return {"status": "ok"}

    @app.post("/submit")
    def submit():
        return {"status": "ok"}

    return app


def test_is_ip_address_detects_ipv4_only():
    assert middleware_module.is_ip_address("127.0.0.1") is True
    assert middleware_module.is_ip_address("example.com") is False


def test_host_check_allows_requests_when_disabled(monkeypatch):
    monkeypatch.setattr(middleware_module, "HOST_CHECK_ENABLED", False)
    client = TestClient(_build_host_app(), base_url="http://127.0.0.1")

    resp = client.get("/ping")

    assert resp.status_code == 200


def test_host_check_blocks_ip_access_when_enabled(monkeypatch):
    monkeypatch.setattr(middleware_module, "HOST_CHECK_ENABLED", True)
    client = TestClient(_build_host_app(), base_url="http://127.0.0.1")

    resp = client.get("/ping")

    assert resp.status_code == 403
    assert resp.json()["error"] == "Access denied"


def test_host_check_allows_domain_access_when_enabled(monkeypatch):
    monkeypatch.setattr(middleware_module, "HOST_CHECK_ENABLED", True)
    client = TestClient(_build_host_app(), base_url="http://example.com")

    resp = client.get("/ping")

    assert resp.status_code == 200


def test_security_headers_are_added_to_response():
    client = TestClient(_build_security_app())

    resp = client.get("/ping")

    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-XSS-Protection"] == "1; mode=block"
    assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_csrf_allows_safe_method():
    client = TestClient(_build_csrf_app())

    resp = client.get("/ping")

    assert resp.status_code == 200


def test_csrf_allows_ajax_requests():
    client = TestClient(_build_csrf_app())

    resp = client.post("/submit", headers={"X-Requested-With": "XMLHttpRequest"})

    assert resp.status_code == 200


def test_csrf_allows_json_requests():
    client = TestClient(_build_csrf_app())

    resp = client.post("/submit", json={"ok": True})

    assert resp.status_code == 200


def test_csrf_allows_same_origin_origin_header():
    client = TestClient(_build_csrf_app())

    resp = client.post("/submit", data={"ok": "1"}, headers={"Origin": "http://testserver", "Host": "testserver"})

    assert resp.status_code == 200


def test_csrf_allows_same_origin_referer_header():
    client = TestClient(_build_csrf_app())

    resp = client.post(
        "/submit",
        data={"ok": "1"},
        headers={"Referer": "http://testserver/form", "Host": "testserver"},
    )

    assert resp.status_code == 200


def test_csrf_rejects_mismatched_origin():
    client = TestClient(_build_csrf_app())

    resp = client.post("/submit", data={"ok": "1"}, headers={"Origin": "http://evil.example", "Host": "testserver"})

    assert resp.status_code == 403
    assert resp.json()["error"] == "CSRF validation failed"


def test_csrf_rejects_mismatched_referer():
    client = TestClient(_build_csrf_app())

    resp = client.post(
        "/submit",
        data={"ok": "1"},
        headers={"Referer": "http://evil.example/form", "Host": "testserver"},
    )

    assert resp.status_code == 403
    assert resp.json()["error"] == "CSRF validation failed"


def test_csrf_rejects_missing_origin_and_referer():
    client = TestClient(_build_csrf_app())

    resp = client.post("/submit", data={"ok": "1"})

    assert resp.status_code == 403
    assert resp.json()["error"] == "CSRF validation failed: missing origin"
