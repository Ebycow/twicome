"""ランダム予測ベースライン

API フローの最小実装。予測ロジックをここに差し替えることでカスタム実装のスケルトンになる。
期待正答率: 50%（クラス比 1:1 のためコインフリップと同じ）

使い方:
    python baseline_random.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse
import random

import requests

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


def predict(training: list[dict], test: list[dict]) -> list[dict]:
    """予測ロジック。このサンプルはランダム予測。ここを実装してください。

    Args:
        training: ラベル付き学習データ。各要素は {"body": str, "is_target": bool}
        test:     ラベルなしテストデータ。各要素は {"id": int, "body": str}

    Returns:
        [{"id": int, "prediction": bool}, ...] — test と同じ順序・件数でなくてよいが全 id が必要
    """
    return [{"id": item["id"], "prediction": random.choice([True, False])} for item in test]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", required=True, help="対象ユーザーの login")
    parser.add_argument("--base-url", default="http://localhost:8000/twicome")
    args = parser.parse_args()

    print(f"タスク取得中: {args.login}")
    task = fetch_task(args.base_url, args.login)
    print(f"  学習データ: {task['train_count']} 件, テストデータ: {task['test_count']} 件")

    answers = predict(task["training"], task["test"])

    print("予測を提出中...")
    result = submit_answers(args.base_url, args.login, task["task_token"], answers)

    print(f"\n--- 結果 ---")
    print(f"正答率: {result['accuracy']:.1%}  ({result['correct']} / {result['total']})")


if __name__ == "__main__":
    main()
