"""TF-IDF + Random Forest ベースライン

文字 n-gram (1〜3文字) で TF-IDF ベクトル化し、ランダムフォレストで分類する。
決定木のアンサンブルで、特徴量の非線形な組み合わせを捉えられる。

依存パッケージ:
    pip install requests scikit-learn

使い方:
    python baseline_rf.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import requests
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import Pipeline

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


def build_model() -> Pipeline:
    """文字 n-gram TF-IDF + Random Forest。

    n_estimators=300: 木の本数。多いほど安定するが遅くなる。
    max_depth=None: 木を完全に展開（過学習気味になりやすいが、アンサンブルが打ち消す）。
    max_features="sqrt": 各分割で sqrt(n_features) 個の特徴量をランダムに使う。
    class_weight="balanced": クラス比1:1なので実質変化なし（念のため設定）。

    注意: TF-IDF の高次元スパース特徴に対してRFは線形モデルほど効率的でないため、
    max_features を小さくし特徴量サブサンプリングを活かすのがコツ。
    """
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(1, 3),
            min_df=2,          # RF は低頻度特徴でノイズを拾いやすいため min_df を少し上げる
            sublinear_tf=True,
            max_features=5000, # 次元削減: RF の学習速度と精度のバランス
        )),
        ("clf", RandomForestClassifier(
            n_estimators=300,
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
