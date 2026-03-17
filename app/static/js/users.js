(function () {
  var searchInput = document.getElementById('users-search');
  var searchClear = document.getElementById('users-search-clear');
  var streamerFilter = document.getElementById('streamer-filter');
  var sortSelect = document.getElementById('sort-select');
  var usersGrid = document.getElementById('users-grid');
  var usersCount = document.getElementById('users-count');
  var usersStatus = document.getElementById('users-status');

  if (!usersGrid) { return; }

  var rawRootPath = JSON.parse(document.getElementById('root-path-data').textContent);
  var rootPath = (typeof rawRootPath === 'string' && rawRootPath && rawRootPath !== '/') ? rawRootPath.replace(/\/+$/, '') : '';

  var allUsers = [];
  var activeLogins = null; // null = no streamer filter, Set = filtered logins
  var currentQuery = '';
  var currentSort = 'login';

  function showStatus(msg) {
    usersStatus.textContent = msg;
    usersStatus.hidden = false;
  }

  function hideStatus() {
    usersStatus.hidden = true;
  }

  function formatCount(n) {
    if (!n) { return '0 comments'; }
    return n.toLocaleString('ja-JP') + ' comments';
  }

  function formatDate(iso) {
    if (!iso) { return null; }
    try {
      var d = new Date(iso);
      return d.toLocaleDateString('ja-JP', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) {
      return null;
    }
  }

  function buildAvatar(user) {
    if (user.profile_image_url) {
      var img = document.createElement('img');
      img.src = user.profile_image_url;
      img.alt = user.display_name || user.login;
      img.width = 40;
      img.height = 40;
      var wrap = document.createElement('span');
      wrap.className = 'user-card-avatar';
      wrap.appendChild(img);
      return wrap;
    }
    var fallback = document.createElement('span');
    fallback.className = 'user-card-avatar';
    var label = (user.display_name || user.login || '?').charAt(0).toUpperCase();
    fallback.textContent = label;
    return fallback;
  }

  function buildCard(user) {
    var card = document.createElement('div');
    card.className = 'user-card';
    card.setAttribute('role', 'listitem');

    // Header
    var header = document.createElement('div');
    header.className = 'user-card-header';

    var avatar = buildAvatar(user);
    header.appendChild(avatar);

    var info = document.createElement('div');
    info.className = 'user-card-info';

    var name = document.createElement('div');
    name.className = 'user-card-name';
    name.textContent = user.display_name || user.login;
    info.appendChild(name);

    if (user.display_name && user.display_name !== user.login) {
      var loginEl = document.createElement('div');
      loginEl.className = 'user-card-login';
      loginEl.textContent = user.login;
      info.appendChild(loginEl);
    }

    header.appendChild(info);

    if (user.comment_count > 0) {
      var countEl = document.createElement('span');
      countEl.className = 'user-card-count';
      countEl.textContent = formatCount(user.comment_count);
      header.appendChild(countEl);
    }

    card.appendChild(header);

    if (user.last_comment_at) {
      var meta = document.createElement('div');
      meta.className = 'user-card-meta';
      var dateStr = formatDate(user.last_comment_at);
      if (dateStr) {
        meta.textContent = '最終コメント: ' + dateStr;
        card.appendChild(meta);
      }
    }

    // Links
    var links = document.createElement('div');
    links.className = 'user-card-links';

    var commentsLink = document.createElement('a');
    commentsLink.className = 'user-card-link user-card-link-primary';
    commentsLink.href = rootPath + '/u/' + encodeURIComponent(user.login) + '?platform=twitch';
    commentsLink.textContent = '▶ コメント一覧';
    links.appendChild(commentsLink);

    var statsLink = document.createElement('a');
    statsLink.className = 'user-card-link user-card-link-secondary';
    statsLink.href = rootPath + '/u/' + encodeURIComponent(user.login) + '/stats?platform=twitch';
    statsLink.textContent = '📊 統計';
    links.appendChild(statsLink);

    var quizLink = document.createElement('a');
    quizLink.className = 'user-card-link user-card-link-secondary';
    quizLink.href = rootPath + '/u/' + encodeURIComponent(user.login) + '/quiz?platform=twitch';
    quizLink.textContent = '🎲 クイズ';
    links.appendChild(quizLink);

    card.appendChild(links);

    return card;
  }

  function matchesQuery(user, query) {
    if (!query) { return true; }
    var q = query.toLowerCase();
    var login = (user.login || '').toLowerCase();
    var display = (user.display_name || '').toLowerCase();
    return login.indexOf(q) !== -1 || display.indexOf(q) !== -1;
  }

  function sortUsers(users, sort) {
    var copy = users.slice();
    if (sort === 'count_desc') {
      copy.sort(function (a, b) { return (b.comment_count || 0) - (a.comment_count || 0); });
    } else if (sort === 'count_asc') {
      copy.sort(function (a, b) { return (a.comment_count || 0) - (b.comment_count || 0); });
    } else if (sort === 'recent') {
      copy.sort(function (a, b) {
        var ta = a.last_comment_at ? new Date(a.last_comment_at).getTime() : 0;
        var tb = b.last_comment_at ? new Date(b.last_comment_at).getTime() : 0;
        return tb - ta;
      });
    } else {
      copy.sort(function (a, b) { return (a.login || '').localeCompare(b.login || ''); });
    }
    return copy;
  }

  function render() {
    var filtered = allUsers.filter(function (u) {
      if (activeLogins !== null && !activeLogins.has(u.login)) { return false; }
      return matchesQuery(u, currentQuery);
    });

    var sorted = sortUsers(filtered, currentSort);

    usersGrid.innerHTML = '';

    if (sorted.length === 0) {
      showStatus('該当するユーザが見つかりませんでした。');
    } else {
      hideStatus();
      var frag = document.createDocumentFragment();
      sorted.forEach(function (u) { frag.appendChild(buildCard(u)); });
      usersGrid.appendChild(frag);
    }

    usersCount.textContent = sorted.length + ' 人';
  }

  function loadStreamerFilter(streamerLogin) {
    if (!streamerLogin) {
      activeLogins = null;
      render();
      return;
    }
    showStatus('読み込み中...');
    fetch(rootPath + '/api/users/commenters?streamer=' + encodeURIComponent(streamerLogin))
      .then(function (res) { return res.json(); })
      .then(function (data) {
        activeLogins = new Set(data.logins || []);
        render();
      })
      .catch(function () {
        activeLogins = null;
        render();
      });
  }

  function loadUsers() {
    showStatus('ユーザ一覧を読み込み中...');
    fetch(rootPath + '/api/users/index')
      .then(function (res) { return res.json(); })
      .then(function (data) {
        allUsers = data.users || [];
        render();
      })
      .catch(function () {
        showStatus('ユーザ一覧の読み込みに失敗しました。ページを再読み込みしてください。');
      });
  }

  // Event listeners
  if (searchInput) {
    searchInput.addEventListener('input', function () {
      currentQuery = searchInput.value;
      searchClear.style.display = currentQuery ? 'flex' : 'none';
      render();
    });
  }

  if (searchClear) {
    searchClear.addEventListener('click', function () {
      searchInput.value = '';
      currentQuery = '';
      searchClear.style.display = 'none';
      searchInput.focus();
      render();
    });
  }

  if (streamerFilter) {
    streamerFilter.addEventListener('change', function () {
      loadStreamerFilter(streamerFilter.value);
    });
  }

  if (sortSelect) {
    sortSelect.addEventListener('change', function () {
      currentSort = sortSelect.value;
      render();
    });
  }

  loadUsers();
}());
