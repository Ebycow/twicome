"""収集対象ユーザー絞り込み（batch/scripts）のユニットテスト。"""

import gzip
import importlib
import json
import sys
from pathlib import Path

import pytest

BATCH_SCRIPTS = Path(__file__).resolve().parents[3] / "batch" / "scripts"


@pytest.fixture(autouse=True)
def _batch_path(monkeypatch):
    monkeypatch.syspath_prepend(str(BATCH_SCRIPTS))
    monkeypatch.setenv("QUICK_LINK_LOGINS", "Alice, bob")
    monkeypatch.setenv("DEFAULT_LOGIN", "carol")
    monkeypatch.setenv("MYSQL_PASSWORD", "dummy")
    monkeypatch.setenv("ENV_FILE", "/nonexistent/.env")


def _import(name):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def _comment(login, cid="c1", vod_id=100, body="hi"):
    return {
        "_id": cid,
        "content_id": str(vod_id),
        "content_offset_seconds": 5,
        "created_at": "2026-01-01T00:00:00Z",
        "commenter": {"_id": "1", "name": login, "display_name": login.upper()},
        "message": {"body": body},
    }


def _chat(comments, vod_id=100):
    return {
        "streamer": {"id": 999, "name": "Streamer", "login": "streamer"},
        "video": {"id": str(vod_id), "title": "t", "created_at": "2026-01-01T00:00:00Z"},
        "comments": comments,
    }


# ── collect_targets ──────────────────────────────────────────────────────────


def test_load_target_logins_merges_and_lowercases():
    ct = _import("collect_targets")
    assert ct.load_target_logins() == frozenset({"alice", "bob", "carol"})


def test_load_target_logins_raises_when_empty():
    ct = _import("collect_targets")
    with pytest.raises(RuntimeError):
        ct.load_target_logins({"QUICK_LINK_LOGINS": " , ", "DEFAULT_LOGIN": ""})


def test_has_target_comment_is_case_insensitive():
    ct = _import("collect_targets")
    targets = frozenset({"alice"})
    assert ct.has_target_comment(_chat([_comment("someone"), _comment("ALICE")]), targets)
    assert not ct.has_target_comment(_chat([_comment("someone")]), targets)
    assert not ct.has_target_comment({"comments": None}, targets)


def test_load_chat_json_reads_plain_and_gzip(tmp_path):
    ct = _import("collect_targets")
    data = _chat([_comment("alice")])
    plain = tmp_path / "1.json"
    plain.write_text(json.dumps(data), encoding="utf-8")
    gz = tmp_path / "2.json.gz"
    with gzip.open(gz, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    assert ct.load_chat_json(plain) == data
    assert ct.load_chat_json(gz) == data


# ── insertdb ────────────────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=()):
        self.log.append((" ".join(sql.split()), params))


class _FakeConn:
    def __init__(self):
        self.log = []

    def cursor(self):
        return _FakeCursor(self.log)

    def commit(self):
        pass


def test_list_comment_json_files_prefers_gzip(tmp_path):
    ins = _import("insertdb")
    for name in ["1.json", "1.json.gz", "2.json", "3.json.gz", "no_target_vods.tsv", "x.json"]:
        (tmp_path / name).write_text("{}")
    names = [name for _full, name, _vod in ins.list_comment_json_files(str(tmp_path))]
    assert names == ["1.json.gz", "2.json", "3.json.gz"]


def test_ingest_one_file_inserts_only_target_comments(tmp_path):
    ins = _import("insertdb")
    path = tmp_path / "100.json.gz"
    data = _chat(
        [
            _comment("alice", cid="a1"),
            _comment("zed", cid="z1"),
            _comment("ALICE", cid="a2"),
            _comment("alice", cid="other-vod", vod_id=555),
        ],
        100,
    )
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    conn = _FakeConn()

    result = ins.ingest_one_file(conn, str(path), path.name, 100, frozenset({"alice"}))

    assert result == (100, 2)
    comment_ids = [p[0] for sql, p in conn.log if sql.startswith("INSERT INTO comments")]
    assert comment_ids == ["a1", "a2"]
    user_logins = [p[1] for sql, p in conn.log if sql.startswith("INSERT INTO users")]
    assert set(user_logins) == {"streamer", "alice", "ALICE"}
    assert "zed" not in user_logins


def test_ingest_one_file_returns_none_without_target(tmp_path):
    ins = _import("insertdb")
    path = tmp_path / "100.json"
    path.write_text(json.dumps(_chat([_comment("zed")], 100)), encoding="utf-8")
    conn = _FakeConn()

    assert ins.ingest_one_file(conn, str(path), path.name, 100, frozenset({"alice"})) is None
    assert conn.log == []  # 配信者・VOD も書かない


def test_write_vods_csv_selects_columns(tmp_path):
    vl = _import("get_vod_list_batch")
    out = tmp_path / "sub" / "vods.csv"
    vl.write_vods_csv(
        out,
        [
            {
                "user_id": "1",
                "id": "9",
                "title": "t,1",
                "created_at": "c",
                "url": "u",
                "view_count": 3,
                "duration": "1h",
                "extra": "drop",
            }
        ],
    )
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "user_id,id,title,created_at,url,view_count,duration"
    assert lines[1] == '1,9,"t,1",c,u,3,1h'

    vl.write_vods_csv(out, [])
    assert out.read_text(encoding="utf-8").splitlines() == [lines[0]]


def test_ingest_directory_reingests_when_targets_grow(tmp_path, monkeypatch):
    ins = _import("insertdb")
    (tmp_path / "100.json.gz").write_bytes(b"dummy")

    class _Conn(_FakeConn):
        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(ins.mysql.connector, "connect", lambda **_k: _Conn())
    sha = ins.compute_sha256(str(tmp_path / "100.json.gz"))
    monkeypatch.setattr(ins, "get_vod_ingest_marker", lambda _cur, _vod: (sha, 1))
    monkeypatch.setattr(ins, "upsert_vod_ingest_marker", lambda **_k: None)
    ingested = []
    monkeypatch.setattr(
        ins, "ingest_one_file", lambda _c, _p, name, _v, targets: ingested.append((name, targets)) or (100, 1)
    )

    # 初回: 記録が無い = 対象が増えた扱いで、マーカー一致でも取り込む
    ins.ingest_directory(str(tmp_path))
    assert len(ingested) == 1
    assert ins.read_ingested_targets(str(tmp_path)) == frozenset({"alice", "bob", "carol"})

    # 対象が変わらなければマーカー一致でスキップ
    ins.ingest_directory(str(tmp_path))
    assert len(ingested) == 1

    # 対象ユーザーが増えたら再取り込み
    monkeypatch.setenv("DEFAULT_LOGIN", "dave")
    ins.ingest_directory(str(tmp_path))
    assert len(ingested) == 2
    assert "dave" in ingested[-1][1]
