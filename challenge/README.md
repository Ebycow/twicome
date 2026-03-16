# Twicome Quiz Challenge "Who Wrote This?"

Twitch コメントの書き手を当てる**ランキング形式の識別タスク**です。
このディレクトリには、タスク API を使ったサンプルコードが含まれています。

---

## タスクの概要

ある Twitch ユーザー（以下「対象ユーザー」）のコメント履歴を学習データとして受け取り、
テストの各問題で提示される **100 件の候補コメント**（本人 1 件 + 別人 99 件）を
本人らしい順にランク付けする **ランキング・検索タスク**です。

| 項目               | 内容                                                                 |
|------------------|----------------------------------------------------------------------|
| 学習データ          | 対象ユーザー **1,000 件** + 別ユーザー 99 人 × 1,000 件 = 計 **100,000 件** |
| テスト             | **500 問** × **100 候補**（本人コメント 1 件 + 別人コメント 99 件）     |
| 出力               | 各問題の `candidate_id` を本人らしい順に並べた全 100 件のリスト          |
| 評価指標           | **Top-1 accuracy**（1 位が正解の割合）と **MRR**（Mean Reciprocal Rank） |
| ランダム予測の期待値 | Top-1 ≈ 1%、MRR ≈ 0.052                                              |
| 参加資格           | 対象ユーザーが DB に **1,500 件以上**のコメントを持つこと               |

### 評価指標の意味

- **Top-1 accuracy**: 500 問のうち 1 位に正解を置けた割合。`correct_top1 / 500`
- **MRR (Mean Reciprocal Rank)**: 各問題で正解が何位だったかの逆数の平均。
  正解が 1 位なら 1.0、2 位なら 0.5、10 位なら 0.1。Top-1 より「惜しい」ケースも評価できる。

### 学習データの構造

| フィールド    | 内容                                              |
|------------|--------------------------------------------------|
| `body`     | コメント本文                                       |
| `is_target`| `true` = 対象ユーザー本人、`false` = 別ユーザー    |
| `user_idx` | `0` = 本人、`1`〜`99` = 各別人（タスク内で一貫した番号） |

学習データ内の `user_idx` を使うと、どのコメントが同一の「別人」由来かを知ることができます。
同一トークン内では各 `user_idx` の割り当ては固定です。

---

## API 仕様

### ベース URL

