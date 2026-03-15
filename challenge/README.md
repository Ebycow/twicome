# 🎉 Twicome Quiz Challenge "Who Wrote This?"🎉

Twitch コメントの書き手を当てるバイナリ分類タスクです。
このディレクトリには、タスク API を使ったサンプルコードが含まれています。

---

## タスクの概要

ある Twitch ユーザー（以下「対象ユーザー」）のコメント履歴を学習データとして受け取り、
テストセットの各コメントが「対象ユーザー本人」か「別ユーザー」かを判定する **バイナリ分類** タスクです。

| 項目       | 内容                                                   |
|----------|------------------------------------------------------|
| 入力       | コメント本文テキスト（1 件ずつ）                         |
| 出力       | `true`（本人）または `false`（別人）                    |
| 評価指標   | テストセットの正答率 (accuracy)                          |
| 学習件数   | **200 件**（本人 100 件 + 別人 100 件）※最大 1000 件まで指定可 |
| テスト件数 | **100 件**（本人 50 件 + 別人 50 件）※最大 500 件まで指定可   |
| クラス比   | 常に **1:1**（ランダム予測の期待正答率は 50%）           |

> **件数について**: これらの値はサーバーが許容する上限です。
> 対象ユーザーのコメント数が DB に不足する場合、実際の件数が少なくなることがあります。
> レスポンスの `train_count` / `test_count` フィールドで実際の件数を確認してください。

---

## API 仕様

### ベース URL

```
http://<host>:<port>/twicome
```

---

### タスク取得

```
GET /api/u/{login}/quiz/task
```

#### パスパラメータ

| パラメータ | 説明                           |
|---------|------------------------------|
| `login` | 対象ユーザーの Twitch ログイン名 |

#### クエリパラメータ

| パラメータ     | 推奨値 | 範囲        | 説明                   |
|-------------|------|-----------|----------------------|
| `train_count` | 200  | 10〜1000  | 学習データ件数             |
| `test_count`  | 100  | 5〜500    | テストデータ件数            |
| `platform`    | twitch | —       | プラットフォーム（変更不要）  |

> サンプルコードは `train_count=200, test_count=100` を固定で使用しています。
> より多くのデータを使いたい場合は `train_count=1000, test_count=500` まで指定できます。
> ただし対象ユーザーの DB コメント数が不足する場合は実際の件数が少なくなります。

#### レスポンス

```json
{
  "task_token": "eyJsb2dpbiI6...",
  "target_login": "someuser",
  "train_count": 200,
  "test_count": 100,
  "training": [
    {"body": "草", "is_target": true},
    {"body": "それな", "is_target": false},
    ...
  ],
  "test": [
    {"id": 0, "body": "えぐい"},
    {"id": 1, "body": "ｗｗｗ"},
    ...
  ]
}
```

#### フィールド説明

| フィールド       | 型              | 説明                                                                 |
|--------------|---------------|-------------------------------------------------------------------|
| `task_token` | string        | 採点に必要な署名済みトークン。再取得するたびに異なる値になる               |
| `target_login` | string      | 対象ユーザーの login                                                  |
| `train_count` | int          | 実際の学習データ件数（DB 不足時は要求値より少ない場合がある）            |
| `test_count`  | int          | 実際のテストデータ件数（同上）                                          |
| `training`    | array        | ラベル付き学習データ。順序はランダム                                     |
| `training[].body` | string   | コメント本文                                                         |
| `training[].is_target` | bool | `true` = 本人、`false` = 別ユーザー                            |
| `test`        | array        | ラベルなしテストデータ。順序はランダム                                   |
| `test[].id`   | int          | 0 始まりの連番。提出時に使う                                           |
| `test[].body` | string       | コメント本文                                                         |

---

### 予測提出・採点

```
POST /api/u/{login}/quiz/task/submit
Content-Type: application/json
```

#### リクエストボディ

```json
{
  "task_token": "eyJsb2dpbiI6...",
  "answers": [
    {"id": 0, "prediction": true},
    {"id": 1, "prediction": false},
    ...
  ]
}
```

| フィールド             | 型     | 説明                                    |
|---------------------|------|---------------------------------------|
| `task_token`        | string | タスク取得時のトークン                    |
| `answers`           | array  | テスト全件分の予測。件数が不足するとエラー  |
| `answers[].id`      | int    | `test[].id` に対応する ID               |
| `answers[].prediction` | bool | 予測結果                              |

#### レスポンス

