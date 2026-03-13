"""
ユーザーコメントページ (/u/{login}) の Playwright UI テスト

【このファイルで学べること】

  1. HTTP ステータスコードの確認    : response = page.goto(url); assert response.status == 404
  2. DBにデータを投入してページを確認: seed 関数 + page.goto() + expect(locator).to_contain_text()
  3. フォーム入力 & 送信           : locator.fill() + page.press("Enter")
  4. URL クエリパラメータの確認     : expect(page).to_have_url(re.compile(r"\?.*q=hello"))
  5. セレクトの変更               : page.select_option("#id", "value")
  6. 要素の数を確認               : expect(locator).to_have_count(n)
  7. ネットワークリクエストの確認   : page.expect_response() を使う例

【DBシードについて】
  - `db` フィクスチャ（conftest.py 定義）を使って MySQL に直接データを投入する
  - テスト終了後に TRUNCATE されるため、テスト間で干渉しない
  - サーバーもテストも同じ appdb_test を参照しているため、
    seeded data をサーバーが読み取れる
"""

import re
from datetime import datetime, timezone

import pytest
from playwright.sync_api import Page, expect

from tests.integration.helpers import seed_comment, seed_user, seed_vod


# ── ヘルパー ─────────────────────────────────────────────────────────────────

def _seed_basic(db, *, login: str = "viewer", comment_body: str = "テストコメント") -> None:
    """よく使うシードパターンをまとめたヘルパー。"""
    seed_user(db, user_id=1, login="streamer", platform="twitch")
    seed_user(db, user_id=2, login=login, platform="twitch")
    seed_vod(db, vod_id=100, owner_user_id=1, title="テスト配信")
    seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2,
                 commenter_login_snapshot=login, body=comment_body)


# ── テスト群 ─────────────────────────────────────────────────────────────────

class TestPageNotFound:
    """存在しないユーザーのページを開いたときの動作を確認するテスト群。"""

    def test_unknown_user_returns_404(self, page: Page):
        """
        【確認内容】存在しないユーザーのページは HTTP 404 を返す

        page.goto() の戻り値はレスポンスオブジェクト。
        .status でステータスコードを取得できる。

        TestClient の assert resp.status_code == 404 に相当するが、
        ブラウザが受け取った実際のステータスコードを確認している点が異なる。
        """
        response = page.goto("/u/nobody_at_all_xyz")
        assert response is not None
        assert response.status == 404

    def test_unknown_user_shows_error_content(self, page: Page):
        """
        【確認内容】404 ページにもコンテンツが表示される（エラーメッセージ等）

        ステータスコードが 404 でも HTML は返る。
        ページが空白でないことを確認する。
        """
        page.goto("/u/nobody_at_all_xyz")
        # ページに何らかのコンテンツがあることを確認
        body_text = page.locator("body").inner_text()
        assert len(body_text) > 0


class TestCommentDisplay:
    """コメントが正しく表示されることを確認するテスト群。"""

    def test_comment_body_is_displayed(self, page: Page, db):
        """
        【確認内容】DB に投入したコメントが画面に表示される

        DB にシードしてからブラウザで確認するパターン。
        expect(locator).to_contain_text() は部分一致でテキストを確認する。
        """
        _seed_basic(db, login="fan1", comment_body="ユニークなコメント文字列ABCXYZ")

        page.goto("/u/fan1")
        expect(page.locator(".body").first).to_contain_text("ユニークなコメント文字列ABCXYZ")

    def test_user_name_in_page_heading(self, page: Page, db):
        """
        【確認内容】ユーザー名がページ上部に表示される

        page.locator(".class").first は最初にマッチした要素。
        """
        _seed_basic(db, login="fan2", comment_body="なんかコメント")

        page.goto("/u/fan2")
        # ページのどこかに "fan2" が含まれていることを確認
        expect(page.locator("body")).to_contain_text("fan2")

    def test_multiple_comments_all_displayed(self, page: Page, db):
        """
        【確認内容】複数コメントがすべて表示される

        expect(locator).to_have_count(n) で要素の個数を確認できる。
        """
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="multicomment_user", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        for i in range(3):
            seed_comment(
                db,
                comment_id=f"c{i}",
                vod_id=100,
                commenter_user_id=2,
                commenter_login_snapshot="multicomment_user",
                body=f"コメント{i}",
                offset_seconds=i * 10,
                created_at=datetime(2024, 6, 1, 10, i, 0, tzinfo=timezone.utc),
            )

        page.goto("/u/multicomment_user")
        # class="comment" を持つ div が 3 つあることを確認
        expect(page.locator(".comment")).to_have_count(3)

    def test_like_button_exists_on_comment(self, page: Page, db):
        """
        【確認内容】コメントにいいねボタンが表示されている

        要素の存在確認の基本。いいねボタンは JavaScript が読み込んだ後に
        カウントを更新するため、初期表示では "😂 0" と表示される。
        """
        _seed_basic(db, login="fan3", comment_body="リアクションのテスト")

        page.goto("/u/fan3")
        like_button = page.locator(".vote-btn").first
        expect(like_button).to_be_visible()


