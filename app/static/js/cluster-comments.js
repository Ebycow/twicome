(function () {
  var rawRootPath = JSON.parse(document.getElementById('root-path-data').textContent);
  var rootPath = (typeof rawRootPath === 'string' && rawRootPath && rawRootPath !== '/') ? rawRootPath.replace(/\/+$/, '') : '';
  var voteCountsApiUrl = rootPath + '/api/comments/votes';

  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
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
      var newPending = {
        count: 1,
        button: button,
        commentId: commentId,
        type: type,
        timer: setTimeout(function () { flushVote(key); }, VOTE_DEBOUNCE_MS)
      };
      votePending.set(key, newPending);
    }
  }

  async function flushVote(key) {
    var pending = votePending.get(key);
    if (!pending) return;
    votePending.delete(key);
    var commentId = pending.commentId, type = pending.type, count = pending.count;
    var url = rootPath + '/' + type + '/' + commentId + '?count=' + count;
    try {
      var response = await fetch(url, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      if (!response.ok) console.error('Vote failed:', await response.text());
    } catch (error) {
      console.error('Network error:', error);
    }
  }

  function setVoteControls(container, commentId, likesCount, dislikesCount) {
    if (!container) return;
    var safeId = escapeHtml(commentId);
    container.innerHTML =
      '<button onclick="vote(this, \'' + safeId + '\', \'like\')" class="vote-btn" data-count="' + likesCount + '">😂 ' + likesCount + '</button>' +
      '<button onclick="vote(this, \'' + safeId + '\', \'dislike\')" class="vote-btn" data-count="' + dislikesCount + '">❓ ' + dislikesCount + '</button>';
  }

  async function hydrateDeferredVoteControls(containers) {
    var targets = (containers || []).filter(function (c) { return c && c.dataset.commentId; });
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
      console.warn('Deferred vote hydration failed:', error);
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

  // vote must be global for onclick attributes in HTML
  window.vote = vote;

  var containers = Array.from(document.querySelectorAll('[data-vote-controls="deferred"]'));
  if (containers.length) {
    var run = function () { void hydrateDeferredVoteControls(containers); };
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(run, { timeout: 1800 });
    } else {
      window.setTimeout(run, 350);
    }
  }
})();
