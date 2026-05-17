"""コミュニティノート生成バッチ

twicome_dislikes_count が閾値以上かつ community_notes が未生成のコメントに対して、
OpenRouter API を使用してコミュニティノートを生成し、community_notes テーブルに保存する。
"""

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))

# .env から設定を読み込み
ENV_PATH = Path(os.getenv("ENV_FILE", str(PROJECT_ROOT / ".env")))
if not ENV_PATH.is_absolute():
    ENV_PATH = PROJECT_ROOT / ENV_PATH
load_dotenv(str(ENV_PATH))

# -----------------------
# 設定
# -----------------------
MYSQL_HOST = os.getenv("MYSQL_HOST", "db")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "appuser")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
if not MYSQL_PASSWORD:
    raise RuntimeError("MYSQL_PASSWORD is not set. Set MYSQL_PASSWORD in .env or environment variables.")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "appdb")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
COMMUNITY_NOTE_MODEL = os.getenv("COMMUNITY_NOTE_MODEL", "openai/gpt-oss-120b")
DISLIKE_THRESHOLD = int(os.getenv("COMMUNITY_NOTE_DISLIKE_THRESHOLD", "1"))
SYSTEM_PROMPT_PATH = Path(
    os.getenv(
        "COMMUNITY_NOTE_SYSTEM_PROMPT_PATH",
        str(PROJECT_ROOT / "batch" / "prompts" / "community_note_system_prompt.txt"),
    )
)
if not SYSTEM_PROMPT_PATH.is_absolute():
    SYSTEM_PROMPT_PATH = PROJECT_ROOT / SYSTEM_PROMPT_PATH

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_META_KEY = "_openrouter"

PROMPT_VERSION = "v4"
try:
    SYSTEM_PROMPT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
except FileNotFoundError as e:
    raise RuntimeError(
        f"SYSTEM_PROMPT file is not found: {SYSTEM_PROMPT_PATH}. Set COMMUNITY_NOTE_SYSTEM_PROMPT_PATH in .env."
    ) from e

if not SYSTEM_PROMPT:
    raise RuntimeError(f"SYSTEM_PROMPT file is empty: {SYSTEM_PROMPT_PATH}. Set a non-empty prompt text.")

REQUEST_INTERVAL_SEC = 1
MAX_RETRIES = 2
BACKUP_DIR = os.getenv("COMMUNITY_NOTE_BACKUP_DIR", str(PROJECT_ROOT / "data" / "default" / "oldcommunitylog"))
MODEL_COLUMN_MAX_LENGTH = 64
MAX_TOKENS = int(os.getenv("COMMUNITY_NOTE_MAX_TOKENS", "2048"))
MAX_TOKENS_CAP = int(os.getenv("COMMUNITY_NOTE_MAX_TOKENS_CAP", "4096"))
NOTE_MAX_LENGTH = int(os.getenv("COMMUNITY_NOTE_MAX_NOTE_CHARS", "140"))
ASK_MAX_LENGTH = int(os.getenv("COMMUNITY_NOTE_MAX_ASK_CHARS", "80"))
ALLOWED_STATUSES = {"supported", "insufficient", "inconsistent", "not_applicable"}
STATUS_ALIASES = {
    "not applicable": "not_applicable",
    "not-applicable": "not_applicable",
    "notapplicable": "not_applicable",
    "none": "not_applicable",
    "irrelevant": "not_applicable",
    "unsupported": "insufficient",
    "unknown": "insufficient",
    "uncertain": "insufficient",
    "lack_of_evidence": "insufficient",
    "contradictory": "inconsistent",
    "contradiction": "inconsistent",
}
OUTPUT_CONSTRAINTS = """
追加制約:
- 必ず1行のJSONオブジェクトのみを返す。Markdownコードフェンス、前置き、末尾説明は禁止。
- "note" は140字以内、"issues" は最大3件、"ask" は80字以内。
- "status" は supported / insufficient / inconsistent / not_applicable のいずれかだけ。
- 雑談、感想、体調報告、予定、質問、相づち、配信音量などの主観的な観測だけなら eligible=false, status="not_applicable"。
""".strip()


def normalize_model_id(model_id) -> str:
    """OpenRouter API response の model 値を保存・表示可能な文字列にする。"""
    if isinstance(model_id, str) and model_id:
        return model_id
    return COMMUNITY_NOTE_MODEL


def get_openrouter_meta(note_data: dict) -> dict:
    """生成結果に埋め込んだ OpenRouter メタ情報を取り出す。"""
    openrouter_meta = note_data.get(OPENROUTER_META_KEY, {})
    if isinstance(openrouter_meta, dict):
        return openrouter_meta
    return {}


def max_tokens_for_attempt(attempt: int) -> int:
    """途中切れ時の再試行では出力トークン上限を広げる。"""
    return min(MAX_TOKENS_CAP, MAX_TOKENS * attempt)


