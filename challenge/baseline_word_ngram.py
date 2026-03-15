"""文字 + 単語 n-gram TF-IDF + ロジスティック回帰ベースライン

文字 n-gram と単語 n-gram を結合した特徴量 + LR。
Twitch スタンプ名のような空白区切りトークンの共起パターンを捉える。

依存パッケージ:
    pip install requests scikit-learn

使い方:
    python baseline_word_ngram.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse

import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline


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
    """文字 n-gram + 単語 n-gram の組み合わせ TF-IDF + ロジスティック回帰。

    FeatureUnion で 2 種類のベクトルを横結合:
        char_wb: 文字レベル (1〜3文字) — 語尾・語中の文字パターンを捉える
        word:    単語レベル (1〜2単語) — スタンプ名・定型フレーズの共起を捉える
    """
    char_tfidf = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(1, 3),
        min_df=1,
        sublinear_tf=True,
    )
    word_tfidf = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    )
    return Pipeline(
        [
            (
                "features",
                FeatureUnion(
                    [
                        ("char", char_tfidf),
                        ("word", word_tfidf),
                    ]
                ),
            ),
            ("clf", LogisticRegression(max_iter=1000, C=1.0)),
        ]
    )


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
