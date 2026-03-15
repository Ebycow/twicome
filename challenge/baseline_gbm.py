"""TF-IDF + Gradient Boosting ベースライン

文字 n-gram (1〜3文字) で TF-IDF ベクトル化し、HistGradientBoostingClassifier で分類する。
100k 規模では学習に数分かかる場合がある。

依存パッケージ:
    pip install requests scikit-learn

使い方:
    python baseline_gbm.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import numpy as np
import requests
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer


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


def _to_dense(matrix):
    if hasattr(matrix, "toarray"):
        return matrix.toarray()
    return np.asarray(matrix)


def build_model(n_features: int = 3000) -> Pipeline:
    """文字 n-gram TF-IDF + HistGradientBoostingClassifier。

    class_weight="balanced": 学習データの本人:別人比 1:99 を自動補正。
    max_iter=100: 100k 規模ではイテレーション数を抑えて速度を確保。
    """
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(1, 3),
            min_df=2,
            sublinear_tf=True,
            max_features=n_features,
        )),
        ("to_dense", FunctionTransformer(_to_dense, accept_sparse=True)),
        ("clf", HistGradientBoostingClassifier(
            max_iter=100,
            learning_rate=0.1,
            max_depth=4,
            l2_regularization=1.0,
            class_weight="balanced",
            random_state=42,
        )),
    ])


def predict(training: list[dict], test: list[dict]) -> list[dict]:
    X_train = [item["body"] for item in training]
    y_train = [item["is_target"] for item in training]

    model = build_model()
    model.fit(X_train, y_train)

    answers = []
    for question in test:
        candidates = question["candidates"]
        X_q = [c["body"] for c in candidates]
        scores = model.predict_proba(X_q)[:, 1]
        ranked = [candidates[i]["candidate_id"] for i in scores.argsort()[::-1]]
        answers.append({"id": question["id"], "ranked_candidates": ranked})
    return answers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", required=True, help="対象ユーザーの login")
    parser.add_argument("--base-url", default="http://localhost:8000/twicome")
    args = parser.parse_args()

    print(f"タスク取得中: {args.login}")
    task = fetch_task(args.base_url, args.login)
    print(f"  学習データ: {task['train_count']} 件, テスト: {task['test_count']} 問 × {task['candidates_per_question']} 候補")

    print("モデルを訓練中...")
    answers = predict(task["training"], task["test"])

    print("予測を提出中...")
    result = submit_answers(args.base_url, args.login, task["task_token"], answers)

    print(f"\n--- 結果 ---")
    print(f"Top-1 accuracy: {result['top1_accuracy']:.1%}  ({result['correct_top1']} / {result['total']})")
    print(f"MRR:            {result['mrr']:.4f}")


if __name__ == "__main__":
    main()
