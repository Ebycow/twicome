編集後積極的にテストとレビューを行うこと

## Playwright MCP

ブラウザ閲覧してレビューしたい場合は、http://localhost:8011/ が利用可能

CSS・テンプレート等の静的ファイルを変更した後、サーバーが変更を反映していない場合は再ビルドが必要:
```
docker compose -f docker-compose.dev.yml --profile faiss up --build
```

### 静的ファイル変更後のブラウザキャッシュ問題

CSS・JS を編集しても Playwright レビュー時に変更が反映されない場合がある。原因は2層のキャッシュ:

1. **Service Worker キャッシュ** — アプリが SW を登録しており、古い CSS/JS をキャッシュしている
2. **ブラウザ HTTP キャッシュ** — `?v=XXXXXXXX` 付き URL は起動時の git hash でバージョニングされており、サーバー再起動なしでは変わらない（`static_version` は `core/config.py` で起動時に決定）

**対処手順（Playwright MCP）:**

```js
// ① Service Worker とキャッシュをクリア
await page.evaluate(async () => {
  const regs = await navigator.serviceWorker.getRegistrations();
  for (const r of regs) await r.unregister();
  for (const n of await caches.keys()) await caches.delete(n);
});

// ② ページ再ナビゲート
await page.goto('http://localhost:8011/...');

// ③ それでも古い CSS が残る場合は <link> タグを差し替えて強制再取得
await page.evaluate(() => {
  const link = document.querySelector('link[href*="user_comments"]');
  link.href = link.href.split('?')[0] + '?v=' + Date.now();
});
// JS ファイルも同様に差し替え可能
```

変更が反映されているか確認する方法:
```js
// サーバーが新しい内容を返しているか確認（fetch は SW・HTTP キャッシュをバイパスしないので注意）
const r = await fetch('/static/css/user_comments.css');
const t = await r.text();
console.log(t.includes('新しいセレクタ名')); // true なら配信は正常

// ブラウザが実際に読み込んだ CSS のルールを確認
for (const sheet of document.styleSheets) {
  if (sheet.href?.includes('user_comments')) {
    for (const r of sheet.cssRules) {
      if (r.selectorText?.includes('確認したいセレクタ')) console.log(r.selectorText);
    }
  }
}
```

## Lint

ファイルを書き込み・編集すると PostToolUse フック（`.claude/hooks/post_tool_lint.sh`）が自動で lint を実行する:
- `.py` → ruff
- `.html` → djlint
- `.js` → eslint
- `.css` → stylelint

lintエラーを受け取ったのを放置しないこと

# Test
testはdocker-compose.dev.ymlで実行
appコンテナでテスト・lintを実行してはいけない。テスト実行用サービス・Lint 実行用サービスが個別に存在する。
サービスは個別で実行を推奨するが、大規模な変更で全体 lint + test を一括実行したい場合は `ci-local.sh`（プロジェクトルート）を使う。
docker-compose.dev.yml はプロジェクトルートにある。appディレクトリにはない。