```json
{
  "accuracy": 0.72,
  "correct": 72,
  "total": 100,
  "details": [
    {"id": 0, "prediction": true,  "actual": true,  "correct": true},
    {"id": 1, "prediction": false, "actual": true,  "correct": false},
    ...
  ]
}
```

| フィールド          | 型     | 説明                             |
|------------------|------|--------------------------------|
| `accuracy`       | float  | 正答率（0.0〜1.0）               |
| `correct`        | int    | 正解件数                         |
| `total`          | int    | テストデータ総件数                 |
| `details`        | array  | 各 ID の予測・正解・正誤           |

#### エラーレスポンス

| HTTP ステータス | `error` 値                  | 説明                            |
|------------|---------------------------|-------------------------------|
| 400        | `invalid_token`            | トークンが不正または期限切れ          |
| 400        | `missing_answer_for_id_N`  | ID=N の予測が含まれていない          |
| 404        | `user_not_found`           | 対象ユーザーが存在しない             |

---

## 公式ルール

1. **使ってよいもの**: 学習データ (`training`) のみ。テストデータの本文はそのまま特徴量に使える
2. **使ってはいけないもの**: サーバーの検索・推薦 API（`/api/u/{login}/search` など）への問い合わせ。学習データとテストデータ以外の外部情報収集
3. **外部データ**: 事前学習済みの言語モデルや一般公開の辞書・コーパスの利用は**可**
4. **再提出**: 同一トークンへの再提出は何度でも可能。異なるアプローチのスコアを手元で比較するために使える
5. **トークンの扱い**: `task_token` は HMAC-SHA256 で署名されており、クライアント側から正解ラベルを逆算することはできない

> **ルール 2 の意図**: `/search` エンドポイントはサーバー上のベクトルインデックスを参照します。
> これを使うとサーバーが持つ追加情報（学習データ外のコメント）に間接的にアクセスすることになり、
> タスクの問題設定と公平性が崩れます。

---

## セットアップ

### 依存パッケージの一括インストール

```bash
cd challenge

# 仮想環境を作成 (推奨)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 必須パッケージ (全ベースライン共通)
pip install requests scikit-learn

# baseline_sentence_bert.py を使う場合のみ追加
pip install sentence-transformers
```

または `requirements.txt` から一括インストール:

```bash
pip install -r requirements.txt
# sentence-transformers が必要な場合はコメントを外してから実行
```

---

## サンプルコード

### run_all.py — 全ベースライン比較

同一タスクで全ベースラインを一括実行し、精度を表で比較します。
**スコアを公平に比較するため、全モデルに同じ問題セットが使われます。**

```bash
# 全ベースラインを実行 (sentence_bert 以外)
python run_all.py --login someuser --base-url http://localhost:8000/twicome

# sentence_bert も含めて実行
python run_all.py --login someuser --include sentence_bert

# 特定のベースラインのみ実行
python run_all.py --login someuser --only adaptive svm ensemble

# 特定のベースラインをスキップ
python run_all.py --login someuser --skip rf gbm
```

出力例:

```
=================================================================
 精度比較結果
=================================================================
   1. [████████████████████████░░░░░░] 80.0%  ( 80/100)  アンサンブル (ソフト投票)  [3.2s]
   2. [███████████████████████░░░░░░░] 76.0%  ( 76/100)  TF-IDF + LinearSVC  [1.8s]
   3. [██████████████████████░░░░░░░░] 74.0%  ( 74/100)  TF-IDF + LogisticRegression  [1.1s]
  ...
  10. [███████████████░░░░░░░░░░░░░░░] 50.0%  ( 50/100)  ランダム予測  [0.0s]
=================================================================

  最高スコア: 80.0%  (アンサンブル (ソフト投票))
  ランダム比: +30.0%
```

---

### 個別実行

各ベースラインは単独でも実行できます。

#### baseline_random.py — ランダム予測

API フローの最小実装。予測ロジックを差し替えるためのスケルトンとして使えます。
期待正答率: **50%**

```bash
python baseline_random.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_tfidf.py — TF-IDF + ロジスティック回帰

文字 n-gram (1〜3文字) を特徴量として TF-IDF ベクトル化し、ロジスティック回帰で分類します。

```bash
python baseline_tfidf.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_svm.py — TF-IDF + LinearSVC

高次元スパース特徴量に強い SVM。テキスト分類の定番手法。

