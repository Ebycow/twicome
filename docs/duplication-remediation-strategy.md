# 重複の再増殖防止と修正・対応方針

作成日: 2026-07-02（2026-07-03 検証反映）
前提: [duplication-inventory.md](duplication-inventory.md)（重複クラスタ棚卸し、38クラスタ）の「再増殖の防止」節を具体化し、修正の進め方を決める文書。台帳が**何があるか**の記録なのに対し、本書は**どう直し、どう戻さないか**を扱う。本書の主張・前提は 2026-07-03 に独立検証され、4点の修正が入った——証拠と根拠は [duplication-verification-and-critique.md](duplication-verification-and-critique.md)（以下「検証編」）を参照。

---

## 1. なぜ再増殖するのか（根本原因の考察）

対策を設計する前に、36クラスタが「なぜ生まれ、なぜ放置すると必ず戻るのか」を構造・プロセス・検出の3面から特定する。原因に対応しない防止策は形骸化する。

### 1-1. 構造的原因: コピーする以外の選択肢が無かった箇所がある

- **app↔batch の import 境界**: `app/Dockerfile` はビルドコンテキストが `./app` で、**プロジェクトルート外のファイルを COPY できない**。batch は独立デプロイで app を import できない。C1（body_html レンダラ）が「バイト単位で同一の2ファイル」になったのは怠慢ではなく、**共有する物理的手段が用意されていなかった**から。同型の境界が util/（独立CLI群）、morpheme-sample/ にもある（R1/R3/R4/N5）。
- **JS にモジュール機構が無い**: バンドラ無しの素の `<script>` 読み込みで、各ファイルが IIFE で閉じている。共有ヘルパを「import する」手段が無いので、`escapeHtml` も `formatRelativeTime` も**書くたびにコピーするのが最も摩擦の低い行動**だった（J1〜J6, N2, N6）。なお `zen-mode.js` だけ `type="module"` で読まれており、ES modules は既に動く前例がある。
- **SSR + CSR の二重描画アーキテクチャ**: 初期表示は Jinja、追加読み込み・動的更新は JS が innerHTML を組む。**同じ markup の定義が構造上2回必要**になり、投票ボタン（C2）・CNノート（C3）・ステータスラベル（C4）はこの必然の産物。これは「サボったコピー」ではなく**設計が要求したコピー**であり、grep 注意喚起だけでは絶対に防げない。

### 1-2. プロセス的原因: LLM駆動開発はコピーを増幅する

このリポジトリは LLM 主導で開発されている。LLM は「コンテキストに見えている実装に似せて書く」ため、(1) 既存ヘルパを探すより手元に複製する方向に強く倒れ、(2) バグ修正時は**報告された1ファイルだけを直して完了と判断する**。git 履歴がそのまま証拠になっている:

- 9時間ズレ修正 `2bda22b` と1日ズレ修正 `394356e` — **同一バグを別ファイルで別々に修正**（J2）
- ページング一意キー修正 `f71a655`（comments）と `6ad9a5b`（vods）— **同じ修正を2つの ORDER BY ビルダに個別適用**（P2）
- 連打修正 `fd0cc33`/`f5936fd` — user-comments には入ったが **vod-comments には今も未反映**（J1）

つまり「修正が N 箇所のうち 1 箇所にしか当たらない」事故はすでに**最低3回**起きており、確率の問題ではなく再現性のあるプロセス欠陥である。

