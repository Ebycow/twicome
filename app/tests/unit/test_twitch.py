import pytest

import clients.twitch as twitch_service


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_get_user_id_raises_when_access_token_missing(monkeypatch):
    monkeypatch.delenv("ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("CLIENT_ID", "client-id")

    with pytest.raises(RuntimeError, match="ACCESS_TOKEN"):
        twitch_service.get_user_id("viewer")


def test_get_user_id_raises_when_client_id_missing(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN", "token")
    monkeypatch.delenv("CLIENT_ID", raising=False)

    with pytest.raises(RuntimeError, match="CLIENT_ID"):
        twitch_service.get_user_id("viewer")


def test_get_user_id_returns_id_and_sends_auth_headers(monkeypatch):
    captured = {}

    def _fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _DummyResponse({"data": [{"id": "12345"}]})

    monkeypatch.setenv("ACCESS_TOKEN", "token")
    monkeypatch.setenv("CLIENT_ID", "client-id")
    monkeypatch.setattr(twitch_service.requests, "get", _fake_get)

    assert twitch_service.get_user_id("viewer") == "12345"
    assert captured["url"].endswith("login=viewer")
    assert captured["headers"] == {
        "Client-ID": "client-id",
        "Authorization": "Bearer token",
    }


@pytest.mark.parametrize("payload", [{"data": []}, {}])
def test_get_user_id_returns_none_when_user_not_found(monkeypatch, payload):
    monkeypatch.setenv("ACCESS_TOKEN", "token")
    monkeypatch.setenv("CLIENT_ID", "client-id")
    monkeypatch.setattr(twitch_service.requests, "get", lambda *_args, **_kwargs: _DummyResponse(payload))

    assert twitch_service.get_user_id("viewer") is None
