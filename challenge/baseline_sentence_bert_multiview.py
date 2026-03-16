"""Sentence-BERT + 短文正規化 multi-view ベースライン

raw と正規化後の 2 視点で埋め込みを作り、短文チャット特有の表記ゆれを吸収する。
`w` / `ｗ` / `wwww` / 全半角の揺れが多いケースを想定した手法。

依存パッケージ:
    pip install requests scikit-learn sentence-transformers

使い方:
    python baseline_sentence_bert_multiview.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import numpy as np
from sentence_bert_utils import (
    DEFAULT_MODEL,
    all_candidate_bodies,
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

TOP_K = 8


def knn_score(query_embeddings: np.ndarray, target_embeddings: np.ndarray) -> np.ndarray:
    similarities = query_embeddings @ target_embeddings.T
    mean_scores, max_scores = topk_mean_max(similarities, TOP_K)
    return 0.7 * mean_scores + 0.3 * max_scores


def predict(training: list[dict], test: list[dict], model_name: str = DEFAULT_MODEL) -> list[dict]:
    X_train_texts = training_bodies(training)
    y_train = training_labels(training)

    print(f"  学習データを raw view でエンコード中 ({len(X_train_texts)} 件)...")
    train_raw = encode_texts(model_name, X_train_texts, view="raw")
    print(f"  学習データを normalized view でエンコード中 ({len(X_train_texts)} 件)...")
    train_norm = encode_texts(model_name, X_train_texts, view="normalized")

    target_raw = train_raw[y_train]
    target_norm = train_norm[y_train]
    target_mix = l2_normalize((target_raw + target_norm) / 2.0)
    target_mix_centroid = l2_normalize(target_mix.mean(axis=0, keepdims=True))[0]

    all_bodies = all_candidate_bodies(test)
    n_cand = len(test[0]["candidates"])
    print(f"  テスト候補を raw view でエンコード中 ({len(all_bodies)} 件)...")
    candidate_raw = encode_texts(model_name, all_bodies, view="raw")
    print(f"  テスト候補を normalized view でエンコード中 ({len(all_bodies)} 件)...")
    candidate_norm = encode_texts(model_name, all_bodies, view="normalized")
    candidate_mix = l2_normalize((candidate_raw + candidate_norm) / 2.0)

    answers = []
    for q_idx, question in enumerate(test):
        start = q_idx * n_cand
        end = (q_idx + 1) * n_cand
        q_raw = candidate_raw[start:end]
        q_norm = candidate_norm[start:end]
        q_mix = candidate_mix[start:end]
        raw_score = knn_score(q_raw, target_raw)
        norm_score = knn_score(q_norm, target_norm)
        mix_score = centroid_similarity(q_mix, target_mix_centroid)
        scores = 0.4 * raw_score + 0.4 * norm_score + 0.2 * mix_score
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
