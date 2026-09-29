/* zen/dopamine-sfx.js – ドーパミンモードの効果音 (Web Audio API で合成、既定はオフ) */

/**
 * ドーパミンモード用の効果音コントローラーを生成する。
 * 音声ファイルは使わず、オシレーターとノイズで都度合成する。
 * @returns {{isSupported: Function, isEnabled: Function, toggle: Function, charge: Function, promote: Function, burst: Function, pickup: Function, levelUp: Function, stopAll: Function}} 効果音関数群
 */
export function createDopamineSfx() {
  const AudioCtor = window.AudioContext || window.webkitAudioContext;
  const live = new Set();
  let ctx = null;
  let master = null;
  let enabled = false;
  let lastPickupAt = 0;
  let pickupStep = 0;

  /**
   * Web Audio API が利用可能かどうかを返す。
   * @returns {boolean} 利用可能なら true
   */
  function isSupported() {
    return Boolean(AudioCtor);
  }

  /**
   * 現在の有効状態を返す。
   * @returns {boolean} 効果音が有効なら true
   */
  function isEnabled() {
    return enabled;
  }

  /**
   * AudioContext を用意して再生可能なら返す。
   * @returns {AudioContext|null} 再生に使うコンテキスト
   */
  function ready() {
    if (!enabled || !AudioCtor) {
      return null;
    }
    if (!ctx) {
      ctx = new AudioCtor();
      master = ctx.createGain();
      master.gain.value = 0.22;
      master.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') {
      ctx.resume().catch(function () {});
    }
    return ctx;
  }

  /**
   * 再生中ノードを追跡し、終了時に破棄する。
   * @param {AudioScheduledSourceNode} node - 追跡するソースノード
   * @returns {void}
   */
  function track(node) {
    live.add(node);
    node.onended = function () {
      live.delete(node);
    };
  }

  /**
   * 減衰エンベロープ付きの単音を鳴らす。
   * @param {number} freq - 開始周波数 (Hz)
   * @param {number} delay - 現在からの開始遅延 (秒)
   * @param {number} dur - 長さ (秒)
   * @param {{type?: OscillatorType, gain?: number, slideTo?: number}} [opts] - 波形・音量・周波数スライド先
   * @returns {void}
   */
  function tone(freq, delay, dur, opts) {
    const ac = ready();
    if (!ac) {
      return;
    }

    const o = opts || {};
    const t0 = ac.currentTime + delay;
    const osc = ac.createOscillator();
    const env = ac.createGain();
    osc.type = o.type || 'sine';
    osc.frequency.setValueAtTime(freq, t0);
    if (o.slideTo) {
      osc.frequency.exponentialRampToValueAtTime(o.slideTo, t0 + dur);
    }
    env.gain.setValueAtTime(0.0001, t0);
    env.gain.linearRampToValueAtTime(o.gain || 0.3, t0 + 0.012);
    env.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(env);
    env.connect(master);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
    track(osc);
  }

  /**
   * ハイパスを通したホワイトノイズを鳴らす（爆発・衝撃音用）。
   * @param {number} dur - 長さ (秒)
   * @param {number} gain - 音量
   * @returns {void}
   */
  function noise(dur, gain) {
    const ac = ready();
    if (!ac) {
      return;
    }

    const length = Math.floor(ac.sampleRate * dur);
    const buffer = ac.createBuffer(1, length, ac.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i++) {
      data[i] = (Math.random() * 2 - 1) * (1 - i / length);
    }
    const src = ac.createBufferSource();
    const filter = ac.createBiquadFilter();
    const env = ac.createGain();
    src.buffer = buffer;
    filter.type = 'highpass';
    filter.frequency.value = 600;
    env.gain.value = gain;
    src.connect(filter);
    filter.connect(env);
    env.connect(master);
    src.start();
    track(src);
  }

  /**
   * 召喚チャージ音（上昇するうなり）。
   * @param {number} seconds - チャージ時間 (秒)
   * @returns {void}
   */
  function charge(seconds) {
    tone(140, 0, seconds, { type: 'sawtooth', gain: 0.06, slideTo: 1400 });
    tone(210, 0, seconds, { type: 'triangle', gain: 0.08, slideTo: 2100 });
  }

  /**
   * レアリティ昇格音。
   * @param {number} tier - 昇格後のレアリティ段階 (0-4)
   * @returns {void}
   */
  function promote(tier) {
    const base = 660 * Math.pow(1.12, tier);
    tone(base, 0, 0.18, { type: 'square', gain: 0.1 });
    tone(base * 1.5, 0.07, 0.3, { type: 'square', gain: 0.1 });
  }

  /**
   * 開封時の爆発音とレアリティに応じたアルペジオ。
   * @param {number} tier - レアリティ段階 (0-4)
   * @returns {void}
   */
  function burst(tier) {
    noise(0.5, 0.35);
    tone(160, 0, 0.6, { type: 'sine', gain: 0.5, slideTo: 40 });

    const root = 523.25;
    const steps = [0, 4, 7, 12, 16, 19, 24];
    const count = 3 + tier;
    for (let i = 0; i < count; i++) {
      const freq = root * Math.pow(2, steps[i % steps.length] / 12);
      tone(freq, 0.05 + i * 0.07, 0.5, { type: 'triangle', gain: 0.16 });
    }
    if (tier >= 4) {
      for (let i = 0; i < 10; i++) {
        tone(2000 + Math.random() * 2600, 0.5 + i * 0.05, 0.25, { type: 'sine', gain: 0.05 });
      }
    }
  }

  /**
   * 経験値ジェム取得音。連続取得で音程が上がる。
   * @returns {void}
   */
  function pickup() {
    const now = performance.now();
    if (now - lastPickupAt < 45) {
      return;
    }
    if (now - lastPickupAt > 600) {
      pickupStep = 0;
    }
    lastPickupAt = now;
    tone(880 * Math.pow(2, (pickupStep % 16) / 16), 0, 0.07, { type: 'square', gain: 0.05 });
    pickupStep += 1;
  }

  /**
   * レベルアップのファンファーレ。
   * @returns {void}
   */
  function levelUp() {
    [523.25, 659.25, 783.99, 1046.5].forEach(function (freq, i) {
      tone(freq, i * 0.09, 0.22, { type: 'square', gain: 0.1 });
    });
    [1046.5, 1318.5, 1568].forEach(function (freq) {
      tone(freq, 0.4, 0.8, { type: 'triangle', gain: 0.09 });
    });
  }

  /**
   * 鳴っている音をすべて止める。
   * @returns {void}
   */
  function stopAll() {
    live.forEach(function (node) {
      try {
        node.stop();
      } catch (error) {
        // 既に停止済みのノードは無視する
      }
    });
    live.clear();
  }

  /**
   * 有効・無効を切り替える。
   * @returns {boolean} 切り替え後の有効状態
   */
  function toggle() {
    enabled = !enabled;
    if (enabled) {
      ready();
    } else {
      stopAll();
    }
    return enabled;
  }

  return { isSupported, isEnabled, toggle, charge, promote, burst, pickup, levelUp, stopAll };
}