```bash
python baseline_svm.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_nb.py — TF-IDF + Naive Bayes

ComplementNB による超軽量な分類。短テキスト向けに調整済み。

```bash
python baseline_nb.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_rf.py — TF-IDF + Random Forest

決定木のアンサンブルで非線形な特徴の組み合わせを捉えます。

```bash
python baseline_rf.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_gbm.py — TF-IDF + Gradient Boosting

HistGradientBoostingClassifier (sklearn の高速 GBM)。
TF-IDF を dense に変換してから学習します。

```bash
python baseline_gbm.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_word_ngram.py — 文字 + 単語 n-gram TF-IDF

文字 n-gram と単語 n-gram を結合した特徴量 + LR。スタンプ名の共起を捉えます。

```bash
python baseline_word_ngram.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_centroid.py — Nearest Centroid

各クラスの TF-IDF ベクトル重心に最も近い側に分類するプロトタイプ法。パラメータほぼゼロ。
現行 sklearn に合わせて euclidean 距離を使用します。

```bash
python baseline_centroid.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_handcrafted.py — 手作り特徴量 + RBF SVM

絵文字率・ひらがな率・wwww率など Twitch チャット特化の 20 次元特徴量 + SVM。

```bash
python baseline_handcrafted.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_ensemble.py — アンサンブル (ソフト投票)

LR・SVM・NB・単語 n-gram の 4 モデルを重み付きソフト投票で統合します。

```bash
python baseline_ensemble.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_adaptive.py — 適応ブレンド + 擬似ラベル

学習データ上の交差検証で複数候補モデルを比較し、そのタスクに合うモデルだけを重み付きで統合します。
さらに README のルール 1 に沿ってテスト本文を無ラベル特徴として扱い、高信頼予測だけを擬似ラベルとして少量追加して再学習します。
固定の単一モデルより伸びやすいので、まず試す本命ベースラインです。

```bash
python baseline_adaptive.py --login someuser --base-url http://localhost:8000/twicome
```

#### baseline_sentence_bert.py — Sentence-BERT + LR

事前学習済み日本語モデルで埋め込み後、LR で分類 (freeze + probe)。
デフォルトモデル: `hotchpotch/static-embedding-japanese`（GPU 不要）

```bash
pip install sentence-transformers
python baseline_sentence_bert.py --login someuser --base-url http://localhost:8000/twicome

# 別のモデルを使う場合
python baseline_sentence_bert.py --login someuser --model cl-tohoku/bert-base-japanese-char-v3
```

---

## 実装のヒント

### データの特性

- コメントは Twitch チャット由来のため **非常に短い**（絵文字・スタンプ・草・ｗ 系が多い）
- 1 ユーザーの語彙・スタイルは比較的一貫している（同じスタンプを繰り返す、特定の言い回しを使うなど）
- 学習データは均等な 1:1 クラス比。クラス不均衡の処理は不要

### 特徴量のアイデア

| アプローチ             | 説明                                                       |
|--------------------|----------------------------------------------------------|
| 文字 n-gram           | 1〜3 文字の組み合わせ。日本語の形態素解析なしで使える       |
| 単語 n-gram           | スペース・句読点でトークナイズ。スタンプ名の一致に有効       |
| 文字種の比率           | 全角英数・半角・絵文字・ひらがな・カタカナの割合             |
| 文字長                 | コメント全体の長さ                                          |
| 事前学習モデル          | sentence-transformers 等で埋め込みベクトル化              |

### NN を使う場合

200 件の学習データは NN にとって小規模です。以下の戦略が有効です:

- **事前学習モデルの fine-tuning**: `cl-tohoku/bert-base-japanese-char` 等を使い、分類層のみ学習
- **freeze + プローブ**: モデル全体を凍結し、埋め込みを固定特徴量として使う（データが少ないほど有効）
- **データ拡張**: 文字の置換・削除・順序入れ替えなど

---

## 注意事項

- `task_token` はサーバーが `QUIZ_SECRET_KEY` 環境変数で設定した秘密鍵で署名されます。
  この変数が未設定の場合はランダム生成されるため、**サーバー再起動でトークンが無効**になります。
  セルフホストする場合は `.env` に `QUIZ_SECRET_KEY` を固定値で設定してください
- タスクを取得するたびに異なるコメントがランダムに選ばれます。スコアを比較するときは **同一トークン** で再提出してください（取得しなおすと別の問題になります）
- ユーザーのコメント数が不十分な場合、`train_count` や `test_count` が要求値を下回ることがあります。
  レスポンスの値を必ず参照してください
