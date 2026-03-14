"""
使い方ガイドページ (/manual) と 配信者追加ページ (/add_user) の Playwright UI テスト

【このファイルで学べること】

  1. 静的コンテンツの確認        : 固定テキスト・目次・セクションの存在チェック
  2. クエリパラメータの表示確認  : ?message= / ?error= でメッセージが描画されるか
  3. 要素数の下限チェック        : locator.count() で「N件以上ある」を確認する
  4. has_text を使った検索       : page.locator("tag", has_text="...") で絞り込む
"""

import re

from playwright.sync_api import Page, expect


class TestManualPageLoad:
    """使い方ガイドページが正しく表示されることを確認するテスト群。"""

    def test_page_title(self, page: Page):
        """
        【確認内容】タイトルに "使い方ガイド" が含まれる

        base.html の {% block title %} が正しく機能していることの確認でもある。
        """
        page.goto("/manual")
        expect(page).to_have_title(re.compile("使い方ガイド"))

    def test_toc_is_visible(self, page: Page):
        """
        【確認内容】目次ブロック (.toc) が画面に表示される

        manual.html 固有の .toc クラスが DOM に存在し見えていることを確認。
        """
        page.goto("/manual")
        expect(page.locator(".toc")).to_be_visible()

    def test_toc_has_multiple_links(self, page: Page):
        """
        【確認内容】目次に 5 件以上のリンクがある

        テンプレートに固定で 14 項目書いてあるが、最低限の下限のみチェックする。
        locator.count() は expect を使わずに数値を直接取れる。
        """
        page.goto("/manual")
        count = page.locator(".toc a").count()
        assert count >= 5

    def test_sections_are_rendered(self, page: Page):
        """
        【確認内容】.section 要素が複数レンダリングされている

        コンテンツの大半がセクションで構成されているため、
        セクション数が適切かを確認する。
        """
        page.goto("/manual")
        count = page.locator(".section").count()
        assert count >= 5

    def test_back_to_index_link_visible(self, page: Page):
        """
        【確認内容】"← トップに戻る" リンクが表示されている

        page.locator("a", has_text="...") はテキスト内容で要素を絞り込む方法。
        """
        page.goto("/manual")
        back_link = page.locator("a", has_text="トップに戻る").first
        expect(back_link).to_be_visible()


class TestManualNavigation:
    """使い方ガイドのナビゲーション動作を確認するテスト群。"""

    def test_back_link_goes_to_index(self, page: Page):
        """
        【確認内容】"← トップに戻る" をクリックするとトップページに遷移する

        page.locator(...).click() → expect(page).to_have_url() の基本パターン。
        """
        page.goto("/manual")
        page.locator("a", has_text="トップに戻る").first.click()
        expect(page).to_have_url(re.compile(r"/$"))

    def test_toc_anchor_link_scrolls_within_page(self, page: Page):
        """
        【確認内容】目次の "#overview" リンクをクリックしてもページ内遷移のみ

        ページ外に出ないことを URL が変わらないか、変わっても # のみかで確認する。
        """
        page.goto("/manual")
        first_toc_link = page.locator(".toc a").first
        first_toc_link.click()
        # ページ遷移ではなくアンカー移動なので /manual は維持される
        expect(page).to_have_url(re.compile(r"/manual"))


class TestAddUserPageLoad:
    """配信者追加ページ (/add_user) の表示を確認するテスト群。"""

    def test_page_title(self, page: Page):
        """【確認内容】タイトルに "配信者" または "追加" が含まれる"""
        page.goto("/add_user")
        expect(page).to_have_title(re.compile("追加|配信者"))

    def test_form_has_username_input(self, page: Page):
        """
        【確認内容】ユーザー名入力フィールドが表示されている

        add_user.html の <input name="username"> を確認する。
        """
        page.goto("/add_user")
        expect(page.locator("input[name='username']")).to_be_visible()

    def test_submit_button_exists(self, page: Page):
        """【確認内容】フォームの送信ボタンが表示されている"""
        page.goto("/add_user")
        expect(page.locator("button[type='submit']")).to_be_visible()

    def test_users_table_is_rendered(self, page: Page):
        """
        【確認内容】現在の監視対象ユーザーテーブルが表示されている

        CSV が存在しなくてもテーブル自体は表示される（行は 0 件）。
        """
        page.goto("/add_user")
        expect(page.locator("table")).to_be_visible()


class TestAddUserMessageDisplay:
    """クエリパラメータ経由のメッセージ表示を確認するテスト群。"""

    def test_message_param_is_displayed(self, page: Page):
        """
        【確認内容】?message=... クエリパラメータの内容がページに表示される

        RedirectResponse のリダイレクト先にメッセージを埋め込む実装を
        直接 GET で確認するパターン。
        """
        page.goto("/add_user?message=追加に成功しました")
        expect(page.locator("body")).to_contain_text("追加に成功しました")

    def test_error_param_is_displayed(self, page: Page):
        """
        【確認内容】?error=... クエリパラメータの内容がページに表示される

        フォームのバリデーションエラーがどう見えるかを確認する。
        """
        page.goto("/add_user?error=ユーザが見つかりませんでした")
        expect(page.locator("body")).to_contain_text("ユーザが見つかりませんでした")
