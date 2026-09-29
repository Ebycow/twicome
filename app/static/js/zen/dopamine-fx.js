/* zen/dopamine-fx.js – ドーパミンモード: ガチャ召喚演出・パーティクル・サバイバー風 HUD */

export const DOPAMINE_SCENE_ID = 'dopamine';

const RARITIES = [
  { rank: 'N', stars: 1, weight: 42, color: '#a9bcd9' },
  { rank: 'R', stars: 2, weight: 30, color: '#3cc8ff' },
  { rank: 'SR', stars: 3, weight: 17, color: '#c46bff' },
  { rank: 'SSR', stars: 4, weight: 8, color: '#ffd23f' },
  { rank: 'UR', stars: 5, weight: 3, color: '#ff5ce1' }
];
const SSR_TIER = 3;
const PITY_LIMIT = 10;
const SUMMON_MS = [1300, 1500, 1900, 2400, 3000];
const CAPTIONS = [null, null, 'チャンス!', '激アツ!!', '虹確定!!!'];
const GEM_COUNTS = [6, 10, 16, 26, 40];
const GOLD_REWARD = [5, 15, 40, 120, 777];
const DAMAGE_BASE = [12, 48, 180, 777, 9999];
const GEM_TYPES = [
  { color: '#4fd2ff', xp: 1, weight: 70 },
  { color: '#6dff8e', xp: 2, weight: 24 },
  { color: '#ff5a6e', xp: 5, weight: 6 }
];
const MAX_PARTICLES = 900;
const XP_BAR_Y = 8;

/**
 * 重み付き抽選でインデックスを返す。
 * @param {Array<{weight: number}>} items - 重みを持つ候補
 * @param {number} [from] - 抽選対象にする先頭インデックス
 * @returns {number} 当選したインデックス
 */
function pickWeighted(items, from) {
  const start = from || 0;
  let total = 0;
  for (let i = start; i < items.length; i++) {
    total += items[i].weight;
  }
  let roll = Math.random() * total;
  for (let i = start; i < items.length; i++) {
    roll -= items[i].weight;
    if (roll < 0) {
      return i;
    }
  }
  return items.length - 1;
}

/**
 * 範囲内の乱数を返す。
 * @param {number} min - 最小値
 * @param {number} max - 最大値
 * @returns {number} min 以上 max 未満の乱数
 */
function rand(min, max) {
  return min + Math.random() * (max - min);
}

/**
 * CSS アニメーションを最初から再生し直すためにクラスを付け直す。
 * @param {Element} el - 対象要素
 * @param {string} cls - 付け直すクラス名
 * @returns {void}
 */
function restartClass(el, cls) {
  el.classList.remove(cls);
  void el.getBoundingClientRect();
  el.classList.add(cls);
}

/**
 * ドーパミンモードの演出コントローラーを生成する。
 * @param {object} state - 共有ミュータブル状態オブジェクト（fxUniforms をシェーダーへ渡す）
 * @param {{overlay: HTMLElement, commentEl: HTMLElement, commentWrap: HTMLElement|null}} dom - DOM 要素群
 * @param {{charge: Function, promote: Function, burst: Function, pickup: Function, levelUp: Function, stopAll: Function}} sfx - 効果音コントローラー
 * @returns {{sceneId: string, isActive: Function, activate: Function, deactivate: Function, summon: Function, dismiss: Function}} 演出関数群
 */
