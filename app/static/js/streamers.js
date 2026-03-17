(function () {
  var searchInput = document.getElementById('streamers-search');
  var searchClear = document.getElementById('streamers-search-clear');
  var countEl = document.getElementById('streamers-count');
  var grid = document.getElementById('streamers-grid');

  if (!grid) { return; }

  var cards = Array.from(grid.querySelectorAll('.streamer-card'));

  function updateCount() {
    var visible = cards.filter(function (c) { return !c.hidden; }).length;
    if (countEl) {
      countEl.textContent = visible.toLocaleString('ja-JP') + ' 件';
    }
  }

  function filterCards(query) {
    var q = query.trim().toLowerCase();
    cards.forEach(function (card) {
      if (!q) {
        card.hidden = false;
        return;
      }
      var login = (card.dataset.login || '').toLowerCase();
      var name = (card.dataset.name || '').toLowerCase();
      card.hidden = login.indexOf(q) === -1 && name.indexOf(q) === -1;
    });
    updateCount();
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      var q = searchInput.value;
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