```
http://<host>:<port>
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

クエリパラメータはありません。学習・テスト件数はサーバー側で固定されます。

#### レスポンス

```json
{
  "task_token": "eyJsb2dpbiI6...",
  "target_login": "someuser",
  "train_count": 100000,
  "test_count": 500,
  "candidates_per_question": 100,
  "training": [
    {"body": "草", "is_target": true,  "user_idx": 0},
    {"body": "それな", "is_target": false, "user_idx": 3},
    ...
  ],
  "test": [
    {
      "id": 0,
      "candidates": [
        {"candidate_id": 0, "body": "えぐい"},
        {"candidate_id": 1, "body": "ｗｗｗ"},
        ...
      ]
    },
    ...
  ]
}
```

#### フィールド説明

| フィールド                        | 型      | 説明                                                           |
|---------------------------------|--------|--------------------------------------------------------------|
| `task_token`                    | string | 採点に必要な署名済みトークン。再取得するたびに異なる値になる          |
| `target_login`                  | string | 対象ユーザーの login                                            |
| `train_count`                   | int    | 学習データの総件数（本人 1,000 + 別人 99,000）                    |
| `test_count`                    | int    | テスト問題数（= 500）                                           |
| `candidates_per_question`       | int    | 1 問あたりの候補数（= 100）                                     |
| `training`                      | array  | ラベル付き学習データ。順序はランダム                               |
| `training[].body`               | string | コメント本文                                                    |
| `training[].is_target`          | bool   | `true` = 本人、`false` = 別ユーザー                            |
| `training[].user_idx`           | int    | `0` = 本人、`1`〜`99` = 各別人（同一タスク内で一貫）              |
| `test`                          | array  | 500 問のテストデータ                                            |
| `test[].id`                     | int    | 0 始まりの問題番号。提出時に使う                                  |
| `test[].candidates`             | array  | 100 件の候補コメント（順序はランダム）                            |
| `test[].candidates[].candidate_id` | int | 0〜99 の候補番号。提出時にこの番号でランクを指定する              |
| `test[].candidates[].body`      | string | 候補コメントの本文                                              |

---

### 予測提出・採点

```
POST /api/u/{login}/quiz/task/submit
Content-Type: application/json
```

#### リクエストボディ

各問題の候補を「本人らしい順（確信度降順）」に並べた `candidate_id` のリストを提出します。
全 100 候補を必ず含めてください。

```json
{
  "task_token": "eyJsb2dpbiI6...",
  "answers": [
    {"id": 0, "ranked_candidates": [42, 7, 15, 0, 99, ...]},
    {"id": 1, "ranked_candidates": [3, 88, 51, 12, ...]},
    ...
  ]
}
```

| フィールド                    | 型     | 説明                                                         |
|-----------------------------|------|-------------------------------------------------------------|
| `task_token`                | string | タスク取得時のトークン                                         |
| `answers`                   | array  | 全 500 問分の予測。件数が不足するとエラー                       |
| `answers[].id`              | int    | `test[].id` に対応する問題番号（0〜499）                       |
| `answers[].ranked_candidates` | array | `candidate_id` を本人らしい順に並べた 100 件のリスト          |

#### レスポンス

```json
{
  "top1_accuracy": 0.29,
  "mrr": 0.4008,
  "correct_top1": 145,
  "total": 500
}
```

| フィールド                 | 型     | 説明                                          |
|--------------------------|------|---------------------------------------------|
| `top1_accuracy`          | float  | Top-1 正答率（0.0〜1.0）                       |
| `mrr`                    | float  | Mean Reciprocal Rank（0.0〜1.0）              |
| `correct_top1`           | int    | 1 位に正解を置けた問題数                         |
| `total`                  | int    | テスト問題の総数（= 500）                        |

#### エラーレスポンス

| HTTP ステータス | `error` 値                         | 説明                                     |
|------------|------------------------------------|----------------------------------------|
| 400        | `invalid_token`                    | トークンが不正または期限切れ                   |
| 400        | `missing_answer_for_id_N`          | 問題 ID=N の提出がない                      |
| 400        | `wrong_ranking_length_for_id_N`    | 問題 N の `ranked_candidates` が 100 件でない |
| 400        | `invalid_candidate_ids_for_id_N`   | 問題 N の候補 ID セットが不正                 |
| 400        | `insufficient_target_comments`     | 対象ユーザーのコメント数が 1,500 件未満         |
| 400        | `insufficient_other_users`         | 条件を満たす別ユーザーが 99 人に満たない         |
| 404        | `user_not_found`                   | 対象ユーザーが存在しない                      |

---

## 公式ルール

1. **使ってよいもの**: 学習データ (`training`) のみ。テスト候補の本文はそのまま特徴量に使える
2. **使ってはいけないもの**: サーバーの検索・推薦 API（`/api/u/{login}/search` など）への問い合わせ
3. **外部データ**: 事前学習済みの言語モデルや一般公開の辞書・コーパスの利用は**可**
4. **再提出**: 同一トークンへの再提出は何度でも可能。異なるアプローチのスコアを比較するために使える
5. **トークンの扱い**: `task_token` は HMAC-SHA256 で署名されており、クライアント側から正解ラベルを逆算することはできない

---

## セットアップ

```bash
cd challenge

# 仮想環境を作成 (推奨)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 必須パッケージ (全ベースライン共通)
pip install requests scikit-learn numpy scipy

# baseline_sentence_bert 系を使う場合のみ追加
pip install sentence-transformers

