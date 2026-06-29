# 重複クラスタ棚卸しレポート

作成日: 2026-06-29
目的: 「片方を直すと同種の別実装にバグが残る」連鎖の根本原因＝コピー＆ペースト由来の重複（shotgun surgery / divergent change）を全件可視化し、集約の優先順位と再増殖防止策を決める台帳。

## サマリ

- 確認できた重複クラスタ: **22**（JS 6 / Python 10 / クロス層 6）
  - 当初版は JS / Python のみを対象としていた。2026-06-30 の検証で **Jinjaテンプレート層** と **app↔batch サーバ間重複**（C1〜C6）を追加。最悪の分岐はこのクロス層に集中している。
- 危険度の本質は「重複」そのものではなく **すでに分岐（divergence）していること**。同一責務のはずのコピーが挙動を違え、過去の fix が一部のコピーにしか反映されていない。
- 個々のコードの質は高い（コメント・コミット粒度とも良好）。問題は設計上の一点＝**単一の真実（source of truth）の欠如**に集約される。

凡例: 🔴 実害あり（fix 未反映/挙動分岐を確認） / 🟡 潜在（現状は閾値内だが脆い） / ⚪ 体裁・保守性

---

## JS クラスタ

### J1. 🔴 投票ウィジェット（最優先）
責務: 楽観的カウント更新・デバウンス・バッチ送信・遅延ハイドレーション・紙吹雪。

| 実装 | 場所 |
|---|---|
| フル実装（debounce + batch + hydrate） | `user-comments.js`: `vote`(512) `flushVote`(535) `setVoteControls`(311) `renderVoteButtonsMarkup`(296) `hydrateDeferredVoteControls`(320) |
| フル実装＋200件チャンク | `cluster-comments.js`: `vote`(64) `flushVote`(91) `hydrate`(135 / チャンク140) |
| 最小実装 | `vod-comments.js`: `window.vote`(10) `loadVoteCounts`(32) |

**分岐と未反映 fix:**
- `vod-comments.js` は **デバウンスもバッチも紙吹雪も無い**（1クリック=1リクエスト）。連打系の修正（`fd0cc33`/`f5936fd`「連打時に投票数消失」）が**まるごと未反映**。
- ハイドレーションのチャンク分割は `cluster-comments.js` のみ。`user-comments.js`/`vod-comments.js` は全ID一括送信（サーバ上限 `MAX_VOTE_BULK_IDS=200` を超えると 400 で表示更新が丸ごと失敗）。VODページは `page_size` 最大 200 で**ちょうど境界**。
- `renderVoteButtonsMarkup` は `user-comments.js` だけ。他はインライン。

集約先: `static/js/vote-widget.js`（チャンク＋debounce を正とする）。

### J2. 🔴 時刻・UTC整形
責務: サーバのTZなしUTC文字列を正しく解釈し、相対時刻/日付に整形。

| 関数 | 場所 | 分岐 |
|---|---|---|
| `normalizeUtcIso` | `users.js`(54), `index.js`(596) | ほぼ同一だが2箇所に複製 |
| `formatRelativeTime` | `index.js`(608), `user-comments.js`(85) | **引数仕様が違う**（index=TZなし文字列前提 / user-comments=オフセット付きISO前提）、丸めも別（`1分前`下限 vs `0分前`） |
| `formatDate` | `users.js`(66), `vods.js`(55) | 同一ロジック2複製 |
| `getJSTDate` / 手動+9h | `user-comments.js`(1329, 1304) | 別方式 |

過去 fix `2bda22b`(9時間ズレ)・`394356e`(1日ズレ) はこのクラスタの**同一バグを別ファイルで個別修正**した痕跡。集約先: `static/js/time-format.js`。

### J3. 🟡 root_path 正規化
8ファイルに散在し **3変種**:
- インライン定番形: `cluster-comments.js`(3) `vods.js`(15) `users.js`(13) `index.js`(17) `user-stats.js`(7) `vod-comments.js`(6)
- `base.js`(5) にヘルパ相当が既にある（未活用）
- `user-comments.js`(13) は `.trim()` 追加の独自変種
- `user-ego-graph.js`(13) は **正規化なし**（`JSON.parse` のみ → root_path 末尾スラッシュ時にURL不整合の恐れ）

