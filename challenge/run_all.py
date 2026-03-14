"""全ベースライン比較ランナー

同一タスクトークンで全ベースラインを実行し、精度を比較する。
タスクは一度だけ取得するため、全モデルが同じ問題セットで評価される。

依存パッケージ:
    pip install requests scikit-learn
    pip install sentence-transformers  # --include sentence_bert 時のみ

使い方:
    # 全ベースライン実行 (sentence_bert は除外)
    python run_all.py --login someuser --base-url http://localhost:8000/twicome

    # sentence_bert も含めて実行
    python run_all.py --login someuser --include sentence_bert

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

TRAIN_COUNT = 1000
TEST_COUNT = 500


# ---------------------------------------------------------------------------
# API ヘルパー
# ---------------------------------------------------------------------------

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
    ("random",        "ランダム予測",                   _make_predict("baseline_random")),
    ("tfidf",         "TF-IDF + LogisticRegression",   _make_predict("baseline_tfidf")),
    ("svm",           "TF-IDF + LinearSVC",             _make_predict("baseline_svm")),
    ("nb",            "TF-IDF + ComplementNB",          _make_predict("baseline_nb")),
    ("rf",            "TF-IDF + RandomForest",          _make_predict("baseline_rf")),
    ("gbm",           "TF-IDF + GradientBoosting",     _make_predict("baseline_gbm")),
    ("word_ngram",    "文字+単語 n-gram + LR",           _make_predict("baseline_word_ngram")),
    ("centroid",      "Nearest Centroid",               _make_predict("baseline_centroid")),
    ("handcrafted",   "手作り特徴量 + RBF SVM",          _make_predict("baseline_handcrafted")),
    ("adaptive",      "適応ブレンド + 擬似ラベル",        _make_predict("baseline_adaptive")),
    ("ensemble",      "アンサンブル (ソフト投票)",         _make_predict("baseline_ensemble")),
    # sentence_bert はデフォルト除外 (--include sentence_bert で有効化)
    ("sentence_bert", "Sentence-BERT + LR",            _make_predict("baseline_sentence_bert",
                                                                      model_name="hotchpotch/static-embedding-japanese")),
]

# デフォルトで除外するベースライン
DEFAULT_EXCLUDE = {"sentence_bert"}


# ---------------------------------------------------------------------------
# 結果表示
# ---------------------------------------------------------------------------

def print_results(results: list[dict], total: int) -> None:
    """結果を精度順のテーブルで表示する。"""
    if not results:
        return

    print("\n" + "=" * 65)
    print(" 精度比較結果")
    print("=" * 65)

    # 精度降順でソート（エラーは末尾）
    ok = sorted([r for r in results if r["accuracy"] is not None], key=lambda r: -r["accuracy"])
    err = [r for r in results if r["accuracy"] is None]

    rank = 1
    for r in ok:
        bar_len = int(r["accuracy"] * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        print(
            f"  {rank:2d}. [{bar}] {r['accuracy']:5.1%}"
            f"  ({r['correct']:3d}/{total})  {r['name']}"
            f"  [{r['elapsed']:.1f}s]"
        )
        rank += 1

    for r in err:
        print(f"  --. {'ERROR':>36}  {r['name']}  [{r['error']}]")

    print("=" * 65)

    if ok:
        best = ok[0]
        random_acc = next((r["accuracy"] for r in ok if r["id"] == "random"), 0.5)
        print(f"\n  最高スコア: {best['accuracy']:.1%}  ({best['name']})")
        print(f"  ランダム比: +{best['accuracy'] - random_acc:.1%}")

    print()


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="全ベースライン比較ランナー")
    parser.add_argument("--login", required=True, help="対象ユーザーの login")
    parser.add_argument("--base-url", default="http://localhost:8000/twicome")
    parser.add_argument(
        "--include", nargs="+", metavar="ID",
        help="デフォルト除外のベースラインを追加する (例: sentence_bert)",
    )
    parser.add_argument(
        "--skip", nargs="+", metavar="ID",
        help="実行しないベースラインの ID (例: rf gbm)",
    )
    parser.add_argument(
        "--only", nargs="+", metavar="ID",
        help="指定したベースラインのみ実行 (--skip/--include を上書き)",
    )
    args = parser.parse_args()

    # 実行対象を決定
    exclude = set(DEFAULT_EXCLUDE)
    if args.include:
        exclude -= set(args.include)
    if args.skip:
        exclude |= set(args.skip)

    if args.only:
        targets = [(bid, name, fn) for bid, name, fn in BASELINES if bid in args.only]
    else:
        targets = [(bid, name, fn) for bid, name, fn in BASELINES if bid not in exclude]

    if not targets:
        print("実行対象のベースラインがありません。--only / --skip を確認してください。")
        sys.exit(1)

    # タスクを一度だけ取得
    print(f"タスク取得中: {args.login}")
    task = fetch_task(args.base_url, args.login)
    total = task["test_count"]
    print(f"  学習データ: {task['train_count']} 件, テストデータ: {total} 件")
    print(f"  実行するベースライン: {len(targets)} 本\n")

    results = []

    for bid, name, predict_fn in targets:
        print(f"{'─' * 55}")
        print(f"[{bid}] {name}")
        t0 = time.perf_counter()
        try:
            answers = predict_fn(task["training"], task["test"])
            result = submit_answers(args.base_url, args.login, task["task_token"], answers)
            elapsed = time.perf_counter() - t0
            acc = result["accuracy"]
            correct = result["correct"]
            print(f"  → 正答率: {acc:.1%}  ({correct}/{total})  [{elapsed:.1f}s]")
            results.append({
                "id": bid, "name": name,
                "accuracy": acc, "correct": correct,
                "elapsed": elapsed, "error": None,
            })
        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"  → エラー: {e}", file=sys.stderr)
            traceback.print_exc()
            results.append({
                "id": bid, "name": name,
                "accuracy": None, "correct": None,
                "elapsed": elapsed, "error": str(e),
            })

    print_results(results, total)


if __name__ == "__main__":
    main()
