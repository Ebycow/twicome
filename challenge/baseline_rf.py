"""TF-IDF + Random Forest ベースライン

文字 n-gram (1〜3文字) で TF-IDF ベクトル化し、ランダムフォレストで分類する。
100k 規模では学習に数分かかる場合がある。

依存パッケージ:
    pip install requests scikit-learn

使い方:
    python baseline_rf.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import requests
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline


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


def build_model() -> Pipeline:
    """文字 n-gram TF-IDF + Random Forest。

    n_estimators=200: 100k 規模では 300 より少なめにして速度を確保。
    max_features=5000: 高次元スパース特徴を削減（RF は線形モデルより次元削減が効く）。
    class_weight="balanced": 学習データの本人:別人比 1:99 を自動補正。
    """
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(1, 3),
            min_df=2,
            sublinear_tf=True,
            max_features=5000,
        )),
        ("clf", RandomForestClassifier(
            n_estimators=200,
            max_depth=None,
            max_features="sqrt",
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
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
