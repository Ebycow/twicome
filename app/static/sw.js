const CACHE_NAME = __TWICOME_CACHE_NAME__;

// SW のスコープから BASE パスを取得 (例: "" または "/twicome")
const BASE = new URL(self.registration.scope).pathname.replace(/\/$/, '');

const OFFLINE_URL = `${BASE}/static/offline.html`;
const TOP_PAGE_URL = `${BASE}/`;
const DATA_VERSION_URL = `${BASE}/api/meta/data-version`;
const USERS_INDEX_URL = `${BASE}/api/users/index`;
const TOP_PAGE_VERSION_CACHE_URL = `${BASE}/__sw/top-page-version`;
const COMMENT_PREFETCH_FAST_PATH_TTL_MS = 10 * 60 * 1000;

const commentFastPathHints = new Map();

function normalizePath(pathname) {
  if (pathname === '/') return '/';
  return pathname.replace(/\/$/, '');
}

function isTopPageNavigation(url, request) {
  return request.mode === 'navigate' && normalizePath(url.pathname) === normalizePath(TOP_PAGE_URL);
}

function isCommentsPageRequest(url) {
  const path = normalizePath(url.pathname);
  const commentsBase = normalizePath(`${BASE}/u`);
  if (!path.startsWith(`${commentsBase}/`)) return false;
  const remainder = path.slice(commentsBase.length + 1);
  return Boolean(remainder) && !remainder.includes('/');
}

/**
 * キャッシュキーやヒント照合用にURLからhashを除いた絶対URLへ正規化する。
 * @param urlString - 正規化するURL文字列
 * @returns hashを除いた絶対URL
 */
function normalizeRequestUrl(urlString) {
  const url = new URL(urlString, self.location.origin);
  url.hash = '';
  return url.toString();
}

/**
 * SW内の保存時刻を付与したキャッシュ用レスポンスを生成する。
 * @param response - 元のネットワークレスポンス
 * @returns キャッシュ保存用レスポンス
 */
function responseForCache(response) {
  const headers = new Headers(response.headers);
  headers.set('X-Twicome-SW-Cached-At', String(Date.now()));
  return new Response(response.clone().body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

/**
 * トップページからの次回コメントページ遷移だけキャッシュ即返しを許可する。
 * @param urlString - fast path対象のコメントページURL
 * @param dataVersion - トップページが保持しているデータバージョン
 */
function rememberCommentsFastPathHint(urlString, dataVersion) {
  const url = normalizeRequestUrl(urlString);
  commentFastPathHints.set(url, {
    dataVersion: typeof dataVersion === 'string' ? dataVersion : '',
    expiresAt: Date.now() + 30 * 1000,
  });
}

/**
 * コメントページ遷移用のfast pathヒントを1回だけ取り出す。
 * @param urlString - 照合するコメントページURL
 * @returns 有効なヒント。存在しない、または期限切れの場合はnull
 */
function takeCommentsFastPathHint(urlString) {
  const url = normalizeRequestUrl(urlString);
  const hint = commentFastPathHints.get(url);
  commentFastPathHints.delete(url);
  if (!hint || hint.expiresAt < Date.now()) return null;
  return hint;
}

/**
 * キャッシュ済みコメントページがトップページ由来の高速表示に使えるか判定する。
 * @param cached - キャッシュ済みレスポンス
 * @param hint - トップページから送られたfast pathヒント
 * @returns data versionと保存時刻が条件を満たす場合はtrue
 */
function canUsePrefetchedCommentsResponse(cached, hint) {
  if (!cached || !hint || !hint.dataVersion) return false;
  if (cached.headers.get('X-Twicome-Data-Version') !== hint.dataVersion) return false;

  const cachedAt = Number(cached.headers.get('X-Twicome-SW-Cached-At') || 0);
  return cachedAt > 0 && Date.now() - cachedAt <= COMMENT_PREFETCH_FAST_PATH_TTL_MS;
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
    redirect: 'manual',
  });
  if (response.type === 'opaqueredirect') {
    const err = new Error('auth-redirect');
    err.isAuthRedirect = true;
    throw err;
  }
  if (!response.ok) throw new Error(`data-version:${response.status}`);
  const data = await response.json();
  return typeof data.data_version === 'string' && data.data_version ? data.data_version : null;
}

