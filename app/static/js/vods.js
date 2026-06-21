(function () {
  const searchInput = document.getElementById('vods-search');
  const searchClear = document.getElementById('vods-search-clear');
  const streamerFilter = document.getElementById('streamer-filter');
  const sortSelect = document.getElementById('sort-select');
  const vodsGrid = document.getElementById('vods-grid');
  const vodsCount = document.getElementById('vods-count');
  const vodsStatus = document.getElementById('vods-status');
  const vodsPagination = document.getElementById('vods-pagination');
  const vodsLoadMore = document.getElementById('vods-load-more');

  if (!vodsGrid) { return; }

  const rawRootPath = JSON.parse(document.getElementById('root-path-data').textContent);
  const rootPath = (typeof rawRootPath === 'string' && rawRootPath && rawRootPath !== '/') ? rawRootPath.replace(/\/+$/, '') : '';

  const PAGE_SIZE = 40;
  let currentPage = 1;
  let currentTotal = 0;
  let currentPages = 0;
  let currentQuery = '';
  let currentSort = 'created_at';
  let currentStreamer = new URLSearchParams(window.location.search).get('owner_login') || '';
  let searchTimer = null;
  // 多重実行ガードと、フィルタ変更で古いレスポンスを破棄するための世代トークン
  let isLoading = false;
  let requestSeq = 0;

  // URL パラメータで配信者が指定されていれば select を初期化
  if (currentStreamer && streamerFilter) {
    streamerFilter.value = currentStreamer;
  }

  /**
   * ステータス表示領域にメッセージを表示する。
   * @param msg - 表示するメッセージ文字列
   */
  function showStatus(msg) {
    vodsStatus.textContent = msg;
    vodsStatus.hidden = false;
  }

  /**
   * ステータス表示領域を非表示にする。
   */
  function hideStatus() {
    vodsStatus.hidden = true;
  }

  /**
   * ISO日時文字列を日本語の短い日付文字列に変換する。
   * @param isoStr - ISO形式の日時文字列
   * @returns フォーマットされた日付文字列。変換に失敗した場合はnull
   */
  function formatDate(isoStr) {
    if (!isoStr) { return null; }
    try {
      // MySQL datetime "2026-03-18 12:00:00" → ISO "2026-03-18T12:00:00Z"
      let normalized = isoStr.replace(' ', 'T');
      if (normalized.indexOf('T') !== -1 && normalized.indexOf('+') === -1 && normalized.slice(-1) !== 'Z') {
        normalized += 'Z';
      }
      const d = new Date(normalized);
      if (isNaN(d.getTime())) { return null; }
      return d.toLocaleDateString('ja-JP', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'Asia/Tokyo' });
    } catch (e) {
      return null;
    }
  }

  /**
   * 秒数を「Xh Ym」または「Xm Ys」形式の文字列に変換する。
   * @param seconds - フォーマットする秒数
   * @returns フォーマットされた時間文字列。秒数がない場合はnull
   */
  function formatDuration(seconds) {
    if (!seconds) { return null; }
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) {
      return `${h}h ${m}m`;
    }
    return `${m}m ${s}s`;
  }

  /**
   * VOD情報からVODカードDOM要素を生成して返す。
   * @param vod - カードを生成するVODオブジェクト
   * @returns 生成したVODカードdiv要素
   */
  function buildCard(vod) {
    const card = document.createElement('div');
    card.className = 'vod-card';
    card.setAttribute('role', 'listitem');

    const title = document.createElement('div');
    title.className = 'vod-card-title';
    title.textContent = vod.title || '（タイトルなし）';
    card.appendChild(title);

    const owner = document.createElement('div');
    owner.className = 'vod-card-owner';
    owner.textContent = vod.owner_display_name || vod.owner_login;
    card.appendChild(owner);

    const meta = document.createElement('div');
    meta.className = 'vod-card-meta';

    const dateStr = vod.created_at_jst || formatDate(vod.created_at_utc);
    if (dateStr) {
      const dateSpan = document.createElement('span');
      dateSpan.textContent = dateStr;
      meta.appendChild(dateSpan);
    }

    const dur = formatDuration(vod.length_seconds);
    if (dur) {
      const durSpan = document.createElement('span');
      durSpan.innerHTML = `<i class="fa-regular fa-clock"></i> ${dur}`;
      meta.appendChild(durSpan);
    }

    if (vod.game_name) {
      const gameSpan = document.createElement('span');
      gameSpan.innerHTML = '<i class="fa-solid fa-gamepad"></i> ';
      gameSpan.append(vod.game_name);
      meta.appendChild(gameSpan);
    }

    card.appendChild(meta);

    const badges = document.createElement('div');
    badges.className = 'vod-card-badges';

    if (vod.comment_count > 0) {
      const badge = document.createElement('span');
      badge.className = 'vod-card-badge';
      badge.textContent = `${vod.comment_count.toLocaleString('ja-JP')} comments`;
      badges.appendChild(badge);
    }

    card.appendChild(badges);

    const link = document.createElement('a');
    link.className = 'vod-card-link';
    link.href = `${rootPath}/vods/${vod.vod_id}`;
    link.innerHTML = '<i class="fa-solid fa-play"></i> コメントを見る';
    card.appendChild(link);

    return card;
  }

  /**
   * VOD配列からカードを生成してグリッドに追加する。
   * @param vods - グリッドに追加するVODオブジェクトの配列
   */
  function appendCards(vods) {
    const frag = document.createDocumentFragment();
    vods.forEach(function (v) { frag.appendChild(buildCard(v)); });
    vodsGrid.appendChild(frag);
  }

  /**
   * APIからVOD一覧を取得してグリッドに描画する。
   * @param reset - trueの場合は現在のグリッドをクリアして1ページ目から読み込む
   */
  function loadVods(reset) {
    // reset（検索・フィルタ・並び順の変更）は常に最新条件を反映させるため通す。
    // 追記ロード（reset=false）だけは多重実行を防ぐ。
    if (!reset && isLoading) { return; }

    const pageToLoad = reset ? 1 : currentPage + 1;
    // 世代トークンを進め、これ以降に解決した古いリクエストの結果は破棄する
    const seq = ++requestSeq;
    isLoading = true;
    if (vodsLoadMore) { vodsLoadMore.disabled = true; }

    if (reset) {
      vodsGrid.innerHTML = '';
    }

    showStatus('読み込み中...');

    const params = new URLSearchParams({
      page: pageToLoad,
      page_size: PAGE_SIZE,
      sort: currentSort,
    });
    if (currentQuery) { params.set('q', currentQuery); }
    if (currentStreamer) { params.set('owner_login', currentStreamer); }

    fetch(`${rootPath}/api/vods?${params.toString()}`)
      .then(function (res) { return res.json(); })
      .then(function (data) {
        // フィルタ変更などで世代が進んでいたら、このレスポンスは古いので破棄する
        if (seq !== requestSeq) { return; }
        const items = data.items || [];
        currentTotal = data.total || 0;
        currentPages = data.pages || 0;
        // ページ番号は成功時にのみ進める（失敗時にページが飛ぶのを防ぐ）
        currentPage = pageToLoad;

        appendCards(items);
        hideStatus();

        vodsCount.textContent = `${currentTotal.toLocaleString('ja-JP')} 件`;

        vodsPagination.hidden = currentPage >= currentPages;

        if (items.length === 0 && currentPage === 1) {
          showStatus('VOD が見つかりませんでした。');
        }
      })
      .catch(function () {
        if (seq !== requestSeq) { return; }
        showStatus('読み込みに失敗しました。ページを再読み込みしてください。');
      })
      .finally(function () {
        // 最新世代のリクエストだけがロード状態とボタンの活性を制御する
        if (seq === requestSeq) {
          isLoading = false;
          if (vodsLoadMore) { vodsLoadMore.disabled = false; }
        }
      });
  }

  /**
   * 入力から一定時間後にVOD一覧を再読み込みするデバウンス検索をスケジュールする。
   */
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
      loadVods(false);
    });
  }

  loadVods(true);
}());
