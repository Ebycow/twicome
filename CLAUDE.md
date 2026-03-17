## Playwright MCP

ブラウザ閲覧してレビューしたい場合は、http://localhost:8011/ が利用可能

CSS・テンプレート等の静的ファイルを変更した後、サーバーが変更を反映していない場合は再ビルドが必要:
```
docker compose -f docker-compose.dev.yml --profile faiss up --build
```

## Lint

ファイルを書き込み・編集すると PostToolUse フック（`.claude/hooks/post_tool_lint.sh`）が自動で lint を実行する:
- `.py` → ruff
- `.html` → djlint
- `.js` → eslint
- `.css` → stylelint

# Test
testはdocker-compose.dev.ymlで実行
個別で実行を推奨するが、手動で全体 lint + test を一括実行したい場合は `ci-local.sh`（プロジェクトルート）を使う。
docker-compose.dev.yml はプロジェクトルートにある。
