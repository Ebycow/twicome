(function () {
  var searchInput = document.getElementById('vods-search');
  var searchClear = document.getElementById('vods-search-clear');
  var streamerFilter = document.getElementById('streamer-filter');
  var sortSelect = document.getElementById('sort-select');
  var vodsGrid = document.getElementById('vods-grid');
  var vodsCount = document.getElementById('vods-count');
  var vodsStatus = document.getElementById('vods-status');
  var vodsPagination = document.getElementById('vods-pagination');
  var vodsLoadMore = document.getElementById('vods-load-more');

  if (!vodsGrid) { return; }

  var rawRootPath = JSON.parse(document.getElementById('root-path-data').textContent);
  var rootPath = (typeof rawRootPath === 'string' && rawRootPath && rawRootPath !== '/') ? rawRootPath.replace(/\/+$/, '') : '';

  var PAGE_SIZE = 40;
  var currentPage = 1;
  var currentTotal = 0;
  var currentPages = 0;
  var currentQuery = '';
  var currentSort = 'created_at';
  var currentStreamer = '';
  var allCards = [];
  var searchTimer = null;

  function showStatus(msg) {
    vodsStatus.textContent = msg;
    vodsStatus.hidden = false;
  }

  function hideStatus() {
    vodsStatus.hidden = true;
  }

  function formatDate(isoStr) {
    if (!isoStr) { return null; }
    try {
      // MySQL datetime "2026-03-18 12:00:00" → ISO "2026-03-18T12:00:00Z"
      var normalized = isoStr.replace(' ', 'T');
      if (normalized.indexOf('T') !== -1 && normalized.indexOf('+') === -1 && normalized.slice(-1) !== 'Z') {
        normalized += 'Z';
      }
      var d = new Date(normalized);
      if (isNaN(d.getTime())) { return null; }
      return d.toLocaleDateString('ja-JP', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'Asia/Tokyo' });
    } catch (e) {
      return null;
    }
  }

  function formatDuration(seconds) {
    if (!seconds) { return null; }
    var h = Math.floor(seconds / 3600);
    var m = Math.floor((seconds % 3600) / 60);
    var s = seconds % 60;
    if (h > 0) {
      return h + 'h ' + m + 'm';
    }
    return m + 'm ' + s + 's';
  }

  function buildCard(vod) {
    var card = document.createElement('div');
    card.className = 'vod-card';
    card.setAttribute('role', 'listitem');

    var title = document.createElement('div');
    title.className = 'vod-card-title';
    title.textContent = vod.title || '（タイトルなし）';
    card.appendChild(title);

    var owner = document.createElement('div');
    owner.className = 'vod-card-owner';
    owner.textContent = vod.owner_display_name || vod.owner_login;
    card.appendChild(owner);

    var meta = document.createElement('div');
    meta.className = 'vod-card-meta';

    var dateStr = vod.created_at_jst || formatDate(vod.created_at_utc);
    if (dateStr) {
      var dateSpan = document.createElement('span');
      dateSpan.textContent = dateStr;
      meta.appendChild(dateSpan);
    }

    var dur = formatDuration(vod.length_seconds);
    if (dur) {
      var durSpan = document.createElement('span');
      durSpan.textContent = '⏱ ' + dur;
      meta.appendChild(durSpan);
    }

    if (vod.game_name) {
      var gameSpan = document.createElement('span');
      gameSpan.textContent = '🎮 ' + vod.game_name;
      meta.appendChild(gameSpan);
    }

    card.appendChild(meta);

    var badges = document.createElement('div');
    badges.className = 'vod-card-badges';

    if (vod.comment_count > 0) {
      var badge = document.createElement('span');
      badge.className = 'vod-card-badge';
      badge.textContent = vod.comment_count.toLocaleString('ja-JP') + ' comments';
      badges.appendChild(badge);
    }

    card.appendChild(badges);

    var link = document.createElement('a');
    link.className = 'vod-card-link';
    link.href = rootPath + '/vods/' + vod.vod_id;
    link.textContent = '▶ コメントを見る';
    card.appendChild(link);

    return card;
  }

  function appendCards(vods) {
    var frag = document.createDocumentFragment();
    vods.forEach(function (v) { frag.appendChild(buildCard(v)); });
    vodsGrid.appendChild(frag);
  }

  function loadVods(reset) {
    if (reset) {
      currentPage = 1;
      vodsGrid.innerHTML = '';
      allCards = [];
    }

    showStatus('読み込み中...');

    var params = new URLSearchParams({
      page: currentPage,
      page_size: PAGE_SIZE,
      sort: currentSort,
    });
    if (currentQuery) { params.set('q', currentQuery); }
    if (currentStreamer) { params.set('owner_login', currentStreamer); }

    fetch(rootPath + '/api/vods?' + params.toString())
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var items = data.items || [];
        currentTotal = data.total || 0;
        currentPages = data.pages || 0;

        appendCards(items);
        hideStatus();

        vodsCount.textContent = currentTotal.toLocaleString('ja-JP') + ' 件';

        if (currentPage < currentPages) {
          vodsPagination.hidden = false;
        } else {
          vodsPagination.hidden = true;
        }

        if (items.length === 0 && currentPage === 1) {
          showStatus('VOD が見つかりませんでした。');
        }
      })
      .catch(function () {
        showStatus('読み込みに失敗しました。ページを再読み込みしてください。');
      });
  }

  function scheduleSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      loadVods(true);
    }, 300);
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      currentQuery = searchInput.value.trim();
      searchClear.style.display = currentQuery ? 'flex' : 'none';
      scheduleSearch();
    });
  }

  if (searchClear) {
    searchClear.addEventListener('click', function () {
      searchInput.value = '';
      currentQuery = '';
      searchClear.style.display = 'none';
      searchInput.focus();
      loadVods(true);
    });
  }

  if (streamerFilter) {
    streamerFilter.addEventListener('change', function () {
      currentStreamer = streamerFilter.value;
      loadVods(true);
    });
  }

  if (sortSelect) {
    sortSelect.addEventListener('change', function () {
      currentSort = sortSelect.value;
      loadVods(true);
    });
  }

  if (vodsLoadMore) {
    vodsLoadMore.addEventListener('click', function () {
      currentPage += 1;
      loadVods(false);
    });
  }

  loadVods(true);
}());
