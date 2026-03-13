"""
HTTP 統合テスト（FastAPI TestClient 経由）。
エンドポイントの振る舞いをエンドツーエンドで確認する。
"""
import pytest
from tests.integration.helpers import seed_comment, seed_user, seed_vod


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestIndex:
    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_data_version_header(self, client):
        resp = client.get("/")
        assert "x-twicome-data-version" in resp.headers

    def test_api_data_version(self, client):
        resp = client.get("/api/meta/data-version")
        assert resp.status_code == 200
        assert "data_version" in resp.json()

    def test_api_users_index_empty(self, client):
        resp = client.get("/api/users/index")
        assert resp.status_code == 200
        assert resp.json()["users"] == []

    def test_index_embeds_default_login_prefetch_marker(self, client, monkeypatch):
        import services.index_service as index_service

        monkeypatch.setattr(index_service, "DEFAULT_LOGIN", "prefetch_target")

        resp = client.get("/")
        assert resp.status_code == 200
        assert 'data-default-login="prefetch_target"' in resp.text

    def test_index_embeds_service_worker_cache_name(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'const serviceWorkerCacheName = "twicome-v11";' in resp.text

    def test_service_worker_script_embeds_cache_name(self, client):
        resp = client.get("/sw.js")
        assert resp.status_code == 200
        assert "application/javascript" in resp.headers["content-type"]
        assert "__TWICOME_CACHE_NAME__" not in resp.text
        assert 'const CACHE_NAME = "twicome-v11";' in resp.text


class TestUserCommentsPage:
    def test_unknown_user_returns_404(self, client):
        resp = client.get("/u/nobody")
        assert resp.status_code == 404

    def test_known_user_returns_200(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="viewer", body="こんにちは")
        resp = client.get("/u/viewer")
        assert resp.status_code == 200
        assert "viewer" in resp.text

    def test_comment_body_in_response(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="viewer", body="ユニークなコメント内容12345")
        resp = client.get("/u/viewer")
        assert "ユニークなコメント内容12345" in resp.text

    def test_initial_comments_page_can_return_cached_html(self, client, monkeypatch):
        import routers.comments as comments_router

        monkeypatch.setattr(comments_router, "get_data_version", lambda: "20260311000000")
        monkeypatch.setattr(
            comments_router,
            "get_comments_html_cache",
            lambda version, platform, login: "<!doctype html><html><body>cached comments page</body></html>",
        )

        resp = client.get("/u/anyone")
        assert resp.status_code == 200
        assert "cached comments page" in resp.text
        assert resp.headers["x-twicome-data-version"] == "20260311000000"

    def test_initial_comments_page_populates_html_cache(self, client, db, monkeypatch):
        import routers.comments as comments_router

        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(
            db,
            comment_id="c1",
            vod_id=100,
            commenter_user_id=2,
            commenter_login_snapshot="viewer",
            body="初期キャッシュ確認",
        )

        saved = {}
        monkeypatch.setattr(comments_router, "get_data_version", lambda: "20260311000001")
        monkeypatch.setattr(comments_router, "get_comments_html_cache", lambda version, platform, login: None)
        monkeypatch.setattr(
            comments_router,
            "set_comments_html_cache",
            lambda version, platform, login, html: saved.update({
                "version": version,
                "platform": platform,
                "login": login,
                "html": html,
            }),
        )

        resp = client.get("/u/viewer")
        assert resp.status_code == 200
        assert "初期キャッシュ確認" in resp.text
        assert saved["version"] == "20260311000001"
        assert saved["platform"] == "twitch"
        assert saved["login"] == "viewer"
        assert "初期キャッシュ確認" in saved["html"]
        assert 'id="data-version-data"' in saved["html"]
        assert "20260311000001" in saved["html"]

    def test_user_comments_page_embeds_data_version_for_stale_cache_notice(self, client, db, monkeypatch):
        import routers.comments as comments_router

        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(
            db,
            comment_id="c1",
            vod_id=100,
            commenter_user_id=2,
            commenter_login_snapshot="viewer",
            body="更新通知テスト",
        )

        monkeypatch.setattr(comments_router, "get_data_version", lambda: "20260311000002:render")
        monkeypatch.setattr(comments_router, "get_comments_html_cache", lambda version, platform, login: None)

        resp = client.get("/u/viewer")
        assert resp.status_code == 200
        assert 'id="data-version-data"' in resp.text
        assert "20260311000002:render" in resp.text
        assert "最新のデータがあります" in resp.text


class TestUserCommentsApi:
    def test_unknown_user_returns_404(self, client):
        resp = client.get("/api/u/nobody")
        assert resp.status_code == 404
        assert resp.json()["error"] == "user_not_found"

    def test_known_user_returns_comments(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="viewer", body="APIテスト")
        resp = client.get("/api/u/viewer")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["body"] == "APIテスト"

    def test_pagination(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        for i in range(15):
            seed_comment(db, comment_id=f"c{i}", vod_id=100, commenter_user_id=2,
                         commenter_login_snapshot="viewer", body=f"コメント{i}",
                         offset_seconds=i * 10)
        resp = client.get("/api/u/viewer?page_size=10&page=1")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 10
        assert resp.json()["total"] == 15

    def test_keyword_filter(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="viewer", body="hello world")
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="viewer", body="goodbye")
        resp = client.get("/api/u/viewer?q=hello")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["body"] == "hello world"

    def test_html_and_api_return_same_total(self, client, db):
        """user_comments_page と user_comments_api が同じ total を返すことを確認。"""
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        for i in range(7):
            seed_comment(db, comment_id=f"c{i}", vod_id=100, commenter_user_id=2,
                         commenter_login_snapshot="viewer", body=f"コメント{i}",
                         offset_seconds=i * 10)
        api_resp = client.get("/api/u/viewer")
        assert api_resp.json()["total"] == 7

    def test_comment_votes_api_returns_counts(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(
            db,
            comment_id="c1",
            vod_id=100,
            commenter_user_id=2,
            commenter_login_snapshot="viewer",
            likes=4,
            dislikes=2,
        )
        resp = client.post("/api/comments/votes", json={"comment_ids": ["c1"]})
        assert resp.status_code == 200
        assert resp.json()["items"]["c1"]["twicome_likes_count"] == 4
        assert resp.json()["items"]["c1"]["twicome_dislikes_count"] == 2


class TestQuizPage:
    def test_unknown_user_returns_404(self, client):
        resp = client.get("/u/nobody/quiz")
        assert resp.status_code == 404

    def test_known_user_returns_200(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        resp = client.get("/u/viewer/quiz")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


class TestQuizStartApi:
    def test_unknown_user_returns_404(self, client):
        resp = client.get("/api/u/nobody/quiz/start")
        assert resp.status_code == 404
        assert resp.json()["error"] == "user_not_found"

    def test_returns_questions(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        for i in range(10):
            seed_comment(db, comment_id=f"t{i}", vod_id=100, commenter_user_id=2,
                         body=f"ターゲットコメント{i}", offset_seconds=i * 10)
        for i in range(10):
            seed_comment(db, comment_id=f"o{i}", vod_id=100, commenter_user_id=3,
                         body=f"他ユーザーコメント{i}", offset_seconds=i * 10 + 1)
        resp = client.get("/api/u/viewer/quiz/start?count=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert len(data["questions"]) == 10

    def test_is_target_flag_is_correct(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        for i in range(10):
            seed_comment(db, comment_id=f"t{i}", vod_id=100, commenter_user_id=2,
                         body=f"ターゲットコメント{i}", offset_seconds=i * 10)
        for i in range(10):
            seed_comment(db, comment_id=f"o{i}", vod_id=100, commenter_user_id=3,
                         body=f"他ユーザーコメント{i}", offset_seconds=i * 10 + 1)
        resp = client.get("/api/u/viewer/quiz/start?count=10")
        questions = resp.json()["questions"]
        target_qs = [q for q in questions if q["is_target"]]
        other_qs = [q for q in questions if not q["is_target"]]
        assert len(target_qs) == 5
        assert len(other_qs) == 5

    def test_count_param_respected(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        for i in range(30):
            seed_comment(db, comment_id=f"t{i}", vod_id=100, commenter_user_id=2,
                         body=f"ターゲットコメント{i}", offset_seconds=i * 10)
        for i in range(30):
            seed_comment(db, comment_id=f"o{i}", vod_id=100, commenter_user_id=3,
                         body=f"他ユーザーコメント{i}", offset_seconds=i * 10 + 1)
        resp = client.get("/api/u/viewer/quiz/start?count=20")
        data = resp.json()
        assert data["total"] == 20


class TestVoting:
    def test_like_increments_count(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="viewer", likes=0)

        resp = client.post("/like/c1", headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        assert resp.json()["added"] == 1

        # API で確認
        data = client.get("/api/u/viewer").json()
        assert data["items"][0]["twicome_likes_count"] == 1

    def test_dislike_increments_count(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="viewer", dislikes=0)

        resp = client.post("/dislike/c1?count=3", headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        assert resp.json()["added"] == 3

    def test_api_users_commenters(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="fan1", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="fan1")
        resp = client.get("/api/users/commenters?streamer=streamer")
        assert resp.status_code == 200
        assert "fan1" in resp.json()["logins"]