async function cacheTopPageResponse(cache, request, response, fallbackVersion) {
  if (!response || !response.ok) return response;
  await cache.put(request, responseForCache(response));
  const dataVersion = response.headers.get('X-Twicome-Data-Version') || fallbackVersion || null;
  await writeTopPageVersion(cache, dataVersion);
  return response;
}

async function fetchAndCacheTopPage(cache, request, fallbackVersion) {
  const url = typeof request === 'string' ? request : request.url;
  const response = await fetchNavigate(url, {}, 'same-origin');
  if (response.type === 'opaqueredirect') {
    await cache.delete(request);
    return response;
  }
  return cacheTopPageResponse(cache, request, response, fallbackVersion);
}

async function fetchAndCacheUsersIndex(cache, request) {
  const response = await fetch(request);
  if (response.ok) {
    await cache.put(USERS_INDEX_URL, response.clone());
  }
  return response;
}

async function fetchAndCacheDocument(cache, request) {
  const response = await fetch(request);
  if (response.ok) {
    await cache.put(request, responseForCache(response));
  }
  return response;
}

// navigate 用フェッチ: redirect: 'manual' で認証リダイレクト（Cloudflare Access 等）を検出・通過させる
async function fetchNavigate(url, headers, credentials) {
  return fetch(url, {
    headers,
    credentials: credentials || 'same-origin',
    redirect: 'manual',
  });
}

async function notifyAuthRedirect(requestUrl) {
  const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  for (const client of clients) {
    client.postMessage({ type: 'twicome-auth-redirect', url: requestUrl });
  }
}

async function prefetchCommentsDocument(urlString) {
  const url = new URL(urlString, self.location.origin);
  if (url.origin !== self.location.origin || !isCommentsPageRequest(url)) {
    throw new Error('invalid_prefetch_url');
  }

  const cache = await caches.open(CACHE_NAME);
  const fetchRequest = new Request(url.toString(), {
    headers: {
      Accept: 'text/html',
      'X-Twicome-Prefetch': '1',
    },
  });
  const cacheRequest = new Request(url.toString());
  const response = await fetch(fetchRequest);
  if (!response.ok) {
    throw new Error(`prefetch_failed:${response.status}`);
  }
  await cache.put(cacheRequest, responseForCache(response));
  return response;
}

async function refreshCommentsDocument(urlString) {
  const url = new URL(urlString, self.location.origin);
  if (url.origin !== self.location.origin || !isCommentsPageRequest(url)) {
    throw new Error('invalid_refresh_url');
  }

  const cache = await caches.open(CACHE_NAME);
  const cacheRequest = new Request(url.toString());
  const headers = new Headers({
    Accept: 'text/html',
    'Cache-Control': 'no-cache',
    Pragma: 'no-cache',
    'X-Twicome-Refresh': '1',
  });
  const response = await fetchNavigate(url.toString(), headers, 'same-origin');

  if (response.type === 'opaqueredirect') {
    await cache.delete(cacheRequest);
    await notifyAuthRedirect(url.toString());
    return { authRedirect: true };
  }
  if (!response.ok) {
    throw new Error(`refresh_failed:${response.status}`);
  }

  await cache.delete(cacheRequest);
  await cache.put(cacheRequest, responseForCache(response));
  return { dataVersion: response.headers.get('X-Twicome-Data-Version') || null };
}

/**
 * キャッシュを即返ししたコメントページをバックグラウンドで最新化する。
 * @param cache - 保存先キャッシュ
 * @param request - 最新化するナビゲーションリクエスト
 */
