const CACHE_NAME = 'twicome-v5';

// SW のスコープから BASE パスを取得 (例: "" または "/twicome")
const BASE = new URL(self.registration.scope).pathname.replace(/\/$/, '');

const OFFLINE_URL = `${BASE}/static/offline.html`;

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) =>
        // offline.html とメインページを事前キャッシュ。失敗しても install は続行
        Promise.all([
          cache.add(OFFLINE_URL).catch(() => {}),
          cache.add(`${BASE}/`).catch(() => {}),
        ])
      )
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // API リクエストはキャッシュしない（常にネットワーク）
  if (url.pathname.startsWith(`${BASE}/api/`)) return;

  // 静的ファイルはキャッシュファースト
  if (url.pathname.startsWith(`${BASE}/static/`)) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        }).catch(() => new Response('Not found', { status: 404 }));
      })
    );
    return;
  }

  // HTML ページ: キャッシュがあれば即返しバックグラウンドで更新（stale-while-revalidate）
  // 一度表示したページ（メインページ・コメントページ等）はオフラインでも表示可能
  if (request.mode === 'navigate') {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        cache.match(request).then((cached) => {
          const networkFetch = fetch(request).then((response) => {
            if (response.ok) cache.put(request, response.clone());
            return response;
          }).catch(() => null);
          if (cached) {
            networkFetch; // バックグラウンド更新（結果は捨てる）
            return cached;
          }
          return networkFetch.then((response) => {
            if (response) return response;
            // オフライン + キャッシュなし → offline.html を返す
            return caches.match(OFFLINE_URL).then(
              (r) => r || new Response('<h1>オフライン</h1><p>ネットワーク接続を確認してください。</p>', {
                status: 503,
                headers: { 'Content-Type': 'text/html; charset=utf-8' },
              })
            );
          });
        })
      ).catch(() =>
        caches.match(OFFLINE_URL).then(
          (r) => r || new Response('<h1>オフライン</h1><p>ネットワーク接続を確認してください。</p>', {
            status: 503,
            headers: { 'Content-Type': 'text/html; charset=utf-8' },
          })
        )
      )
    );
  }
});
