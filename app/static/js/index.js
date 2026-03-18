(function () {
  const loginInput = document.getElementById('login-search');
  const loginSearchWrapper = document.getElementById('login-search-wrapper');
  const loginSearchResults = document.getElementById('login-search-results');
  const loginSearchClear = document.getElementById('login-search-clear');
  const offlineStatus = document.getElementById('offline-status');
  const selectedUserCard = document.getElementById('selected-user-card');
  const selectedUserAvatar = document.getElementById('selected-user-avatar');
  const selectedUserName = document.getElementById('selected-user-name');
  const selectedUserLogin = document.getElementById('selected-user-login');
  const selectedUserMeta = document.getElementById('selected-user-meta');
  const selectedUserCount = document.getElementById('selected-user-count');

  if (!loginInput) {return;}

  const rawRootPath = JSON.parse(document.getElementById('root-path-data').textContent);
  const rootPath = (typeof rawRootPath === 'string' && rawRootPath && rawRootPath !== '/') ? rawRootPath.replace(/\/+$/, '') : '';
  const currentDataVersion = JSON.parse(document.getElementById('data-version-data').textContent);
  const serviceWorkerCacheName = JSON.parse(document.getElementById('sw-cache-name-data').textContent);

  const topPageReloadMarkerKey = 'twicome:last-top-page-reload-version';
  const serviceWorkerUrl = `${rootPath  }/sw.js`;
  const offlineAccess = window.TwicomeOfflineAccess || {
    createEmpty () { return { comments: new Set(), stats: new Set(), quiz: new Set() }; },
    getStorageKey () { return null; },
    isAccessible (routes, route, login) {
      const normalized = String(login || '').trim().toLowerCase();
      return Boolean(routes && routes[route] && normalized && routes[route].has(normalized));
    },
    read () { return this.createEmpty(); },
  };
  const offlineAccessStorageKey = offlineAccess.getStorageKey(rootPath);

  const statsLink = document.getElementById('stats-link');
  const quizLink = document.getElementById('quiz-link');
  const goBtn = document.getElementById('go-btn');
  const quickLinkElements = Array.from(document.querySelectorAll('.quick-link[data-prefetch-login]'));
  const streamerFilter = document.getElementById('streamer-filter');
  const sortSelect = document.getElementById('sort-select');
  const form = loginInput.closest('form');

  const maxCandidates = 25;
  const usersIndexUrl = `${rootPath  }/api/users/index`;
  const statsPathTemplate = `${rootPath  }/u/__LOGIN_PLACEHOLDER__/stats`;
  const quizPathTemplate = `${rootPath  }/u/__LOGIN_PLACEHOLDER__/quiz`;
  const commentsPathTemplate = `${rootPath  }/u/__LOGIN_PLACEHOLDER__`;
  const commentPrefetchConcurrency = 2;

  let indexedUsers = [];
  let loginMap = new Map();
  let displayMap = new Map();
  let userMap = new Map();
  let usersLoaded = false;
  let usersLoadPromise = null;
  let currentSort = 'login';
  let streamerFilterSet = null;
  let offlineMode = navigator.onLine === false;
  let offlineAccessibleRoutes = offlineAccess.read(rootPath);
  let activeCommentPrefetchCount = 0;
  let commentPrefetchFlushScheduled = false;
  let resolvedInputPrefetchTimer = null;
  const queuedCommentPrefetches = [];
  const queuedCommentPrefetchKeys = new Set();
  const prefetchedCommentPages = new Set();
  const prefetchingCommentPages = new Set();
  let commentsPrefetchTransportMode = 'direct-fetch';

  /**
   * Service Workerがページをコントロール下に置くまで待機し、タイムアウトした場合はfalseで解決する。
   * @param timeoutMs - タイムアウトまでの待機時間（ミリ秒、デフォルト3000）
   * @returns ServiceWorkerがcontrollerを取得できたかどうかを表すPromise
   */
  function waitForServiceWorkerControl(timeoutMs) {
    timeoutMs = timeoutMs || 3000;
    if (!('serviceWorker' in navigator)) {return Promise.resolve(false);}
    if (navigator.serviceWorker.controller) {return Promise.resolve(true);}
    return new Promise(function (resolve) {
      let settled = false;
      const finish = function (controlled) {
        if (settled) {return;}
        settled = true;
        window.clearTimeout(timerId);
        navigator.serviceWorker.removeEventListener('controllerchange', onControllerChange);
        resolve(controlled);
      };
      const onControllerChange = function () { finish(Boolean(navigator.serviceWorker.controller)); };
      const timerId = window.setTimeout(function () { finish(Boolean(navigator.serviceWorker.controller)); }, timeoutMs);
      navigator.serviceWorker.addEventListener('controllerchange', onControllerChange);
    });
  }

  const commentsPrefetchTransportReadyPromise = ('serviceWorker' in navigator)
    ? navigator.serviceWorker.register(serviceWorkerUrl, { scope: `${rootPath  }/` })
        .then(function () { return navigator.serviceWorker.ready; })
        .then(function () {
          return waitForServiceWorkerControl().then(function (controlled) {
            commentsPrefetchTransportMode = controlled ? 'service-worker-cache' : 'server-warm-only';
            return navigator.serviceWorker.ready;
          });
        })
        .catch(function () {
          commentsPrefetchTransportMode = 'direct-fetch';
          return null;
        })
    : Promise.resolve(null);

  /**
   * パステンプレートのプレースホルダをエンコードされたログイン名で置換する。
   * @param template - `__LOGIN_PLACEHOLDER__` を含むパステンプレート
   * @param login - 置換するログイン名
   * @returns ログイン名を埋め込んだパス文字列
   */
  function pathForLogin(template, login) {
    return template.replace('__LOGIN_PLACEHOLDER__', encodeURIComponent(login));
  }

  /**
   * ログイン名とプラットフォームからコメントページのURLを組み立てる。
   * @param login - ユーザのログイン名
   * @param platform - プラットフォーム名（デフォルト: 'twitch'）
   * @returns コメントページのURL文字列
   */
  function buildCommentsUrl(login, platform) {
    platform = platform || 'twitch';
    return `${pathForLogin(commentsPathTemplate, login)  }?platform=${  encodeURIComponent(platform)}`;
  }

  /**
   * ログイン名とプラットフォームを正規化してプリフェッチ重複チェック用のキーを生成する。
   * @param login - ユーザのログイン名
   * @param platform - プラットフォーム名（デフォルト: 'twitch'）
   * @returns 正規化されたプリフェッチキー文字列
   */
  function normalizePrefetchKey(login, platform) {
    platform = platform || 'twitch';
    const normalizedLogin = String(login || '').trim().toLowerCase();
    const normalizedPlatform = String(platform || 'twitch').trim().toLowerCase() || 'twitch';
    if (!normalizedLogin) {return '';}
    return `${normalizedPlatform  }:${  normalizedLogin}`;
  }

  /**
   * アイドル時またはタイムアウト後にコメントプリフェッチキューの処理をスケジュールする。
   */
  function scheduleCommentPrefetchFlush() {
    if (commentPrefetchFlushScheduled || offlineMode) {return;}
    commentPrefetchFlushScheduled = true;
    const run = function () {
      commentPrefetchFlushScheduled = false;
      flushCommentPrefetchQueue();
    };
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(run, { timeout: 1200 });
      return;
    }
    window.setTimeout(run, 150);
  }

  /**
   * Service Worker経由でコメントページをキャッシュにプリフェッチする。
   * @param url - プリフェッチ対象のコメントページURL
   * @returns プリフェッチ完了を表すPromise
   */
  function prefetchCommentPageViaServiceWorker(url) {
    return commentsPrefetchTransportReadyPromise.then(function (registration) {
      const worker = registration && (registration.active || registration.waiting || registration.installing);
      if (!worker) {throw new Error('service_worker_unavailable');}
      return new Promise(function (resolve, reject) {
        const channel = new MessageChannel();
        const timerId = window.setTimeout(function () {
          reject(new Error('service_worker_prefetch_timeout'));
        }, 6000);
        channel.port1.onmessage = function (event) {
          window.clearTimeout(timerId);
          const data = event.data || {};
          if (data.ok) { resolve(true); return; }
          reject(new Error(data.error || 'service_worker_prefetch_failed'));
        };
        worker.postMessage({ type: 'twicome-prefetch-comments', url }, [channel.port2]);
      });
    });
  }

  /**
   * Service Workerまたは直接フェッチでコメントページをプリフェッチしキャッシュに保存する。
   * @param login - プリフェッチ対象ユーザのログイン名
   * @param platform - プラットフォーム名（デフォルト: 'twitch'）
   */
  async function prefetchCommentPage(login, platform) {
    platform = platform || 'twitch';
    const key = normalizePrefetchKey(login, platform);
    if (!key || offlineMode || prefetchedCommentPages.has(key) || prefetchingCommentPages.has(key)) {return;}
    const url = buildCommentsUrl(login, platform);
    prefetchingCommentPages.add(key);
    try {
      let usedServiceWorker = false;
      try {
        await prefetchCommentPageViaServiceWorker(url);
        commentsPrefetchTransportMode = 'service-worker-message';
        usedServiceWorker = true;
      } catch (swError) {
        const response = await fetch(url, {
          credentials: 'same-origin',
          headers: { Accept: 'text/html', 'X-Twicome-Prefetch': '1' },
        });
        if (!response.ok) {throw new Error(`prefetch_failed:${  response.status}`);}
        const responseForCache = response.clone();
        await response.text();
        commentsPrefetchTransportMode = 'direct-fetch';
        if (window.location.hostname === 'localhost' || window.location.protocol === 'https:') {
          try {
            const cache = await caches.open(serviceWorkerCacheName);
            await cache.put(url, responseForCache);
            commentsPrefetchTransportMode = 'window-cache-put';
          } catch (_) {}
        }
        if (swError) {console.warn('Service worker prefetch fallback:', swError);}
      }
      prefetchedCommentPages.add(key);
      if (usedServiceWorker && !navigator.serviceWorker.controller) {
        commentsPrefetchTransportMode = 'service-worker-message';
      }
    } catch (error) {
      console.warn('Failed to prefetch comments page:', login, error);
    } finally {
      prefetchingCommentPages.delete(key);
    }
  }

  /**
   * 同時実行数の上限を守りながらコメントプリフェッチキューを順次処理する。
   */
  async function flushCommentPrefetchQueue() {
    if (offlineMode) {return;}
    while (activeCommentPrefetchCount < commentPrefetchConcurrency && queuedCommentPrefetches.length) {
      const next = queuedCommentPrefetches.shift();
      if (!next) {break;}
      queuedCommentPrefetchKeys.delete(next.key);
      if (prefetchedCommentPages.has(next.key) || prefetchingCommentPages.has(next.key)) {continue;}
      activeCommentPrefetchCount += 1;
      prefetchCommentPage(next.login, next.platform)
        .finally(function () {
          activeCommentPrefetchCount = Math.max(0, activeCommentPrefetchCount - 1);
          scheduleCommentPrefetchFlush();
        });
    }
    if (queuedCommentPrefetches.length) {scheduleCommentPrefetchFlush();}
  }

  /**
   * 指定ユーザのコメントページをプリフェッチキューに追加してフラッシュをスケジュールする。
   * @param login - キューに追加するユーザのログイン名
   * @param platform - プラットフォーム名（デフォルト: 'twitch'）
   */
  function queueCommentPrefetch(login, platform) {
    platform = platform || 'twitch';
    const key = normalizePrefetchKey(login, platform);
    if (!key || offlineMode) {return;}
    if (prefetchedCommentPages.has(key) || prefetchingCommentPages.has(key) || queuedCommentPrefetchKeys.has(key)) {return;}
    queuedCommentPrefetches.push({ key, login, platform });
    queuedCommentPrefetchKeys.add(key);
    scheduleCommentPrefetchFlush();
  }

  window.__twicomeCommentPrefetch = {
    getState () {
      return {
        activeCount: activeCommentPrefetchCount,
        mode: commentsPrefetchTransportMode,
        offlineMode,
        prefetched: Array.from(prefetchedCommentPages),
        prefetching: Array.from(prefetchingCommentPages),
        queued: queuedCommentPrefetches.map(function (item) { return item.key; }),
        serviceWorkerControlled: Boolean('serviceWorker' in navigator && navigator.serviceWorker.controller),
      };
    },
    queue (login, platform) { queueCommentPrefetch(login, platform || 'twitch'); },
  };

  /**
   * 入力欄の現在値を解決して対応するコメントページのプリフェッチをデバウンス付きでスケジュールする。
   */
  function scheduleResolvedInputPrefetch() {
    if (resolvedInputPrefetchTimer) {window.clearTimeout(resolvedInputPrefetchTimer);}
    if (offlineMode) {return;}
    resolvedInputPrefetchTimer = window.setTimeout(async function () {
      try { await ensureUsersLoaded(); } catch (_) { return; }
      const resolved = resolveLogin(loginInput.value);
      if (resolved) {queueCommentPrefetch(resolved);}
    }, 250);
  }

  /**
   * ページ読み込み直後にデフォルトユーザとクイックリンクのコメントページをプリフェッチキューに追加する。
   */
  function primeInitialCommentPrefetches() {
    const defaultLogin = form.dataset.defaultLogin || loginInput.value.trim();
    if (defaultLogin) {queueCommentPrefetch(defaultLogin);}
    for (let i = 0; i < quickLinkElements.length; i++) {
      const link = quickLinkElements[i];
      const login = link.dataset.prefetchLogin;
      const platform = link.dataset.prefetchPlatform || 'twitch';
      if (!login) {continue;}
      queueCommentPrefetch(login, platform);
    }
  }

  /**
   * リンク要素のaria-disabled属性を設定して有効/無効状態を切り替える。
   * @param link - 状態を変更するリンク要素
   * @param enabled - trueなら有効、falseなら無効（aria-disabled）
   */
  function setLinkState(link, enabled) {
    link.setAttribute('aria-disabled', String(!enabled));
  }

  /**
   * 統計ページとクイズページへのリンクを一括で有効/無効にする。
   * @param enabled - trueなら統計・クイズリンクを有効化、falseなら無効化
   */
  function setActionLinkState(enabled) {
    const disabled = String(!enabled);
    statsLink.setAttribute('aria-disabled', disabled);
    quizLink.setAttribute('aria-disabled', disabled);
  }

  /**
   * 統計ページとクイズページへのリンクhrefを指定ユーザのURLに更新する。
   * @param login - リンク先を設定するユーザのログイン名
   */
  function setActionLinks(login) {
    statsLink.href = `${pathForLogin(statsPathTemplate, login)  }?platform=twitch`;
    quizLink.href = `${pathForLogin(quizPathTemplate, login)  }?platform=twitch`;
  }

  /**
   * 選択中ユーザカードのアバター領域をプロフィール画像または頭文字で更新する。
   * @param user - 表示対象ユーザ。null の場合はプレースホルダ表示
   * @param fallbackText - ユーザ不在時に表示する1文字
   */
  function renderSelectedUserAvatar(user, fallbackText) {
    if (!selectedUserAvatar) {return;}
    selectedUserAvatar.textContent = '';
    selectedUserAvatar.innerHTML = '';
    if (user && user.profileImageUrl) {
      const img = document.createElement('img');
      img.src = user.profileImageUrl;
      img.alt = '';
      img.loading = 'lazy';
      selectedUserAvatar.appendChild(img);
      return;
    }
    selectedUserAvatar.textContent = String(fallbackText || '?').slice(0, 1).toUpperCase();
  }

  /**
   * 入力欄の状態に合わせて「選択中のユーザ」カードの表示内容を更新する。
   */
  function updateSelectedUserPreview() {
    if (!selectedUserCard || !selectedUserName || !selectedUserLogin || !selectedUserMeta || !selectedUserCount) {return;}

    const currentValue = loginInput.value.trim();
    const setEmpty = function (name, meta, fallbackText) {
      selectedUserCard.classList.add('selected-user-card-empty');
      selectedUserName.textContent = name;
      selectedUserMeta.textContent = meta;
      selectedUserLogin.hidden = true;
      selectedUserLogin.textContent = '';
      selectedUserCount.hidden = true;
      selectedUserCount.textContent = '';
      renderSelectedUserAvatar(null, fallbackText || '?');
    };

    if (!currentValue) {
      setEmpty('まだ選択されていません', 'ユーザ名を入力して候補から選ぶと、ここで確認できます。', '?');
      return;
    }

    if (!usersLoaded) {
      setEmpty(currentValue, 'ユーザ情報を読み込み中です...', currentValue);
      return;
    }

    const resolved = resolveLogin(currentValue);
    if (!resolved) {
      setEmpty(
        currentValue,
        offlineMode ? 'オフライン中は閲覧済みユーザから選択してください。' : '候補から一致するユーザを選択してください。',
        currentValue
      );
      return;
    }

    const user = userMap.get(resolved.toLowerCase());
    if (!user) {
      setEmpty(resolved, 'ユーザ情報を表示できません。', resolved);
      return;
    }

    selectedUserCard.classList.remove('selected-user-card-empty');
    selectedUserName.textContent = user.displayName || user.login;
    selectedUserLogin.hidden = false;
    selectedUserLogin.textContent = `@${user.login}`;
    const rel = formatRelativeTime(user.lastCommentAt);
    if (user.commentCount > 0) {
      selectedUserCount.hidden = false;
      selectedUserCount.textContent = `${user.commentCount.toLocaleString()}件`;
      selectedUserMeta.textContent = rel ? `最終活動: ${rel}` : 'コメント一覧を開く準備ができています。';
    } else {
      selectedUserCount.hidden = true;
      selectedUserCount.textContent = '';
      selectedUserMeta.textContent = 'コメント数はまだ集計されていません。';
    }
    renderSelectedUserAvatar(user, user.displayName || user.login);
  }

  /**
   * 候補リストの代わりにメッセージを表示する。
   * @param message - 候補リストに表示するメッセージ文字列
   */
  function showCandidateMessage(message) {
    loginSearchResults.innerHTML = `<div class="search-empty">${  message  }</div>`;
    loginSearchResults.hidden = false;
  }

  /**
   * localStorage からオフラインアクセス可能なルート情報を再読み込みする。
   */
  function refreshOfflineAccessibleRoutes() {
    offlineAccessibleRoutes = offlineAccess.read(rootPath);
  }

  /**
   * 指定ルートとログイン名の組み合わせがオフラインでアクセス可能かどうかを返す。
   * @param route - チェック対象のルート名（'comments', 'stats', 'quiz'）
   * @param login - ユーザのログイン名
   * @returns オフラインでアクセス可能かどうか
   */
  function hasOfflineRouteAccess(route, login) {
    if (!offlineMode) {return true;}
    return offlineAccess.isAccessible(offlineAccessibleRoutes, route, login);
  }

  /**
   * オフラインでコメントページを開けるユーザ数を返す。
   * @returns オフラインでコメントページを開けるユーザ数
   */
  function countOfflineCommentUsers() {
    if (!usersLoaded) {return offlineAccessibleRoutes.comments.size;}
    let count = 0;
    for (let i = 0; i < indexedUsers.length; i++) {
      if (hasOfflineRouteAccess('comments', indexedUsers[i].login)) {count += 1;}
    }
    return count;
  }

  /**
   * オフライン状態に応じてステータス表示要素の内容と表示/非表示を更新する。
   */
  function updateOfflineStatus() {
    if (!offlineMode) { offlineStatus.hidden = true; return; }
    const count = countOfflineCommentUsers();
    if (count > 0) {
      offlineStatus.textContent = `オフライン中です。閲覧済みの ${  count  } ユーザのみ候補に表示します。`;
    } else {
      offlineStatus.textContent = 'オフライン中です。閲覧済みユーザがまだ見つからないため、候補は表示できません。';
    }
    offlineStatus.hidden = false;
  }

  /**
   * オフラインアクセス情報を再読み込みし、ステータス表示・リンク・候補リストを更新する。
   * @param opts - オプション（`rerender: true` で候補リストを再描画）
   */
  function refreshOfflineState(opts) {
    opts = opts || {};
    refreshOfflineAccessibleRoutes();
    updateOfflineStatus();
    updateSelectedUserPreview();
    syncActionLinksFromInput();
    if (opts.rerender && !loginSearchResults.hidden) {
      void renderCandidates(loginInput.value);
    }
  }

  /**
   * APIから受け取ったユーザ配列を正規化してindexedUsers・loginMap・displayMapを構築する。
   * @param rawUsers - APIから受け取ったユーザ配列
   */
  function hydrateUsers(rawUsers) {
    const normalizedUsers = Array.isArray(rawUsers) ? rawUsers.map(function (user) {
      return {
        login: user.login,
        displayName: user.display_name || '',
        profileImageUrl: user.profile_image_url || '',
        commentCount: Number(user.comment_count || 0),
        lastCommentAt: user.last_comment_at || null,
      };
    }) : [];

    indexedUsers = normalizedUsers.map(function (user) {
      return Object.assign({}, user, {
        loginLower: user.login.toLowerCase(),
        displayLower: user.displayName.toLowerCase(),
      });
    });

    loginMap = new Map(indexedUsers.map(function (user) { return [user.loginLower, user.login]; }));
    userMap = new Map(indexedUsers.map(function (user) { return [user.loginLower, user]; }));
    displayMap = new Map();
    for (let i = 0; i < indexedUsers.length; i++) {
      const user = indexedUsers[i];
      if (!user.displayLower) {continue;}
      if (!displayMap.has(user.displayLower)) {displayMap.set(user.displayLower, []);}
      displayMap.get(user.displayLower).push(user.login);
    }
  }

  /**
   * ユーザインデックスが未読み込みの場合はAPIからフェッチして読み込む。
   * @returns ユーザインデックスの読み込み完了を表すPromise
   */
  async function ensureUsersLoaded() {
    if (usersLoaded) {return indexedUsers;}
    if (usersLoadPromise) {return usersLoadPromise;}
    usersLoadPromise = fetch(usersIndexUrl, { headers: { Accept: 'application/json' } })
      .then(async function (response) {
        if (!response.ok) {throw new Error(`failed_to_load_users:${  response.status}`);}
        const data = await response.json();
        hydrateUsers(data.users || []);
        usersLoaded = true;
        updateOfflineStatus();
        updateSelectedUserPreview();
        syncActionLinksFromInput();
        scheduleResolvedInputPrefetch();
        return indexedUsers;
      })
      .catch(function (error) {
        usersLoadPromise = null;
        throw error;
      });
    return usersLoadPromise;
  }

  /**
   * ISO日時文字列から現在時刻までの差分を日本語の相対時間文字列に変換する。
   * @param isoStr - ISO形式の日時文字列
   * @returns 表示用の相対時間文字列。日時がない場合はnull
   */
  function formatRelativeTime(isoStr) {
    if (!isoStr) {return null;}
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) {return `${Math.max(1, mins)  }分前`;}
    const hours = Math.floor(mins / 60);
    if (hours < 24) {return `${hours  }時間前`;}
    const days = Math.floor(hours / 24);
    if (days < 30) {return `${days  }日前`;}
    const months = Math.floor(days / 30);
    if (months < 12) {return `${months  }ヶ月前`;}
    return `${Math.floor(months / 12)  }年前`;
  }

  /**
   * ユーザの表示名とログイン名からサジェスト候補に表示するラベル文字列を生成する。
   * @param user - 候補表示に使うユーザ情報オブジェクト
   * @returns 候補一覧に表示するラベル文字列
   */
  function formatCandidateLabel(user) {
    if (!user.displayName || user.displayLower === user.loginLower) {return user.login;}
    return `${user.displayName  } (${  user.login  })`;
  }

  /**
   * 入力値をログインマップ・表示名マップと照合して一意に解決できるログイン名を返す。
   * @param input - 入力欄に現在入っている文字列
   * @returns 一意に解決できたログイン名。解決できない場合は空文字列
   */
  function resolveLogin(input) {
    if (!usersLoaded) {return '';}
    const normalized = input.trim().toLowerCase();
    if (!normalized) {return '';}
    const loginMatch = loginMap.get(normalized);
    if (loginMatch && hasOfflineRouteAccess('comments', loginMatch)) {return loginMatch;}
    const displayMatches = (displayMap.get(normalized) || []).filter(function (login) { return hasOfflineRouteAccess('comments', login); });
    if (displayMatches.length === 1) {return displayMatches[0];}
    return '';
  }

  /**
   * 選択中の配信者フィルタをユーザ配列に適用して絞り込んだ配列を返す。
   * @param users - フィルタ前のユーザ配列
   * @returns 配信者フィルタ適用後のユーザ配列
   */
  function applyStreamerFilter(users) {
    if (streamerFilterSet === null) {return users;}
    if (streamerFilterSet === 'loading') {return [];}
    return users.filter(function (user) { return streamerFilterSet.has(user.login); });
  }

  /**
   * オフラインモード時にコメントページへアクセス可能なユーザだけに絞り込む。
   * @param users - フィルタ前のユーザ配列
   * @returns オフライン閲覧可能なユーザだけに絞った配列
   */
  function applyOfflineAvailabilityFilter(users) {
    if (!offlineMode) {return users;}
    return users.filter(function (user) { return hasOfflineRouteAccess('comments', user.login); });
  }

  /**
   * 現在のソート条件に従ってユーザ配列をソートした新しい配列を返す。
   * @param users - 並び替え対象のユーザ配列
   * @returns 現在のソート条件で並び替えた新しい配列
   */
  function applySort(users) {
    const sorted = users.slice();
    if (currentSort === 'count_desc') {
      sorted.sort(function (a, b) { return b.commentCount - a.commentCount; });
    } else if (currentSort === 'count_asc') {
      sorted.sort(function (a, b) { return a.commentCount - b.commentCount; });
    } else if (currentSort === 'recent') {
      sorted.sort(function (a, b) {
        if (!a.lastCommentAt && !b.lastCommentAt) {return 0;}
        if (!a.lastCommentAt) {return 1;}
        if (!b.lastCommentAt) {return -1;}
        return new Date(b.lastCommentAt) - new Date(a.lastCommentAt);
      });
    }
    return sorted;
  }

  /**
   * 入力文字列に対してフィルタ・ソート・重複排除を適用して候補ユーザ配列を返す。
   * @param input - 検索欄に入力された文字列
   * @returns 表示候補となるユーザ配列
   */
  function getCandidates(input) {
    const q = input.trim().toLowerCase();
    if (!q) {
      const pool = applyOfflineAvailabilityFilter(applyStreamerFilter(indexedUsers));
      return applySort(pool).slice(0, maxCandidates);
    }
    const loginStarts = [], displayStarts = [], loginContains = [], displayContains = [];
    const filtered = applyOfflineAvailabilityFilter(applyStreamerFilter(indexedUsers));
    for (let i = 0; i < filtered.length; i++) {
      const user = filtered[i];
      const matchedLogin = user.loginLower.includes(q);
      const matchedDisplay = user.displayLower.includes(q);
      if (!matchedLogin && !matchedDisplay) {continue;}
      if (user.loginLower.startsWith(q)) {loginStarts.push(user);}
      else if (user.displayLower.startsWith(q)) {displayStarts.push(user);}
      else if (matchedLogin) {loginContains.push(user);}
      else {displayContains.push(user);}
    }
    const groups = [loginStarts, displayStarts, loginContains, displayContains];
    const ordered = groups.map(function (g) { return applySort(g); }).reduce(function (a, b) { return a.concat(b); }, []);
    const deduped = [];
    const seen = new Set();
    for (let j = 0; j < ordered.length; j++) {
      if (seen.has(ordered[j].login)) {continue;}
      seen.add(ordered[j].login);
      deduped.push(ordered[j]);
      if (deduped.length >= maxCandidates) {break;}
    }
    return deduped;
  }

  /**
   * ユーザ情報からサジェスト候補のボタン要素を生成する。
   * @param user - 候補として描画するユーザ情報
   * @returns 候補一覧に追加するボタン要素
   */
  function buildCandidateItem(user) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'search-item';
    btn.setAttribute('role', 'option');

    const avatarEl = document.createElement('span');
    avatarEl.className = 'search-item-avatar';
    if (user.profileImageUrl) {
      const img = document.createElement('img');
      img.src = user.profileImageUrl;
      img.alt = '';
      img.loading = 'lazy';
      avatarEl.appendChild(img);
    } else {
      avatarEl.textContent = (user.displayName || user.login)[0].toUpperCase();
    }
    btn.appendChild(avatarEl);

    const bodyEl = document.createElement('div');
    bodyEl.className = 'search-item-body';
    const nameEl = document.createElement('div');
    nameEl.className = 'search-item-name';
    nameEl.textContent = formatCandidateLabel(user);
    bodyEl.appendChild(nameEl);
    if (user.commentCount > 0) {
      const metaEl = document.createElement('div');
      metaEl.className = 'search-item-meta';
      const rel = formatRelativeTime(user.lastCommentAt);
      metaEl.textContent = rel ? `最終活動: ${  rel}` : '';
      bodyEl.appendChild(metaEl);
    }
    btn.appendChild(bodyEl);

    if (user.commentCount > 0) {
      const countEl = document.createElement('span');
      countEl.className = 'search-item-count';
      countEl.textContent = user.commentCount.toLocaleString();
      btn.appendChild(countEl);
    }

    btn.addEventListener('pointerdown', function (event) { event.preventDefault(); });
    btn.addEventListener('click', function () {
      selectLogin(user.login);
      loginInput.focus();
    });
    return btn;
  }

  /**
   * 候補リストを非表示にする。
   */
  function hideCandidates() { loginSearchResults.hidden = true; }

  /**
   * 候補からユーザを選択して入力欄とアクションリンクを更新しプリフェッチをキューに追加する。
   * @param login - 選択されたユーザのログイン名
   */
  function selectLogin(login) {
    loginInput.value = login;
    loginInput.setCustomValidity('');
    setActionLinks(login);
    updateSelectedUserPreview();
    syncActionLinksFromInput();
    queueCommentPrefetch(login);
    hideCandidates();
    updateClearBtn();
  }

  /**
   * 現在の入力値に基づいて候補リストをDOMに描画する。
   * @param input - 候補抽出に使う現在の入力値
   */
  async function renderCandidates(input) {
    if (!usersLoaded) {showCandidateMessage('候補を読み込み中...');}
    try { await ensureUsersLoaded(); } catch (_) {
      setActionLinkState(false);
      showCandidateMessage('候補の読み込みに失敗しました');
      return;
    }
    if (offlineMode) {refreshOfflineAccessibleRoutes();}
    const candidates = getCandidates(input);
    loginSearchResults.innerHTML = '';
    if (!candidates.length) {
      if (offlineMode) {
        const message = countOfflineCommentUsers() > 0
          ? 'オフライン中の閲覧済みユーザでは見つかりません'
          : 'オフライン中に開ける閲覧済みユーザがありません';
        showCandidateMessage(message);
        return;
      }
      showCandidateMessage('該当するユーザが見つかりません');
      return;
    }
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < candidates.length; i++) {
      fragment.appendChild(buildCandidateItem(candidates[i]));
    }
    loginSearchResults.appendChild(fragment);
    loginSearchResults.hidden = false;
  }

  /**
   * 入力欄の現在値を解決して統計・クイズリンクのhrefと有効/無効状態を同期する。
   */
  function syncActionLinksFromInput() {
    updateSelectedUserPreview();
    const currentValue = loginInput.value.trim();
    if (!usersLoaded) {
      if (currentValue) { setActionLinks(currentValue); setActionLinkState(!offlineMode); }
      else { setActionLinkState(false); }
      return;
    }
    const resolved = resolveLogin(loginInput.value);
    if (!resolved) { setActionLinkState(false); return; }
    setActionLinks(resolved);
    if (offlineMode) {
      setLinkState(statsLink, hasOfflineRouteAccess('stats', resolved));
      setLinkState(quizLink, hasOfflineRouteAccess('quiz', resolved));
      return;
    }
    setActionLinkState(true);
  }

  /**
   * 入力欄の値の有無に応じてクリアボタンの表示/非表示を切り替える。
   */
  function updateClearBtn() {
    loginSearchClear.style.display = loginInput.value ? 'flex' : 'none';
  }

  updateClearBtn();
  loginSearchClear.addEventListener('click', function () {
    loginInput.value = '';
    loginInput.focus();
    void renderCandidates('');
    syncActionLinksFromInput();
    updateClearBtn();
  });

  loginInput.addEventListener('focus', function () {
    void renderCandidates(this.value);
    scheduleResolvedInputPrefetch();
  });

  loginInput.addEventListener('input', function () {
    this.setCustomValidity('');
    void renderCandidates(this.value);
    syncActionLinksFromInput();
    scheduleResolvedInputPrefetch();
    updateClearBtn();
  });

  loginInput.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {hideCandidates();}
  });

  document.addEventListener('click', function (event) {
    if (!loginSearchWrapper.contains(event.target)) {hideCandidates();}
  });

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    if (goBtn) { goBtn.disabled = true; }
    try { await ensureUsersLoaded(); } catch (_) {
      loginInput.setCustomValidity('候補の読み込みに失敗しました。しばらくしてから再度お試しください');
      loginInput.reportValidity();
      loginInput.focus();
      if (goBtn) { goBtn.disabled = false; }
      return;
    }
    if (offlineMode) {refreshOfflineAccessibleRoutes();}
    const resolved = resolveLogin(loginInput.value);
    if (resolved) { if (goBtn) { goBtn.disabled = false; } window.location.href = buildCommentsUrl(resolved); return; }
    void renderCandidates(loginInput.value);
    loginInput.setCustomValidity(offlineMode
      ? 'オフライン中は閲覧済みのユーザのみ開けます'
      : '候補からTwitchユーザを選択してください');
    loginInput.reportValidity();
    loginInput.focus();
    if (goBtn) { goBtn.disabled = false; }
  });

  if (streamerFilter) {
    streamerFilter.addEventListener('change', async function () {
      if (offlineMode) {
        this.value = '';
        streamerFilterSet = null;
        void renderCandidates(loginInput.value);
        loginInput.focus();
        return;
      }
      const streamer = this.value;
      loginInput.value = '';
      loginInput.setCustomValidity('');
      setActionLinkState(false);
      updateClearBtn();
      if (!streamer) {
        streamerFilterSet = null;
        void renderCandidates('');
        loginInput.focus();
        return;
      }
      streamerFilterSet = 'loading';
      showCandidateMessage('読み込み中...');
      try {
        const res = await fetch(`${rootPath  }/api/users/commenters?streamer=${  encodeURIComponent(streamer)}`);
        const data = await res.json();
        streamerFilterSet = new Set(data.logins);
      } catch (_) {
        streamerFilterSet = null;
      }
      void renderCandidates('');
      loginInput.focus();
    });
  }

  if (sortSelect) {
    sortSelect.addEventListener('change', function () {
      currentSort = this.value;
      void renderCandidates(loginInput.value);
    });
  }

  for (let i = 0; i < quickLinkElements.length; i++) {
    (function (link) {
      const login = link.dataset.prefetchLogin;
      const platform = link.dataset.prefetchPlatform || 'twitch';
      if (!login) {return;}
      const triggerPrefetch = function () { queueCommentPrefetch(login, platform); };
      link.addEventListener('pointerenter', triggerPrefetch, { passive: true });
      link.addEventListener('focus', triggerPrefetch);
    })(quickLinkElements[i]);
  }

  window.addEventListener('pageshow', function (event) { if (goBtn && event.persisted) { goBtn.disabled = false; } refreshOfflineState({ rerender: true }); });
  window.addEventListener('focus', function () { refreshOfflineState({ rerender: true }); });
  window.addEventListener('storage', function (event) {
    if (offlineAccessStorageKey && event.key && event.key !== offlineAccessStorageKey) {return;}
    refreshOfflineState({ rerender: true });
  });
  window.addEventListener('online', function () {
    offlineMode = false;
    refreshOfflineState({ rerender: true });
    primeInitialCommentPrefetches();
    scheduleResolvedInputPrefetch();
  });
  window.addEventListener('offline', function () {
    offlineMode = true;
    refreshOfflineState({ rerender: true });
  });

  updateOfflineStatus();
  updateSelectedUserPreview();
  syncActionLinksFromInput();
  primeInitialCommentPrefetches();
  void ensureUsersLoaded().catch(function () {});

  // ---- PWA Banner ----
  (function () {
    const banner = document.getElementById('pwa-banner');
    const bannerTitle = document.getElementById('pwa-banner-title');
    const bannerSub = document.getElementById('pwa-banner-sub');
    if (!banner) {return;}
    if (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone) {
      banner.style.display = 'none';
      return;
    }
    let deferredPrompt = null;
    window.addEventListener('beforeinstallprompt', function (e) {
      e.preventDefault();
      deferredPrompt = e;
      banner.classList.add('pwa-banner--installable');
      bannerSub.textContent = 'タップしてアプリをインストール';
    });
    banner.addEventListener('click', async function () {
      if (!deferredPrompt) {return;}
      deferredPrompt.prompt();
      const result = await deferredPrompt.userChoice;
      deferredPrompt = null;
      banner.classList.remove('pwa-banner--installable');
      if (result.outcome === 'accepted') {
        banner.classList.add('pwa-banner--installed');
        bannerTitle.textContent = 'インストールしました！';
        bannerSub.textContent = 'ホーム画面からアプリのように起動できます';
        banner.removeAttribute('role');
        banner.removeAttribute('tabindex');
      } else {
        bannerSub.textContent = '「共有」→「ホーム画面に追加」でもインストールできます';
      }
    });
    banner.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {banner.click();}
    });
    window.addEventListener('appinstalled', function () {
      deferredPrompt = null;
      banner.classList.remove('pwa-banner--installable');
      banner.classList.add('pwa-banner--installed');
      bannerTitle.textContent = 'インストールしました！';
      bannerSub.textContent = 'ホーム画面からアプリのように起動できます';
      banner.removeAttribute('role');
      banner.removeAttribute('tabindex');
    });
  })();

  // ---- SW version update / auth redirect listener ----
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', function (event) {
      const data = event.data || {};
      if (data.type === 'twicome-auth-redirect') {
        window.location.reload();
        return;
      }
      if (data.type !== 'twicome-top-page-updated') {return;}
      if (!data.dataVersion || data.dataVersion === currentDataVersion) {return;}
      try {
        if (sessionStorage.getItem(topPageReloadMarkerKey) === data.dataVersion) {return;}
        sessionStorage.setItem(topPageReloadMarkerKey, data.dataVersion);
      } catch (_) {}
      window.location.reload();
    });
  }
})();

