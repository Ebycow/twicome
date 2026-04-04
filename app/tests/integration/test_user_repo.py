"""user_repo の統合テスト。"""

from repositories import user_repo
from tests.integration.helpers import seed_comment, seed_user, seed_vod


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
        seed_user(db, user_id=1, login="alice", platform="twitch", profile_image_url="https://example.com/alice.png")
        result = user_repo.find_user(db, "alice", "twitch")
        assert result["profile_image_url"] == "https://example.com/alice.png"

    def test_profile_image_url_none_when_not_set(self, db):
        seed_user(db, user_id=1, login="alice", platform="twitch", profile_image_url=None)
        result = user_repo.find_user(db, "alice", "twitch")
        assert result["profile_image_url"] is None


class TestFetchIndexUsers:
    def test_returns_users_with_comment_count(self, db):
        seed_user(db, user_id=10, login="streamer", platform="twitch")
        seed_user(db, user_id=11, login="viewer", platform="twitch")
        seed_vod(db, vod_id=200, owner_user_id=10)
        seed_comment(db, comment_id="c1", vod_id=200, commenter_user_id=11, commenter_login_snapshot="viewer")
        seed_comment(db, comment_id="c2", vod_id=200, commenter_user_id=11, commenter_login_snapshot="viewer")

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


class TestFetchSimilarUsers:
    def test_returns_users_sharing_multiple_streamers(self, db):
        # streamer1, streamer2 を2人が共通視聴、viewer_c は1つのみ
        seed_user(db, user_id=1, login="streamer1", platform="twitch")
        seed_user(db, user_id=2, login="streamer2", platform="twitch")
        seed_user(db, user_id=10, login="target", platform="twitch")
        seed_user(db, user_id=11, login="similar_user", platform="twitch")
        seed_user(db, user_id=12, login="viewer_c", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_vod(db, vod_id=101, owner_user_id=2)
        # target watches streamer1 and streamer2
        seed_comment(db, comment_id="t1", vod_id=100, commenter_user_id=10)
        seed_comment(db, comment_id="t2", vod_id=101, commenter_user_id=10)
        # similar_user also watches both
        seed_comment(db, comment_id="s1", vod_id=100, commenter_user_id=11)
        seed_comment(db, comment_id="s2", vod_id=101, commenter_user_id=11)
        # viewer_c watches only streamer1
        seed_comment(db, comment_id="v1", vod_id=100, commenter_user_id=12)

        result = user_repo.fetch_similar_users(db, uid=10)
        logins = [r["login"] for r in result]
        assert "similar_user" in logins
        assert "viewer_c" not in logins  # shared_count < 2

    def test_excludes_self(self, db):
        seed_user(db, user_id=1, login="streamer1", platform="twitch")
        seed_user(db, user_id=2, login="streamer2", platform="twitch")
        seed_user(db, user_id=10, login="target", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_vod(db, vod_id=101, owner_user_id=2)
        seed_comment(db, comment_id="t1", vod_id=100, commenter_user_id=10)
        seed_comment(db, comment_id="t2", vod_id=101, commenter_user_id=10)

        result = user_repo.fetch_similar_users(db, uid=10)
        logins = [r["login"] for r in result]
        assert "target" not in logins

    def test_returns_empty_when_no_shared(self, db):
        seed_user(db, user_id=1, login="streamer1", platform="twitch")
        seed_user(db, user_id=10, login="target", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="t1", vod_id=100, commenter_user_id=10)

        result = user_repo.fetch_similar_users(db, uid=10)
        assert result == []

    def test_shared_count_is_correct(self, db):
        seed_user(db, user_id=1, login="s1", platform="twitch")
        seed_user(db, user_id=2, login="s2", platform="twitch")
        seed_user(db, user_id=3, login="s3", platform="twitch")
        seed_user(db, user_id=10, login="target", platform="twitch")
        seed_user(db, user_id=11, login="other", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_vod(db, vod_id=101, owner_user_id=2)
        seed_vod(db, vod_id=102, owner_user_id=3)
        for vod in [100, 101, 102]:
            seed_comment(db, comment_id=f"t{vod}", vod_id=vod, commenter_user_id=10)
            seed_comment(db, comment_id=f"o{vod}", vod_id=vod, commenter_user_id=11)

        result = user_repo.fetch_similar_users(db, uid=10)
        assert len(result) == 1
        assert result[0]["shared_count"] == 3


class TestFetchSharedStreamers:
    def test_returns_shared_streamer_names(self, db):
        seed_user(db, user_id=1, login="streamer_a", display_name="配信者A", platform="twitch")
        seed_user(db, user_id=2, login="streamer_b", display_name="配信者B", platform="twitch")
        seed_user(db, user_id=10, login="target", platform="twitch")
        seed_user(db, user_id=11, login="other", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_vod(db, vod_id=101, owner_user_id=2)
        seed_comment(db, comment_id="t1", vod_id=100, commenter_user_id=10)
        seed_comment(db, comment_id="t2", vod_id=101, commenter_user_id=10)
        seed_comment(db, comment_id="o1", vod_id=100, commenter_user_id=11)
        seed_comment(db, comment_id="o2", vod_id=101, commenter_user_id=11)

        result = user_repo.fetch_shared_streamers(db, uid=10, other_uids=[11])
        assert 11 in result
        names = result[11]
        assert "配信者A" in names
        assert "配信者B" in names

    def test_returns_empty_for_no_other_uids(self, db):
        seed_user(db, user_id=10, login="target", platform="twitch")
        result = user_repo.fetch_shared_streamers(db, uid=10, other_uids=[])
        assert result == {}


class TestFetchCommentersForStreamer:
    def test_returns_commenters(self, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer_a", platform="twitch")
        seed_user(db, user_id=3, login="viewer_b", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, commenter_login_snapshot="viewer_a")
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=3, commenter_login_snapshot="viewer_b")

        logins = user_repo.fetch_commenters_for_streamer(db, "streamer")
        assert "viewer_a" in logins
        assert "viewer_b" in logins

    def test_no_commenters_for_unknown_streamer(self, db):
        logins = user_repo.fetch_commenters_for_streamer(db, "nobody")
        assert logins == []
