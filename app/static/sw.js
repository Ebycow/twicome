const CACHE_NAME = 'twicome-v9';

// SW のスコープから BASE パスを取得 (例: "" または "/twicome")
const BASE = new URL(self.registration.scope).pathname.replace(/\/$/, '');

const OFFLINE_URL = `${BASE}/static/offline.html`;
const TOP_PAGE_URL = `${BASE}/`;
const DATA_VERSION_URL = `${BASE}/api/meta/data-version`;
const USERS_INDEX_URL = `${BASE}/api/users/index`;
const TOP_PAGE_VERSION_CACHE_URL = `${BASE}/__sw/top-page-version`;

function normalizePath(pathname) {
  if (pathname === '/') return '/';
  return pathname.replace(/\/$/, '');
}

function isTopPageNavigation(url, request) {
  return request.mode === 'navigate' && normalizePath(url.pathname) === normalizePath(TOP_PAGE_URL);
}

async function readTopPageVersion(cache) {
  const response = await cache.match(TOP_PAGE_VERSION_CACHE_URL);
  if (!response) return null;
  try {
    const data = await response.json();
    return typeof data.dataVersion === 'string' && data.dataVersion ? data.dataVersion : null;
  } catch {
    return null;
  }
}

async function writeTopPageVersion(cache, dataVersion) {
  if (!dataVersion) return;
  await cache.put(
    TOP_PAGE_VERSION_CACHE_URL,
    new Response(JSON.stringify({ dataVersion }), {
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    })
  );
}

async function fetchDataVersion() {
  const response = await fetch(DATA_VERSION_URL, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`data-version:${response.status}`);
  const data = await response.json();
  return typeof data.data_version === 'string' && data.data_version ? data.data_version : null;
}

async function cacheTopPageResponse(cache, request, response, fallbackVersion) {
  if (!response || !response.ok) return response;
  await cache.put(request, response.clone());
  const dataVersion = response.headers.get('X-Twicome-Data-Version') || fallbackVersion || null;
  await writeTopPageVersion(cache, dataVersion);
  return response;
}

async function fetchAndCacheTopPage(cache, request, fallbackVersion) {
  const response = await fetch(request);
  return cacheTopPageResponse(cache, request, response, fallbackVersion);
}

async function fetchAndCacheUsersIndex(cache, request) {
  const response = await fetch(request);
  if (response.ok) {
    await cache.put(USERS_INDEX_URL, response.clone());
  }
  return response;
}

async function notifyTopPageUpdated(dataVersion) {
  const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  for (const client of clients) {
    client.postMessage({ type: 'twicome-top-page-updated', dataVersion });
  }
}

async function offlineFallback(cache, request) {
  const cached = await cache.match(request);
  if (cached) return cached;
  return caches.match(OFFLINE_URL).then(
    (r) => r || new Response('<h1>オフライン</h1><p>ネットワーク接続を確認してください。</p>', {
      status: 503,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    })
  );
}

async function precacheTopPage(cache) {
  try {
    await fetchAndCacheTopPage(cache, TOP_PAGE_URL);
  } catch {
    // install 時の失敗は無視して次回アクセス時に構築する
  }
}

async function revalidateTopPage(cache, request) {
  const cachedVersion = await readTopPageVersion(cache);
  try {
    const latestVersion = await fetchDataVersion();
    if (latestVersion && latestVersion === cachedVersion) return;

    const response = await fetchAndCacheTopPage(cache, request, latestVersion);
    if (!response || !response.ok) return;

    const updatedVersion = response.headers.get('X-Twicome-Data-Version') || latestVersion;
    if (updatedVersion && updatedVersion !== cachedVersion) {
      await notifyTopPageUpdated(updatedVersion);
    }
  } catch {
    // 背景再検証に失敗しても現在のキャッシュは維持する
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) =>
        // offline.html とメインページを事前キャッシュ。失敗しても install は続行
        Promise.all([
          cache.add(OFFLINE_URL).catch(() => {}),
          precacheTopPage(cache),
          cache.add(USERS_INDEX_URL).catch(() => {}),
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

  if (normalizePath(url.pathname) === normalizePath(USERS_INDEX_URL)) {
    event.respondWith(
      caches.open(CACHE_NAME).then(async (cache) => {
        try {
          return await fetchAndCacheUsersIndex(cache, request);
        } catch {
          const cached = await cache.match(USERS_INDEX_URL);
          return cached || new Response(JSON.stringify({ error: 'offline_users_index_unavailable' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json; charset=utf-8' },
          });
        }
      })
    );
    return;
  }

  // API リクエストはキャッシュしない（常にネットワーク）
  if (url.pathname.startsWith(`${BASE}/api/`)) return;

  // Twitch CDN 画像: キャッシュファースト、未キャッシュ時はネットワーク取得してキャッシュ、オフライン時はプレースホルダー
  if (url.hostname === 'static-cdn.jtvnw.net') {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            caches.open(CACHE_NAME).then((cache) => cache.put(request, response.clone()));
          }
          return response;
        }).catch(() =>
          new Response(
            '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" fill="#555"/></svg>',
            { headers: { 'Content-Type': 'image/svg+xml' } }
          )
        );
      })
    );
    return;
  }

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

  if (isTopPageNavigation(url, request)) {
    event.respondWith(
      caches.open(CACHE_NAME).then(async (cache) => {
        const cached = await cache.match(request);
        if (cached) {
          event.waitUntil(revalidateTopPage(cache, request));
          return cached;
        }

        try {
          return await fetchAndCacheTopPage(cache, request);
        } catch {
          return offlineFallback(cache, request);
        }
      })
    );
    return;
  }

  // HTML ページ: ネットワークファースト。失敗時のみキャッシュ（オフライン対応）
  if (request.mode === 'navigate') {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) =>
        fetch(request).then((response) => {
          if (response.ok) cache.put(request, response.clone());
          return response;
        }).catch(() =>
          cache.match(request).then(
            (cached) => cached || caches.match(OFFLINE_URL).then(
              (r) => r || new Response('<h1>オフライン</h1><p>ネットワーク接続を確認してください。</p>', {
                status: 503,
                headers: { 'Content-Type': 'text/html; charset=utf-8' },
              })
            )
          )
        )
      )
    );
  }
});
