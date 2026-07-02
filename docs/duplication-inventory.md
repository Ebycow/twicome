# 重複クラスタ棚卸しレポート

作成日: 2026-06-29
目的: 「片方を直すと同種の別実装にバグが残る」連鎖の根本原因＝コピー＆ペースト由来の重複（shotgun surgery / divergent change）を全件可視化し、集約の優先順位と再増殖防止策を決める台帳。

## サマリ

- 確認できた重複クラスタ: **36**（JS 6 / Python 10 / クロス層 6 / 追加検証 7 / リポジトリ全域 7）
  - 当初版は JS / Python のみを対象としていた。2026-06-30 の検証で **Jinjaテンプレート層** と **app↔batch サーバ間重複**（C1〜C6）を追加。最悪の分岐はこのクロス層に集中している。
  - 2026-07-01 の全コード再走査で **N1〜N7** を追加。C1（body_html）は **クライアント検証層（JS）** まで含む多層重複だと判明し、実測で **app↔batch のコメント差分（コメント行の分岐）** も検出した。既存 C1〜C6 / J1〜J6 / P1〜P10 は全件コードで裏取り済み（行番号は 6/29 以降のコミットで多少ズレるが構造は不変）。
  - 2026-07-02 に **既存29クラスタを全件再検証（全件現存を確認、下記の増殖・訂正あり）** し、これまで一度も走査対象になっていなかった **challenge/ ・ morpheme-sample/ ・ util/ ・ migrate/ ・ faiss-api/ ・ morpheme-api/ ・ twicome-mcp-server/ ・ CSS層** を走査して **R1〜R7** を追加。台帳のスコープ外だったディレクトリに最大14ファイル同一コピーのクラスタが存在した。
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
10ファイルに散在し **4変種**（2026-07-02 再検証で quiz.js / offline-access.js を追加確認）:
- インライン定番形: `cluster-comments.js`(3) `vods.js`(15) `users.js`(13) `index.js`(17) `user-stats.js`(7) `vod-comments.js`(6)
- `base.js`(5) にヘルパ相当が既にある（未活用）
- `user-comments.js`(13) と `quiz.js`(7-8) は `.trim()` 追加の独自変種
- `offline-access.js`(7) は `normalizeRootPath` という**4つ目のヘルパ関数**（trim 変種と同等ロジックの別実装）
- `user-ego-graph.js`(13) は **正規化なし**（`JSON.parse` のみ → root_path 末尾スラッシュ時にURL不整合の恐れ）
- （参考: `sw.js` は SW スコープ由来の独自正規化。DOM を読めない制約上やむを得ないが、正規化仕様を変えるときは追随が必要）

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
- SQL: `+ INTERVAL 9 HOUR`（`stats_repo.py` ×5、2026-07-02 時点で1箇所増殖）
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

**2026-07-01 実測: すでに分岐が始まっている。** `_sanitize_emote_text` に `app` 側だけコメント行 `# Emote labels should stay plain text even if raw JSON is malformed or hostile.` があり `batch` 版には無い。レンダ本体は同一だがコメント単位で乖離済み——「無言の分岐」懸念が現実化しつつある証拠。
**さらに描画は 4 経路に散在**（この台帳は当初 C1 を app↔batch の 2 経路として記述していたが、クライアント検証層を見落としていた）: ① batch 保存 ② app 再描画 ③ JS `appendSafeBodyHtml`（`user-comments.js` / `quiz.js`）。③の詳細は **N2** 参照。emote 許可 URL・`class="emote"`・属性許可リストが Python 2 実装 + JS 2 実装の計 **4 箇所**にハードコピーされている。集約は 3 層すべてを同時に揃える必要がある。

2026-07-02 追記: emote CDN URL `static-cdn.jtvnw.net` は上記4実装に加えて **`core/middleware.py`(47) の CSP ヘッダ**と **`sw.js`(342) のキャッシュ分岐**にもリテラルで存在（計 **6 箇所**）。CDN ドメイン変更・追加時は描画4実装＋配信ポリシー2箇所の全てを揃える必要がある。

### C2. 🔴 投票ボタン markup（J1のクロス層拡張）
JS `renderVoteButtonsMarkup`(user-comments.js 296) と**同一のボタンHTML**が `vod_comments.html`(151) `user_comments.html`(312) `cluster_comments.html`(62) に**ハードコピー（計4箇所）**。J1 は JS 側しか見ていなかった。集約先: J1 の共通ウィジェット化と同時に、初期描画もマクロ/部分テンプレートで1定義に。

