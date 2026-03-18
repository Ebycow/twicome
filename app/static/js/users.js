(function () {
  const searchInput = document.getElementById('users-search');
  const searchClear = document.getElementById('users-search-clear');
  const streamerFilter = document.getElementById('streamer-filter');
  const sortSelect = document.getElementById('sort-select');
  const usersGrid = document.getElementById('users-grid');
  const usersCount = document.getElementById('users-count');
  const usersStatus = document.getElementById('users-status');

  if (!usersGrid) { return; }

  const rawRootPath = JSON.parse(document.getElementById('root-path-data').textContent);
  const rootPath = (typeof rawRootPath === 'string' && rawRootPath && rawRootPath !== '/') ? rawRootPath.replace(/\/+$/, '') : '';

  let allUsers = [];
  let activeLogins = null; // null = no streamer filter, Set = filtered logins
  let currentQuery = '';
  let currentSort = 'login';

  /**
   * ステータス表示領域にメッセージを表示する。
   * @param msg - 表示するメッセージ文字列
   */
  function showStatus(msg) {
    usersStatus.textContent = msg;
    usersStatus.hidden = false;
  }

  /**
   * ステータス表示領域を非表示にする。
   */
  function hideStatus() {
    usersStatus.hidden = true;
  }

  /**
   * コメント数を日本語ロケールでフォーマットした文字列を返す。
   * @param n - フォーマットするコメント数
   * @returns フォーマットされたコメント数文字列
   */
  function formatCount(n) {
    if (!n) { return '0 comments'; }
    return `${n.toLocaleString('ja-JP')} comments`;
  }

  /**
   * ISO日時文字列を日本語の短い日付文字列に変換する。
   * @param iso - ISO形式の日時文字列
   * @returns フォーマットされた日付文字列。変換に失敗した場合はnull
   */
  function formatDate(iso) {
    if (!iso) { return null; }
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('ja-JP', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) {
      return null;
    }
  }

  /**
   * ユーザのアバター要素を生成して返す。
   * @param user - アバターを生成するユーザオブジェクト
   * @returns アバターを含むspan要素
   */
  function buildAvatar(user) {
    if (user.profile_image_url) {
      const img = document.createElement('img');
      img.src = user.profile_image_url;
      img.alt = user.display_name || user.login;
      img.width = 40;
      img.height = 40;
      const wrap = document.createElement('span');
      wrap.className = 'user-card-avatar';
      wrap.appendChild(img);
      return wrap;
    }
    const fallback = document.createElement('span');
    fallback.className = 'user-card-avatar';
    const label = (user.display_name || user.login || '?').charAt(0).toUpperCase();
    fallback.textContent = label;
    return fallback;
  }

  /**
   * ユーザ情報からユーザカードDOM要素を生成して返す。
   * @param user - カードを生成するユーザオブジェクト
   * @returns 生成したユーザカードdiv要素
   */
  function buildCard(user) {
    const card = document.createElement('div');
    card.className = 'user-card';
    card.setAttribute('role', 'listitem');

    // Header
    const header = document.createElement('div');
    header.className = 'user-card-header';

    const avatar = buildAvatar(user);
    header.appendChild(avatar);

    const info = document.createElement('div');
    info.className = 'user-card-info';

    const name = document.createElement('div');
    name.className = 'user-card-name';
    name.textContent = user.display_name || user.login;
    info.appendChild(name);

    if (user.display_name && user.display_name !== user.login) {
      const loginEl = document.createElement('div');
      loginEl.className = 'user-card-login';
      loginEl.textContent = user.login;
      info.appendChild(loginEl);
    }

    header.appendChild(info);

    if (user.comment_count > 0) {
      const countEl = document.createElement('span');
      countEl.className = 'user-card-count';
      countEl.textContent = formatCount(user.comment_count);
      header.appendChild(countEl);
    }

    card.appendChild(header);

    if (user.last_comment_at) {
      const meta = document.createElement('div');
      meta.className = 'user-card-meta';
      const dateStr = formatDate(user.last_comment_at);
      if (dateStr) {
        meta.textContent = `最終コメント: ${dateStr}`;
        card.appendChild(meta);
      }
    }

    // Links
    const links = document.createElement('div');
    links.className = 'user-card-links';

    const commentsLink = document.createElement('a');
    commentsLink.className = 'user-card-link user-card-link-primary';
    commentsLink.href = `${rootPath}/u/${encodeURIComponent(user.login)}?platform=twitch`;
    commentsLink.innerHTML = '<i class="fa-solid fa-play"></i> コメント一覧';
    links.appendChild(commentsLink);

    const statsLink = document.createElement('a');
    statsLink.className = 'user-card-link user-card-link-secondary';
    statsLink.href = `${rootPath}/u/${encodeURIComponent(user.login)}/stats?platform=twitch`;
    statsLink.innerHTML = '<i class="fa-solid fa-chart-bar"></i> 統計';
    links.appendChild(statsLink);

    const quizLink = document.createElement('a');
    quizLink.className = 'user-card-link user-card-link-secondary';
    quizLink.href = `${rootPath}/u/${encodeURIComponent(user.login)}/quiz?platform=twitch`;
    quizLink.innerHTML = '<i class="fa-solid fa-dice"></i> クイズ';
    links.appendChild(quizLink);

    card.appendChild(links);

    return card;
  }

  /**
   * ユーザがクエリ文字列に一致するか判定する。
   * @param user - 判定対象のユーザオブジェクト
   * @param query - 検索クエリ文字列
   * @returns クエリに一致する場合はtrue
   */
  function matchesQuery(user, query) {
    if (!query) { return true; }
    const q = query.toLowerCase();
    const login = (user.login || '').toLowerCase();
    const display = (user.display_name || '').toLowerCase();
    return login.indexOf(q) !== -1 || display.indexOf(q) !== -1;
  }

  /**
   * 指定されたソート条件でユーザ配列を並び替えた新しい配列を返す。
   * @param users - 並び替え対象のユーザ配列
   * @param sort - ソートキー文字列
   * @returns ソートされた新しいユーザ配列
   */
  function sortUsers(users, sort) {
    const copy = users.slice();
    if (sort === 'count_desc') {
      copy.sort(function (a, b) { return (b.comment_count || 0) - (a.comment_count || 0); });
    } else if (sort === 'count_asc') {
      copy.sort(function (a, b) { return (a.comment_count || 0) - (b.comment_count || 0); });
    } else if (sort === 'recent') {
      copy.sort(function (a, b) {
        const ta = a.last_comment_at ? new Date(a.last_comment_at).getTime() : 0;
        const tb = b.last_comment_at ? new Date(b.last_comment_at).getTime() : 0;
        return tb - ta;
      });
    } else {
      copy.sort(function (a, b) { return (a.login || '').localeCompare(b.login || ''); });
    }
    return copy;
  }

  /**
   * フィルタとソートを適用してユーザグリッドを再描画する。
   */
  function render() {
    const filtered = allUsers.filter(function (u) {
      if (activeLogins !== null && !activeLogins.has(u.login)) { return false; }
      return matchesQuery(u, currentQuery);
    });

    const sorted = sortUsers(filtered, currentSort);

    usersGrid.innerHTML = '';

    if (sorted.length === 0) {
      showStatus('該当するユーザが見つかりませんでした。');
    } else {
      hideStatus();
      const frag = document.createDocumentFragment();
      sorted.forEach(function (u) { frag.appendChild(buildCard(u)); });
      usersGrid.appendChild(frag);
    }

    usersCount.textContent = `${sorted.length} 人`;
  }

  /**
   * 配信者ログインに基づいてコメントしたユーザをAPIから取得してフィルタを設定する。
   * @param streamerLogin - フィルタに使う配信者のログイン名
   */
  function loadStreamerFilter(streamerLogin) {
    if (!streamerLogin) {
      activeLogins = null;
      render();
      return;
    }
    showStatus('読み込み中...');
    fetch(`${rootPath}/api/users/commenters?streamer=${encodeURIComponent(streamerLogin)}`)
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

  /**
   * APIからユーザ一覧を取得してグリッドに描画する。
   */
  function loadUsers() {
    showStatus('ユーザ一覧を読み込み中...');
    fetch(`${rootPath}/api/users/index`)
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
