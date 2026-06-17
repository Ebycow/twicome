"""comment_repo の統合テスト。"""

import pytest

from repositories import comment_repo
from tests.integration.helpers import seed_comment, seed_user, seed_vod


@pytest.fixture(autouse=True)
def base_data(db):
    """各テストで使う共通ベースデータ。"""
    seed_user(db, user_id=1, login="streamer", platform="twitch")
    seed_user(db, user_id=2, login="viewer", platform="twitch")
    seed_vod(db, vod_id=100, owner_user_id=1, title="テスト配信", url="https://www.twitch.tv/videos/100")


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
            seed_comment(
                db, comment_id=f"c{i}", vod_id=100, commenter_user_id=2, body=f"コメント{i}", offset_seconds=i * 10
            )
        rows = comment_repo.fetch_comments(db, uid=2, limit=2, offset=0)
        assert len(rows) == 2

    def test_default_sort_is_created_at_desc(self, db):
        """デフォルト（sort=created_at・フィルタなし）のサブクエリ最適化パスでも
        投稿日時降順が保証されること。外側 ORDER BY 欠落の回帰防止。"""
        from datetime import UTC, datetime

        seed_vod(db, vod_id=101, owner_user_id=1)
        # 挿入順を時系列とずらし、複数 VOD をまたいで投入する
        seed_comment(
            db,
            comment_id="mid",
            vod_id=101,
            commenter_user_id=2,
            created_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC),
        )
        seed_comment(
            db,
            comment_id="newest",
            vod_id=100,
            commenter_user_id=2,
            created_at=datetime(2024, 6, 3, 9, 0, 0, tzinfo=UTC),
        )
        seed_comment(
            db,
            comment_id="oldest",
            vod_id=101,
            commenter_user_id=2,
            created_at=datetime(2024, 6, 1, 8, 0, 0, tzinfo=UTC),
        )
        rows = comment_repo.fetch_comments(db, uid=2)
        assert [r["comment_id"] for r in rows] == ["newest", "mid", "oldest"]

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
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2, body="ok")  # 2文字
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2, body="長いコメント")
        rows = comment_repo.fetch_quiz_target_comments(db, uid=2, limit=10)
        assert len(rows) == 1
        assert rows[0]["body"] == "長いコメント"

    def test_respects_limit(self, db):
        for i in range(5):
            seed_comment(
                db, comment_id=f"c{i}", vod_id=100, commenter_user_id=2, body=f"コメント{i}", offset_seconds=i * 10
            )
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
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=3, body="ok")  # 2文字
        seed_comment(db, comment_id="c3", vod_id=100, commenter_user_id=3, body="長いコメント")
        rows = comment_repo.fetch_quiz_other_comments(db, uid=2, limit=10)
        assert len(rows) == 1
        assert rows[0]["body"] == "長いコメント"

    def test_respects_limit(self, db):
        seed_user(db, user_id=3, login="other", platform="twitch")
        seed_comment(db, comment_id="c0", vod_id=100, commenter_user_id=2, body="trigger")
        for i in range(5):
            seed_comment(
                db, comment_id=f"c{i + 1}", vod_id=100, commenter_user_id=3, body=f"コメント{i}", offset_seconds=i * 10
            )
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


class TestFetchVodCommentsFilteredRandom:
    def test_seeded_random_pagination_has_no_overlap_or_gaps(self, db):
        """シード固定のランダムソートでは、VOD コメントのページ間で重複・欠落が起きないこと。

        シードなしの RAND() では各ページが再シャッフルされ重複・欠落が起きていた回帰を防ぐ。
        """
        for i in range(20):
            seed_comment(db, comment_id=f"c{i}", vod_id=100, commenter_user_id=2, offset_seconds=i * 10)

        page1 = comment_repo.fetch_vod_comments_filtered(db, vod_id=100, sort="random", limit=10, offset=0, seed=42)
        page2 = comment_repo.fetch_vod_comments_filtered(db, vod_id=100, sort="random", limit=10, offset=10, seed=42)
        ids1 = {r["comment_id"] for r in page1}
        ids2 = {r["comment_id"] for r in page2}
        assert len(ids1) == 10
        assert len(ids2) == 10
        assert ids1.isdisjoint(ids2)  # ページ間で重複なし
        assert ids1 | ids2 == {f"c{i}" for i in range(20)}  # 全件をユニークに網羅

    def test_same_seed_yields_same_order(self, db):
        for i in range(10):
            seed_comment(db, comment_id=f"c{i}", vod_id=100, commenter_user_id=2, offset_seconds=i * 10)
        page_a = comment_repo.fetch_vod_comments_filtered(db, vod_id=100, sort="random", limit=10, offset=0, seed=7)
        page_b = comment_repo.fetch_vod_comments_filtered(db, vod_id=100, sort="random", limit=10, offset=0, seed=7)
        order1 = [r["comment_id"] for r in page_a]
        order2 = [r["comment_id"] for r in page_b]
        assert order1 == order2
