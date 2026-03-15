"""アンサンブル (ソフト投票) ベースライン

複数モデルの本人確率スコアを重み付き平均し、降順でランク付けする。
SVM は decision_function をシグモイド変換してスコア化する。

構成モデル:
    1. 文字 n-gram TF-IDF + LogisticRegression
    2. 文字 n-gram TF-IDF + LinearSVC (decision_function)
    3. 文字 n-gram TF-IDF + ComplementNB
    4. 文字+単語 n-gram TF-IDF + LogisticRegression

依存パッケージ:
    pip install requests scikit-learn

使い方:
    python baseline_ensemble.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import numpy as np
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import MaxAbsScaler
from sklearn.svm import LinearSVC


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


def _char_tfidf(ngram=(1, 3)):
    return TfidfVectorizer(analyzer="char_wb", ngram_range=ngram, min_df=1, sublinear_tf=True)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """decision_function の値を [0, 1] にスケールする。"""
    return 1.0 / (1.0 + np.exp(-x))


def predict(training: list[dict], test: list[dict]) -> list[dict]:
    """4 モデルのスコアを重み付き平均してランク付けする。

    LR と NB は predict_proba の is_target 列を使用。
    SVM は decision_function をシグモイド変換してスコア化。
    weights=[2, 2, 1, 2]: LR×2、SVM×2、NB×1、LR_both×2。
    """
    X_train = [item["body"] for item in training]
    y_train = [item["is_target"] for item in training]

    lr_char = Pipeline(
        [
            ("tfidf", _char_tfidf()),
            ("clf", LogisticRegression(max_iter=1000, C=1.0)),
        ]
    )
    svm_char = Pipeline(
        [
            ("tfidf", _char_tfidf()),
            ("clf", LinearSVC(max_iter=2000, C=0.5)),
        ]
    )
    nb_char = Pipeline(
        [
            ("tfidf", _char_tfidf()),
            ("scaler", MaxAbsScaler()),
            ("clf", ComplementNB(alpha=0.3)),
        ]
    )
    lr_both = Pipeline(
        [
            (
                "features",
                FeatureUnion(
                    [
                        ("char", _char_tfidf()),
                        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
                    ]
                ),
            ),
            ("clf", LogisticRegression(max_iter=1000, C=1.0)),
        ]
    )

    models = [lr_char, svm_char, nb_char, lr_both]
    weights = [2.0, 2.0, 1.0, 2.0]
    total_weight = sum(weights)

    for m in models:
        m.fit(X_train, y_train)

    answers = []
    for question in test:
        candidates = question["candidates"]
        X_q = [c["body"] for c in candidates]

        scores = np.zeros(len(candidates))
        scores += weights[0] * lr_char.predict_proba(X_q)[:, 1]
        scores += weights[1] * _sigmoid(svm_char.decision_function(X_q))
        scores += weights[2] * nb_char.predict_proba(X_q)[:, 1]
        scores += weights[3] * lr_both.predict_proba(X_q)[:, 1]
        scores /= total_weight

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
    print(
        f"  学習データ: {task['train_count']} 件, "
        f"テスト: {task['test_count']} 問 × {task['candidates_per_question']} 候補"
    )

    print("モデルを訓練中...")
    answers = predict(task["training"], task["test"])

    print("予測を提出中...")
    result = submit_answers(args.base_url, args.login, task["task_token"], answers)

    print("\n--- 結果 ---")
    print(f"Top-1 accuracy: {result['top1_accuracy']:.1%}  ({result['correct_top1']} / {result['total']})")
    print(f"MRR:            {result['mrr']:.4f}")


if __name__ == "__main__":
    main()
