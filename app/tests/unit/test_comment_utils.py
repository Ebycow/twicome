"""
services/comment_utils.py の純粋関数ユニットテスト
DB・外部API 不要。
"""
from datetime import datetime, timezone

import pytest

from services.comment_utils import (
    build_vod_link,
    build_youtube_link,
    decorate_comment,
    get_comment_body_html,
    normalize_emote_id,
    render_comment_body_html,
    seconds_to_hms,
    seconds_to_twitch_t,
    split_filter_terms,
    utc_to_jst,
)


# ── seconds_to_hms ──────────────────────────────────────────────────────────

class TestSecondsToHms:
    def test_under_one_hour(self):
        assert seconds_to_hms(90) == "01:30"

    def test_exactly_one_hour(self):
        assert seconds_to_hms(3600) == "01:00:00"

    def test_over_one_hour(self):
        assert seconds_to_hms(3661) == "01:01:01"

    def test_zero(self):
        assert seconds_to_hms(0) == "00:00"

    def test_59_minutes_59_seconds(self):
        assert seconds_to_hms(3599) == "59:59"


# ── seconds_to_twitch_t ──────────────────────────────────────────────────────

class TestSecondsToTwitchT:
    def test_hours_minutes_seconds(self):
        assert seconds_to_twitch_t(3661) == "1h1m1s"

    def test_only_seconds(self):
        assert seconds_to_twitch_t(45) == "45s"

    def test_minutes_and_seconds(self):
        assert seconds_to_twitch_t(90) == "1m30s"

    def test_zero(self):
        assert seconds_to_twitch_t(0) == "0s"

    def test_exactly_one_hour(self):
        assert seconds_to_twitch_t(3600) == "1h0s"


# ── split_filter_terms ───────────────────────────────────────────────────────

class TestSplitFilterTerms:
    def test_space_separated(self):
        assert split_filter_terms("foo bar") == ["foo", "bar"]

    def test_comma_separated(self):
        assert split_filter_terms("foo,bar") == ["foo", "bar"]

    def test_japanese_comma(self):
        assert split_filter_terms("foo、bar") == ["foo", "bar"]

    def test_mixed_separators(self):
        assert split_filter_terms("foo bar,baz") == ["foo", "bar", "baz"]

    def test_empty_string(self):
        assert split_filter_terms("") == []

    def test_none(self):
        assert split_filter_terms(None) == []

    def test_extra_whitespace(self):
        assert split_filter_terms("  foo   bar  ") == ["foo", "bar"]

    def test_single_term(self):
        assert split_filter_terms("hello") == ["hello"]


# ── normalize_emote_id ───────────────────────────────────────────────────────

class TestNormalizeEmoteId:
    def test_valid_id(self):
        assert normalize_emote_id("emotesv2_abc123") == "emotesv2_abc123"

    def test_none(self):
        assert normalize_emote_id(None) is None

    def test_empty_string(self):
        assert normalize_emote_id("") is None

    def test_invalid_chars(self):
        assert normalize_emote_id("emote/id") is None

    def test_numeric_id(self):
        assert normalize_emote_id("12345") == "12345"

    def test_whitespace_stripped(self):
        assert normalize_emote_id("  abc  ") is None  # スペース含むので invalid


# ── build_vod_link ───────────────────────────────────────────────────────────

class TestBuildVodLink:
    def test_basic(self):
        link = build_vod_link("https://www.twitch.tv/videos/123", 90)
        assert link == "https://www.twitch.tv/videos/123?t=1m30s"

    def test_url_already_has_query(self):
        link = build_vod_link("https://www.twitch.tv/videos/123?foo=bar", 60)
        assert link == "https://www.twitch.tv/videos/123?foo=bar&t=1m0s"

    def test_none_url(self):
        assert build_vod_link(None, 90) is None

    def test_zero_offset(self):
        link = build_vod_link("https://www.twitch.tv/videos/123", 0)
        assert link == "https://www.twitch.tv/videos/123?t=0s"


# ── build_youtube_link ───────────────────────────────────────────────────────

class TestBuildYoutubeLink:
    def test_basic(self):
        link = build_youtube_link("https://www.youtube.com/watch?v=abc", 90)
        assert "t=90s" in link

    def test_none_url(self):
        assert build_youtube_link(None, 90) is None

    def test_negative_offset_clamped(self):
        link = build_youtube_link("https://www.youtube.com/watch?v=abc", -10)
        assert "t=0s" in link

    def test_existing_t_param_replaced(self):
        link = build_youtube_link("https://www.youtube.com/watch?v=abc&t=10s", 120)
        assert "t=120s" in link
        assert "t=10s" not in link


# ── render_comment_body_html ─────────────────────────────────────────────────

