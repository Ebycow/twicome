(function () {
  'use strict';

  const cfgEl = document.getElementById('quiz-data');
  if (!cfgEl) {return;}
  const cfg = JSON.parse(cfgEl.textContent);
  const normalizedRootPath = (typeof cfg.root_path === 'string') ? cfg.root_path.trim() : '';
  const rootPath = (normalizedRootPath && normalizedRootPath !== '/') ? normalizedRootPath.replace(/\/+$/, '') : '';
  const displayName = cfg.display_name;

  // markVisited
  if (window.TwicomeOfflineAccess) {
    window.TwicomeOfflineAccess.markVisited(rootPath, 'quiz', cfg.login);
  }

  // DOM
  const startScreen = document.getElementById('start-screen');
  const gameScreen = document.getElementById('game-screen');
  const gameoverScreen = document.getElementById('gameover-screen');
  const startBtn = document.getElementById('start-btn');
  const retryBtn = document.getElementById('retry-btn');
  const btnTarget = document.getElementById('btn-target');
  const btnOther = document.getElementById('btn-other');
  const scoreEl = document.getElementById('score-value');
  const streakEl = document.getElementById('streak-value');
  const progressEl = document.getElementById('progress-value');
  const totalEl = document.getElementById('total-value');
  const questionCard = document.getElementById('question-card');
  const commentBody = document.getElementById('comment-body');
  const vodContext = document.getElementById('vod-context');
  const questionNumber = document.getElementById('question-number');
  const resultOverlay = document.getElementById('result-overlay');
  const livesContainer = document.getElementById('lives');

  if (!startBtn) {return;}

  btnTarget.textContent = `${displayName  } の発言`;

  // State
  let questions = [];
  let idx = 0;
  let score = 0;
  let lives = 3;
  let streak = 0;
  let bestStreak = 0;
  let totalCorrect = 0;
  let totalWrong = 0;
  let answering = false;

  /**
   * 文字列内のHTML特殊文字をエスケープする。
   * @param s - エスケープ対象の文字列
   * @returns HTMLエスケープされた文字列
   */
  function escapeHtml(s) {
    if (s == null) {return '';}
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  /**
   * body_html を安全な DOM ノードとして el に追加する。
   * 許可: テキストノード・<img class="emote" src="https://static-cdn.jtvnw.net/...">
   * それ以外のタグはすべて除去する。
   * @param {HTMLElement} el - 追加先の要素
   * @param {string} bodyHtml - サーバーから受け取った body_html
   */
  function appendSafeBodyHtml(el, bodyHtml) {
    const template = document.createElement('template');
    template.innerHTML = bodyHtml;
    const frag = document.createDocumentFragment();
    template.content.childNodes.forEach(function (node) {
      if (node.nodeType === Node.TEXT_NODE) {
        frag.appendChild(document.createTextNode(node.textContent));
      } else if (node.nodeName === 'IMG') {
        const src = node.getAttribute('src') || '';
        if (!src.startsWith('https://static-cdn.jtvnw.net/')) { return; }
        const img = document.createElement('img');
        ['class', 'src', 'srcset', 'alt', 'title', 'loading', 'decoding'].forEach(function (attr) {
          if (node.hasAttribute(attr)) { img.setAttribute(attr, node.getAttribute(attr)); }
        });
        if (img.getAttribute('class') !== 'emote') { img.removeAttribute('class'); }
        frag.appendChild(img);
      }
    });
    el.appendChild(frag);
  }

  /**
   * ライフ表示のハートをリセットして初期状態（3個）に戻す。
   */
  function resetHearts() {
    livesContainer.innerHTML = '';
    for (let i = 0; i < 3; i++) {
      const span = document.createElement('span');
      span.className = 'heart';
      span.innerHTML = '<i class="fa-solid fa-heart"></i>';
      livesContainer.appendChild(span);
    }
  }

  /**
   * 正解時に画面全体にコンフェティアニメーションを生成する。
   */
  function spawnConfetti() {
    const colors = ['#f44336','#ff9800','#ffeb3b','#4caf50','#2196f3','#9c27b0','#e91e63'];
    const shapes = ['circle','square','strip'];
    for (let i = 0; i < 24; i++) {
      const el = document.createElement('div');
      const shape = shapes[Math.floor(Math.random()*shapes.length)];
      el.className = `confetti ${  shape}`;
      el.style.background = colors[Math.floor(Math.random()*colors.length)];
      el.style.left = `${Math.random()*100  }vw`;
      el.style.top = `${20 + Math.random()*30  }vh`;
      el.style.opacity = '1';
      document.body.appendChild(el);
      animateConfetti(el);
    }
  }

  /**
   * 1つのコンフェティ要素にフォールアニメーションを適用して終了後に削除する。
   * @param el - アニメーションさせるコンフェティ要素
   */
  function animateConfetti(el) {
    const drift = (Math.random()-0.5)*200;
    const duration = 900 + Math.random()*700;
    const delay = Math.random()*200;
    let startTime = null;

    setTimeout(function () {
      startTime = performance.now();
      requestAnimationFrame(function step(ts) {
        const elapsed = ts - startTime;
        const t = Math.min(elapsed / duration, 1);
        const ease = t < 0.5 ? 2*t*t : 1-Math.pow(-2*t+2,2)/2;
        el.style.transform = `translateY(${  ease*350  }px) translateX(${  drift*t  }px) rotate(${  t*720  }deg)`;
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

  /**
   * ゲームの状態をリセットしてAPIからクイズ問題を取得しゲームを開始する。
   */
  function startGame() {
    idx = 0; score = 0; lives = 3; streak = 0; bestStreak = 0;
    totalCorrect = 0; totalWrong = 0; answering = false;

    startBtn.disabled = true;
    retryBtn.disabled = true;
    startBtn.textContent = '読み込み中...';

    fetch(`${rootPath  }/api/u/${  encodeURIComponent(cfg.login)  }/quiz/start?platform=${  encodeURIComponent(cfg.platform)  }&count=30`, {
      headers: {'X-Requested-With': 'XMLHttpRequest'}
    })
    .then(function (r) {
      if (!r.ok) {throw new Error('API error');}
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

  /**
   * 現在のインデックスの問題を画面に表示する。ゲームオーバー条件を満たす場合は終了画面へ遷移する。
   */
  function showQuestion() {
    if (idx >= questions.length || lives <= 0) {
      showGameOver();
      return;
    }
    const q = questions[idx];
    progressEl.textContent = String(idx + 1);
    questionNumber.textContent = `Q${  idx + 1}`;
    questionCard.className = 'question-card';
    void questionCard.offsetWidth;
    questionCard.classList.add('slide-in');
    commentBody.textContent = '';
    if (q.body_html) {
      appendSafeBodyHtml(commentBody, q.body_html);
    } else {
      commentBody.textContent = q.body;
    }
    vodContext.textContent = q.vod_title ? `配信: ${  escapeHtml(q.vod_title)}` : '';
    btnTarget.disabled = false;
    btnOther.disabled = false;
    answering = false;
    resultOverlay.style.display = 'none';
  }

  btnTarget.addEventListener('click', function () { handleAnswer(true); });
  btnOther.addEventListener('click', function () { handleAnswer(false); });

  /**
   * ユーザの回答を受け取り正誤判定を行い結果オーバーレイを表示して次の問題へ進む。
   * @param guessedTarget - trueなら「この配信者の発言」と回答、falseなら「他の人の発言」と回答
   */
  function handleAnswer(guessedTarget) {
    if (answering) {return;}
    answering = true;
    btnTarget.disabled = true;
    btnOther.disabled = true;
    const q = questions[idx];
    const isCorrect = (guessedTarget === q.is_target);
    if (isCorrect) { onCorrect(q); } else { onWrong(q); }
    const overlayClass = `result-overlay ${  isCorrect ? 'correct' : 'wrong'}`;
    resultOverlay.className = overlayClass;
    resultOverlay.style.display = 'block';
    resultOverlay.innerHTML =
      `<div class="result-text" style="color:var(--${  isCorrect ? 'correct' : 'wrong'  }-color);">${ 
      isCorrect ? '正解!' : '不正解...'  }</div>` +
      `<div class="result-commenter">投稿者: ${  escapeHtml(q.actual_commenter_display_name)  }</div>`;
    setTimeout(function () { idx++; showQuestion(); }, 1400);
  }

  /**
   * 正解時のスコア・ストリークを更新しUIにフィードバックを反映する。
   * @param q - 正解した問題オブジェクト
   */
  function onCorrect(q) {
    score++; totalCorrect++; streak++;
    if (streak > bestStreak) {bestStreak = streak;}
    scoreEl.textContent = String(score);
    scoreEl.classList.remove('pop');
    void scoreEl.offsetWidth;
    scoreEl.classList.add('pop');
    streakEl.textContent = String(streak);
    questionCard.className = 'question-card correct-flash';
    spawnConfetti();
  }

  /**
   * 不正解時にライフを減らしストリークをリセットしUIに反映する。
   * @param q - 不正解だった問題オブジェクト
   */
  function onWrong(q) {
    totalWrong++; lives--; streak = 0;
    streakEl.textContent = '0';
    questionCard.className = 'question-card wrong-shake';
    const hearts = livesContainer.querySelectorAll('.heart:not(.lost)');
    if (hearts.length > 0) {hearts[hearts.length - 1].classList.add('lost');}
  }

  /**
   * ゲームオーバー画面を表示し最終スコアや統計をアニメーション付きで描画する。
   */
  function showGameOver() {
    gameScreen.style.display = 'none';
    gameoverScreen.style.display = 'block';
    const answered = totalCorrect + totalWrong;
    const accuracy = answered > 0 ? Math.round((totalCorrect / answered) * 100) : 0;
    let sub = '';
    if (score >= 20) {sub = `${displayName  } の専門家ですね!`;}
    else if (score >= 10) {sub = 'なかなかの実力です!';}
    else if (score >= 5) {sub = 'まだまだこれから!';}
    else {sub = `もっと ${  displayName  } のコメントを読もう!`;}
    document.getElementById('gameover-sub').textContent = sub;
    animateCountUp(document.getElementById('final-score'), score, 600);
    document.getElementById('stat-correct').textContent = String(totalCorrect);
    document.getElementById('stat-wrong').textContent = String(totalWrong);
    document.getElementById('stat-accuracy').textContent = `${accuracy  }%`;
    document.getElementById('stat-best-streak').textContent = String(bestStreak);
    if (score >= 10) {spawnConfetti();}
  }

  /**
   * 指定DOM要素の数値を0から目標値までイージングアニメーションでカウントアップする。
   * @param el - 数値を表示するDOM要素
   * @param target - カウントアップの目標値
   * @param duration - アニメーション時間（ミリ秒）
   */
  function animateCountUp(el, target, duration) {
    const start = performance.now();
    el.textContent = '0';
    if (target === 0) {return;}
    requestAnimationFrame(function step(ts) {
      const t = Math.min((ts - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      el.textContent = String(Math.round(ease * target));
      if (t < 1) {requestAnimationFrame(step);}
    });
  }
})();
