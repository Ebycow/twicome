"""
HTML レンダリング統合テスト。

テンプレートのリファクタリング（部品化・構造変更）によるデグレを検知するための
回帰テスト。FastAPI TestClient 経由でレスポンス HTML を BeautifulSoup で検証する。

カバー範囲:
- ページ骨格（タイトル、データスクリプトタグ）
- フィルターフォーム（存在・入力値の保持）
- コメントカード（件数・投票ボタン・本文）
- コミュニティノートの条件付きレンダリング
- FAISS UI の非表示（FAISS_API_URL 未設定時）
"""
from bs4 import BeautifulSoup

from tests.integration.helpers import seed_comment, seed_user, seed_vod

# ── ヘルパー ──────────────────────────────────────────────────────────────────

def _soup(resp) -> BeautifulSoup:
    return BeautifulSoup(resp.text, "html.parser")


def _setup_viewer(db, *, n_comments=1, comment_bodies=None):
    """streamer + viewer + vod + コメント n 件を作成して viewer の login を返す。"""
    seed_user(db, user_id=1, login="streamer", platform="twitch")
    seed_user(db, user_id=2, login="viewer", platform="twitch",
              display_name="ビューワー")
    seed_vod(db, vod_id=100, owner_user_id=1, title="テスト配信タイトル")
    bodies = comment_bodies or [f"コメント{i}" for i in range(n_comments)]
    for i, body in enumerate(bodies):
        seed_comment(
            db, comment_id=f"c{i}", vod_id=100,
            commenter_user_id=2, commenter_login_snapshot="viewer",
            body=body, offset_seconds=i * 10,
        )
    return "viewer"


# ── ページ骨格 ────────────────────────────────────────────────────────────────

