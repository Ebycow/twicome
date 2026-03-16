"""Sentence-BERT + target/other margin ベースライン

本人コメントとの近さに加えて、他ユーザー群の重心に近すぎないことも見る。
短くて誰でも言いそうなコメントを落としやすいように margin を使う。

依存パッケージ:
    pip install requests scikit-learn sentence-transformers

使い方:
    python baseline_sentence_bert_margin.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import numpy as np
from sentence_bert_utils import (
    DEFAULT_MODEL,
    all_candidate_bodies,
    build_user_centroids,
    centroid_similarity,
    encode_texts,
    fetch_task,
    rank_question,
    submit_answers,
    topk_mean_max,
    training_bodies,
    training_labels,
)

TOP_K = 8


def margin_score(
    query_embeddings: np.ndarray,
    target_embeddings: np.ndarray,
    target_centroid: np.ndarray,
    other_centroids: np.ndarray,
) -> np.ndarray:
    target_similarities = query_embeddings @ target_embeddings.T
    target_mean, target_max = topk_mean_max(target_similarities, TOP_K)
    target_local = 0.65 * target_mean + 0.35 * target_max
    target_global = centroid_similarity(query_embeddings, target_centroid)
    other_global = (query_embeddings @ other_centroids.T).max(axis=1)
    return 0.7 * target_local + 0.25 * target_global - 0.4 * other_global


def predict(training: list[dict], test: list[dict], model_name: str = DEFAULT_MODEL) -> list[dict]:
    X_train_texts = training_bodies(training)
    y_train = training_labels(training)

    print(f"  学習データをエンコード中 ({len(X_train_texts)} 件)...")
    train_embeddings = encode_texts(model_name, X_train_texts, view="raw")
    target_embeddings = train_embeddings[y_train]
    centroids = build_user_centroids(train_embeddings, training)
    target_centroid = centroids[0]
    other_centroids = np.vstack([centroid for user_idx, centroid in centroids.items() if user_idx != 0])

    all_bodies = all_candidate_bodies(test)
    n_cand = len(test[0]["candidates"])
    print(f"  テスト候補をエンコード中 ({len(all_bodies)} 件)...")
    candidate_embeddings = encode_texts(model_name, all_bodies, view="raw")

    answers = []
    for q_idx, question in enumerate(test):
        q_embeddings = candidate_embeddings[q_idx * n_cand : (q_idx + 1) * n_cand]
        scores = margin_score(q_embeddings, target_embeddings, target_centroid, other_centroids)
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