class TestRenderCommentBodyHtml:
    def test_plain_text(self):
        result = render_comment_body_html(None, "hello world")
        assert result == "hello world"

    def test_html_escaped(self):
        result = render_comment_body_html(None, "<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_with_emote_fragment(self):
        raw = {
            "message": {
                "fragments": [
                    {"text": "Kappa", "emoticon": {"emoticon_id": "25"}}
                ]
            }
        }
        result = render_comment_body_html(raw, "Kappa")
        assert '<img class="emote"' in result
        assert 'alt="Kappa"' in result
        assert "jtvnw.net" in result

    def test_with_text_and_emote_mixed(self):
        raw = {
            "message": {
                "fragments": [
                    {"text": "hello ", "emoticon": {}},
                    {"text": "Kappa", "emoticon": {"emoticon_id": "25"}},
                ]
            }
        }
        result = render_comment_body_html(raw, "fallback")
        assert "hello " in result
        assert '<img class="emote"' in result

    def test_empty_fragments_falls_back(self):
        raw = {"message": {"fragments": []}}
        result = render_comment_body_html(raw, "fallback text")
        assert result == "fallback text"

    def test_invalid_json_falls_back(self):
        result = render_comment_body_html("not json", "fallback")
        assert result == "fallback"

    def test_xss_in_emote_text(self):
        raw = {
            "message": {
                "fragments": [
                    {"text": '<img src=x onerror=alert(1)>', "emoticon": {"emoticon_id": "25"}}
                ]
            }
        }
        result = render_comment_body_html(raw, "fallback")
        assert "onerror" not in result


# ── get_comment_body_html ────────────────────────────────────────────────────

class TestGetCommentBodyHtml:
    def test_uses_stored_html_when_version_matches(self):
        row = {
            "body_html": "<b>cached</b>",
            "body_html_version": 1,
            "raw_json": None,
            "body": "cached",
        }
        assert get_comment_body_html(row) == "<b>cached</b>"

    def test_rerenders_when_version_mismatch(self):
        row = {
            "body_html": "<b>old</b>",
            "body_html_version": 0,
            "raw_json": None,
            "body": "plain text",
        }
        result = get_comment_body_html(row)
        assert result == "plain text"

    def test_rerenders_when_no_stored_html(self):
        row = {
            "body_html": None,
            "body_html_version": None,
            "raw_json": None,
            "body": "plain text",
        }
        result = get_comment_body_html(row)
        assert result == "plain text"


# ── utc_to_jst ───────────────────────────────────────────────────────────────

class TestUtcToJst:
    def test_converts_correctly(self):
        dt_utc = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        dt_jst = utc_to_jst(dt_utc)
        assert dt_jst.hour == 9
        assert dt_jst.day == 1

    def test_naive_datetime_treated_as_utc(self):
        dt_naive = datetime(2024, 1, 1, 15, 0, 0)
        dt_jst = utc_to_jst(dt_naive)
        assert dt_jst.hour == 0
        assert dt_jst.day == 2  # 15:00 UTC → 00:00 JST 翌日


# ── decorate_comment ─────────────────────────────────────────────────────────

class TestDecorateComment:
    def _base_row(self, **kwargs):
        row = {
            "comment_id": "c1",
            "vod_id": 123,
            "offset_seconds": 90,
            "comment_created_at_utc": datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
            "body": "hello",
            "body_html": "hello",
            "body_html_version": 1,
            "raw_json": None,
            "vod_url": "https://www.twitch.tv/videos/123",
            "youtube_url": None,
            "user_color": None,
            "bits_spent": 0,
            "twicome_likes_count": 0,
            "twicome_dislikes_count": 0,
        }
        row.update(kwargs)
        return row

    def test_offset_hms_computed(self):
        row = self._base_row(offset_seconds=90)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = decorate_comment(row, now)
        assert result["offset_hms"] == "01:30"

    def test_vod_link_built(self):
        row = self._base_row(offset_seconds=90)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = decorate_comment(row, now)
        assert "t=1m30s" in result["vod_link"]

    def test_raw_json_removed(self):
        row = self._base_row()
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = decorate_comment(row, now)
        assert "raw_json" not in result
        assert "body_html_version" not in result

    def test_relative_time_hours(self):
        row = self._base_row(
            comment_created_at_utc=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        )
        now = datetime(2024, 6, 1, 12, 30, 0, tzinfo=timezone.utc)
        result = decorate_comment(row, now)
        assert "2時間" in result["relative_time"]

    def test_relative_time_days(self):
        row = self._base_row(
            comment_created_at_utc=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        )
        now = datetime(2024, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
        result = decorate_comment(row, now)
        assert "日前" in result["relative_time"]

    def test_is_recent_within_24h(self):
        row = self._base_row(
            comment_created_at_utc=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        )
        now = datetime(2024, 6, 1, 20, 0, 0, tzinfo=timezone.utc)
        result = decorate_comment(row, now)
        assert result["is_recent"] is True

    def test_is_recent_false_over_24h(self):
        row = self._base_row(
            comment_created_at_utc=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        )
        now = datetime(2024, 6, 2, 11, 0, 0, tzinfo=timezone.utc)
        result = decorate_comment(row, now)
        assert result["is_recent"] is False

    def test_string_created_at_parsed(self):
        """Redis キャッシュから復元した文字列の datetime を正しく扱う。"""
        row = self._base_row(comment_created_at_utc="2024-06-01T10:00:00")
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = decorate_comment(row, now)
        assert result["relative_time"] is not None
