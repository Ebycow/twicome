(function () {
  const rootPathEl = document.getElementById('root-path-data');
  if (!rootPathEl) { return; }

  const rawRootPath = JSON.parse(rootPathEl.textContent);
  const rootPath = (typeof rawRootPath === 'string' && rawRootPath && rawRootPath !== '/') ? rawRootPath.replace(/\/+$/, '') : '';

  // ── 投票機能 ──────────────────────────────────────────────────────────────

  window.vote = function (btn, commentId, type) {
    const url = `${rootPath}/${type === 'like' ? 'like' : 'dislike'}/${encodeURIComponent(commentId)}`;
    fetch(url, { method: 'POST' })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data.error) { return; }
        const count = parseInt(btn.getAttribute('data-count') || '0', 10) + 1;
        btn.setAttribute('data-count', count);
        const icon = type === 'like' ? '<i class="fa-solid fa-thumbs-up"></i>' : '<i class="fa-solid fa-thumbs-down"></i>';
        btn.innerHTML = `${icon} ${count}`;
      })
      .catch(function () {});
  };

  // ── 投票数の遅延ロード ────────────────────────────────────────────────────

  /**
   * 遅延ロード対象の投票コントロールをAPIから取得した最新の投票数で更新する。
   */
  function loadVoteCounts() {
    const controls = document.querySelectorAll('[data-vote-controls="deferred"]');
    if (controls.length === 0) { return; }

    const ids = [];
    controls.forEach(function (el) {
      const id = el.getAttribute('data-comment-id');
      if (id) { ids.push(id); }
    });

    if (ids.length === 0) { return; }

    fetch(`${rootPath}/api/comments/votes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment_ids: ids }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        const items = data.items || {};
        controls.forEach(function (el) {
          const id = el.getAttribute('data-comment-id');
          const counts = items[id];
          if (!counts) { return; }

          const btns = el.querySelectorAll('.vote-btn');
          if (btns[0]) {
            btns[0].setAttribute('data-count', counts.twicome_likes_count || 0);
            btns[0].innerHTML = `<i class="fa-solid fa-thumbs-up"></i> ${counts.twicome_likes_count || 0}`;
          }
          if (btns[1]) {
            btns[1].setAttribute('data-count', counts.twicome_dislikes_count || 0);
            btns[1].innerHTML = `<i class="fa-solid fa-thumbs-down"></i> ${counts.twicome_dislikes_count || 0}`;
          }
        });
      })
      .catch(function () {});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadVoteCounts);
  } else {
    loadVoteCounts();
  }
}());
