(function () {
  if (!('serviceWorker' in navigator)) {return;}
  const el = document.getElementById('app-root-path');
  const raw = el ? JSON.parse(el.textContent) : '';
  const rootPath = (typeof raw === 'string' && raw && raw !== '/') ? raw.replace(/\/+$/, '') : '';
  window.addEventListener('load', function () {
    navigator.serviceWorker.register(`${rootPath  }/sw.js`, { scope: `${rootPath  }/` }).catch(function () {});
  });
})();