### C3. 🔴 コミュニティノート描画が JS↔Jinja で分岐
`renderCommunityNote`(user-comments.js 167) と Jinja 版（`vod_comments.html` 157 / `user_comments.html` 350）。**すでに分岐済み**:
- `vod_comments.html` は**スコアバーも `cn_model が生成` も無い**（user_comments.html と JS には有る）
- **`cluster-comments.js` はコミュニティノートを一切描画しない**（クラスタ画面では注釈が不可視）

集約先: ノート1コメント分のHTMLを生成する単一ソース（テンプレート部分 or JSモジュール）に寄せ、全画面が同じ表現を使う。

### C4. 🟡 判定ステータス日本語ラベル表が6ファイル重複（4→6箇所に訂正）
`{supported:裏付けあり, insufficient:情報不足, inconsistent:矛盾あり, not_applicable:該当なし}` がリテラルで `user-comments.js`(181) `vod_comments.html`(167) `user_comments.html`(350) `user_stats.html`(67)。

2026-07-02 追記でさらに2箇所: **`manual.html`(319, 371) がラベル一覧を文書として再掲**しており、**ステータス集合の真のマスタは `batch/scripts/generate_community_notes.py`(70) の `ALLOWED_STATUSES` ＋同義語正規化マップ**にある（app からは import されない別デプロイ）。つまり C1 と同型の **app↔batch 境界越え**でもある。ステータス追加時に6箇所更新が必要。集約先: サーバ側マスタ→テンプレ/JS/manual へ単一供給（batch の enum 定義と共有）。

### C5. ⚪ CNスコア5軸のラベル＋配色
`検証可能性/被害可能性/誇張度/根拠不足/主観度` と hex色が `user-comments.js`(193) `user_comments.html`(364-385) `user-stats.js`(68 チャート) に三重化。2026-07-02 追記: `manual.html`(351) にも軸名が文書として存在（4箇所目）。集約先: 軸定義（ラベル+色）の単一データ。

### C6. ⚪ ページング引数ボイラープレート
`page:int=Query(1,ge=1)` / `page_size:int=Query(N,ge=10,le=200)` が `vods.py` `comments.py` の各エンドポイントに反復し、上限200のマジックナンバーが散在。集約先: 共通 Depends/Pydantic パラメータ。

---

## 追加検証クラスタ（2026-07-01 全コード再走査）

全 `.py` / `.js` を「2ファイル以上で定義される同名関数」「同一 SQL / DOM 構築」で機械的に洗い出し、既存クラスタに含まれない 7 件を追加。傾向は明確: **①同一責務 SQL の app 内二重化、②描画クラスタの JS 層・Python 層への波及（C1/J2 の追跡漏れ）、③クライアント/util の boilerplate**。

### N1. 🔴 `count_user_comments` が app 内で二重実装
[`stats_repo.py`(9)](../app/repositories/stats_repo.py) と [`comment_repo.py`(682)](../app/repositories/comment_repo.py)。どちらも「ユーザー総コメント数 `COUNT(*) WHERE commenter_user_id = :uid`」。一方は `COUNT(*) AS cnt` + `.mappings().first()`、他方は `.scalar()`。用途（統計 / タスク API 資格チェック）で分かれているが**同一責務**。カウント条件（例: 論理削除・除外フィルタ）を足すと片方に取りこぼしが出る。P2 と同型の「別ファイル同一 SQL」。集約先: 単一のカウント関数。

### N2. 🔴 `appendSafeBodyHtml`（C1 のクライアント検証層＝body_html 描画の第3・第4実装）
[`user-comments.js`(137)](../app/static/js/user-comments.js) と [`quiz.js`(67)](../app/static/js/quiz.js)。emote 許可 URL `https://static-cdn.jtvnw.net/`・`class="emote"`・属性許可リスト `[class,src,srcset,alt,title,loading,decoding]` を**ハードコピー**。C1（app↔batch Python）と合わせ emote 描画仕様が **4 実装**に散在。**すでに分岐済み**——`user-comments.js` 版は `fallbackBody` 引数を持ち空 body 時に `textContent` で埋めるが、`quiz.js` 版は無し（body_html 空でノード生成されない）。C1 を直す際に JS 側も揃えないと表示が食い違う。集約先: C1 の共有モジュール化と同時に、JS 側も単一の sanitizer に統一。

