"""sentence-transformers 埋め込み + ロジスティック回帰ベースライン

事前学習済み日本語モデルでコメントをベクトル化し、ロジスティック回帰で分類する。
モデルはこのプロジェクトで使用している `hotchpotch/static-embedding-japanese`。
静的埋め込み (static embeddings) のため非常に高速で GPU 不要。

他の BERT 系モデル (encode に時間がかかるが精度が高い可能性) を使いたい場合:
    MODEL_NAME = "cl-tohoku/bert-base-japanese-char-v3"  など

依存パッケージ:
    pip install requests scikit-learn sentence-transformers

使い方:
    python baseline_sentence_bert.py --login someuser --base-url http://localhost:8000/twicome
    python baseline_sentence_bert.py --login someuser --model cl-tohoku/bert-base-japanese-char-v3
"""

import argparse

import numpy as np
import requests
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

TRAIN_COUNT = 200
TEST_COUNT = 100
DEFAULT_MODEL = "hotchpotch/static-embedding-japanese"


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


def load_encoder(model_name: str):
    """SentenceTransformer モデルをロードして返す。"""
    from sentence_transformers import SentenceTransformer
    print(f"  モデルロード中: {model_name}")
    return SentenceTransformer(model_name)


def encode(encoder, texts: list[str]) -> np.ndarray:
    """テキストリストを埋め込みベクトル行列に変換する。"""
    return encoder.encode(texts, show_progress_bar=False, convert_to_numpy=True)


def predict(training: list[dict], test: list[dict], model_name: str) -> list[dict]:
    """埋め込みを固定特徴量として使う "freeze + probe" アプローチ。

    アルゴリズム:
        1. 事前学習済みモデルでコメントを固定ベクトルに変換
        2. そのベクトルを特徴量にロジスティック回帰を学習
        3. テストデータを同様にベクトル化して予測

    200 件の少データでは BERT の fine-tuning は過学習しやすいため、
    モデルを凍結して線形分類器のみ学習する方が安定する。

    C=5.0: 埋め込みベクトルは密で高品質なため、LR の正則化は緩めでよい。
    """
    encoder = load_encoder(model_name)

    X_train_texts = [item["body"] for item in training]
    y_train = [item["is_target"] for item in training]
    X_test_texts = [item["body"] for item in test]

    print("  学習データをエンコード中...")
    X_train = encode(encoder, X_train_texts)
    print("  テストデータをエンコード中...")
    X_test = encode(encoder, X_test_texts)

    clf = LogisticRegression(max_iter=1000, C=5.0)

    cv_scores = cross_val_score(clf, X_train, y_train, cv=5, scoring="accuracy")
    print(f"  交差検証 (5-fold): {cv_scores.mean():.1%} ± {cv_scores.std():.1%}")

    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    return [{"id": item["id"], "prediction": bool(pred)} for item, pred in zip(test, y_pred)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", required=True, help="対象ユーザーの login")
    parser.add_argument("--base-url", default="http://localhost:8000/twicome")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="SentenceTransformer モデル名")
    args = parser.parse_args()

    print(f"タスク取得中: {args.login}")
    task = fetch_task(args.base_url, args.login)
    print(f"  学習データ: {task['train_count']} 件, テストデータ: {task['test_count']} 件")

    print("モデルを訓練中...")
    answers = predict(task["training"], task["test"], args.model)

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
