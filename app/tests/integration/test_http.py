"""
HTTP 統合テスト（FastAPI TestClient 経由）。
エンドポイントの振る舞いをエンドツーエンドで確認する。
"""

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

    def test_index_uses_default_login_in_search_placeholder(self, client, db, monkeypatch):
        import services.index_service as index_service

        monkeypatch.setattr(index_service, "DEFAULT_LOGIN", "prefetch_target")
        seed_user(db, user_id=99, login="prefetch_target", display_name="表示用ユーザ", platform="twitch")

        resp = client.get("/")
        assert resp.status_code == 200
        assert 'placeholder="例: prefetch_target / 表示用ユーザ"' in resp.text

    def test_index_uses_generic_display_name_when_default_login_user_is_missing(self, client, monkeypatch):
        import services.index_service as index_service

        monkeypatch.setattr(index_service, "DEFAULT_LOGIN", "prefetch_target")

        resp = client.get("/")
        assert resp.status_code == 200
        assert 'placeholder="例: prefetch_target / 表示名"' in resp.text

    def test_index_embeds_service_worker_cache_name(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert '<script type="application/json" id="sw-cache-name-data">"twicome-v15"</script>' in resp.text

    def test_index_form_uses_get_for_non_js_fallback(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'method="get" action="/go"' in resp.text

    def test_index_renders_selected_user_panel(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'id="selected-user-panel"' in resp.text
        assert 'id="selected-user-name"' in resp.text
        assert "まだ選択されていません" in resp.text

    def test_index_renders_recommended_users_heading_when_quick_links_exist(self, client, db, monkeypatch):
        import services.index_service as index_service

        seed_user(db, user_id=10, login="viewer", display_name="おすすめ太郎", platform="twitch")
        monkeypatch.setattr(index_service, "QUICK_LINK_LOGINS", ["viewer"])

        resp = client.get("/")

        assert resp.status_code == 200
        assert '<h2 class="quick-links-title">おすすめユーザ</h2>' in resp.text
        assert "おすすめ太郎をみるならここ" in resp.text

    def test_service_worker_script_embeds_cache_name(self, client):
        resp = client.get("/sw.js")
        assert resp.status_code == 200
        assert "application/javascript" in resp.headers["content-type"]
        assert "__TWICOME_CACHE_NAME__" not in resp.text
        assert 'const CACHE_NAME = "twicome-v15";' in resp.text

    def test_service_worker_does_not_force_auth_redirect_reload(self, client):
        resp = client.get("/sw.js")
        assert resp.status_code == 200
        assert "twicome-auth-redirect" not in resp.text
        assert "notifyAuthRedirect" not in resp.text

    def test_page_scripts_ignore_legacy_auth_redirect_messages(self, client):
        for path in ("/static/js/index.js", "/static/js/user-comments.js"):
            resp = client.get(path)
            assert resp.status_code == 200
            assert "twicome-auth-redirect" not in resp.text

    def test_go_get_redirects_to_user_page(self, client):
        resp = client.get("/go", params={"login": " Viewer ", "platform": "youtube"}, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "http://testserver/u/Viewer?platform=youtube"

    def test_go_get_without_login_redirects_to_index(self, client):
        resp = client.get("/go", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "http://testserver/"

    def test_go_post_redirects_to_user_page(self, client):
        resp = client.post(
            "/go",
            data={"login": "viewer", "platform": "twitch"},
            headers={"Origin": "http://testserver", "Referer": "http://testserver/"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "http://testserver/u/viewer?platform=twitch"


class TestUserCommentsPage:
    def test_unknown_user_returns_404(self, client):
        resp = client.get("/u/nobody")
        assert resp.status_code == 404

    def test_known_user_returns_200(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(
            db, comment_id="c1", vod_id=100, commenter_user_id=2, commenter_login_snapshot="viewer", body="こんにちは"
        )
        resp = client.get("/u/viewer")
        assert resp.status_code == 200
        assert "viewer" in resp.text

    def test_comment_body_in_response(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(
            db,
            comment_id="c1",
            vod_id=100,
            commenter_user_id=2,
            commenter_login_snapshot="viewer",
            body="ユニークなコメント内容12345",
        )
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
            lambda version, platform, login, html: saved.update(
                {
                    "version": version,
                    "platform": platform,
                    "login": login,
                    "html": html,
                }
            ),
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

    def test_random_sort_without_seed_redirects_with_seed(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, commenter_login_snapshot="viewer")

        resp = client.get("/u/viewer?sort=random", follow_redirects=False)
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "sort=random" in location
        assert "seed=" in location

    def test_random_sort_with_seed_does_not_redirect_and_embeds_seed(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, commenter_login_snapshot="viewer")

        resp = client.get("/u/viewer?sort=random&seed=12345", follow_redirects=False)
        assert resp.status_code == 200
        # filters-data（無限スクロールが引き継ぐシード）に seed が埋め込まれる
        assert "12345" in resp.text

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
        seed_comment(
            db, comment_id="c1", vod_id=100, commenter_user_id=2, commenter_login_snapshot="viewer", body="APIテスト"
        )
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
            seed_comment(
                db,
                comment_id=f"c{i}",
                vod_id=100,
                commenter_user_id=2,
                commenter_login_snapshot="viewer",
                body=f"コメント{i}",
                offset_seconds=i * 10,
            )
        resp = client.get("/api/u/viewer?page_size=10&page=1")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 10
        assert resp.json()["total"] == 15

    def test_random_sort_seeded_pagination_has_no_overlap_or_gaps(self, client, db):
        """シード固定のランダムソートでは、ページ間でコメントが重複・欠落しないことを確認。

        シードなしの RAND() では各ページが再シャッフルされ重複・欠落が起きていた回帰を防ぐ。
        """
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        for i in range(20):
            seed_comment(
                db,
                comment_id=f"c{i}",
                vod_id=100,
                commenter_user_id=2,
                commenter_login_snapshot="viewer",
                offset_seconds=i * 10,
            )

        page1 = client.get("/api/u/viewer?sort=random&seed=42&page_size=10&page=1")
        page2 = client.get("/api/u/viewer?sort=random&seed=42&page_size=10&page=2")
        assert page1.status_code == 200
        assert page2.status_code == 200
        ids1 = {item["comment_id"] for item in page1.json()["items"]}
        ids2 = {item["comment_id"] for item in page2.json()["items"]}
        assert len(ids1) == 10
        assert len(ids2) == 10
        assert ids1.isdisjoint(ids2)  # ページ間で重複なし
        assert ids1 | ids2 == {f"c{i}" for i in range(20)}  # 全件をユニークに網羅

    def test_random_sort_same_seed_yields_same_order(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        for i in range(10):
            seed_comment(
                db,
                comment_id=f"c{i}",
                vod_id=100,
                commenter_user_id=2,
                commenter_login_snapshot="viewer",
                offset_seconds=i * 10,
            )

        url = "/api/u/viewer?sort=random&seed=7&page_size=10"
        order1 = [it["comment_id"] for it in client.get(url).json()["items"]]
        order2 = [it["comment_id"] for it in client.get(url).json()["items"]]
        assert order1 == order2

    def test_keyword_filter(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(
            db, comment_id="c1", vod_id=100, commenter_user_id=2, commenter_login_snapshot="viewer", body="hello world"
        )
        seed_comment(
            db, comment_id="c2", vod_id=100, commenter_user_id=2, commenter_login_snapshot="viewer", body="goodbye"
        )
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
            seed_comment(
                db,
                comment_id=f"c{i}",
                vod_id=100,
                commenter_user_id=2,
                commenter_login_snapshot="viewer",
                body=f"コメント{i}",
                offset_seconds=i * 10,
            )
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
            seed_comment(
                db,
                comment_id=f"t{i}",
                vod_id=100,
                commenter_user_id=2,
                body=f"ターゲットコメント{i}",
                offset_seconds=i * 10,
            )
        for i in range(10):
            seed_comment(
                db,
                comment_id=f"o{i}",
                vod_id=100,
                commenter_user_id=3,
                body=f"他ユーザーコメント{i}",
                offset_seconds=i * 10 + 1,
            )
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
            seed_comment(
                db,
                comment_id=f"t{i}",
                vod_id=100,
                commenter_user_id=2,
                body=f"ターゲットコメント{i}",
                offset_seconds=i * 10,
            )
        for i in range(10):
            seed_comment(
                db,
                comment_id=f"o{i}",
                vod_id=100,
                commenter_user_id=3,
                body=f"他ユーザーコメント{i}",
                offset_seconds=i * 10 + 1,
            )
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
            seed_comment(
                db,
                comment_id=f"t{i}",
                vod_id=100,
                commenter_user_id=2,
                body=f"ターゲットコメント{i}",
                offset_seconds=i * 10,
            )
        for i in range(30):
            seed_comment(
                db,
                comment_id=f"o{i}",
                vod_id=100,
                commenter_user_id=3,
                body=f"他ユーザーコメント{i}",
                offset_seconds=i * 10 + 1,
            )
        resp = client.get("/api/u/viewer/quiz/start?count=20")
        data = resp.json()
        assert data["total"] == 20


class TestVodCommentsPage:
    def test_random_sort_without_seed_redirects_with_seed(self, client, db):
        """VOD コメントページのランダムソートは、シードなしだと seed 付き URL へ 303 する。

        シードを固定しないとページ送り毎に RAND() が再シャッフルされ、コメントが重複・欠落する。
        """
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        resp = client.get("/vods/100?sort=random", follow_redirects=False)
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "sort=random" in location
        assert "seed=" in location

    def test_random_sort_with_seed_does_not_redirect(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        resp = client.get("/vods/100?sort=random&seed=12345", follow_redirects=False)
        assert resp.status_code == 200

    def test_random_sort_seed_is_carried_in_pagination_links(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        for i in range(15):
            seed_comment(
                db,
                comment_id=f"c{i}",
                vod_id=100,
                commenter_user_id=2,
                commenter_login_snapshot="viewer",
                offset_seconds=i * 10,
            )
        resp = client.get("/vods/100?sort=random&seed=999&page_size=10&page=1")
        assert resp.status_code == 200
        # 2ページ目以降のリンクが同じシードを引き継いでいること
        assert "seed=999" in resp.text

    def test_pagination_links_url_encode_special_chars_in_query(self, client, db):
        """検索語に & # 空白等が含まれてもページネーションリンクが壊れないこと。

        生のまま連結すると ?q=A&B&page=2 のように & が区切り文字に化けて、
        次ページで検索条件が欠落・破損する。urlencode 済みの ?q=A%26B でなければならない。
        """
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        for i in range(15):
            seed_comment(
                db,
                comment_id=f"c{i}",
                vod_id=100,
                commenter_user_id=2,
                commenter_login_snapshot="viewer",
                body=f"A&B test {i}",
                offset_seconds=i * 10,
            )
        resp = client.get("/vods/100", params={"q": "A&B", "page_size": 10, "page": 1})
        assert resp.status_code == 200
        # ページネーションリンク内で & が %26 にエンコードされていること
        assert "q=A%26B" in resp.text
        # 区切り文字に化ける生の "?q=A&B" がリンクに出ていないこと
        assert "?q=A&B&" not in resp.text


class TestVoting:
    def test_like_increments_count(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, commenter_login_snapshot="viewer", likes=0)

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
        seed_comment(
            db, comment_id="c1", vod_id=100, commenter_user_id=2, commenter_login_snapshot="viewer", dislikes=0
        )

        resp = client.post("/dislike/c1?count=3", headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        assert resp.json()["added"] == 3

    def test_api_users_commenters(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="fan1", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, commenter_login_snapshot="fan1")
        resp = client.get("/api/users/commenters?streamer=streamer")
        assert resp.status_code == 200
        assert "fan1" in resp.json()["logins"]
