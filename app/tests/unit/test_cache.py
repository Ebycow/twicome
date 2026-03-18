import json
import sys
import types

import pytest

import core.cache as cache_module


class _FakeRedis:
    def __init__(
        self,
        *,
        data=None,
        ping_error=None,
        get_error=None,
        set_error=None,
        setex_error=None,
        scan_error=None,
        delete_error=None,
        scan_results=None,
    ):
        self.data = dict(data or {})
        self.ping_error = ping_error
        self.get_error = get_error
        self.set_error = set_error
        self.setex_error = setex_error
        self.scan_error = scan_error
        self.delete_error = delete_error
        self.scan_results = list(scan_results or [])
        self.set_calls = []
        self.setex_calls = []
        self.delete_calls = []

    def ping(self):
        if self.ping_error:
            raise self.ping_error

    def get(self, key):
        if self.get_error:
            raise self.get_error
        return self.data.get(key)

    def set(self, key, value):
        if self.set_error:
            raise self.set_error
        self.data[key] = value
        self.set_calls.append((key, value))

    def setex(self, key, ttl, value):
        if self.setex_error:
            raise self.setex_error
        self.data[key] = value
        self.setex_calls.append((key, ttl, value))

    def scan_iter(self, _pattern):
        if self.scan_error:
            raise self.scan_error
        return iter(self.scan_results)

    def delete(self, *keys):
        if self.delete_error:
            raise self.delete_error
        self.delete_calls.append(keys)


@pytest.fixture(autouse=True)
def _reset_cache_globals(monkeypatch):
    monkeypatch.setattr(cache_module, "_redis_client", None)
    monkeypatch.setattr(cache_module, "REDIS_URL", "")
    monkeypatch.setattr(cache_module, "COMMENTS_CACHE_TTL", 321)
    monkeypatch.setattr(cache_module, "_startup_data_version", "startup-version")
    monkeypatch.setattr(cache_module, "_render_version", "render-version")


class TestComputeRenderVersion:
    def test_returns_explicit_version_from_env(self, monkeypatch):
        monkeypatch.setenv("APP_RENDER_VERSION", "manual-version")

        assert cache_module._compute_render_version() == "manual-version"

    def test_tracks_index_service_changes_in_render_version(self, monkeypatch, tmp_path):
        monkeypatch.delenv("APP_RENDER_VERSION", raising=False)
        app_dir = tmp_path / "app"
        (app_dir / "templates").mkdir(parents=True)
        (app_dir / "static").mkdir(parents=True)
        (app_dir / "core").mkdir(parents=True)
        (app_dir / "routers").mkdir(parents=True)
        (app_dir / "services").mkdir(parents=True)

        (app_dir / "templates" / "index.html").write_text("template", encoding="utf-8")
        (app_dir / "static" / "sw.js").write_text("sw", encoding="utf-8")
        (app_dir / "core" / "config.py").write_text("config", encoding="utf-8")
        (app_dir / "routers" / "comments.py").write_text("comments", encoding="utf-8")
        target = app_dir / "services" / "index_service.py"
        target.write_text("index-service", encoding="utf-8")

        monkeypatch.setattr(cache_module, "Path", lambda *_args, **_kwargs: app_dir / "core" / "cache.py")

        assert cache_module._compute_render_version() == str(target.stat().st_mtime_ns)

    def test_falls_back_to_startup_version_when_candidates_missing(self, monkeypatch):
        monkeypatch.delenv("APP_RENDER_VERSION", raising=False)

        class _MissingPath:
            def __init__(self, *_args, **_kwargs):
                pass

            def resolve(self):
                return self

            @property
            def parent(self):
                return self

            def __truediv__(self, _other):
                return self

            def is_dir(self):
                return False

            def exists(self):
                return False

        monkeypatch.setattr(cache_module, "Path", _MissingPath)

        assert cache_module._compute_render_version() == "startup-version"


