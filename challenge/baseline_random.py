"""ランダム予測ベースライン

API フローの最小実装。候補の中からランダムに 1 件を選び、残りを任意順で並べる。
Top-1 期待正答率: 1/100 = 1%、MRR 期待値: ≈ 0.019

使い方:
    python baseline_random.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse
import random

import requests


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


def predict(training: list[dict], test: list[dict]) -> list[dict]:
    """予測ロジック。このサンプルはランダムな順位付け。ここを実装してください。

    Args:
        training: ラベル付き学習データ。各要素は {"body": str, "is_target": bool, "user_idx": int}
        test:     テスト問題リスト。各要素は {"id": int, "candidates": [{"candidate_id": int, "body": str}, ...]}

    Returns:
        [{"id": int, "ranked_candidates": [candidate_id, ...]}, ...]
        ranked_candidates は予測確信度降順（先頭が本人と思われる候補）の全候補 ID リスト。
    """
    answers = []
    for question in test:
        cids = [c["candidate_id"] for c in question["candidates"]]
        random.shuffle(cids)
        answers.append({"id": question["id"], "ranked_candidates": cids})
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

    answers = predict(task["training"], task["test"])

    print("予測を提出中...")
    result = submit_answers(args.base_url, args.login, task["task_token"], answers)

    print("\n--- 結果 ---")
    print(f"Top-1 accuracy: {result['top1_accuracy']:.1%}  ({result['correct_top1']} / {result['total']})")
    print(f"MRR:            {result['mrr']:.4f}")


if __name__ == "__main__":
    main()
