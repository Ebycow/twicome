(function() {
  'use strict';

  const STORAGE_PREFIX = 'twicome:offline-accessible-routes:v1';
  const ROUTES = ['comments', 'stats', 'quiz'];

  function normalizeRootPath(rootPath) {
    const value = typeof rootPath === 'string' ? rootPath.trim() : '';
    return value && value !== '/' ? value.replace(/\/+$/, '') : '';
  }

  function getStorageKey(rootPath) {
    const normalizedRootPath = normalizeRootPath(rootPath);
    return `${STORAGE_PREFIX}:${normalizedRootPath || '/'}`;
  }

  function createEmpty() {
    return {
      comments: new Set(),
      stats: new Set(),
      quiz: new Set(),
    };
  }

  function normalizeLogin(login) {
    const value = String(login || '').trim().toLowerCase();
    return value || '';
  }

  function read(rootPath) {
    const routes = createEmpty();

    try {
      const raw = localStorage.getItem(getStorageKey(rootPath));
      if (!raw) return routes;

      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return routes;

      for (const route of ROUTES) {
        const values = Array.isArray(parsed[route]) ? parsed[route] : [];
        for (const login of values) {
          const normalized = normalizeLogin(login);
          if (normalized) routes[route].add(normalized);
        }
      }
    } catch {}

    return routes;
  }

  function write(rootPath, routes) {
    try {
      localStorage.setItem(getStorageKey(rootPath), JSON.stringify({
        comments: [...routes.comments].sort(),
        stats: [...routes.stats].sort(),
        quiz: [...routes.quiz].sort(),
      }));
    } catch {}
  }

  function markVisited(rootPath, route, login) {
    if (!ROUTES.includes(route)) return false;

    const normalizedLogin = normalizeLogin(login);
    if (!normalizedLogin) return false;

    const routes = read(rootPath);
    if (routes[route].has(normalizedLogin)) return false;

    routes[route].add(normalizedLogin);
    write(rootPath, routes);
    return true;
  }

  function isAccessible(routes, route, login) {
    if (!routes || !ROUTES.includes(route)) return false;
    const normalizedLogin = normalizeLogin(login);
    return normalizedLogin ? routes[route].has(normalizedLogin) : false;
  }

  window.TwicomeOfflineAccess = {
    createEmpty,
    getStorageKey,
    isAccessible,
    markVisited,
    normalizeLogin,
    normalizeRootPath,
    read,
    write,
  };
})();
