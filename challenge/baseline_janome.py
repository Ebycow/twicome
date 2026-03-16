"""Janome 分かち書き + 特徴量融合 + LinearSVC ベースライン

日本語形態素解析で分かち書きした単語・原形/品詞特徴に、
文字 n-gram と手作り特徴量を加えて分類する。
短い Twitch コメントでも「語彙」「言い回し」「書き方の癖」をまとめて捉えやすい。

依存パッケージ:
    pip install requests scikit-learn janome

使い方:
    python baseline_janome.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse
import unicodedata
from functools import lru_cache

import numpy as np
import requests
from baseline_handcrafted import extract_features
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import MaxAbsScaler
from sklearn.svm import LinearSVC

try:
    from janome.tokenizer import Tokenizer as JanomeTokenizer
except ImportError:
    JanomeTokenizer = None


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


_TOKENIZER = None
_CONTENT_POS = {"名詞", "動詞", "形容詞", "副詞"}


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    return " ".join(normalized.split())


def _get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        if JanomeTokenizer is None:
            raise RuntimeError(
                "Janome がインストールされていません。"
                " `pip install janome` してから baseline_janome.py を実行してください。"
            )
        _TOKENIZER = JanomeTokenizer()
    return _TOKENIZER


@lru_cache(maxsize=200000)
def _analyze_text(text: str) -> tuple[tuple[str, str, str], ...]:
    normalized = normalize_text(text)
    if not normalized:
        return tuple()

    tokenizer = _get_tokenizer()
    analyzed = []
    for token in tokenizer.tokenize(normalized):
        pos = token.part_of_speech.split(",")[0]
        base_form = token.base_form if token.base_form != "*" else token.surface
        analyzed.append((token.surface, base_form, pos))
    return tuple(analyzed)


def _space_join(tokens: list[str]) -> str:
    return " ".join(tokens) if tokens else "__EMPTY__"


class JanomeTextTransformer(BaseEstimator, TransformerMixin):
    """Janome の解析結果を TF-IDF 用の空白区切り文字列に変換する。"""

    def __init__(self, mode: str):
        self.mode = mode

    def fit(self, X, y=None):
        _get_tokenizer()
        return self

    def transform(self, X):
        rows = []
        for text in X:
            analyzed = _analyze_text(text)
            if self.mode == "surface":
                rows.append(_space_join([surface for surface, _, _ in analyzed]))
            elif self.mode == "lemma_pos":
                rows.append(_space_join([f"{lemma}/{pos}" for _, lemma, pos in analyzed]))
            else:
                raise ValueError(f"unknown mode: {self.mode}")
        return rows


def extract_morph_style_features(text: str) -> np.ndarray:
    normalized = normalize_text(text)
    base = np.asarray(extract_features(normalized), dtype=np.float32)
    analyzed = _analyze_text(text)

    if not analyzed:
        extra = np.zeros(9, dtype=np.float32)
        return np.concatenate([base, extra])

    surfaces = [surface for surface, _, _ in analyzed]
    lemmas = [lemma for _, lemma, _ in analyzed]
    pos_tags = [pos for _, _, pos in analyzed]

    token_count = float(len(analyzed))
    unique_lemma_ratio = len(set(lemmas)) / token_count
    avg_token_length = sum(len(surface) for surface in surfaces) / token_count
    noun_ratio = sum(pos == "名詞" for pos in pos_tags) / token_count
    verb_ratio = sum(pos == "動詞" for pos in pos_tags) / token_count
    particle_ratio = sum(pos == "助詞" for pos in pos_tags) / token_count
    symbol_ratio = sum(pos == "記号" for pos in pos_tags) / token_count
    content_ratio = sum(pos in _CONTENT_POS for pos in pos_tags) / token_count
    normalized_length = token_count / max(len(normalized), 1)

    extra = np.asarray(
        [
            token_count,
            unique_lemma_ratio,
            avg_token_length,
            noun_ratio,
            verb_ratio,
            particle_ratio,
            symbol_ratio,
            content_ratio,
            normalized_length,
        ],
        dtype=np.float32,
    )
    return np.concatenate([base, extra])


class MorphStyleFeatureTransformer(BaseEstimator, TransformerMixin):
    """分かち書き由来のスタイル特徴を疎行列として返す。"""

    def fit(self, X, y=None):
        _get_tokenizer()
        return self

    def transform(self, X):
        rows = np.asarray([extract_morph_style_features(text) for text in X], dtype=np.float32)
        return sparse.csr_matrix(rows)


def build_model() -> Pipeline:
    """分かち書き特徴 + 文字 n-gram + 手作り特徴量を結合した SVM。"""
    return Pipeline(
        [
            (
                "features",
                FeatureUnion(
                    [
                        (
                            "char",
                            TfidfVectorizer(
                                analyzer="char_wb",
                                preprocessor=normalize_text,
                                ngram_range=(2, 5),
                                min_df=1,
                                sublinear_tf=True,
                            ),
                        ),
                        (
                            "surface",
                            Pipeline(
                                [
                                    ("tokenize", JanomeTextTransformer(mode="surface")),
                                    (
                                        "tfidf",
                                        TfidfVectorizer(
                                            tokenizer=str.split,
                                            token_pattern=None,
                                            lowercase=False,
                                            ngram_range=(1, 2),
                                            min_df=1,
                                            sublinear_tf=True,
                                        ),
                                    ),
                                ]
                            ),
                        ),
                        (
                            "lemma_pos",
                            Pipeline(
                                [
                                    ("tokenize", JanomeTextTransformer(mode="lemma_pos")),
                                    (
                                        "tfidf",
                                        TfidfVectorizer(
                                            tokenizer=str.split,
                                            token_pattern=None,
                                            lowercase=False,
                                            ngram_range=(1, 2),
                                            min_df=1,
                                            sublinear_tf=True,
                                        ),
                                    ),
                                ]
                            ),
                        ),
                        (
                            "style",
                            Pipeline(
                                [
                                    ("extract", MorphStyleFeatureTransformer()),
                                    ("scale", MaxAbsScaler()),
                                ]
                            ),
                        ),
                    ]
                ),
            ),
            ("clf", LinearSVC(C=0.6, class_weight="balanced", max_iter=5000)),
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
