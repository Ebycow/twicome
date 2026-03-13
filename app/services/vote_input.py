"""投票入力バリデーション"""

MAX_VOTE_BULK_IDS = 200


def normalize_comment_ids(comment_ids: list[str]) -> list[str]:
    """コメント ID リストを正規化・重複排除して返す。件数超過時は ValueError。"""
    normalized_ids: list[str] = []
    seen = set()
    for comment_id in comment_ids:
        value = str(comment_id or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized_ids.append(value)

    if len(normalized_ids) > MAX_VOTE_BULK_IDS:
        raise ValueError("too_many_comment_ids")

    return normalized_ids
