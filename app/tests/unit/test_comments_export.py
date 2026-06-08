"""CSV エクスポートの数式インジェクション対策テスト。"""

import csv
import io

import pytest
from routers.comments import _comments_to_csv, _csv_safe


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("=cmd|'/c calc'!A1", "'=cmd|'/c calc'!A1"),
        ("+1+2", "'+1+2"),
        ("-1+2", "'-1+2"),
        ("@SUM(A1:A9)", "'@SUM(A1:A9)"),
        ("\tTAB", "'\tTAB"),
        ("\rCR", "'\rCR"),
    ],
)
def test_csv_safe_neutralizes_formula_prefixes(raw, expected):
    assert _csv_safe(raw) == expected


@pytest.mark.parametrize("raw", ["普通のコメント", "https://example.com", "1+1", "", "a=b"])
def test_csv_safe_keeps_normal_values_unchanged(raw):
    assert _csv_safe(raw) == raw


def test_csv_safe_handles_none_and_non_str():
    assert _csv_safe(None) == ""
    assert _csv_safe(123) == "123"


def test_comments_to_csv_neutralizes_malicious_body():
    comments = [
        {
            "comment_created_at_jst": "2026-06-08 00:10:00",
            "owner_login": "foo",
            "vod_title": "title",
            "offset_hms": "00:10",
            "body_html": '=cmd|"/c calc"!A1',
            "bits_spent": None,
        }
    ]
    out = _comments_to_csv(comments)

    # ヘッダ + データ1行を表計算ソフトと同じ解釈でパースし、本文セルが数式化されないことを検証
    rows = list(csv.reader(io.StringIO(out)))
    body_cell = rows[1][4]
    assert body_cell.startswith("'=")
    assert not body_cell.startswith("=")
