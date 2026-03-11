import pytest
import requests

import faiss_search


class _DummyResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"results": []}

    def raise_for_status(self):
        if self.status_code >= 400 and self.status_code != 404:
            raise requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return self._payload


@pytest.mark.parametrize(
    "func,args",
    [
        (faiss_search.similar_search, ("viewer", "query", 10)),
        (faiss_search.centroid_search, ("viewer", 0.5, 10)),
        (faiss_search.emotion_search, ("viewer", {"joy": 1.0}, 10)),
    ],
)
def test_search_functions_raise_runtime_error_when_backend_unreachable(monkeypatch, func, args):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")

    def _raise(*_args, **_kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(faiss_search.requests, "post", _raise)

    with pytest.raises(RuntimeError):
        func(*args)


def test_similar_search_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")
    monkeypatch.setattr(faiss_search.requests, "post", lambda *_a, **_k: _DummyResponse(status_code=404))

    assert faiss_search.similar_search("viewer", "q", 5) is None