export function createDopamineFx(state, dom, sfx) {
  const { overlay, commentEl, commentWrap } = dom;
  const reducedMotion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  const stats = { level: 1, xp: 0, kills: 0, gold: 0, combo: 0, pity: 0, activeMs: 0 };
  const timers = new Set();
  let els = null;
  let ctx = null;
  let active = false;
  let raf = null;
  let lastTs = null;
  let particles = [];
  let charging = null;
  let displaying = false;
  let displayTier = 0;
  let nextDamageAt = 0;
  let convergeDebt = 0;
  let pendingSummon = null;
  let shownSecond = -1;
  let dpr = 1;

  /**
   * 視差効果を減らす設定かどうかを返す。
   * @returns {boolean} prefers-reduced-motion: reduce なら true
   */
  function isReduced() {
    return Boolean(reducedMotion && reducedMotion.matches);
  }

  /**
   * 非アクティブ化で一括解除できるタイマーを登録する。
   * @param {Function} fn - 実行する処理
   * @param {number} ms - 遅延 (ミリ秒)
   * @returns {void}
   */
  function later(fn, ms) {
    const id = setTimeout(function () {
      timers.delete(id);
      fn();
    }, ms);
    timers.add(id);
  }

  /**
   * 演出用の DOM (パーティクル canvas・HUD・召喚オーブ) を必要なら生成する。
   * @returns {object} 演出用要素の参照
   */
  function ensureDom() {
    if (els) {
      return els;
    }

    const layer = document.createElement('div');
    layer.className = 'dopa-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.innerHTML = `
      <canvas class="dopa-fx-canvas"></canvas>
      <div class="dopa-xp"><div class="dopa-xp__fill"></div><span class="dopa-xp__level">LV 1</span></div>
      <div class="dopa-stats">
        <span class="dopa-stat">⏱ <b data-stat="timer">00:00</b></span>
        <span class="dopa-stat">💀 <b data-stat="kills">0</b></span>
        <span class="dopa-stat">🪙 <b data-stat="gold">0</b></span>
        <span class="dopa-stat dopa-stat--pity">SSR天井まで <b data-stat="pity">${PITY_LIMIT}</b></span>
      </div>
      <div class="dopa-combo"><b class="dopa-combo__count">0</b><span class="dopa-combo__label">COMBO</span></div>
      <div class="dopa-orb"><div class="dopa-orb__core"></div></div>
      <div class="dopa-caption"></div>
      <div class="dopa-banner"></div>
      <div class="dopa-flash"></div>`;
    overlay.insertBefore(layer, commentWrap);

    els = {
      layer,
      canvas: layer.querySelector('.dopa-fx-canvas'),
      xpFill: layer.querySelector('.dopa-xp__fill'),
      level: layer.querySelector('.dopa-xp__level'),
      timer: layer.querySelector('[data-stat="timer"]'),
      kills: layer.querySelector('[data-stat="kills"]'),
      gold: layer.querySelector('[data-stat="gold"]'),
      pity: layer.querySelector('[data-stat="pity"]'),
      combo: layer.querySelector('.dopa-combo'),
      comboCount: layer.querySelector('.dopa-combo__count'),
      orb: layer.querySelector('.dopa-orb'),
      caption: layer.querySelector('.dopa-caption'),
      banner: layer.querySelector('.dopa-banner'),
      flash: layer.querySelector('.dopa-flash')
    };
    ctx = els.canvas.getContext('2d');
    renderHud();
    return els;
  }

  /**
   * 次に必要な経験値量を返す。
   * @returns {number} 現在レベルから次レベルまでの必要経験値
   */
  function xpToNext() {
    return 8 + stats.level * 4;
  }

  /**
   * HUD の数値表示を更新する。
   * @returns {void}
   */
  function renderHud() {
    if (!els) {
      return;
    }
    els.xpFill.style.width = `${Math.min(100, (stats.xp / xpToNext()) * 100).toFixed(1)}%`;
    els.level.textContent = `LV ${stats.level}`;
    els.kills.textContent = stats.kills.toLocaleString();
    els.gold.textContent = stats.gold.toLocaleString();
    els.pity.textContent = String(PITY_LIMIT - stats.pity);
    els.comboCount.textContent = String(stats.combo);
    els.combo.classList.toggle('is-visible', stats.combo > 0);
  }

  /**
   * 経過時間表示を 1 秒単位で更新する。
   * @returns {void}
   */
  function renderTimer() {
    const sec = Math.floor(stats.activeMs / 1000);
    if (sec === shownSecond) {
      return;
    }
    shownSecond = sec;
    const mm = String(Math.floor(sec / 60)).padStart(2, '0');
    const ss = String(sec % 60).padStart(2, '0');
    els.timer.textContent = `${mm}:${ss}`;
  }

  /**
   * オーバーレイ中心座標 (CSS px) を返す。
   * @returns {{x: number, y: number}} 中心座標
   */
  function center() {
    return { x: overlay.clientWidth / 2, y: overlay.clientHeight / 2 };
  }

  /**
   * パーティクルを上限内で追加する。
   * @param {object} p - パーティクル
   * @returns {void}
   */
  function add(p) {
    if (particles.length < MAX_PARTICLES) {
      particles.push(p);
    }
  }

  /**
   * レアリティ色（UR はランダムな虹色）を返す。
   * @param {number} tier - レアリティ段階
   * @returns {string} CSS カラー
   */
  function tierColor(tier) {
    if (tier >= 4) {
      return `hsl(${Math.floor(rand(0, 360))}, 100%, 65%)`;
    }
    return Math.random() < 0.35 ? '#ffffff' : RARITIES[tier].color;
  }

  /**
   * 放射状に飛び散る火花を生成する。
   * @param {number} x - 発生 X
   * @param {number} y - 発生 Y
   * @param {number} count - 個数
   * @param {number} tier - 色に使うレアリティ段階
   * @param {number} [power] - 速度倍率
   * @returns {void}
   */
  function spawnSparks(x, y, count, tier, power) {
    const k = power || 1;
    for (let i = 0; i < count; i++) {
      const ang = rand(0, Math.PI * 2);
      const speed = rand(180, 900) * k;
      add({
        kind: 'spark', x, y,
        vx: Math.cos(ang) * speed, vy: Math.sin(ang) * speed,
        drag: 2.6, grav: 120, life: rand(0.45, 1.1), age: 0,
        size: rand(1.5, 3.5), color: tierColor(tier)
      });
    }
  }

  /**
   * 紙吹雪を生成する。
   * @param {number} x - 発生 X
   * @param {number} y - 発生 Y
   * @param {number} count - 個数
   * @returns {void}
   */
  function spawnConfetti(x, y, count) {
    for (let i = 0; i < count; i++) {
      const ang = rand(-Math.PI * 0.95, -Math.PI * 0.05);
      const speed = rand(350, 950);
      add({
        kind: 'confetti', x, y,
        vx: Math.cos(ang) * speed, vy: Math.sin(ang) * speed,
        drag: 1.6, grav: 900, life: rand(1.6, 2.8), age: 0,
        size: rand(5, 10), rot: rand(0, Math.PI), vr: rand(-12, 12),
        color: `hsl(${Math.floor(rand(0, 360))}, 95%, 62%)`
      });
    }
  }

  /**
   * 広がる光の輪を生成する。
   * @param {number} x - 中心 X
   * @param {number} y - 中心 Y
   * @param {string} color - 線色
   * @param {number} maxRadius - 最大半径
   * @param {number} life - 寿命 (秒)
   * @returns {void}
   */
  function spawnRing(x, y, color, maxRadius, life) {
    add({ kind: 'ring', x, y, maxRadius, life, age: 0, color, vx: 0, vy: 0, drag: 0, grav: 0 });
  }

  /**
   * 経験値ジェムを生成する。散らばった後 XP バーへ吸い込まれる。
   * @param {number} x - 発生 X
   * @param {number} y - 発生 Y
   * @param {number} count - 個数
   * @returns {void}
   */
  function spawnGems(x, y, count) {
    for (let i = 0; i < count; i++) {
      const type = GEM_TYPES[pickWeighted(GEM_TYPES)];
      const ang = rand(0, Math.PI * 2);
      const speed = rand(220, 620);
      add({
        kind: 'gem', x, y,
        vx: Math.cos(ang) * speed, vy: Math.sin(ang) * speed,
        drag: 3.2, grav: 0, life: 99, age: 0, homeAt: rand(0.5, 1.1),
        size: type.xp >= 5 ? 9 : 6.5, color: type.color, xp: type.xp, rot: rand(0, 6)
      });
    }
  }

  /**
   * 画面上部から金貨を降らせる。
   * @param {number} count - 枚数
   * @returns {void}
   */
  function spawnCoins(count) {
    const w = overlay.clientWidth;
    for (let i = 0; i < count; i++) {
      add({
        kind: 'coin', x: rand(0, w), y: rand(-120, -10),
        vx: rand(-40, 40), vy: rand(80, 320),
        drag: 0, grav: 650, life: 3, age: 0, size: rand(7, 11), rot: rand(0, 6), vr: rand(4, 10)
      });
    }
  }

  /**
   * ヴァンサバ風のダメージ数値を生成する。
   * @param {number} x - 表示 X
   * @param {number} y - 表示 Y
   * @param {number} tier - 威力に使うレアリティ段階
   * @returns {void}
   */
  function spawnDamage(x, y, tier) {
    const crit = Math.random() < 0.14;
    const value = Math.round(DAMAGE_BASE[tier] * rand(0.5, 1.5) * (crit ? 3 : 1));
    add({
      kind: 'text', x, y,
      vx: rand(-40, 40), vy: rand(-320, -220),
      drag: 0.8, grav: 620, life: crit ? 1.1 : 0.8, age: 0,
      size: crit ? 34 : 22,
      text: crit ? `${value.toLocaleString()}!` : value.toLocaleString(),
      color: crit ? '#ffe23d' : '#ffffff'
    });
    spawnSparks(x, y, crit ? 12 : 5, tier, 0.4);
  }

  /**
   * 表示中コメントの周囲 (たまに画面全体) にダメージ数値を出す。
   * @returns {void}
   */
  function spawnDamageAroundComment() {
    const o = overlay.getBoundingClientRect();
    const c = commentEl.getBoundingClientRect();
    let x;
    let y;
    if (Math.random() < 0.7 && c.width > 0) {
      // カードの背面に隠れないよう、カードを囲む楕円上に出す
      const ang = rand(0, Math.PI * 2);
      x = c.left - o.left + c.width / 2 + Math.cos(ang) * (c.width / 2 + rand(30, 110));
      y = c.top - o.top + c.height / 2 + Math.sin(ang) * (c.height / 2 + rand(30, 80));
    } else {
      x = rand(40, o.width - 40);
      y = rand(80, o.height - 60);
    }
    // 中央揃えの数値が画面端で切れないよう内側に収める
    spawnDamage(Math.min(Math.max(x, 56), o.width - 56), Math.min(Math.max(y, 40), o.height - 20), displayTier);
  }

  /**
   * チャージ中にオーブへ吸い込まれる光粒を生成する。
   * @param {number} count - 個数
   * @param {number} tier - 色に使うレアリティ段階
   * @returns {void}
   */
  function spawnConverge(count, tier) {
    const c = center();
    const reach = Math.max(overlay.clientWidth, overlay.clientHeight) * 0.55;
    for (let i = 0; i < count; i++) {
      const ang = rand(0, Math.PI * 2);
      const dist = rand(120, reach);
      add({
        kind: 'converge', x: c.x + Math.cos(ang) * dist, y: c.y + Math.sin(ang) * dist,
        vx: 0, vy: 0, drag: 0, grav: 0, life: 2, age: 0,
        size: rand(1.5, 3), color: tierColor(tier), speed: rand(250, 520)
      });
    }
  }

  /**
   * 経験値を加算し、必要ならレベルアップさせる。
   * @param {number} amount - 加算する経験値
   * @returns {void}
   */
  function gainXp(amount) {
    stats.xp += amount;
    while (stats.xp >= xpToNext()) {
      stats.xp -= xpToNext();
      stats.level += 1;
      levelUp();
    }
    renderHud();
  }

  /**
   * レベルアップ演出（バナー・金貨の雨・ファンファーレ）。
   * @returns {void}
   */
  function levelUp() {
    stats.gold += 50 * stats.level;
    els.banner.textContent = `LEVEL UP!  LV ${stats.level}`;
    restartClass(els.banner, 'is-show');
    spawnCoins(isReduced() ? 8 : 36);
    sfx.levelUp();
  }

  /**
   * レアリティを抽選する。PITY_LIMIT 連で SSR 以上が無ければ SSR 以上が確定する。
   * @returns {number} レアリティ段階 (0-4)
   */
  function rollTier() {
    const guaranteed = stats.pity >= PITY_LIMIT - 1;
    const tier = pickWeighted(RARITIES, guaranteed ? SSR_TIER : 0);
    stats.pity = tier >= SSR_TIER ? 0 : stats.pity + 1;
    return tier;
  }

  /**
   * 召喚オーブの色段階を切り替える。
   * @param {number} tier - 表示するレアリティ段階
   * @returns {void}
   */
  function setOrbTier(tier) {
    els.orb.dataset.tier = String(tier);
    state.fxUniforms.rarity = tier;
  }

  /**
   * チャージ中のオーブ下に煽り文句を出す。
   * @param {string} text - 表示文言
   * @param {number} tier - 色に使うレアリティ段階
   * @returns {void}
   */
  function showCaption(text, tier) {
    els.caption.textContent = text;
    els.caption.dataset.tier = String(tier);
    restartClass(els.caption, 'is-show');
  }

  /**
   * チャージ途中のレアリティ昇格演出（色変わり）。
   * @param {number} tier - 昇格後のレアリティ段階
   * @returns {void}
   */
  function promote(tier) {
    if (!charging) {
      return;
    }
    const c = center();
    setOrbTier(tier);
    restartClass(els.orb, 'is-promote');
    spawnRing(c.x, c.y, RARITIES[tier].color, 260, 0.6);
    spawnSparks(c.x, c.y, 40, tier, 0.6);
    if (CAPTIONS[tier]) {
      showCaption(CAPTIONS[tier], tier);
    }
    sfx.promote(tier);
  }

  /**
   * コメント要素からドーパミン演出の状態を外す。
   * @returns {void}
   */
  function clearCommentFx() {
    commentEl.classList.remove('is-dopa-slam');
    delete commentEl.dataset.dopaTier;
    delete commentEl.dataset.dopaRank;
    delete commentEl.dataset.dopaStars;
  }

  /**
   * 開封演出。フラッシュ・衝撃波・パーティクルを出してコメントを叩きつける。
   * @param {number} tier - 確定したレアリティ段階
   * @returns {void}
   */
  function burst(tier) {
    const rarity = RARITIES[tier];
    const reduced = isReduced();
    const c = center();
    const scale = reduced ? 0.25 : 1;

    charging = null;
    state.fxUniforms.chargeEnd = 0;
    setOrbTier(tier);
    if (!reduced) {
      state.fxUniforms.burstAt = performance.now();
      restartClass(els.flash, 'is-on');
      if (commentWrap) {
        restartClass(commentWrap, 'is-dopa-shake');
      }
    }
    els.orb.classList.remove('is-charging', 'is-promote');
    els.caption.classList.remove('is-show');

    commentEl.dataset.dopaTier = String(tier);
    commentEl.dataset.dopaRank = rarity.rank;
    commentEl.dataset.dopaStars = '★'.repeat(rarity.stars);
    restartClass(commentEl, 'is-dopa-slam');

    const diag = Math.hypot(overlay.clientWidth, overlay.clientHeight);
    spawnSparks(c.x, c.y, Math.round((90 + tier * 60) * scale), tier, 1 + tier * 0.15);
    spawnConfetti(c.x, c.y, Math.round((tier >= SSR_TIER ? 140 : 40) * scale));
    spawnRing(c.x, c.y, rarity.color, diag * 0.6, 0.9);
    spawnRing(c.x, c.y, '#ffffff', diag * 0.35, 0.6);
    spawnGems(c.x, c.y, GEM_COUNTS[tier]);
    if (tier >= SSR_TIER) {
      spawnCoins(Math.round(40 * scale));
    }

    stats.kills += 1;
    stats.combo += 1;
    stats.gold += GOLD_REWARD[tier];
    renderHud();
    restartClass(els.combo, 'is-bump');
    sfx.burst(tier);

    displaying = true;
    displayTier = tier;
    nextDamageAt = performance.now() + 220;
  }

  /**
   * ガチャ召喚演出を開始する。演出後 true、途中で中断されたら false で解決する。
   * @returns {Promise<boolean>} コメントを開封できたかどうか
   */
  function summon() {
    if (!active) {
      return Promise.resolve(false);
    }

    ensureDom();
    clearCommentFx();
    displaying = false;

    const reduced = isReduced();
    const tier = rollTier();
    const duration = reduced ? 500 : SUMMON_MS[tier];
    // SR 以上は低い色から始めて途中で昇格させる（いわゆる昇格演出）
    const startTier = !reduced && tier >= 2 ? Math.floor(Math.random() * 2) : tier;
    const now = performance.now();

    charging = { start: now, end: now + duration, tier: startTier };
    state.fxUniforms.chargeStart = now;
    state.fxUniforms.chargeEnd = now + duration;
    setOrbTier(startTier);
    restartClass(els.orb, 'is-charging');
    renderHud();
    sfx.charge(duration / 1000);

    const steps = tier - startTier;
    for (let i = 1; i <= steps; i++) {
      const promoted = startTier + i;
      later(function () {
        if (charging) {
          charging.tier = promoted;
        }
        promote(promoted);
      }, duration * (0.3 + 0.55 * (i / steps)));
    }

    return new Promise(function (resolve) {
      pendingSummon = resolve;
      later(function () {
        pendingSummon = null;
        burst(tier);
        resolve(true);
      }, duration);
    });
  }

  /**
   * コメント表示の終了時に呼ぶ。ダメージ数値の発生を止める。
   * @returns {void}
   */
  function dismiss() {
    displaying = false;
    commentEl.classList.remove('is-dopa-slam');
  }

  /**
   * 1 パーティクルを dt 秒進める。
   * @param {object} p - パーティクル
   * @param {number} dt - 経過秒
   * @param {{x: number, y: number}} c - 画面中心
   * @param {{x: number, y: number}} xpTarget - XP バーの吸い込み先
   * @returns {boolean} 生存していれば true
   */
  function step(p, dt, c, xpTarget) {
    p.age += dt;

    if (p.kind === 'converge') {
      const dx = c.x - p.x;
      const dy = c.y - p.y;
      const dist = Math.hypot(dx, dy);
      if (dist < 24 || p.age >= p.life) {
        return false;
      }
      p.speed += 900 * dt;
      p.px = p.x;
      p.py = p.y;
      p.x += (dx / dist) * p.speed * dt;
      p.y += (dy / dist) * p.speed * dt;
      return true;
    }

    if (p.kind === 'gem' && p.age > p.homeAt) {
      const dx = xpTarget.x - p.x;
      const dy = xpTarget.y - p.y;
      const dist = Math.hypot(dx, dy);
      if (dist < 18) {
        gainXp(p.xp);
        sfx.pickup();
        spawnSparks(p.x, p.y, 4, 1, 0.25);
        return false;
      }
      const pull = 2400 * Math.min(1, (p.age - p.homeAt) * 1.5 + 0.2);
      p.vx += (dx / dist) * pull * dt;
      p.vy += (dy / dist) * pull * dt;
      p.vx *= 1 - Math.min(1, 2.2 * dt);
      p.vy *= 1 - Math.min(1, 2.2 * dt);
    }

    const damp = 1 - Math.min(1, p.drag * dt);
    p.vx *= damp;
    p.vy *= damp;
    p.vy += p.grav * dt;
    p.px = p.x;
    p.py = p.y;
    p.x += p.vx * dt;
    p.y += p.vy * dt;
    if (p.vr) {
      p.rot += p.vr * dt;
    }
    return p.age < p.life;
  }

  /**
   * 1 パーティクルを描画する。
   * @param {object} p - パーティクル
   * @returns {void}
   */
  function draw(p) {
    const fade = Math.max(0, 1 - p.age / p.life);

    if (p.kind === 'spark' || p.kind === 'converge') {
      ctx.globalAlpha = p.kind === 'spark' ? fade : 0.9;
      ctx.strokeStyle = p.color;
      ctx.lineWidth = p.size;
      ctx.beginPath();
      ctx.moveTo(p.px, p.py);
      ctx.lineTo(p.x + (p.x - p.px) * 1.5, p.y + (p.y - p.py) * 1.5);
      ctx.stroke();
      return;
    }

    if (p.kind === 'ring') {
      const k = p.age / p.life;
      ctx.globalAlpha = fade;
      ctx.strokeStyle = p.color;
      ctx.lineWidth = 2 + 10 * fade;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.maxRadius * (1 - Math.pow(1 - k, 3)), 0, Math.PI * 2);
      ctx.stroke();
      return;
    }

    if (p.kind === 'confetti') {
      ctx.globalAlpha = Math.min(1, fade * 2);
      ctx.fillStyle = p.color;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2 * Math.abs(Math.cos(p.rot * 1.7)) + 1);
      ctx.restore();
      return;
    }

    if (p.kind === 'gem') {
      const s = p.size;
      ctx.globalAlpha = 1;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(Math.sin(p.age * 6 + p.rot) * 0.35);
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.moveTo(0, -s * 1.3);
      ctx.lineTo(s, 0);
      ctx.lineTo(0, s * 1.3);
      ctx.lineTo(-s, 0);
      ctx.closePath();
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
      ctx.stroke();
      ctx.restore();
      return;
    }

    if (p.kind === 'coin') {
      ctx.globalAlpha = Math.min(1, fade * 3);
      ctx.fillStyle = '#ffcf33';
      ctx.strokeStyle = '#9a6a00';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.ellipse(p.x, p.y, p.size * Math.abs(Math.cos(p.rot)) + 1, p.size, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      return;
    }

    if (p.kind === 'text') {
      const pop = p.age < 0.12 ? 0.6 + (p.age / 0.12) * 0.6 : 1.2 - Math.min(0.2, (p.age - 0.12));
      ctx.globalAlpha = Math.min(1, fade * 2.5);
      ctx.font = `italic 900 ${Math.round(p.size * pop)}px system-ui, "Hiragino Sans", sans-serif`;
      ctx.textAlign = 'center';
      ctx.lineJoin = 'round';
      ctx.lineWidth = 5;
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.9)';
      ctx.strokeText(p.text, p.x, p.y);
      ctx.fillStyle = p.color;
      ctx.fillText(p.text, p.x, p.y);
    }
  }

  /**
   * パーティクル canvas の解像度をオーバーレイに合わせる。
   * @returns {void}
   */
  function resizeFxCanvas() {
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const width = Math.max(1, Math.floor(overlay.clientWidth * dpr));
    const height = Math.max(1, Math.floor(overlay.clientHeight * dpr));
    if (els.canvas.width !== width || els.canvas.height !== height) {
      els.canvas.width = width;
      els.canvas.height = height;
    }
  }

  /**
   * 演出のフレーム更新。
   * @param {number} ts - requestAnimationFrame のタイムスタンプ
   * @returns {void}
   */
  function tick(ts) {
    raf = requestAnimationFrame(tick);
    const dt = lastTs === null ? 1 / 60 : Math.min((ts - lastTs) / 1000, 0.05);
    lastTs = ts;
    stats.activeMs += dt * 1000;
    renderTimer();
    resizeFxCanvas();

    if (charging) {
      const k = Math.min(1, Math.max(0, (ts - charging.start) / (charging.end - charging.start)));
      els.orb.style.setProperty('--dopa-amp', `${(1 + k * 7).toFixed(1)}px`);
      convergeDebt += dt * (isReduced() ? 20 : 50 + k * 260);
      const n = Math.floor(convergeDebt);
      convergeDebt -= n;
      spawnConverge(n, charging.tier);
    }

    if (displaying && ts >= nextDamageAt) {
      spawnDamageAroundComment();
      nextDamageAt = ts + rand(110, 330) * (isReduced() ? 3 : 1);
    }

    const c = center();
    const xpTarget = {
      x: Math.max(24, overlay.clientWidth * Math.min(1, stats.xp / xpToNext())),
      y: XP_BAR_Y
    };
    const next = [];
    for (let i = 0; i < particles.length; i++) {
      if (step(particles[i], dt, c, xpTarget)) {
        next.push(particles[i]);
      }
    }
    particles = next;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, overlay.clientWidth, overlay.clientHeight);
    // 光るものは加算合成、それ以外は通常合成で 2 パスに分けて描く
    ctx.globalCompositeOperation = 'lighter';
    particles.forEach(function (p) {
      if (p.kind === 'spark' || p.kind === 'converge' || p.kind === 'ring') {
        draw(p);
      }
    });
    ctx.globalCompositeOperation = 'source-over';
    particles.forEach(function (p) {
      if (p.kind !== 'spark' && p.kind !== 'converge' && p.kind !== 'ring') {
        draw(p);
      }
    });
    ctx.globalAlpha = 1;
  }

  /**
   * ドーパミンモードを開始する（HUD 表示とフレーム更新）。
   * @returns {void}
   */
  function activate() {
    if (active) {
      return;
    }
    ensureDom();
    active = true;
    lastTs = null;
    raf = requestAnimationFrame(tick);
  }

  /**
   * ドーパミンモードを停止し、進行中の演出をすべて片付ける。
   * 召喚中なら summon() の Promise を false で解決する。
   * @returns {void}
   */
  function deactivate() {
    if (!active) {
      return;
    }
    active = false;
    if (raf !== null) {
      cancelAnimationFrame(raf);
      raf = null;
    }
    timers.forEach(clearTimeout);
    timers.clear();
    sfx.stopAll();

    charging = null;
    displaying = false;
    particles = [];
    state.fxUniforms.chargeEnd = 0;
    state.fxUniforms.burstAt = -Infinity;

    els.orb.classList.remove('is-charging', 'is-promote');
    els.caption.classList.remove('is-show');
    els.banner.classList.remove('is-show');
    els.flash.classList.remove('is-on');
    if (commentWrap) {
      commentWrap.classList.remove('is-dopa-shake');
    }
    clearCommentFx();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, els.canvas.width, els.canvas.height);

    if (pendingSummon) {
      const resolve = pendingSummon;
      pendingSummon = null;
      resolve(false);
    }
  }

  /**
   * ドーパミンモードが動作中かどうかを返す。
   * @returns {boolean} 動作中なら true
   */
  function isActive() {
    return active;
  }

  return { sceneId: DOPAMINE_SCENE_ID, isActive, activate, deactivate, summon, dismiss };
}
