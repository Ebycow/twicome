(function () {
  const filters = JSON.parse(document.getElementById('filters-data').textContent);
  const rawRootPath = JSON.parse(document.getElementById('root-path-data').textContent);
  const normalizedRootPath = (typeof rawRootPath === 'string') ? rawRootPath.trim() : '';
  const rootPath = (normalizedRootPath && normalizedRootPath !== '/') ? normalizedRootPath.replace(/\/+$/, '') : '';
  const voteCountsApiUrl = `${rootPath  }/api/comments/votes`;
  const initialPage = JSON.parse(document.getElementById('page-data').textContent);
  let totalPages = JSON.parse(document.getElementById('pages-data').textContent);
  const userLogin = JSON.parse(document.getElementById('user-data').textContent);
  const currentDataVersion = JSON.parse(document.getElementById('data-version-data').textContent);

  // markVisited
  if (window.TwicomeOfflineAccess) {
    window.TwicomeOfflineAccess.markVisited(rootPath, 'comments', userLogin);
  }

  // SW registration (overrides base.html sw_script block)
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register(`${rootPath  }/sw.js`, { scope: `${rootPath  }/` }).catch(function () {});
    });
    navigator.serviceWorker.addEventListener('message', function (event) {
      if (event.data && event.data.type === 'twicome-auth-redirect') {
        window.location.reload();
      }
    });
  }

  let currentMinPage = initialPage;
  let currentMaxPage = initialPage;
  const loadedPages = new Set([initialPage]);
  let isLoading = false;
  let isBest9Mode = false;
  let best9List = [];
  const best9Selected = new Set();
  const best9Data = new Map();

  (function () {
    try {
      const stored = localStorage.getItem(`best9_${  userLogin}`);
      if (stored) {
        best9List = JSON.parse(stored);
        best9List.forEach(function (id) { best9Selected.add(id); });
      }
      isBest9Mode = localStorage.getItem(`best9_mode_${  userLogin}`) === '1';
    } catch (e) {}
  })();

  const listElement = document.querySelector('.list');
  const isCursorMode = Boolean(filters.cursor);

  // FAISS mode flags (declared at top so scroll observer can reference them)
  let isSimilarMode = false;
  let isSpecialMode = false;

  /**
   * 文字列内のHTML特殊文字をエスケープする。
   * @param str - HTMLエスケープする文字列
   * @returns HTMLエスケープ済みの文字列
   */
  function escapeHtml(str) {
    if (str == null) {return '';}
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /**
   * コメントオブジェクトから本文HTMLを生成する。body_htmlがあればそのまま返し、なければテキストをエスケープする。
   * @param comment - 描画対象のコメントオブジェクト
   * @returns コメント本文として表示するHTML文字列
   */
  function renderBody(comment) {
    if (comment && comment.body_html) {return comment.body_html;}
    return escapeHtml(comment.body);
  }

  /**
   * コメントのコミュニティノート情報からHTML文字列を生成する。ノートがなければ空文字を返す。
   * @param comment - コミュニティノート情報を含むコメントオブジェクト
   * @returns コミュニティノート表示用のHTML文字列
   */
  function renderCommunityNote(comment) {
    if (!comment.community_note_body) {return '';}
    let html = '<div class="community-note"><div>';
    if (comment.cn_harm_risk != null) {
      const danger = Math.round((comment.cn_harm_risk + comment.cn_exaggeration + comment.cn_evidence_gap + (comment.cn_subjectivity || 0)) / 4);
      let badgeStyle;
      if (danger >= 60) {badgeStyle = 'background:rgba(244,67,54,0.2);color:#d32f2f;border:1px solid #d32f2f';}
      else if (danger >= 30) {badgeStyle = 'background:rgba(255,152,0,0.2);color:#e65100;border:1px solid #e65100';}
      else {badgeStyle = 'background:rgba(76,175,80,0.2);color:#2e7d32;border:1px solid #2e7d32';}
      html += `<span class="cn-danger-badge" style="${  badgeStyle  }">危険度 ${  danger  }</span>`;
    }
    if (comment.cn_status) {
      const statusJa = {supported: '裏付けあり', insufficient: '情報不足', inconsistent: '矛盾あり', not_applicable: '該当なし'};
      html += `<span class="cn-status-badge">${  escapeHtml(statusJa[comment.cn_status] || comment.cn_status)  }</span>`;
    }
    html += ` <i class="fa-solid fa-note-sticky"></i> ${  escapeHtml(comment.community_note_body)  }</div>`;
    if (comment.cn_harm_risk != null) {
      html += '<div class="cn-scores">';
      const scores = [
        {label:'検証可能性', val:comment.cn_verifiability, color:'#2196f3'},
        {label:'被害可能性', val:comment.cn_harm_risk, color:'#f44336'},
        {label:'誇張度', val:comment.cn_exaggeration, color:'#ff9800'},
        {label:'根拠不足', val:comment.cn_evidence_gap, color:'#9c27b0'},
        {label:'主観度', val:comment.cn_subjectivity, color:'#607d8b'},
      ];
      scores.forEach(function (s) {
        html += `<div class="cn-score-item"><span>${  s.label  }</span><div class="cn-score-bar"><div class="cn-score-fill" style="width:${  s.val  }%;background:${  s.color  };"></div></div><span>${  s.val  }</span></div>`;
      });
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  /**
   * コメントオブジェクトからDOM要素（リンクとコメント本体）を生成して返す。
   * @param comment - 描画対象のコメントオブジェクト
   * @param options - バッジ表示や強調表示を切り替える描画オプション
   * @returns コメントリンク要素とコメント本体要素
   */
  function createCommentElement(comment, options) {
    options = options || {};
    const badge = typeof options.badge === 'function' ? options.badge(comment) : (options.badge || '');
    const link = document.createElement('a');
    link.href = `?cursor=${  comment.comment_id}`;
    link.style.textDecoration = 'none';
    link.style.color = 'inherit';
    link.style.display = 'block';
    link.addEventListener('click', function (e) {
      if (e.target.closest('button')) { e.preventDefault(); return; }
    });
    const commentDiv = document.createElement('div');
    if (options.cursorMode) {
      if (comment.comment_id === filters.cursor) {commentDiv.className = 'comment highlighted';}
      else if (comment.commenter_login_snapshot === userLogin) {commentDiv.className = 'comment grayed';}
      else {commentDiv.className = 'comment';}
    } else {
      commentDiv.className = 'comment';
    }
    commentDiv.id = comment.comment_id;
    commentDiv.innerHTML =
      `<div class="comment-head">` +
      `<div>${ 
      badge 
      }<a href="${  escapeHtml(comment.vod_jump_link)  }" target="_blank" class="pill">VOD ${  escapeHtml(String(comment.vod_id))  }</a>${ 
      comment.youtube_jump_link ? `<a href="${  escapeHtml(comment.youtube_jump_link)  }" target="_blank" class="pill">YouTube</a>` : '' 
      }<strong>${  escapeHtml(comment.vod_title)  }</strong>${ 
      options.showOwner ? `<span class="meta">· 配信者: ${  escapeHtml(comment.owner_login)  }${comment.owner_display_name ? `（${  escapeHtml(comment.owner_display_name)  }）` : ''  }</span>` : '' 
      }<span class="meta">· ${  escapeHtml(comment.commenter_login_snapshot)  }${comment.commenter_display_name_snapshot ? `（${  escapeHtml(comment.commenter_display_name_snapshot)  }）` : ''  }の書き込み</span>` +
      `<span class="meta">· ${  escapeHtml(comment.offset_hms)  }</span>${ 
      comment.comment_created_at_jst ? `<span class="meta">· ${  escapeHtml(comment.comment_created_at_jst)  } JST</span>` : '' 
      }${options.showRelativeTime && comment.relative_time ? `<span class="meta ${  comment.is_recent ? 'recent' : ''  }">· ${  escapeHtml(comment.relative_time)  }</span>` : '' 
      }${options.showBits && comment.bits_spent ? `<span class="pill">bits ${  escapeHtml(comment.bits_spent)  }</span>` : '' 
      }</div>` +
      `<div class="meta">${  renderVoteButtonsMarkup(comment.comment_id, comment.twicome_likes_count, comment.twicome_dislikes_count)  }</div>` +
      `</div>` +
      `<div class="body">${  renderBody(comment)  }</div>${ 
      renderCommunityNote(comment)}`;
    link.appendChild(commentDiv);
    return { link, commentDiv };
  }

  /**
   * ブラウザのURLをページ番号またはカーソルIDに基づいて履歴に積む形で更新する。
   * @param page - 現在表示中として反映するページ番号
   * @param cursor - URLに残すカーソルID。未指定ならpageを使う
   */
  function updateURL(page, cursor) {
    const url = new URL(window.location);
    if (cursor) {
      url.searchParams.set('cursor', cursor);
      url.searchParams.delete('page');
    } else {
      url.searchParams.set('page', page);
      url.searchParams.delete('cursor');
    }
    window.history.pushState({}, '', url);
  }

  /**
   * 前ページ読み込みボタンの表示/非表示をカーソルモードと現在ページ番号に応じて切り替える。
   */
  function updatePrevButton() {
    const btn = document.getElementById('load-prev');
    if (!btn) {return;}
    if (isCursorMode || currentMinPage <= 1) {
      btn.style.display = 'none';
    } else {
      btn.style.display = 'block';
    }
  }

  /**
   * 投票ボタン（いいね・疑問）のHTML文字列を生成して返す。
   * @param commentId - 対象コメントのID
   * @param likesCount - いいね数
   * @param dislikesCount - 疑問票数
   * @returns 投票ボタン一式のHTML文字列
   */
  function renderVoteButtonsMarkup(commentId, likesCount, dislikesCount) {
    const safeCommentId = escapeHtml(commentId);
    const safeLikes = escapeHtml(likesCount);
    const safeDislikes = escapeHtml(dislikesCount);
    return `<button onclick="vote(this, '${  safeCommentId  }', 'like')" class="vote-btn" data-count="${  safeLikes  }"><i class="fa-solid fa-thumbs-up"></i> ${  safeLikes  }</button>` +
           `<button onclick="vote(this, '${  safeCommentId  }', 'dislike')" class="vote-btn" data-count="${  safeDislikes  }"><i class="fa-solid fa-thumbs-down"></i> ${  safeDislikes  }</button>`;
  }

  /**
   * コンテナ要素内に投票ボタンHTMLをセットする。
   * @param container - 投票ボタンを書き込むコンテナ要素
   * @param commentId - 対象コメントのID
   * @param likesCount - いいね数
   * @param dislikesCount - 疑問票数
   */
  function setVoteControls(container, commentId, likesCount, dislikesCount) {
    if (!container) {return;}
    container.innerHTML = renderVoteButtonsMarkup(commentId, likesCount, dislikesCount);
  }

  /**
   * APIから最新の投票数を取得して遅延ハイドレーション対象の投票ボタンを更新する。
   * @param containers - 遅延ハイドレーション対象の投票コンテナ配列
   */
  async function hydrateDeferredVoteControls(containers) {
    const targets = (containers || []).filter(function (container) { return container && container.dataset.commentId; });
    if (!targets.length) {return;}
    let items = {};
    try {
      const response = await fetch(voteCountsApiUrl, {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ comment_ids: targets.map(function (c) { return c.dataset.commentId; }) }),
      });
      if (!response.ok) {throw new Error(`vote_counts_failed:${  response.status}`);}
      const data = await response.json();
      items = (data && data.items) || {};
    } catch (error) {
      console.warn('Deferred vote hydration failed, keeping initial counts:', error);
      return;
    }
    targets.forEach(function (container) {
      const commentId = container.dataset.commentId;
      const currentButtons = container.querySelectorAll('.vote-btn');
      const currentLikes = Number(currentButtons[0] && currentButtons[0].dataset.count || 0);
      const currentDislikes = Number(currentButtons[1] && currentButtons[1].dataset.count || 0);
      const item = items[commentId] || {};
      setVoteControls(container, commentId,
        Number(item.twicome_likes_count != null ? item.twicome_likes_count : currentLikes),
        Number(item.twicome_dislikes_count != null ? item.twicome_dislikes_count : currentDislikes)
      );
    });
  }

  /**
   * アイドル時またはタイムアウト後に遅延投票ハイドレーションをスケジュールする。
   */
  function scheduleDeferredVoteHydration() {
    const containers = Array.from(document.querySelectorAll('[data-vote-controls="deferred"]'));
    if (!containers.length) {return;}
    const run = function () { void hydrateDeferredVoteControls(containers); };
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(run, { timeout: 1800 });
      return;
    }
    window.setTimeout(run, 350);
  }

  /**
   * 指定ページのコメントをAPIから取得してリストに追加または差し替える。
   * @param page - 読み込むページ番号
   * @param direction - コメントの挿入方向（`append` または `prepend`）
   * @param reset - trueなら既存一覧をリセットして再描画する
   */
  async function loadComments(page, direction, reset) {
    direction = direction || 'append';
    reset = reset || false;
    if (isLoading) {return;}
    if (!reset && (loadedPages.has(page) || page < 1 || page > totalPages)) {return;}
    isLoading = true;

    if (reset) {
      listElement.innerHTML = '';
      loadedPages.clear();
      currentMinPage = page;
      currentMaxPage = page;
      loadedPages.add(page);
      updateURL(page, filters.cursor);
    }

    const params = new URLSearchParams({
      platform: filters.platform,
      page,
      page_size: filters.page_size,
      sort: filters.sort,
    });
    if (filters.cursor) {params.set('cursor', filters.cursor);}
    if (filters.vod_id) {params.set('vod_id', filters.vod_id);}
    if (filters.owner_user_id) {params.set('owner_user_id', filters.owner_user_id);}
    if (filters.q) {params.set('q', filters.q);}
    if (filters.exclude_q) {params.set('exclude_q', filters.exclude_q);}

    try {
      const response = await fetch(`${rootPath  }/api/u/${  userLogin  }?${  params}`);
      if (!response.ok) {throw new Error('Failed to load comments');}
      const data = await response.json();

      if (reset) {totalPages = Math.ceil(data.total / filters.page_size);}
      if (!reset) {loadedPages.add(page);}

      const itemsToRender = direction === 'prepend' ? data.items.slice().reverse() : data.items;
      itemsToRender.forEach(function (comment) {
        const el = createCommentElement(comment, {
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
        if (isBest9Mode) {addBest9Button(el.commentDiv);}
      });

      if (direction === 'prepend') {currentMinPage = Math.min(currentMinPage, page);}
      else {currentMaxPage = Math.max(currentMaxPage, page);}

      updatePrevButton();
      if (!reset) {updateURL(page, filters.cursor);}
    } catch (error) {
      console.error('Error loading comments:', error);
    } finally {
      isLoading = false;
    }
  }

  const sentinel = document.getElementById('scroll-sentinel');
  const scrollObserver = new IntersectionObserver(function (entries) {
    if (isCursorMode || isSimilarMode || isSpecialMode) {return;}
    if (entries[0].isIntersecting && currentMaxPage < totalPages) {
      loadComments(currentMaxPage + 1, 'append');
    }
  }, { rootMargin: '0px 0px 600px 0px' });

  if (!isCursorMode) {scrollObserver.observe(sentinel);}

  const loadPrevBtn = document.getElementById('load-prev-btn');
  if (loadPrevBtn) {
    loadPrevBtn.addEventListener('click', function () {
      if (isCursorMode) {return;}
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
    const element = document.getElementById(filters.cursor);
    if (element) {
      element.classList.add('highlighted');
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  /**
   * ボタンの位置を起点にコンフェティアニメーションを生成する。
   * @param button - コンフェティを発生させる基点のボタン要素
   */
  function spawnConfetti(button) {
    const rect = button.getBoundingClientRect();
    const ox = rect.left + rect.width / 2;
    const oy = rect.top + rect.height / 2;
    const colors = ['#ff6b6b','#ffd93d','#6bcb77','#4d96ff','#ff6eb4','#a66cff'];
    const shapes = ['50%','2px'];
    for (let i = 0; i < 12; i++) {
      const el = document.createElement('div');
      el.className = 'confetti';
      const angle = (Math.PI * 2 * i) / 12 + (Math.random() - 0.5) * 0.5;
      const dist = 30 + Math.random() * 50;
      el.style.left = `${ox  }px`;
      el.style.top = `${oy  }px`;
      el.style.background = colors[Math.floor(Math.random() * colors.length)];
      el.style.borderRadius = shapes[Math.floor(Math.random() * shapes.length)];
      el.style.width = `${5 + Math.random() * 5  }px`;
      el.style.height = `${5 + Math.random() * 5  }px`;
      el.style.setProperty('--cx', `${Math.cos(angle) * dist  }px`);
      el.style.setProperty('--cy', `${Math.sin(angle) * dist - 20  }px`);
      el.style.setProperty('--cr', `${Math.random() * 720 - 360  }deg`);
      document.body.appendChild(el);
      el.addEventListener('animationend', function () { this.remove(); });
    }
  }

  const votePending = new Map();
  const VOTE_DEBOUNCE_MS = 500;

  /**
   * 投票ボタンのクリック時にカウントを即時更新しデバウンス付きでAPIへ送信する。
   * @param button - クリックされた投票ボタン要素
   * @param commentId - 投票対象コメントのID
   * @param type - 投票種別（`like` または `dislike`）
   */
  function vote(button, commentId, type) {
    spawnConfetti(button);
    const key = `${commentId  }-${  type}`;
    const currentCount = parseInt(button.dataset.count || '0', 10) + 1;
    button.dataset.count = currentCount;
    button.innerHTML = (type === 'like' ? '<i class="fa-solid fa-thumbs-up"></i> ' : '<i class="fa-solid fa-thumbs-down"></i> ') + currentCount;
    if (votePending.has(key)) {
      const pending = votePending.get(key);
      pending.count++;
      clearTimeout(pending.timer);
      pending.timer = setTimeout(function () { flushVote(key); }, VOTE_DEBOUNCE_MS);
    } else {
      votePending.set(key, {
        count: 1, button, commentId, type,
        timer: setTimeout(function () { flushVote(key); }, VOTE_DEBOUNCE_MS)
      });
    }
  }

  /**
   * デバウンスキーに対応する保留中の投票をAPIへ送信する。
   * @param key - 投票バッファを識別する `{commentId}-{type}` 形式のキー
   */
  async function flushVote(key) {
    const pending = votePending.get(key);
    if (!pending) {return;}
    votePending.delete(key);
    const url = `${rootPath  }/${  pending.type  }/${  pending.commentId  }?count=${  pending.count}`;
    try {
      const response = await fetch(url, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!response.ok) {console.error('Vote failed:', await response.text());}
    } catch (error) {
      console.error('Network error:', error);
    }
  }

  // vote must be global for onclick attributes in HTML
  window.vote = vote;

  // -----------------------
  // Best9モード
  // -----------------------
  const best9ToggleBtn = document.getElementById('best9-toggle-btn');
  const best9Bar = document.getElementById('best9-bar');

  /**
   * コメント本文テキストをBest9テキストキャッシュに保存する。
   * @param commentId - Best9候補として保存するコメントID
   * @param commentDiv - コメント本文を抽出するDOM要素
   */
  function captureBest9Text(commentId, commentDiv) {
    if (best9Data.has(commentId)) {return;}
    const bodyEl = commentDiv ? commentDiv.querySelector('.body') : null;
    if (bodyEl) {best9Data.set(commentId, (bodyEl.innerText || bodyEl.textContent || '').trim());}
  }

  /**
   * コメント要素のメタ領域にBest9追加ボタンを挿入する。
   * @param commentDiv - Best9操作ボタンを追加するコメント要素
   */
  function addBest9Button(commentDiv) {
    if (commentDiv.querySelector('.best9-add-btn')) {return;}
    const commentId = commentDiv.id;
    if (!commentId) {return;}
    if (best9Selected.has(commentId)) {captureBest9Text(commentId, commentDiv);}
    const btn = document.createElement('button');
    const isSelected = best9Selected.has(commentId);
    btn.className = `best9-add-btn${  isSelected ? ' selected' : ''}`;
    btn.innerHTML = isSelected ? '選択済み <i class="fa-solid fa-check"></i>' : '+ Best9';
    btn.type = 'button';
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      toggleBest9(commentId, btn, commentDiv);
    });
    const metaDiv = commentDiv.querySelector('.comment-head > div.meta');
    if (metaDiv) {metaDiv.appendChild(btn);}
  }

  /**
   * 現在のBest9リストをlocalStorageに保存する。
   */
  function saveBest9() {
    try { localStorage.setItem(`best9_${  userLogin}`, JSON.stringify(best9List)); } catch (e) {}
  }

  /**
   * Best9トグルボタンのラベルをモードと選択件数に応じて更新する。
   */
  function updateBest9ToggleLabel() {
    if (!best9ToggleBtn) {return;}
    const count = best9List.length;
    if (isBest9Mode) {
      best9ToggleBtn.textContent = count > 0 ? `Best9: ON（${  count  }件）` : 'Best9: ON';
    } else {
      best9ToggleBtn.textContent = count > 0 ? `Best9モード（${  count  }件保存中）` : 'Best9モード';
    }
  }

  /**
   * コメントのBest9選択状態をトグルし、UIとlocalStorageを更新する。
   * @param commentId - 切り替え対象のコメントID
   * @param btn - 状態表示を更新するBest9ボタン要素
   * @param commentDiv - 選択状態を反映するコメント要素
   */
  function toggleBest9(commentId, btn, commentDiv) {
    if (best9Selected.has(commentId)) {
      best9Selected.delete(commentId);
      best9List = best9List.filter(function (id) { return id !== commentId; });
      if (btn) { btn.className = 'best9-add-btn'; btn.textContent = '+ Best9'; }
      if (commentDiv) {commentDiv.classList.remove('best9-selected');}
    } else {
      if (best9List.length >= 9) { alert('9件まで選択できます'); return; }
      best9List.push(commentId);
      best9Selected.add(commentId);
      if (btn) { btn.className = 'best9-add-btn selected'; btn.innerHTML = '選択済み <i class="fa-solid fa-check"></i>'; }
      if (commentDiv) {commentDiv.classList.add('best9-selected');}
      captureBest9Text(commentId, commentDiv);
    }
    saveBest9();
    updateBest9Bar();
    updateBest9ToggleLabel();
    const previewArea = document.getElementById('best9-preview-area');
    if (previewArea && previewArea.style.display !== 'none') {renderPreviewGrid();}
  }

  /**
   * コメントID配列をdeflate-raw圧縮してURL安全なBase64文字列に変換する。
   * @param idArray - URL短縮用に圧縮するコメントID配列
   * @returns deflate圧縮したID文字列。未対応時はnull
   */
  async function compressIds(idArray) {
    if (!window.CompressionStream) {return null;}
    try {
      const encoded = new TextEncoder().encode(idArray.join(','));
      const cs = new CompressionStream('deflate-raw');
      const writer = cs.writable.getWriter();
      writer.write(encoded);
      writer.close();
      const chunks = [];
      const reader = cs.readable.getReader();
      while (true) {
        const result = await reader.read();
        if (result.done) {break;}
        chunks.push(result.value);
      }
      const totalLen = chunks.reduce(function (acc, c) { return acc + c.length; }, 0);
      const buf = new Uint8Array(totalLen);
      let offset = 0;
      for (let i = 0; i < chunks.length; i++) { buf.set(chunks[i], offset); offset += chunks[i].length; }
      const binary = String.fromCharCode.apply(null, buf);
      return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
    } catch (e) { return null; }
  }

  /**
   * 現在のBest9リストを元に共有用URLを生成して返す。
   * @returns 現在のBest9共有URL
   */
  async function buildBest9Url() {
    const z = await compressIds(best9List);
    if (z) {return `${location.origin + rootPath  }/best9?z=${  z  }&login=${  encodeURIComponent(userLogin)}`;}
    return `${location.origin + rootPath  }/best9?ids=${  encodeURIComponent(best9List.join(','))  }&login=${  encodeURIComponent(userLogin)}`;
  }

  /**
   * Best9バーの件数表示と共有URLを最新の選択状態に更新する。
   */
  async function updateBest9Bar() {
    document.getElementById('best9-count').textContent = `${best9List.length  }/9`;
    const urlBox = document.getElementById('best9-url-box');
    if (best9List.length > 0) {
      const url = await buildBest9Url();
      document.getElementById('best9-url-input').value = url;
      document.getElementById('best9-go-btn').onclick = function () { window.open(url, '_blank'); };
      urlBox.style.display = 'flex';
    } else {
      urlBox.style.display = 'none';
    }
  }

  /**
   * Best9モードのON/OFFに応じてトグルボタン・バー・各コメントへのボタン追加/削除を行う。
   */
  function applyBest9ModeUI() {
    if (!best9ToggleBtn) {return;}
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
      try { localStorage.setItem(`best9_mode_${  userLogin}`, isBest9Mode ? '1' : '0'); } catch (e) {}
      applyBest9ModeUI();
      updateBest9ToggleLabel();
    });

    document.getElementById('best9-copy-btn').addEventListener('click', function () {
      const input = document.getElementById('best9-url-input');
      navigator.clipboard.writeText(input.value).then(function () {
        const btn = document.getElementById('best9-copy-btn');
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
      const previewArea = document.getElementById('best9-preview-area');
      if (previewArea && previewArea.style.display !== 'none') {renderPreviewGrid();}
      updateBest9Bar();
      updateBest9ToggleLabel();
    });

    const best9PreviewBtn = document.getElementById('best9-preview-btn');
    if (best9PreviewBtn) {
      best9PreviewBtn.addEventListener('click', function () {
        const area = document.getElementById('best9-preview-area');
        const isVisible = area.style.display !== 'none';
        area.style.display = isVisible ? 'none' : 'block';
        best9PreviewBtn.textContent = isVisible ? '▲ プレビュー' : '▼ プレビュー';
        if (!isVisible) {renderPreviewGrid();}
      });
    }
  }

  let dragSrcIndex = null;

  /**
   * Best9プレビューグリッドを現在の選択リストで再描画する。
   */
  function renderPreviewGrid() {
    const grid = document.getElementById('best9-preview-grid');
    if (!grid) {return;}
    grid.innerHTML = '';
    for (let i = 0; i < 9; i++) {
      const slot = document.createElement('div');
      const id = best9List[i];
      if (id) {
        slot.className = 'best9-slot filled';
        slot.draggable = true;
        slot.dataset.index = i;
        const text = best9Data.get(id) || '';
        const snippet = text.length > 80 ? `${text.substring(0, 80)  }…` : text;
        slot.innerHTML =
          `<div class="best9-slot-num">No.${  i + 1  }</div>` +
          `<div class="best9-slot-text">${  escapeHtml(snippet)  }</div>` +
          `<button type="button" class="best9-slot-remove" title="選択解除">×</button>`;
        slot.addEventListener('dragstart', onSlotDragStart);
        slot.addEventListener('dragover', onSlotDragOver);
        slot.addEventListener('dragleave', onSlotDragLeave);
        slot.addEventListener('drop', onSlotDrop);
        slot.addEventListener('dragend', onSlotDragEnd);
        (function (slotId) {
          slot.querySelector('.best9-slot-remove').addEventListener('click', function (e) {
            e.stopPropagation();
            const commentDiv = document.getElementById(slotId);
            const addBtn = commentDiv ? commentDiv.querySelector('.best9-add-btn') : null;
            toggleBest9(slotId, addBtn, commentDiv);
          });
        })(id);
      } else {
        slot.className = 'best9-slot empty-slot';
        slot.innerHTML = `<div class="best9-slot-num">No.${  i + 1  }</div><div class="best9-slot-text">（未選択）</div>`;
      }
      grid.appendChild(slot);
    }
  }

  /**
   * Best9プレビュースロットのドラッグ開始時にソースインデックスを記録しスタイルを適用する。
   * @param e - ドラッグ開始イベント
   */
  function onSlotDragStart(e) {
    dragSrcIndex = parseInt(this.dataset.index);
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
  }

  /**
   * Best9プレビュースロット上をドラッグ通過中にドロップ受け入れスタイルを適用する。
   * @param e - ドラッグオーバーイベント
   */
  function onSlotDragOver(e) {
    if (!this.classList.contains('filled')) {return;}
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    this.classList.add('drag-over');
  }

  /**
   * Best9プレビュースロットからドラッグが離れた際にドロップ強調スタイルを除去する。
   */
  function onSlotDragLeave() { this.classList.remove('drag-over'); }

  /**
   * Best9プレビュースロットへのドロップ時にリスト内の順序を入れ替えてグリッドを再描画する。
   * @param e - ドロップイベント
   */
  function onSlotDrop(e) {
    e.preventDefault();
    this.classList.remove('drag-over');
    const destIndex = parseInt(this.dataset.index);
    if (dragSrcIndex === null || dragSrcIndex === destIndex) {return;}
    if (destIndex >= best9List.length) {return;}
    const moved = best9List.splice(dragSrcIndex, 1)[0];
    best9List.splice(destIndex, 0, moved);
    saveBest9();
    renderPreviewGrid();
    updateBest9Bar();
  }

  /**
   * Best9プレビュースロットのドラッグ終了時にドラッグ状態をリセットする。
   */
  function onSlotDragEnd() {
    this.classList.remove('dragging');
    dragSrcIndex = null;
    document.querySelectorAll('.best9-slot').forEach(function (s) { s.classList.remove('drag-over'); });
  }

  // -----------------------
  // FAISS: 類似検索・典型度・感情スライダー
  // (DOM要素が存在する場合のみ有効)
  // -----------------------
  const similarBtn = document.getElementById('similar-search-btn');
  const similarInput = document.getElementById('similar-q');
  const similarTopK = document.getElementById('similar-top-k');
  const similarClear = document.getElementById('similar-clear');
  const similarClearBtn = document.getElementById('similar-clear-btn');
  const similarStatus = document.getElementById('similar-status');
  const diversitySlider = document.getElementById('diversity-slider');
  const diversityVal = document.getElementById('diversity-val');

  if (diversitySlider) {
    diversitySlider.addEventListener('input', function () {
      const v = parseInt(this.value, 10);
      diversityVal.textContent = v === 100 ? 'OFF' : `${100 - v}%`;
    });
  }

  /**
   * 検索結果のコメント配列をリスト要素に描画する。
   * @param items - 特殊検索結果として表示するコメント配列
   * @param badgeHtml - 各コメントに付けるバッジHTML、または生成関数
   */
  function renderSearchResults(items, badgeHtml) {
    listElement.innerHTML = '';
    if (items.length === 0) {
      listElement.innerHTML = '<div class="comment">該当するコメントが見つかりませんでした</div>';
      return;
    }
    items.forEach(function (comment) {
      const el = createCommentElement(comment, { badge: badgeHtml });
      listElement.appendChild(el.link);
      if (isBest9Mode) {addBest9Button(el.commentDiv);}
    });
  }

  /**
   * 類似検索・典型度・感情検索などの特殊モードを終了して通常のコメント一覧に戻る。
   */
  function exitSpecialMode() {
    isSpecialMode = false;
    isSimilarMode = false;
    if (similarClear) {similarClear.style.display = 'none';}
    if (similarStatus) {similarStatus.textContent = '';}
    if (centroidClear) {centroidClear.style.display = 'none';}
    if (centroidStatus) {centroidStatus.textContent = '';}
    if (emotionClear) {emotionClear.style.display = 'none';}
    if (emotionStatus) {emotionStatus.textContent = '';}
    if (centroidDetails) {centroidDetails.open = false;}
    if (emotionDetails) {emotionDetails.open = false;}
    loadComments(initialPage, 'append', true);
  }

  if (similarBtn) {
    similarBtn.addEventListener('click', performSimilarSearch);
    similarInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); performSimilarSearch(); }
    });
    similarClearBtn.addEventListener('click', exitSpecialMode);
  }

  /**
   * 入力クエリでFAISS類似検索APIを呼び出して結果をコメントリストに描画する。
   */
  async function performSimilarSearch() {
    const query = similarInput.value.trim();
    if (!query) {return;}
    similarBtn.disabled = true;
    similarBtn.textContent = '検索中...';
    similarStatus.textContent = '検索中...';
    try {
      const params = new URLSearchParams({ q: query, platform: filters.platform, top_k: similarTopK.value });
      const diversityRaw = diversitySlider ? parseInt(diversitySlider.value, 10) : 100;
      const useMmr = diversityRaw < 100;
      if (useMmr) {
        // スライダー値 (0=多様優先〜100=類似優先) を diversity (0.0〜1.0) に変換
        params.set('diversity', (diversityRaw / 100).toFixed(2));
      }
      const response = await fetch(`${rootPath  }/api/u/${  userLogin  }/similar?${  params}`);
      if (!response.ok) {
        const err = await response.json();
        if (err.error === 'similar_search_not_available') {
          similarStatus.textContent = 'このユーザの類似検索インデックスはまだ作成されていません';
          return;
        }
        throw new Error('Search failed');
      }
      const data = await response.json();
      isSimilarMode = true;
      similarClear.style.display = 'block';
      if (data.items.length === 0) {
        listElement.innerHTML = '<div class="comment">類似するコメントが見つかりませんでした</div>';
        similarStatus.textContent = '0 件の結果';
        return;
      }
      const modeLabel = useMmr ? `（多様性 ${100 - diversityRaw}%）` : '';
      similarStatus.textContent = `「${  escapeHtml(query)  }」に類似する ${  data.items.length  } 件の結果${modeLabel}`;
      renderSearchResults(data.items, function (c) {
        return `<span class="similarity-badge">類似度: ${  (c.similarity_score * 100).toFixed(1)  }%</span>`;
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
  const centroidDetails = document.getElementById('centroid-details');
  const emotionDetails = document.getElementById('emotion-details');
  const centroidSlider = document.getElementById('centroid-slider');
  const centroidVal = document.getElementById('centroid-val');
  const centroidSearchBtn = document.getElementById('centroid-search-btn');
  const centroidClear = document.getElementById('centroid-clear');
  const centroidClearBtn = document.getElementById('centroid-clear-btn');
  const centroidStatus = document.getElementById('centroid-status');
  const centroidTopK = document.getElementById('centroid-top-k');

  if (centroidSlider) {
    centroidSlider.addEventListener('input', function () {
      centroidVal.textContent = `${centroidSlider.value  }%`;
    });

    centroidSearchBtn.addEventListener('click', async function () {
      centroidSearchBtn.disabled = true;
      centroidSearchBtn.textContent = '検索中...';
      centroidStatus.textContent = '検索中...';
      try {
        const position = parseInt(centroidSlider.value) / 100;
        const params = new URLSearchParams({ position, platform: filters.platform, top_k: centroidTopK.value });
        const resp = await fetch(`${rootPath  }/api/u/${  userLogin  }/centroid?${  params}`);
        if (!resp.ok) {throw new Error('Failed');}
        const data = await resp.json();
        isSpecialMode = true;
        centroidClear.style.display = 'block';
        centroidDetails.open = true;
        let posLabel;
        if (position < 0.3) { posLabel = '典型的な発言'; }
        else if (position > 0.7) { posLabel = '珍しい発言'; }
        else { posLabel = '中間の発言'; }
        centroidStatus.textContent = `${posLabel  } - ${  data.items.length  } 件`;
        renderSearchResults(data.items, function (c) {
          return `<span class="centroid-badge">重心類似度: ${  (c.similarity_score * 100).toFixed(1)  }%</span>`;
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
  const emotionSliders = document.querySelectorAll('#emotion-sliders input[type="range"]');
  const emotionSearchBtn = document.getElementById('emotion-search-btn');
  const emotionResetBtn = document.getElementById('emotion-reset-btn');
  const emotionClear = document.getElementById('emotion-clear');
  const emotionClearBtn = document.getElementById('emotion-clear-btn');
  const emotionStatus = document.getElementById('emotion-status');
  const emotionTopK = document.getElementById('emotion-top-k');
  const emotionDiversitySlider = document.getElementById('emotion-diversity-slider');
  const emotionDiversityVal = document.getElementById('emotion-diversity-val');

  if (emotionDiversitySlider) {
    emotionDiversitySlider.addEventListener('input', function () {
      const v = parseInt(this.value, 10);
      emotionDiversityVal.textContent = v === 100 ? 'OFF' : `${100 - v}%`;
    });
  }

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
      const weights = {};
      let hasAny = false;
      emotionSliders.forEach(function (slider) {
        const val = parseInt(slider.value) / 100;
        weights[slider.dataset.emotion] = val;
        if (val > 0) {hasAny = true;}
      });
      if (!hasAny) { emotionStatus.textContent = 'スライダーを1つ以上動かしてください'; return; }
      emotionSearchBtn.disabled = true;
      emotionSearchBtn.textContent = '検索中...';
      emotionStatus.textContent = '検索中...';
      try {
        const params = new URLSearchParams(Object.assign({ platform: filters.platform, top_k: emotionTopK.value }, weights));
        const diversityRaw = emotionDiversitySlider ? parseInt(emotionDiversitySlider.value, 10) : 100;
        const useMmr = diversityRaw < 100;
        if (useMmr) {
          params.set('diversity', (diversityRaw / 100).toFixed(2));
        }
        const resp = await fetch(`${rootPath  }/api/u/${  userLogin  }/emotion?${  params}`);
        if (!resp.ok) {throw new Error('Failed');}
        const data = await resp.json();
        isSpecialMode = true;
        emotionClear.style.display = 'block';
        emotionDetails.open = true;
        const labels = { joy:'笑い', surprise:'驚き', admiration:'称賛', anger:'怒り', sadness:'悲しみ', cheer:'応援' };
        const activeList = Object.entries(weights).filter(function (kv) { return kv[1] > 0; })
          .map(function (kv) { return `${labels[kv[0]] || kv[0]  }:${  Math.round(kv[1]*100)  }%`; }).join(' + ');
        const modeLabel = useMmr ? `（多様性 ${100 - diversityRaw}%）` : '';
        emotionStatus.textContent = `${activeList  } → ${  data.items.length  } 件${modeLabel}`;
        renderSearchResults(data.items, function (c) {
          return `<span class="similarity-badge">一致度: ${  (c.similarity_score * 100).toFixed(1)  }%</span>`;
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
    const drawer = document.getElementById('side-drawer');
    const backdrop = document.getElementById('drawer-backdrop');
    const closeBtn = document.getElementById('drawer-close-btn');
    const fabMenu = document.getElementById('fab-menu');
    const fabTop = document.getElementById('fab-top');
    if (!drawer) {return;}
    /**
     * モバイル用サイドドロワーを開いてスクロールをロックする。
     */
    function openDrawer() {
      drawer.classList.add('open');
      if (backdrop) {backdrop.classList.add('open');}
      document.body.style.overflow = 'hidden';
    }
    /**
     * モバイル用サイドドロワーを閉じてスクロールロックを解除する。
     */
    function closeDrawer() {
      drawer.classList.remove('open');
      if (backdrop) {backdrop.classList.remove('open');}
      document.body.style.overflow = '';
    }
    if (fabMenu) {fabMenu.addEventListener('click', function () {
      drawer.classList.contains('open') ? closeDrawer() : openDrawer();
    });}
    if (backdrop) {backdrop.addEventListener('click', closeDrawer);}
    if (closeBtn) {closeBtn.addEventListener('click', closeDrawer);}
    if (fabTop) {
      fabTop.addEventListener('click', function () { window.scrollTo({ top: 0, behavior: 'smooth' }); });
      window.addEventListener('scroll', function () {
        fabTop.classList.toggle('visible', window.scrollY > 300);
      }, { passive: true });
    }
    const filterForm = document.querySelector('form');
    if (filterForm) {filterForm.addEventListener('submit', closeDrawer);}
  })();

  // -----------------------
  // データバージョン更新バナー
  // -----------------------
  (function () {
    const banner = document.getElementById('data-version-update-banner');
    const meta = document.getElementById('data-version-update-meta');
    const reloadBtn = document.getElementById('data-version-reload-btn');
    const dismissBtn = document.getElementById('data-version-dismiss-btn');
    if (!banner || !meta || !reloadBtn || !dismissBtn) {return;}

    let isRefreshing = false;

    /**
     * データバージョン文字列からコロン以降の付加情報を除いた基底バージョンを返す。
     * @param version - データバージョン文字列
     * @returns 付加情報を除いた基底バージョン文字列
     */
    function versionBase(version) { return String(version || '').split(':')[0]; }

    /**
     * 数字14桁形式のデータバージョン文字列を人が読みやすい日時形式に整形する。
     * @param version - 表示対象のデータバージョン文字列
     * @returns バナー表示用に整形したバージョン文字列
     */
    function formatVersion(version) {
      const base = versionBase(version);
      if (base.length >= 14) {
        return `${base.slice(0,4)  }/${  base.slice(4,6)  }/${  base.slice(6,8)  } ${  base.slice(8,10)  }:${  base.slice(10,12)  } (UTC)`;
      }
      return base || '不明';
    }

    /**
     * データ更新バナーの表示/非表示を切り替える。
     * @param visible - trueならバナーを表示し、falseなら非表示にする
     */
    function setBannerVisible(visible) {
      banner.hidden = !visible;
      banner.classList.toggle('visible', visible);
    }

    /**
     * 最新バージョンが現在のバージョンと異なる場合にデータ更新バナーを表示する。
     * @param latestVersion - サーバ側で取得した最新データバージョン
     */
    function showUpdateNotice(latestVersion) {
      if (!latestVersion || latestVersion === currentDataVersion) {return;}
      meta.textContent = `表示中: ${  formatVersion(currentDataVersion)  } / 最新: ${  formatVersion(latestVersion)}`;
      setBannerVisible(true);
    }

    /**
     * データ更新バナーを非表示にする。
     */
    function hideUpdateNotice() { setBannerVisible(false); }

    /**
     * 現在ページのURLに対応するキャッシュ削除候補のURLリストを返す。
     * @returns 現在ページに対応する削除候補キャッシュキーの配列
     */
    function getCurrentPageCacheCandidates() {
      const currentUrl = new URL(window.location.href);
      currentUrl.hash = '';
      const candidates = new Set([currentUrl.toString()]);
      if (currentUrl.searchParams.get('page') === '1') {
        const withoutPage = new URL(currentUrl.toString());
        withoutPage.searchParams.delete('page');
        candidates.add(withoutPage.toString());
      }
      return Array.from(candidates);
    }

    /**
     * 現在ページに関連するすべてのキャッシュエントリを削除する。
     * @returns 現在ページに関連するキャッシュ削除が完了したかどうか
     */
    async function clearCurrentPageCaches() {
      if (!('caches' in window)) {return false;}
      const targets = getCurrentPageCacheCandidates();
      const cacheNames = await caches.keys();
      await Promise.all(cacheNames.map(async function (cacheName) {
        const cache = await caches.open(cacheName);
        await Promise.all(targets.map(async function (target) {
          await cache.delete(target);
          await cache.delete(new Request(target));
        }));
      }));
      return true;
    }

    /**
     * Service Worker経由で指定URLのキャッシュを更新する。
     * @param targetUrl - Service Worker経由で更新したいページURL
     * @returns Service Workerによる更新が成功したかどうか
     */
    async function refreshViaServiceWorker(targetUrl) {
      if (!('serviceWorker' in navigator)) {return false;}
      const registration = await navigator.serviceWorker.ready;
      const worker = (registration && (registration.active || registration.waiting || registration.installing))
        || navigator.serviceWorker.controller;
      if (!worker) {return false;}
      return new Promise(function (resolve, reject) {
        const channel = new MessageChannel();
        const timerId = window.setTimeout(function () {
          reject(new Error('service_worker_refresh_timeout'));
        }, 8000);
        channel.port1.onmessage = function (event) {
          window.clearTimeout(timerId);
          const data = event.data || {};
          if (data.ok) { resolve(true); return; }
          reject(new Error(data.error || 'service_worker_refresh_failed'));
        };
        worker.postMessage({ type: 'twicome-refresh-comments', url: targetUrl }, [channel.port2]);
      });
    }

    /**
     * Service Workerまたはキャッシュ削除を経てコメントページをリロードする。
     */
    async function refreshCommentsPage() {
      if (isRefreshing) {return;}
      isRefreshing = true;
      reloadBtn.disabled = true;
      dismissBtn.disabled = true;
      reloadBtn.textContent = '更新中...';
      const currentUrl = new URL(window.location.href);
      currentUrl.hash = '';
      try {
        const refreshed = await refreshViaServiceWorker(currentUrl.toString()).catch(function () { return false; });
        if (!refreshed) {await clearCurrentPageCaches().catch(function () {});}
      } finally {
        window.location.reload();
      }
    }

    window.TwicomeCommentsPageUpdate = { hideUpdateNotice, showUpdateNotice };

    reloadBtn.addEventListener('click', function () {
      refreshCommentsPage().catch(function () { window.location.reload(); });
    });
    dismissBtn.addEventListener('click', hideUpdateNotice);
  })();

  // -----------------------
  // エクスポート機能
  // -----------------------
  (function () {
    const exportDetails = document.getElementById('export-details');
    if (!exportDetails) {return;}

    const dvEl = document.getElementById('export-data-version');
    if (dvEl) {
      fetch(`${rootPath  }/api/meta/data-version`)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          const latestDataVersion = data.data_version || '';
          const base = latestDataVersion.split(':')[0];
          if (base && base.length >= 14) {
            dvEl.textContent = `データ更新: ${  base.slice(0,4)  }/${  base.slice(4,6)  }/${  base.slice(6,8)  } ${  base.slice(8,10)  }:${  base.slice(10,12)  } (UTC)`;
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

    /**
     * JST基準で当日または指定オフセット日数後のYYYY-MM-DD形式の日付文字列を返す。
     * @param offsetDays - 当日からの加減日数
     * @returns JST基準の `YYYY-MM-DD` 形式日付文字列
     */
    function getJSTDate(offsetDays) {
      const now = new Date(Date.now() + 9 * 60 * 60 * 1000);
      if (offsetDays) {now.setUTCDate(now.getUTCDate() + offsetDays);}
      return now.toISOString().slice(0, 10);
    }

    /**
     * 指定パラメータでエクスポートURLを構築して画面遷移する。
     * @param params - エクスポートURLに付与するクエリパラメータ
     */
    function doExport(params) {
      const url = new URL(`${location.origin + rootPath  }/u/${  encodeURIComponent(userLogin)  }/export`);
      Object.entries(params).forEach(function (kv) { if (kv[1]) {url.searchParams.set(kv[0], kv[1]);} });
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
        const from = document.getElementById('export-date-from').value;
        const to = document.getElementById('export-date-to').value;
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
