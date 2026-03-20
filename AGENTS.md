# Test
testはdocker-compose.dev.ymlで実行
appコンテナでテスト・lintを実行してはいけない。テスト実行用サービス・Lint 実行用サービスが個別に存在する。
サービスは個別で実行を推奨するが、大規模な変更で全体 lint + test を一括実行したい場合は `ci-local.sh`（プロジェクトルート）を使う。
docker-compose.dev.yml はプロジェクトルートにある。appディレクトリにはない。