def coerce_bool(value) -> bool | None:
    """LLMが文字列で返した boolean を吸収する。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def normalize_status(status, eligible: bool) -> str:
    """DB enum に入る status へ正規化する。"""
    if isinstance(status, str):
        cleaned = status.strip().lower().replace("-", "_")
        if cleaned in ALLOWED_STATUSES:
            return cleaned
        alias = STATUS_ALIASES.get(status.strip().lower()) or STATUS_ALIASES.get(cleaned)
        if alias:
            return alias
    return "insufficient" if eligible else "not_applicable"


def extract_json_object(content: str) -> dict:
    """余計な前後テキストやコードフェンスを含む応答から先頭のJSON objectを取り出す。"""
    cleaned = content.strip()
    brace = cleaned.find("{")
    if brace < 0:
        raise json.JSONDecodeError("JSON object not found", cleaned, 0)

    decoder = json.JSONDecoder()
    result, _ = decoder.raw_decode(cleaned[brace:])
    if not isinstance(result, dict):
        raise json.JSONDecodeError("JSON root is not an object", cleaned, brace)
    return result


def normalize_note_data(note_data: dict) -> dict | None:
    """LLM応答を保存可能なコミュニティノート形式へ整える。"""
    eligible = coerce_bool(note_data.get("eligible"))
    if eligible is None:
        return None

    scores = note_data.get("scores", {})
    if not isinstance(scores, dict):
        scores = {}
    normalized_scores = {
        "verifiability": clamp_score(scores.get("verifiability", 0)),
        "harm_risk": clamp_score(scores.get("harm_risk", 0)),
        "exaggeration": clamp_score(scores.get("exaggeration", 0)),
        "evidence_gap": clamp_score(scores.get("evidence_gap", 0)),
        "subjectivity": clamp_score(scores.get("subjectivity", 0)),
    }

    issues = note_data.get("issues", [])
    if not isinstance(issues, list):
        issues = []
    issues = [str(issue).strip() for issue in issues if str(issue).strip()][:3]

    note = note_data.get("note", "")
    if not isinstance(note, str):
        note = str(note) if note is not None else ""
    note = note.strip()
    if not note:
        note = "事実確認の対象となる具体的な主張ではありません。" if not eligible else "根拠や具体性が不足しています。"
    note = note[:NOTE_MAX_LENGTH]

    ask = note_data.get("ask", "")
    if not isinstance(ask, str):
        ask = str(ask) if ask is not None else ""
    ask = ask.strip()[:ASK_MAX_LENGTH]

    normalized = dict(note_data)
    normalized["eligible"] = eligible
    normalized["status"] = normalize_status(note_data.get("status"), eligible)
    if not eligible:
        normalized["status"] = "not_applicable"
    normalized["note"] = note
    normalized["scores"] = normalized_scores
    normalized["issues"] = issues
    normalized["ask"] = ask
    return normalized


def get_db_connection():
    """MySQL データベース接続を返す。"""
    import mysql.connector

    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
    )


def fetch_target_comments(cur, force: bool = False):
    """閾値以上の dislike があるコメントを取得。force=True なら生成済みも含む。"""
    if force:
        cur.execute(
            """
            SELECT c.comment_id, c.body, cn.note_json
            FROM comments c
            LEFT JOIN community_notes cn ON cn.comment_id = c.comment_id
            WHERE c.twicome_dislikes_count >= %s
            ORDER BY c.twicome_dislikes_count DESC
            """,
            (DISLIKE_THRESHOLD,),
        )
    else:
        cur.execute(
            """
            SELECT c.comment_id, c.body, NULL
            FROM comments c
            LEFT JOIN community_notes cn ON cn.comment_id = c.comment_id
            WHERE c.twicome_dislikes_count >= %s
              AND cn.note_id IS NULL
            ORDER BY c.twicome_dislikes_count DESC
            """,
            (DISLIKE_THRESHOLD,),
        )
    return cur.fetchall()


def backup_old_notes(notes: list[tuple[str, str]]):
    """旧コミュニティノートをJSONファイルにバックアップ"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.json")
    data = [{"comment_id": cid, "old_note_json": body} for cid, body in notes]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"バックアップ保存: {path} ({len(data)} 件)")


