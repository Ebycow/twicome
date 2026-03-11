import pytest

from services.vote_input import MAX_VOTE_BULK_IDS, normalize_comment_ids


def test_normalize_comment_ids_deduplicates_and_trims():
    ids = normalize_comment_ids([" a ", "a", "", "b"])
    assert ids == ["a", "b"]


def test_normalize_comment_ids_raises_when_too_many_ids():
    with pytest.raises(ValueError):
        normalize_comment_ids([f"c{i}" for i in range(MAX_VOTE_BULK_IDS + 1)])
