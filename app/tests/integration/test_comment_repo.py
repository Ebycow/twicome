"""comment_repo の統合テスト。"""
from datetime import datetime, timezone

import pytest
from tests.integration.helpers import seed_comment, seed_user, seed_vod
from repositories import comment_repo


@pytest.fixture(autouse=True)
def base_data(db):
    """各テストで使う共通ベースデータ。"""
    seed_user(db, user_id=1, login="streamer", platform="twitch")
    seed_user(db, user_id=2, login="viewer", platform="twitch")
    seed_vod(db, vod_id=100, owner_user_id=1, title="テスト配信",
             url="https://www.twitch.tv/videos/100")


class TestCountComments:
    def test_counts_all_comments(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2)
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2)
        assert comment_repo.count_comments(db, uid=2) == 2

    def test_count_zero_for_no_comments(self, db):
        assert comment_repo.count_comments(db, uid=2) == 0

    def test_filter_by_vod(self, db):
        seed_vod(db, vod_id=101, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2)
        seed_comment(db, comment_id="c2", vod_id=101, commenter_user_id=2)
        assert comment_repo.count_comments(db, uid=2, vod_id=100) == 1

    def test_filter_by_keyword(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="hello world")
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2, body="goodbye")
        assert comment_repo.count_comments(db, uid=2, q="hello") == 1

    def test_filter_exclude_term(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="hello world")
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2, body="goodbye")
        assert comment_repo.count_comments(db, uid=2, exclude_terms=["hello"]) == 1


class TestFetchComments:
    def test_returns_comments(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="コメント1")
        rows = comment_repo.fetch_comments(db, uid=2)
        assert len(rows) == 1
        assert rows[0]["body"] == "コメント1"

    def test_pagination(self, db):
        for i in range(5):
            seed_comment(db, comment_id=f"c{i}", vod_id=100, commenter_user_id=2,
                         body=f"コメント{i}", offset_seconds=i * 10)
        rows = comment_repo.fetch_comments(db, uid=2, limit=2, offset=0)
        assert len(rows) == 2

    def test_sort_by_likes(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="low", likes=1)
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2, body="high", likes=10)
        rows = comment_repo.fetch_comments(db, uid=2, sort="likes")
        assert rows[0]["body"] == "high"

    def test_includes_vod_info(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2)
        rows = comment_repo.fetch_comments(db, uid=2)
        assert rows[0]["vod_title"] == "テスト配信"
        assert rows[0]["vod_url"] == "https://www.twitch.tv/videos/100"

    def test_includes_owner_info(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2)
        rows = comment_repo.fetch_comments(db, uid=2)
        assert rows[0]["owner_login"] == "streamer"

    def test_only_own_comments(self, db):
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="mine")
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=3, body="theirs")
        rows = comment_repo.fetch_comments(db, uid=2)
        assert all(r["body"] == "mine" for r in rows)


class TestFindCommentById:
    def test_finds_comment(self, db):
        seed_comment(db, comment_id="c001", vod_id=100, commenter_user_id=2, body="見つかる")
        row = comment_repo.find_comment_by_id(db, "c001")
        assert row is not None
        assert row["body"] == "見つかる"

    def test_returns_none_for_unknown(self, db):
        assert comment_repo.find_comment_by_id(db, "nonexistent") is None


class TestCountCommentsInVod:
    def test_counts_correctly(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2)
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2)
        assert comment_repo.count_comments_in_vod(db, vod_id=100) == 2

    def test_zero_for_empty_vod(self, db):
        assert comment_repo.count_comments_in_vod(db, vod_id=100) == 0


