# Twicome MCP Server

Twicome の HTTP API を [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) ツールとして公開するサーバー。
Claude などの AI クライアントから Twicome のコメントデータを自然言語で検索・取得できるようになります。

## セットアップ

```bash
cd twicome-mcp-server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 設定

### 環境変数

| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|-----------|------|
| `TWICOME_BASE_URL` | 任意 | `http://localhost:8000/twicome` | Twicome API のベース URL |
| `CF_CLIENT_ID` | 任意 | — | Cloudflare Access サービストークンのクライアント ID |
| `CF_CLIENT_SECRET` | 任意 | — | Cloudflare Access サービストークンのシークレット |

Twicome が Cloudflare Access で保護されている場合は `CF_CLIENT_ID` / `CF_CLIENT_SECRET` を設定してください。

### Claude Desktop / Claude Code への登録

`claude_desktop_config.json`（Claude Desktop）または Claude Code の MCP 設定に追加します。

```json
{
  "mcpServers": {
    "twicome": {
      "command": "/path/to/twicome-mcp-server/.venv/bin/python3",
      "args": [
        "/path/to/twicome-mcp-server/server.py"
      ],
      "env": {
        "TWICOME_BASE_URL": "https://example.com/twicome/",
        "CF_CLIENT_ID": "",
        "CF_CLIENT_SECRET": ""
      }
    }
  }
}
```

パスは絶対パスで指定してください。Cloudflare Access を使用しない場合は `CF_CLIENT_ID` / `CF_CLIENT_SECRET` を省略できます。

## 提供ツール

### `get_user_comments`

ユーザーのコメントをキーワード検索・フィルタリングして取得します。

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `login` | string | 必須 | コメンターのログイン名 |
| `q` | string | — | テキスト検索クエリ（部分一致） |
| `exclude_q` | string | — | 除外キーワード（カンマ区切りで複数指定可） |
| `vod_id` | string | — | VOD ID でフィルタ |
| `owner_user_id` | string | — | 配信者の user_id でフィルタ |
| `page` | int | `1` | ページ番号 |
| `page_size` | int | `50` | 1ページの件数（10〜200） |
| `sort` | string | `created_at` | ソート順: `created_at` / `likes` / `dislikes` / `community_note` / `danger` / `random` |

### `get_commenters_for_streamer`

指定した配信者の VOD にコメントしたユーザー一覧を取得します。

| パラメータ | 型 | 説明 |
|-----------|-----|------|
| `streamer` | string | 配信者のログイン名 |

### `similar_search_comments`

埋め込みベクトル（FAISS）を使い、意味的に類似したコメントを検索します。
キーワード検索では拾えない言い換えや類義語も検索できます。

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `login` | string | 必須 | コメンターのログイン名 |
| `q` | string | 必須 | 意味検索クエリ |
| `top_k` | int | `20` | 取得件数（1〜100） |
| `diversity` | float | `None` | MMR 多様性パラメータ（0.0〜1.0）。`None`=通常検索、`0.5`=バランス重視、`1.0`=最大多様性 |

> FAISS インデックスが未構築のユーザーはエラーになります。

### `centroid_search_comments`

全コメントの重心（平均ベクトル）からの距離でソートし、「典型的」または「珍しい」コメントを探します。

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `login` | string | 必須 | コメンターのログイン名 |
| `position` | float | `0.5` | 重心距離のパーセンタイル（0.0=最も典型的 〜 1.0=最も珍しい） |
| `top_k` | int | `50` | 取得件数（1〜100） |

> FAISS インデックスが未構築のユーザーはエラーになります。

### `emotion_search_comments`

感情ベクトルを指定してコメントをベクトル検索します。複数の感情を同時に指定することも可能です。

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `login` | string | 必須 | コメンターのログイン名 |
| `joy` | float | `0.0` | 喜び・楽しさの強度（0.0〜1.0） |
| `surprise` | float | `0.0` | 驚きの強度（0.0〜1.0） |
| `admiration` | float | `0.0` | 称賛・感動の強度（0.0〜1.0） |
| `anger` | float | `0.0` | 怒り・批判の強度（0.0〜1.0） |
| `sadness` | float | `0.0` | 悲しみの強度（0.0〜1.0） |
| `cheer` | float | `0.0` | 応援・チアの強度（0.0〜1.0） |
| `top_k` | int | `50` | 取得件数（1〜100） |
| `diversity` | float | `None` | MMR 多様性パラメータ（0.0〜1.0） |

> FAISS インデックスが未構築のユーザーはエラーになります。
