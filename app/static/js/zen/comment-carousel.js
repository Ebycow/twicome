/* zen/comment-carousel.js – コメント収集・スライドショー表示 */

/**
 * コメントカルーセルを生成する。
 * @param {object} state - 共有ミュータブル状態オブジェクト
 * @param {HTMLElement} commentEl - コメントテキスト表示要素
 * @param {HTMLElement|null} commentWrap - コメントラッパー要素（波紋演出用）
 * @returns {{collectComments: Function, showNextComment: Function, pulseCommentAura: Function}} カルーセル関数群
 */
export function createCarousel(state, commentEl, commentWrap) {
  /**
   * DOM 内のコメント本文をテキストとして収集してシャッフルして返す。
   * @returns {string[]} シャッフルされたコメントテキスト配列
   */
  function collectComments() {
    const out = [];
    document.querySelectorAll('.comment .body').forEach(function (el) {
      const clone = el.cloneNode(true);
      clone.querySelectorAll('img').forEach(function (img) {
        img.replaceWith(document.createTextNode(img.alt || ''));
      });
      const text = clone.textContent.replace(/\s+/g, ' ').trim();
      if (text.length >= 3 && text.length <= 120) {
        out.push(text);
      }
    });

    for (let i = out.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const tmp = out[i];
      out[i] = out[j];
      out[j] = tmp;
    }
    return out.length ? out : ['コメントがありません'];
  }

  /**
   * コメント表示に合わせて背景の波紋をやり直す。
   * @returns {void}
   */
  function pulseCommentAura() {
    if (!commentWrap) {
      return;
    }

    commentWrap.classList.remove('is-pulsing');
    void commentWrap.offsetWidth;
    commentWrap.classList.add('is-pulsing');
  }

  /**
   * 次のコメントをフェードイン表示し、一定時間後にフェードアウトして次へ進める。
   * @returns {void}
   */
  function showNextComment() {
    if (!state.comments.length) {
      return;
    }

    const text = state.comments[state.commentIdx % state.comments.length];
    state.commentIdx += 1;

    const isMatrix = state.currentSceneId === 'matrix-rain';

    commentEl.style.transition = 'none';
    commentEl.style.opacity = '0';
    commentEl.style.transform = isMatrix ? 'none' : 'translate3d(0, 24px, 0) scale(0.985)';
    commentEl.style.filter = isMatrix ? 'none' : 'blur(14px)';
    commentEl.textContent = text;
    if (!isMatrix) {
      pulseCommentAura();
    }
    void commentEl.offsetHeight;

    if (isMatrix) {
      commentEl.style.transition = 'opacity 0.35s ease';
      commentEl.style.opacity = '1';
    } else {
      commentEl.style.transition =
        'opacity 1.8s ease, transform 2.3s cubic-bezier(0.22, 1, 0.36, 1), filter 2.1s ease';
      commentEl.style.opacity = '1';
      commentEl.style.transform = 'translate3d(0, 0, 0) scale(1)';
      commentEl.style.filter = 'blur(0)';
    }

    state.slideTimer = setTimeout(function () {
      const stillMatrix = state.currentSceneId === 'matrix-rain';
      if (stillMatrix) {
        commentEl.style.transition = 'opacity 0.25s ease';
        commentEl.style.opacity = '0';
        state.slideTimer = setTimeout(showNextComment, 400);
      } else {
        commentEl.style.transition = 'opacity 1.4s ease, transform 1.8s ease, filter 1.8s ease';
        commentEl.style.opacity = '0';
        commentEl.style.transform = 'translate3d(0, -18px, 0) scale(1.015)';
        commentEl.style.filter = 'blur(10px)';
        state.slideTimer = setTimeout(showNextComment, 1500);
      }
    }, isMatrix ? 6500 : 5200);
  }

  return { collectComments, showNextComment, pulseCommentAura };
}
