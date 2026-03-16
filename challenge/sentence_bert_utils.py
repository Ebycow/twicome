import hashlib
import re
import unicodedata
from collections import defaultdict

import numpy as np
import requests

DEFAULT_MODEL = "hotchpotch/static-embedding-japanese"

_ENCODER_CACHE = {}
_EMBEDDING_CACHE = {}

_LAUGH_RE = re.compile(r"[wWｗＷ]{3,}")
_KUSA_RE = re.compile(r"(草){2,}")
_PUNCT_REPEAT_RE = re.compile(r"([!！?？。．、,.~〜ー])\1{2,}")
_CHAR_REPEAT_RE = re.compile(r"(.)\1{5,}")


def fetch_task(base_url: str, login: str) -> dict:
    url = f"{base_url}/api/u/{login}/quiz/task"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()


def submit_answers(base_url: str, login: str, task_token: str, answers: list[dict]) -> dict:
    url = f"{base_url}/api/u/{login}/quiz/task/submit"
    resp = requests.post(url, json={"task_token": task_token, "answers": answers})
    resp.raise_for_status()
    return resp.json()


def load_encoder(model_name: str, *, fresh: bool = False):
    from sentence_transformers import SentenceTransformer

    if fresh or model_name not in _ENCODER_CACHE:
        print(f"  モデルロード中: {model_name}")
        encoder = SentenceTransformer(model_name)
        if not fresh:
            _ENCODER_CACHE[model_name] = encoder
        return encoder
    return _ENCODER_CACHE[model_name]


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return matrix / norms


def normalize_chat_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = " ".join(normalized.split())
    normalized = _LAUGH_RE.sub("www", normalized)
    normalized = _KUSA_RE.sub("草草", normalized)
    normalized = _PUNCT_REPEAT_RE.sub(r"\1\1", normalized)
    normalized = _CHAR_REPEAT_RE.sub(lambda m: m.group(1) * 3, normalized)
    return normalized.strip()


def transform_texts(texts: list[str], view: str) -> list[str]:
    if view == "raw":
        return [text or "" for text in texts]
    if view == "normalized":
        return [normalize_chat_text(text) for text in texts]
    raise ValueError(f"unknown view: {view}")


def encode_with_encoder(encoder, texts: list[str], *, batch_size: int = 256) -> np.ndarray:
    embeddings = encoder.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return l2_normalize(np.asarray(embeddings, dtype=np.float32))


