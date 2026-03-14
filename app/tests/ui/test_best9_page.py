"""
Best9 ページ (/best9) の Playwright UI テスト

【このファイルで学べること】

  1. クエリパラメータ必須ページのテスト  : IDs なしでアクセスすると 400 を返す
  2. seed した comment_id を URL に埋め込む: 実際のコメント ID を /best9?ids= に渡す
  3. 「空スロット」の確認               : 9 枠に満たない場合 .cell.empty が表示される
  4. JavaScript で動く UI を確認        : コピーボタンのテキスト変化を確認する
  5. input の value を確認              : share URL の input に値が入っているかを確認
"""

import re

from playwright.sync_api import Page, expect

from tests.integration.helpers import seed_comment, seed_user, seed_vod


def _seed_with_comment(db, *, comment_id: str = "b9-test-001", login: str = "best9user") -> str:
    """
    Best9 ページテスト用のシードデータを投入し、コメント ID を返すヘルパー。

    best9 ページは /best9?ids={comment_id} で動作するため、
    シード時に使った comment_id を返す。
    """
    seed_user(db, user_id=1, login="streamer", platform="twitch")
    seed_user(db, user_id=2, login=login, platform="twitch")
    seed_vod(db, vod_id=100, owner_user_id=1, title="Best9テスト配信")
    seed_comment(
        db,
        comment_id=comment_id,
        vod_id=100,
        commenter_user_id=2,
        commenter_login_snapshot=login,
        body="これはBest9のテストコメントです",
    )
    return comment_id


class TestErrorCases:
    """不正なパラメータでアクセスした場合の動作を確認するテスト群。"""

    def test_no_ids_param_returns_400(self, page: Page):
        """
        【確認内容】ids も z も指定しないと HTTP 400 を返す

        best9.py のガード節: `if not id_list: return HTMLResponse(..., 400)`
        """
        response = page.goto("/best9")
        assert response is not None
        assert response.status == 400

    def test_invalid_z_param_returns_400(self, page: Page):
        """
        【確認内容】壊れた z パラメータ（base64 / deflate 不正）は 400 を返す

        _decompress_ids() が例外を投げると 400 になる。
        """
        response = page.goto("/best9?z=INVALIDDATA!!!!")
        assert response is not None
        assert response.status == 400


class TestPageLoad:
    """有効なパラメータでアクセスしたときのページ表示を確認するテスト群。"""

    def test_page_title_contains_mybest9(self, page: Page, db):
        """
        【確認内容】タイトルに "#MyBest9" が含まれる

        best9.html の {% block title %}#MyBest9{{ commenter_login }}{% endblock %} の確認。
        """
        cid = _seed_with_comment(db, comment_id="b9-title-001", login="titleuser9")
        page.goto(f"/best9?ids={cid}&login=titleuser9")
        expect(page).to_have_title(re.compile("MyBest9"))

    def test_title_contains_login(self, page: Page, db):
        """
        【確認内容】タイトルにログイン名が含まれる"""
        cid = _seed_with_comment(db, comment_id="b9-login-001", login="loginuser9")
        page.goto(f"/best9?ids={cid}&login=loginuser9")
        expect(page).to_have_title(re.compile("loginuser9"))

    def test_grid_is_visible(self, page: Page, db):
        """
        【確認内容】コメントグリッド (.grid) が表示されている

        best9.html のメインコンテンツ部分の確認。
        """
        cid = _seed_with_comment(db, comment_id="b9-grid-001", login="griduser9")
        page.goto(f"/best9?ids={cid}&login=griduser9")
        expect(page.locator(".grid")).to_be_visible()

    def test_comment_cell_is_displayed(self, page: Page, db):
        """
        【確認内容】シードしたコメントが .cell として表示されている

        1 件 ID を渡すと非 empty の .cell が 1 つ描画される。
        """
        cid = _seed_with_comment(db, comment_id="b9-cell-001", login="celluser9")
        page.goto(f"/best9?ids={cid}&login=celluser9")
        # 空でない（.empty クラスがない）セルが存在することを確認
        non_empty_cells = page.locator(".cell:not(.empty)")
        expect(non_empty_cells).to_have_count(1)

    def test_empty_slots_fill_remaining(self, page: Page, db):
        """
        【確認内容】9 枠に満たない場合 .cell.empty で残りが埋められる

        1 件だけ渡すと 8 個の空スロットが表示されることを確認する。
        """
        cid = _seed_with_comment(db, comment_id="b9-empty-001", login="emptyslotuser")
        page.goto(f"/best9?ids={cid}&login=emptyslotuser")
        empty_cells = page.locator(".cell.empty")
        expect(empty_cells).to_have_count(8)

    def test_share_url_input_has_value(self, page: Page, db):
        """
        【確認内容】シェア URL の input に現在のページ URL が自動で入力されている

        best9.html の JavaScript: `shareInput.value = window.location.href;`
        input.value は DOM プロパティなので to_have_value() で確認できる。
        """
        cid = _seed_with_comment(db, comment_id="b9-share-001", login="shareuser9")
        page.goto(f"/best9?ids={cid}&login=shareuser9")
        share_input = page.locator("#share-url")
        # 値が空でないことを確認（URL が入っているはず）
        value = share_input.input_value()
        assert len(value) > 0
        assert "best9" in value

    def test_copy_button_exists(self, page: Page, db):
        """
        【確認内容】コピーボタンが表示されている"""
        cid = _seed_with_comment(db, comment_id="b9-copy-001", login="copyuser9")
        page.goto(f"/best9?ids={cid}&login=copyuser9")
        expect(page.locator("#copy-btn")).to_be_visible()

    def test_back_link_exists(self, page: Page, db):
        """
        【確認内容】コメント一覧に戻るリンクが表示されている

        best9.html の .footer に "<- {login} のコメント一覧に戻る" リンクがある。
        """
        cid = _seed_with_comment(db, comment_id="b9-back-001", login="backuser9")
        page.goto(f"/best9?ids={cid}&login=backuser9")
        back_link = page.locator(".footer a")
        expect(back_link).to_be_visible()
        href = back_link.get_attribute("href")
        assert href is not None
        assert "backuser9" in href


class TestCopyInteraction:
    """コピーボタンのインタラクションを確認するテスト群。"""

    def test_copy_button_text_changes_after_click(self, page: Page, db):
        """
        【確認内容】コピーボタンをクリックするとテキストが "コピーしました！" に変わる

        JavaScript: btn.textContent = 'コピーしました！' の動作確認。
        navigator.clipboard.writeText() は HTTPS または localhost でないと動作しないため、
        page.context.grant_permissions() でクリップボード書き込み権限を明示的に付与する。
        """
        # Clipboard API の書き込み権限をブラウザコンテキストに付与
        page.context.grant_permissions(["clipboard-write"])

        cid = _seed_with_comment(db, comment_id="b9-clickcopy-001", login="clickcopyuser")
        page.goto(f"/best9?ids={cid}&login=clickcopyuser")

        copy_btn = page.locator("#copy-btn")
        copy_btn.click()

        # JavaScript で textContent が変わるのを待つ
        expect(copy_btn).to_contain_text("コピーしました")
