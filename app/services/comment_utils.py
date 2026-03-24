"""コメントデータ加工ユーティリティ"""

import html
import json
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

import pytz

BODY_HTML_RENDER_VERSION = 1

_ALLOWED_IMG_ATTRS = frozenset(["src", "srcset", "alt", "title", "loading", "decoding"])
_ALLOWED_SRC_PREFIX = "https://static-cdn.jtvnw.net/"


class _BodyHtmlSanitizer(HTMLParser):
    """body_html フィールドから安全な要素のみを抽出するサニタイザー。

    許可: テキストノード、<img class="emote"> (jtvnw.net URL のみ)
    その他のタグはすべて除去する。
    """

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        # 許可されていないタグの内側にいる深さ（テキストを抑制するため）
        self._suppress_depth: int = 0

    def handle_data(self, data: str) -> None:
        if self._suppress_depth == 0:
            self._parts.append(html.escape(data))

    def handle_entityref(self, name: str) -> None:
        if self._suppress_depth == 0:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._suppress_depth == 0:
            self._parts.append(f"&#{name};")

    def handle_endtag(self, tag: str) -> None:
        if tag != "img" and self._suppress_depth > 0:
            self._suppress_depth -= 1

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag != "img":
            # void 要素（br, hr 等）は子を持たないので深さを増やさない
            void_elements = frozenset(
                ["area", "base", "br", "col", "embed", "hr", "input", "link", "meta", "param", "source", "track", "wbr"]
            )
            if tag not in void_elements:
                self._suppress_depth += 1
            return
        attr_dict = dict(attrs)
        if attr_dict.get("class") != "emote":
            return
        src = attr_dict.get("src", "")
        if not src.startswith(_ALLOWED_SRC_PREFIX):
            return
        srcset = attr_dict.get("srcset", "")
        if srcset and not all(
            s.strip().split()[0].startswith(_ALLOWED_SRC_PREFIX) for s in srcset.split(",") if s.strip()
        ):
            return
        parts = ["<img"]
        for attr in _ALLOWED_IMG_ATTRS:
            if attr in attr_dict:
                parts.append(f' {attr}="{html.escape(attr_dict[attr], quote=True)}"')
        parts.append(' class="emote">')
        self._parts.append("".join(parts))

    def get_result(self) -> str:
        return "".join(self._parts)


def sanitize_body_html(value: str) -> str:
    """body_html を安全な要素のみに制限してサニタイズする。

    許可される要素: テキストノード、<img class="emote"> (jtvnw.net URL のみ)
    その他のタグはすべて除去する。
    """
    sanitizer = _BodyHtmlSanitizer()
    sanitizer.feed(value)
    return sanitizer.get_result()


def seconds_to_hms(total: int) -> str:
    """秒数を HH:MM:SS または MM:SS 形式に変換する。"""
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def seconds_to_twitch_t(total: int) -> str:
    """秒数を Twitch の時刻パラメータ形式（例: 1h2m3s）に変換する。"""
    # Twitch: ?t=1h2m3s
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    out = ""
    if h:
        out += f"{h}h"
    if m:
        out += f"{m}m"
    out += f"{s}s"
    return out


def utc_to_jst(dt: datetime) -> datetime:
    """UTC の datetime を JST に変換する。"""
    utc_tz = pytz.timezone("UTC")
    jst_tz = pytz.timezone("Asia/Tokyo")
    if dt.tzinfo is None:
        dt = utc_tz.localize(dt)
    return dt.astimezone(jst_tz)


def build_vod_link(url: str | None, offset_seconds: int) -> str | None:
    """VOD URL にオフセット秒のタイムスタンプパラメータを付与する。"""
    if not url:
        return None
    # 既に ? がある場合も想定（必要なら厳密化）
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={seconds_to_twitch_t(offset_seconds)}"


def build_youtube_link(url: str | None, offset_seconds: int) -> str | None:
    """YouTube URL にオフセット秒のタイムスタンプパラメータを付与する。"""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        params["t"] = f"{max(0, int(offset_seconds))}s"
        return urlunparse(parsed._replace(query=urlencode(params)))
    except Exception:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}t={max(0, int(offset_seconds))}s"


def split_filter_terms(raw: str | None):
    """カンマ・スペース・読点区切りのフィルタ文字列をリストに分割する。"""
    if not raw:
        return []
    return [term for term in re.split(r"[\s,、]+", raw.strip()) if term]


EMOTE_URL_TEMPLATE = "https://static-cdn.jtvnw.net/emoticons/v2/{emote_id}/default/dark/{scale}"
EMOTE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def normalize_emote_id(raw_emote_id) -> str | None:
    """エモート ID を正規化して返す。無効な場合は None。"""
    if raw_emote_id is None:
        return None
    raw_value = str(raw_emote_id)
    emote_id = raw_value.strip()
    if not emote_id:
        return None
    if raw_value != emote_id:
        return None
    if not EMOTE_ID_PATTERN.fullmatch(emote_id):
        return None
    return emote_id


