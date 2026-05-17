import importlib.util
import json
import sys
from pathlib import Path


def _load_generate_module(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("MYSQL_PASSWORD", "testpass")
    monkeypatch.setenv("OPENROUTER_API_KEY", "testkey")
    monkeypatch.setenv(
        "COMMUNITY_NOTE_SYSTEM_PROMPT_PATH",
        str(root / "batch" / "prompts" / "community_note_system_prompt.txt.example"),
    )
    spec = importlib.util.spec_from_file_location(
        "twicome_generate_community_notes_unit",
        root / "batch" / "scripts" / "generate_community_notes.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_extract_json_object_accepts_fenced_json_with_trailing_text(monkeypatch):
    generate_notes = _load_generate_module(monkeypatch)

    result = generate_notes.extract_json_object('```json\n{"eligible": false, "status": "not_applicable"}\n```\nextra')

    assert result == {"eligible": False, "status": "not_applicable"}


def test_normalize_note_data_maps_invalid_status_to_enum(monkeypatch):
    generate_notes = _load_generate_module(monkeypatch)
    long_note = "あ" * (generate_notes.NOTE_MAX_LENGTH + 10)
    long_ask = "い" * (generate_notes.ASK_MAX_LENGTH + 10)

    result = generate_notes.normalize_note_data(
        {
            "eligible": "true",
            "status": "unsupported",
            "note": long_note,
            "scores": {"harm_risk": 500, "subjectivity": "80"},
            "issues": ["根拠不足", "長すぎる説明", "曖昧", "余分"],
            "ask": long_ask,
        }
    )

    assert result["eligible"] is True
    assert result["status"] == "insufficient"
    assert result["note"] == "あ" * generate_notes.NOTE_MAX_LENGTH
    assert result["scores"]["harm_risk"] == 100
    assert result["scores"]["subjectivity"] == 80
    assert result["issues"] == ["根拠不足", "長すぎる説明", "曖昧"]
    assert result["ask"] == "い" * generate_notes.ASK_MAX_LENGTH


def test_normalize_note_data_forces_not_applicable_when_ineligible(monkeypatch):
    generate_notes = _load_generate_module(monkeypatch)

    result = generate_notes.normalize_note_data(
        {
            "eligible": False,
            "status": "insufficient",
            "note": "",
            "scores": {},
            "issues": "not-list",
            "ask": None,
        }
    )

    assert result["status"] == "not_applicable"
    assert result["note"] == "事実確認の対象となる具体的な主張ではありません。"
    assert result["issues"] == []
    assert result["ask"] == ""


def test_save_community_note_normalizes_status_before_insert(monkeypatch):
    generate_notes = _load_generate_module(monkeypatch)

    class FakeCursor:
        params = None

        def execute(self, _sql, params):
            self.params = params

    cur = FakeCursor()
    generate_notes.save_community_note(
        cur,
        "comment-1",
        {
            "eligible": True,
            "status": "unsupported",
            "note": "根拠が不足しています。",
            "scores": {},
            "issues": "not-list",
            "ask": "出典はありますか。",
        },
    )

    assert cur.params[2] == "insufficient"
    assert json.loads(cur.params[11])["status"] == "insufficient"


def test_generate_note_retries_with_more_tokens_after_length(monkeypatch):
    generate_notes = _load_generate_module(monkeypatch)
    monkeypatch.setattr(generate_notes.time, "sleep", lambda _seconds: None)
    payloads = []

    class FakeResponse:
        def __init__(self, content, finish_reason):
            self._content = content
            self._finish_reason = finish_reason

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "generation-1",
                "model": "test/model",
                "choices": [
                    {
                        "message": {"content": self._content},
                        "finish_reason": self._finish_reason,
                    }
                ],
                "usage": {"total_tokens": 1},
            }

    responses = [
        FakeResponse("```json", "length"),
        FakeResponse(
            json.dumps(
                {
                    "eligible": True,
                    "status": "unsupported",
                    "note": "出典が示されていません。",
                    "scores": {"evidence_gap": 90},
                    "issues": ["出典不明"],
                    "ask": "出典はありますか。",
                },
                ensure_ascii=False,
            ),
            "stop",
        ),
    ]

    def fake_post(_url, headers, json, timeout):
        assert headers["Authorization"] == "Bearer testkey"
        assert timeout == 60
        payloads.append(json)
        return responses.pop(0)

    monkeypatch.setattr(generate_notes.requests, "post", fake_post)

    result = generate_notes.generate_note("スロースリップは4月20日の地震解析で出た情報")

    assert payloads[0]["max_tokens"] == generate_notes.MAX_TOKENS
    assert payloads[1]["max_tokens"] > payloads[0]["max_tokens"]
    assert result["status"] == "insufficient"
    assert result[generate_notes.OPENROUTER_META_KEY]["actual_model"] == "test/model"
