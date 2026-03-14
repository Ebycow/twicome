(function () {
  const loginInput = document.getElementById('login-search');
  const loginSearchWrapper = document.getElementById('login-search-wrapper');
  const loginSearchResults = document.getElementById('login-search-results');
  const loginSearchClear = document.getElementById('login-search-clear');
  const offlineStatus = document.getElementById('offline-status');

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
   *
   * @param timeoutMs
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
      var onControllerChange = function () { finish(Boolean(navigator.serviceWorker.controller)); };
      var timerId = window.setTimeout(function () { finish(Boolean(navigator.serviceWorker.controller)); }, timeoutMs);
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
   *
   * @param template
   * @param login
   */
  function pathForLogin(template, login) {
    return template.replace('__LOGIN_PLACEHOLDER__', encodeURIComponent(login));
  }

  /**
   *
   * @param login
   * @param platform
   */
  function buildCommentsUrl(login, platform) {
    platform = platform || 'twitch';
    return `${pathForLogin(commentsPathTemplate, login)  }?platform=${  encodeURIComponent(platform)}`;
  }

  /**
   *
   * @param login
   * @param platform
   */
  function normalizePrefetchKey(login, platform) {
    platform = platform || 'twitch';
    const normalizedLogin = String(login || '').trim().toLowerCase();
    const normalizedPlatform = String(platform || 'twitch').trim().toLowerCase() || 'twitch';
    if (!normalizedLogin) {return '';}
    return `${normalizedPlatform  }:${  normalizedLogin}`;
  }

  /**
   *
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
   *
   * @param url
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
   *
   * @param login
   * @param platform
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
   *
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
   *
   * @param login
   * @param platform
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
   *
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
   *
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
   *
   * @param link
   * @param enabled
   */
  function setLinkState(link, enabled) {
    link.setAttribute('aria-disabled', String(!enabled));
  }

  /**
   *
   * @param enabled
   */
  function setActionLinkState(enabled) {
    const disabled = String(!enabled);
    statsLink.setAttribute('aria-disabled', disabled);
    quizLink.setAttribute('aria-disabled', disabled);
  }

  /**
   *
   * @param login
   */
  function setActionLinks(login) {
    statsLink.href = `${pathForLogin(statsPathTemplate, login)  }?platform=twitch`;
    quizLink.href = `${pathForLogin(quizPathTemplate, login)  }?platform=twitch`;
  }

  /**
   *
   * @param message
   */
  function showCandidateMessage(message) {
    loginSearchResults.innerHTML = `<div class="search-empty">${  message  }</div>`;
    loginSearchResults.hidden = false;
  }

  /**
   *
   */
  function refreshOfflineAccessibleRoutes() {
    offlineAccessibleRoutes = offlineAccess.read(rootPath);
  }

  /**
   *
   * @param route
   * @param login
   */
  function hasOfflineRouteAccess(route, login) {
    if (!offlineMode) {return true;}
    return offlineAccess.isAccessible(offlineAccessibleRoutes, route, login);
  }

  /**
   *
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
   *
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
   *
   * @param opts
   */
  function refreshOfflineState(opts) {
    opts = opts || {};
    refreshOfflineAccessibleRoutes();
    updateOfflineStatus();
    syncActionLinksFromInput();
    if (opts.rerender && !loginSearchResults.hidden) {
      void renderCandidates(loginInput.value);
    }
  }

  /**
   *
   * @param rawUsers
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
    displayMap = new Map();
    for (let i = 0; i < indexedUsers.length; i++) {
      const user = indexedUsers[i];
      if (!user.displayLower) {continue;}
      if (!displayMap.has(user.displayLower)) {displayMap.set(user.displayLower, []);}
      displayMap.get(user.displayLower).push(user.login);
    }
  }

  /**
   *
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
   *
   * @param isoStr
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
   *
   * @param user
   */
  function formatCandidateLabel(user) {
    if (!user.displayName || user.displayLower === user.loginLower) {return user.login;}
    return `${user.displayName  } (${  user.login  })`;
  }

  /**
   *
   * @param input
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
   *
   * @param users
   */
  function applyStreamerFilter(users) {
    if (streamerFilterSet === null) {return users;}
    if (streamerFilterSet === 'loading') {return [];}
    return users.filter(function (user) { return streamerFilterSet.has(user.login); });
  }

  /**
   *
   * @param users
   */
  function applyOfflineAvailabilityFilter(users) {
    if (!offlineMode) {return users;}
    return users.filter(function (user) { return hasOfflineRouteAccess('comments', user.login); });
  }

  /**
   *
   * @param users
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
   *
   * @param input
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
   *
   * @param user
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
   *
   */
  function hideCandidates() { loginSearchResults.hidden = true; }

  /**
   *
   * @param login
   */
  function selectLogin(login) {
    loginInput.value = login;
    loginInput.setCustomValidity('');
    setActionLinks(login);
    syncActionLinksFromInput();
    queueCommentPrefetch(login);
    hideCandidates();
    updateClearBtn();
  }

  /**
   *
   * @param input
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
   *
   */
  function syncActionLinksFromInput() {
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
   *
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
    try { await ensureUsersLoaded(); } catch (_) {
      loginInput.setCustomValidity('候補の読み込みに失敗しました。しばらくしてから再度お試しください');
      loginInput.reportValidity();
      loginInput.focus();
      return;
    }
    if (offlineMode) {refreshOfflineAccessibleRoutes();}
    const resolved = resolveLogin(loginInput.value);
    if (resolved) { window.location.href = buildCommentsUrl(resolved); return; }
    void renderCandidates(loginInput.value);
    loginInput.setCustomValidity(offlineMode
      ? 'オフライン中は閲覧済みのユーザのみ開けます'
      : '候補からTwitchユーザを選択してください');
    loginInput.reportValidity();
    loginInput.focus();
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

  window.addEventListener('pageshow', function () { refreshOfflineState({ rerender: true }); });
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

  // ---- SW version update listener ----
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', function (event) {
      const data = event.data || {};
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
