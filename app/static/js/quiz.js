(function () {
  'use strict';

  var cfgEl = document.getElementById('quiz-data');
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent);
  var normalizedRootPath = (typeof cfg.root_path === 'string') ? cfg.root_path.trim() : '';
  var rootPath = (normalizedRootPath && normalizedRootPath !== '/') ? normalizedRootPath.replace(/\/+$/, '') : '';
  var displayName = cfg.display_name;

  // markVisited
  if (window.TwicomeOfflineAccess) {
    window.TwicomeOfflineAccess.markVisited(rootPath, 'quiz', cfg.login);
  }

  // DOM
  var startScreen = document.getElementById('start-screen');
  var gameScreen = document.getElementById('game-screen');
  var gameoverScreen = document.getElementById('gameover-screen');
  var startBtn = document.getElementById('start-btn');
  var retryBtn = document.getElementById('retry-btn');
  var btnTarget = document.getElementById('btn-target');
  var btnOther = document.getElementById('btn-other');
  var scoreEl = document.getElementById('score-value');
  var streakEl = document.getElementById('streak-value');
  var progressEl = document.getElementById('progress-value');
  var totalEl = document.getElementById('total-value');
  var questionCard = document.getElementById('question-card');
  var commentBody = document.getElementById('comment-body');
  var vodContext = document.getElementById('vod-context');
  var questionNumber = document.getElementById('question-number');
  var resultOverlay = document.getElementById('result-overlay');
  var livesContainer = document.getElementById('lives');

  if (!startBtn) return;

  btnTarget.textContent = displayName + ' の発言';

  // State
  var questions = [];
  var idx = 0;
  var score = 0;
  var lives = 3;
  var streak = 0;
  var bestStreak = 0;
  var totalCorrect = 0;
  var totalWrong = 0;
  var answering = false;

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function resetHearts() {
    livesContainer.innerHTML = '';
    for (var i = 0; i < 3; i++) {
      var span = document.createElement('span');
      span.className = 'heart';
      span.innerHTML = '&#x2764;&#xFE0F;';
      livesContainer.appendChild(span);
    }
  }

  function spawnConfetti() {
    var colors = ['#f44336','#ff9800','#ffeb3b','#4caf50','#2196f3','#9c27b0','#e91e63'];
    var shapes = ['circle','square','strip'];
    for (var i = 0; i < 24; i++) {
      var el = document.createElement('div');
      var shape = shapes[Math.floor(Math.random()*shapes.length)];
      el.className = 'confetti ' + shape;
      el.style.background = colors[Math.floor(Math.random()*colors.length)];
      el.style.left = (Math.random()*100) + 'vw';
      el.style.top = (20 + Math.random()*30) + 'vh';
      el.style.opacity = '1';
      document.body.appendChild(el);
      animateConfetti(el);
    }
  }

  function animateConfetti(el) {
    var drift = (Math.random()-0.5)*200;
    var duration = 900 + Math.random()*700;
    var delay = Math.random()*200;
    var startTime = null;

    setTimeout(function () {
      startTime = performance.now();
      requestAnimationFrame(function step(ts) {
        var elapsed = ts - startTime;
        var t = Math.min(elapsed / duration, 1);
        var ease = t < 0.5 ? 2*t*t : 1-Math.pow(-2*t+2,2)/2;
        el.style.transform = 'translateY(' + (ease*350) + 'px) translateX(' + (drift*t) + 'px) rotate(' + (t*720) + 'deg)';
        el.style.opacity = String(1-t);
        if (t < 1) {
          requestAnimationFrame(step);
        } else {
          el.remove();
        }
      });
    }, delay);
  }

  startBtn.addEventListener('click', startGame);
  retryBtn.addEventListener('click', startGame);

  function startGame() {
    idx = 0; score = 0; lives = 3; streak = 0; bestStreak = 0;
    totalCorrect = 0; totalWrong = 0; answering = false;

    startBtn.disabled = true;
    retryBtn.disabled = true;
    startBtn.textContent = '読み込み中...';

    fetch(rootPath + '/api/u/' + encodeURIComponent(cfg.login) + '/quiz/start?platform=' + encodeURIComponent(cfg.platform) + '&count=30', {
      headers: {'X-Requested-With': 'XMLHttpRequest'}
    })
    .then(function (r) {
      if (!r.ok) throw new Error('API error');
      return r.json();
    })
    .then(function (data) {
      questions = data.questions;
      if (questions.length === 0) {
        alert('コメントが少なすぎてクイズを生成できませんでした。');
        return;
      }
      startScreen.style.display = 'none';
      gameoverScreen.style.display = 'none';
      gameScreen.style.display = 'block';
      resetHearts();
      scoreEl.textContent = '0';
      streakEl.textContent = '0';
      totalEl.textContent = String(questions.length);
      resultOverlay.style.display = 'none';
      showQuestion();
    })
    .catch(function (err) {
      console.error(err);
      alert('クイズの読み込みに失敗しました。');
    })
    .finally(function () {
      startBtn.disabled = false;
      retryBtn.disabled = false;
      startBtn.textContent = 'スタート';
    });
  }

  function showQuestion() {
    if (idx >= questions.length || lives <= 0) {
      showGameOver();
      return;
    }
    var q = questions[idx];
    progressEl.textContent = String(idx + 1);
    questionNumber.textContent = 'Q' + (idx + 1);
    questionCard.className = 'question-card';
    void questionCard.offsetWidth;
    questionCard.classList.add('slide-in');
    if (q.body_html) {
      commentBody.innerHTML = q.body_html;
    } else {
      commentBody.textContent = q.body;
    }
    vodContext.textContent = q.vod_title ? '配信: ' + escapeHtml(q.vod_title) : '';
    btnTarget.disabled = false;
    btnOther.disabled = false;
    answering = false;
    resultOverlay.style.display = 'none';
  }

  btnTarget.addEventListener('click', function () { handleAnswer(true); });
  btnOther.addEventListener('click', function () { handleAnswer(false); });

  function handleAnswer(guessedTarget) {
    if (answering) return;
    answering = true;
    btnTarget.disabled = true;
    btnOther.disabled = true;
    var q = questions[idx];
    var isCorrect = (guessedTarget === q.is_target);
    if (isCorrect) { onCorrect(q); } else { onWrong(q); }
    var overlayClass = 'result-overlay ' + (isCorrect ? 'correct' : 'wrong');
    resultOverlay.className = overlayClass;
    resultOverlay.style.display = 'block';
    resultOverlay.innerHTML =
      '<div class="result-text" style="color:var(--' + (isCorrect ? 'correct' : 'wrong') + '-color);">' +
      (isCorrect ? '正解!' : '不正解...') + '</div>' +
      '<div class="result-commenter">投稿者: ' + escapeHtml(q.actual_commenter_display_name) + '</div>';
    setTimeout(function () { idx++; showQuestion(); }, 1400);
  }

  function onCorrect(q) {
    score++; totalCorrect++; streak++;
    if (streak > bestStreak) bestStreak = streak;
    scoreEl.textContent = String(score);
    scoreEl.classList.remove('pop');
    void scoreEl.offsetWidth;
    scoreEl.classList.add('pop');
    streakEl.textContent = String(streak);
    questionCard.className = 'question-card correct-flash';
    spawnConfetti();
  }

  function onWrong(q) {
    totalWrong++; lives--; streak = 0;
    streakEl.textContent = '0';
    questionCard.className = 'question-card wrong-shake';
    var hearts = livesContainer.querySelectorAll('.heart:not(.lost)');
    if (hearts.length > 0) hearts[hearts.length - 1].classList.add('lost');
  }

  function showGameOver() {
    gameScreen.style.display = 'none';
    gameoverScreen.style.display = 'block';
    var answered = totalCorrect + totalWrong;
    var accuracy = answered > 0 ? Math.round((totalCorrect / answered) * 100) : 0;
    var sub = '';
    if (score >= 20) sub = displayName + ' の専門家ですね!';
    else if (score >= 10) sub = 'なかなかの実力です!';
    else if (score >= 5) sub = 'まだまだこれから!';
    else sub = 'もっと ' + displayName + ' のコメントを読もう!';
    document.getElementById('gameover-sub').textContent = sub;
    animateCountUp(document.getElementById('final-score'), score, 600);
    document.getElementById('stat-correct').textContent = String(totalCorrect);
    document.getElementById('stat-wrong').textContent = String(totalWrong);
    document.getElementById('stat-accuracy').textContent = accuracy + '%';
    document.getElementById('stat-best-streak').textContent = String(bestStreak);
    if (score >= 10) spawnConfetti();
  }

  function animateCountUp(el, target, duration) {
    var start = performance.now();
    el.textContent = '0';
    if (target === 0) return;
    requestAnimationFrame(function step(ts) {
      var t = Math.min((ts - start) / duration, 1);
      var ease = 1 - Math.pow(1 - t, 3);
      el.textContent = String(Math.round(ease * target));
      if (t < 1) requestAnimationFrame(step);
    });
  }
})();