2026-07-03 の定量分析（検証編 §1）でこれを裏付けた: 兄弟ファイル群を触るコミットのうち**一部だけを触るコミットが J1 で 96%、C3 で 98%、P2 で 92%** を占める。さらに C1 の考古学から決定的な教訓が出た——分岐コメントを導入した `0ca20a1` は**両ファイルを同時に触りながら片方にだけ変更を入れていた**。「同時に触る」ことと「同一に保つ」ことは別物であり、co-change 規律（Layer 3）では分岐を防げない。内容 diff を照合する Layer 2.5 が構造的に必須である根拠がここにある。なお LLM 駆動開発が重複を増幅する傾向は業界データ（[GitClear 2025](https://www.gitclear.com/ai_assistant_code_quality_2025_research): 重複ブロック8倍、リファクタ行 24.1%→9.5%）とも整合し、「分岐が欠陥を生む」テーゼには [Juergens et al. ICSE 2009](https://dl.acm.org/doi/10.1109/ICSE.2009.5070547)（クローンの52%が不整合変更、非意図的不整合の約半分が欠陥）という古典的実証がある（検証編 §4）。

### 1-3. 検出の欠如: 増えても誰も気づかない

CI（`.github/workflows/ci.yml` / `ci-local.sh`）は compile / lint / test を持つが、**重複を検出するステップが1つも無い**。P9 は台帳作成からわずか数日で ×4→×5 に増殖したが、何のアラートも出ていない。lint は「1ファイルの中の正しさ」しか見ないので、重複はどのゲートにも引っかからない。

### 1-4. 教訓（本書の全ての判断の基礎）

> **危険なのは重複ではなく分岐である。そしてコピーは書かれた瞬間から必ず分岐を始める。**

C1 のコメント行分岐、C3 のスコアバー欠落、R1 の接続デフォルト分岐、R5 の vote-btn 見た目分岐——観測された分岐は全て「同一だったコピー」の成れの果て。よって対策の優先目標は（a）コピーを1定義に潰すこと、それが直ちにできない場合は（b）**分岐した瞬間に CI が落ちる**ようにすることの2段構えになる。

---

## 2. 防止策: 4層の多重防御

単一の対策では戻る。原因3つ（構造・プロセス・検出）にそれぞれ対応させ、さらに「意図的コピー」を明示的に管理する。

### Layer 1 — 物理集約（構造への対策）

「参照する方がコピーより楽」な状態を作る。具体的な集約手段は §3 の修正方針で層別に定める。ここでの原則は1つ:

- **集約先が無いままコピー禁止令だけ出さない。** 共有モジュール・マクロ・データ供給経路を先に用意し、コピーの動機を消す。

### Layer 2 — CIガード + ラチェット方式（検出への対策）

`ci/check-duplication.sh` を新設し、GitHub Actions の Lint ジョブと `ci-local.sh` のステップ（`lint-css` の後に `dup-check`）に組み込む。設計の核心は**ラチェット（逆戻り防止爪）方式**:

1. **ベースライン凍結**: 現存36クラスタの重複シンボルを `ci/duplication-baseline.txt` に「シンボル → 許容ファイル集合」として全件記録する。既存の重複では CI は落ちない（いきなり全部直すことを要求しない）。
2. **新規増殖で fail**: ベースラインに無いファイルに既知シンボルが現れたら fail。P9 の ×4→×5 のような無自覚な増殖をその PR の時点で止める。
3. **解消したら締める**: クラスタを共通化した PR でベースラインから該当行を削除する。**削除した行は二度と増やせない**（爪が掛かる）。ベースライン行数がそのまま「残債」のメトリクスになる。

検出内容（台帳の防止策2を実装に落としたもの）:

```bash
# (a) 同名関数の複数ファイル定義（Python / JS）
#     grep -rn '^(async )?def <sym>\(' / '^\s*(async )?function <sym>\(' を
#     シンボル台帳と突き合わせ、許容集合外のファイルが出たら fail
#     対象例: vote, flushVote, appendSafeBodyHtml, escapeHtml, spawnConfetti,
#             normalizeUtcIso, formatRelativeTime, formatDate, showStatus,
#             _parse_int, count_user_comments, fetch_task, submit_answers,
#             call_analyze_api, fetch_comments, get_database_url, get_user_id, load_env
# (b) 単一定義であるべき定数: BODY_HTML_RENDER_VERSION が 2 ファイル以上で「= 数値」定義されたら fail
# (c) リテラルの散在検出: 'static-cdn.jtvnw.net'（許容: 共有 sanitizer, middleware CSP, sw.js の3箇所のみ）、
#     '裏付けあり'（JAステータスラベル）、'os.getenv("MYSQL_HOST"'（許容: 共有 db_config のみ）
# (d) CSS: '^\.page-header \{' '^\.vote-btn' 等の複数ファイル定義
```

grep ベースで十分。AST 解析や類似度検出（jscpd 等）は偽陽性の調整コストが高く、この規模ではシンボル台帳の方が確実に運用できる。将来余力があれば jscpd を「参考レポート（non-blocking）」として併走させるのは可。

2026-07-03 実証（検証編 §2）: AST 正規化ハッシュで全 Python 関数を走査した結果、**本番コードに改名クローンは存在せず**、同名 grep 方式で現状の全クローンを捕捉できることを確認した。ただしこの性質は時限的（成熟ライブラリでは改名クローンが大量発生する型を対照群で観測）なので、走査スクリプトを `ci/clone_scan.py` としてコミットし、**月次棚卸しを non-blocking の機械走査で行う**。この走査は同名 grep が見落としていた T1（テスト conftest）・M1（指示ファイル）を実際に発見しており、棚卸しの網羅性を人手より高くできる。

### Layer 2.5 — 同期ガード（分岐だけを先に殺す中間形態）

物理集約が重い箇所（特に C1 の app↔batch）に対し、**集約完了までの暫定措置**として「コピーは許すが分岐したら fail」を入れる:

```bash
# comment_body_html.py が comment_utils.py の該当関数群と一致しなければ fail
python ci/check_sync.py app/services/comment_utils.py batch/scripts/comment_body_html.py \
  --symbols parse_raw_comment _sanitize_emote_text normalize_emote_id render_comment_body_html \
            EMOTE_URL_TEMPLATE EMOTE_ID_PATTERN BODY_HTML_RENDER_VERSION
```

C1 で実測された「コメント行だけの分岐」はこのガードなら即日検出できた。**Phase 0（§4）で最優先に入れる**。ただしこれは鎮痛剤であって治療ではない——同期ガードを入れたクラスタも必ず物理集約のロードマップに残す。

2026-07-03 補強（検証編 §1-1）: C1 の考古学で「共有シンボルを触る全コミットが両ファイルを co-change していたのに分岐した」ことが判明。同期ガードはプロセス規律の劣化に備える保険ではなく、**プロセス規律では原理的に防げない分岐（同一コミット内の非対称変更）を捕まえる唯一の層**である。

### Layer 3 — プロセス（LLM駆動開発への対策）

- **CLAUDE.md に修正フローを明文化する**（2026-07-03 訂正: 「唯一の場所」は誤り——`AGENTS.md` が CLAUDE.md の Test 節の逐語コピーとして並存している＝台帳 M1。ルールの正本は CLAUDE.md に置き、AGENTS.md は参照1行に畳む。指示ファイル自体を分岐させない）:
  1. バグ修正の前に、対象シンボル・SQL断片・markup を **grep して兄弟実装を列挙**する（台帳の該当クラスタを見る）
  2. 兄弟がいる場合、**全コピーに同時適用**するか、適用しない理由を PR に明記する
  3. **レイヤをまたぐ描画（Jinja↔JS、app↔batch、CSS の base↔ページ）は特に確認**——見落とし実績が最も多い境界
  4. 新しいヘルパを書く前に、同名・同責務の既存実装を grep する
- PR テンプレート（`.github/PULL_REQUEST_TEMPLATE.md`）に「[ ] 兄弟実装を grep で確認した / 該当クラスタ: 」のチェック項目を置く。
- **兄弟リマインダーフック（2026-07-03 追加、検証編 §5-4）**: 既存の PostToolUse lint フック（`.claude/hooks/post_tool_lint.sh`）と同じ機構で、編集ファイルを `ci/duplication-baseline.txt` のクラスタ表と突き合わせ「このファイルには兄弟がいる: …」を編集直後に自動注入する。これで「思い出させる」がLLMの注意力・CLAUDE.md 読了に依存しなくなり、baseline は CI ガード入力と LLM 向け兄弟インデックスの二役を担う単一の真実になる。
- Layer 2 の CI ガードがあるため、プロセス層は「思い出させる」役割で良い。**人（LLM）の注意力を最後の砦にしない**のが設計思想（フック化により Layer 3 自体にもこの思想を適用する）。

### Layer 4 — 意図的コピーの登録簿（例外の明示管理）

全てのコピーが悪ではない。**「事故コピー」と「意図的コピー」を区別できないガードは、例外だらけになって死ぬ**。`ci/duplication-baseline.txt` とは別に、意図的なものは台帳へ理由付きで登録する:

| 対象 | 理由 | 扱い |
|---|---|---|
| `challenge/` の `fetch_task`/`submit_answers` ×14 | ベースラインは参加者への配布物であり**1ファイル完結が仕様**（コピペで動くことが価値） | ガード除外。ただし**同期ガード対象**（`sentence_bert_utils.py` を正として diff 一致を要求）にし、API 変更時は一括 sed で同期する運用を challenge/README に明記 |
| `migrate/migrations/versions/` の `upgrade`/`downgrade` | Alembic の規約 | ガード対象外（パス除外） |
| `sw.js` の root_path 正規化 | Service Worker は DOM を読めず、スコープから導出するしかない | 現状維持。正規化仕様の変更時に追随することを台帳 J3 に記載済み |
| `zen/` のモジュール群 | すでに ES modules で分割済み・重複なし | 対象外（むしろ他 JS の集約の手本） |

---

## 3. 修正・対応方針（層別の考察）

### 3-0. 大原則

1. **テスト先行・1クラスタ1PR**。回帰テストで現挙動を固定 → 共通実装を追加 → 呼び出しを1つずつ差し替え → 旧実装削除 → ベースラインから削除。big-bang リファクタは禁止（台帳の防止策4を維持）。
2. **「分岐の解消」は機能変更として扱う**。分岐済みクラスタの共通化は、どちらかの挙動を「正」に選ぶ意思決定を含む（例: J1 で vod-comments に debounce を入れる＝挙動が変わる）。**リファクタ PR と挙動統一 PR を分けるか、PR 内で「正とした挙動と根拠」を明記**する。無言で挙動を変えない。
3. **正の選定基準**: 過去の fix が最も反映されている実装を正とする（J1 なら cluster-comments のチャンク+debounce 版、J2 なら normalizeUtcIso 系）。fix の再消失が最悪の結果だから。
4. 完了（Done）の定義: (a) 実装が物理的に1箇所 (b) 全呼び出しが差し替え済み (c) ベースラインから削除済み (d) 回帰テスト green (e) 分岐解消があった場合はその決定が PR に記録されている (f) デプロイ単位をまたぐ集約（app↔batch）では、両サービスの再ビルド・再デプロイ手順と backfill 要否が README/CLAUDE.md に記録されている——の6点。(f) の根拠: 単一定義はコード分岐を消すが**デプロイ分岐は消さない**。片方だけ再デプロイされた期間は実行バイナリのレベルで二重実装が復活する（検証編 §5-2）。

### 3-1. Python: app 内（P1〜P8, P10, N1, N3）

最も単純。`services/`・`repositories/` 内に集約先モジュールを作り import するだけで、ビルドもデプロイも変わらない。

- P1: `comment_utils` に `COMMENT_LIST_COLUMNS` 定数 + JOIN 句ヘルパ。`build_comment_body_select_sql` という**成功済みの前例**があるので同じ型を踏襲する。
- P2: タイブレーカー必須を**型で強制**する単一ビルダ（`build_order_by(sort_key, *, tiebreaker: str)` — tiebreaker をキーワード必須引数にし、忘れられない API にする）。
- P10: 危険度の算出式と **NULL 欠損ポリシーを1関数 + 対応する SQL 断片**として定義（Python 側 `danger_score(row) -> int | None`、SQL 側は式文字列定数）。5者5様の現状は「どれが正か」の意思決定が必要——推奨は「**4軸いずれか NULL なら判定不能（バッジ非表示・集計除外）**」で全画面統一。0 扱い（過小評価）はミスリードだから。

### 3-2. Python: app↔batch 境界（C1, C4, R1, R3, R4, N5）

import 境界を越える唯一の正攻法は**共有パッケージ**。実装手段は3案:

| 案 | 内容 | 評価 |
|---|---|---|
| (a) `shared/` パッケージ + ビルドコンテキスト変更 | ルートに `shared/twicome_shared/` を作り、app/batch 両 Dockerfile が COPY。app は compose の `build: ./app` を `context: ., dockerfile: app/Dockerfile` に変更 | ~~推奨~~ **2026-07-03 検証で降格**（検証編 §5-1）: `build: ./app` は dev 4 + prod 1 の**5サービス定義**に散在し、ルートコンテキストは `challenge/.venv`（実測 **7.6GB**）を含む。`.dockerignore` の `.venv` はルート相対でこれにマッチしない |
| **(a') `additional_contexts`（新・推奨）** | compose（本環境 5.1.4、2.17+ で対応）の `build.additional_contexts: {shared: ../shared}` を app に追加し、Dockerfile で `COPY --from=shared`。context は `./app` のまま | **推奨**。5サービスのコンテキスト変更も 7.6GB 問題も回避して真の単一定義を得る。案(b) の「依存の向きの不自然さ」も無い |
| (b) batch が app から COPY | batch/Dockerfile（コンテキストはルート）が `COPY app/services/comment_utils.py` | 変更最小だが、「app のモジュールに batch が依存」という不自然な向き。app 側の無関係な変更が batch を壊しうる。暫定としては可 |
| (c) コピー維持 + 同期ガード | Layer 2.5 | 治療ではない。Phase 0 の止血専用 |

なお shared 化と独立に、`.dockerignore` へ `**/.venv` / `node_modules` / `challenge/` を**即日追加**する（batch は既にルートコンテキストであり、BuildKit の遅延転送で顕在化していないだけの地雷）。

推奨手順（C1、2026-07-03 に順序修正）: ① `render_comment_body_html` の golden test（入力 raw_json → 出力 HTML のスナップショット）を app/batch 双方の実装に対して走らせ一致を確認——`test_generate_community_notes.py` が `importlib.util.spec_from_file_location` で batch スクリプトをロードする**既存前例**をそのまま流用でき、パッケージ化を待たず即日書ける → ② 同期ガード投入（テストが先にあればガード導入自体が安全） → ③ `shared/` へ移動（案a'）、両者を import に差し替え → ④ ガードを「shared 以外での定義禁止」に切り替え。**併せて renderer↔sanitizer の恒等 property test**（`sanitize_body_html(render(...)) == render(...)`）を追加する——emote 仕様は実は5実装（app の `_BodyHtmlSanitizer` 含む、台帳 C1 訂正）で、レンダラ出力がサニタイザ許可リストを通過するという暗黙契約が明文化されていない（検証編 §3）。
**併せて運用ルールを明文化**: レンダラの出力に影響する変更は `BODY_HTML_RENDER_VERSION` インクリメント + `backfill_comment_body_html.py` 実行をセットで行う（version を上げ忘れると C1 の本文で警告した「サイレント不整合」が単一実装でも起きる）。

- C4 は shared に `NoteStatus` enum（キー・JA ラベル・同義語正規化を1定義）を置き、batch の `ALLOWED_STATUSES` と app のラベル表を両方これに差し替える。JS/テンプレへの供給は §3-4。
- R1 は shared に `db_config.py`（`DATABASE_URL` 優先、無ければ `MYSQL_*` から合成、デフォルトは1箇所で定義）。morpheme-sample の `appdb_dev` 向きデフォルトは**分岐ではなく事故**とみなし、明示的な env 指定に置き換える。
- R4/N5 は shared に `twitch_client.py`（token 取得 + helix/users）。util/ を独立 CLI として残す場合も、共有パッケージを pip install -e で参照できる。

### 3-3. JS: モジュール化の戦略（J1〜J6, N2, N6）

バンドラ導入は現状の規模ではオーバーキル。**ES modules（`type="module"`）へ段階移行**する。`zen-mode.js` が既に module で動いており、対応ブラウザ・配信・SW キャッシュとも実績がある。

- 新設する共有モジュール: `static/js/lib/time-format.js`（J2+正規化）、`static/js/lib/vote-widget.js`（J1、チャンク+debounce 版を正とする）、`static/js/lib/dom.js`（escapeHtml / appendSafeBodyHtml / spawnConfetti）、`static/js/lib/root-path.js`（J3）、`static/js/lib/list-page.js`（N6+J6、無限スクロール骨格）。
- ページエントリ（user-comments.js 等）を1本ずつ `type="module"` に切り替えて import する。IIFE のまま残るページとの共存は問題ない（グローバルを共有していないため）。
- 注意: module 化すると `window.vote` のような**グローバル関数に依存した inline `onclick` が壊れる**。vod-comments.js の `window.vote` がこの形。差し替え時は `addEventListener` + `data-*` 属性に移行する（これは J1 の「正の実装」がすでに採っている方式）。
- `?v={{ static_version }}` のキャッシュバスティングは **import 先の URL にも必要**。`import './lib/dom.js'` は version が付かず古いキャッシュを掴む恐れがあるため、importmap を base.html に置いて version 付き URL に解決させるか、SW のキャッシュ戦略（現状 git hash 連動）で吸収するかを Phase 2 の最初に決める。ここを曖昧にすると「CSS が反映されない」問題（CLAUDE.md 記載）の JS 版を作ることになる。

### 3-4. Jinja↔JS 二重描画（C2, C3, C4, C5, P10 の表示側）

**最重要の設計判断**。同じ markup をサーバとクライアントが別々に持つ限り、ここは何度直しても分岐する。選択肢は3つ:

| 案 | 内容 | 評価 |
|---|---|---|
| (i) JS が HTML を組むのをやめ、サーバから partial HTML を fetch | 追加読み込み API が JSON でなく描画済み HTML 断片を返す | 一貫性は最強だが API 設計の変更が大きく、クイズ等 JSON を使う画面と二重規約になる |
| (ii) `<template>` タグ方式 | Jinja マクロで定義した markup を `<template id="vote-buttons-tpl">` としてページに1回出力し、**JS は cloneNode して値を流し込むだけ**にする | **推奨**。markup 定義が Jinja マクロ1箇所になり、JS から innerHTML 組み立てが消える。既存構成への侵襲が最小 |
| (iii) 二重維持 + golden test | サーバ描画と JS 描画の出力一致をテストで強制 | テストが分岐を検出はするが、二重実装の保守コストは残る。**(ii) の補完として常設する**（下記） |

2026-07-03 補足（検証編 §5-3）: (ii) でも**データバインディングの重複は残る**——どの値をどのスロットへ流すかは、Jinja のマクロ引数展開と JS の cloneNode 後代入の2箇所に分かれたままで、スロット追加時に C3 型の分岐がバインディング層で再発しうる。緩和策: スロットのアドレッシングを `data-field="vote-count"` のような単一の属性体系に統一（Jinja/JS とも同じ `data-field` を埋める/引く）し、(iii) の golden test（サーバ描画 vs JS 描画の DOM 一致）を**代替でなく補完として併用**する。

- C2（投票ボタン）: Jinja マクロ `vote_buttons(comment)` を新設 → 3テンプレのハードコピーをマクロ呼び出しに → 同マクロで `<template>` を出力し、`vote-widget.js` が clone。
- C3（CNノート）: 同じく `community_note(comment)` マクロ + template。**分岐の解消判断が必要**: スコアバーと `cn_model` 表記は user_comments 版を正とし、vod にも出す。cluster-comments がノートを描画しない件は「意図的省略か欠落か」を決めてから（台帳 C3 の記載どおり欠落の可能性が高い）。
- C4/C5/P10 のデータ（ラベル・閾値・配色・式）: **サーバを唯一の起点**にする。Python 定数 → Jinja へは context、JS へは `<script type="application/json" id="app-cn-config">` で供給。`app-root-path` という**既存の成功パターン**があるので同じ型で増やす。manual.html の文書記載は自動化しない（文章なので）——代わりにガード (c) のリテラル検出で乖離時に気づけるようにする。

### 3-5. CSS（R5, R6）

- 共通コンポーネント（page-header 系、vote-btn、comment カード、CNノート、filter-bar）は **base.css に1定義**し、ページ CSS は本当にページ固有の差分だけを持つ。cluster_comments.css が既にこの方式（コメントで base 参照を明示）なので、これを標準とする。
- vod_comments.css の vote-btn 再定義は**分岐の解消判断が必要**: base の見た目（角丸4px + like/dislike 配色）を正とし、VOD ページの pill 形状は意図的デザインなら `.vod-page .vote-btn` の差分オーバーライドとして明示、意図でないなら削除。「同名クラスの全面再定義」だけを禁止する。
- CNノート CSS のクラス名分岐（`.cn-note-*` vs `.community-note`）は C3 のマクロ統一と**同一 PR で**片方に寄せる（markup とスタイルを別 PR にすると中間状態が壊れる）。

### 3-6. 周辺ディレクトリ（R2, R3, N4, R7）

- R2（challenge/）: §2 Layer 4 のとおり**意図的コピーとして明文化 + 同期ガード**。集約はしない。
- R3（morpheme-sample/）: サンプルコードなので優先度は低いが、`call_analyze_api` は batch と共有（shared の morpheme クライアントへ）。`fetch_comments` の ASC/DESC 分岐は用途差か事故かを確認して README に記録。
- N4/R7（faiss-api/morpheme-api）: 2サービス間の共通基盤化はサービスが3つになるまで待つ（早すぎる抽象化のコストの方が高い）。台帳に記録済みであることが現時点の対策。

---

## 4. ロードマップ

| Phase | 内容 | 対応クラスタ | 目安 |
|---|---|---|---|
| **0. 止血** | `ci/check-duplication.sh` + ベースライン凍結 + C1/challenge の同期ガード（golden test 先行、§3-2 手順①②） + CLAUDE.md/PR テンプレのフロー明文化 + **M1 解消（AGENTS.md 参照化）・`.dockerignore` 修正・`ci/clone_scan.py` コミット・兄弟リマインダーフック**（2026-07-03 追加分） | 全クラスタの増殖停止・分岐検出 | 半日〜1日。**他の全 Phase に先行** |
| **1. body_html 統一** | shared/ パッケージ新設（**additional_contexts 方式=案a'**）、golden test → C1 統合 + renderer↔sanitizer 恒等 property test、JS sanitizer（N2）も同一仕様に | C1, N2 | 台帳優先順位1位 |
| **2. 投票ウィジェット** | importmap/キャッシュ方針決定 → `lib/vote-widget.js`（チャンク+debounce を正）→ C2 マクロ+template 化 → vod-comments 差し替え（挙動統一を明記） | J1, C2 | 優先順位2位 |
| **3. 時刻整形** | `lib/time-format.js` + N3 のサーバ側閾値を JS と共通定義から生成 | J2, N3 | 優先順位3位 |
| **4. SQL ビルダ** | P2 タイブレーカー必須ビルダ、N1 カウント統合、P1 列定数。**併せて T1（テスト conftest 4フィクスチャ）を共通化**——このPhaseはテストを厚く触るため同時回収が効率的 | P2, N1, P1, T1 | 優先順位4〜5位 |
| **5. CN 表示系** | C3 マクロ + CSS 統一（R5 の CN 分）、C4/C5/P10 のデータ駆動化 | C3, C4, C5, P10 | 優先順位5〜6位 |
| **6. 基盤整理** | R1 db_config、R4/N5 twitch_client、残りの ⚪ 回収 | R1, R4, N5, ほか | 優先順位6位以下 |

各 Phase 完了時にベースラインを縮め、台帳の該当クラスタに「解消済み（コミットハッシュ）」を追記する。**台帳・ベースライン・コードの3点が常に一致している状態**を維持する。

---

## 5. リスクと注意点

- **共通化そのものが挙動変更になる罠**: 分岐済みクラスタでは「共通化＝どちらかの挙動の採用」。§3-0 原則2を徹底し、正の選定を必ず PR に書く。テストが無い画面（vod-comments 等）は先に UI テストを足してから触る。
- **キャッシュ3層との相互作用**: static_version（git hash）・SW キャッシュ・保存済み body_html。特に Phase 1 は `BODY_HTML_RENDER_VERSION` の運用ルール（§3-2）を、Phase 2 は JS module の version 付与（§3-3）を先に決めてから実装する。
- **ガードの偽陽性で無効化される危険**: ガードが誤検知でうるさいと `--no-verify` 文化が生まれ全てが無に帰す。シンボル台帳方式は「自分で列挙したものしか検出しない」ので偽陽性がほぼ出ない——**検出範囲の狭さは意図した設計**であり、網羅性は台帳の定期棚卸し（次回 2026-08 目安）で補う。
- **ベースラインの風化**: ラチェットは「解消時に削除する」運用が止まると単なる例外リストになる。§3-0 の Done 定義 (c) を PR レビューで確認する。
- **文書群自体の重複と分岐（2026-07-03 追加）**: 台帳・本書・検証編の3文書にクラスタの事実が散在し始めており、コードと同じ分岐力学が文書にも働く（M1 が最小例）。原則: **機械検証可能な事実（シンボル・ファイル集合・許容例外）の正本は `ci/duplication-baseline.txt`**、文書はクラスタ ID と考察のみを持つ。台帳の「現存確認」は `ci/clone_scan.py` の定期実行で自動化する（検証編 §6）。

## 6. 次アクション

1. Phase 0 を実施する（本書と台帳を正として `ci/check-duplication.sh`・ベースライン・同期ガード・CLAUDE.md 追記・PR テンプレを作る）
2. Phase 1 に着手する前に、shared/ パッケージ案（§3-2 案(a)）の compose/Dockerfile 変更を dev 環境で検証する
3. 台帳の「次アクション候補」は本書のロードマップに置き換える（A/B/C 択は B→A の順で確定）
