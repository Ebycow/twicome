/* zen-mode.js – Zenモードエントリーポイント */

import { SCENES, sceneMap, VERT } from './zen/scenes.js';
import { createRenderer } from './zen/gl-renderer.js';
import { createCarousel } from './zen/comment-carousel.js';
import { createUIController } from './zen/ui-controller.js';
import { createTTSController } from './zen/tts-controller.js';

const STORAGE_KEY = 'twicome-zen-scene';
const ATTR_POSITION = 0;

/**
 * 保存済みのシーン ID を返す。
 * @returns {string} 利用可能なシーン ID
 */
function getStoredSceneId() {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && sceneMap.has(stored)) {
      return stored;
    }
  } catch (error) {
    console.warn('[ZenMode] localStorage read failed:', error);
  }
  return SCENES[0].id;
}

/**
 * 現在のシーン ID を保存する。
 * @param {string} sceneId - 保存するシーン ID
 * @returns {void}
 */
function storeSceneId(sceneId) {
  try {
    window.localStorage.setItem(STORAGE_KEY, sceneId);
  } catch (error) {
    console.warn('[ZenMode] localStorage write failed:', error);
  }
}

const overlay = document.getElementById('zen-overlay');
const canvas = document.getElementById('zen-canvas');
const commentEl = document.getElementById('zen-comment');
const commentWrap = document.getElementById('zen-comment-wrap');
const closeBtn = document.getElementById('zen-close-btn');
const fsBtn = document.getElementById('zen-fs-btn');
const ttsBtn = document.getElementById('zen-tts-btn');
const triggerBtn = document.getElementById('zen-mode-btn');
const themeSwitcher = document.getElementById('zen-theme-switcher');

/**
 * DOM 要素が揃っていれば Zen モードを初期化する。
 * @returns {void}
 */
function init() {
  if (!overlay || !canvas || !commentEl) {
    return;
  }

  const state = {
    gl: null,
    quadBuffer: null,
    glReady: false,
    raf: null,
    sceneStartTime: null,
    scenePrograms: new Map(),
    currentSceneState: null,
    currentSceneId: getStoredSceneId(),
    comments: [],
    commentIdx: 0,
    slideTimer: null,
    lunarPhase: 0
  };

  const tts = createTTSController();
  const renderer = createRenderer(state, canvas, overlay, VERT, ATTR_POSITION);
  const carousel = createCarousel(state, commentEl, commentWrap, tts);
  const dom = { overlay, canvas, commentEl, commentWrap, themeSwitcher, fsBtn, tts };
  const ui = createUIController(
    state, dom, { SCENES, sceneMap }, renderer, carousel, storeSceneId, ATTR_POSITION
  );

  ui.renderThemeButtons();
  overlay.dataset.zenScene = state.currentSceneId;
  ui.updateThemeButtons();
  ui.updateFsIcon();

  if (triggerBtn) {
    triggerBtn.addEventListener('click', ui.openZen);
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', ui.closeZen);
  }
  if (fsBtn) {
    fsBtn.addEventListener('click', ui.toggleFullscreen);
  }
  if (ttsBtn) {
    if (!tts.isSupported()) {
      ttsBtn.hidden = true;
    } else {
      ttsBtn.addEventListener('click', function () {
        const nowEnabled = tts.toggle();
        ttsBtn.setAttribute('aria-pressed', nowEnabled ? 'true' : 'false');
        ttsBtn.title = nowEnabled ? '読み上げをオフ' : '読み上げをオン';
        ttsBtn.setAttribute('aria-label', nowEnabled ? '読み上げをオフ' : '読み上げをオン');
        ttsBtn.innerHTML = nowEnabled
          ? '<i class="fa-solid fa-volume-high"></i>'
          : '<i class="fa-solid fa-volume-xmark"></i>';
      });
    }
  }
  if (commentWrap) {
    commentWrap.addEventListener('animationend', function (event) {
      if (event.animationName === 'zen-comment-ripple') {
        commentWrap.classList.remove('is-pulsing');
      }
    });
  }

  document.addEventListener('keydown', function (event) {
    if (overlay.hidden) {
      return;
    }

    if ((event.key === 'Escape' || event.key === 'Esc') && !document.fullscreenElement) {
      ui.closeZen();
      return;
    }
    if (event.key === 'ArrowRight') {
      ui.selectAdjacentScene(1);
      return;
    }
    if (event.key === 'ArrowLeft') {
      ui.selectAdjacentScene(-1);
    }
  });

  document.addEventListener('fullscreenchange', ui.updateFsIcon);
}

init();