# baseline_janome.py を使う場合のみ追加
pip install janome
```

または `requirements.txt` から一括インストール:

```bash
pip install -r requirements.txt
```

---

## サンプルコード

### run_all.py — 全ベースライン比較

同一タスクで全ベースラインを一括実行し、Top-1 accuracy と MRR を表で比較します。

```bash
# 全ベースラインを実行 (sentence_bert 系 / janome 以外)
python run_all.py --login someuser --base-url http://localhost:8000

# sentence_bert 系も含めて実行
python run_all.py --login someuser --base-url http://localhost:8000 --include sentence_bert_suite

# 追加依存があるベースラインを全部含めて実行
python run_all.py --login someuser --base-url http://localhost:8000 --include sentence_bert_suite janome

# 特定のベースラインのみ実行
python run_all.py --login someuser --only svm ensemble adaptive

# 特定のベースラインをスキップ
python run_all.py --login someuser --skip rf gbm centroid
```

出力例:

```
===========================================================================
 精度比較結果
===========================================================================
   順位   Top-1     MRR  Bar (Top-1)                     名前
---------------------------------------------------------------------------
    1.  29.0%  0.4008  [████████░░░░░░░░░░░░░░░░░░░░░░]  TF-IDF + LinearSVC  [9.0s]
    2.  26.0%  0.3793  [███████░░░░░░░░░░░░░░░░░░░░░░░]  適応ブレンド  [196.6s]
    3.  24.0%  0.3452  [███████░░░░░░░░░░░░░░░░░░░░░░░]  TF-IDF + LogisticRegression  [14.1s]
   ...
   11.   1.0%  0.0401  [░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  ランダム予測  [0.1s]
===========================================================================

  最高 Top-1: 29.0%  (TF-IDF + LinearSVC)
  最高 MRR:   0.4008  (TF-IDF + LinearSVC)
  ランダム比 (Top-1): +28.0%
```

---

### 個別実行

各ベースラインは単独でも実行できます。

#### baseline_random.py — ランダム予測

候補をランダムにシャッフルして提出する最小実装。スコアを自分の実装と比較するベースラインとして使えます。
期待値: Top-1 ≈ 1%、MRR ≈ 0.052

```bash
python baseline_random.py --login someuser --base-url http://localhost:8000
```

#### baseline_tfidf.py — TF-IDF + ロジスティック回帰

文字 n-gram (1〜3文字) の TF-IDF + LR。`predict_proba` でスコアリングしてランク付け。

```bash
python baseline_tfidf.py --login someuser --base-url http://localhost:8000
```

#### baseline_svm.py — TF-IDF + LinearSVC

高次元スパース特徴量に強い SVM。`decision_function` でランキングスコアを取得。
100k 件の学習データでも高速に動作します。

```bash
python baseline_svm.py --login someuser --base-url http://localhost:8000
```

#### baseline_nb.py — TF-IDF + Naive Bayes

ComplementNB による超軽量な分類。短テキスト向けに調整済み。

```bash
python baseline_nb.py --login someuser --base-url http://localhost:8000
```

#### baseline_rf.py — TF-IDF + Random Forest

決定木のアンサンブルで非線形な特徴の組み合わせを捉えます。

```bash
python baseline_rf.py --login someuser --base-url http://localhost:8000
```

#### baseline_gbm.py — TF-IDF + Gradient Boosting

HistGradientBoostingClassifier (sklearn の高速 GBM)。TF-IDF を dense に変換してから学習します。

```bash
python baseline_gbm.py --login someuser --base-url http://localhost:8000
```

#### baseline_word_ngram.py — 文字 + 単語 n-gram TF-IDF

文字 n-gram と単語 n-gram を結合した特徴量 + LR。スタンプ名の共起を捉えます。

```bash
python baseline_word_ngram.py --login someuser --base-url http://localhost:8000
```

#### baseline_centroid.py — Nearest Centroid (cosine)

学習データ中の本人コメント群の TF-IDF 重心を計算し、各候補とのコサイン類似度でランク付けします。
パラメータほぼゼロで高速ですが、100k 件の混合コーパスで学習した TF-IDF 空間では本人の特徴が薄れやすく精度は低めです。

```bash
python baseline_centroid.py --login someuser --base-url http://localhost:8000
```

#### baseline_handcrafted.py — 手作り特徴量 + LinearSVC

絵文字率・ひらがな率・wwww率など Twitch チャット特化の 20 次元特徴量 + LinearSVC。
テキスト内容ではなく「書き方のスタイル」だけを使って識別します。

```bash
python baseline_handcrafted.py --login someuser --base-url http://localhost:8000
```

#### baseline_janome.py — Janome 分かち書き + 特徴量融合 + LinearSVC

Janome で日本語を分かち書きし、単語・原形/品詞 n-gram に加えて文字 n-gram と手作り特徴量を結合する上級ベースラインです。
語彙だけでなく、助詞の使い方や語尾、記号の混ぜ方といったスタイル差もまとめて捉えられます。

```bash
pip install janome
python baseline_janome.py --login someuser --base-url http://localhost:8000
```

#### baseline_ensemble.py — アンサンブル (ソフト投票)

LR・SVM・NB・単語 n-gram の 4 モデルのスコアを重み付き平均してランク付けします。

```bash
python baseline_ensemble.py --login someuser --base-url http://localhost:8000
```

#### baseline_adaptive.py — 適応ブレンド

学習データの交差検証で複数候補モデルを比較し、そのタスクに適したモデルだけを CV スコアに応じて重み付きでブレンドします。
CV はサブサンプリング（最大 5,000 件）で高速化しています。精度は高めですが実行時間は長くなります。

```bash
python baseline_adaptive.py --login someuser --base-url http://localhost:8000
```

#### baseline_sentence_bert.py — Sentence-BERT + LR

事前学習済み日本語モデルで埋め込み後、LR で分類 (freeze + probe)。
デフォルトモデル: `hotchpotch/static-embedding-japanese`（GPU 不要・静的埋め込みで高速）

```bash
pip install sentence-transformers
python baseline_sentence_bert.py --login someuser --base-url http://localhost:8000

# 別のモデルを使う場合
python baseline_sentence_bert.py --login someuser --model cl-tohoku/bert-base-japanese-char-v3
```

#### baseline_sentence_bert_knn.py — Sentence-BERT + top-k 近傍

本人コメント埋め込みとの類似度を top-k 近傍で集約するベースラインです。
短文チャットでは「意味の平均」よりも、似た言い回しやスタンプ名への局所一致が効くケースを狙います。

```bash
python baseline_sentence_bert_knn.py --login someuser --base-url http://localhost:8000
```

#### baseline_sentence_bert_margin.py — Sentence-BERT + target/other margin

本人コメントへの近さに加えて、`user_idx` ごとにまとめた別人重心へ近すぎないこともスコア化します。
「誰でも言いそうな短文」を落としたいときに向く variant です。

```bash
python baseline_sentence_bert_margin.py --login someuser --base-url http://localhost:8000
```

#### baseline_sentence_bert_multiview.py — Sentence-BERT + short-text multi-view

raw テキストと正規化テキストの両方を埋め込み、`w/ｗ/wwww` や全半角の揺れを吸収します。
短文特有の表記揺れに強くしたいときの variant です。

```bash
python baseline_sentence_bert_multiview.py --login someuser --base-url http://localhost:8000
```

#### baseline_sentence_bert_bucketed.py — Sentence-BERT + バケット別プロトタイプ

候補コメントを「笑い系」「疑問文」「超短文」などに分け、同タイプの本人コメント重心と比較します。
短文のスタイル差を明示的に使う variant です。

```bash
python baseline_sentence_bert_bucketed.py --login someuser --base-url http://localhost:8000
```

#### baseline_sentence_bert_rerank.py — Sentence-BERT + 二段階 rerank

1段目で近傍類似度から top 候補を拾い、2段目で margin・bucket 類似度・長さなど少数特徴で並べ替えます。
検索と識別を分けて考える sentence_bert 系の実験用ベースラインです。

```bash
python baseline_sentence_bert_rerank.py --login someuser --base-url http://localhost:8000
```

#### baseline_sentence_bert_contrastive.py — Sentence-BERT + 対照学習アダプタ

固定 Sentence-BERT 埋め込みの上に軽量な線形アダプタを学習し、本人同士を近づけて本人/別人を引き離します。
フル fine-tuning より軽く、対照学習の方向性を試すための variant です。

```bash
python baseline_sentence_bert_contrastive.py --login someuser --base-url http://localhost:8000
```

---

## 実装のヒント

### データの特性

- コメントは Twitch チャット由来のため **非常に短い**（絵文字・スタンプ・草・ｗ 系が多い）
- 1 ユーザーの語彙・スタイルは比較的一貫している（同じスタンプを繰り返す、特定の言い回しを使うなど）
- 学習データは **1:99 の強いクラス不均衡**（本人 1,000 件 vs 別人 99,000 件）。`class_weight="balanced"` などの対処が有効
- `user_idx` を使うと別人 99 人を個別に識別でき、マルチクラス分類や one-vs-rest 戦略が取れる

### ランキングの作り方

各候補に「本人らしさスコア」を付けて降順に並べるのが基本パターンです。

```python
# LR / NB など predict_proba を持つモデル
scores = model.predict_proba(X_candidates)[:, 1]  # is_target=True の確率
ranked = [candidates[i]["candidate_id"] for i in scores.argsort()[::-1]]

# LinearSVC など decision_function を使うモデル
scores = model.decision_function(X_candidates)
ranked = [candidates[i]["candidate_id"] for i in scores.argsort()[::-1]]
```

### 特徴量のアイデア

| アプローチ          | 説明                                                           |
|------------------|--------------------------------------------------------------|
| 文字 n-gram        | 1〜5 文字の組み合わせ。日本語の形態素解析なしで使える             |
| 単語 n-gram        | スペース・句読点でトークナイズ。スタンプ名の一致に有効             |
| 文字種の比率        | 全角英数・半角・絵文字・ひらがな・カタカナの割合                  |
| 形態素解析 + 品詞 n-gram | Janome などで分かち書きし、原形・品詞列・助詞の癖を特徴量化       |
| 事前学習モデル      | sentence-transformers 等で埋め込みベクトル化                    |
| 埋め込み + top-k 近傍 | 本人コメント群との局所一致をスコア化し、短文の言い回し重視で比較   |
| 埋め込み + multi-view | raw/正規化テキストの両方を埋め込み、短文の表記ゆれを吸収         |
| user_idx の活用   | 別人 99 人をそれぞれモデル化し、テスト候補が「誰でもない」ことを確認 |

### NN を使う場合

100k 件の学習データは NN にとって十分な量です。

- **freeze + プローブ**: 事前学習モデルを凍結し、埋め込みを固定特徴量として LR で識別
- **fine-tuning**: `cl-tohoku/bert-base-japanese-char` 等の最終層のみ学習
- **対照学習**: 本人コメントと別人コメントの埋め込みを引き離す損失関数

---

## 注意事項

- `task_token` はサーバーが `QUIZ_SECRET_KEY` 環境変数で設定した秘密鍵で署名されます。
  この変数が未設定の場合はランダム生成されるため、**サーバー再起動でトークンが無効**になります。
  セルフホストする場合は `.env` に `QUIZ_SECRET_KEY` を固定値で設定してください
- タスクを取得するたびに**コメントの選択・候補のシャッフルがランダム**に変わります。
  スコアを比較するときは **同一トークン** で再提出してください（取得しなおすと別の問題になります）
- 対象ユーザーのコメント数が 1,500 件未満の場合、タスク取得時に `400 insufficient_target_comments` エラーが返ります
