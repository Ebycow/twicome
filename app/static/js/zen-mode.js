/* zen-mode.js – Zenモード: 最適化GLSLナイトシーン + コメントスライドショー */
(function () {
  'use strict';

  /* ─────────────────────────────────────────
     GLSL シェーダー
  ───────────────────────────────────────── */
  const VERT = [
    'attribute vec2 a_pos;',
    'void main(){gl_Position=vec4(a_pos,0.0,1.0);}'
  ].join('\n');

  /*
   * 手続き的ナイトシーン
   *  ・月: アスペクト比補正で真円, 適切な輝度
   *  ・草: 地面から上向きに成長（正しい方向）
   *  ・星: 3スケール グリッドベース, キラキラ点滅
   *  ・全体的に暗く静寂なシーン
   */
  const FRAG = [
    'precision mediump float;',
    'uniform float u_time;',
    'uniform vec2  u_res;',
    'uniform float u_phase;',   /* 月相: 0=新月, 0.5=満月, 1=新月 */

    /* --- 高速ハッシュ (sin 不使用) --- */
    'float h1(float n){n=fract(n*.1031);n*=n+33.33;n*=n+n;return fract(n);}',
    'float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}',
    'float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1,0)),f.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),f.x),f.y);}',

    'void main(){',
    '  vec2 uv = gl_FragCoord.xy / u_res;',
    '  float ar = u_res.x / u_res.y;',    /* アスペクト比 */
    '  float t  = u_time;',
    '  float GY = 0.20;',                  /* 草の地平線 (画面下20%) */

    /* === 夜空 ===
       ・下端: 漆黒 (地平線帯なし)
       ・上部: ごくわずかに深紺
       ・二次関数グラデーション → 均一に暗く帯なし */
    '  vec3 skyTop  = vec3(.004,.003,.022);',
    '  vec3 skyBot  = vec3(.0,.0,.004);',
    '  vec3 col = mix(skyBot, skyTop, uv.y*uv.y);',

    /* === 天の川 (非常に控えめ、草エリアより上のみ) === */
    '  float mw = vn(vec2(uv.x*2.8+.4, uv.y*9.+t*.006))*.22',
    '           + vn(vec2(uv.x*5.5, uv.y*18.))*.11;',
    '  col += vec3(.010,.007,.025)*mw',
    '        *smoothstep(GY+.18,GY+.45,uv.y)',
    '        *smoothstep(0.,.3,uv.y*(1.-uv.y)*4.);',

    /* === 月 (アスペクト比補正で真円, 実際の月相に同期) ===
       位置: 右上エリア
       大きさ: 控えめ, 輝度: 穏やか */
    '  vec2 mpos = vec2(.74,.80);',
    '  vec2 mvec = (uv - mpos) * vec2(ar, 1.0);',
    '  float md  = length(mvec);',
    '  float mr  = .030;',

    /* 月相: pa=0で新月, pa=PIで満月 */
    '  float pa   = u_phase*6.28318;',
    '  float illum = (1.-cos(pa))*.5;',  /* 輝面比: 0=新月,1=満月 */
    '  float moonLit = 0.0;',
    '  if(md < mr){',
    '    float muX = mvec.x/mr;',
    '    float muY = mvec.y/mr;',
    '    float disc = sqrt(max(0.,1.-muY*muY));',
    '    float tx = cos(pa)*disc;',          /* 明暗境界線のX位置 */
    '    if(u_phase<0.5){',                  /* 上弦: 右側が輝く */
    '      moonLit = smoothstep(tx-.04,tx+.04,muX);',
    '    } else {',                           /* 下弦: 左側が輝く */
    '      moonLit = 1.0-smoothstep(-tx-.04,-tx+.04,muX);',
    '    }',
    '  }',

    '  float limb = md<mr ? sqrt(max(0.,1.-(md/mr)*(md/mr)))*.08 : 0.;',
    /* 地球照: 月の暗い面にごく薄く青みがかった反射 */
    '  float earthshine = smoothstep(mr+.002,mr-.002,md)*(1.-moonLit)*.018;',
    '  col += vec3(.94,.91,.80) * (',
    '    smoothstep(mr+.002,mr-.002,md)*moonLit*(.90+limb)',
    '    + exp(-md*16.)*illum*.18',
    '    + exp(-md*5.5)*illum*.06);',
    '  col += vec3(.72,.82,.98)*earthshine;',

    /* 月面テクスチャ (照らされた面のみ) */
    '  if(md < mr){',
    '    vec2 mu = mvec/mr;',
    '    float cr = vn(mu*7.+1.8)*.040 + vn(mu*18.)*.016;',
    '    col -= vec3(cr,cr*.84,cr*.60) * smoothstep(mr,.0,md) * moonLit;',
    '  }',

    /* === 星 (3スケール, キラキラ) === */
    '  {',
    '    vec2 s,si,sf,jit; float h,sp,tw;',

    /* 大きい星: 色のバリエーション付き */
    '    s=uv*vec2(43.,25.); si=floor(s); sf=fract(s)-.5; h=h2(si);',
    '    if(h>.875){jit=vec2(h2(si+.3)-.5,h2(si+.7)-.5)*.6;tw=.55+.45*sin(t*(1.+h*3.)+h*27.);sp=smoothstep(.050,.0,length(sf-jit));col+=mix(vec3(.68,.80,1.),vec3(1.,.88,.62),h2(si+1.1))*sp*tw;}',

    /* 中くらいの星 */
    '    s=uv*vec2(87.,50.); si=floor(s); sf=fract(s)-.5; h=h2(si+50.);',
    '    if(h>.895){jit=vec2(h2(si+10.3)-.5,h2(si+10.7)-.5)*.65;tw=.48+.52*sin(t*(1.5+h*4.)+h*48.);sp=smoothstep(.028,.0,length(sf-jit));col+=vec3(.72,.84,1.)*sp*tw*.50;}',

    /* 遠い小さな星: 点滅なし */
    '    s=uv*vec2(178.,100.); si=floor(s); sf=fract(s)-.5; h=h2(si+200.);',
    '    if(h>.915){jit=vec2(h2(si+20.3)-.5,h2(si+20.7)-.5)*.6;sp=smoothstep(.020,.0,length(sf-jit));col+=vec3(.56,.60,.82)*sp*.26;}',
    '  }',


    /* === 草 (地面から上向きに成長, セルベース)
       layer=0: 後ろの列 (暗い, 低め)
       layer=1: 前の列 (わずかに明るい, 高め) — 後から描いて前面に出す */
    /* === 草 (細長い三角形, 地面→上向き成長, セルベース)
       地平線バンドを防ぐため:
         ・密度を下げてセル間に隙間を確保
         ・根元をできるだけ広く, 先端を0にする真の三角形
         ・草の色を空より若干明るくして個々の刃を可視化
       layer=0: 後ろ列, layer=1: 前列 (後から描いて前面に出す) */
    '  if(uv.y < GY+.01){',
    '    float D   = 55.;',            /* セル数: 少なめ→刃間に隙間 */
    '    float ci0 = floor(uv.x*D);',
    '    for(int layer=0;layer<2;layer++){',
    '      float lf = float(layer);',
    '      float ls = lf*300.;',
    '      for(int di=0;di<3;di++){',
    '        float ci  = ci0+float(di)-1.;',
    /* 前列(lf=1)は若干高め */
    '        float bh  = (.12+h1(ci+ls)*.10)*(.76+lf*.26);',
    /* 根元の幅: セル幅の約30%→刃間に明確な隙間 */
    '        float bw  = .0040+h1(ci+ls+100.)*.0035;',
    '        float bx  = (ci+.5+(h1(ci+ls+50.)-.5)*.45)/D;',
    '        float wf  = .8+h1(ci+ls+150.)*.9;',
    '        float wp  = bx*13.+t*wf;',
    /* 2周波の自然な風揺らぎ */
    '        float sw  = sin(wp)*.014+sin(wp*1.7+1.1)*.006;',

    /* 真の三角形: prog=0(根元)→最大幅, prog=1(先端)→幅0 */
    '        if(uv.y < bh){',
    '          float prog  = uv.y/bh;',
    '          float bendX = bx+sw*prog*prog;',
    '          float tapW  = bw*(1.-prog);',
    '          float dx    = abs(uv.x-bendX);',
    '          if(dx<tapW){',
    /* エッジをsmootstepでアンチエイリアス */
    '            float a  = smoothstep(tapW, tapW*.35, dx);',
    /* 月光に照らされた草: 先端ほど明るい(月光の反射) */
    /* 空(skyDark=.001,.001,.006)より明るくして刃を可視化 */
    '            float br = .009+prog*.020+lf*.004;',
    '            col = mix(col, vec3(br*.60, br, br*.55+prog*.006), a*.97);',
    '          }',
    '        }',
    '      }',
    '    }',
    '  }',

    /* === ビネット (周辺減光) === */
    '  vec2 vp = uv-.5;',
    '  col *= clamp(1.-dot(vp*vec2(1.5,1.3),vp*vec2(1.5,1.3))*.7, 0.,1.);',

    /* === トーンマップ === */
    '  col = col/(col+.07);',

    '  gl_FragColor = vec4(col,1.);',
    '}'
  ].join('\n');

  /* ─────────────────────────────────────────
     DOM 参照
  ───────────────────────────────────────── */
  const overlay    = document.getElementById('zen-overlay');
  const canvas     = document.getElementById('zen-canvas');
  const commentEl  = document.getElementById('zen-comment');
  const closeBtn   = document.getElementById('zen-close-btn');
  const fsBtn      = document.getElementById('zen-fs-btn');
  const triggerBtn = document.getElementById('zen-mode-btn');

  if (!overlay || !canvas || !commentEl) { return; }

  /* ─────────────────────────────────────────
     月相計算 (朔望周期 29.530588853 日)
     基準新月: 2000-01-06 18:14 UTC
  ───────────────────────────────────────── */
  /**
   * 今日の月相を返す。
   * @returns {number} 0=新月, 0.5=満月, 1=新月 の範囲の実数
   */
  function getLunarPhase() {
    const refNewMoon     = new Date('2000-01-06T18:14:00Z');
    const synodicPeriod  = 29.530588853; /* days */
    const daysSince = (Date.now() - refNewMoon.getTime()) / 86400000;
    return ((daysSince % synodicPeriod) + synodicPeriod) % synodicPeriod / synodicPeriod;
  }

  const lunarPhase = getLunarPhase();

  /* ─────────────────────────────────────────
     WebGL 状態
  ───────────────────────────────────────── */
  let gl = null, uTime = null, uRes = null, uPhase = null;
  let raf = null, startTime = null;
  let glReady = false;

  /**
   * 指定タイプのGLSLシェーダーをコンパイルして返す。
   * @param {number} type - gl.VERTEX_SHADER または gl.FRAGMENT_SHADER
   * @param {string} src - GLSLソースコード
   * @returns {WebGLShader} コンパイル済みシェーダー
   */
  function compileShader(type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    return s;
  }

  /**
   * WebGLコンテキストを初期化してシェーダーをセットアップする。
   * @returns {boolean} 初期化成功なら true
   */
  function initGL() {
    if (glReady) { return true; }
    try {
      gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (!gl) { return false; }

      const prog = gl.createProgram();
      gl.attachShader(prog, compileShader(gl.VERTEX_SHADER,   VERT));
      gl.attachShader(prog, compileShader(gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
        console.warn('[ZenMode] shader link error:', gl.getProgramInfoLog(prog));
        return false;
      }
      gl.useProgram(prog);

      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER,
        new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(prog, 'a_pos');
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

      uTime  = gl.getUniformLocation(prog, 'u_time');
      uRes   = gl.getUniformLocation(prog, 'u_res');
      uPhase = gl.getUniformLocation(prog, 'u_phase');

      glReady = true;
      return true;
    } catch (e) {
      console.warn('[ZenMode] WebGL init failed:', e);
      return false;
    }
  }

  /**
   * オーバーレイサイズに合わせてキャンバスの解像度を更新する。
   * DPRは最大2xに制限してパフォーマンスを確保する。
   * @returns {void}
   */
  function resizeCanvas() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.floor(overlay.clientWidth  * dpr);
    const h = Math.floor(overlay.clientHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width  = w;
      canvas.height = h;
      if (gl) { gl.viewport(0, 0, w, h); }
    }
  }

  /* ─────────────────────────────────────────
     レンダーループ
  ───────────────────────────────────────── */
  /**
   * rAFコールバック: キャンバスリサイズ後にシェーダーを描画する。
   * @param {number} ts - requestAnimationFrameのタイムスタンプ (ms)
   * @returns {void}
   */
  function render(ts) {
    raf = requestAnimationFrame(render);
    resizeCanvas();
    if (!glReady) { return; }
    if (startTime === null) { startTime = ts; }
    const t = (ts - startTime) * 0.001;
    gl.uniform1f(uTime,  t);
    gl.uniform2f(uRes,   canvas.width, canvas.height);
    gl.uniform1f(uPhase, lunarPhase);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  /* ─────────────────────────────────────────
     コメント収集・スライドショー
  ───────────────────────────────────────── */
  let comments   = [];
  let commentIdx = 0;
  let slideTimer = null;

  /**
   * DOM内のコメント本文をテキストとして収集してシャッフルして返す。
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
    /* Fisher-Yates シャッフル */
    for (let i = out.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const tmp = out[i]; out[i] = out[j]; out[j] = tmp;
    }
    return out.length ? out : ['コメントがありません'];
  }

  /**
   * 次のコメントをフェードイン表示し、一定時間後にフェードアウトして次へ進める。
   * @returns {void}
   */
  function showNextComment() {
    if (!comments.length) { return; }
    const text = comments[commentIdx % comments.length];
    commentIdx++;

    /* 瞬時にリセット → フェードイン */
    commentEl.style.transition = 'none';
    commentEl.style.opacity = '0';
    commentEl.textContent = text;
    void commentEl.offsetHeight; /* reflow */
    commentEl.style.transition = 'opacity 1.5s ease';
    commentEl.style.opacity = '1';

    /* 5秒後にフェードアウト → 次へ */
    slideTimer = setTimeout(function () {
      commentEl.style.transition = 'opacity 1.2s ease';
      commentEl.style.opacity = '0';
      slideTimer = setTimeout(showNextComment, 1300);
    }, 5000);
  }

  /* ─────────────────────────────────────────
     開く / 閉じる
  ───────────────────────────────────────── */
  /**
   * Zenモードを開く。コメントを収集してWebGLレンダリングとスライドショーを開始する。
   * @returns {void}
   */
  function openZen() {
    comments   = collectComments();
    commentIdx = 0;

    overlay.hidden = false;
    document.body.style.overflow = 'hidden';

    if (!initGL()) {
      canvas.style.display = 'none'; /* WebGL 非対応時はキャンバスを隠す */
    }

    startTime = null;
    raf = requestAnimationFrame(render);
    showNextComment();

    /* Noto Serif JP を遅延ロード */
    if (!document.getElementById('zen-serif-font')) {
      const link = document.createElement('link');
      link.id   = 'zen-serif-font';
      link.rel  = 'stylesheet';
      link.href = 'https://fonts.googleapis.com/css2?family=Noto+Serif+JP:wght@300;400&display=swap';
      document.head.appendChild(link);
    }
  }

  /**
   * Zenモードを閉じる。アニメーションを停止してオーバーレイを非表示にする。
   * @returns {void}
   */
  function closeZen() {
    if (raf)        { cancelAnimationFrame(raf); raf = null; }
    if (slideTimer) { clearTimeout(slideTimer); slideTimer = null; }
    overlay.hidden = true;
    document.body.style.overflow = '';
    commentEl.style.opacity = '0';
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(function () {});
    }
  }

  /* ─────────────────────────────────────────
     フルスクリーン
  ───────────────────────────────────────── */
  /**
   * フルスクリーン表示を切り替える。
   * @returns {void}
   */
  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      overlay.requestFullscreen().catch(function () {});
    } else {
      document.exitFullscreen().catch(function () {});
    }
  }

  /**
   * フルスクリーン状態に応じてボタンアイコンを更新する。
   * @returns {void}
   */
  function updateFsIcon() {
    if (!fsBtn) { return; }
    if (document.fullscreenElement) {
      fsBtn.innerHTML = '<i class="fa-solid fa-compress"></i>';
      fsBtn.title = '全画面を終了';
    } else {
      fsBtn.innerHTML = '<i class="fa-solid fa-expand"></i>';
      fsBtn.title = 'フルスクリーン';
    }
  }

  /* ─────────────────────────────────────────
     イベントリスナー
  ───────────────────────────────────────── */
  if (triggerBtn) { triggerBtn.addEventListener('click', openZen); }
  if (closeBtn)   { closeBtn.addEventListener('click', closeZen); }
  if (fsBtn)      { fsBtn.addEventListener('click', toggleFullscreen); }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !overlay.hidden && !document.fullscreenElement) {
      closeZen();
    }
  });

  document.addEventListener('fullscreenchange', updateFsIcon);

})();