class TestFetchQuizTargetComments:
    def test_returns_target_user_comments(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="ターゲットコメント")
        rows = comment_repo.fetch_quiz_target_comments(db, uid=2, limit=10)
        assert len(rows) == 1
        assert rows[0]["body"] == "ターゲットコメント"

    def test_excludes_other_users_comments(self, db):
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="mine")
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=3, body="theirs")
        rows = comment_repo.fetch_quiz_target_comments(db, uid=2, limit=10)
        assert all(r["body"] == "mine" for r in rows)

    def test_filters_short_bodies(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="ok")   # 2文字
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2, body="長いコメント")
        rows = comment_repo.fetch_quiz_target_comments(db, uid=2, limit=10)
        assert len(rows) == 1
        assert rows[0]["body"] == "長いコメント"

    def test_respects_limit(self, db):
        for i in range(5):
            seed_comment(db, comment_id=f"c{i}", vod_id=100, commenter_user_id=2,
                         body=f"コメント{i}", offset_seconds=i * 10)
        rows = comment_repo.fetch_quiz_target_comments(db, uid=2, limit=3)
        assert len(rows) == 3

    def test_includes_vod_title(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="コメント")
        rows = comment_repo.fetch_quiz_target_comments(db, uid=2, limit=10)
        assert rows[0]["vod_title"] == "テスト配信"

    def test_returns_empty_for_no_comments(self, db):
        rows = comment_repo.fetch_quiz_target_comments(db, uid=2, limit=10)
        assert rows == []


class TestFetchQuizOtherComments:
    def test_returns_other_users_comments_in_same_vod(self, db):
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="target")
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=3, body="other comment")
        rows = comment_repo.fetch_quiz_other_comments(db, uid=2, limit=10)
        assert len(rows) == 1
        assert rows[0]["body"] == "other comment"

    def test_excludes_target_user_own_comments(self, db):
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="mine")
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=3, body="theirs")
        rows = comment_repo.fetch_quiz_other_comments(db, uid=2, limit=10)
        assert all(r["body"] != "mine" for r in rows)

    def test_excludes_vods_target_never_visited(self, db):
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_vod(db, vod_id=101, owner_user_id=1, title="別の配信")
        # uid=2 は vod_id=101 にコメントしていない
        seed_comment(db, comment_id="c1", vod_id=101, commenter_user_id=3, body="別VODコメント")
        rows = comment_repo.fetch_quiz_other_comments(db, uid=2, limit=10)
        assert rows == []

    def test_filters_short_bodies(self, db):
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="trigger")
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=3, body="ok")   # 2文字
        seed_comment(db, comment_id="c3", vod_id=100, commenter_user_id=3, body="長いコメント")
        rows = comment_repo.fetch_quiz_other_comments(db, uid=2, limit=10)
        assert len(rows) == 1
        assert rows[0]["body"] == "長いコメント"

    def test_respects_limit(self, db):
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_comment(db, comment_id="c0", vod_id=100, commenter_user_id=2, body="trigger")
        for i in range(5):
            seed_comment(db, comment_id=f"c{i+1}", vod_id=100, commenter_user_id=3,
                         body=f"コメント{i}", offset_seconds=i * 10)
        rows = comment_repo.fetch_quiz_other_comments(db, uid=2, limit=3)
        assert len(rows) == 3

    def test_returns_empty_when_target_has_no_comments(self, db):
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=3, body="other comment")
        # uid=2 はどのVODにもコメントしていない
        rows = comment_repo.fetch_quiz_other_comments(db, uid=2, limit=10)
        assert rows == []


class TestGetCursorPosition:
    def test_position_by_offset_seconds(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, offset_seconds=10)
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2, offset_seconds=30)
        seed_comment(db, comment_id="c3", vod_id=100, commenter_user_id=2, offset_seconds=60)
        # c3 (offset=60) は先頭から0番目（DESCソートで最大値が先頭）
        cursor_row = comment_repo.find_comment_by_id(db, "c3")
        pos = comment_repo.get_cursor_position(db, vod_id=100, sort="vod_time", cursor_row=cursor_row)
        assert pos == 0

    def test_position_by_likes(self, db):
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, likes=100)
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2, likes=50)
        seed_comment(db, comment_id="c3", vod_id=100, commenter_user_id=2, likes=1)
        # c3(likes=1) の前には c1, c2 がいる
        cursor_row = comment_repo.find_comment_by_id(db, "c3")
        pos = comment_repo.get_cursor_position(db, vod_id=100, sort="likes", cursor_row=cursor_row)
        assert pos == 2