集約先: `base.js` の正規化を全JSが import。

### J4. ⚪ `escapeHtml`
`quiz.js`(55) `cluster-comments.js`(11) `user-comments.js`(65) の3複製（実装は同等）。

### J5. ⚪ `spawnConfetti`
`quiz.js`(104, 引数なし) `cluster-comments.js`(25) `user-comments.js`(476) の3複製。

### J6. 🟡 無限スクロール/追加読込の多重実行ガード
- `vods.js`: 世代トークン方式（`requestSeq`(27)+`isLoading`(26)）
- `user-comments.js`: `isLoading`(36)+`loadedPages`(35)+`currentMin/MaxPage`(33-34)

**同じ「多重実行・競合」問題に別戦略**。fix `2188433`（多重実行ガード追加）は一方のモデルにしか入っていない。共通の取得制御に寄せる余地。

---

## Python クラスタ

### P1. 🔴 コメント一覧 SELECT 列ブロック（community_notes JOIN 列）
本文HTMLの部分式は `build_comment_body_select_sql` で集約済み（良い前例）。だが**周辺の `cn.* / v.* / u.*` 列リストは4箇所コピー**:
- `comment_repo.py` `_COL_LIST`(16-31)
- `search.py`(94-122 インライン, 162-180 ヘルパ内)
- `best9.py`(64-82)

さらに **5つ目の変種** `_QUIZ_COL_LIST`(528) が存在し、列リストだけでなく `FROM comments c JOIN vods v … JOIN users u … LEFT JOIN community_notes cn …` の **JOIN句ブロックも4箇所で重複**（best9 は `cn.*` 列と community_notes JOIN を持たない分岐）。列追加（`cn_model`/`cn_ask` 等）時に一部で取りこぼすリスク。集約先: `comment_utils` に `COMMENT_LIST_COLUMNS` 定数＋JOIN句ヘルパ。

### P2. 🔴 ORDER BY タイブレーカー生成
- `comment_repo.py`: `_build_user_comment_order`(75) `_build_vod_order`(104) `_build_vod_comment_order`(304)
- `vod_repo.py`: `_build_vod_list_order`(112)

「末尾に一意キーを足す」修正（`f71a655` comments / `6ad9a5b` vods）を**各関数に個別適用**。RAND(:seed) 分岐も2関数で重複。集約先: タイブレーカー必須を強制する単一ビルダ。

### P3. 🟡 ユーザ検索SQL
`user_repo.find_user`(9) が正。なのに `search.py` が**インラインで3回**再実装（46, 221, 267、列は少なめ）。集約先: `find_user` 呼び出しに統一。

### P4. 🔴 FAISS結果→コメント詳細取得（search.py 内）
`similar_search_api` が詳細取得+decorate を**インライン**で実装(90-146)。同一処理の `_fetch_comment_details`(149-203) が直下に存在。**1ファイル内に同じ処理が2つ**。集約先: `similar_search_api` も `_fetch_comment_details` を使う。

### P5. 🟡 ランダムサンプリング分岐
`_fetch_comment_ids_random`(538) というヘルパがあるのに、`fetch_quiz_other_comments`(613) は同じ COUNT/ratio/ORDER BY RAND の分岐を**インライン再実装**。集約先: ヘルパ呼び出しに統一。

### P6. ⚪ comment_id 正規化（strip/dedup）
`vote_input.normalize_comment_ids`(6) と `comment_repo.fetch_comment_vote_counts`(404-413) に**同一ループ**。さらに `config._parse_csv_env`(42-48) も同じ `seen=set()`+`strip`+dedup ループ（ドメインは違うがロジック同一・計3箇所）。集約先: 単一正規化関数。

### P7. 🟡 body_html 後処理（raw_json/body_html_version の除去）
`comment_utils.decorate_comment`(290-291) と `index_service.build_popular_comments`(99-100) が同じ後処理を別実装。後者は decorate を部分的に手再現。集約先: 共通レンダラ。

