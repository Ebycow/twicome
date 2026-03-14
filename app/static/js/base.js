(function () {
  if (!('serviceWorker' in navigator)) return;
  var el = document.getElementById('app-root-path');
  var raw = el ? JSON.parse(el.textContent) : '';
  var rootPath = (typeof raw === 'string' && raw && raw !== '/') ? raw.replace(/\/+$/, '') : '';
  window.addEventListener('load', function () {
    navigator.serviceWorker.register(rootPath + '/sw.js', { scope: rootPath + '/' }).catch(function () {});
  });
})();
