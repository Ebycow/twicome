"""適応ブレンド ベースライン

学習データ上の交差検証で複数候補モデルを比較し、良いモデルだけを重み付きでブレンドする。
擬似ラベル自己学習はランキング形式と相性が悪いため省いた。
CV はサブサンプリング（最大 _MAX_CV_SAMPLES 件）で高速化する。

依存パッケージ:
    pip install requests scikit-learn

使い方:
    python baseline_adaptive.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse
import random
import unicodedata
from collections.abc import Callable

import numpy as np
import requests
from baseline_handcrafted import extract_features
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import MaxAbsScaler
from sklearn.svm import LinearSVC

RANDOM_STATE = 42
_MAX_CV_SAMPLES = 5000  # CV 用サブサンプリング上限（100k 規模で CV が重くなるのを防ぐ）
CV = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)


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


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    return " ".join(normalized.split())


def whitespace_tokenize(text: str) -> list[str]:
    return normalize_text(text).split()


class HandcraftedFeatureTransformer(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = np.asarray([extract_features(text) for text in X], dtype=np.float32)
        return sparse.csr_matrix(rows)


def _char_wb_tfidf(*, ngram_range=(1, 5), preprocessor=None) -> TfidfVectorizer:
    return TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=ngram_range,
        min_df=1,
        sublinear_tf=True,
        preprocessor=preprocessor,
    )


def _char_tfidf(*, ngram_range=(2, 6), preprocessor=None) -> TfidfVectorizer:
    return TfidfVectorizer(
        analyzer="char",
        ngram_range=ngram_range,
        min_df=1,
        sublinear_tf=True,
        preprocessor=preprocessor,
    )


def _word_tfidf() -> TfidfVectorizer:
    return TfidfVectorizer(
        analyzer="word",
        tokenizer=whitespace_tokenize,
        token_pattern=None,
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
        lowercase=False,
    )


def build_char_svm() -> Pipeline:
    return Pipeline([
        ("tfidf", _char_wb_tfidf(ngram_range=(1, 5))),
        ("clf", CalibratedClassifierCV(
            estimator=LinearSVC(C=0.7, max_iter=5000),
            cv=3,
            method="sigmoid",
        )),
    ])


def build_dual_char_lr() -> Pipeline:
    return Pipeline([
        ("features", FeatureUnion([
            ("raw_char_wb", _char_wb_tfidf(ngram_range=(1, 5))),
            ("norm_char", _char_tfidf(ngram_range=(2, 6), preprocessor=normalize_text)),
        ])),
        ("clf", LogisticRegression(
            max_iter=2000,
            C=3.0,
            solver="liblinear",
            random_state=RANDOM_STATE,
        )),
    ])


def build_token_mix_lr() -> Pipeline:
    return Pipeline([
        ("features", FeatureUnion([
            ("char", _char_tfidf(ngram_range=(2, 5))),
            ("char_norm", _char_wb_tfidf(ngram_range=(2, 5), preprocessor=normalize_text)),
            ("word", _word_tfidf()),
        ])),
        ("clf", LogisticRegression(
            max_iter=2000,
            C=2.0,
            solver="liblinear",
            random_state=RANDOM_STATE,
        )),
    ])


def build_char_nb() -> Pipeline:
    return Pipeline([
        ("tfidf", _char_wb_tfidf(ngram_range=(1, 4), preprocessor=normalize_text)),
        ("scaler", MaxAbsScaler()),
        ("clf", ComplementNB(alpha=0.15)),
    ])


def build_style_hybrid_lr() -> Pipeline:
    return Pipeline([
        ("features", FeatureUnion([
            ("char", _char_tfidf(ngram_range=(2, 5))),
            ("style", Pipeline([
                ("extract", HandcraftedFeatureTransformer()),
                ("scale", MaxAbsScaler()),
            ])),
        ])),
        ("clf", LogisticRegression(
            max_iter=2000,
            C=2.5,
            solver="liblinear",
            random_state=RANDOM_STATE,
        )),
    ])


CANDIDATES: list[tuple[str, str, Callable[[], Pipeline]]] = [
    ("char_svm",       "広め文字 n-gram + LinearSVC",    build_char_svm),
    ("dual_char_lr",   "生文字+正規化文字 + LR",          build_dual_char_lr),
    ("token_mix_lr",   "文字+空白トークン + LR",           build_token_mix_lr),
    ("char_nb",        "正規化文字 + ComplementNB",        build_char_nb),
    ("style_hybrid_lr","文字+手作り特徴量 + LR",           build_style_hybrid_lr),
]


def _subsample(X: list[str], y: list[bool], n: int) -> tuple[list[str], list[bool]]:
    """CV 用サブサンプリング。クラス比を維持しながら最大 n 件に絞る。"""
    if len(X) <= n:
        return X, y
    idx = random.sample(range(len(X)), n)
    return [X[i] for i in idx], [y[i] for i in idx]


def evaluate_candidates(X_train: list[str], y_train: list[bool]) -> list[dict]:
    """サブサンプリング + CV で各候補モデルを採点し、スコア順に返す。"""
    X_cv, y_cv = _subsample(X_train, y_train, _MAX_CV_SAMPLES)
    print(f"  候補モデルの交差検証 ({len(X_cv)} 件でサブサンプリング):")
    results = []
    for model_id, name, builder in CANDIDATES:
        scores = cross_val_score(builder(), X_cv, y_cv, cv=CV, scoring="accuracy")
        result = {
            "id": model_id,
            "name": name,
            "builder": builder,
            "cv_mean": float(scores.mean()),
            "cv_std": float(scores.std()),
        }
        results.append(result)
        print(f"    - {name}: {result['cv_mean']:.1%} ± {result['cv_std']:.1%}")
    return sorted(results, key=lambda item: item["cv_mean"], reverse=True)


def select_models(scored_models: list[dict]) -> list[dict]:
    """ベスト付近のモデルだけを残し、CV スコアに応じて重みを付ける。"""
    best_score = scored_models[0]["cv_mean"]
    selected = [m.copy() for m in scored_models if m["cv_mean"] >= best_score - 0.025][:4]
    if len(selected) < 2:
        selected = [m.copy() for m in scored_models[:2]]

    raw_weights = np.array(
        [max(model["cv_mean"] - 0.45, 0.02) ** 2 for model in selected],
        dtype=np.float64,
    )
    raw_weights /= raw_weights.sum()

    print("  採用モデル:")
    for model, weight in zip(selected, raw_weights, strict=True):
        model["weight"] = float(weight)
        print(f"    - {model['name']}: 重み {model['weight']:.2f}")
    return selected


def fit_models(selected_models: list[dict], X_train: list[str], y_train: list[bool]) -> list[dict]:
    fitted_models = []
    for model in selected_models:
        fitted = model["builder"]()
        fitted.fit(X_train, y_train)
        fitted_models.append({
            "id": model["id"],
            "name": model["name"],
            "weight": model["weight"],
            "model": fitted,
        })
    return fitted_models


def blend_scores(fitted_models: list[dict], X: list[str]) -> np.ndarray:
    """各モデルのスコア（predict_proba の is_target 列）を重み付き平均する。"""
    scores = np.zeros(len(X), dtype=np.float64)
    for m in fitted_models:
        scores += m["weight"] * m["model"].predict_proba(X)[:, 1]
    return scores


def predict(training: list[dict], test: list[dict]) -> list[dict]:
    X_train = [item["body"] for item in training]
    y_train = [item["is_target"] for item in training]

    scored_models = evaluate_candidates(X_train, y_train)
    selected_models = select_models(scored_models)
    fitted_models = fit_models(selected_models, X_train, y_train)

    answers = []
    for question in test:
        candidates = question["candidates"]
        X_q = [c["body"] for c in candidates]
        scores = blend_scores(fitted_models, X_q)
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

    print("\n--- 結果 ---")
    print(f"Top-1 accuracy: {result['top1_accuracy']:.1%}  ({result['correct_top1']} / {result['total']})")
    print(f"MRR:            {result['mrr']:.4f}")


if __name__ == "__main__":
    main()
