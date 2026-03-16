"""Sentence-BERT + top-k 近傍ベースライン

本人コメント埋め込みとの近傍類似度でランキングする。
短文チャットは「意味の平均」よりも、似た言い回しへの局所一致が効く前提の手法。

依存パッケージ:
    pip install requests scikit-learn sentence-transformers

使い方:
    python baseline_sentence_bert_knn.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import numpy as np
from sentence_bert_utils import (
    DEFAULT_MODEL,
    all_candidate_bodies,
    encode_texts,
    fetch_task,
    rank_question,
    submit_answers,
    topk_mean_max,
    training_bodies,
    training_labels,
)

TOP_K = 8


def knn_score(query_embeddings: np.ndarray, target_embeddings: np.ndarray) -> np.ndarray:
    similarities = query_embeddings @ target_embeddings.T
    mean_scores, max_scores = topk_mean_max(similarities, TOP_K)
    return 0.7 * mean_scores + 0.3 * max_scores


def predict(training: list[dict], test: list[dict], model_name: str = DEFAULT_MODEL) -> list[dict]:
    X_train_texts = training_bodies(training)
    y_train = training_labels(training)

    print(f"  学習データをエンコード中 ({len(X_train_texts)} 件)...")
    train_embeddings = encode_texts(model_name, X_train_texts, view="raw")
    target_embeddings = train_embeddings[y_train]

    all_bodies = all_candidate_bodies(test)
    n_cand = len(test[0]["candidates"])
    print(f"  テスト候補をエンコード中 ({len(all_bodies)} 件)...")
    candidate_embeddings = encode_texts(model_name, all_bodies, view="raw")

    answers = []
    for q_idx, question in enumerate(test):
        q_embeddings = candidate_embeddings[q_idx * n_cand : (q_idx + 1) * n_cand]
        answers.append(rank_question(question, knn_score(q_embeddings, target_embeddings)))
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
