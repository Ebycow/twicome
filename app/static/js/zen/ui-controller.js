/* zen/ui-controller.js – シーン切替・ボタン・モーダル開閉・フルスクリーン */

/**
 * UI コントローラーを生成する。
 * @param {object} state - 共有ミュータブル状態オブジェクト
 * @param {{overlay: HTMLElement, canvas: HTMLCanvasElement, commentEl: HTMLElement, commentWrap: HTMLElement|null, themeSwitcher: HTMLElement|null, fsBtn: HTMLElement|null}} dom - DOM 要素群
 * @param {{SCENES: Array, sceneMap: Map}} scenesData - シーン定義データ
 * @param {{initGL: Function, resizeCanvas: Function, buildSceneProgram: Function, render: Function}} renderer - レンダラー関数群
 * @param {{collectComments: Function, showNextComment: Function}} carousel - カルーセル関数群
 * @param {Function} storeSceneId - シーン ID 保存関数
 * @param {number} attrPosition - 位置属性のバインドインデックス
 * @returns {{renderThemeButtons: Function, updateThemeButtons: Function, selectAdjacentScene: Function, applyScene: Function, openZen: Function, closeZen: Function, toggleFullscreen: Function, updateFsIcon: Function}} UI 関数群
 */
export function createUIController(state, dom, scenesData, renderer, carousel, storeSceneId, attrPosition) {
  const { SCENES, sceneMap } = scenesData;

  /**
   * シーン切り替えボタンを描画する。
   * @returns {void}
   */
  function renderThemeButtons() {
    if (!dom.themeSwitcher) {
      return;
    }

    dom.themeSwitcher.textContent = '';
    SCENES.forEach(function (scene) {
      const button = document.createElement('button');
      const buttonLabel = `${scene.label}に切り替え`;
      button.type = 'button';
      button.className = 'zen-theme-btn';
      button.dataset.sceneId = scene.id;
      button.title = buttonLabel;
      button.setAttribute('aria-label', buttonLabel);
      button.setAttribute('aria-pressed', scene.id === state.currentSceneId ? 'true' : 'false');
      button.innerHTML = `<span class="zen-theme-emoji" aria-hidden="true">${scene.emoji}</span>`;
      button.addEventListener('click', function () {
        applyScene(scene.id);
      });
      dom.themeSwitcher.appendChild(button);
    });
  }

  /**
   * 現在選択中のシーンに合わせてボタン状態を更新する。
   * @returns {void}
   */
  function updateThemeButtons() {
    if (!dom.themeSwitcher) {
      return;
    }

    dom.themeSwitcher.querySelectorAll('.zen-theme-btn').forEach(function (button) {
      const isActive = button.dataset.sceneId === state.currentSceneId;
      button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }

  /**
   * フルスクリーン状態に応じてボタン表示を更新する。
   * @returns {void}
   */
  function updateFsIcon() {
    if (!dom.fsBtn) {
      return;
    }

    if (document.fullscreenElement) {
      dom.fsBtn.innerHTML = '<i class="fa-solid fa-compress"></i>';
      dom.fsBtn.title = '全画面を終了';
      dom.fsBtn.setAttribute('aria-label', '全画面を終了');
      return;
    }

    dom.fsBtn.innerHTML = '<i class="fa-solid fa-expand"></i>';
    dom.fsBtn.title = 'フルスクリーン';
    dom.fsBtn.setAttribute('aria-label', 'フルスクリーン');
  }

  /**
   * シーンを切り替えて、必要なら GL プログラムも差し替える。
   * @param {string} sceneId - 切り替え先のシーン ID
   * @returns {void}
   */
  function applyScene(sceneId) {
    const nextScene = sceneMap.get(sceneId) || SCENES[0];
    state.currentSceneId = nextScene.id;
    dom.overlay.dataset.zenScene = state.currentSceneId;
    storeSceneId(state.currentSceneId);
    updateThemeButtons();

    if (!state.glReady) {
      return;
    }

    const programEntry = renderer.buildSceneProgram(nextScene);
    if (!programEntry) {
      if (nextScene.id !== SCENES[0].id) {
        applyScene(SCENES[0].id);
        return;
      }

      dom.canvas.style.display = 'none';
      state.currentSceneState = null;
      return;
    }

    const gl = state.gl;
    dom.canvas.style.display = 'block';
    gl.useProgram(programEntry.program);
    gl.bindBuffer(gl.ARRAY_BUFFER, state.quadBuffer);
    gl.enableVertexAttribArray(attrPosition);
    gl.vertexAttribPointer(attrPosition, 2, gl.FLOAT, false, 0, 0);
    state.currentSceneState = { scene: nextScene, programEntry };
    state.sceneStartTime = null;
  }

  /**
   * 隣のシーンへ切り替える。
   * @param {number} step - 前後方向。1 で次、-1 で前
   * @returns {void}
   */
  function selectAdjacentScene(step) {
    if (SCENES.length < 2) {
      return;
    }

    const currentIndex = SCENES.findIndex(function (scene) {
      return scene.id === state.currentSceneId;
    });
    const nextIndex = (currentIndex + step + SCENES.length) % SCENES.length;
    applyScene(SCENES[nextIndex].id);
  }

  /**
   * Zen モードを開く。
   * @returns {void}
   */
  function openZen() {
    state.comments = carousel.collectComments();
    state.commentIdx = 0;
    if (state.slideTimer) {
      clearTimeout(state.slideTimer);
      state.slideTimer = null;
    }

    dom.overlay.hidden = false;
    dom.overlay.dataset.zenScene = state.currentSceneId;
    document.body.style.overflow = 'hidden';
    if (dom.commentWrap) {
      dom.commentWrap.classList.remove('is-pulsing');
    }

    if (renderer.initGL()) {
      renderer.resizeCanvas();
      applyScene(state.currentSceneId);
    } else {
      dom.canvas.style.display = 'none';
    }

    if (state.raf === null) {
      state.raf = requestAnimationFrame(renderer.render);
    }
    carousel.showNextComment();
    updateFsIcon();

    if (!document.getElementById('zen-serif-font')) {
      const link = document.createElement('link');
      link.id = 'zen-serif-font';
      link.rel = 'stylesheet';
      link.href = 'https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@300;400&display=swap';
      document.head.appendChild(link);
    }
  }

  /**
   * Zen モードを閉じる。
   * @returns {void}
   */
  function closeZen() {
    if (state.raf !== null) {
      cancelAnimationFrame(state.raf);
      state.raf = null;
    }
    if (state.slideTimer) {
      clearTimeout(state.slideTimer);
      state.slideTimer = null;
    }

    dom.overlay.hidden = true;
    document.body.style.overflow = '';
    dom.commentEl.style.opacity = '0';
    dom.commentEl.style.transform = 'translate3d(0, 18px, 0) scale(0.985)';
    dom.commentEl.style.filter = 'blur(12px)';
    if (dom.commentWrap) {
      dom.commentWrap.classList.remove('is-pulsing');
    }
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(function () {});
    }
  }

  /**
   * フルスクリーン表示を切り替える。
   * @returns {void}
   */
  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      if (dom.overlay.requestFullscreen) {
        dom.overlay.requestFullscreen().catch(function () {});
      }
      return;
    }
    document.exitFullscreen().catch(function () {});
  }

  return {
    renderThemeButtons,
    updateThemeButtons,
    selectAdjacentScene,
    applyScene,
    openZen,
    closeZen,
    toggleFullscreen,
    updateFsIcon
  };
}
