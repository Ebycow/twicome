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

import requests
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.model_selection import cross_val_score
import numpy as np

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


# 絵文字判定: Unicode 絵文字ブロックの主要範囲
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F9FF"  # Misc Symbols, Emoticons, etc.
    "\U00002600-\U000027BF"   # Misc Symbols
    "\U0001FA00-\U0001FA9F"   # Chess Symbols, etc.
    "\U00002702-\U000027B0"   # Dingbats
    "]"
)
# 全角英数字
_FULLWIDTH_ALNUM_RE = re.compile(r"[Ａ-Ｚａ-ｚ０-９]")
# 半角英字
_HALFWIDTH_ALPHA_RE = re.compile(r"[A-Za-z]")
# 半角数字
_HALFWIDTH_DIGIT_RE = re.compile(r"[0-9]")
# ひらがな
_HIRAGANA_RE = re.compile(r"[\u3041-\u3096]")
# カタカナ（全角）
_KATAKANA_RE = re.compile(r"[\u30A0-\u30FF]")
# 半角カタカナ
_HALFKANA_RE = re.compile(r"[\uFF65-\uFF9F]")
# CJK 漢字
_KANJI_RE = re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF]")
# ASCII 記号・句読点
_ASCII_PUNCT_RE = re.compile(r"[!-/:-@\[-`{-~]")
# 連続する同じ文字（例: "草草草", "ｗｗｗ", "wwww"）
_REPEAT_RE = re.compile(r"(.)\1{2,}")  # 同一文字が3回以上連続


def extract_features(text: str) -> list[float]:
    """テキスト1件から手作り特徴量ベクトルを返す。

    特徴量一覧:
        0: テキスト長 (文字数)
        1: ユニーク文字種数
        2: ユニーク文字比率 (ユニーク数 / 総文字数)
        3: 絵文字の割合
        4: 全角英数字の割合
        5: 半角英字の割合
        6: 半角数字の割合
        7: ひらがなの割合
        8: カタカナ（全角）の割合
        9: 半角カタカナの割合
       10: 漢字の割合
       11: ASCII 記号の割合
       12: 連続同一文字パターン数 (wwww, 草草草 など)
       13: 空白文字の割合
       14: 大文字の割合 (半角英字中)
       15: 平均コードポイント (文字の「重さ」)
       16: テキストが1文字のみか (bool)
       17: テキストが純粋な絵文字のみか (bool)
       18: 「w」系文字の割合 (w, ｗ, W, Ｗ)
       19: 「草」文字の割合
    """
    n = len(text) if text else 1  # ゼロ除算防止
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
    spaces = text.count(" ") + text.count("\u3000")  # 半角・全角スペース

    upper_alpha = [c for c in hw_alpha if c.isupper()]
    upper_ratio = len(upper_alpha) / max(len(hw_alpha), 1)

    avg_codepoint = sum(ord(c) for c in text) / n

    only_one_char = 1.0 if length == 1 else 0.0
    non_emoji = _EMOJI_RE.sub("", text).strip()
    only_emoji = 1.0 if (emoji_chars and not non_emoji) else 0.0

    w_chars = [c for c in text if c in ("w", "ｗ", "W", "Ｗ")]
    kusa_chars = [c for c in text if c == "草"]

    return [
        float(length),                     # 0
        float(unique_chars),               # 1
        unique_chars / n,                  # 2
        len(emoji_chars) / n,              # 3
        len(fw_alnum) / n,                 # 4
        len(hw_alpha) / n,                 # 5
        len(hw_digit) / n,                 # 6
        len(hiragana) / n,                 # 7
        len(katakana) / n,                 # 8
        len(halfkana) / n,                 # 9
        len(kanji) / n,                    # 10
        len(ascii_punct) / n,              # 11
        float(repeats),                    # 12
        spaces / n,                        # 13
        upper_ratio,                       # 14
        avg_codepoint / 100000.0,          # 15 (正規化)
        only_one_char,                     # 16
        only_emoji,                        # 17
        len(w_chars) / n,                  # 18
        len(kusa_chars) / n,               # 19
    ]


def featurize(items: list[dict]) -> np.ndarray:
    return np.array([extract_features(item["body"]) for item in items])


def build_model():
    """標準化 + RBF SVM。

    手作り特徴量は単位がバラバラなため StandardScaler で正規化する。
    RBF カーネルは非線形境界を学習できる。
    C=10, gamma="scale": 少次元特徴量向けに少し C を大きめに。
    """
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", SVC(kernel="rbf", C=10.0, gamma="scale", probability=True)),
    ])


def predict(training: list[dict], test: list[dict]) -> list[dict]:
    X_train = featurize(training)
    y_train = [item["is_target"] for item in training]
    X_test = featurize(test)

    model = build_model()

    cv_scores = cross_val_score(model, X_train, y_train, cv=5, scoring="accuracy")
    print(f"  交差検証 (5-fold): {cv_scores.mean():.1%} ± {cv_scores.std():.1%}")

    # 特徴量の重要度（参考）
    print(f"  特徴量数: {X_train.shape[1]}")

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