### N3. 🟡 相対時刻文字列生成が Python にも存在（J2 のクロス層拡張）
[`comment_utils.py` `decorate_comment`(286)](../app/services/comment_utils.py) が `"{hours}時間{minutes}分前"` / `"{days}日前"` を生成（noscript フォールバック）。JS `formatRelativeTime`(J2) と**同じ表記を別実装**。丸め・閾値が乖離すると **JS 有効時と無効時で「○分前」が食い違う**。J2 は JS ファイルのみ、P9 は JST 変換手段のみを対象にしており、この「相対時刻の文字列化」は両方の網から漏れていた。集約先: 相対時刻文字列の生成ルールを 1 か所に定義し、noscript 用サーバ描画と JS が同じ閾値・丸めを使う。

### N4. 🟡 HTTP クライアント boilerplate（`_is_enabled` + `ping_*_api`）
[`faiss.py`(16)](../app/clients/faiss.py) と [`morpheme.py`(16)](../app/clients/morpheme.py) が `_is_enabled()`（URL→bool）と `ping_*_api()`（`/health` 確認、失敗時 `RuntimeError`）を**ほぼ同型で複製**。外部クライアントを足すたび増殖する型。集約先: 有効判定 + ヘルスチェックの共通基底/ヘルパ。

### N5. ⚪ `get_user_id` / `load_env` が app↔util で重複
`get_user_id` は [`twitch.py`(11)](../app/clients/twitch.py)・[`util/userid.py`(29)](../util/userid.py)・[`util/adduserid.py`(34)](../util/adduserid.py) の **3 実装**（署名分岐: env 読み vs 引数渡し、URL 文字列 vs `params={login}`、timeout 定数 vs 20 固定）。`load_env` は `util/` 3 ファイルに同一定義。Twitch users API 呼び出しの真実が分散。C1 同様 import 境界越えなので、util を独立 CLI として残すなら最低限「Twitch API 呼び出しの正」を 1 か所に。

### N6. ⚪ `showStatus` / `hideStatus`
[`vods.js`(38)](../app/static/js/vods.js) と [`users.js`(24)](../app/static/js/users.js) に**変数名以外同一**のペア。`buildCard` / `render` / `formatDate` / root_path も含め、この 2 ファイルは「無限スクロール・リストページ」の**兄弟実装**でページ骨格ごと平行進化している（J6 多重実行ガードと同根）。集約先: リストページ共通の状態表示・カード描画ヘルパ。

### N7. ⚪ ページングレスポンス / テンプレコンテキスト dict
[`comments.py`(197)](../app/routers/comments.py) と [`vods.py`(76)](../app/routers/vods.py) 他で `{page, pages, total, filters, root_path, ...}` の構築が反復。C6（**引数側**）の対になる**応答側**の重複。集約先: ページングメタの生成ヘルパ or Pydantic レスポンスモデル。

---

## リポジトリ全域クラスタ（2026-07-02 走査）

既存台帳のスコープは実質 `app/` + `batch/` だった。今回、これまで一度も対象になっていなかった `challenge/`（20ファイル）・`morpheme-sample/`・`util/`・`migrate/`・`faiss-api/`・`morpheme-api/`・`twicome-mcp-server/`・**CSS層**（14ファイル）を「2ファイル以上で定義される同名関数」「同一セレクタの複数定義」「env/接続ボイラープレート」で機械走査した。**シロ判定**も記録する: `zen/` はモジュール分割済みで重複なし、`twicome-mcp-server` は app への HTTP クライアントで SQL 重複なし、テストは `tests/integration/helpers.py` に seed 関数が集約済み。

### R1. 🔴 DB接続設定が3方式・9ファイルに分裂、デフォルト値がすでに分岐
| 方式 | 場所 | デフォルト |
|---|---|---|
| `DATABASE_URL` 一本 | `app/core/config.py` `get_database_url`(12) | 定数フォールバックあり |
| `DATABASE_URL` 一本（**同名関数の別実装**） | `migrate/migrations/env.py` `get_database_url`(17) | フォールバック無し・`.strip()` あり・エラー文言も別 |
| `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` 個別読み | `batch/scripts/` の `insertdb.py`(28) `backfill_comment_body_html.py`(17) `analyze_morphemes.py`(35) `build_faiss_index.py`(43) | host=`db`, db=`appdb`, パスワードのデフォルト無し |
| 同上（**別デフォルト**） | `morpheme-sample/` の `analyze_user_comments.py`(27) `word_ranking.py`(29) | **host=`localhost`, password=`apppass`, db=`appdb_dev`** |

