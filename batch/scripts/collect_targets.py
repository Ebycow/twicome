"""収集対象ユーザー（コメント投稿者）の判定ヘルパー。

QUICK_LINK_LOGINS と DEFAULT_LOGIN に書かれたログイン名を「収集対象ユーザー」とみなし、
それ以外のユーザーのコメントは保存・DB 投入しない。
"""

import gzip
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def load_target_logins(env: dict[str, str] | None = None) -> frozenset[str]:
    """環境変数から収集対象ログイン名の集合（小文字）を返す。空なら RuntimeError。

    対象が空のまま走ると全コメント・全ファイルを破棄してしまうため、明示的に失敗させる。
    """
    source = os.environ if env is None else env
    raw = ",".join([source.get("QUICK_LINK_LOGINS", ""), source.get("DEFAULT_LOGIN", "")])
    logins = frozenset(token.strip().lower() for token in raw.split(",") if token.strip())
    if not logins:
        raise RuntimeError("収集対象ユーザーが未設定です。QUICK_LINK_LOGINS か DEFAULT_LOGIN を設定してください。")
    return logins


def commenter_login(comment: dict[str, Any]) -> str:
    """TwitchDownloader のコメント dict から投稿者ログイン名（小文字）を返す。"""
    commenter = comment.get("commenter") or {}
    return str(commenter.get("name") or "").strip().lower()


def iter_target_comments(comments: Iterable[dict[str, Any]], targets: frozenset[str]):
    """収集対象ユーザーのコメントだけを返す。"""
    for comment in comments:
        if commenter_login(comment) in targets:
            yield comment


def has_target_comment(data: dict[str, Any], targets: frozenset[str]) -> bool:
    """チャット JSON に収集対象ユーザーのコメントが 1 件でも含まれるか。"""
    return any(True for _ in iter_target_comments(data.get("comments") or [], targets))


def load_chat_json(path: str | Path) -> dict[str, Any]:
    """.json / .json.gz のチャットファイルを読み込む。"""
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    with path.open(encoding="utf-8") as f:
        return json.load(f)
