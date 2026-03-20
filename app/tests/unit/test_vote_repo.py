from repositories import vote_repo


class _DummyResult:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _DummyDB:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount
        self.executed = []
        self.committed = False

    def execute(self, stmt, params):
        self.executed.append((str(stmt), params))
        return _DummyResult(self.rowcount)

    def commit(self):
        self.committed = True


def test_increment_like_returns_true_when_comment_exists():
    db = _DummyDB(rowcount=1)

    updated = vote_repo.increment_like(db, "c1", 2)

    assert updated is True
    assert db.committed is False


def test_increment_like_returns_false_when_comment_missing():
    db = _DummyDB(rowcount=0)

    updated = vote_repo.increment_like(db, "missing", 1)

    assert updated is False
    assert db.committed is False


def test_increment_dislike_returns_false_when_comment_missing():
    db = _DummyDB(rowcount=0)

    updated = vote_repo.increment_dislike(db, "missing", 1)

    assert updated is False
    assert db.committed is False
