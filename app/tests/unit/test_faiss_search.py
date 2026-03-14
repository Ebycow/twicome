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


def test_is_enabled_reflects_faiss_api_url(monkeypatch):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "")
    assert faiss_search._is_enabled() is False

    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")
    assert faiss_search._is_enabled() is True


def test_ping_faiss_api_returns_false_when_disabled(monkeypatch):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "")

    assert faiss_search.ping_faiss_api() is False


def test_ping_faiss_api_returns_true_on_success(monkeypatch):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")
    monkeypatch.setattr(faiss_search.requests, "get", lambda *_a, **_k: _DummyResponse(status_code=200))

    assert faiss_search.ping_faiss_api() is True


def test_ping_faiss_api_raises_runtime_error_on_failure(monkeypatch):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")

    def _raise(*_args, **_kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(faiss_search.requests, "get", _raise)

    with pytest.raises(RuntimeError, match="faiss-api"):
        faiss_search.ping_faiss_api()


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (200, True),
        (503, False),
    ],
)
def test_is_index_available_returns_status_based_bool(monkeypatch, status_code, expected):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")
    monkeypatch.setattr(faiss_search.requests, "get", lambda *_a, **_k: _DummyResponse(status_code=status_code))

    assert faiss_search.is_index_available("viewer") is expected


def test_is_index_available_returns_false_when_disabled_or_error(monkeypatch):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "")
    assert faiss_search.is_index_available("viewer") is False

    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(faiss_search.requests, "get", _raise)

    assert faiss_search.is_index_available("viewer") is False


def test_get_emotion_axes_returns_axes_or_empty_list(monkeypatch):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "")
    assert faiss_search.get_emotion_axes() == []

    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")
    monkeypatch.setattr(
        faiss_search.requests,
        "get",
        lambda *_a, **_k: _DummyResponse(payload={"axes": [{"name": "joy"}]}),
    )
    assert faiss_search.get_emotion_axes() == [{"name": "joy"}]

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(faiss_search.requests, "get", _raise)
    assert faiss_search.get_emotion_axes() == []


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


@pytest.mark.parametrize(
    ("func", "args"),
    [
        (faiss_search.centroid_search, ("viewer", 0.5, 10)),
        (faiss_search.emotion_search, ("viewer", {"joy": 1.0}, 10)),
    ],
)
def test_search_functions_return_none_on_404(monkeypatch, func, args):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")
    monkeypatch.setattr(faiss_search.requests, "post", lambda *_a, **_k: _DummyResponse(status_code=404))

    assert func(*args) is None


@pytest.mark.parametrize(
    ("func", "args"),
    [
        (faiss_search.similar_search, ("viewer", "query", 10)),
        (faiss_search.centroid_search, ("viewer", 0.5, 10)),
        (faiss_search.emotion_search, ("viewer", {"joy": 1.0}, 10)),
    ],
)
def test_search_functions_return_none_when_disabled(monkeypatch, func, args):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "")

    assert func(*args) is None


@pytest.mark.parametrize(
    ("func", "args"),
    [
        (faiss_search.similar_search, ("viewer", "query", 10)),
        (faiss_search.centroid_search, ("viewer", 0.5, 10)),
        (faiss_search.emotion_search, ("viewer", {"joy": 1.0}, 10)),
    ],
)
def test_search_functions_transform_results(monkeypatch, func, args):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")
    monkeypatch.setattr(
        faiss_search.requests,
        "post",
        lambda *_a, **_k: _DummyResponse(payload={"results": [{"comment_id": "c1", "score": 0.75}]}),
    )

    assert func(*args) == [("c1", 0.75)]


@pytest.mark.parametrize(
    ("func", "args", "payload_key"),
    [
        (faiss_search.get_clusters, ("viewer", 8), "clusters"),
        (faiss_search.get_cluster_members, ("viewer", [0.1, 0.2], 5), "comment_ids"),
        (faiss_search.get_subclusters, ("viewer", [0.1, 0.2], 10, 4), "subclusters"),
    ],
)
def test_cluster_related_functions_return_none_when_disabled(monkeypatch, func, args, payload_key):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "")

    assert func(*args) is None


@pytest.mark.parametrize(
    ("func", "args", "method_name", "payload", "expected"),
    [
        (
            faiss_search.get_clusters,
            ("viewer", 8),
            "get",
            {"clusters": [{"cluster_id": 1}]},
            [{"cluster_id": 1}],
        ),
        (
            faiss_search.get_cluster_members,
            ("viewer", [0.1, 0.2], 5),
            "post",
            {"comment_ids": ["c1", "c2"]},
            ["c1", "c2"],
        ),
        (
            faiss_search.get_subclusters,
            ("viewer", [0.1, 0.2], 10, 4),
            "post",
            {"subclusters": [{"cluster_id": 2}]},
            [{"cluster_id": 2}],
        ),
    ],
)
def test_cluster_related_functions_return_payload(monkeypatch, func, args, method_name, payload, expected):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")
    monkeypatch.setattr(faiss_search.requests, method_name, lambda *_a, **_k: _DummyResponse(payload=payload))

    assert func(*args) == expected


@pytest.mark.parametrize(
    ("func", "args", "method_name"),
    [
        (faiss_search.get_clusters, ("viewer", 8), "get"),
        (faiss_search.get_cluster_members, ("viewer", [0.1, 0.2], 5), "post"),
        (faiss_search.get_subclusters, ("viewer", [0.1, 0.2], 10, 4), "post"),
    ],
)
def test_cluster_related_functions_return_none_on_404(monkeypatch, func, args, method_name):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")
    monkeypatch.setattr(faiss_search.requests, method_name, lambda *_a, **_k: _DummyResponse(status_code=404))

    assert func(*args) is None


@pytest.mark.parametrize(
    ("func", "args", "method_name"),
    [
        (faiss_search.get_clusters, ("viewer", 8), "get"),
        (faiss_search.get_cluster_members, ("viewer", [0.1, 0.2], 5), "post"),
        (faiss_search.get_subclusters, ("viewer", [0.1, 0.2], 10, 4), "post"),
    ],
)
def test_cluster_related_functions_raise_runtime_error_on_request_exception(monkeypatch, func, args, method_name):
    monkeypatch.setattr(faiss_search, "FAISS_API_URL", "http://faiss-api:8100")

    def _raise(*_args, **_kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(faiss_search.requests, method_name, _raise)

    with pytest.raises(RuntimeError):
        func(*args)