class TestPageStructure:
    def test_title_contains_user_login(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert "viewer" in soup.title.string

    def test_title_contains_display_name(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert "ビューワー" in soup.title.string

    def test_data_script_tags_present(self, client, db):
        """JavaScript が参照する JSON スクリプトタグが全て存在する。"""
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        for tag_id in ("filters-data", "root-path-data", "page-data",
                       "pages-data", "user-data"):
            assert soup.find("script", {"id": tag_id}) is not None, \
                f"<script id='{tag_id}'> が見つからない"

    def test_user_data_script_contains_login(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        user_data = soup.find("script", {"id": "user-data"}).string
        assert "viewer" in user_data

    def test_unknown_user_returns_404(self, client):
        resp = client.get("/u/nobody")
        assert resp.status_code == 404


# ── フィルターフォーム ────────────────────────────────────────────────────────

class TestFilterForm:
    def test_filter_form_exists(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        form = soup.find("form", {"method": "get"})
        assert form is not None

    def test_form_has_platform_hidden_input(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        hidden = soup.find("input", {"name": "platform", "type": "hidden"})
        assert hidden is not None

    def test_sort_select_exists(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(id="select-sort") is not None

    def test_page_size_select_exists(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(id="select-page-size") is not None

    def test_keyword_query_preserved_in_input(self, client, db):
        """q パラメータがフォームの input に反映される（入力値保持）。"""
        _setup_viewer(db, n_comments=3, comment_bodies=["hello", "world", "foo"])
        soup = _soup(client.get("/u/viewer?q=hello"))
        q_input = soup.find("input", {"name": "q"})
        assert q_input is not None
        assert q_input.get("value") == "hello"

    def test_exclude_query_preserved_in_input(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer?exclude_q=ng_word"))
        excl_input = soup.find("input", {"name": "exclude_q"})
        assert excl_input is not None
        assert excl_input.get("value") == "ng_word"

    def test_vod_select_exists(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(id="select-vod") is not None

    def test_owner_select_exists(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(id="select-owner") is not None

    def test_sort_options_present(self, client, db):
        """主要なソートオプションが全て選択肢に存在する。"""
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        select = soup.find(id="select-sort")
        values = [o.get("value") for o in select.find_all("option")]
        for expected in ("created_at", "vod_time", "likes", "dislikes",
                         "community_note", "danger", "random"):
            assert expected in values, f"sort オプション '{expected}' が見つからない"

    def test_owner_filtered_vod_options_loaded_even_when_quick_link_meta_cached(self, client, db, monkeypatch):
        import routers.comments as comments_router

        seed_user(db, user_id=1, login="streamer1", platform="twitch")
        seed_user(db, user_id=2, login="streamer2", platform="twitch")
        seed_user(db, user_id=3, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1, title="配信1")
        seed_vod(db, vod_id=101, owner_user_id=2, title="配信2")
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=3,
                     commenter_login_snapshot="viewer")
        seed_comment(db, comment_id="c2", vod_id=101, commenter_user_id=3,
                     commenter_login_snapshot="viewer")

        monkeypatch.setattr(comments_router, "QUICK_LINK_LOGINS", ["viewer"])
        monkeypatch.setattr(
            comments_router,
            "get_user_meta_cache",
            lambda login: {
                "vod_options": [
                    {"vod_id": 100, "title": "配信1"},
                    {"vod_id": 101, "title": "配信2"},
                ],
                "owner_options": [
                    {"user_id": 1, "login": "streamer1", "display_name": None},
                    {"user_id": 2, "login": "streamer2", "display_name": None},
                ],
            },
        )

        soup = _soup(client.get("/u/viewer?owner_user_id=1"))
        select = soup.find(id="select-vod")
        option_values = [o.get("value") for o in select.find_all("option")]
        option_texts = [o.get_text(strip=True) for o in select.find_all("option")]

        assert "100" in option_values
        assert "101" not in option_values
        assert any("配信1" in text for text in option_texts)
        assert all("配信2" not in text for text in option_texts)


# ── コメントカード ────────────────────────────────────────────────────────────

class TestCommentCards:
    def test_comment_cards_rendered(self, client, db):
        """seed したコメント数と .comment 要素の個数が一致する。"""
        _setup_viewer(db, n_comments=5)
        soup = _soup(client.get("/u/viewer?page_size=20"))
        cards = soup.find_all(class_="comment")
        assert len(cards) == 5

    def test_comment_body_in_card(self, client, db):
        _setup_viewer(db, comment_bodies=["ユニーク文字列XYZ999"])
        soup = _soup(client.get("/u/viewer"))
        assert "ユニーク文字列XYZ999" in soup.get_text()

    def test_comment_card_has_id_attribute(self, client, db):
        """コメントカードの id 属性が comment_id と一致する（カーソル機能の前提）。"""
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="test_comment_id_abc", vod_id=100,
                     commenter_user_id=2, commenter_login_snapshot="viewer")
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(id="test_comment_id_abc") is not None

    def test_each_comment_has_zeroed_vote_buttons_before_hydration(self, client, db):
        """初期 HTML は 0/0 の vote ボタンを描画し、後で実数に差し替える。"""
        _setup_viewer(db, n_comments=3)
        soup = _soup(client.get("/u/viewer?page_size=20"))
        cards = soup.find_all(class_="comment")
        for card in cards:
            deferred = card.find(attrs={"data-vote-controls": "deferred"})
            assert deferred is not None, f"comment #{card.get('id')} の deferred vote container が見つからない"
            vote_btns = card.find_all(class_="vote-btn")
            assert len(vote_btns) == 2, \
                f"comment #{card.get('id')} の初期 HTML に vote-btn が {len(vote_btns)} 個ある"
            assert vote_btns[0].get_text(strip=True) == "😂 0"
            assert vote_btns[1].get_text(strip=True) == "❓ 0"

    def test_no_comments_shows_zero_cards(self, client, db):
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        # コメントなし
        soup = _soup(client.get("/u/viewer"))
        cards = soup.find_all(class_="comment")
        assert len(cards) == 0

    def test_best9_toggle_button_present(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(id="best9-toggle-btn") is not None

    def test_scroll_sentinel_present(self, client, db):
        """無限スクロール用センチネル要素が存在する。"""
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(id="scroll-sentinel") is not None


# ── コミュニティノート ────────────────────────────────────────────────────────

class TestCommunityNotes:
    def _seed_with_note(self, db):
        from sqlalchemy import text
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="viewer", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="cn_comment", vod_id=100,
                     commenter_user_id=2, commenter_login_snapshot="viewer",
                     body="ノート付きコメント")
        db.execute(
            text("""
                INSERT INTO community_notes (
                    comment_id, note, eligible, status,
                    verifiability, harm_risk, exaggeration,
                    evidence_gap, subjectivity, issues, ask, note_json,
                    created_at_utc
                ) VALUES (
                    'cn_comment', 'これはノートです', 1, 'supported',
                    70, 80, 60, 50, 40, NULL, '', '{}',
                    NOW(6)
                )
            """)
        )
        db.commit()

    def test_community_note_section_rendered(self, client, db):
        self._seed_with_note(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(class_="community-note") is not None

    def test_community_note_body_in_html(self, client, db):
        self._seed_with_note(db)
        soup = _soup(client.get("/u/viewer"))
        assert "これはノートです" in soup.get_text()

    def test_no_community_note_section_without_note(self, client, db):
        _setup_viewer(db)  # ノートなしのコメント
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(class_="community-note") is None

    def test_cn_scores_rendered_when_harm_risk_present(self, client, db):
        self._seed_with_note(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(class_="cn-scores") is not None


# ── FAISS UI の非表示 ────────────────────────────────────────────────────────

class TestFaissUiDisabled:
    """conftest.py で FAISS_API_URL="" に設定されているため、
    FAISS 関連 UI は一切レンダリングされないことを確認する。"""

    def test_similar_search_section_absent(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(id="similar-search-btn") is None

    def test_centroid_search_section_absent(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(id="centroid-slider") is None

    def test_emotion_search_section_absent(self, client, db):
        _setup_viewer(db)
        soup = _soup(client.get("/u/viewer"))
        assert soup.find(id="emotion-sliders") is None
