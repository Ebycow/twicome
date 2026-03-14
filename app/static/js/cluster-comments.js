(function () {
  const rawRootPath = JSON.parse(document.getElementById('root-path-data').textContent);
  const rootPath = (typeof rawRootPath === 'string' && rawRootPath && rawRootPath !== '/') ? rawRootPath.replace(/\/+$/, '') : '';
  const voteCountsApiUrl = `${rootPath  }/api/comments/votes`;

  /**
   * @param str - エスケープ対象の文字列
   * @returns HTMLエスケープされた文字列
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
   * @param button - コンフェティの発生起点となるボタン要素
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
   * @param button - クリックされた投票ボタン要素
   * @param commentId - 投票対象のコメントID
   * @param type - 投票種別（'like' または 'dislike'）
   */
  function vote(button, commentId, type) {
    spawnConfetti(button);
    const key = `${commentId  }-${  type}`;
    const currentCount = parseInt(button.dataset.count || '0', 10) + 1;
    button.dataset.count = currentCount;
    button.textContent = (type === 'like' ? '😂 ' : '❓️ ') + currentCount;
    if (votePending.has(key)) {
      const pending = votePending.get(key);
      pending.count++;
      clearTimeout(pending.timer);
      pending.timer = setTimeout(function () { flushVote(key); }, VOTE_DEBOUNCE_MS);
    } else {
      const newPending = {
        count: 1,
        button,
        commentId,
        type,
        timer: setTimeout(function () { flushVote(key); }, VOTE_DEBOUNCE_MS)
      };
      votePending.set(key, newPending);
    }
  }

  /**
   * @param key - 投票キー（`{commentId}-{type}` 形式）
   */
  async function flushVote(key) {
    const pending = votePending.get(key);
    if (!pending) {return;}
    votePending.delete(key);
    const commentId = pending.commentId, type = pending.type, count = pending.count;
    const url = `${rootPath  }/${  type  }/${  commentId  }?count=${  count}`;
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      if (!response.ok) {console.error('Vote failed:', await response.text());}
    } catch (error) {
      console.error('Network error:', error);
    }
  }

  /**
   * @param container - 投票ボタンを挿入するコンテナ要素
   * @param commentId - コメントID
   * @param likesCount - 現在のいいね数
   * @param dislikesCount - 現在の？数
   */
  function setVoteControls(container, commentId, likesCount, dislikesCount) {
    if (!container) {return;}
    const safeId = escapeHtml(commentId);
    container.innerHTML =
      `<button onclick="vote(this, '${  safeId  }', 'like')" class="vote-btn" data-count="${  likesCount  }">😂 ${  likesCount  }</button>` +
      `<button onclick="vote(this, '${  safeId  }', 'dislike')" class="vote-btn" data-count="${  dislikesCount  }">❓ ${  dislikesCount  }</button>`;
  }

  /**
   * @param containers - 遅延ハイドレーション対象のコンテナ要素の配列
   */
  async function hydrateDeferredVoteControls(containers) {
    const targets = (containers || []).filter(function (c) { return c && c.dataset.commentId; });
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
      console.warn('Deferred vote hydration failed:', error);
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

  // vote must be global for onclick attributes in HTML
  window.vote = vote;

  const containers = Array.from(document.querySelectorAll('[data-vote-controls="deferred"]'));
  if (containers.length) {
    const run = function () { void hydrateDeferredVoteControls(containers); };
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(run, { timeout: 1800 });
    } else {
      window.setTimeout(run, 350);
    }
  }
})();
