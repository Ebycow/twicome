"""手作り特徴量 + SVM ベースライン

テキストの統計的・文字種的な特徴を手動で抽出して分類する。
TF-IDF を使わず、言語に依存しない「コメントスタイル」の違いを捉える。

依存パッケージ:
    pip install requests scikit-learn

使い方:
    python baseline_handcrafted.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse
import re
import unicodedata

import numpy as np
import requests
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
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


# 絵文字判定: Unicode 絵文字ブロックの主要範囲
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F9FF"  # Misc Symbols, Emoticons, etc.
    "\U00002600-\U000027BF"   # Misc Symbols
    "\U0001FA00-\U0001FA9F"   # Chess Symbols, etc.
    "\U00002702-\U000027B0"   # Dingbats
    "]"
)
_FULLWIDTH_ALNUM_RE = re.compile(r"[Ａ-Ｚａ-ｚ０-９]")
_HALFWIDTH_ALPHA_RE = re.compile(r"[A-Za-z]")
_HALFWIDTH_DIGIT_RE = re.compile(r"[0-9]")
_HIRAGANA_RE = re.compile(r"[\u3041-\u3096]")
_KATAKANA_RE = re.compile(r"[\u30A0-\u30FF]")
_HALFKANA_RE = re.compile(r"[\uFF65-\uFF9F]")
_KANJI_RE = re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF]")
_ASCII_PUNCT_RE = re.compile(r"[!-/:-@\[-`{-~]")
_REPEAT_RE = re.compile(r"(.)\1{2,}")


def extract_features(text: str) -> list[float]:
    """テキスト1件から手作り特徴量ベクトルを返す。"""
    n = len(text) if text else 1
    if not text:
        return [0.0] * 20

    length = len(text)
    unique_chars = len(set(text))

    emoji_chars = _EMOJI_RE.findall(text)
    fw_alnum = _FULLWIDTH_ALNUM_RE.findall(text)
    hw_alpha = _HALFWIDTH_ALPHA_RE.findall(text)
    hw_digit = _HALFWIDTH_DIGIT_RE.findall(text)
    hiragana = _HIRAGANA_RE.findall(text)
    katakana = _KATAKANA_RE.findall(text)
    halfkana = _HALFKANA_RE.findall(text)
    kanji = _KANJI_RE.findall(text)
    ascii_punct = _ASCII_PUNCT_RE.findall(text)
    repeats = len(_REPEAT_RE.findall(text))
    spaces = text.count(" ") + text.count("\u3000")

    upper_alpha = [c for c in hw_alpha if c.isupper()]
    upper_ratio = len(upper_alpha) / max(len(hw_alpha), 1)

    avg_codepoint = sum(ord(c) for c in text) / n

    only_one_char = 1.0 if length == 1 else 0.0
    non_emoji = _EMOJI_RE.sub("", text).strip()
    only_emoji = 1.0 if (emoji_chars and not non_emoji) else 0.0

    w_chars = [c for c in text if c in ("w", "ｗ", "W", "Ｗ")]
    kusa_chars = [c for c in text if c == "草"]

    return [
        float(length),
        float(unique_chars),
        unique_chars / n,
        len(emoji_chars) / n,
        len(fw_alnum) / n,
        len(hw_alpha) / n,
        len(hw_digit) / n,
        len(hiragana) / n,
        len(katakana) / n,
        len(halfkana) / n,
        len(kanji) / n,
        len(ascii_punct) / n,
        float(repeats),
        spaces / n,
        upper_ratio,
        avg_codepoint / 100000.0,
        only_one_char,
        only_emoji,
        len(w_chars) / n,
        len(kusa_chars) / n,
    ]


def featurize(items: list[dict]) -> np.ndarray:
    return np.array([extract_features(item["body"]) for item in items])


def featurize_texts(texts: list[str]) -> np.ndarray:
    return np.array([extract_features(t) for t in texts])


def build_model():
    """標準化 + LinearSVC。

    手作り特徴量は単位がバラバラなため StandardScaler で正規化する。
    LinearSVC は 100k 規模でも高速。decision_function でランキングスコアを取得する。
    """
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LinearSVC(C=1.0, max_iter=2000)),
    ])


def predict(training: list[dict], test: list[dict]) -> list[dict]:
    X_train = featurize(training)
    y_train = [item["is_target"] for item in training]

    model = build_model()
    model.fit(X_train, y_train)

    answers = []
    for question in test:
        candidates = question["candidates"]
        X_q = featurize_texts([c["body"] for c in candidates])
        scores = model.decision_function(X_q)
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
