"""
統計ページ (/u/{login}/stats) の Playwright UI テスト

【このファイルで学べること】

  1. Chart.js の canvas 要素を確認する  : id セレクターで canvas の存在を確認
  2. ナビゲーションリンクの href 確認   : get_attribute("href") で遷移先を検証
  3. データなし状態の表示確認           : コメント 0 件でもページが成立するか
  4. データあり状態の表示確認           : seed データを入れてグラフ領域の存在確認
"""

import re
from datetime import UTC, datetime

from playwright.sync_api import Page, expect

from tests.integration.helpers import seed_comment, seed_user, seed_vod


def _seed_user_with_comments(db, *, login: str = "statsuser") -> None:
    """統計ページのテスト用シードデータを投入するヘルパー。"""
    seed_user(db, user_id=1, login="streamer", platform="twitch")
    seed_user(db, user_id=2, login=login, platform="twitch")
    seed_vod(db, vod_id=100, owner_user_id=1, title="テスト配信")
    for i in range(3):
        seed_comment(
            db,
            comment_id=f"sc{i}",
            vod_id=100,
            commenter_user_id=2,
            commenter_login_snapshot=login,
            body=f"コメント{i}",
            offset_seconds=i * 60,
            created_at=datetime(2024, 6, 1, 10 + i, 0, 0, tzinfo=UTC),
        )


class TestPageNotFound:
    """存在しないユーザーの統計ページを開いたときの動作を確認するテスト群。"""

    def test_unknown_user_returns_404(self, page: Page):
        """
        【確認内容】存在しないユーザーの統計ページは HTTP 404 を返す

        user_stats.html は 404 時もテンプレートを描画するため、
        ステータスコードを明示的に確認する必要がある。
        """
        response = page.goto("/u/nobody_stats_xyz/stats")
        assert response is not None
        assert response.status == 404

    def test_error_message_is_shown(self, page: Page):
        """
        【確認内容】404 時にエラーカードが表示される

        user_stats.html の {% if error %} ブロックが機能することを確認。
        """
        page.goto("/u/nobody_stats_xyz/stats")
        expect(page.locator(".card.error, .error")).to_be_visible()


class TestPageLoad:
    """統計ページが正しく読み込まれることを確認するテスト群。"""

    def test_page_title_contains_username(self, page: Page, db):
        """
        【確認内容】タイトルにユーザー名が含まれる

        {% block title %}統計 - {{ user.login }}{% endblock %} の確認。
        """
        _seed_user_with_comments(db, login="titleuser")
        page.goto("/u/titleuser/stats")
        expect(page).to_have_title(re.compile("titleuser"))

    def test_hourly_chart_canvas_exists(self, page: Page, db):
        """
        【確認内容】時間帯分布チャートの canvas 要素が DOM に存在する

        Chart.js は canvas に描画するため、canvas の存在 = グラフ領域の存在。
        JavaScript の実行結果ではなく DOM 要素の存在を確認する点に注意。
        """
        _seed_user_with_comments(db, login="chartuser")
        page.goto("/u/chartuser/stats")
        expect(page.locator("#statsChart")).to_be_attached()

    def test_weekday_chart_canvas_exists(self, page: Page, db):
        """
        【確認内容】曜日分布チャートの canvas 要素が DOM に存在する

        複数の canvas が同ページに存在するケースの確認。
        """
        _seed_user_with_comments(db, login="weekdayuser")
        page.goto("/u/weekdayuser/stats")
        expect(page.locator("#weekdayChart")).to_be_attached()

    def test_nav_link_back_to_index_exists(self, page: Page, db):
        """
        【確認内容】"← 検索に戻る" リンクが表示されている

        ページ内ナビゲーションの確認。
        """
        _seed_user_with_comments(db, login="navuser")
        page.goto("/u/navuser/stats")
        back_link = page.locator("a", has_text="検索に戻る").first
        expect(back_link).to_be_visible()

    def test_nav_link_to_manual_exists(self, page: Page, db):
        """
        【確認内容】"使い方ガイド" リンクが表示されている

        user_stats.html の top-links に含まれるリンクの確認。
        """
        _seed_user_with_comments(db, login="manualuser")
        page.goto("/u/manualuser/stats")
        manual_link = page.locator("a", has_text="使い方ガイド")
        expect(manual_link).to_be_visible()
        href = manual_link.get_attribute("href")
        assert href is not None
        assert "/manual" in href

    def test_owners_table_is_rendered(self, page: Page, db):
        """
        【確認内容】配信者ごとのアクティブ状況テーブルが表示される

        seed データがある場合、コメントした配信者の統計が表示される。
        """
        _seed_user_with_comments(db, login="tableuser")
        page.goto("/u/tableuser/stats")
        # テーブルヘッダーが存在することで確認（データがなくてもヘッダーは出る）
        expect(page.locator("table")).to_be_visible()


class TestEgoGraph:
    """似ているユーザーグラフセクションのテスト群。"""

    def test_ego_graph_container_exists(self, page: Page, db):
        """
        【確認内容】ego-graph-container が DOM に存在する

        ユーザーが存在すれば、グラフコンテナは常にレンダリングされる。
        """
        _seed_user_with_comments(db, login="egographuser")
        page.goto("/u/egographuser/stats")
        expect(page.locator("#ego-graph-container")).to_be_attached()

    def test_ego_graph_not_rendered_on_404(self, page: Page):
        """
        【確認内容】404 時は ego-graph-container が存在しない

        user が None の場合テンプレートの {% if user %} ブロックが描画されないことを確認。
        """
        page.goto("/u/nobody_ego_xyz/stats")
        expect(page.locator("#ego-graph-container")).not_to_be_attached()


class TestNoDataDisplay:
    """コメントデータが 0 件の場合の表示を確認するテスト群。"""

    def test_page_loads_without_comments(self, page: Page, db):
        """
        【確認内容】コメントが 0 件でも統計ページが正常に描画される

        エラーなく 200 が返ることを確認する。
        グラフは空データで Chart.js が描画するため DOM 自体は成立する。
        """
        seed_user(db, user_id=1, login="emptyuser", platform="twitch")
        response = page.goto("/u/emptyuser/stats")
        assert response is not None
        assert response.status == 200

    def test_chart_canvases_exist_with_no_data(self, page: Page, db):
        """
        【確認内容】コメント 0 件でも canvas 要素が存在する

        Chart.js はデータが空でも canvas は DOM に保持される。
        """
        seed_user(db, user_id=1, login="nodata_stats", platform="twitch")
        page.goto("/u/nodata_stats/stats")
        expect(page.locator("#statsChart")).to_be_attached()
