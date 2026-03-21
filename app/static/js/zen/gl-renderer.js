/* zen/gl-renderer.js – WebGL 初期化・シェーダーコンパイル・描画ループ */

/**
 * WebGL レンダラーを生成する。
 * @param {object} state - 共有ミュータブル状態オブジェクト
 * @param {HTMLCanvasElement} canvas - 描画先キャンバス要素
 * @param {HTMLElement} overlay - オーバーレイ要素（サイズ参照用）
 * @param {string} vert - 頂点シェーダーソースコード
 * @param {number} attrPosition - 位置属性のバインドインデックス
 * @returns {{initGL: Function, resizeCanvas: Function, buildSceneProgram: Function, render: Function}} レンダラー関数群
 */
export function createRenderer(state, canvas, overlay, vert, attrPosition) {
  /**
   * 今日の月相を返す。
   * @returns {number} 0=新月, 0.5=満月, 1=新月 の範囲の実数
   */
  function getLunarPhase() {
    const refNewMoon = new Date('2000-01-06T18:14:00Z');
    const synodicPeriod = 29.530588853;
    const daysSince = (Date.now() - refNewMoon.getTime()) / 86400000;
    return (((daysSince % synodicPeriod) + synodicPeriod) % synodicPeriod) / synodicPeriod;
  }

  /**
   * 指定タイプの GLSL シェーダーをコンパイルして返す。
   * @param {number} type - gl.VERTEX_SHADER または gl.FRAGMENT_SHADER
   * @param {string} src - GLSL ソースコード
   * @returns {WebGLShader|null} コンパイル済みシェーダー
   */
  function compileShader(type, src) {
    const gl = state.gl;
    const shader = gl.createShader(type);
    if (!shader) {
      return null;
    }

    gl.shaderSource(shader, src);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      console.warn('[ZenMode] shader compile error:', gl.getShaderInfoLog(shader));
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  }

  /**
   * シーンに対応する GL プログラムを生成または取得する。
   * @param {{id: string, fragmentSource: string}} scene - 使用するシーン定義
   * @returns {{program: WebGLProgram, uniforms: {time: WebGLUniformLocation|null, res: WebGLUniformLocation|null, phase: WebGLUniformLocation|null}}|null} プログラム情報
   */
  function buildSceneProgram(scene) {
    const cached = state.scenePrograms.get(scene.id);
    if (cached) {
      return cached;
    }

    const gl = state.gl;
    const vertexShader = compileShader(gl.VERTEX_SHADER, vert);
    const fragmentShader = compileShader(gl.FRAGMENT_SHADER, scene.fragmentSource);
    if (!vertexShader || !fragmentShader) {
      if (vertexShader) {
        gl.deleteShader(vertexShader);
      }
      if (fragmentShader) {
        gl.deleteShader(fragmentShader);
      }
      return null;
    }

    const program = gl.createProgram();
    if (!program) {
      gl.deleteShader(vertexShader);
      gl.deleteShader(fragmentShader);
      return null;
    }

    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.bindAttribLocation(program, attrPosition, 'a_pos');
    gl.linkProgram(program);
    gl.deleteShader(vertexShader);
    gl.deleteShader(fragmentShader);

    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.warn('[ZenMode] shader link error:', gl.getProgramInfoLog(program));
      gl.deleteProgram(program);
      return null;
    }

    const entry = {
      program,
      uniforms: {
        time: gl.getUniformLocation(program, 'u_time'),
        res: gl.getUniformLocation(program, 'u_res'),
        phase: gl.getUniformLocation(program, 'u_phase')
      }
    };
    state.scenePrograms.set(scene.id, entry);
    return entry;
  }

  /**
   * WebGL コンテキストを初期化する。
   * @returns {boolean} 初期化成功なら true
   */
  function initGL() {
    if (state.glReady) {
      return true;
    }

    try {
      state.gl = canvas.getContext('webgl', {
        alpha: false,
        antialias: false,
        depth: false,
        stencil: false,
        premultipliedAlpha: false,
        preserveDrawingBuffer: false,
        powerPreference: 'high-performance'
      }) || canvas.getContext('experimental-webgl');
      if (!state.gl) {
        return false;
      }

      const gl = state.gl;
      state.quadBuffer = gl.createBuffer();
      if (!state.quadBuffer) {
        return false;
      }

      gl.bindBuffer(gl.ARRAY_BUFFER, state.quadBuffer);
      gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
        gl.STATIC_DRAW
      );
      gl.disable(gl.DEPTH_TEST);
      gl.disable(gl.BLEND);

      state.glReady = true;
      return true;
    } catch (error) {
      console.warn('[ZenMode] WebGL init failed:', error);
      return false;
    }
  }

  /**
   * オーバーレイサイズに合わせてキャンバス解像度を更新する。
   * @returns {void}
   */
  function resizeCanvas() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.floor(overlay.clientWidth * dpr));
    const height = Math.max(1, Math.floor(overlay.clientHeight * dpr));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      if (state.gl) {
        state.gl.viewport(0, 0, width, height);
      }
    }
  }

  /**
   * rAF コールバック。現在アクティブなシーンを描画する。
   * @param {number} ts - requestAnimationFrame のタイムスタンプ
   * @returns {void}
   */
  function render(ts) {
    state.raf = requestAnimationFrame(render);
    resizeCanvas();
    if (!state.glReady || !state.currentSceneState) {
      return;
    }

    if (state.sceneStartTime === null) {
      state.sceneStartTime = ts;
    }

    const elapsed = (ts - state.sceneStartTime) * 0.001;
    const { uniforms } = state.currentSceneState.programEntry;
    const gl = state.gl;
    if (uniforms.time) {
      gl.uniform1f(uniforms.time, elapsed);
    }
    if (uniforms.res) {
      gl.uniform2f(uniforms.res, canvas.width, canvas.height);
    }
    if (uniforms.phase) {
      gl.uniform1f(uniforms.phase, state.lunarPhase);
    }
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  state.lunarPhase = getLunarPhase();

  return { initGL, resizeCanvas, buildSceneProgram, render };
}
