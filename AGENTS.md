## Playwright MCP

ブラウザ閲覧してレビューしたい場合は、http://localhost:8011/ が利用可能

CSS・テンプレート等の静的ファイルを変更した後、サーバーが変更を反映していない場合は再ビルドが必要:
```
docker compose -f docker-compose.dev.yml --profile faiss up --build
```

# Test
testはdocker-compose.dev.ymlで実行
appコンテナでテスト・lintを実行してはいけない。テスト実行用サービス・Lint 実行用サービスが個別に存在する。
サービスは個別で実行を推奨するが、大規模な変更で全体 lint + test を一括実行したい場合は `ci-local.sh`（プロジェクトルート）を使う。
docker-compose.dev.yml はプロジェクトルートにある。appディレクトリにはない。