def parse_raw_comment(raw_json):
    """raw_json フィールドを dict にパースして返す。"""
    if not raw_json:
        return None
    if isinstance(raw_json, dict):
        return raw_json
    try:
        return json.loads(raw_json)
    except Exception:
        return None


def _sanitize_emote_text(text) -> str:
    # Emote labels should stay plain text even if raw JSON is malformed or hostile.
    return html.escape(re.sub(r"<[^>]*>", "", text or ""))


def _normalize_utc_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return pytz.UTC.localize(value)
    return value.astimezone(pytz.UTC)


def render_comment_body_html(raw_json, fallback_body):
    """コメントの raw_json からエモート付き HTML を生成する。"""
    data = parse_raw_comment(raw_json)
    fragments = None
    if isinstance(data, dict):
        msg = data.get("message") or {}
        fragments = msg.get("fragments")

    if not fragments:
        return html.escape(fallback_body or "")

    parts = []
    for frag in fragments:
        if not isinstance(frag, dict):
            continue
        text = frag.get("text") or ""
        emoticon = frag.get("emoticon") or {}
        emote_id = normalize_emote_id(emoticon.get("emoticon_id"))
        if emote_id:
            escaped = _sanitize_emote_text(text)
            emote_id_url = quote(emote_id, safe="")
            url1 = html.escape(EMOTE_URL_TEMPLATE.format(emote_id=emote_id_url, scale="1.0"), quote=True)
            url2 = html.escape(EMOTE_URL_TEMPLATE.format(emote_id=emote_id_url, scale="2.0"), quote=True)
            url3 = html.escape(EMOTE_URL_TEMPLATE.format(emote_id=emote_id_url, scale="3.0"), quote=True)
            parts.append(
                f'<img class="emote" src="{url1}" srcset="{url2} 2x, {url3} 3x"'
                f' alt="{escaped}" title="{escaped}" loading="lazy" decoding="async">'
            )
        else:
            parts.append(html.escape(text))

    if not parts:
        return html.escape(fallback_body or "")

    return "".join(parts)


def _normalize_body_html_version(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_comment_body_html(row) -> str:
    """コメント行から body_html を取得または生成して返す。"""
    stored_body_html = row.get("body_html")
    if (
        stored_body_html is not None
        and _normalize_body_html_version(row.get("body_html_version")) == BODY_HTML_RENDER_VERSION
    ):
        return sanitize_body_html(stored_body_html)
    return sanitize_body_html(render_comment_body_html(row.get("raw_json"), row.get("body")))


def build_comment_body_select_sql(alias: str = "c") -> str:
    """コメント本文 HTML 取得用の SELECT カラム断片 SQL を返す。"""
    return f"""
                    {alias}.body,
                    {alias}.body_html,
                    {alias}.body_html_version,
                    CASE
                        WHEN {alias}.body_html IS NOT NULL
                         AND {alias}.body_html_version = :body_html_version
                        THEN NULL
                        ELSE {alias}.raw_json
                    END AS raw_json
    """.strip()


def decorate_comment(row, now):
    """コメント行に body_html・時刻表示・VOD リンク等の装飾フィールドを追加する。"""
    r = dict(row)
    r["body_html"] = get_comment_body_html(r)
    r.pop("raw_json", None)
    r.pop("body_html_version", None)
    offset_sec = int(r.get("offset_seconds") or 0)
    created_at = _normalize_utc_datetime(r.get("comment_created_at_utc"))
    now_utc = _normalize_utc_datetime(now) or pytz.UTC.localize(datetime.utcnow())
    comment_created_at_jst = None
    relative_time = None
    is_recent = False
    if created_at:
        jst_dt = utc_to_jst(created_at)
        comment_created_at_jst = jst_dt.strftime("%Y-%m-%d %H:%M:%S")
        delta = now_utc - created_at
        if delta.days == 0:
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            if hours > 0:
                relative_time = f"{hours}時間{minutes}分前"
            else:
                relative_time = f"{minutes}分前"
        else:
            relative_time = f"{delta.days}日前"
        is_recent = delta < timedelta(hours=24)

    r.update(
        {
            "offset_hms": seconds_to_hms(offset_sec),
            "vod_link": build_vod_link(r.get("vod_url"), offset_sec),
            "vod_jump_link": f"https://www.twitch.tv/videos/{r.get('vod_id')}?t={seconds_to_twitch_t(offset_sec)}",
            "youtube_jump_link": build_youtube_link(r.get("youtube_url"), offset_sec),
            "comment_created_at_jst": comment_created_at_jst,
            "relative_time": relative_time,
            "is_recent": is_recent,
        }
    )
    return r


# Backward-compatible aliases for routers that still import the old helpers.
_get_comment_body_html = get_comment_body_html
_build_comment_body_select_sql = build_comment_body_select_sql
_decorate_comment = decorate_comment
