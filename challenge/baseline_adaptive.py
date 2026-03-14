"""適応ブレンド + 擬似ラベル自己学習ベースライン

学習データ上の交差検証で複数候補モデルを比較し、良いモデルだけを重み付きでブレンドする。
その後、高信頼なテスト予測を少量だけ擬似ラベルとして学習に加えて再学習し、
固定の単一モデルより安定して高めの精度を狙う。

依存パッケージ:
    pip install requests scikit-learn

使い方:
    python baseline_adaptive.py --login someuser --base-url http://localhost:8000/twicome
"""

import argparse
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
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
    cross_val_score,
)
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import MaxAbsScaler
from sklearn.svm import LinearSVC

TRAIN_COUNT = 200
TEST_COUNT = 100
RANDOM_STATE = 42
CV = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
PSEUDO_LABEL_ROUNDS = [
    (0.97, 8),
    (0.93, 6),
]


def fetch_task(base_url: str, login: str) -> dict:
    """評価用タスクを取得する。"""
    url = f"{base_url}/api/u/{login}/quiz/task"
    resp = requests.get(url, params={"train_count": TRAIN_COUNT, "test_count": TEST_COUNT})
    resp.raise_for_status()
    return resp.json()


def submit_answers(base_url: str, login: str, task_token: str, answers: list[dict]) -> dict:
    """予測結果を提出して採点を受ける。"""
    url = f"{base_url}/api/u/{login}/quiz/task/submit"
    resp = requests.post(url, json={"task_token": task_token, "answers": answers})
    resp.raise_for_status()
    return resp.json()


def normalize_text(text: str) -> str:
    """表記ゆれを少しだけ潰した軽量正規化。"""
    normalized = unicodedata.normalize("NFKC", text or "")
    return " ".join(normalized.split())


def whitespace_tokenize(text: str) -> list[str]:
    """Twitch スタンプ名のような空白区切りトークンをそのまま使う。"""
    return normalize_text(text).split()


class HandcraftedFeatureTransformer(BaseEstimator, TransformerMixin):
    """既存の手作り特徴量を sparse 化して TF-IDF 系特徴と結合する。"""

    def fit(self, X, y=None):
        """scikit-learn の fit シグネチャに合わせる。"""
        return self

    def transform(self, X):
        """手作り特徴量を CSR 行列にする。"""
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
    """広めの文字 n-gram を使う SVM 候補。"""
    return Pipeline([
        ("tfidf", _char_wb_tfidf(ngram_range=(1, 5))),
        ("clf", CalibratedClassifierCV(
            estimator=LinearSVC(C=0.7, max_iter=5000),
            cv=3,
            method="sigmoid",
        )),
    ])


def build_dual_char_lr() -> Pipeline:
    """生文字と正規化文字を両方見る LR 候補。"""
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
    """文字特徴と空白トークン特徴を混ぜる LR 候補。"""
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
    """軽量で安定しやすい NB 候補。"""
    return Pipeline([
        ("tfidf", _char_wb_tfidf(ngram_range=(1, 4), preprocessor=normalize_text)),
        ("scaler", MaxAbsScaler()),
        ("clf", ComplementNB(alpha=0.15)),
    ])


def build_style_hybrid_lr() -> Pipeline:
    """手作り特徴量で話し方の癖も拾う LR 候補。"""
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
    ("char_svm", "広め文字 n-gram + LinearSVC", build_char_svm),
    ("dual_char_lr", "生文字+正規化文字 + LR", build_dual_char_lr),
    ("token_mix_lr", "文字+空白トークン + LR", build_token_mix_lr),
    ("char_nb", "正規化文字 + ComplementNB", build_char_nb),
    ("style_hybrid_lr", "文字+手作り特徴量 + LR", build_style_hybrid_lr),
]


def evaluate_candidates(X_train: list[str], y_train: list[bool]) -> list[dict]:
    """候補モデルを CV で採点し、スコア順に並べる。"""
    results = []
    print("  候補モデルの交差検証:")
    for model_id, name, builder in CANDIDATES:
        scores = cross_val_score(builder(), X_train, y_train, cv=CV, scoring="accuracy")
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
    """ベスト付近のモデルだけを残し、CV に応じて重みを付ける。"""
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
    """選ばれたモデル群をフル学習データで学習する。"""
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


def blend_probabilities(fitted_models: list[dict], X: list[str]) -> np.ndarray:
    """各モデルの確率を重み付き平均する。"""
    probabilities = np.zeros(len(X), dtype=np.float64)
    for model in fitted_models:
        probabilities += model["weight"] * model["model"].predict_proba(X)[:, 1]
    return probabilities


