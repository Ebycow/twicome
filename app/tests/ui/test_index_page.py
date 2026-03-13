"""
トップページ (/) の Playwright UI テスト

【このファイルで学べるUIテストの基本】

  1. ページを開く          : page.goto("/")
  2. タイトルを確認する    : expect(page).to_have_title("...")
  3. 要素が見えることを確認: expect(locator).to_be_visible()
  4. 要素が隠れていることを確認: expect(locator).to_be_hidden()
  5. テキスト入力          : page.fill("#id", "text") または locator.fill("text")
  6. 要素をクリック        : page.click("#id") または locator.click()
  7. 入力値を確認          : expect(locator).to_have_value("text")
  8. URL 遷移を確認        : expect(page).to_have_url(re.compile(r"/u/..."))
  9. テキスト内容を確認    : expect(locator).to_contain_text("...")

【pytest-playwright の page フィクスチャ】
  - `page` は pytest-playwright が自動的に提供する
  - `base_url` フィクスチャを定義することで、page.goto("/") が
    http://127.0.0.1:{port}/ として解釈される
"""

import re

from playwright.sync_api import Page, expect


class TestPageLoad:
    """ページが正しく読み込まれることを確認するテスト群。"""

    def test_page_title(self, page: Page):
        """
        【確認内容】ページタイトルが "ツイコメ" を含む

        expect(page).to_have_title() はブラウザのタブに表示されるタイトルを確認する。
        """
        page.goto("/")
        expect(page).to_have_title(re.compile("ツイコメ"))

    def test_hero_section_visible(self, page: Page):
        """
        【確認内容】ヒーローセクションに説明テキストが表示されている

        page.locator() は CSS セレクターや XPath で要素を指定する。
        expect(locator).to_be_visible() は要素が DOM に存在し、かつ画面に表示されていることを確認する。
        """
        page.goto("/")
        hero = page.locator(".hero-title")
        expect(hero).to_be_visible()
        # テキストが含まれていることも確認できる（実際のテキスト: "ツイコメ Twicome"）
        expect(hero).to_contain_text("ツイコメ")

    def test_search_input_exists(self, page: Page):
        """
        【確認内容】ユーザー名検索フォームの input が表示されている

        id セレクターで要素を特定する例。
        """
        page.goto("/")
        search_input = page.locator("#login-search")
        expect(search_input).to_be_visible()

    def test_sort_select_visible_when_streamers_exist(self, page: Page, db):
        """
        【確認内容】配信者データがあるとき、ソート選択が表示される

        `#sort-select` は Jinja2 の {% if streamers %} ブロック内にあるため、
        DB にデータがないと HTML に出力されない。
        これはサーバーサイドの条件付きレンダリングの動作確認の例。
        """
        from tests.integration.helpers import seed_user, seed_vod
        seed_user(db, user_id=1, login="somestreamer", platform="twitch")
        # streamers は users JOIN vods クエリなので VOD も必要
        seed_vod(db, vod_id=100, owner_user_id=1)

        page.goto("/")
        expect(page.locator("#sort-select")).to_be_visible()


class TestSearchInput:
    """検索フォームのインタラクティブな動作を確認するテスト群。"""

    def test_clear_button_hidden_initially(self, page: Page):
        """
        【確認内容】入力前はクリアボタンが非表示になっている

        expect(locator).to_be_hidden() は要素が display:none や visibility:hidden など
        で非表示になっていることを確認する。
        """
        page.goto("/")
        clear_btn = page.locator("#login-search-clear")
        expect(clear_btn).to_be_hidden()

    def test_clear_button_appears_after_typing(self, page: Page):
        """
        【確認内容】文字を入力するとクリアボタンが表示される

        page.fill() で input に値をセット後、JavaScript イベントが発火して
        DOM が変化することを確認する。これは TestClient では確認できない、
        UI テスト固有の検証。
        """
        page.goto("/")
        search_input = page.locator("#login-search")
        search_input.fill("testuser")

        clear_btn = page.locator("#login-search-clear")
        expect(clear_btn).to_be_visible()

    def test_clear_button_clears_input(self, page: Page):
        """
        【確認内容】クリアボタンをクリックすると入力が消える

        locator.click() でボタンをクリックし、
        expect(locator).to_have_value("") で入力が空になったことを確認する。
        """
        page.goto("/")
        search_input = page.locator("#login-search")
        search_input.fill("testuser")

        page.locator("#login-search-clear").click()

        expect(search_input).to_have_value("")

    def test_clear_button_hides_after_clearing(self, page: Page):
        """
        【確認内容】クリア後はクリアボタンが再び非表示になる

        状態の変化を段階的に確認する例。
        """
        page.goto("/")
        search_input = page.locator("#login-search")

        search_input.fill("someuser")
        expect(page.locator("#login-search-clear")).to_be_visible()  # 表示を確認

        page.locator("#login-search-clear").click()
        expect(page.locator("#login-search-clear")).to_be_hidden()   # 非表示を確認


class TestFormSubmission:
    """フォーム送信によるページ遷移を確認するテスト群。"""

    def test_form_submit_redirects_to_user_page(self, page: Page, db):
        """
        【確認内容】ユーザー名を入力して送信するとコメントページに遷移する

        page.press() でキーボード操作（Enter キー）を模倣する例。
        expect(page).to_have_url() で遷移後のURLを確認する。

        【重要な設計上の注意】
        このアプリのフォームは JS が event.preventDefault() して、
        /api/users/index から取得したユーザーリストで resolveLogin() を行う。
        マッチするユーザーが見つかったときだけ window.location.href に遷移する。

        → DB にユーザーを投入 → JS がユーザーリストを読み込むまで待機 → Enter
        という手順が必要になる。
        """
        from tests.integration.helpers import seed_user
        # DB にユーザーを投入してからページを開く
        seed_user(db, user_id=10, login="gostreamer", platform="twitch")

        # JS が /api/users/index を取得してユーザーリストを読み込むまで待機
        # expect_response は goto() より前に設定しないとレスポンスを見逃す
        with page.expect_response(re.compile(r"/api/users/index")):
            page.goto("/")

        search_input = page.locator("#login-search")
        search_input.fill("gostreamer")
        search_input.press("Enter")

        # /u/gostreamer に遷移したことを確認
        expect(page).to_have_url(re.compile(r"/u/gostreamer"))

    def test_stats_link_points_to_stats_page(self, page: Page):
        """
        【確認内容】統計ページへのリンクが href を持っている

        locator.get_attribute() で要素の属性値を取得する例。
        動的なリンク (JS で href が変わるもの) のテストにも使える。
        """
        page.goto("/")
        stats_link = page.locator("#stats-link")
        expect(stats_link).to_be_visible()
        href = stats_link.get_attribute("href")
        assert href is not None
        assert "/stats" in href