batch 4スクリプトは `PROJECT_ROOT` / `ENV_PATH` の env 読みブロックまで同一コピー。接続先規約を変えると9ファイル修正になり、morpheme-sample はデフォルト分岐ですでに**別DBを向いて動く**。集約先: 接続設定の読み取りを共有モジュール1箇所に（少なくとも batch 内は共通 `db_config` に）。

### R2. 🔴 challenge/ の APIクライアント関数が14ファイルに同一コピー
`fetch_task` / `submit_answers` が `sentence_bert_utils.py` に共有実装として存在するのに、**非BERT系ベースライン12ファイル + `run_all.py` が同一コードを個別に再定義**（diff で完全一致を確認）。ほかに `predict` ×19 / `main`（argparse+実行フロー）×20 / `build_model` ×8 が同型ボイラープレート。クイズ API のパス・リクエスト形式（`/api/u/{login}/quiz/task`）を変えると**14箇所修正**。「ベースラインは1ファイル完結で配布したい」意図なら、その旨を本台帳と challenge/README に明記して CI ガード対象外にする（意図的コピーと事故コピーの区別を付ける）。そうでなければ `challenge/api_client.py` に集約。

### R3. 🟡 morpheme-sample のDB取得・API呼び出しが多重コピー（すでに分岐）
- `fetch_comments` が `analyze_user_comments.py`(36) `word_ranking.py`(41) `pipeline.py`(126) の**3実装**。SELECT 列（comment_id/body/created_at の有無）と **ORDER BY が DESC / DESC / ASC で分岐済み**。
- `call_analyze_api` が上記3ファイル + **`batch/scripts/analyze_morphemes.py`(96)** の**4実装**（完全一致を確認）。morpheme-api のリクエスト形式変更で4箇所修正、しかも sample↔batch の境界越え。
- `count_words` も `pipeline.py` / `word_ranking.py` で二重。

集約先: sample ディレクトリ内共通モジュール（batch との共有は C1 と同じパッケージ化課題）。

### R4. 🟡 Twitch OAuth `client_credentials` フローが3実装（N5の拡張）
N5 は `get_user_id`（helix/users）だけを見ていたが、**トークン取得 POST `id.twitch.tv/oauth2/token` + `grant_type=client_credentials`** も `util/tokens.py`(52) `util/refreshtoken.py`(105) `batch/scripts/get_vod_list_batch.py`(26) の3実装。Twitch 認証仕様変更・エラー処理改善（レートリミット等）が3箇所行き。N5 と合わせ「Twitch API クライアントの正」を1モジュールに。

### R5. 🟡 CSS層の重複（本台帳はこれまでCSSを完全に未対象）
- **ページヘッダ骨格**: `.page-header` `.page-header-inner` `.page-title` `.page-back` が `streamers.css`(15) `users.css`(15) `vods.css`(15) `vod_comments.css`(8) に**同一ルールで4重コピー**（先頭3ファイルは行番号まで一致）。
- **C2/J1 の CSS層**: `vod_comments.css`(215) が `base.css`(135) 定義済みの `.vote-btn` `.vote-controls` を再定義し、**すでに分岐**——base は角丸4px＋like緑/dislike赤の配色、vod版は pill(999px)・配色なし。`.comment` `.body` `.comment-head` も同様に vod だけ再定義。VODページの投票ボタンだけ見た目が別物。
- **C3 の CSS層**: CNノートのスタイルが `user_comments.css`(54-) は `.cn-note-*` 系、`vod_comments.css`(229-) は `.community-note` 系と**クラス名から分岐**。マークアップ統一（C3）の際に CSS も同時に1系統へ。

### R6. ⚪ users/vods 兄弟ページのフィルタUI（N6のテンプレ+CSS層）
`users.html`(23-35) と `vods.html`(23-35) の `filter-bar / filter-item / sort-select` マークアップが行番号まで一致するコピー。対応する `.filter-bar` `.filter-item` `.filter-select` ルールも `users.css` / `vods.css` に二重。N6（JS骨格）と合わせ、リストページ雛形（テンプレ・CSS・JS）を3層セットで共通化するのが正道。