class TestFilterForm:
    """フィルターフォームの動作を確認するテスト群。"""

    def test_keyword_filter_updates_url(self, page: Page, db):
        """
        【確認内容】キーワードを入力してフォームを送信すると URL に q= が付く

        実際のフォーム操作によって URL が変わることを確認するテスト。
        这は JavaScript 経由の非同期フェッチではなく、通常のフォーム送信 (GET) なので
        URL が変わることで確認できる。
        """
        _seed_basic(db, login="fan4", comment_body="キーワードフィルターテスト")

        page.goto("/u/fan4")

        # フィルターフォームの本文検索に入力して送信
        q_input = page.locator("input[name='q']")
        q_input.fill("hello")
        q_input.press("Enter")

        # URL に q=hello が含まれることを確認
        expect(page).to_have_url(re.compile(r"q=hello"))

    def test_sort_select_changes_url(self, page: Page, db):
        """
        【確認内容】並び順を変更すると URL の sort パラメータが変わる

        page.select_option() でドロップダウンの選択肢を変更する例。
        select 要素を変更してフォームを手動で submit する。
        """
        _seed_basic(db, login="fan5", comment_body="ソートテスト")

        page.goto("/u/fan5")

        # 並びを「いいね順」に変更
        page.select_option("#select-sort", "likes")

        # フォームを送信（submit ボタンがないためフォーム要素から送信）
        page.locator("form.card").first.evaluate("form => form.submit()")

        # URL に sort=likes が含まれることを確認
        expect(page).to_have_url(re.compile(r"sort=likes"))

    def test_filter_narrows_results(self, page: Page, db):
        """
        【確認内容】キーワードフィルターでマッチしないコメントは表示されない

        2 件投入して 1 件だけマッチするキーワードで絞り込み、
        表示件数が 1 件になることを確認する。
        """
        seed_user(db, user_id=1, login="streamer", platform="twitch")
        seed_user(db, user_id=2, login="fan6", platform="twitch")
        seed_vod(db, vod_id=100, owner_user_id=1)
        seed_comment(db, comment_id="c1", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="fan6", body="hello world",
                     offset_seconds=10,
                     created_at=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc))
        seed_comment(db, comment_id="c2", vod_id=100, commenter_user_id=2,
                     commenter_login_snapshot="fan6", body="goodbye",
                     offset_seconds=20,
                     created_at=datetime(2024, 6, 1, 10, 1, 0, tzinfo=timezone.utc))

        # q=hello でフィルターして直接アクセス（フォーム送信の代わりに URL で指定）
        page.goto("/u/fan6?q=hello")

        # "hello world" を含むコメントが 1 件表示されていることを確認
        expect(page.locator(".comment")).to_have_count(1)
        expect(page.locator(".body").first).to_contain_text("hello world")


class TestNetworkRequests:
    """ネットワークリクエストを監視するテスト群。"""

    def test_votes_api_called_on_page_load(self, page: Page, db):
        """
        【確認内容】ページ読み込み時に投票数を取得する API が呼ばれる

        page.expect_response() を使うと、特定の URL へのリクエスト/レスポンスを
        待ち受けることができる。JavaScript の非同期処理のテストに使える。

        このテストは「API が呼ばれたこと」を確認するため、
        TestClient では検証できない。
        """
        _seed_basic(db, login="fan7", comment_body="APIコールのテスト")

        # /api/comments/votes へのリクエストを待ち受ける
        with page.expect_response(re.compile(r"/api/comments/votes")) as response_info:
            page.goto("/u/fan7")

        response = response_info.value
        assert response.status == 200
        data = response.json()
        assert "items" in data