async function revalidateCommentsNavigation(cache, request) {
  try {
    const response = await fetchNavigate(request.url, request.headers, 'same-origin');
    if (response.type === 'opaqueredirect') {
      await cache.delete(request);
      await notifyAuthRedirect(request.url);
      return;
    }
    if (response.ok) {
      await cache.put(request, responseForCache(response));
    }
  } catch {
    // ネットワークエラー時は、直前に返したキャッシュを維持する
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

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) =>
        // 初回表示直後の install では軽量なオフラインページだけを事前キャッシュする。
        // トップページとユーザー index は通常アクセス時かバッチ prewarm で温める。
        cache.add(OFFLINE_URL).catch(() => {})
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

self.addEventListener('message', (event) => {
  const data = event.data || {};
  const replyPort = event.ports && event.ports[0];
  if (data.type === 'twicome-prefetch-comments' && data.url) {
    event.waitUntil(
      prefetchCommentsDocument(data.url)
        .then(() => {
          if (replyPort) replyPort.postMessage({ ok: true });
        })
        .catch((error) => {
          if (replyPort) {
            replyPort.postMessage({
              ok: false,
              error: error instanceof Error ? error.message : String(error),
            });
          }
        })
    );
    return;
  }

  if (data.type === 'twicome-refresh-comments' && data.url) {
    event.waitUntil(
      refreshCommentsDocument(data.url)
        .then((result) => {
          if (replyPort) replyPort.postMessage({ ok: true, ...result });
        })
        .catch((error) => {
          if (replyPort) {
            replyPort.postMessage({
              ok: false,
              error: error instanceof Error ? error.message : String(error),
            });
          }
        })
    );
    return;
  }

  if (data.type === 'twicome-use-prefetched-comments' && data.url) {
    event.waitUntil(
      Promise.resolve()
        .then(() => {
          rememberCommentsFastPathHint(data.url, data.dataVersion);
          if (replyPort) replyPort.postMessage({ ok: true });
        })
        .catch((error) => {
          if (replyPort) {
            replyPort.postMessage({
              ok: false,
              error: error instanceof Error ? error.message : String(error),
            });
          }
        })
    );
  }
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
        try {
          const latestVersion = await fetchDataVersion().catch(() => null);
          const response = await fetchAndCacheTopPage(cache, request, latestVersion);
          if (response.type === 'opaqueredirect') {
            await notifyAuthRedirect(request.url);
          }
          return response;
        } catch {
          return offlineFallback(cache, request);
        }
      })
    );
    return;
  }

  if (request.method === 'GET' && isCommentsPageRequest(url)) {
    event.respondWith(
      caches.open(CACHE_NAME).then(async (cache) => {
        const cached = await cache.match(request);

        if (request.mode === 'navigate') {
          const fastPathHint = takeCommentsFastPathHint(request.url);
          if (canUsePrefetchedCommentsResponse(cached, fastPathHint)) {
            event.waitUntil(revalidateCommentsNavigation(cache, request));
            return cached;
          }

          try {
            const response = await fetchNavigate(request.url, request.headers, 'same-origin');
            if (response.type === 'opaqueredirect') {
              await cache.delete(request);
              await notifyAuthRedirect(request.url);
              return response;
            }
            if (response.ok) {
              await cache.put(request, responseForCache(response));
            }
            return response;
          } catch {
            return cached || offlineFallback(cache, request);
          }
        }

        // 非ナビゲーション（プリフェッチ等）: キャッシュファースト
        if (cached) {
          event.waitUntil(fetchAndCacheDocument(cache, request).catch(() => {}));
          return cached;
        }

        try {
          return await fetchAndCacheDocument(cache, request);
        } catch {
          return new Response('', { status: 503, statusText: 'Offline' });
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
          if (response.ok) cache.put(request, responseForCache(response));
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