class TestGetRedis:
    def test_returns_none_when_redis_disabled(self):
        assert cache_module._get_redis() is None

    def test_reuses_existing_client(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(cache_module, "REDIS_URL", "redis://example")
        monkeypatch.setattr(cache_module, "_redis_client", fake)

        assert cache_module._get_redis() is fake

    def test_initializes_client_from_redis_url(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(cache_module, "REDIS_URL", "redis://example")
        monkeypatch.setitem(
            sys.modules,
            "redis",
            types.SimpleNamespace(from_url=lambda *args, **kwargs: fake),
        )

        assert cache_module._get_redis() is fake
        assert cache_module._get_redis() is fake

    def test_returns_none_when_connection_fails(self, monkeypatch, capsys):
        def _raise_from_url(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(cache_module, "REDIS_URL", "redis://example")
        monkeypatch.setitem(sys.modules, "redis", types.SimpleNamespace(from_url=_raise_from_url))

        assert cache_module._get_redis() is None
        assert "Redis 接続失敗" in capsys.readouterr().out


class TestPublicCacheApis:
    def test_public_functions_noop_when_redis_unavailable(self, monkeypatch):
        monkeypatch.setattr(cache_module, "_get_redis", lambda: None)

        assert cache_module.get_user_meta_cache("viewer") is None
        cache_module.set_user_meta_cache("viewer", {"a": 1})
        assert cache_module.get_data_version() == "startup-version:render-version"
        assert cache_module.set_data_version("version-1") == "version-1"
        assert cache_module.get_index_html_cache("v1") is None
        cache_module.set_index_html_cache("v1", "<html></html>")
        assert cache_module.get_comments_html_cache("v1", "twitch", "viewer") is None
        cache_module.set_comments_html_cache("v1", "twitch", "viewer", "<html></html>")
        assert cache_module.get_index_landing_cache() is None
        cache_module.set_index_landing_cache({"quick_links": []})
        assert cache_module.get_index_users_cache() is None
        cache_module.set_index_users_cache([{"login": "viewer"}])
        cache_module.invalidate_index_cache()

    def test_round_trips_cached_values_and_normalizes_comment_html_key(self, monkeypatch):
        fake = _FakeRedis(data={cache_module.DATA_VERSION_KEY: "data-v2"})
        monkeypatch.setattr(cache_module, "_get_redis", lambda: fake)

        cache_module.set_user_meta_cache("viewer", {"owners": [1]})
        cache_module.set_index_html_cache("v1", "<html>index</html>")
        cache_module.set_comments_html_cache("v1", " YouTube ", " Viewer ", "<html>comments</html>")
        cache_module.set_index_landing_cache({"quick_links": [1]})
        cache_module.set_index_users_cache([{"login": "viewer"}])

        assert cache_module.get_user_meta_cache("viewer") == {"owners": [1]}
        assert cache_module.get_index_html_cache("v1") == "<html>index</html>"
        assert cache_module.get_comments_html_cache("v1", "youtube", "viewer") == "<html>comments</html>"
        assert cache_module.get_index_landing_cache() == {"quick_links": [1]}
        assert cache_module.get_index_users_cache() == [{"login": "viewer"}]
        assert cache_module.get_data_version() == "data-v2:render-version"

        comments_key = "twicome:comments:html:v1:youtube:viewer"
        assert fake.data[comments_key] == "<html>comments</html>"
        assert ("twicome:index:users", 321, json.dumps([{"login": "viewer"}], default=str)) in fake.setex_calls

    def test_get_data_version_sets_startup_value_when_missing_in_redis(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(cache_module, "_get_redis", lambda: fake)

        assert cache_module.get_data_version() == "startup-version:render-version"
        assert fake.set_calls == [(cache_module.DATA_VERSION_KEY, "startup-version")]

    def test_get_data_version_falls_back_when_redis_errors(self, monkeypatch, capsys):
        fake = _FakeRedis(get_error=RuntimeError("boom"))
        monkeypatch.setattr(cache_module, "_get_redis", lambda: fake)

        assert cache_module.get_data_version() == "startup-version:render-version"
        assert "get_data_version error" in capsys.readouterr().out

    def test_get_data_version_returns_combined_versions_without_redis(self):
        assert cache_module.get_data_version() == "startup-version:render-version"

    def test_set_data_version_uses_fallback_when_value_blank(self, monkeypatch):
        assert cache_module.set_data_version("   ") == "startup-version"

        fake = _FakeRedis()
        monkeypatch.setattr(cache_module, "_get_redis", lambda: fake)
        assert cache_module.set_data_version("custom-version") == "custom-version"
        assert fake.set_calls == [(cache_module.DATA_VERSION_KEY, "custom-version")]

    def test_set_data_version_swallow_errors(self, monkeypatch, capsys):
        fake = _FakeRedis(set_error=RuntimeError("boom"))
        monkeypatch.setattr(cache_module, "_get_redis", lambda: fake)

        assert cache_module.set_data_version("custom-version") == "custom-version"
        assert "set_data_version error" in capsys.readouterr().out

    @pytest.mark.parametrize(
        ("func", "args"),
        [
            (cache_module.get_user_meta_cache, ("viewer",)),
            (cache_module.get_index_html_cache, ("v1",)),
            (cache_module.get_comments_html_cache, ("v1", "twitch", "viewer")),
            (cache_module.get_index_landing_cache, ()),
            (cache_module.get_index_users_cache, ()),
        ],
    )
    def test_getters_return_none_when_redis_raises(self, monkeypatch, func, args, capsys):
        fake = _FakeRedis(get_error=RuntimeError("boom"))
        monkeypatch.setattr(cache_module, "_get_redis", lambda: fake)

        assert func(*args) is None
        assert "error" in capsys.readouterr().out

    @pytest.mark.parametrize(
        ("func", "args"),
        [
            (cache_module.set_user_meta_cache, ("viewer", {"a": 1})),
            (cache_module.set_index_html_cache, ("v1", "<html></html>")),
            (cache_module.set_comments_html_cache, ("v1", "twitch", "viewer", "<html></html>")),
            (cache_module.set_index_landing_cache, ({"quick_links": []},)),
            (cache_module.set_index_users_cache, ([{"login": "viewer"}],)),
        ],
    )
    def test_setters_swallow_redis_errors(self, monkeypatch, func, args, capsys):
        fake = _FakeRedis(setex_error=RuntimeError("boom"))
        monkeypatch.setattr(cache_module, "_get_redis", lambda: fake)

        func(*args)

        assert "error" in capsys.readouterr().out

    def test_invalidate_index_cache_deletes_base_and_html_keys(self, monkeypatch):
        fake = _FakeRedis(scan_results=["twicome:index:html:v1", "twicome:index:html:v2"])
        monkeypatch.setattr(cache_module, "_get_redis", lambda: fake)

        cache_module.invalidate_index_cache()

        assert fake.delete_calls == [
            (
                cache_module.INDEX_LANDING_CACHE_KEY,
                cache_module.INDEX_USERS_CACHE_KEY,
                "twicome:index:html:v1",
                "twicome:index:html:v2",
            )
        ]

    def test_invalidate_index_cache_swallow_errors(self, monkeypatch, capsys):
        fake = _FakeRedis(scan_error=RuntimeError("boom"))
        monkeypatch.setattr(cache_module, "_get_redis", lambda: fake)

        cache_module.invalidate_index_cache()

        assert "invalidate_index_cache error" in capsys.readouterr().out
