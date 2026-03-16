"""Sentence-BERT + 二段階 rerank ベースライン

1段目で近傍類似度から候補を絞り、2段目で埋め込み由来の少数特徴を使って再ランキングする。
短文タスク向けに「拾う」と「落とす」を分離した構成。

依存パッケージ:
    pip install requests scikit-learn sentence-transformers

使い方:
    python baseline_sentence_bert_rerank.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import numpy as np
from sentence_bert_utils import (
    DEFAULT_MODEL,
    all_candidate_bodies,
    batch_topk_features,
    bucketize_short_text,
    build_bucket_centroids,
    build_user_centroids,
    centroid_similarity,
    encode_texts,
    fetch_task,
    normalize_chat_text,
    stratified_sample_indices,
    submit_answers,
    training_bodies,
    training_labels,
)
from sklearn.linear_model import LogisticRegression

TOP_K = 8
RERANK_TOP_N = 20
TRAIN_SAMPLE_MAX = 20000


def _bucket_similarity(
    texts: list[str],
    embeddings: np.ndarray,
    bucket_centroids: dict[str, np.ndarray],
    fallback_centroid: np.ndarray,
) -> np.ndarray:
    values = np.empty(len(texts), dtype=np.float32)
    for idx, text in enumerate(texts):
        centroid = bucket_centroids.get(bucketize_short_text(text), fallback_centroid)
        values[idx] = float(centroid_similarity(embeddings[idx : idx + 1], centroid)[0])
    return values


def build_feature_matrix(
    texts: list[str],
    raw_embeddings: np.ndarray,
    norm_embeddings: np.ndarray,
    target_raw: np.ndarray,
    target_norm: np.ndarray,
    target_raw_centroid: np.ndarray,
    target_norm_centroid: np.ndarray,
    other_raw_centroids: np.ndarray,
    raw_bucket_centroids: dict[str, np.ndarray],
    norm_bucket_centroids: dict[str, np.ndarray],
    *,
    exclude_target_index: np.ndarray | None = None,
) -> np.ndarray:
    raw_mean, raw_max = batch_topk_features(
        raw_embeddings,
        target_raw,
        k=TOP_K,
        exclude_reference_index=exclude_target_index,
    )
    norm_mean, norm_max = batch_topk_features(
        norm_embeddings,
        target_norm,
        k=TOP_K,
        exclude_reference_index=exclude_target_index,
    )
    raw_centroid = centroid_similarity(raw_embeddings, target_raw_centroid)
    norm_centroid = centroid_similarity(norm_embeddings, target_norm_centroid)
    other_max = (raw_embeddings @ other_raw_centroids.T).max(axis=1)
    bucket_raw = _bucket_similarity(texts, raw_embeddings, raw_bucket_centroids, target_raw_centroid)
    bucket_norm = _bucket_similarity(texts, norm_embeddings, norm_bucket_centroids, target_norm_centroid)

    norm_lengths = np.asarray([np.log1p(len(normalize_chat_text(text))) for text in texts], dtype=np.float32)
    short_flags = np.asarray(
        [1.0 if bucketize_short_text(text) in {"ultra_short", "short"} else 0.0 for text in texts],
        dtype=np.float32,
    )
    laugh_flags = np.asarray(
        [1.0 if bucketize_short_text(text) == "laugh" else 0.0 for text in texts],
        dtype=np.float32,
    )

    return np.column_stack(
        [
            raw_mean,
            raw_max,
            norm_mean,
            norm_max,
            raw_centroid,
            norm_centroid,
            raw_centroid - other_max,
            bucket_raw,
            bucket_norm,
            norm_lengths,
            short_flags,
            laugh_flags,
        ]
    ).astype(np.float32)


def base_stage_score(features: np.ndarray) -> np.ndarray:
    return (
        0.28 * features[:, 0]
        + 0.12 * features[:, 1]
        + 0.24 * features[:, 2]
        + 0.08 * features[:, 3]
        + 0.18 * features[:, 6]
        + 0.10 * features[:, 8]
    )


def predict(training: list[dict], test: list[dict], model_name: str = DEFAULT_MODEL) -> list[dict]:
    X_train_texts = training_bodies(training)
    y_train = training_labels(training)
    target_indices = np.flatnonzero(y_train)
    target_position = np.full(len(training), -1, dtype=np.int32)
    target_position[target_indices] = np.arange(len(target_indices), dtype=np.int32)

    print(f"  学習データを raw view でエンコード中 ({len(X_train_texts)} 件)...")
    train_raw = encode_texts(model_name, X_train_texts, view="raw")
    print(f"  学習データを normalized view でエンコード中 ({len(X_train_texts)} 件)...")
    train_norm = encode_texts(model_name, X_train_texts, view="normalized")

    target_raw = train_raw[y_train]
    target_norm = train_norm[y_train]
    target_raw_centroid = build_user_centroids(train_raw, training)[0]
    other_raw_centroids = np.vstack(
        [centroid for user_idx, centroid in build_user_centroids(train_raw, training).items() if user_idx != 0]
    )
    target_norm_centroid = target_norm.mean(axis=0, keepdims=True)
    target_norm_centroid = target_norm_centroid / np.linalg.norm(target_norm_centroid, axis=1, keepdims=True)
    target_norm_centroid = target_norm_centroid[0].astype(np.float32)

    target_texts = [text for text, is_target in zip(X_train_texts, y_train, strict=True) if is_target]
    raw_bucket_centroids = build_bucket_centroids(target_texts, target_raw)
    norm_bucket_centroids = build_bucket_centroids(target_texts, target_norm)

    sample_indices = stratified_sample_indices(y_train, TRAIN_SAMPLE_MAX, seed=7)
    sample_texts = [X_train_texts[idx] for idx in sample_indices]
    sample_features = build_feature_matrix(
        sample_texts,
        train_raw[sample_indices],
        train_norm[sample_indices],
        target_raw,
        target_norm,
        target_raw_centroid,
        target_norm_centroid,
        other_raw_centroids,
        raw_bucket_centroids,
        norm_bucket_centroids,
        exclude_target_index=target_position[sample_indices],
    )
    sample_labels = y_train[sample_indices]

    reranker = LogisticRegression(
        max_iter=2000,
        C=3.0,
        solver="liblinear",
        class_weight="balanced",
    )
    reranker.fit(sample_features, sample_labels)

    all_bodies = all_candidate_bodies(test)
    n_cand = len(test[0]["candidates"])
    print(f"  テスト候補を raw view でエンコード中 ({len(all_bodies)} 件)...")
    candidate_raw = encode_texts(model_name, all_bodies, view="raw")
    print(f"  テスト候補を normalized view でエンコード中 ({len(all_bodies)} 件)...")
    candidate_norm = encode_texts(model_name, all_bodies, view="normalized")

    answers = []
    for q_idx, question in enumerate(test):
        start = q_idx * n_cand
        end = (q_idx + 1) * n_cand
        q_texts = [candidate["body"] for candidate in question["candidates"]]
        q_features = build_feature_matrix(
            q_texts,
            candidate_raw[start:end],
            candidate_norm[start:end],
            target_raw,
            target_norm,
            target_raw_centroid,
            target_norm_centroid,
            other_raw_centroids,
            raw_bucket_centroids,
            norm_bucket_centroids,
        )

        coarse_scores = base_stage_score(q_features)
        coarse_order = coarse_scores.argsort()[::-1]
        head = coarse_order[:RERANK_TOP_N]
        tail = coarse_order[RERANK_TOP_N:]
        head_scores = reranker.predict_proba(q_features[head])[:, 1]
        head = head[head_scores.argsort()[::-1]]
        ranked_indices = np.concatenate([head, tail])
        ranked = [question["candidates"][idx]["candidate_id"] for idx in ranked_indices]
        answers.append({"id": question["id"], "ranked_candidates": ranked})
    return answers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", required=True, help="対象ユーザーの login")
    parser.add_argument("--base-url", default="http://localhost:8000/twicome")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="SentenceTransformer モデル名")
    args = parser.parse_args()

    print(f"タスク取得中: {args.login}")
    task = fetch_task(args.base_url, args.login)
    print(
        f"  学習データ: {task['train_count']} 件, "
        f"テスト: {task['test_count']} 問 × {task['candidates_per_question']} 候補"
    )

    print("モデルを訓練中...")
    answers = predict(task["training"], task["test"], args.model)

    print("予測を提出中...")
    result = submit_answers(args.base_url, args.login, task["task_token"], answers)

    print("\n--- 結果 ---")
    print(f"Top-1 accuracy: {result['top1_accuracy']:.1%}  ({result['correct_top1']} / {result['total']})")
    print(f"MRR:            {result['mrr']:.4f}")


if __name__ == "__main__":
    main()