def _embedding_cache_key(model_name: str, view: str, texts: list[str]) -> str:
    hasher = hashlib.sha1()
    hasher.update(model_name.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(view.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(str(len(texts)).encode("utf-8"))
    for text in texts:
        hasher.update(b"\0")
        hasher.update(text.encode("utf-8", errors="ignore"))
    return hasher.hexdigest()


def encode_texts(
    model_name: str,
    texts: list[str],
    *,
    view: str = "raw",
    batch_size: int = 256,
    use_cache: bool = True,
) -> np.ndarray:
    prepared = transform_texts(texts, view)
    cache_key = _embedding_cache_key(model_name, view, prepared)
    if use_cache and cache_key in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[cache_key]

    encoder = load_encoder(model_name)
    embeddings = encode_with_encoder(encoder, prepared, batch_size=batch_size)
    if use_cache:
        _EMBEDDING_CACHE[cache_key] = embeddings
    return embeddings


def training_bodies(training: list[dict]) -> list[str]:
    return [item["body"] for item in training]


def training_labels(training: list[dict]) -> np.ndarray:
    return np.asarray([bool(item["is_target"]) for item in training], dtype=bool)


def all_candidate_bodies(test: list[dict]) -> list[str]:
    return [candidate["body"] for question in test for candidate in question["candidates"]]


def rank_question(question: dict, scores: np.ndarray) -> dict:
    candidates = question["candidates"]
    ranked = [candidates[i]["candidate_id"] for i in scores.argsort()[::-1]]
    return {"id": question["id"], "ranked_candidates": ranked}


def topk_mean_max(similarities: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    if similarities.shape[1] == 0:
        zeros = np.zeros(similarities.shape[0], dtype=np.float32)
        return zeros, zeros

    k = min(k, similarities.shape[1])
    if k == similarities.shape[1]:
        topk = similarities
    else:
        topk = np.partition(similarities, similarities.shape[1] - k, axis=1)[:, -k:]
    return topk.mean(axis=1), topk.max(axis=1)


def batch_topk_features(
    query_embeddings: np.ndarray,
    reference_embeddings: np.ndarray,
    *,
    k: int,
    batch_size: int = 512,
    exclude_reference_index: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    means = np.empty(query_embeddings.shape[0], dtype=np.float32)
    maxes = np.empty(query_embeddings.shape[0], dtype=np.float32)

    for start in range(0, query_embeddings.shape[0], batch_size):
        end = min(start + batch_size, query_embeddings.shape[0])
        similarities = query_embeddings[start:end] @ reference_embeddings.T
        if exclude_reference_index is not None:
            local_indices = exclude_reference_index[start:end]
            valid_rows = np.where(local_indices >= 0)[0]
            if valid_rows.size:
                similarities[valid_rows, local_indices[valid_rows]] = -1.0
        means[start:end], maxes[start:end] = topk_mean_max(similarities, k)

    return means, maxes


def build_user_centroids(embeddings: np.ndarray, training: list[dict]) -> dict[int, np.ndarray]:
    grouped = defaultdict(list)
    for idx, item in enumerate(training):
        grouped[int(item["user_idx"])].append(idx)

    centroids = {}
    for user_idx, indices in grouped.items():
        centroid = embeddings[np.asarray(indices, dtype=np.int32)].mean(axis=0, keepdims=True)
        centroids[user_idx] = l2_normalize(centroid)[0]
    return centroids


def _is_symbolic_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return all(
        char.isspace() or unicodedata.category(char).startswith(("S", "P"))
        for char in stripped
    )


def bucketize_short_text(text: str) -> str:
    normalized = normalize_chat_text(text)
    if not normalized:
        return "empty"
    if _is_symbolic_text(normalized):
        return "symbolic"
    if "?" in normalized or "？" in normalized:
        return "question"
    if "草" in normalized or "w" in normalized.lower():
        return "laugh"
    if len(normalized) <= 2:
        return "ultra_short"
    if len(normalized) <= 6:
        return "short"
    if " " in normalized:
        return "multi_token"
    return "default"


def build_bucket_embeddings(texts: list[str], embeddings: np.ndarray) -> dict[str, np.ndarray]:
    grouped = defaultdict(list)
    for idx, text in enumerate(texts):
        grouped[bucketize_short_text(text)].append(idx)
    return {
        bucket: embeddings[np.asarray(indices, dtype=np.int32)]
        for bucket, indices in grouped.items()
    }


def build_bucket_centroids(texts: list[str], embeddings: np.ndarray) -> dict[str, np.ndarray]:
    grouped = defaultdict(list)
    for idx, text in enumerate(texts):
        grouped[bucketize_short_text(text)].append(idx)

    centroids = {}
    for bucket, indices in grouped.items():
        centroid = embeddings[np.asarray(indices, dtype=np.int32)].mean(axis=0, keepdims=True)
        centroids[bucket] = l2_normalize(centroid)[0]
    return centroids


def centroid_similarity(query_embeddings: np.ndarray, centroid: np.ndarray) -> np.ndarray:
    return query_embeddings @ centroid


def stratified_sample_indices(labels: np.ndarray, max_items: int, *, seed: int = 42) -> np.ndarray:
    if len(labels) <= max_items:
        return np.arange(len(labels), dtype=np.int32)

    rng = np.random.default_rng(seed)
    pos_idx = np.flatnonzero(labels)
    neg_idx = np.flatnonzero(~labels)

    if len(pos_idx) >= max_items:
        return np.sort(rng.choice(pos_idx, size=max_items, replace=False))

    n_neg = max_items - len(pos_idx)
    sampled_neg = rng.choice(neg_idx, size=n_neg, replace=False)
    combined = np.concatenate([pos_idx, sampled_neg]).astype(np.int32)
    return np.sort(combined)
