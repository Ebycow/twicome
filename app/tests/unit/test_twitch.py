import pytest

import clients.twitch as twitch_service


class _DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _reset_token_cache():
    """プロセス内トークンキャッシュがテスト間で漏れないようにする。"""
    twitch_service._cached_token = None
    twitch_service._cached_token_expires_at = 0.0
    yield
    twitch_service._cached_token = None
    twitch_service._cached_token_expires_at = 0.0


def test_get_user_id_raises_when_access_token_missing(monkeypatch):
    monkeypatch.delenv("ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CLIENT_SECRET", raising=False)
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
    monkeypatch.delenv("CLIENT_SECRET", raising=False)
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
    monkeypatch.delenv("CLIENT_SECRET", raising=False)
    monkeypatch.setenv("CLIENT_ID", "client-id")
    monkeypatch.setattr(twitch_service.requests, "get", lambda *_args, **_kwargs: _DummyResponse(payload))

    assert twitch_service.get_user_id("viewer") is None


def _set_client_credentials(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "client-id")
    monkeypatch.setenv("CLIENT_SECRET", "client-secret")


def test_client_secret_takes_precedence_over_stale_env_token(monkeypatch):
    """.env の ACCESS_TOKEN は失効しうるので、取得したアプリトークンを使う。"""
    monkeypatch.setenv("ACCESS_TOKEN", "stale-token")
    _set_client_credentials(monkeypatch)
    captured = {}

    def _fake_post(url, data, timeout):
        captured["token_url"] = url
        captured["token_data"] = data
        return _DummyResponse({"access_token": "fresh-token", "expires_in": 5000})

    def _fake_get(url, headers, timeout):
        captured["headers"] = headers
        return _DummyResponse({"data": [{"id": "12345"}]})

    monkeypatch.setattr(twitch_service.requests, "post", _fake_post)
    monkeypatch.setattr(twitch_service.requests, "get", _fake_get)

    assert twitch_service.get_user_id("viewer") == "12345"
    assert captured["token_url"] == "https://id.twitch.tv/oauth2/token"
    assert captured["token_data"]["grant_type"] == "client_credentials"
    assert captured["headers"]["Authorization"] == "Bearer fresh-token"


def test_valid_token_is_cached_between_calls(monkeypatch):
    _set_client_credentials(monkeypatch)
    post_calls = []

    def _fake_post(url, data, timeout):
        post_calls.append(url)
        return _DummyResponse({"access_token": "fresh-token", "expires_in": 5000})

    monkeypatch.setattr(twitch_service.requests, "post", _fake_post)
    monkeypatch.setattr(
        twitch_service.requests, "get", lambda *_a, **_kw: _DummyResponse({"data": [{"id": "12345"}]})
    )

    twitch_service.get_user_id("viewer")
    twitch_service.get_user_id("viewer")

    assert len(post_calls) == 1


def test_401_triggers_token_refresh_and_single_retry(monkeypatch):
    _set_client_credentials(monkeypatch)
    tokens = iter(["expired-token", "fresh-token"])
    used_tokens = []

    monkeypatch.setattr(
        twitch_service.requests,
        "post",
        lambda *_a, **_kw: _DummyResponse({"access_token": next(tokens), "expires_in": 5000}),
    )

    def _fake_get(url, headers, timeout):
        token = headers["Authorization"].removeprefix("Bearer ")
        used_tokens.append(token)
        if token == "expired-token":
            return _DummyResponse({"message": "Invalid OAuth token"}, status_code=401)
        return _DummyResponse({"data": [{"id": "12345"}]})

    monkeypatch.setattr(twitch_service.requests, "get", _fake_get)

    assert twitch_service.get_user_id("viewer") == "12345"
    assert used_tokens == ["expired-token", "fresh-token"]


def test_persistent_401_raises_twitch_api_error(monkeypatch):
    _set_client_credentials(monkeypatch)
    monkeypatch.setattr(
        twitch_service.requests,
        "post",
        lambda *_a, **_kw: _DummyResponse({"access_token": "token", "expires_in": 5000}),
    )
    monkeypatch.setattr(
        twitch_service.requests,
        "get",
        lambda *_a, **_kw: _DummyResponse({"message": "Invalid OAuth token"}, status_code=401),
    )

    with pytest.raises(twitch_service.TwitchApiError):
        twitch_service.get_user_id("viewer")


def test_network_error_raises_twitch_api_error(monkeypatch):
    import requests

    monkeypatch.setenv("ACCESS_TOKEN", "token")
    monkeypatch.delenv("CLIENT_SECRET", raising=False)
    monkeypatch.setenv("CLIENT_ID", "client-id")

    def _raise(*_args, **_kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(twitch_service.requests, "get", _raise)

    with pytest.raises(twitch_service.TwitchApiError):
        twitch_service.get_user_id("viewer")


def test_token_endpoint_failure_raises_twitch_api_error(monkeypatch):
    _set_client_credentials(monkeypatch)
    monkeypatch.setattr(
        twitch_service.requests, "post", lambda *_a, **_kw: _DummyResponse({"error": "bad"}, status_code=400)
    )

    with pytest.raises(twitch_service.TwitchApiError, match="アプリアクセストークン"):
        twitch_service.get_user_id("viewer")