### R7. ⚪ 同一ファイル内・サービス雛形の小規模重複
- `vod_comments.html`(108, 180): ページングブロック（前/次＋件数表示）が**同一ファイル内で上下に2回コピー**。マクロ化で1定義に（C6/N7 と同族）。
- `faiss-api/main.py` / `morpheme-api/main.py`: シングルトン＋`threading.Lock` の遅延初期化・`/health`・`startup` の雛形が同型（N4 のサーバ側対応物）。実害はないが、3つ目のAPIサービスを足すときに3重化する。

---

## 優先順位（バグ密度 × 影響範囲）

| 順位 | クラスタ | 理由 |
|---|---|---|
| 1 | C1 body_html renderer (app↔batch) ＋ N2 JS sanitizer | version 定数まで二重定義。描画分岐がキャッシュ無効化されずサイレントなデータ不整合に直結。実測でコメント行の分岐を確認。emote 仕様は Python2 + JS2 の計4実装 |
| 2 | J1 投票ウィジェット ＋ C2 投票markup | 既存 fix がvod画面に未反映、チャンク欠落で表示破綻の芽。初期markupも3テンプレに散在 |
| 3 | J2 時刻整形 ＋ N3 Python 相対時刻 | 9h/1日ズレの再発源。引数仕様まで分岐。noscript フォールバックが JS と別実装で「○分前」が食い違いうる |
| 4 | P2 ORDER BY ビルダ / N1 count_user_comments | ページング重複/欠落の再発源。fixを毎回N重に適用中。N1 は同一 COUNT を app 内2実装 |
| 5 | C3 CNノート描画 / P1 SELECT列 / P4 search内重複 | C3はvod/clusterで表示欠落・分岐済み（CSSもクラス名から分岐 → R5）。P1は列追加時の取りこぼし、即効性高 |
| 6 | P10 危険度式 / C4 ステータスラベル / R1 DB接続設定 | 画面間で値・表記が食い違う潜在不整合（C4はbatchマスタ含め6箇所）。R1はデフォルト値がすでに分岐し別DBを向く |
| 7 | R2 challenge APIクライアント / R3 morpheme-sample / R4 Twitchトークン | 本体の挙動には響かないが、API変更時に最大14箇所修正。意図的コピーなら明文化して除外 |
| 8 | J3/J4/J5/J6, P3/P5/P6/P7/P8/P9, C5/C6, N4/N5/N6/N7, R5/R6/R7 | 体裁・保守性。ついでに回収 |

## 再増殖の防止（これが無いと必ず戻る）

1. **物理的に1箇所へ**: JSは共通モジュール import 必須、Pythonは utils/constants 参照必須。app↔batch のように import 境界をまたぐものは共有モジュール（パッケージ化）で1定義に。
2. **CIガード**: 「同名関数が2ファイル以上で定義されたら fail」する grep ベースの軽量チェックを1本追加（例: `function vote(` / `def _parse_int` / `def count_user_comments` / `normalizeUtcIso` / `function appendSafeBodyHtml` / `def fetch_task` / `def call_analyze_api` / `def get_database_url` の重複検出）。加えて (a) `BODY_HTML_RENDER_VERSION` が単一ファイルでしか定義されないこと、(b) 投票ボタン/CNノートの markup・JA ステータスラベル表がテンプレと JS に二重定義されていないこと、(c) emote 許可 URL `https://static-cdn.jtvnw.net/` / `class="emote"` 属性許可リストが JS 2 箇所以上に現れないこと、(d) `MYSQL_HOST` の os.getenv 直読みが共有モジュール以外に現れないこと、を検出する。challenge/ のような**意図的な1ファイル完結コピー**は除外リストで明示し、事故コピーと区別する。
3. **修正フロー**: 「ある処理を直したら兄弟実装を grep で探す」を PR チェックリスト/フックに明文化。**特にレイヤをまたぐ描画（Jinjaテンプレート ↔ JS、app ↔ batch）は見落としやすいので明示的に確認する**。
4. **集約はテスト先行・1クラスタずつ**: big-bang リファクタは禁止。回帰テストで挙動を固定 → 共通化 → 各呼び出し差し替え。

## 次アクション

防止策の具体設計（CIガード実装・ラチェット方式・意図的コピー登録簿）と修正の進め方（層別の集約手段・分岐解消の原則・ロードマップ）は **[duplication-remediation-strategy.md](duplication-remediation-strategy.md)** に確定した。旧「次アクション候補」の A/B/C 択は B（ガード先行）→ A（クラスタ着手）の順で同書 Phase 0〜1 に置き換え。
