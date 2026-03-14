"""アンサンブル (投票) ベースライン

複数の異なるモデルの予測を多数決（ソフト投票）で統合する。
個々のモデルの弱点を補い合い、単一モデルより安定した性能を期待できる。

構成モデル:
    1. 文字 n-gram TF-IDF + LogisticRegression
    2. 文字 n-gram TF-IDF + LinearSVC (calibrated)
    3. 文字 n-gram TF-IDF + ComplementNB
    4. 文字+単語 n-gram TF-IDF + LogisticRegression

依存パッケージ:
    pip install requests scikit-learn

使い方:
    python baseline_ensemble.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import requests
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import VotingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.preprocessing import MaxAbsScaler
from sklearn.svm import LinearSVC

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


def _char_tfidf(ngram=(1, 3), **kwargs):
    return TfidfVectorizer(analyzer="char_wb", ngram_range=ngram, min_df=1, sublinear_tf=True, **kwargs)


def build_model() -> Pipeline:
    """4つのモデルをソフト投票でアンサンブル。

    voting="soft": 各モデルの確率の平均を取って最終予測を決定。
        "hard" (多数決) より確率的に安定している。
    weights=[2, 2, 1, 2]: LR と SVM を重めに、NB を軽めに。
        データや対象ユーザーによって最適な重みは変わる。

    各モデルの特徴:
        lr_char:   文字 n-gram の主力モデル
        svm_char:  SVM は決定境界が LR と異なる視点を提供
        nb_char:   Naive Bayes は過学習しにくく安定役
        lr_both:   文字+単語の結合ベクトルで語彙パターンも捉える
    """
    lr_char = Pipeline([
        ("tfidf", _char_tfidf()),
        ("clf", LogisticRegression(max_iter=1000, C=1.0)),
    ])
    svm_char = Pipeline([
        ("tfidf", _char_tfidf()),
        ("clf", CalibratedClassifierCV(LinearSVC(max_iter=2000, C=0.5))),
    ])
    nb_char = Pipeline([
        ("tfidf", _char_tfidf()),
        ("scaler", MaxAbsScaler()),
        ("clf", ComplementNB(alpha=0.3)),
    ])
    lr_both = Pipeline([
        ("features", FeatureUnion([
            ("char", _char_tfidf()),
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
        ])),
        ("clf", LogisticRegression(max_iter=1000, C=1.0)),
    ])

    ensemble = VotingClassifier(
        estimators=[
            ("lr_char", lr_char),
            ("svm_char", svm_char),
            ("nb_char", nb_char),
            ("lr_both", lr_both),
        ],
        voting="soft",
        weights=[2, 2, 1, 2],
    )
    return ensemble


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