def select_threshold(selected_models: list[dict], X_train: list[str], y_train: list[bool]) -> tuple[float, float]:
    """OOF 予測から最適なしきい値を選ぶ。"""
    blended_oof = np.zeros(len(X_train), dtype=np.float64)
    y_array = np.asarray(y_train, dtype=bool)

    for model in selected_models:
        probabilities = cross_val_predict(
            model["builder"](),
            X_train,
            y_train,
            cv=CV,
            method="predict_proba",
        )[:, 1]
        blended_oof += model["weight"] * probabilities

    best_threshold = 0.5
    best_accuracy = 0.0
    for threshold in np.linspace(0.35, 0.65, 31):
        accuracy = float(((blended_oof >= threshold) == y_array).mean())
        current_distance = abs(threshold - 0.5)
        best_distance = abs(best_threshold - 0.5)
        if accuracy > best_accuracy or (accuracy == best_accuracy and current_distance < best_distance):
            best_threshold = float(threshold)
            best_accuracy = accuracy

    print(f"  しきい値最適化: {best_threshold:.2f} (OOF accuracy {best_accuracy:.1%})")
    return best_threshold, best_accuracy


def pick_pseudo_labels(
    remaining_indices: list[int],
    probabilities: np.ndarray,
    threshold: float,
    max_per_class: int,
) -> list[tuple[int, bool, float]]:
    """高信頼な正例・負例を少量ずつ選ぶ。"""
    positive = sorted(
        [
            (index, True, float(probability))
            for index, probability in zip(remaining_indices, probabilities, strict=True)
            if probability >= threshold
        ],
        key=lambda item: item[2],
        reverse=True,
    )[:max_per_class]
    negative = sorted(
        [
            (index, False, float(probability))
            for index, probability in zip(remaining_indices, probabilities, strict=True)
            if probability <= 1.0 - threshold
        ],
        key=lambda item: item[2],
    )[:max_per_class]
    return positive + negative


def self_train(
    selected_models: list[dict],
    X_train: list[str],
    y_train: list[bool],
    X_test: list[str],
) -> tuple[list[dict], int]:
    """擬似ラベルを少しずつ足して再学習する。"""
    augmented_X = list(X_train)
    augmented_y = list(y_train)
    remaining_indices = list(range(len(X_test)))
    pseudo_labeled = 0

    for round_index, (threshold, max_per_class) in enumerate(PSEUDO_LABEL_ROUNDS, start=1):
        if not remaining_indices:
            break

        fitted_models = fit_models(selected_models, augmented_X, augmented_y)
        remaining_texts = [X_test[index] for index in remaining_indices]
        probabilities = blend_probabilities(fitted_models, remaining_texts)
        picked = pick_pseudo_labels(remaining_indices, probabilities, threshold, max_per_class)

        if not picked:
            print(f"  擬似ラベル round {round_index}: 追加なし (threshold={threshold:.2f})")
            continue

        picked_indices = {index for index, _, _ in picked}
        positives = sum(1 for _, label, _ in picked if label)
        negatives = len(picked) - positives
        pseudo_labeled += len(picked)

        for index, label, _ in picked:
            augmented_X.append(X_test[index])
            augmented_y.append(label)

        remaining_indices = [index for index in remaining_indices if index not in picked_indices]
        print(
            "  擬似ラベル round "
            f"{round_index}: +{len(picked)} 件 (pos {positives} / neg {negatives}, threshold={threshold:.2f})"
        )

    return fit_models(selected_models, augmented_X, augmented_y), pseudo_labeled


def predict(training: list[dict], test: list[dict]) -> list[dict]:
    """学習データからテスト予測を作る。"""
    X_train = [item["body"] for item in training]
    y_train = [item["is_target"] for item in training]
    X_test = [item["body"] for item in test]

    scored_models = evaluate_candidates(X_train, y_train)
    selected_models = select_models(scored_models)
    threshold, _ = select_threshold(selected_models, X_train, y_train)
    fitted_models, pseudo_labeled = self_train(selected_models, X_train, y_train, X_test)

    final_probabilities = blend_probabilities(fitted_models, X_test)
    y_pred = final_probabilities >= threshold

    mean_cv = np.mean([model["cv_mean"] for model in selected_models])
    print(f"  採用モデル平均CV: {mean_cv:.1%}")
    print(f"  擬似ラベル総数: {pseudo_labeled} 件")
    confident = np.sum((final_probabilities >= 0.9) | (final_probabilities <= 0.1))
    print(f"  高信頼予測数 (>=0.9 or <=0.1): {confident} 件")

    return [
        {"id": item["id"], "prediction": bool(pred)}
        for item, pred in zip(test, y_pred, strict=True)
    ]


def main():
    """CLI エントリーポイント。"""
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

    print("\n--- 結果 ---")
    print(f"正答率: {result['accuracy']:.1%}  ({result['correct']} / {result['total']})")

    false_positives = [d for d in result["details"] if d["prediction"] and not d["actual"]]
    false_negatives = [d for d in result["details"] if not d["prediction"] and d["actual"]]
    print(f"偽陽性 (別人→本人と判定): {len(false_positives)} 件")
    print(f"偽陰性 (本人→別人と判定): {len(false_negatives)} 件")


if __name__ == "__main__":
    main()