def generate_note(body: str) -> dict | None:
    """OpenRouter API でコミュニティノートを生成。JSON形式で返す。"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    user_content = json.dumps({"statement": body}, ensure_ascii=False)
    base_payload = {
        "model": COMMUNITY_NOTE_MODEL,
        "messages": [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{OUTPUT_CONSTRAINTS}"},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        payload = {**base_payload, "max_tokens": max_tokens_for_attempt(attempt)}
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        actual_model = normalize_model_id(data.get("model"))

        choice = data["choices"][0]
        content = (choice["message"]["content"] or "").strip()
        finish_reason = choice.get("finish_reason", "")

        if not content:
            print(f"      (試行 {attempt}/{MAX_RETRIES}: 空レスポンス, finish_reason={finish_reason})")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_INTERVAL_SEC)
                continue
            return None

        if finish_reason == "length":
            print(f"      (試行 {attempt}/{MAX_RETRIES}: max_tokens で途中切れ, {len(content)} chars)")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_INTERVAL_SEC)
                continue

        try:
            result = extract_json_object(content)
        except json.JSONDecodeError as e:
            print(f"      (試行 {attempt}/{MAX_RETRIES}: JSONパース失敗: {e})")
            print(f"      --- raw content ---\n{content}\n      --- end ---")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_INTERVAL_SEC)
                continue
            return None

        normalized = normalize_note_data(result)
        if normalized is None:
            print(f"      (試行 {attempt}/{MAX_RETRIES}: eligible フィールドが不正)")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_INTERVAL_SEC)
                continue
            return None

        normalized[OPENROUTER_META_KEY] = {
            "requested_model": COMMUNITY_NOTE_MODEL,
            "actual_model": actual_model,
            "generation_id": data.get("id"),
            "finish_reason": finish_reason,
            "native_finish_reason": choice.get("native_finish_reason"),
            "usage": data.get("usage"),
        }
        return normalized


def clamp_score(val, min_val=0, max_val=100) -> int:
    """スコアを0-100の整数に丸める"""
    try:
        return max(min_val, min(max_val, int(val)))
    except (TypeError, ValueError):
        return 0


def save_community_note(cur, comment_id: str, note_data: dict):
    """コミュニティノートを community_notes テーブルに保存（REPLACE INTO で冪等）"""
    normalized = normalize_note_data(note_data)
    if normalized is None:
        raise ValueError("eligible フィールドが不正です")
    note_data = normalized
    scores = note_data.get("scores", {})
    issues = note_data.get("issues", [])
    if not isinstance(issues, list):
        issues = []
    openrouter_meta = get_openrouter_meta(note_data)
    actual_model = normalize_model_id(openrouter_meta.get("actual_model"))

    cur.execute(
        """
        REPLACE INTO community_notes
            (comment_id, eligible, status, note,
             verifiability, harm_risk, exaggeration, evidence_gap, subjectivity,
             issues, ask, note_json, model, prompt_version)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            comment_id,
            1 if note_data.get("eligible", False) else 0,
            note_data.get("status", "not_applicable"),
            note_data.get("note", ""),
            clamp_score(scores.get("verifiability", 0)),
            clamp_score(scores.get("harm_risk", 0)),
            clamp_score(scores.get("exaggeration", 0)),
            clamp_score(scores.get("evidence_gap", 0)),
            clamp_score(scores.get("subjectivity", 0)),
            json.dumps(issues[:3], ensure_ascii=False),
            note_data.get("ask", "")[:255],
            json.dumps(note_data, ensure_ascii=False),
            actual_model[:MODEL_COLUMN_MAX_LENGTH],
            PROMPT_VERSION,
        ),
    )


def main():
    """コミュニティノート生成バッチのエントリーポイント。"""
    parser = argparse.ArgumentParser(description="コミュニティノート生成バッチ")
    parser.add_argument("-f", "--force", action="store_true", help="生成済みのコミュニティノートも含めて全件再生成する")
    args = parser.parse_args()

    if not OPENROUTER_API_KEY:
        print("Error: OPENROUTER_API_KEY is not set in .env")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        targets = fetch_target_comments(cur, force=args.force)
        mode = "強制再生成" if args.force else "未生成のみ"
        print(f"対象コメント: {len(targets)} 件 (dislike >= {DISLIKE_THRESHOLD}, {mode})")

        if not targets:
            print("生成対象なし")
            return

        # -f 時は既存ノートをバックアップ
        if args.force:
            old_notes = [(cid, note_json) for cid, _, note_json in targets if note_json]
            if old_notes:
                backup_old_notes(old_notes)

        success = 0
        fail = 0

        for comment_id, body, _ in targets:
            try:
                print(f"  生成中: {comment_id} ({body[:40]}...)")
                note_data = generate_note(body)
                if note_data:
                    save_community_note(cur, comment_id, note_data)
                    conn.commit()
                    note_text = note_data.get("note", "")
                    scores = note_data.get("scores", {})
                    danger = (
                        scores.get("harm_risk", 0)
                        + scores.get("exaggeration", 0)
                        + scores.get("evidence_gap", 0)
                        + scores.get("subjectivity", 0)
                    ) / 4
                    print(f"    -> {note_text[:60]}...")
                    subj = scores.get("subjectivity", 0)
                    openrouter_meta = get_openrouter_meta(note_data)
                    actual_model = normalize_model_id(openrouter_meta.get("actual_model"))
                    print(
                        f"       eligible={note_data.get('eligible')},"
                        f" status={note_data.get('status')},"
                        f" danger={danger:.0f}, subjectivity={subj}"
                    )
                    print(f"       model={actual_model} (requested={COMMUNITY_NOTE_MODEL})")
                    success += 1
                else:
                    print("    -> 空のレスポンスまたはパース失敗、スキップ")
                    fail += 1
            except Exception as e:
                print(f"    -> エラー: {e}")
                conn.rollback()
                fail += 1

            time.sleep(REQUEST_INTERVAL_SEC)

        print(f"\n完了: 成功 {success} 件, 失敗 {fail} 件")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
