## Playwright MCP

ブラウザ閲覧してレビューしたい場合は、http://localhost:8011/ が利用可能

CSS・テンプレート等の静的ファイルを変更した後、サーバーが変更を反映していない場合は再ビルドが必要:
```
docker compose -f docker-compose.dev.yml --profile faiss up --build
```

## test lint

testは`ci-local.sh`で実行
説明を読み、個別で実行を推奨する
docker-compose.dev.yml はプロジェクトルートにある。