"""vod_repo の統合テスト。"""

from datetime import UTC, datetime

import pytest

from repositories import vod_repo
from tests.integration.helpers import seed_user, seed_vod


@pytest.fixture(autouse=True)
def base_data(db):
    """各テストで使う共通配信者。"""
    seed_user(db, user_id=1, login="streamer", platform="twitch")


class TestSearchVodsTiebreak:
    """created_at_utc が同値の VOD でも OFFSET ページ送りで重複・欠落が起きないこと。

    一意キー v.vod_id を最終タイブレーカーに追加する前は、同一秒に作成された VOD（別配信者が
    同じ秒に開始した VOD 等）の順序が不定になり、「さらに読み込む」ページ送りで重複・欠落が
    発生していた回帰を防ぐ（コメント一覧と同じバグクラス）。
    """

    def test_created_at_pagination_all_tied_no_overlap_or_gaps(self, db):
        # 全 VOD を同一の created_at_utc で投入 → vod_id だけが順序を一意に決める
        same_dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        for i in range(20):
            seed_vod(db, vod_id=200 + i, owner_user_id=1, title=f"VOD{i:02d}", created_at=same_dt)

        page1 = vod_repo.search_vods(db, sort="created_at", limit=10, offset=0)
        page2 = vod_repo.search_vods(db, sort="created_at", limit=10, offset=10)
        ids1 = [r["vod_id"] for r in page1]
        ids2 = [r["vod_id"] for r in page2]

        assert len(set(ids1)) == 10
        assert len(set(ids2)) == 10
        assert set(ids1).isdisjoint(set(ids2))  # ページ間で重複なし
        assert set(ids1) | set(ids2) == {200 + i for i in range(20)}  # 全件をユニークに網羅
        # 全タイ時は vod_id DESC が安定順
        assert ids1 + ids2 == list(range(219, 199, -1))

    def test_comment_count_pagination_all_tied_no_overlap_or_gaps(self, db):
        # comment_count=0・created_at_utc 同値で全タイ → vod_id がページ送りを一意化
        same_dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        for i in range(20):
            seed_vod(db, vod_id=200 + i, owner_user_id=1, title=f"VOD{i:02d}", created_at=same_dt)

        page1 = vod_repo.search_vods(db, sort="comment_count", limit=10, offset=0)
        page2 = vod_repo.search_vods(db, sort="comment_count", limit=10, offset=10)
        ids1 = [r["vod_id"] for r in page1]
        ids2 = [r["vod_id"] for r in page2]

        assert set(ids1).isdisjoint(set(ids2))
        assert set(ids1) | set(ids2) == {200 + i for i in range(20)}
