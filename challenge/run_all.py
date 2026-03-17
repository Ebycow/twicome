"""全ベースライン比較ランナー

同一タスクトークンで全ベースラインを実行し、Top-1 accuracy と MRR を比較する。
タスクは一度だけ取得するため、全モデルが同じ問題セットで評価される。

依存パッケージ:
    pip install requests scikit-learn
    pip install sentence-transformers  # --include sentence_bert_suite 時のみ
    pip install janome  # --include janome 時のみ

使い方:
    # 全ベースライン実行 (sentence_bert 系 / janome は除外)
    python run_all.py --login someuser --base-url http://localhost:8000/twicome

    # sentence_bert 系も含めて実行
    python run_all.py --login someuser --include sentence_bert_suite

    # 追加依存があるベースラインを全部含めて実行
    python run_all.py --login someuser --include sentence_bert_suite janome

    # 特定のベースラインのみ実行
    python run_all.py --login someuser --only tfidf svm ensemble

    # 特定のベースラインをスキップ
    python run_all.py --login someuser --skip rf gbm
"""

import argparse
import sys
import time
import traceback

import requests

# ---------------------------------------------------------------------------
# API ヘルパー
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ベースライン定義
# ---------------------------------------------------------------------------


def _make_predict(module_name: str, **kwargs):
    """モジュールの predict 関数をインポートして、共通シグネチャのラッパーを返す。"""

    def runner(training, test):
        import importlib

        mod = importlib.import_module(module_name)
        return mod.predict(training, test, **kwargs)

    return runner


BASELINES: list[tuple[str, str, callable]] = [
    # (id, 表示名, predict ラッパー)
    ("random", "ランダム予測", _make_predict("baseline_random")),
    ("tfidf", "TF-IDF + LogisticRegression", _make_predict("baseline_tfidf")),
    ("svm", "TF-IDF + LinearSVC", _make_predict("baseline_svm")),
    ("nb", "TF-IDF + ComplementNB", _make_predict("baseline_nb")),
    ("rf", "TF-IDF + RandomForest", _make_predict("baseline_rf")),
    ("gbm", "TF-IDF + GradientBoosting", _make_predict("baseline_gbm")),
    ("word_ngram", "文字+単語 n-gram + LR", _make_predict("baseline_word_ngram")),
    ("centroid", "Nearest Centroid (cosine)", _make_predict("baseline_centroid")),
    ("handcrafted", "手作り特徴量 + LinearSVC", _make_predict("baseline_handcrafted")),
    ("janome", "Janome 分かち書き + 特徴量融合 + LinearSVC", _make_predict("baseline_janome")),
    ("adaptive", "適応ブレンド", _make_predict("baseline_adaptive")),
    ("ensemble", "アンサンブル (ソフト投票)", _make_predict("baseline_ensemble")),
    # sentence_bert 系と janome はデフォルト除外 (--include ... で有効化)
    (
        "sentence_bert",
        "Sentence-BERT + LR",
        _make_predict("baseline_sentence_bert", model_name="hotchpotch/static-embedding-japanese"),
    ),
    (
        "sentence_bert_knn",
        "Sentence-BERT + top-k 近傍",
        _make_predict("baseline_sentence_bert_knn", model_name="hotchpotch/static-embedding-japanese"),
    ),
    (
        "sentence_bert_margin",
        "Sentence-BERT + target/other margin",
        _make_predict("baseline_sentence_bert_margin", model_name="hotchpotch/static-embedding-japanese"),
    ),
    (
        "sentence_bert_multiview",
        "Sentence-BERT + short-text multi-view",
        _make_predict("baseline_sentence_bert_multiview", model_name="hotchpotch/static-embedding-japanese"),
    ),
    (
        "sentence_bert_bucketed",
        "Sentence-BERT + バケット別プロトタイプ",
        _make_predict("baseline_sentence_bert_bucketed", model_name="hotchpotch/static-embedding-japanese"),
    ),
    (
        "sentence_bert_rerank",
        "Sentence-BERT + 二段階 rerank",
        _make_predict("baseline_sentence_bert_rerank", model_name="hotchpotch/static-embedding-japanese"),
    ),
    (
        "sentence_bert_contrastive",
        "Sentence-BERT + 対照学習アダプタ",
        _make_predict("baseline_sentence_bert_contrastive", model_name="hotchpotch/static-embedding-japanese"),
    ),
]

OPTIONAL_GROUPS = {
    "sentence_bert_suite": {
        "sentence_bert",
        "sentence_bert_knn",
        "sentence_bert_margin",
        "sentence_bert_multiview",
        "sentence_bert_bucketed",
        "sentence_bert_rerank",
        "sentence_bert_contrastive",
    }
}


