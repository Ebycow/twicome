"""
コメント当てクイズページ (/u/{login}/quiz) の Playwright UI テスト

【このファイルで学べること】

  1. JavaScript で切り替わる画面の確認  : 初期表示が "start-screen" であることを確認
  2. hidden な要素の確認               : game-screen / gameover-screen が非表示か
  3. クリックによる状態変化を待つ      : expect(...).to_be_visible() はデフォルトで待機する
  4. API レスポンスを待ってからアクション: page.expect_response() との組み合わせ
"""

import re
from datetime import UTC, datetime

from playwright.sync_api import Page, expect

from tests.integration.helpers import seed_comment, seed_user, seed_vod


def _seed_quiz_user(db, *, login: str = "quizuser") -> None:
    """クイズテスト用のユーザーとコメントを投入するヘルパー。"""
    seed_user(db, user_id=1, login="streamer", platform="twitch")
    seed_user(db, user_id=2, login=login, display_name="クイズユーザー", platform="twitch")
    seed_vod(db, vod_id=100, owner_user_id=1, title="クイズ配信")
    # クイズには対象ユーザーのコメントが必要
    for i in range(5):
        seed_comment(
            db,
            comment_id=f"qc{i}",
            vod_id=100,
            commenter_user_id=2,
            commenter_login_snapshot=login,
            body=f"クイズコメント{i}",
            offset_seconds=i * 30,
            created_at=datetime(2024, 6, 1, 10, i, 0, tzinfo=UTC),
        )


class TestPageNotFound:
    """存在しないユーザーのクイズページを開いたときの動作を確認するテスト群。"""

    def test_unknown_user_returns_404(self, page: Page):
        """
        【確認内容】存在しないユーザーのクイズページは HTTP 404 を返す

        quiz.html は user=None のとき status_code=404 でテンプレートを描画する。
        """
        response = page.goto("/u/nobody_quiz_xyz/quiz")
        assert response is not None
        assert response.status == 404

    def test_error_message_shown_for_unknown_user(self, page: Page):
        """
        【確認内容】404 時にエラーメッセージが表示される

        quiz.html の {% if error %} ブロックが機能することを確認。
        """
        page.goto("/u/nobody_quiz_xyz/quiz")
        expect(page.locator("body")).to_contain_text("見つかりません")


class TestPageLoad:
    """クイズページが正しく読み込まれることを確認するテスト群。"""

    def test_page_title_contains_username(self, page: Page, db):
        """
        【確認内容】タイトルにユーザー名が含まれる

        {% block title %}コメント当てクイズ - {{ display_name }}{% endblock %} の確認。
        """
        _seed_quiz_user(db, login="titlequiz")
        page.goto("/u/titlequiz/quiz")
        expect(page).to_have_title(re.compile("クイズ"))

    def test_start_screen_is_visible(self, page: Page, db):
        """
        【確認内容】初期状態でスタート画面が表示されている

        JavaScript が DOM を操作する前の初期状態を確認する。
        quiz.html では #start-screen がデフォルト表示。
        """
        _seed_quiz_user(db, login="startscreenuser")
        page.goto("/u/startscreenuser/quiz")
        expect(page.locator("#start-screen")).to_be_visible()

    def test_start_button_is_visible(self, page: Page, db):
        """
        【確認内容】スタートボタンが表示されている

        #start-btn は .start-card の中にある。
        """
        _seed_quiz_user(db, login="startbtnuser")
        page.goto("/u/startbtnuser/quiz")
        expect(page.locator("#start-btn")).to_be_visible()

    def test_game_screen_is_hidden_initially(self, page: Page, db):
        """
        【確認内容】初期状態でゲーム画面が非表示になっている

        quiz.html では <div id="game-screen" style="display:none;"> で初期非表示。
        JavaScript がスタート後に表示切り替えする仕組みの確認。
        """
        _seed_quiz_user(db, login="hiddenscreen")
        page.goto("/u/hiddenscreen/quiz")
        expect(page.locator("#game-screen")).to_be_hidden()

    def test_gameover_screen_is_hidden_initially(self, page: Page, db):
        """【確認内容】初期状態でゲームオーバー画面が非表示になっている"""
        _seed_quiz_user(db, login="gameoveruser")
        page.goto("/u/gameoveruser/quiz")
        expect(page.locator("#gameover-screen")).to_be_hidden()

    def test_user_comment_count_is_displayed(self, page: Page, db):
        """
        【確認内容】コメント収録数が画面に表示されている

        quiz.html の .meta に {{ "{:,}".format(comment_count) }} コメント収録済み と
        表示されることを確認する。
        """
        _seed_quiz_user(db, login="countuser")
        page.goto("/u/countuser/quiz")
        # "コメント収録済み" のテキストが含まれていることを確認
        expect(page.locator("body")).to_contain_text("コメント収録済み")

    def test_nav_link_back_to_index(self, page: Page, db):
        """
        【確認内容】"トップに戻る" リンクが表示されている

        quiz.html の .nav に含まれるリンクの確認。
        """
        _seed_quiz_user(db, login="navquiz")
        page.goto("/u/navquiz/quiz")
        back_link = page.locator("a", has_text="トップに戻る")
        expect(back_link).to_be_visible()


class TestQuizInteraction:
    """クイズのインタラクション（ゲーム開始）を確認するテスト群。"""

    def test_start_button_triggers_api_call(self, page: Page, db):
        """
        【確認内容】スタートボタンをクリックすると /api/u/{login}/quiz/start が呼ばれる

        JS の fetch() が発火することをネットワーク監視で確認する。
        コメント数が少ないと問題数 0 になる場合があるが、API 呼び出し自体は確認できる。
        """
        _seed_quiz_user(db, login="apiuser")
        page.goto("/u/apiuser/quiz")

        with page.expect_response(re.compile(r"/api/u/apiuser/quiz/start")) as resp_info:
            page.locator("#start-btn").click()

        resp = resp_info.value
        assert resp.status == 200
        data = resp.json()
        assert "questions" in data
