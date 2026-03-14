(function () {
  var shareInput = document.getElementById('share-url');
  if (!shareInput) return;
  shareInput.value = window.location.href;

  document.getElementById('copy-btn').addEventListener('click', function () {
    navigator.clipboard.writeText(shareInput.value).then(function () {
      var btn = document.getElementById('copy-btn');
      btn.textContent = 'コピーしました！';
      setTimeout(function () { btn.textContent = 'URLをコピー'; }, 2000);
    });
  });
})();