def expand_ids(values: list[str] | None) -> set[str]:
    if not values:
        return set()

    expanded = set()
    for value in values:
        expanded |= OPTIONAL_GROUPS.get(value, {value})
    return expanded


# デフォルトで除外するベースライン
DEFAULT_EXCLUDE = OPTIONAL_GROUPS["sentence_bert_suite"] | {"janome"}


# ---------------------------------------------------------------------------
# 結果表示
# ---------------------------------------------------------------------------


def print_results(results: list[dict], total: int) -> None:
    """結果を Top-1 accuracy 降順のテーブルで表示する。"""
    if not results:
        return

    print("\n" + "=" * 75)
    print(" 精度比較結果")
    print("=" * 75)
    print(f"  {'順位':>3}  {'Top-1':>6}  {'MRR':>6}  {'Bar (Top-1)':30}  名前")
    print("-" * 75)

    ok = sorted([r for r in results if r["top1"] is not None], key=lambda r: -r["top1"])
    err = [r for r in results if r["top1"] is None]

    rank = 1
    for r in ok:
        bar_len = int(r["top1"] * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        print(f"  {rank:3d}.  {r['top1']:5.1%}  {r['mrr']:6.4f}  [{bar}]  {r['name']}  [{r['elapsed']:.1f}s]")
        rank += 1

    for r in err:
        print(f"  ---.  {'ERROR':>6}  {'--':>6}  {'':30}  {r['name']}  [{r['error']}]")

    print("=" * 75)

    if ok:
        best = ok[0]
        random_top1 = next((r["top1"] for r in ok if r["id"] == "random"), 1.0 / total)

        print(f"\n  最高 Top-1: {best['top1']:.1%}  ({best['name']})")
        print(f"  最高 MRR:   {max(r['mrr'] for r in ok):.4f}  ({max(ok, key=lambda r: r['mrr'])['name']})")
        print(f"  ランダム比 (Top-1): +{best['top1'] - random_top1:.1%}")

    print()


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="全ベースライン比較ランナー")
    parser.add_argument("--login", required=True, help="対象ユーザーの login")
    parser.add_argument("--base-url", default="http://localhost:8000/twicome")
    parser.add_argument(
        "--include",
        nargs="+",
        metavar="ID",
        help="デフォルト除外のベースライン/グループを追加する (例: sentence_bert_suite janome)",
    )
    parser.add_argument(
        "--skip",
        nargs="+",
        metavar="ID",
        help="実行しないベースラインの ID (例: rf gbm)",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="ID",
        help="指定したベースライン/グループのみ実行 (--skip/--include を上書き)",
    )
    args = parser.parse_args()

    # 実行対象を決定
    exclude = set(DEFAULT_EXCLUDE)
    if args.include:
        exclude -= expand_ids(args.include)
    if args.skip:
        exclude |= expand_ids(args.skip)

    if args.only:
        only_ids = expand_ids(args.only)
        targets = [(bid, name, fn) for bid, name, fn in BASELINES if bid in only_ids]
    else:
        targets = [(bid, name, fn) for bid, name, fn in BASELINES if bid not in exclude]

    if not targets:
        print("実行対象のベースラインがありません。--only / --skip を確認してください。")
        sys.exit(1)

    # タスクを一度だけ取得
    print(f"タスク取得中: {args.login}")
    task = fetch_task(args.base_url, args.login)
    total = task["test_count"]
    n_cand = task["candidates_per_question"]
    print(f"  学習データ: {task['train_count']} 件")
    print(f"  テスト: {total} 問 × {n_cand} 候補")
    print(f"  実行するベースライン: {len(targets)} 本\n")

    results = []

    for bid, name, predict_fn in targets:
        print(f"{'─' * 60}")
        print(f"[{bid}] {name}")
        t0 = time.perf_counter()
        try:
            answers = predict_fn(task["training"], task["test"])
            result = submit_answers(args.base_url, args.login, task["task_token"], answers)
            elapsed = time.perf_counter() - t0
            top1 = result["top1_accuracy"]
            mrr = result["mrr"]
            correct = result["correct_top1"]
            print(f"  → Top-1: {top1:.1%}  ({correct}/{total})  MRR: {mrr:.4f}  [{elapsed:.1f}s]")
            results.append(
                {
                    "id": bid,
                    "name": name,
                    "top1": top1,
                    "mrr": mrr,
                    "correct": correct,
                    "elapsed": elapsed,
                    "error": None,
                }
            )
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  → エラー: {e}", file=sys.stderr)
            traceback.print_exc()
            results.append(
                {
                    "id": bid,
                    "name": name,
                    "top1": None,
                    "mrr": None,
                    "correct": None,
                    "elapsed": elapsed,
                    "error": str(e),
                }
            )

    print_results(results, total)


if __name__ == "__main__":
    main()
