"""コメント本文 HTML レンダリングユーティリティ（バッチ用）。"""

import html
import json
import re
from urllib.parse import quote

BODY_HTML_RENDER_VERSION = 1

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
    return html.escape(re.sub(r"<[^>]*>", "", text or ""))


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
                f'<img class="emote" src="{url1}" srcset="{url2} 2x, {url3} 3x" alt="{escaped}" title="{escaped}" loading="lazy" decoding="async">'
            )
        else:
            parts.append(html.escape(text))

    if not parts:
        return html.escape(fallback_body or "")

    return "".join(parts)