(function () {
  const stats = document.querySelectorAll('.hero-stat-value[data-count]');
  if (!stats.length) { return; }
  const duration = 1200;
  /**
   * @param {number} t - 0〜1の進行度
   * @returns {number} イージング後の値
   */
  function easeOut(t) { return 1 - (1 - t) * (1 - t); }
  /**
   * @param {number} n - 整数値
   * @returns {string} カンマ区切りの文字列
   */
  function fmt(n) { return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
  /**
   * @param {Element} el - アニメーション対象要素
   */
  function animate(el) {
    const target = parseInt(el.dataset.count, 10);
    if (isNaN(target)) { return; }
    const start = performance.now();
    el.textContent = '0';
    /**
     * @param {number} now - DOMHighResTimeStamp
     */
    function step(now) {
      const t = Math.min((now - start) / duration, 1);
      el.textContent = fmt(target * easeOut(t));
      if (t < 1) { requestAnimationFrame(step); }
    }
    requestAnimationFrame(step);
  }
  stats.forEach(animate);
}());

(function () {
  const fallbackComments = [
    'wwwwwwwwwwwwww',
    'ドンマイドンマイ！',
    'それな',
    'これはひどい笑',
    'クリップ待って',
    '5000兆点あげたい',
    'やばすぎて草',
    'ガチ勢すぎる',
    'さすがっす',
    '天才かよ',
    'リスナー強すぎ',
    '配信者より上手いの草',
    '待ってそれは草',
    '神回確定',
    '声が好きすぎる',
    '笑いすぎて涙出てきた',
    '毎日見てるけど飽きない',
    'このゲームセンスおかしい',
    'コメント欄強すぎwww',
    '今日も来てよかった',
    '全力で草生やしてる',
    'もう一回見よ',
    'ここ何度見ても笑える',
  ];
  const dataEl = document.getElementById('showcase-comments-data');
  let loaded = [];
  if (dataEl) {
    try { loaded = JSON.parse(dataEl.textContent) || []; } catch (e) { loaded = []; }
  }
  const comments = loaded.length > 0 ? loaded : fallbackComments;
  // ランダムな順序に並び替え
  for (let i = comments.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    const tmp = comments[i]; comments[i] = comments[j]; comments[j] = tmp;
  }

  const textEl = document.getElementById('comment-showcase-text');
  if (!textEl) { return; }

  let idx = Math.floor(Math.random() * comments.length);
  let pos = 0;
  let deleting = false;

  /** タイプアニメーションの1ステップ */
  function tick() {
    const text = comments[idx];
    if (!deleting) {
      pos++;
      textEl.textContent = text.slice(0, pos);
      if (pos >= text.length) {
        deleting = true;
        setTimeout(tick, 2200);
      } else {
        setTimeout(tick, 72);
      }
    } else {
      pos--;
      textEl.textContent = text.slice(0, pos);
      if (pos <= 0) {
        deleting = false;
        idx = (idx + 1) % comments.length;
        setTimeout(tick, 380);
      } else {
        setTimeout(tick, 36);
      }
    }
  }

  setTimeout(tick, 800);
}());
