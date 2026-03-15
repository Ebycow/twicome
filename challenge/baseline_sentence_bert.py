"""sentence-transformers 埋め込み + ロジスティック回帰ベースライン

事前学習済み日本語モデルでコメントをベクトル化し、ロジスティック回帰で分類する。
デフォルトモデル: hotchpotch/static-embedding-japanese（静的埋め込み、GPU 不要・高速）

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

DEFAULT_MODEL = "hotchpotch/static-embedding-japanese"


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


def load_encoder(model_name: str):
    from sentence_transformers import SentenceTransformer

    print(f"  モデルロード中: {model_name}")
    return SentenceTransformer(model_name)


def encode(encoder, texts: list[str]) -> np.ndarray:
    return encoder.encode(texts, show_progress_bar=False, convert_to_numpy=True)


def predict(training: list[dict], test: list[dict], model_name: str = DEFAULT_MODEL) -> list[dict]:
    """埋め込みを固定特徴量として使う "freeze + probe" アプローチ。

    1. 事前学習済みモデルでコメントを固定ベクトルに変換
    2. そのベクトルを特徴量にロジスティック回帰を学習
    3. 各問題の 100 候補を埋め込みベクトル化して predict_proba でスコアリング
    """
    encoder = load_encoder(model_name)

    X_train_texts = [item["body"] for item in training]
    y_train = [item["is_target"] for item in training]

    print(f"  学習データをエンコード中 ({len(X_train_texts)} 件)...")
    X_train = encode(encoder, X_train_texts)

    clf = LogisticRegression(max_iter=1000, C=5.0)
    clf.fit(X_train, y_train)

    # テスト候補を問題ごとにエンコードしてスコアリング
    # 全候補をまとめてエンコードした方が速い
    all_bodies = [c["body"] for q in test for c in q["candidates"]]
    n_cand = len(test[0]["candidates"])

    print(f"  テスト候補をエンコード中 ({len(all_bodies)} 件)...")
    all_embeddings = encode(encoder, all_bodies)
    all_scores = clf.predict_proba(all_embeddings)[:, 1]

    answers = []
    for q_idx, question in enumerate(test):
        candidates = question["candidates"]
        scores = all_scores[q_idx * n_cand : (q_idx + 1) * n_cand]
        ranked = [candidates[i]["candidate_id"] for i in scores.argsort()[::-1]]
        answers.append({"id": question["id"], "ranked_candidates": ranked})
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
