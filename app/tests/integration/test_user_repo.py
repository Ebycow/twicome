"""user_repo の統合テスト。"""
import pytest
from tests.integration.helpers import seed_comment, seed_user, seed_vod
from repositories import user_repo


class TestFindUser:
    def test_finds_existing_user(self, db):
        seed_user(db, user_id=1, login="alice", platform="twitch")
        result = user_repo.find_user(db, "alice", "twitch")
        assert result is not None
        assert result["login"] == "alice"
        assert result["user_id"] == 1

    def test_returns_none_for_unknown_user(self, db):
        result = user_repo.find_user(db, "nobody", "twitch")
        assert result is None

    def test_platform_scoped(self, db):
        seed_user(db, user_id=1, login="alice", platform="twitch")
        result = user_repo.find_user(db, "alice", "youtube")
        assert result is None

    def test_returns_profile_image_url(self, db):
        seed_user(db, user_id=1, login="alice", platform="twitch",
                  profile_image_url="https://example.com/alice.png")
        result = user_repo.find_user(db, "alice", "twitch")
        assert result["profile_image_url"] == "https://example.com/alice.png"

    def test_profile_image_url_none_when_not_set(self, db):
        seed_user(db, user_id=1, login="alice", platform="twitch", profile_image_url=None)
        result = user_repo.find_user(db, "alice", "twitch")
        assert result["profile_image_url"] is None


class TestFetchIndexUsers:
    def test_returns_users_with_comment_count(self, db):
        owner = seed_user(db, user_id=10, login="streamer", platform="twitch")
        commenter = seed_user(db, user_id=11, login="viewer", platform="twitch")
        vod = seed_vod(db, vod_id=200, owner_user_id=10)
        seed_comment(db, comment_id="c1", vod_id=200, commenter_user_id=11,
                     commenter_login_snapshot="viewer")
        seed_comment(db, comment_id="c2", vod_id=200, commenter_user_id=11,
                     commenter_login_snapshot="viewer")

        users = user_repo.fetch_index_users(db)
        viewer = next((u for u in users if u["login"] == "viewer"), None)
        assert viewer is not None
        assert viewer["comment_count"] == 2

    def test_only_twitch_platform(self, db):
        seed_user(db, user_id=1, login="twitch_user", platform="twitch")
        seed_user(db, user_id=2, login="youtube_user", platform="youtube")
        users = user_repo.fetch_index_users(db)
        logins = [u["login"] for u in users]
        assert "twitch_user" in logins
        assert "youtube_user" not in logins


class TestFetchUserVodOptions:
    def test_returns_vods_user_commented_on(self, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1, title="配信1")
        seed_vod(db, vod_id=101, owner_user_id=1, title="配信2")
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2)
        # vod_id=101 にはコメントしていない

        options = user_repo.fetch_user_vod_options(db, uid=2, owner_user_id=None)
        vod_ids = [o["vod_id"] for o in options]
        assert 100 in vod_ids
        assert 101 not in vod_ids

    def test_filtered_by_owner(self, db):
        seed_user(db, user_id=1, login="streamer1", platform="twitch")
        seed_user(db, user_id=2, login="streamer2", platform="twitch")
        seed_user(db, user_id=3, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_vod(db, vod_id=101, owner_user_id=2)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=3)
        seed_comment(db, comment_id="c2", vod_id=101, commenter_user_id=3)

        options = user_repo.fetch_user_vod_options(db, uid=3, owner_user_id=1)
        vod_ids = [o["vod_id"] for o in options]
        assert 100 in vod_ids
        assert 101 not in vod_ids


class TestFetchCommentersForStreamer:
    def test_returns_commenters(self, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer_a", platform="twitch")
        seed_user(db, user_id=3, login="viewer_b", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="viewer_a")
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=3,
                     commenter_login_snapshot="viewer_b")

        logins = user_repo.fetch_commenters_for_streamer(db, "streamer")
        assert "viewer_a" in logins
        assert "viewer_b" in logins

    def test_no_commenters_for_unknown_streamer(self, db):
        logins = user_repo.fetch_commenters_for_streamer(db, "nobody")
        assert logins == []
