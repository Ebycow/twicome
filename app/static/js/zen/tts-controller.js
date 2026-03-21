/* zen/tts-controller.js – Web Speech API による読み上げ制御 */

/**
 * TTS コントローラーを生成する。
 * Web Speech API (SpeechSynthesis) を使ってコメントを読み上げる。
 * @returns {{speak: Function, stop: Function, toggle: Function, isEnabled: Function, isSupported: Function}} TTS 関数群
 */
export function createTTSController() {
  let enabled = false;

  /**
   * Web Speech API が利用可能かどうかを返す。
   * @returns {boolean} Web Speech API が利用可能なら true
   */
  function isSupported() {
    return 'speechSynthesis' in window;
  }

  /**
   * 現在の有効状態を返す。
   * @returns {boolean} TTS が有効なら true
   */
  function isEnabled() {
    return enabled;
  }

  /**
   * テキストを読み上げる。無効または非対応の場合は即時解決の Promise を返す。
   * @param {string} text - 読み上げるテキスト
   * @returns {Promise<void>} 読み上げ完了（またはキャンセル）時に解決する Promise
   */
  function speak(text) {
    if (!enabled || !isSupported()) {
      return Promise.resolve();
    }

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'ja-JP';
    return new Promise(function (resolve) {
      utterance.onend = resolve;
      utterance.onerror = resolve;
      window.speechSynthesis.speak(utterance);
    });
  }

  /**
   * 読み上げを停止する。
   * @returns {void}
   */
  function stop() {
    if (!isSupported()) {
      return;
    }

    window.speechSynthesis.cancel();
  }

  /**
   * 有効・無効を切り替える。
   * @returns {boolean} 切り替え後の有効状態
   */
  function toggle() {
    enabled = !enabled;
    if (!enabled) {
      stop();
    }
    return enabled;
  }

  return { speak, stop, toggle, isEnabled, isSupported };
}
