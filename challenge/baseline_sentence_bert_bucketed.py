"""Sentence-BERT + バケット別プロトタイプベースライン

候補コメントを短文タイプごとに分け、同じタイプの本人コメント重心と比較する。
「笑い系」「超短文」「疑問文」などの短文スタイル差を明示的に使う。

依存パッケージ:
    pip install requests scikit-learn sentence-transformers

使い方:
    python baseline_sentence_bert_bucketed.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import numpy as np
from sentence_bert_utils import (
    DEFAULT_MODEL,
    all_candidate_bodies,
    bucketize_short_text,
    build_bucket_centroids,
    build_bucket_embeddings,
    centroid_similarity,
    encode_texts,
    fetch_task,
    l2_normalize,
    rank_question,
    submit_answers,
    topk_mean_max,
    training_bodies,
    training_labels,
)

TOP_K = 6
MIN_BUCKET_ITEMS = 8


def local_bucket_score(query_embedding: np.ndarray, bucket_embeddings: np.ndarray) -> float:
    similarities = query_embedding[None, :] @ bucket_embeddings.T
    mean_score, max_score = topk_mean_max(similarities, TOP_K)
    return float(0.6 * mean_score[0] + 0.4 * max_score[0])


def predict(training: list[dict], test: list[dict], model_name: str = DEFAULT_MODEL) -> list[dict]:
    X_train_texts = training_bodies(training)
    y_train = training_labels(training)
    target_texts = [text for text, is_target in zip(X_train_texts, y_train, strict=True) if is_target]

    print(f"  学習データを normalized view でエンコード中 ({len(X_train_texts)} 件)...")
    train_embeddings = encode_texts(model_name, X_train_texts, view="normalized")
    target_embeddings = train_embeddings[y_train]
    global_centroid = l2_normalize(target_embeddings.mean(axis=0, keepdims=True))[0]
    bucket_centroids = build_bucket_centroids(target_texts, target_embeddings)
    bucket_embeddings = build_bucket_embeddings(target_texts, target_embeddings)

    all_bodies = all_candidate_bodies(test)
    n_cand = len(test[0]["candidates"])
    print(f"  テスト候補を normalized view でエンコード中 ({len(all_bodies)} 件)...")
    candidate_embeddings = encode_texts(model_name, all_bodies, view="normalized")

    answers = []
    for q_idx, question in enumerate(test):
        q_embeddings = candidate_embeddings[q_idx * n_cand : (q_idx + 1) * n_cand]
        scores = np.empty(n_cand, dtype=np.float32)
        for idx, candidate in enumerate(question["candidates"]):
            bucket = bucketize_short_text(candidate["body"])
            local_centroid = bucket_centroids.get(bucket, global_centroid)
            local_centroid_score = float(centroid_similarity(q_embeddings[idx : idx + 1], local_centroid)[0])

            local_bucket = bucket_embeddings.get(bucket)
            if local_bucket is None or len(local_bucket) < MIN_BUCKET_ITEMS:
                local_knn_score = float(local_centroid_score)
            else:
                local_knn_score = local_bucket_score(q_embeddings[idx], local_bucket)

            global_score = float(centroid_similarity(q_embeddings[idx : idx + 1], global_centroid)[0])
            scores[idx] = 0.5 * local_knn_score + 0.3 * local_centroid_score + 0.2 * global_score

        answers.append(rank_question(question, scores))
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
