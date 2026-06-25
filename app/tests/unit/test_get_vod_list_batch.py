import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module():
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "twicome_get_vod_list_batch_unit",
        root / "batch" / "scripts" / "get_vod_list_batch.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _DummyResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def test_get_app_access_token_returns_token_and_sends_credentials(monkeypatch):
    module = _load_module()
    captured = {}

    def _fake_post(url, data, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        return _DummyResponse({"access_token": "fresh-token", "expires_in": 5000})

    monkeypatch.setattr(module.requests, "post", _fake_post)

    assert module.get_app_access_token("cid", "secret") == "fresh-token"
    assert captured["url"] == "https://id.twitch.tv/oauth2/token"
    assert captured["data"] == {
        "client_id": "cid",
        "client_secret": "secret",
        "grant_type": "client_credentials",
    }


def test_get_app_access_token_raises_on_non_200(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *_a, **_k: _DummyResponse({"error": "Unauthorized"}, status_code=401, text="Unauthorized"),
    )

    with pytest.raises(RuntimeError, match="Get app access token failed: 401"):
        module.get_app_access_token("cid", "secret")


def test_get_app_access_token_raises_when_token_missing(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module.requests, "post", lambda *_a, **_k: _DummyResponse({"expires_in": 5000}))

    with pytest.raises(RuntimeError, match="Unexpected token response"):
        module.get_app_access_token("cid", "secret")


def test_get_live_user_ids_returns_live_set_and_sends_auth_headers(monkeypatch):
    module = _load_module()
    captured = {}

    def _fake_get(url, headers, params):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        return _DummyResponse({"data": [{"user_id": 111}, {"user_id": 222}]})

    monkeypatch.setattr(module.requests, "get", _fake_get)

    live = module.get_live_user_ids(["111", "333"], "tok", "cid")

    assert live == {"111", "222"}
    assert captured["headers"] == {"Client-ID": "cid", "Authorization": "Bearer tok"}


def test_get_live_user_ids_raises_on_non_200(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *_a, **_k: _DummyResponse({"error": "Unauthorized"}, status_code=401),
    )

    with pytest.raises(RuntimeError, match="Get Streams failed: 401"):
        module.get_live_user_ids(["111"], "tok", "cid")
