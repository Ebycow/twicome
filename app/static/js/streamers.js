(function () {
  const searchInput = document.getElementById('streamers-search');
  const searchClear = document.getElementById('streamers-search-clear');
  const countEl = document.getElementById('streamers-count');
  const grid = document.getElementById('streamers-grid');

  if (!grid) { return; }

  const cards = Array.from(grid.querySelectorAll('.streamer-card'));

  /**
   * 表示中のカード数をカウント表示要素に反映する。
   */
  function updateCount() {
    const visible = cards.filter(function (c) { return !c.hidden; }).length;
    if (countEl) {
      countEl.textContent = `${visible.toLocaleString('ja-JP')} 件`;
    }
  }

  /**
   * クエリ文字列に一致するカードだけを表示してカウントを更新する。
   * @param query - フィルタに使う検索文字列
   */
  function filterCards(query) {
    const q = query.trim().toLowerCase();
    cards.forEach(function (card) {
      if (!q) {
        card.hidden = false;
        return;
      }
      const login = (card.dataset.login || '').toLowerCase();
      const name = (card.dataset.name || '').toLowerCase();
      card.hidden = login.indexOf(q) === -1 && name.indexOf(q) === -1;
    });
    updateCount();
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      const q = searchInput.value;
      if (searchClear) { searchClear.style.display = q ? 'flex' : 'none'; }
      filterCards(q);
    });
  }

  if (searchClear) {
    searchClear.addEventListener('click', function () {
      searchInput.value = '';
      searchClear.style.display = 'none';
      filterCards('');
      searchInput.focus();
    });
  }

  updateCount();
}());
