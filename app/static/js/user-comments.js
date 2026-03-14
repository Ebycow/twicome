(function () {
  var filters = JSON.parse(document.getElementById('filters-data').textContent);
  var rawRootPath = JSON.parse(document.getElementById('root-path-data').textContent);
  var normalizedRootPath = (typeof rawRootPath === 'string') ? rawRootPath.trim() : '';
  var rootPath = (normalizedRootPath && normalizedRootPath !== '/') ? normalizedRootPath.replace(/\/+$/, '') : '';
  var voteCountsApiUrl = rootPath + '/api/comments/votes';
  var initialPage = JSON.parse(document.getElementById('page-data').textContent);
  var totalPages = JSON.parse(document.getElementById('pages-data').textContent);
  var userLogin = JSON.parse(document.getElementById('user-data').textContent);
  var currentDataVersion = JSON.parse(document.getElementById('data-version-data').textContent);

  // markVisited
  if (window.TwicomeOfflineAccess) {
    window.TwicomeOfflineAccess.markVisited(rootPath, 'comments', userLogin);
  }

  // SW registration (overrides base.html sw_script block)
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register(rootPath + '/sw.js', { scope: rootPath + '/' }).catch(function () {});
    });
    navigator.serviceWorker.addEventListener('message', function (event) {
      if (event.data && event.data.type === 'twicome-auth-redirect') {
        window.location.reload();
      }
    });
  }

  var currentMinPage = initialPage;
  var currentMaxPage = initialPage;
  var loadedPages = new Set([initialPage]);
  var isLoading = false;
  var isBest9Mode = false;
  var best9List = [];
  var best9Selected = new Set();
  var best9Data = new Map();

  (function () {
    try {
      var stored = localStorage.getItem('best9_' + userLogin);
      if (stored) {
        best9List = JSON.parse(stored);
        best9List.forEach(function (id) { best9Selected.add(id); });
      }
      isBest9Mode = localStorage.getItem('best9_mode_' + userLogin) === '1';
    } catch (e) {}
  })();

  var listElement = document.querySelector('.list');
  var isCursorMode = !!filters.cursor;

  // FAISS mode flags (declared at top so scroll observer can reference them)
  var isSimilarMode = false;
  var isSpecialMode = false;

  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function renderBody(comment) {
    if (comment && comment.body_html) return comment.body_html;
    return escapeHtml(comment.body);
  }

  function renderCommunityNote(comment) {
    if (!comment.community_note_body) return '';
    var html = '<div class="community-note"><div>';
    if (comment.cn_harm_risk != null) {
      var danger = Math.round((comment.cn_harm_risk + comment.cn_exaggeration + comment.cn_evidence_gap + (comment.cn_subjectivity || 0)) / 4);
      var badgeStyle;
      if (danger >= 60) badgeStyle = 'background:rgba(244,67,54,0.2);color:#d32f2f;border:1px solid #d32f2f';
      else if (danger >= 30) badgeStyle = 'background:rgba(255,152,0,0.2);color:#e65100;border:1px solid #e65100';
      else badgeStyle = 'background:rgba(76,175,80,0.2);color:#2e7d32;border:1px solid #2e7d32';
      html += '<span class="cn-danger-badge" style="' + badgeStyle + '">危険度 ' + danger + '</span>';
    }
    if (comment.cn_status) {
      var statusJa = {supported: '裏付けあり', insufficient: '情報不足', inconsistent: '矛盾あり', not_applicable: '該当なし'};
      html += '<span class="cn-status-badge">' + escapeHtml(statusJa[comment.cn_status] || comment.cn_status) + '</span>';
    }
    html += ' &#x1f4dd; ' + escapeHtml(comment.community_note_body) + '</div>';
    if (comment.cn_harm_risk != null) {
      html += '<div class="cn-scores">';
      var scores = [
        {label:'検証可能性', val:comment.cn_verifiability, color:'#2196f3'},
        {label:'被害可能性', val:comment.cn_harm_risk, color:'#f44336'},
        {label:'誇張度', val:comment.cn_exaggeration, color:'#ff9800'},
        {label:'根拠不足', val:comment.cn_evidence_gap, color:'#9c27b0'},
        {label:'主観度', val:comment.cn_subjectivity, color:'#607d8b'},
      ];
      scores.forEach(function (s) {
        html += '<div class="cn-score-item"><span>' + s.label + '</span><div class="cn-score-bar"><div class="cn-score-fill" style="width:' + s.val + '%;background:' + s.color + ';"></div></div><span>' + s.val + '</span></div>';
      });
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function createCommentElement(comment, options) {
    options = options || {};
    var badge = typeof options.badge === 'function' ? options.badge(comment) : (options.badge || '');
    var link = document.createElement('a');
    link.href = '?cursor=' + comment.comment_id;
    link.style.textDecoration = 'none';
    link.style.color = 'inherit';
    link.style.display = 'block';
    link.addEventListener('click', function (e) {
      if (e.target.closest('button')) { e.preventDefault(); return; }
    });
    var commentDiv = document.createElement('div');
    if (options.cursorMode) {
      if (comment.comment_id === filters.cursor) commentDiv.className = 'comment highlighted';
      else if (comment.commenter_login_snapshot === userLogin) commentDiv.className = 'comment grayed';
      else commentDiv.className = 'comment';
    } else {
      commentDiv.className = 'comment';
    }
    commentDiv.id = comment.comment_id;
    commentDiv.innerHTML =
      '<div class="comment-head">' +
      '<div>' +
      badge +
      '<a href="' + escapeHtml(comment.vod_jump_link) + '" target="_blank" class="pill">VOD ' + escapeHtml(String(comment.vod_id)) + '</a>' +
      (comment.youtube_jump_link ? '<a href="' + escapeHtml(comment.youtube_jump_link) + '" target="_blank" class="pill">YouTube</a>' : '') +
      '<strong>' + escapeHtml(comment.vod_title) + '</strong>' +
      (options.showOwner ? '<span class="meta">· 配信者: ' + escapeHtml(comment.owner_login) + (comment.owner_display_name ? '（' + escapeHtml(comment.owner_display_name) + '）' : '') + '</span>' : '') +
      '<span class="meta">· ' + escapeHtml(comment.commenter_login_snapshot) + (comment.commenter_display_name_snapshot ? '（' + escapeHtml(comment.commenter_display_name_snapshot) + '）' : '') + 'の書き込み</span>' +
      '<span class="meta">· ' + escapeHtml(comment.offset_hms) + '</span>' +
      (comment.comment_created_at_jst ? '<span class="meta">· ' + escapeHtml(comment.comment_created_at_jst) + ' JST</span>' : '') +
      (options.showRelativeTime && comment.relative_time ? '<span class="meta ' + (comment.is_recent ? 'recent' : '') + '">· ' + escapeHtml(comment.relative_time) + '</span>' : '') +
      (options.showBits && comment.bits_spent ? '<span class="pill">bits ' + escapeHtml(comment.bits_spent) + '</span>' : '') +
      '</div>' +
      '<div class="meta">' + renderVoteButtonsMarkup(comment.comment_id, comment.twicome_likes_count, comment.twicome_dislikes_count) + '</div>' +
      '</div>' +
      '<div class="body">' + renderBody(comment) + '</div>' +
      renderCommunityNote(comment);
    link.appendChild(commentDiv);
    return { link: link, commentDiv: commentDiv };
  }

  function updateURL(page, cursor) {
    var url = new URL(window.location);
    if (cursor) {
      url.searchParams.set('cursor', cursor);
      url.searchParams.delete('page');
    } else {
      url.searchParams.set('page', page);
      url.searchParams.delete('cursor');
    }
    window.history.pushState({}, '', url);
  }

  function updatePrevButton() {
    var btn = document.getElementById('load-prev');
    if (!btn) return;
    if (isCursorMode || currentMinPage <= 1) {
      btn.style.display = 'none';
    } else {
      btn.style.display = 'block';
    }
  }

  function renderVoteButtonsMarkup(commentId, likesCount, dislikesCount) {
    var safeCommentId = escapeHtml(commentId);
    var safeLikes = escapeHtml(likesCount);
    var safeDislikes = escapeHtml(dislikesCount);
    return '<button onclick="vote(this, \'' + safeCommentId + '\', \'like\')" class="vote-btn" data-count="' + safeLikes + '">😂 ' + safeLikes + '</button>' +
           '<button onclick="vote(this, \'' + safeCommentId + '\', \'dislike\')" class="vote-btn" data-count="' + safeDislikes + '">❓ ' + safeDislikes + '</button>';
  }

  function setVoteControls(container, commentId, likesCount, dislikesCount) {
    if (!container) return;
    container.innerHTML = renderVoteButtonsMarkup(commentId, likesCount, dislikesCount);
  }

  async function hydrateDeferredVoteControls(containers) {
    var targets = (containers || []).filter(function (container) { return container && container.dataset.commentId; });
    if (!targets.length) return;
    var items = {};
    try {
      var response = await fetch(voteCountsApiUrl, {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment_ids: targets.map(function (c) { return c.dataset.commentId; }) }),
      });
      if (!response.ok) throw new Error('vote_counts_failed:' + response.status);
      var data = await response.json();
      items = (data && data.items) || {};
    } catch (error) {
      console.warn('Deferred vote hydration failed, keeping initial counts:', error);
      return;
    }
    targets.forEach(function (container) {
      var commentId = container.dataset.commentId;
      var currentButtons = container.querySelectorAll('.vote-btn');
      var currentLikes = Number(currentButtons[0] && currentButtons[0].dataset.count || 0);
      var currentDislikes = Number(currentButtons[1] && currentButtons[1].dataset.count || 0);
      var item = items[commentId] || {};
      setVoteControls(container, commentId,
        Number(item.twicome_likes_count != null ? item.twicome_likes_count : currentLikes),
        Number(item.twicome_dislikes_count != null ? item.twicome_dislikes_count : currentDislikes)
      );
    });
  }

  function scheduleDeferredVoteHydration() {
    var containers = Array.from(document.querySelectorAll('[data-vote-controls="deferred"]'));
    if (!containers.length) return;
    var run = function () { void hydrateDeferredVoteControls(containers); };
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(run, { timeout: 1800 });
      return;
    }
    window.setTimeout(run, 350);
  }

  async function loadComments(page, direction, reset) {
    direction = direction || 'append';
    reset = reset || false;
    if (isLoading) return;
    if (!reset && (loadedPages.has(page) || page < 1 || page > totalPages)) return;
    isLoading = true;

    if (reset) {
      listElement.innerHTML = '';
      loadedPages.clear();
      currentMinPage = page;
      currentMaxPage = page;
      loadedPages.add(page);
      updateURL(page, filters.cursor);
    }

    var params = new URLSearchParams({
      platform: filters.platform,
      page: page,
      page_size: filters.page_size,
      sort: filters.sort,
    });
    if (filters.cursor) params.set('cursor', filters.cursor);
    if (filters.vod_id) params.set('vod_id', filters.vod_id);
    if (filters.owner_user_id) params.set('owner_user_id', filters.owner_user_id);
    if (filters.q) params.set('q', filters.q);
    if (filters.exclude_q) params.set('exclude_q', filters.exclude_q);

    try {
      var response = await fetch(rootPath + '/api/u/' + userLogin + '?' + params);
      if (!response.ok) throw new Error('Failed to load comments');
      var data = await response.json();

      if (reset) totalPages = Math.ceil(data.total / filters.page_size);
      if (!reset) loadedPages.add(page);

      var itemsToRender = direction === 'prepend' ? data.items.slice().reverse() : data.items;
      itemsToRender.forEach(function (comment) {
        var el = createCommentElement(comment, {
          cursorMode: isCursorMode,
          showOwner: true,
          showRelativeTime: true,
          showBits: true,
        });
        if (direction === 'prepend') {
          listElement.insertBefore(el.link, listElement.firstChild);
        } else {
          listElement.appendChild(el.link);
        }
        if (isBest9Mode) addBest9Button(el.commentDiv);
      });

      if (direction === 'prepend') currentMinPage = Math.min(currentMinPage, page);
      else currentMaxPage = Math.max(currentMaxPage, page);

      updatePrevButton();
      if (!reset) updateURL(page, filters.cursor);
    } catch (error) {
      console.error('Error loading comments:', error);
    } finally {
      isLoading = false;
    }
  }

  var sentinel = document.getElementById('scroll-sentinel');
  var scrollObserver = new IntersectionObserver(function (entries) {
    if (isCursorMode || isSimilarMode || isSpecialMode) return;
    if (entries[0].isIntersecting && currentMaxPage < totalPages) {
      loadComments(currentMaxPage + 1, 'append');
    }
  }, { rootMargin: '0px 0px 600px 0px' });

  if (!isCursorMode) scrollObserver.observe(sentinel);

  var loadPrevBtn = document.getElementById('load-prev-btn');
  if (loadPrevBtn) {
    loadPrevBtn.addEventListener('click', function () {
      if (isCursorMode) return;
      loadComments(currentMinPage - 1, 'prepend');
    });
  }

  updatePrevButton();
  if (document.readyState === 'complete') {
    scheduleDeferredVoteHydration();
  } else {
    window.addEventListener('load', scheduleDeferredVoteHydration, { once: true });
  }
  if (filters.cursor) {
    var element = document.getElementById(filters.cursor);
    if (element) {
      element.classList.add('highlighted');
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  function spawnConfetti(button) {
    var rect = button.getBoundingClientRect();
    var ox = rect.left + rect.width / 2;
    var oy = rect.top + rect.height / 2;
    var colors = ['#ff6b6b','#ffd93d','#6bcb77','#4d96ff','#ff6eb4','#a66cff'];
    var shapes = ['50%','2px'];
    for (var i = 0; i < 12; i++) {
      var el = document.createElement('div');
      el.className = 'confetti';
      var angle = (Math.PI * 2 * i) / 12 + (Math.random() - 0.5) * 0.5;
      var dist = 30 + Math.random() * 50;
      el.style.left = ox + 'px';
      el.style.top = oy + 'px';
      el.style.background = colors[Math.floor(Math.random() * colors.length)];
      el.style.borderRadius = shapes[Math.floor(Math.random() * shapes.length)];
      el.style.width = (5 + Math.random() * 5) + 'px';
      el.style.height = (5 + Math.random() * 5) + 'px';
      el.style.setProperty('--cx', Math.cos(angle) * dist + 'px');
      el.style.setProperty('--cy', Math.sin(angle) * dist - 20 + 'px');
      el.style.setProperty('--cr', (Math.random() * 720 - 360) + 'deg');
      document.body.appendChild(el);
      el.addEventListener('animationend', function () { this.remove(); });
    }
  }

  var votePending = new Map();
  var VOTE_DEBOUNCE_MS = 500;

  function vote(button, commentId, type) {
    spawnConfetti(button);
    var key = commentId + '-' + type;
    var currentCount = parseInt(button.dataset.count || '0', 10) + 1;
    button.dataset.count = currentCount;
    button.textContent = (type === 'like' ? '😂 ' : '❓️ ') + currentCount;
    if (votePending.has(key)) {
      var pending = votePending.get(key);
      pending.count++;
      clearTimeout(pending.timer);
      pending.timer = setTimeout(function () { flushVote(key); }, VOTE_DEBOUNCE_MS);
    } else {
      votePending.set(key, {
        count: 1, button: button, commentId: commentId, type: type,
        timer: setTimeout(function () { flushVote(key); }, VOTE_DEBOUNCE_MS)
      });
    }
  }

  async function flushVote(key) {
    var pending = votePending.get(key);
    if (!pending) return;
    votePending.delete(key);
    var url = rootPath + '/' + pending.type + '/' + pending.commentId + '?count=' + pending.count;
    try {
      var response = await fetch(url, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!response.ok) console.error('Vote failed:', await response.text());
    } catch (error) {
      console.error('Network error:', error);
    }
  }

  // vote must be global for onclick attributes in HTML
  window.vote = vote;

  // -----------------------
  // Best9モード
  // -----------------------
  var best9ToggleBtn = document.getElementById('best9-toggle-btn');
  var best9Bar = document.getElementById('best9-bar');

  function captureBest9Text(commentId, commentDiv) {
    if (best9Data.has(commentId)) return;
    var bodyEl = commentDiv ? commentDiv.querySelector('.body') : null;
    if (bodyEl) best9Data.set(commentId, (bodyEl.innerText || bodyEl.textContent || '').trim());
  }

  function addBest9Button(commentDiv) {
    if (commentDiv.querySelector('.best9-add-btn')) return;
    var commentId = commentDiv.id;
    if (!commentId) return;
    if (best9Selected.has(commentId)) captureBest9Text(commentId, commentDiv);
    var btn = document.createElement('button');
    var isSelected = best9Selected.has(commentId);
    btn.className = 'best9-add-btn' + (isSelected ? ' selected' : '');
    btn.textContent = isSelected ? '選択済み ✓' : '+ Best9';
    btn.type = 'button';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      toggleBest9(commentId, btn, commentDiv);
    });
    var metaDiv = commentDiv.querySelector('.comment-head > div.meta');
    if (metaDiv) metaDiv.appendChild(btn);
  }

  function saveBest9() {
    try { localStorage.setItem('best9_' + userLogin, JSON.stringify(best9List)); } catch (e) {}
  }

  function updateBest9ToggleLabel() {
    if (!best9ToggleBtn) return;
    var count = best9List.length;
    if (isBest9Mode) {
      best9ToggleBtn.textContent = count > 0 ? 'Best9: ON（' + count + '件）' : 'Best9: ON';
    } else {
      best9ToggleBtn.textContent = count > 0 ? 'Best9モード（' + count + '件保存中）' : 'Best9モード';
    }
  }

  function toggleBest9(commentId, btn, commentDiv) {
    if (best9Selected.has(commentId)) {
      best9Selected.delete(commentId);
      best9List = best9List.filter(function (id) { return id !== commentId; });
      if (btn) { btn.className = 'best9-add-btn'; btn.textContent = '+ Best9'; }
      if (commentDiv) commentDiv.classList.remove('best9-selected');
    } else {
      if (best9List.length >= 9) { alert('9件まで選択できます'); return; }
      best9List.push(commentId);
      best9Selected.add(commentId);
      if (btn) { btn.className = 'best9-add-btn selected'; btn.textContent = '選択済み ✓'; }
      if (commentDiv) commentDiv.classList.add('best9-selected');
      captureBest9Text(commentId, commentDiv);
    }
    saveBest9();
    updateBest9Bar();
    updateBest9ToggleLabel();
    var previewArea = document.getElementById('best9-preview-area');
    if (previewArea && previewArea.style.display !== 'none') renderPreviewGrid();
  }

  async function compressIds(idArray) {
    if (!window.CompressionStream) return null;
    try {
      var encoded = new TextEncoder().encode(idArray.join(','));
      var cs = new CompressionStream('deflate-raw');
      var writer = cs.writable.getWriter();
      writer.write(encoded);
      writer.close();
      var chunks = [];
      var reader = cs.readable.getReader();
      while (true) {
        var result = await reader.read();
        if (result.done) break;
        chunks.push(result.value);
      }
      var totalLen = chunks.reduce(function (acc, c) { return acc + c.length; }, 0);
      var buf = new Uint8Array(totalLen);
      var offset = 0;
      for (var i = 0; i < chunks.length; i++) { buf.set(chunks[i], offset); offset += chunks[i].length; }
      var binary = String.fromCharCode.apply(null, buf);
      return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    } catch (e) { return null; }
  }

  async function buildBest9Url() {
    var z = await compressIds(best9List);
    if (z) return location.origin + rootPath + '/best9?z=' + z + '&login=' + encodeURIComponent(userLogin);
    return location.origin + rootPath + '/best9?ids=' + encodeURIComponent(best9List.join(',')) + '&login=' + encodeURIComponent(userLogin);
  }

  async function updateBest9Bar() {
    document.getElementById('best9-count').textContent = best9List.length + '/9';
    var urlBox = document.getElementById('best9-url-box');
    if (best9List.length > 0) {
      var url = await buildBest9Url();
      document.getElementById('best9-url-input').value = url;
      document.getElementById('best9-go-btn').onclick = function () { window.open(url, '_blank'); };
      urlBox.style.display = 'flex';
    } else {
      urlBox.style.display = 'none';
    }
  }

  function applyBest9ModeUI() {
    if (!best9ToggleBtn) return;
    best9ToggleBtn.style.borderColor = isBest9Mode ? '#4caf50' : '';
    best9ToggleBtn.style.color = isBest9Mode ? '#4caf50' : '';
    best9Bar.style.display = isBest9Mode ? 'flex' : 'none';
    if (isBest9Mode) {
      updateBest9Bar();
      document.querySelectorAll('.comment').forEach(function (div) { addBest9Button(div); });
    } else {
      document.querySelectorAll('.best9-add-btn').forEach(function (btn) { btn.remove(); });
      document.querySelectorAll('.best9-selected').forEach(function (div) { div.classList.remove('best9-selected'); });
    }
  }

  updateBest9ToggleLabel();
  applyBest9ModeUI();

  if (best9ToggleBtn) {
    best9ToggleBtn.addEventListener('click', function () {
      isBest9Mode = !isBest9Mode;
      try { localStorage.setItem('best9_mode_' + userLogin, isBest9Mode ? '1' : '0'); } catch (e) {}
      applyBest9ModeUI();
      updateBest9ToggleLabel();
    });

    document.getElementById('best9-copy-btn').addEventListener('click', function () {
      var input = document.getElementById('best9-url-input');
      navigator.clipboard.writeText(input.value).then(function () {
        var btn = document.getElementById('best9-copy-btn');
        btn.textContent = 'コピーしました！';
        setTimeout(function () { btn.textContent = 'URLをコピー'; }, 2000);
      });
    });

    document.getElementById('best9-clear-btn').addEventListener('click', function () {
      best9Selected.clear();
      best9List = [];
      best9Data.clear();
      saveBest9();
      document.querySelectorAll('.best9-add-btn').forEach(function (btn) {
        btn.className = 'best9-add-btn';
        btn.textContent = '+ Best9';
      });
      document.querySelectorAll('.best9-selected').forEach(function (div) { div.classList.remove('best9-selected'); });
      var previewArea = document.getElementById('best9-preview-area');
      if (previewArea && previewArea.style.display !== 'none') renderPreviewGrid();
      updateBest9Bar();
      updateBest9ToggleLabel();
    });

    var best9PreviewBtn = document.getElementById('best9-preview-btn');
    if (best9PreviewBtn) {
      best9PreviewBtn.addEventListener('click', function () {
        var area = document.getElementById('best9-preview-area');
        var isVisible = area.style.display !== 'none';
        area.style.display = isVisible ? 'none' : 'block';
        best9PreviewBtn.textContent = isVisible ? '▲ プレビュー' : '▼ プレビュー';
        if (!isVisible) renderPreviewGrid();
      });
    }
  }

  var dragSrcIndex = null;

  function renderPreviewGrid() {
    var grid = document.getElementById('best9-preview-grid');
    if (!grid) return;
    grid.innerHTML = '';
    for (var i = 0; i < 9; i++) {
      var slot = document.createElement('div');
      var id = best9List[i];
      if (id) {
        slot.className = 'best9-slot filled';
        slot.draggable = true;
        slot.dataset.index = i;
        var text = best9Data.get(id) || '';
        var snippet = text.length > 80 ? text.substring(0, 80) + '…' : text;
        slot.innerHTML =
          '<div class="best9-slot-num">No.' + (i + 1) + '</div>' +
          '<div class="best9-slot-text">' + escapeHtml(snippet) + '</div>' +
          '<button type="button" class="best9-slot-remove" title="選択解除">×</button>';
        slot.addEventListener('dragstart', onSlotDragStart);
        slot.addEventListener('dragover', onSlotDragOver);
        slot.addEventListener('dragleave', onSlotDragLeave);
        slot.addEventListener('drop', onSlotDrop);
        slot.addEventListener('dragend', onSlotDragEnd);
        (function (slotId) {
          slot.querySelector('.best9-slot-remove').addEventListener('click', function (e) {
            e.stopPropagation();
            var commentDiv = document.getElementById(slotId);
            var addBtn = commentDiv ? commentDiv.querySelector('.best9-add-btn') : null;
            toggleBest9(slotId, addBtn, commentDiv);
          });
        })(id);
      } else {
        slot.className = 'best9-slot empty-slot';
        slot.innerHTML = '<div class="best9-slot-num">No.' + (i + 1) + '</div><div class="best9-slot-text">（未選択）</div>';
      }
      grid.appendChild(slot);
    }
  }

  function onSlotDragStart(e) {
    dragSrcIndex = parseInt(this.dataset.index);
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
  }

  function onSlotDragOver(e) {
    if (!this.classList.contains('filled')) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    this.classList.add('drag-over');
  }

  function onSlotDragLeave() { this.classList.remove('drag-over'); }

  function onSlotDrop(e) {
    e.preventDefault();
    this.classList.remove('drag-over');
    var destIndex = parseInt(this.dataset.index);
    if (dragSrcIndex === null || dragSrcIndex === destIndex) return;
    if (destIndex >= best9List.length) return;
    var moved = best9List.splice(dragSrcIndex, 1)[0];
    best9List.splice(destIndex, 0, moved);
    saveBest9();
    renderPreviewGrid();
    updateBest9Bar();
  }

  function onSlotDragEnd() {
    this.classList.remove('dragging');
    dragSrcIndex = null;
    document.querySelectorAll('.best9-slot').forEach(function (s) { s.classList.remove('drag-over'); });
  }

  // -----------------------
  // FAISS: 類似検索・典型度・感情スライダー
  // (DOM要素が存在する場合のみ有効)
  // -----------------------
  var similarBtn = document.getElementById('similar-search-btn');
  var similarInput = document.getElementById('similar-q');
  var similarTopK = document.getElementById('similar-top-k');
  var similarClear = document.getElementById('similar-clear');
  var similarClearBtn = document.getElementById('similar-clear-btn');
  var similarStatus = document.getElementById('similar-status');

  function renderSearchResults(items, badgeHtml) {
    listElement.innerHTML = '';
    if (items.length === 0) {
      listElement.innerHTML = '<div class="comment">該当するコメントが見つかりませんでした</div>';
      return;
    }
    items.forEach(function (comment) {
      var el = createCommentElement(comment, { badge: badgeHtml });
      listElement.appendChild(el.link);
      if (isBest9Mode) addBest9Button(el.commentDiv);
    });
  }

  function exitSpecialMode() {
    isSpecialMode = false;
    isSimilarMode = false;
    if (similarClear) similarClear.style.display = 'none';
    if (similarStatus) similarStatus.textContent = '';
    if (centroidClear) centroidClear.style.display = 'none';
    if (centroidStatus) centroidStatus.textContent = '';
    if (emotionClear) emotionClear.style.display = 'none';
    if (emotionStatus) emotionStatus.textContent = '';
    if (centroidDetails) centroidDetails.open = false;
    if (emotionDetails) emotionDetails.open = false;
    loadComments(initialPage, 'append', true);
  }

  if (similarBtn) {
    similarBtn.addEventListener('click', performSimilarSearch);
    similarInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); performSimilarSearch(); }
    });
    similarClearBtn.addEventListener('click', exitSpecialMode);
  }

  async function performSimilarSearch() {
    var query = similarInput.value.trim();
    if (!query) return;
    similarBtn.disabled = true;
    similarBtn.textContent = '検索中...';
    similarStatus.textContent = '検索中...';
    try {
      var params = new URLSearchParams({ q: query, platform: filters.platform, top_k: similarTopK.value });
      var response = await fetch(rootPath + '/api/u/' + userLogin + '/similar?' + params);
      if (!response.ok) {
        var err = await response.json();
        if (err.error === 'similar_search_not_available') {
          similarStatus.textContent = 'このユーザの類似検索インデックスはまだ作成されていません';
          return;
        }
        throw new Error('Search failed');
      }
      var data = await response.json();
      isSimilarMode = true;
      similarClear.style.display = 'block';
      if (data.items.length === 0) {
        listElement.innerHTML = '<div class="comment">類似するコメントが見つかりませんでした</div>';
        similarStatus.textContent = '0 件の結果';
        return;
      }
      similarStatus.textContent = '「' + escapeHtml(query) + '」に類似する ' + data.items.length + ' 件の結果';
      renderSearchResults(data.items, function (c) {
        return '<span class="similarity-badge">類似度: ' + (c.similarity_score * 100).toFixed(1) + '%</span>';
      });
    } catch (error) {
      console.error('Similar search error:', error);
      similarStatus.textContent = '類似検索でエラーが発生しました';
    } finally {
      similarBtn.disabled = false;
      similarBtn.textContent = '類似検索';
    }
  }

  // 典型度スライダー
  var centroidDetails = document.getElementById('centroid-details');
  var emotionDetails = document.getElementById('emotion-details');
  var centroidSlider = document.getElementById('centroid-slider');
  var centroidVal = document.getElementById('centroid-val');
  var centroidSearchBtn = document.getElementById('centroid-search-btn');
  var centroidClear = document.getElementById('centroid-clear');
  var centroidClearBtn = document.getElementById('centroid-clear-btn');
  var centroidStatus = document.getElementById('centroid-status');
  var centroidTopK = document.getElementById('centroid-top-k');

  if (centroidSlider) {
    centroidSlider.addEventListener('input', function () {
      centroidVal.textContent = centroidSlider.value + '%';
    });

    centroidSearchBtn.addEventListener('click', async function () {
      centroidSearchBtn.disabled = true;
      centroidSearchBtn.textContent = '検索中...';
      centroidStatus.textContent = '検索中...';
      try {
        var position = parseInt(centroidSlider.value) / 100;
        var params = new URLSearchParams({ position: position, platform: filters.platform, top_k: centroidTopK.value });
        var resp = await fetch(rootPath + '/api/u/' + userLogin + '/centroid?' + params);
        if (!resp.ok) throw new Error('Failed');
        var data = await resp.json();
        isSpecialMode = true;
        centroidClear.style.display = 'block';
        centroidDetails.open = true;
        var posLabel = position < 0.3 ? '典型的な発言' : position > 0.7 ? '珍しい発言' : '中間の発言';
        centroidStatus.textContent = posLabel + ' - ' + data.items.length + ' 件';
        renderSearchResults(data.items, function (c) {
          return '<span class="centroid-badge">重心類似度: ' + (c.similarity_score * 100).toFixed(1) + '%</span>';
        });
      } catch (e) {
        centroidStatus.textContent = 'エラーが発生しました';
      } finally {
        centroidSearchBtn.disabled = false;
        centroidSearchBtn.textContent = '検索';
      }
    });

    centroidClearBtn.addEventListener('click', exitSpecialMode);
  }

  // 感情スライダー
  var emotionSliders = document.querySelectorAll('#emotion-sliders input[type="range"]');
  var emotionSearchBtn = document.getElementById('emotion-search-btn');
  var emotionResetBtn = document.getElementById('emotion-reset-btn');
  var emotionClear = document.getElementById('emotion-clear');
  var emotionClearBtn = document.getElementById('emotion-clear-btn');
  var emotionStatus = document.getElementById('emotion-status');
  var emotionTopK = document.getElementById('emotion-top-k');

  if (emotionSliders.length) {
    emotionSliders.forEach(function (slider) {
      slider.addEventListener('input', function () {
        slider.parentElement.querySelector('.slider-val').textContent = slider.value;
      });
    });

    emotionResetBtn.addEventListener('click', function () {
      emotionSliders.forEach(function (slider) {
        slider.value = 0;
        slider.parentElement.querySelector('.slider-val').textContent = '0';
      });
    });

    emotionSearchBtn.addEventListener('click', async function () {
      var weights = {};
      var hasAny = false;
      emotionSliders.forEach(function (slider) {
        var val = parseInt(slider.value) / 100;
        weights[slider.dataset.emotion] = val;
        if (val > 0) hasAny = true;
      });
      if (!hasAny) { emotionStatus.textContent = 'スライダーを1つ以上動かしてください'; return; }
      emotionSearchBtn.disabled = true;
      emotionSearchBtn.textContent = '検索中...';
      emotionStatus.textContent = '検索中...';
      try {
        var params = new URLSearchParams(Object.assign({ platform: filters.platform, top_k: emotionTopK.value }, weights));
        var resp = await fetch(rootPath + '/api/u/' + userLogin + '/emotion?' + params);
        if (!resp.ok) throw new Error('Failed');
        var data = await resp.json();
        isSpecialMode = true;
        emotionClear.style.display = 'block';
        emotionDetails.open = true;
        var labels = { joy:'笑い', surprise:'驚き', admiration:'称賛', anger:'怒り', sadness:'悲しみ', cheer:'応援' };
        var activeList = Object.entries(weights).filter(function (kv) { return kv[1] > 0; })
          .map(function (kv) { return (labels[kv[0]] || kv[0]) + ':' + Math.round(kv[1]*100) + '%'; }).join(' + ');
        emotionStatus.textContent = activeList + ' → ' + data.items.length + ' 件';
        renderSearchResults(data.items, function (c) {
          return '<span class="similarity-badge">一致度: ' + (c.similarity_score * 100).toFixed(1) + '%</span>';
        });
      } catch (e) {
        emotionStatus.textContent = 'エラーが発生しました';
      } finally {
        emotionSearchBtn.disabled = false;
        emotionSearchBtn.textContent = '感情検索';
      }
    });

    emotionClearBtn.addEventListener('click', exitSpecialMode);
  }

  // -----------------------
  // Mobile Drawer & FABs
  // -----------------------
  (function () {
    var drawer = document.getElementById('side-drawer');
    var backdrop = document.getElementById('drawer-backdrop');
    var closeBtn = document.getElementById('drawer-close-btn');
    var fabMenu = document.getElementById('fab-menu');
    var fabTop = document.getElementById('fab-top');
    if (!drawer) return;
    function openDrawer() {
      drawer.classList.add('open');
      if (backdrop) backdrop.classList.add('open');
      document.body.style.overflow = 'hidden';
    }
    function closeDrawer() {
      drawer.classList.remove('open');
      if (backdrop) backdrop.classList.remove('open');
      document.body.style.overflow = '';
    }
    if (fabMenu) fabMenu.addEventListener('click', function () {
      drawer.classList.contains('open') ? closeDrawer() : openDrawer();
    });
    if (backdrop) backdrop.addEventListener('click', closeDrawer);
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);
    if (fabTop) fabTop.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
    var filterForm = document.querySelector('form');
    if (filterForm) filterForm.addEventListener('submit', closeDrawer);
  })();

  // -----------------------
  // データバージョン更新バナー
  // -----------------------
  (function () {
    var banner = document.getElementById('data-version-update-banner');
    var meta = document.getElementById('data-version-update-meta');
    var reloadBtn = document.getElementById('data-version-reload-btn');
    var dismissBtn = document.getElementById('data-version-dismiss-btn');
    if (!banner || !meta || !reloadBtn || !dismissBtn) return;

    var isRefreshing = false;

    function versionBase(version) { return String(version || '').split(':')[0]; }

    function formatVersion(version) {
      var base = versionBase(version);
      if (base.length >= 14) {
        return base.slice(0,4) + '/' + base.slice(4,6) + '/' + base.slice(6,8) + ' ' + base.slice(8,10) + ':' + base.slice(10,12) + ' (UTC)';
      }
      return base || '不明';
    }

    function setBannerVisible(visible) {
      banner.hidden = !visible;
      banner.classList.toggle('visible', visible);
    }

    function showUpdateNotice(latestVersion) {
      if (!latestVersion || latestVersion === currentDataVersion) return;
      meta.textContent = '表示中: ' + formatVersion(currentDataVersion) + ' / 最新: ' + formatVersion(latestVersion);
      setBannerVisible(true);
    }

    function hideUpdateNotice() { setBannerVisible(false); }

    function getCurrentPageCacheCandidates() {
      var currentUrl = new URL(window.location.href);
      currentUrl.hash = '';
      var candidates = new Set([currentUrl.toString()]);
      if (currentUrl.searchParams.get('page') === '1') {
        var withoutPage = new URL(currentUrl.toString());
        withoutPage.searchParams.delete('page');
        candidates.add(withoutPage.toString());
      }
      return Array.from(candidates);
    }

    async function clearCurrentPageCaches() {
      if (!('caches' in window)) return false;
      var targets = getCurrentPageCacheCandidates();
      var cacheNames = await caches.keys();
      await Promise.all(cacheNames.map(async function (cacheName) {
        var cache = await caches.open(cacheName);
        await Promise.all(targets.map(async function (target) {
          await cache.delete(target);
          await cache.delete(new Request(target));
        }));
      }));
      return true;
    }

    async function refreshViaServiceWorker(targetUrl) {
      if (!('serviceWorker' in navigator)) return false;
      var registration = await navigator.serviceWorker.ready;
      var worker = (registration && (registration.active || registration.waiting || registration.installing))
        || navigator.serviceWorker.controller;
      if (!worker) return false;
      return new Promise(function (resolve, reject) {
        var channel = new MessageChannel();
        var timerId = window.setTimeout(function () {
          reject(new Error('service_worker_refresh_timeout'));
        }, 8000);
        channel.port1.onmessage = function (event) {
          window.clearTimeout(timerId);
          var data = event.data || {};
          if (data.ok) { resolve(true); return; }
          reject(new Error(data.error || 'service_worker_refresh_failed'));
        };
        worker.postMessage({ type: 'twicome-refresh-comments', url: targetUrl }, [channel.port2]);
      });
    }

    async function refreshCommentsPage() {
      if (isRefreshing) return;
      isRefreshing = true;
      reloadBtn.disabled = true;
      dismissBtn.disabled = true;
      reloadBtn.textContent = '更新中...';
      var currentUrl = new URL(window.location.href);
      currentUrl.hash = '';
      try {
        var refreshed = await refreshViaServiceWorker(currentUrl.toString()).catch(function () { return false; });
        if (!refreshed) await clearCurrentPageCaches().catch(function () {});
      } finally {
        window.location.reload();
      }
    }

    window.TwicomeCommentsPageUpdate = { hideUpdateNotice: hideUpdateNotice, showUpdateNotice: showUpdateNotice };

    reloadBtn.addEventListener('click', function () {
      refreshCommentsPage().catch(function () { window.location.reload(); });
    });
    dismissBtn.addEventListener('click', hideUpdateNotice);
  })();

  // -----------------------
  // エクスポート機能
  // -----------------------
  (function () {
    var exportDetails = document.getElementById('export-details');
    if (!exportDetails) return;

    var dvEl = document.getElementById('export-data-version');
    if (dvEl) {
      fetch(rootPath + '/api/meta/data-version')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var latestDataVersion = data.data_version || '';
          var base = latestDataVersion.split(':')[0];
          if (base && base.length >= 14) {
            dvEl.textContent = 'データ更新: ' + base.slice(0,4) + '/' + base.slice(4,6) + '/' + base.slice(6,8) + ' ' + base.slice(8,10) + ':' + base.slice(10,12) + ' (UTC)';
          }
          if (window.TwicomeCommentsPageUpdate) {
            if (latestDataVersion && latestDataVersion !== currentDataVersion) {
              window.TwicomeCommentsPageUpdate.showUpdateNotice(latestDataVersion);
            } else {
              window.TwicomeCommentsPageUpdate.hideUpdateNotice();
            }
          }
        })
        .catch(function () {});
    }

    function getJSTDate(offsetDays) {
      var now = new Date(Date.now() + 9 * 60 * 60 * 1000);
      if (offsetDays) now.setUTCDate(now.getUTCDate() + offsetDays);
      return now.toISOString().slice(0, 10);
    }

    function doExport(params) {
      var url = new URL(location.origin + rootPath + '/u/' + encodeURIComponent(userLogin) + '/export');
      Object.entries(params).forEach(function (kv) { if (kv[1]) url.searchParams.set(kv[0], kv[1]); });
      location.href = url.toString();
    }

    exportDetails.querySelectorAll('.export-today-btn').forEach(function (btn) {
      btn.addEventListener('click', function () { doExport({ format: btn.dataset.format, date: getJSTDate(0) }); });
    });

    exportDetails.querySelectorAll('.export-yesterday-btn').forEach(function (btn) {
      btn.addEventListener('click', function () { doExport({ format: btn.dataset.format, date: getJSTDate(-1) }); });
    });

    exportDetails.querySelectorAll('.export-range-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var from = document.getElementById('export-date-from').value;
        var to = document.getElementById('export-date-to').value;
        if (!from && !to) { alert('日付を入力してください'); return; }
        doExport({ format: btn.dataset.format, date_from: from, date_to: to });
      });
    });

    exportDetails.querySelectorAll('.export-current-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        doExport({
          format: btn.dataset.format,
          date_from: filters.date_from || '',
          date_to: filters.date_to || '',
          q: filters.q || '',
          exclude_q: filters.exclude_q || '',
          owner_user_id: filters.owner_user_id || '',
          vod_id: filters.vod_id || '',
        });
      });
    });
  })();
})();
