(function () {
  var loginInput = document.getElementById('login-search');
  var loginSearchWrapper = document.getElementById('login-search-wrapper');
  var loginSearchResults = document.getElementById('login-search-results');
  var loginSearchClear = document.getElementById('login-search-clear');
  var offlineStatus = document.getElementById('offline-status');

  if (!loginInput) return;

  var rawRootPath = JSON.parse(document.getElementById('root-path-data').textContent);
  var rootPath = (typeof rawRootPath === 'string' && rawRootPath && rawRootPath !== '/') ? rawRootPath.replace(/\/+$/, '') : '';
  var currentDataVersion = JSON.parse(document.getElementById('data-version-data').textContent);
  var serviceWorkerCacheName = JSON.parse(document.getElementById('sw-cache-name-data').textContent);

  var topPageReloadMarkerKey = 'twicome:last-top-page-reload-version';
  var serviceWorkerUrl = rootPath + '/sw.js';
  var offlineAccess = window.TwicomeOfflineAccess || {
    createEmpty: function () { return { comments: new Set(), stats: new Set(), quiz: new Set() }; },
    getStorageKey: function () { return null; },
    isAccessible: function (routes, route, login) {
      var normalized = String(login || '').trim().toLowerCase();
      return Boolean(routes && routes[route] && normalized && routes[route].has(normalized));
    },
    read: function () { return this.createEmpty(); },
  };
  var offlineAccessStorageKey = offlineAccess.getStorageKey(rootPath);

  var statsLink = document.getElementById('stats-link');
  var quizLink = document.getElementById('quiz-link');
  var quickLinkElements = Array.from(document.querySelectorAll('.quick-link[data-prefetch-login]'));
  var streamerFilter = document.getElementById('streamer-filter');
  var sortSelect = document.getElementById('sort-select');
  var form = loginInput.closest('form');

  var maxCandidates = 25;
  var usersIndexUrl = rootPath + '/api/users/index';
  var statsPathTemplate = rootPath + '/u/__LOGIN_PLACEHOLDER__/stats';
  var quizPathTemplate = rootPath + '/u/__LOGIN_PLACEHOLDER__/quiz';
  var commentsPathTemplate = rootPath + '/u/__LOGIN_PLACEHOLDER__';
  var commentPrefetchConcurrency = 2;

  var indexedUsers = [];
  var loginMap = new Map();
  var displayMap = new Map();
  var usersLoaded = false;
  var usersLoadPromise = null;
  var currentSort = 'login';
  var streamerFilterSet = null;
  var offlineMode = navigator.onLine === false;
  var offlineAccessibleRoutes = offlineAccess.read(rootPath);
  var activeCommentPrefetchCount = 0;
  var commentPrefetchFlushScheduled = false;
  var resolvedInputPrefetchTimer = null;
  var queuedCommentPrefetches = [];
  var queuedCommentPrefetchKeys = new Set();
  var prefetchedCommentPages = new Set();
  var prefetchingCommentPages = new Set();
  var commentsPrefetchTransportMode = 'direct-fetch';

  function waitForServiceWorkerControl(timeoutMs) {
    timeoutMs = timeoutMs || 3000;
    if (!('serviceWorker' in navigator)) return Promise.resolve(false);
    if (navigator.serviceWorker.controller) return Promise.resolve(true);
    return new Promise(function (resolve) {
      var settled = false;
      var finish = function (controlled) {
        if (settled) return;
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

  var commentsPrefetchTransportReadyPromise = ('serviceWorker' in navigator)
    ? navigator.serviceWorker.register(serviceWorkerUrl, { scope: rootPath + '/' })
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

  function pathForLogin(template, login) {
    return template.replace('__LOGIN_PLACEHOLDER__', encodeURIComponent(login));
  }

  function buildCommentsUrl(login, platform) {
    platform = platform || 'twitch';
    return pathForLogin(commentsPathTemplate, login) + '?platform=' + encodeURIComponent(platform);
  }

  function normalizePrefetchKey(login, platform) {
    platform = platform || 'twitch';
    var normalizedLogin = String(login || '').trim().toLowerCase();
    var normalizedPlatform = String(platform || 'twitch').trim().toLowerCase() || 'twitch';
    if (!normalizedLogin) return '';
    return normalizedPlatform + ':' + normalizedLogin;
  }

  function scheduleCommentPrefetchFlush() {
    if (commentPrefetchFlushScheduled || offlineMode) return;
    commentPrefetchFlushScheduled = true;
    var run = function () {
      commentPrefetchFlushScheduled = false;
      flushCommentPrefetchQueue();
    };
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(run, { timeout: 1200 });
      return;
    }
    window.setTimeout(run, 150);
  }

  function prefetchCommentPageViaServiceWorker(url) {
    return commentsPrefetchTransportReadyPromise.then(function (registration) {
      var worker = registration && (registration.active || registration.waiting || registration.installing);
      if (!worker) throw new Error('service_worker_unavailable');
      return new Promise(function (resolve, reject) {
        var channel = new MessageChannel();
        var timerId = window.setTimeout(function () {
          reject(new Error('service_worker_prefetch_timeout'));
        }, 6000);
        channel.port1.onmessage = function (event) {
          window.clearTimeout(timerId);
          var data = event.data || {};
          if (data.ok) { resolve(true); return; }
          reject(new Error(data.error || 'service_worker_prefetch_failed'));
        };
        worker.postMessage({ type: 'twicome-prefetch-comments', url: url }, [channel.port2]);
      });
    });
  }

  async function prefetchCommentPage(login, platform) {
    platform = platform || 'twitch';
    var key = normalizePrefetchKey(login, platform);
    if (!key || offlineMode || prefetchedCommentPages.has(key) || prefetchingCommentPages.has(key)) return;
    var url = buildCommentsUrl(login, platform);
    prefetchingCommentPages.add(key);
    try {
      var usedServiceWorker = false;
      try {
        await prefetchCommentPageViaServiceWorker(url);
        commentsPrefetchTransportMode = 'service-worker-message';
        usedServiceWorker = true;
      } catch (swError) {
        var response = await fetch(url, {
          credentials: 'same-origin',
          headers: { Accept: 'text/html', 'X-Twicome-Prefetch': '1' },
        });
        if (!response.ok) throw new Error('prefetch_failed:' + response.status);
        var responseForCache = response.clone();
        await response.text();
        commentsPrefetchTransportMode = 'direct-fetch';
        if (window.location.hostname === 'localhost' || window.location.protocol === 'https:') {
          try {
            var cache = await caches.open(serviceWorkerCacheName);
            await cache.put(url, responseForCache);
            commentsPrefetchTransportMode = 'window-cache-put';
          } catch (_) {}
        }
        if (swError) console.warn('Service worker prefetch fallback:', swError);
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

  async function flushCommentPrefetchQueue() {
    if (offlineMode) return;
    while (activeCommentPrefetchCount < commentPrefetchConcurrency && queuedCommentPrefetches.length) {
      var next = queuedCommentPrefetches.shift();
      if (!next) break;
      queuedCommentPrefetchKeys.delete(next.key);
      if (prefetchedCommentPages.has(next.key) || prefetchingCommentPages.has(next.key)) continue;
      activeCommentPrefetchCount += 1;
      prefetchCommentPage(next.login, next.platform)
        .finally(function () {
          activeCommentPrefetchCount = Math.max(0, activeCommentPrefetchCount - 1);
          scheduleCommentPrefetchFlush();
        });
    }
    if (queuedCommentPrefetches.length) scheduleCommentPrefetchFlush();
  }

  function queueCommentPrefetch(login, platform) {
    platform = platform || 'twitch';
    var key = normalizePrefetchKey(login, platform);
    if (!key || offlineMode) return;
    if (prefetchedCommentPages.has(key) || prefetchingCommentPages.has(key) || queuedCommentPrefetchKeys.has(key)) return;
    queuedCommentPrefetches.push({ key: key, login: login, platform: platform });
    queuedCommentPrefetchKeys.add(key);
    scheduleCommentPrefetchFlush();
  }

  window.__twicomeCommentPrefetch = {
    getState: function () {
      return {
        activeCount: activeCommentPrefetchCount,
        mode: commentsPrefetchTransportMode,
        offlineMode: offlineMode,
        prefetched: Array.from(prefetchedCommentPages),
        prefetching: Array.from(prefetchingCommentPages),
        queued: queuedCommentPrefetches.map(function (item) { return item.key; }),
        serviceWorkerControlled: Boolean('serviceWorker' in navigator && navigator.serviceWorker.controller),
      };
    },
    queue: function (login, platform) { queueCommentPrefetch(login, platform || 'twitch'); },
  };

  function scheduleResolvedInputPrefetch() {
    if (resolvedInputPrefetchTimer) window.clearTimeout(resolvedInputPrefetchTimer);
    if (offlineMode) return;
    resolvedInputPrefetchTimer = window.setTimeout(async function () {
      try { await ensureUsersLoaded(); } catch (_) { return; }
      var resolved = resolveLogin(loginInput.value);
      if (resolved) queueCommentPrefetch(resolved);
    }, 250);
  }

  function primeInitialCommentPrefetches() {
    var defaultLogin = form.dataset.defaultLogin || loginInput.value.trim();
    if (defaultLogin) queueCommentPrefetch(defaultLogin);
    for (var i = 0; i < quickLinkElements.length; i++) {
      var link = quickLinkElements[i];
      var login = link.dataset.prefetchLogin;
      var platform = link.dataset.prefetchPlatform || 'twitch';
      if (!login) continue;
      queueCommentPrefetch(login, platform);
    }
  }

  function setLinkState(link, enabled) {
    link.setAttribute('aria-disabled', String(!enabled));
  }

  function setActionLinkState(enabled) {
    var disabled = String(!enabled);
    statsLink.setAttribute('aria-disabled', disabled);
    quizLink.setAttribute('aria-disabled', disabled);
  }

  function setActionLinks(login) {
    statsLink.href = pathForLogin(statsPathTemplate, login) + '?platform=twitch';
    quizLink.href = pathForLogin(quizPathTemplate, login) + '?platform=twitch';
  }

  function showCandidateMessage(message) {
    loginSearchResults.innerHTML = '<div class="search-empty">' + message + '</div>';
    loginSearchResults.hidden = false;
  }

  function refreshOfflineAccessibleRoutes() {
    offlineAccessibleRoutes = offlineAccess.read(rootPath);
  }

  function hasOfflineRouteAccess(route, login) {
    if (!offlineMode) return true;
    return offlineAccess.isAccessible(offlineAccessibleRoutes, route, login);
  }

  function countOfflineCommentUsers() {
    if (!usersLoaded) return offlineAccessibleRoutes.comments.size;
    var count = 0;
    for (var i = 0; i < indexedUsers.length; i++) {
      if (hasOfflineRouteAccess('comments', indexedUsers[i].login)) count += 1;
    }
    return count;
  }

  function updateOfflineStatus() {
    if (!offlineMode) { offlineStatus.hidden = true; return; }
    var count = countOfflineCommentUsers();
    if (count > 0) {
      offlineStatus.textContent = 'オフライン中です。閲覧済みの ' + count + ' ユーザのみ候補に表示します。';
    } else {
      offlineStatus.textContent = 'オフライン中です。閲覧済みユーザがまだ見つからないため、候補は表示できません。';
    }
    offlineStatus.hidden = false;
  }

  function refreshOfflineState(opts) {
    opts = opts || {};
    refreshOfflineAccessibleRoutes();
    updateOfflineStatus();
    syncActionLinksFromInput();
    if (opts.rerender && !loginSearchResults.hidden) {
      void renderCandidates(loginInput.value);
    }
  }

  function hydrateUsers(rawUsers) {
    var normalizedUsers = Array.isArray(rawUsers) ? rawUsers.map(function (user) {
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
    for (var i = 0; i < indexedUsers.length; i++) {
      var user = indexedUsers[i];
      if (!user.displayLower) continue;
      if (!displayMap.has(user.displayLower)) displayMap.set(user.displayLower, []);
      displayMap.get(user.displayLower).push(user.login);
    }
  }

  async function ensureUsersLoaded() {
    if (usersLoaded) return indexedUsers;
    if (usersLoadPromise) return usersLoadPromise;
    usersLoadPromise = fetch(usersIndexUrl, { headers: { Accept: 'application/json' } })
      .then(async function (response) {
        if (!response.ok) throw new Error('failed_to_load_users:' + response.status);
        var data = await response.json();
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

  function formatRelativeTime(isoStr) {
    if (!isoStr) return null;
    var diff = Date.now() - new Date(isoStr).getTime();
    var mins = Math.floor(diff / 60000);
    if (mins < 60) return Math.max(1, mins) + '分前';
    var hours = Math.floor(mins / 60);
    if (hours < 24) return hours + '時間前';
    var days = Math.floor(hours / 24);
    if (days < 30) return days + '日前';
    var months = Math.floor(days / 30);
    if (months < 12) return months + 'ヶ月前';
    return Math.floor(months / 12) + '年前';
  }

  function formatCandidateLabel(user) {
    if (!user.displayName || user.displayLower === user.loginLower) return user.login;
    return user.displayName + ' (' + user.login + ')';
  }

  function resolveLogin(input) {
    if (!usersLoaded) return '';
    var normalized = input.trim().toLowerCase();
    if (!normalized) return '';
    var loginMatch = loginMap.get(normalized);
    if (loginMatch && hasOfflineRouteAccess('comments', loginMatch)) return loginMatch;
    var displayMatches = (displayMap.get(normalized) || []).filter(function (login) { return hasOfflineRouteAccess('comments', login); });
    if (displayMatches.length === 1) return displayMatches[0];
    return '';
  }

  function applyStreamerFilter(users) {
    if (streamerFilterSet === null) return users;
    if (streamerFilterSet === 'loading') return [];
    return users.filter(function (user) { return streamerFilterSet.has(user.login); });
  }

  function applyOfflineAvailabilityFilter(users) {
    if (!offlineMode) return users;
    return users.filter(function (user) { return hasOfflineRouteAccess('comments', user.login); });
  }

  function applySort(users) {
    var sorted = users.slice();
    if (currentSort === 'count_desc') {
      sorted.sort(function (a, b) { return b.commentCount - a.commentCount; });
    } else if (currentSort === 'count_asc') {
      sorted.sort(function (a, b) { return a.commentCount - b.commentCount; });
    } else if (currentSort === 'recent') {
      sorted.sort(function (a, b) {
        if (!a.lastCommentAt && !b.lastCommentAt) return 0;
        if (!a.lastCommentAt) return 1;
        if (!b.lastCommentAt) return -1;
        return new Date(b.lastCommentAt) - new Date(a.lastCommentAt);
      });
    }
    return sorted;
  }

  function getCandidates(input) {
    var q = input.trim().toLowerCase();
    if (!q) {
      var pool = applyOfflineAvailabilityFilter(applyStreamerFilter(indexedUsers));
      return applySort(pool).slice(0, maxCandidates);
    }
    var loginStarts = [], displayStarts = [], loginContains = [], displayContains = [];
    var filtered = applyOfflineAvailabilityFilter(applyStreamerFilter(indexedUsers));
    for (var i = 0; i < filtered.length; i++) {
      var user = filtered[i];
      var matchedLogin = user.loginLower.includes(q);
      var matchedDisplay = user.displayLower.includes(q);
      if (!matchedLogin && !matchedDisplay) continue;
      if (user.loginLower.startsWith(q)) loginStarts.push(user);
      else if (user.displayLower.startsWith(q)) displayStarts.push(user);
      else if (matchedLogin) loginContains.push(user);
      else displayContains.push(user);
    }
    var groups = [loginStarts, displayStarts, loginContains, displayContains];
    var ordered = groups.map(function (g) { return applySort(g); }).reduce(function (a, b) { return a.concat(b); }, []);
    var deduped = [];
    var seen = new Set();
    for (var j = 0; j < ordered.length; j++) {
      if (seen.has(ordered[j].login)) continue;
      seen.add(ordered[j].login);
      deduped.push(ordered[j]);
      if (deduped.length >= maxCandidates) break;
    }
    return deduped;
  }

  function buildCandidateItem(user) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'search-item';
    btn.setAttribute('role', 'option');

    var avatarEl = document.createElement('span');
    avatarEl.className = 'search-item-avatar';
    if (user.profileImageUrl) {
      var img = document.createElement('img');
      img.src = user.profileImageUrl;
      img.alt = '';
      img.loading = 'lazy';
      avatarEl.appendChild(img);
    } else {
      avatarEl.textContent = (user.displayName || user.login)[0].toUpperCase();
    }
    btn.appendChild(avatarEl);

    var bodyEl = document.createElement('div');
    bodyEl.className = 'search-item-body';
    var nameEl = document.createElement('div');
    nameEl.className = 'search-item-name';
    nameEl.textContent = formatCandidateLabel(user);
    bodyEl.appendChild(nameEl);
    if (user.commentCount > 0) {
      var metaEl = document.createElement('div');
      metaEl.className = 'search-item-meta';
      var rel = formatRelativeTime(user.lastCommentAt);
      metaEl.textContent = rel ? '最終活動: ' + rel : '';
      bodyEl.appendChild(metaEl);
    }
    btn.appendChild(bodyEl);

    if (user.commentCount > 0) {
      var countEl = document.createElement('span');
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

  function hideCandidates() { loginSearchResults.hidden = true; }

  function selectLogin(login) {
    loginInput.value = login;
    loginInput.setCustomValidity('');
    setActionLinks(login);
    syncActionLinksFromInput();
    queueCommentPrefetch(login);
    hideCandidates();
    updateClearBtn();
  }

  async function renderCandidates(input) {
    if (!usersLoaded) showCandidateMessage('候補を読み込み中...');
    try { await ensureUsersLoaded(); } catch (_) {
      setActionLinkState(false);
      showCandidateMessage('候補の読み込みに失敗しました');
      return;
    }
    if (offlineMode) refreshOfflineAccessibleRoutes();
    var candidates = getCandidates(input);
    loginSearchResults.innerHTML = '';
    if (!candidates.length) {
      if (offlineMode) {
        var message = countOfflineCommentUsers() > 0
          ? 'オフライン中の閲覧済みユーザでは見つかりません'
          : 'オフライン中に開ける閲覧済みユーザがありません';
        showCandidateMessage(message);
        return;
      }
      showCandidateMessage('該当するユーザが見つかりません');
      return;
    }
    var fragment = document.createDocumentFragment();
    for (var i = 0; i < candidates.length; i++) {
      fragment.appendChild(buildCandidateItem(candidates[i]));
    }
    loginSearchResults.appendChild(fragment);
    loginSearchResults.hidden = false;
  }

  function syncActionLinksFromInput() {
    var currentValue = loginInput.value.trim();
    if (!usersLoaded) {
      if (currentValue) { setActionLinks(currentValue); setActionLinkState(!offlineMode); }
      else { setActionLinkState(false); }
      return;
    }
    var resolved = resolveLogin(loginInput.value);
    if (!resolved) { setActionLinkState(false); return; }
    setActionLinks(resolved);
    if (offlineMode) {
      setLinkState(statsLink, hasOfflineRouteAccess('stats', resolved));
      setLinkState(quizLink, hasOfflineRouteAccess('quiz', resolved));
      return;
    }
    setActionLinkState(true);
  }

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
    if (event.key === 'Escape') hideCandidates();
  });

  document.addEventListener('click', function (event) {
    if (!loginSearchWrapper.contains(event.target)) hideCandidates();
  });

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    try { await ensureUsersLoaded(); } catch (_) {
      loginInput.setCustomValidity('候補の読み込みに失敗しました。しばらくしてから再度お試しください');
      loginInput.reportValidity();
      loginInput.focus();
      return;
    }
    if (offlineMode) refreshOfflineAccessibleRoutes();
    var resolved = resolveLogin(loginInput.value);
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
      var streamer = this.value;
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
        var res = await fetch(rootPath + '/api/users/commenters?streamer=' + encodeURIComponent(streamer));
        var data = await res.json();
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

  for (var i = 0; i < quickLinkElements.length; i++) {
    (function (link) {
      var login = link.dataset.prefetchLogin;
      var platform = link.dataset.prefetchPlatform || 'twitch';
      if (!login) return;
      var triggerPrefetch = function () { queueCommentPrefetch(login, platform); };
      link.addEventListener('pointerenter', triggerPrefetch, { passive: true });
      link.addEventListener('focus', triggerPrefetch);
    })(quickLinkElements[i]);
  }

  window.addEventListener('pageshow', function () { refreshOfflineState({ rerender: true }); });
  window.addEventListener('focus', function () { refreshOfflineState({ rerender: true }); });
  window.addEventListener('storage', function (event) {
    if (offlineAccessStorageKey && event.key && event.key !== offlineAccessStorageKey) return;
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
    var banner = document.getElementById('pwa-banner');
    var bannerTitle = document.getElementById('pwa-banner-title');
    var bannerSub = document.getElementById('pwa-banner-sub');
    if (!banner) return;
    if (window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone) {
      banner.style.display = 'none';
      return;
    }
    var deferredPrompt = null;
    window.addEventListener('beforeinstallprompt', function (e) {
      e.preventDefault();
      deferredPrompt = e;
      banner.classList.add('pwa-banner--installable');
      bannerSub.textContent = 'タップしてアプリをインストール';
    });
    banner.addEventListener('click', async function () {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      var result = await deferredPrompt.userChoice;
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
      if (e.key === 'Enter' || e.key === ' ') banner.click();
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
      var data = event.data || {};
      if (data.type !== 'twicome-top-page-updated') return;
      if (!data.dataVersion || data.dataVersion === currentDataVersion) return;
      try {
        if (sessionStorage.getItem(topPageReloadMarkerKey) === data.dataVersion) return;
        sessionStorage.setItem(topPageReloadMarkerKey, data.dataVersion);
      } catch (_) {}
      window.location.reload();
    });
  }
})();