### P8. ⚪ `_parse_int`
`comments.py`(54) と `vods.py`(17) に同一実装。集約先: 共通util。

### P9. 🟡 JST変換手段の乱立
- SQL: `+ INTERVAL 9 HOUR`（`stats_repo.py` ×4）
- Python: `utc_to_jst`（pytz Asia/Tokyo）/ `comment_service.JST = timezone(+9h)` 固定オフセット
- JS: `toLocale… timeZone:'Asia/Tokyo'` / 手動 `+9h`

日本にDSTが無いため結果は一致するが、概念的に**4系統**。レイヤごとに「to_jst」を一本化したい。

### P10. 🔴 危険度スコア式 (harm+exag+evid+subj)/4 の null 処理が5者5様
| 場所 | 式 | NULL時の挙動 |
|---|---|---|
| `user-comments.js`(173) | `(…+(subj||0))/4` | subj=null→0、4で割る（過小評価）。harm/exag/evid が null だと NaN |
| `vod_comments.html`(161) Jinja | `(harm+exag+evid+subj)/4` | **NULLガード無し**（harm_risk の is not none しか見ない→他列nullでJinja算術エラー/None） |
| `comment_repo.py`(96) ORDER BY | `COALESCE(sum,0)` | **どれか1つでもNULL→合計NULL→0** で最下位ソート |
| `stats_repo.py`(263) ヒストグラム | `sum/4/10` | NULL→そのコメントが集計から脱落 |
| `stats_service.py`(110) 平均 | 各列を個別平均 | 列ごとにNULLを無視 |

同じ「危険度」が**画面ごとに違う値**になりうる、明確な潜在不整合。バッジ閾値(60/30)と配色rgbaも JS と Jinja で重複（→ C2）。集約先: 危険度の算出と欠損ポリシーを1関数（+対応SQL断片）に定義。

---

## クロス層クラスタ（テンプレート / app↔batch）

本台帳は当初スコープを JS / Python に限定したため、**Jinjaテンプレート層**と **app↔batch のサーバ間重複**が抜けていた（2026-06-30 追記）。最悪の分岐はここにある——サーバ描画（Jinja）とクライアント描画（JS）が同じものを別実装で持ち、すでに食い違っている。

### C1. 🔴 body_html / エモート描画が app↔batch で完全二重化（新・最優先級）
`app/services/comment_utils.py` と `batch/scripts/comment_body_html.py` の `parse_raw_comment` / `_sanitize_emote_text` / `normalize_emote_id` / `render_comment_body_html` / `EMOTE_URL_TEMPLATE` / `EMOTE_ID_PATTERN` が**バイト単位で同一**。しかも **`BODY_HTML_RENDER_VERSION = 1` が両ファイルで独立定義**。

危険性が最大の理由: batch（`insertdb.py` / `backfill_comment_body_html.py`）が version 付きで `body_html` を**保存**し、app は version 一致時にそれを使い不一致なら再描画する。**片方の描画ロジックだけ変えて version を揃えたままにすると、保存済みHTMLと実時描画が無言で食い違い、キャッシュ無効化も走らない**＝サイレントなデータ不整合。batch は app を import できない別デプロイなのでコピーされた。集約先: app/batch 双方が import できる共有モジュール（version 定数も単一定義）。

### C2. 🔴 投票ボタン markup（J1のクロス層拡張）
JS `renderVoteButtonsMarkup`(user-comments.js 296) と**同一のボタンHTML**が `vod_comments.html`(151) `user_comments.html`(312) `cluster_comments.html`(62) に**ハードコピー（計4箇所）**。J1 は JS 側しか見ていなかった。集約先: J1 の共通ウィジェット化と同時に、初期描画もマクロ/部分テンプレートで1定義に。

### C3. 🔴 コミュニティノート描画が JS↔Jinja で分岐
`renderCommunityNote`(user-comments.js 167) と Jinja 版（`vod_comments.html` 157 / `user_comments.html` 350）。**すでに分岐済み**:
- `vod_comments.html` は**スコアバーも `cn_model が生成` も無い**（user_comments.html と JS には有る）
- **`cluster-comments.js` はコミュニティノートを一切描画しない**（クラスタ画面では注釈が不可視）

