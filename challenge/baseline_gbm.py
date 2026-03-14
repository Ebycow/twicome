"""TF-IDF + Gradient Boosting ベースライン

文字 n-gram (1〜3文字) で TF-IDF ベクトル化し、勾配ブースティングで分類する。
HistGradientBoostingClassifier は scikit-learn 実装の高速版 GBM。

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
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

TRAIN_COUNT = 200
TEST_COUNT = 100


def fetch_task(base_url: str, login: str) -> dict:
    url = f"{base_url}/api/u/{login}/quiz/task"
    resp = requests.get(url, params={"train_count": TRAIN_COUNT, "test_count": TEST_COUNT})
    resp.raise_for_status()
    return resp.json()


def submit_answers(base_url: str, login: str, task_token: str, answers: list[dict]) -> dict:
    url = f"{base_url}/api/u/{login}/quiz/task/submit"
    resp = requests.post(url, json={"task_token": task_token, "answers": answers})
    resp.raise_for_status()
    return resp.json()


def _to_dense(matrix):
    """HistGradientBoostingClassifier 用に疎行列を dense に変換する。"""
    if hasattr(matrix, "toarray"):
        return matrix.toarray()
    return np.asarray(matrix)


def build_model(n_features: int = 3000) -> Pipeline:
    """文字 n-gram TF-IDF + HistGradientBoostingClassifier。

    GBM は TF-IDF の高次元スパース行列が苦手なため、次元削減が重要。
    ここでは max_features で上位 n_features 個に絞り、
    さらに dense 行列へ変換して HistGBM に渡す。

    max_iter=200: ブースティングの反復回数（木の本数に相当）。
    learning_rate=0.1: 各ステップの学習率。小さいほど慎重に学習。
    max_depth=4: 各木の深さ。浅めにして過学習を防ぐ。
    l2_regularization=1.0: L2 正則化。
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
            max_iter=200,
            learning_rate=0.1,
            max_depth=4,
            l2_regularization=1.0,
            random_state=42,
        )),
    ])


def predict(training: list[dict], test: list[dict]) -> list[dict]:
    X_train = [item["body"] for item in training]
    y_train = [item["is_target"] for item in training]
    X_test = [item["body"] for item in test]

    model = build_model()

    cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring="accuracy")
    print(f"  交差検証 (5-fold): {cv_scores.mean():.1%} ± {cv_scores.std():.1%}")

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    return [{"id": item["id"], "prediction": bool(pred)} for item, pred in zip(test, y_pred)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", required=True, help="対象ユーザーの login")
    parser.add_argument("--base-url", default="http://localhost:8000/twicome")
    args = parser.parse_args()

    print(f"タスク取得中: {args.login}")
    task = fetch_task(args.base_url, args.login)
    print(f"  学習データ: {task['train_count']} 件, テストデータ: {task['test_count']} 件")

    print("モデルを訓練中...")
    answers = predict(task["training"], task["test"])

    print("予測を提出中...")
    result = submit_answers(args.base_url, args.login, task["task_token"], answers)

    print(f"\n--- 結果 ---")
    print(f"正答率: {result['accuracy']:.1%}  ({result['correct']} / {result['total']})")

    false_positives = [d for d in result["details"] if d["prediction"] and not d["actual"]]
    false_negatives = [d for d in result["details"] if not d["prediction"] and d["actual"]]
    print(f"偽陽性 (別人→本人と判定): {len(false_positives)} 件")
    print(f"偽陰性 (本人→別人と判定): {len(false_negatives)} 件")


if __name__ == "__main__":
    main()
