import pytest

from tests.integration.helpers import seed_comment, seed_user, seed_vod


@pytest.fixture()
def seeded_search_data(db):
    seed_user(db, user_id=1, login="streamer", platform="twitch")
    seed_user(db, user_id=2, login="viewer", platform="twitch")
    seed_vod(db, vod_id=100, owner_user_id=1, title="検索テスト配信")
    seed_comment(
        db,
        comment_id="c1",
        vod_id=100,
        commenter_user_id=2,
        commenter_login_snapshot="viewer",
        body="検索対象コメント",
    )


class TestSimilarSearchApi:
    def test_returns_503_when_faiss_disabled(self, client, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", False)

        resp = client.get("/api/u/viewer/similar?q=test")

        assert resp.status_code == 503
        assert resp.json()["error"] == "faiss_not_enabled"

    def test_returns_404_for_unknown_user(self, client, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)

        resp = client.get("/api/u/nobody/similar?q=test")

        assert resp.status_code == 404
        assert resp.json()["error"] == "user_not_found"

    def test_returns_404_when_index_missing(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: False)

        resp = client.get("/api/u/viewer/similar?q=test")

        assert resp.status_code == 404
        assert resp.json()["error"] == "similar_search_not_available"

    def test_returns_backend_error_when_search_fails(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        def _raise(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(search_router, "similar_search", _raise)

        resp = client.get("/api/u/viewer/similar?q=test")

        assert resp.status_code == 503
        assert resp.json()["error"] == "faiss_backend_unavailable"

    def test_returns_empty_payload_when_no_results(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(search_router, "similar_search", lambda *_args, **_kwargs: [])

        resp = client.get("/api/u/viewer/similar?q=test")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    def test_returns_404_when_backend_reports_missing_index_after_search(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(search_router, "similar_search", lambda *_args, **_kwargs: None)

        resp = client.get("/api/u/viewer/similar?q=test")

        assert resp.status_code == 404
        assert resp.json()["error"] == "similar_search_not_available"

    def test_returns_comments_and_skips_missing_ids(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(
            search_router,
            "similar_search",
            lambda *_args, **_kwargs: [("missing", 0.1234), ("c1", 0.87654)],
        )

        resp = client.get("/api/u/viewer/similar?q=test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["comment_id"] == "c1"
        assert data["items"][0]["similarity_score"] == 0.8765


class TestCentroidSearchApi:
    def test_returns_503_when_faiss_disabled(self, client, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", False)

        resp = client.get("/api/u/viewer/centroid?position=0.7")

        assert resp.status_code == 503
        assert resp.json()["error"] == "faiss_not_enabled"

    def test_returns_404_for_unknown_user(self, client, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)

        resp = client.get("/api/u/nobody/centroid?position=0.7")

        assert resp.status_code == 404
        assert resp.json()["error"] == "user_not_found"

    def test_returns_404_when_index_is_unavailable(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: False)

        resp = client.get("/api/u/viewer/centroid?position=0.7")

        assert resp.status_code == 404
        assert resp.json()["error"] == "index_not_available"

    def test_returns_backend_error_when_search_fails(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        def _raise(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(search_router, "centroid_search", _raise)

        resp = client.get("/api/u/viewer/centroid?position=0.7")

        assert resp.status_code == 503
        assert resp.json()["error"] == "faiss_backend_unavailable"

    def test_returns_404_when_backend_reports_missing_index(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(search_router, "centroid_search", lambda *_args, **_kwargs: None)

        resp = client.get("/api/u/viewer/centroid?position=0.7")

        assert resp.status_code == 404
        assert resp.json()["error"] == "index_not_available"

    def test_returns_empty_items_when_search_succeeds_with_no_hits(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(search_router, "centroid_search", lambda *_args, **_kwargs: [])

        resp = client.get("/api/u/viewer/centroid?position=0.7")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    def test_returns_comments_when_search_succeeds(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(
            search_router,
            "centroid_search",
            lambda *_args, **_kwargs: [("missing", 0.11), ("c1", 0.55)],
        )

        resp = client.get("/api/u/viewer/centroid?position=0.7")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["comment_id"] == "c1"


class TestEmotionSearchApi:
    def test_returns_503_when_faiss_disabled(self, client, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", False)

        resp = client.get("/api/u/viewer/emotion?joy=1")

        assert resp.status_code == 503
        assert resp.json()["error"] == "faiss_not_enabled"

    def test_returns_404_for_unknown_user(self, client, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)

        resp = client.get("/api/u/nobody/emotion?joy=1")

        assert resp.status_code == 404
        assert resp.json()["error"] == "user_not_found"

    def test_returns_404_when_index_is_unavailable(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: False)

        resp = client.get("/api/u/viewer/emotion?joy=1")

        assert resp.status_code == 404
        assert resp.json()["error"] == "index_not_available"

    def test_returns_empty_without_calling_backend_when_weights_are_zero(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        def _should_not_be_called(*_args, **_kwargs):
            raise AssertionError("emotion_search should not be called")

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(search_router, "emotion_search", _should_not_be_called)

        resp = client.get("/api/u/viewer/emotion")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    def test_returns_backend_error_when_search_fails(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        def _raise(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(search_router, "emotion_search", _raise)

        resp = client.get("/api/u/viewer/emotion?joy=1")

        assert resp.status_code == 503
        assert resp.json()["error"] == "faiss_backend_unavailable"

    def test_returns_404_when_backend_reports_missing_index(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(search_router, "emotion_search", lambda *_args, **_kwargs: None)

        resp = client.get("/api/u/viewer/emotion?joy=1")

        assert resp.status_code == 404
        assert resp.json()["error"] == "index_not_available"

    def test_returns_comments_when_search_succeeds(self, client, seeded_search_data, monkeypatch):
        import routers.search as search_router

        monkeypatch.setattr(search_router, "FAISS_ENABLED", True)
        monkeypatch.setattr(search_router, "is_index_available", lambda _login: True)
        monkeypatch.setattr(search_router, "emotion_search", lambda *_args, **_kwargs: [("c1", 0.42)])

        resp = client.get("/api/u/viewer/emotion?joy=0.8")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["comment_id"] == "c1"


def test_emotion_axes_api_returns_backend_axes(client, monkeypatch):
    import routers.search as search_router

    monkeypatch.setattr(search_router, "get_emotion_axes", lambda: [{"key": "joy", "label": "Joy"}])

    resp = client.get("/api/emotion_axes")

    assert resp.status_code == 200
    assert resp.json()["axes"] == [{"key": "joy", "label": "Joy"}]