集約先: ノート1コメント分のHTMLを生成する単一ソース（テンプレート部分 or JSモジュール）に寄せ、全画面が同じ表現を使う。

### C4. 🟡 判定ステータス日本語ラベル表が4ファイル重複
`{supported:裏付けあり, insufficient:情報不足, inconsistent:矛盾あり, not_applicable:該当なし}` がリテラルで `user-comments.js`(181) `vod_comments.html`(167) `user_comments.html`(350) `user_stats.html`(67)。ステータス追加時に4箇所更新が必要。集約先: サーバ側マスタ→テンプレ/JSへ単一供給。

### C5. ⚪ CNスコア5軸のラベル＋配色
`検証可能性/被害可能性/誇張度/根拠不足/主観度` と hex色が `user-comments.js`(193) `user_comments.html`(364-385) `user-stats.js`(68 チャート) に三重化。集約先: 軸定義（ラベル+色）の単一データ。

### C6. ⚪ ページング引数ボイラープレート
`page:int=Query(1,ge=1)` / `page_size:int=Query(N,ge=10,le=200)` が `vods.py` `comments.py` の各エンドポイントに反復し、上限200のマジックナンバーが散在。集約先: 共通 Depends/Pydantic パラメータ。

---

## 優先順位（バグ密度 × 影響範囲）

| 順位 | クラスタ | 理由 |
|---|---|---|
| 1 | C1 body_html renderer (app↔batch) | version 定数まで二重定義。描画分岐がキャッシュ無効化されずサイレントなデータ不整合に直結 |
| 2 | J1 投票ウィジェット ＋ C2 投票markup | 既存 fix がvod画面に未反映、チャンク欠落で表示破綻の芽。初期markupも3テンプレに散在 |
| 3 | J2 時刻整形 | 9h/1日ズレの再発源。引数仕様まで分岐 |
| 4 | P2 ORDER BY ビルダ | ページング重複/欠落の再発源。fixを毎回N重に適用中 |
| 5 | C3 CNノート描画 / P1 SELECT列 / P4 search内重複 | C3はvod/clusterで表示欠落・分岐済み。P1は列追加時の取りこぼし、即効性高 |
| 6 | P10 危険度式 / C4 ステータスラベル | 画面間で値・表記が食い違う潜在不整合（Jinja含め5〜4箇所） |
| 7 | J3/J4/J5/J6, P3/P5/P6/P7/P8/P9, C5/C6 | 体裁・保守性。ついでに回収 |

## 再増殖の防止（これが無いと必ず戻る）

1. **物理的に1箇所へ**: JSは共通モジュール import 必須、Pythonは utils/constants 参照必須。app↔batch のように import 境界をまたぐものは共有モジュール（パッケージ化）で1定義に。
2. **CIガード**: 「同名関数が2ファイル以上で定義されたら fail」する grep ベースの軽量チェックを1本追加（例: `function vote(` / `def _parse_int` / `normalizeUtcIso` の重複検出）。加えて (a) `BODY_HTML_RENDER_VERSION` が単一ファイルでしか定義されないこと、(b) 投票ボタン/CNノートの markup・JA ステータスラベル表がテンプレと JS に二重定義されていないこと、を検出する。
3. **修正フロー**: 「ある処理を直したら兄弟実装を grep で探す」を PR チェックリスト/フックに明文化。**特にレイヤをまたぐ描画（Jinjaテンプレート ↔ JS、app ↔ batch）は見落としやすいので明示的に確認する**。
4. **集約はテスト先行・1クラスタずつ**: big-bang リファクタは禁止。回帰テストで挙動を固定 → 共通化 → 各呼び出し差し替え。

## 次アクション候補

- A) 本台帳を確定し、J1（投票）から テスト→共通化→差し替え に着手
- B) 先に CIガード（防止策2）だけ入れて出血を止める
- C) 各クラスタに GitHub Issue を切って追跡可能にする
