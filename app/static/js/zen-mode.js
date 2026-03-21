/* zen-mode.js – Zenモード: 拡張可能な複数GLSLシーン + コメントスライドショー */
(function () {
  'use strict';

  const STORAGE_KEY = 'twicome-zen-scene';
  const ATTR_POSITION = 0;

  const VERT = `
attribute vec2 a_pos;
void main() {
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`;

  const NIGHT_SKY_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;
uniform float u_phase;

float h1(float n){n=fract(n*.1031);n*=n+33.33;n*=n+n;return fract(n);}
float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1,0)),f.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),f.x),f.y);}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res;
  float ar = u_res.x / u_res.y;
  float t = u_time;
  float GY = 0.20;

  vec3 skyTop = vec3(.004,.003,.022);
  vec3 skyBot = vec3(.0,.0,.004);
  vec3 col = mix(skyBot, skyTop, uv.y * uv.y);

  float mw = vn(vec2(uv.x * 2.8 + .4, uv.y * 9. + t * .006)) * .22
           + vn(vec2(uv.x * 5.5, uv.y * 18.)) * .11;
  col += vec3(.010,.007,.025) * mw
      * smoothstep(GY + .18, GY + .45, uv.y)
      * smoothstep(0., .3, uv.y * (1. - uv.y) * 4.);

  vec2 mpos = vec2(.74,.80);
  vec2 mvec = (uv - mpos) * vec2(ar, 1.0);
  float md = length(mvec);
  float mr = .030;

  float pa = u_phase * 6.28318;
  float illum = (1. - cos(pa)) * .5;
  float moonLit = 0.0;
  if (md < mr) {
    float muX = mvec.x / mr;
    float muY = mvec.y / mr;
    float disc = sqrt(max(0., 1. - muY * muY));
    float tx = cos(pa) * disc;
    if (u_phase < 0.5) {
      moonLit = smoothstep(tx - .04, tx + .04, muX);
    } else {
      moonLit = 1.0 - smoothstep(-tx - .04, -tx + .04, muX);
    }
  }

  float limb = md < mr ? sqrt(max(0., 1. - (md / mr) * (md / mr))) * .08 : 0.;
  float earthshine = smoothstep(mr + .002, mr - .002, md) * (1. - moonLit) * .018;
  col += vec3(.94,.91,.80) * (
    smoothstep(mr + .002, mr - .002, md) * moonLit * (.90 + limb)
    + exp(-md * 16.) * illum * .18
    + exp(-md * 5.5) * illum * .06
  );
  col += vec3(.72,.82,.98) * earthshine;

  if (md < mr) {
    vec2 mu = mvec / mr;
    float cr = vn(mu * 7. + 1.8) * .040 + vn(mu * 18.) * .016;
    col -= vec3(cr, cr * .84, cr * .60) * smoothstep(mr, .0, md) * moonLit;
  }

  {
    vec2 s;
    vec2 si;
    vec2 sf;
    vec2 jit;
    float h;
    float sp;
    float tw;

    s = uv * vec2(43.,25.);
    si = floor(s);
    sf = fract(s) - .5;
    h = h2(si);
    if (h > .875) {
      jit = vec2(h2(si + .3) - .5, h2(si + .7) - .5) * .6;
      tw = .55 + .45 * sin(t * (1. + h * 3.) + h * 27.);
      sp = smoothstep(.050, .0, length(sf - jit));
      col += mix(vec3(.68,.80,1.), vec3(1.,.88,.62), h2(si + 1.1)) * sp * tw;
    }

    s = uv * vec2(87.,50.);
    si = floor(s);
    sf = fract(s) - .5;
    h = h2(si + 50.);
    if (h > .895) {
      jit = vec2(h2(si + 10.3) - .5, h2(si + 10.7) - .5) * .65;
      tw = .48 + .52 * sin(t * (1.5 + h * 4.) + h * 48.);
      sp = smoothstep(.028, .0, length(sf - jit));
      col += vec3(.72,.84,1.) * sp * tw * .50;
    }

    s = uv * vec2(178.,100.);
    si = floor(s);
    sf = fract(s) - .5;
    h = h2(si + 200.);
    if (h > .915) {
      jit = vec2(h2(si + 20.3) - .5, h2(si + 20.7) - .5) * .6;
      sp = smoothstep(.020, .0, length(sf - jit));
      col += vec3(.56,.60,.82) * sp * .26;
    }
  }

  if (uv.y < GY + .01) {
    float D = 150.;
    float ci0 = floor(uv.x * D);
    for (int layer = 0; layer < 3; layer++) {
      float lf = float(layer);
      float ls = lf * 200.;
      float lsc = .74 + lf * .22;
      for (int di = 0; di < 3; di++) {
        float ci = ci0 + float(di) - 1.;
        for (int bi = 0; bi < 2; bi++) {
          float bf = float(bi);
          float seed = ci + ls + bf * 73.;
          float bh = (.09 + h1(seed) * .11) * lsc;
          float bw = .0016 + h1(seed + 100.) * .0018;
          float bx = (ci + bf * .5 + .25 + (h1(seed + 50.) - .5) * .40) / D;
          float sw = sin(bx * 14. + t * (.75 + h1(seed + 150.) * .85)) * .012;
          float inB = step(uv.y, bh);
          float prog = min(uv.y / max(bh, .0001), 1.);
          float tapW = max(bw * (1. - prog), .0001);
          float bendX = bx + sw * prog * prog;
          float dx = abs(uv.x - bendX);
          float a = (1. - smoothstep(tapW * .3, tapW, dx)) * inB;
          float br = .007 + prog * .021 + lf * .004;
          col = mix(col, vec3(br * .58, br, br * .52 + prog * .007), a * .97);
        }
      }
    }
  }

  vec2 vp = uv - .5;
  col *= clamp(1. - dot(vp * vec2(1.5, 1.3), vp * vec2(1.5, 1.3)) * .7, 0., 1.);
  col = col / (col + .07);
  gl_FragColor = vec4(col, 1.);
}
`;

  const RAIN_WINDOW_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;

float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1,0)),f.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),f.x),f.y);}

float rainField(vec2 uv, float t, float density, float slant, float speed, float cutoff) {
  vec2 p = vec2(
    uv.x * density + uv.y * density * slant,
    uv.y * density * .82 + t * speed
  );
  vec2 id = floor(p);
  vec2 st = fract(p) - .5;
  float seed = h2(id);
  float active = smoothstep(cutoff, 1.0, seed);
  float width = mix(.008, .026, h2(id + vec2(4.3, 1.7)));
  float line = 1.0 - smoothstep(width, width * 2.4, abs(st.x + (seed - .5) * .12));
  float tail = 1.0 - smoothstep(.04, .54, abs(st.y));
  float translucency = mix(.42, .82, h2(id + vec2(8.1, 2.6)));
  return line * tail * active * translucency;
}

float waveCurve(float w) {
  float s = sin(w);
  return s * abs(s) * abs(s);
}

vec3 rainLayer(vec2 baseUv, float time, float scale, vec2 shift) {
  vec2 aspect = vec2(2.0, 1.0);
  vec2 uv = (baseUv * 2.0 - 1.0) * vec2(u_res.x / u_res.y, 1.0);
  uv *= scale * aspect;
  uv += shift;
  uv.y += time * .22;

  vec2 gv = fract(uv) - .5;
  vec2 id = floor(uv);
  float n = h2(id + shift);
  float active = smoothstep(.46, .94, n);
  float t = time + n * 6.28318;
  float w = baseUv.y * 12.0 + shift.x * .35 + n * 8.0;
  float x = (n - .5) * .78;
  x += (.36 - abs(x)) * waveCurve(w);
  float y = -sin(t + sin(t + sin(t) * .5)) * .44;
  y -= (gv.x - x) * (gv.x - x);

  vec2 dropPos = (gv - vec2(x, y)) / aspect;
  float drop = smoothstep(.055, .026, length(dropPos));
  vec2 trailPos = (gv - vec2(x, time * .22)) / aspect;
  trailPos.y = (fract(trailPos.y * 8.0) - .5) / 8.0;
  float trail = smoothstep(.028, .010, length(trailPos));
  float fogTrail = smoothstep(-.05, .05, dropPos.y);
  fogTrail *= smoothstep(.50, y, gv.y);
  trail *= fogTrail;
  fogTrail *= smoothstep(.055, .025, abs(dropPos.x));

  drop *= active;
  trail *= active;
  fogTrail *= active;

  vec2 offs = dropPos * drop + trailPos * trail;
  float clarity = clamp(fogTrail + drop * .45 + trail * .25, 0.0, 1.0);
  return vec3(offs, clarity);
}

float windowFrame(vec2 uv) {
  float left = 1.0 - smoothstep(0.0, .05, uv.x);
  float right = smoothstep(.95, 1.0, uv.x);
  float sill = 1.0 - smoothstep(0.0, .05, uv.y);
  return clamp(left + right + sill * .75, 0.0, 1.0);
}

vec3 rainyBackdrop(vec2 uv, float t) {
  vec3 skyBot = vec3(.020,.030,.050);
  vec3 skyTop = vec3(.11,.15,.21);
  vec3 col = mix(skyBot, skyTop, clamp(uv.y * .85 + .10, 0.0, 1.0));

  float cloud = vn(vec2(uv.x * 2.2 + .4, uv.y * 3.6 - t * .020));
  cloud += vn(vec2(uv.x * 4.8 + 5.2, uv.y * 7.2 + 1.4)) * .45;
  col += vec3(.035,.045,.055) * smoothstep(.48, .94, cloud) * (.18 + uv.y * .28);

  float horizon = smoothstep(0.0, .32, uv.y + vn(vec2(uv.x * 6.0, 8.0)) * .06 - .04);
  col *= mix(.48, 1.0, horizon);

  vec2 s = uv * vec2(14., 7.);
  vec2 si = floor(s);
  vec2 sf = fract(s) - .5;
  float h = h2(si + vec2(10.3, 4.1));
  if (h > .93) {
    vec2 jitter = vec2(h2(si + vec2(1.7, 2.4)) - .5, h2(si + vec2(4.2, 8.5)) - .5) * .68;
    float glow = 1.0 - smoothstep(.08, .34, length(sf - jitter));
    vec3 lightColor = mix(vec3(.95,.66,.34), vec3(.44,.61,.82), h2(si + vec2(7.7, 1.8)));
    col += lightColor * glow * (.025 + .05 * h2(si + vec2(9.4, 2.2))) * (1.0 - smoothstep(.26, .58, uv.y));
  }

  s = uv * vec2(26., 12.);
  si = floor(s);
  sf = fract(s) - .5;
  h = h2(si + vec2(23.1, 7.4));
  if (h > .97) {
    vec2 jitter = vec2(h2(si + vec2(1.1, 6.8)) - .5, h2(si + vec2(8.1, 3.5)) - .5) * .58;
    float glow = 1.0 - smoothstep(.04, .20, length(sf - jitter));
    vec3 lightColor = mix(vec3(.84,.90,1.), vec3(.98,.84,.56), h2(si + vec2(4.5, 9.7)));
    col += lightColor * glow * .035 * (1.0 - smoothstep(.22, .54, uv.y));
  }

  float lampA = exp(-length((uv - vec2(.12,.78)) * vec2(1.5, 3.1)) * 6.5);
  float lampB = exp(-length((uv - vec2(.21,.24)) * vec2(1.7, 2.4)) * 7.0);
  float coolReflect = exp(-length((uv - vec2(.86,.66)) * vec2(1.4, 2.8)) * 6.8);
  col += vec3(.13,.08,.05) * lampA * .7;
  col += vec3(.09,.06,.04) * lampB * .5;
  col += vec3(.04,.07,.11) * coolReflect * .32;

  float rainFar = rainField(uv + vec2(0.0, .06), t, 88., .32, 7.4, .80);
  float rainMid = rainField(uv + vec2(.1, .10), t, 124., .46, 11.6, .84);
  col += vec3(.10,.12,.15) * rainFar * .14;
  col += vec3(.14,.17,.20) * rainMid * .12;

  return col;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res;
  float t = u_time;

  vec3 drops = rainLayer(uv, t, 1.65, vec2(0.0, 0.0)) * .65;
  drops += rainLayer(uv * 1.21 - vec2(9.87, 4.31), t * .96, 2.05, vec2(4.1, 7.3)) * .55;
  drops += rainLayer(uv * 1.37 + vec2(6.54, 1.12), t * 1.07, 2.55, vec2(12.7, 3.9)) * .45;
  drops += rainLayer(uv * 2.10 + vec2(3.21, 5.76), t * 1.16, 3.10, vec2(21.3, 15.1)) * .30;

  vec2 refraction = drops.xy * .65;
  float clarity = clamp(drops.z, 0.0, 1.0);
  vec3 sharp = rainyBackdrop(clamp(uv + refraction, vec2(0.0), vec2(1.0)), t);
  vec3 blurred = rainyBackdrop(clamp(uv + refraction * .35 + vec2(.012, .018), vec2(0.0), vec2(1.0)), t);
  blurred += rainyBackdrop(clamp(uv + refraction * .15 - vec2(.014, .010), vec2(0.0), vec2(1.0)), t);
  blurred *= .5;
  float blurMix = clamp(1.0 - clarity * 1.1, 0.0, 1.0);
  vec3 col = mix(sharp, blurred, blurMix);

  float mist = vn(vec2(uv.x * 80.0, uv.y * 45.0 - t * .04));
  float condensation = smoothstep(.60, .97, vn(uv * vec2(34., 22.) + t * .02));
  col = mix(col, col + vec3(.03,.04,.05), mist * .012);
  col = mix(col, col + vec3(.03,.04,.06), condensation * .018 * (1.0 - clarity));
  col += vec3(.74,.80,.86) * clarity * .05;

  float frame = windowFrame(uv);
  float frameHighlight = exp(-abs(uv.x - .06) * 60.) + exp(-abs(uv.x - .94) * 60.);
  col = mix(col, vec3(.03,.02,.018), frame * .76);
  col += vec3(.18,.12,.08) * frameHighlight * .04 * (.5 + .5 * smoothstep(0.0, 1.0, uv.y));

  vec2 vp = uv - .5;
  col *= clamp(1. - dot(vp * vec2(1.45, 1.2), vp * vec2(1.45, 1.2)) * .65, 0., 1.);
  col = col / (col + .14);
  gl_FragColor = vec4(col, 1.);
}
`;

  const DAWN_LAKE_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;

float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1.,0.)),f.x),mix(h2(i+vec2(0.,1.)),h2(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){
  float v = 0.0;
  v += vn(p) * .5;
  p = p * 2.03 + vec2(3.1, 1.7);
  v += vn(p) * .25;
  p = p * 2.01 + vec2(2.4, 8.3);
  v += vn(p) * .125;
  return v;
}

vec3 dawnSky(vec2 uv, float horizon, float ar, float t) {
  vec3 zenith = vec3(.015,.055,.120);
  vec3 midSky = vec3(.16,.29,.42);
  vec3 horizonGlow = vec3(.94,.63,.43);
  vec3 col = mix(midSky, zenith, smoothstep(horizon + .05, 1.0, uv.y));
  col = mix(col, horizonGlow, exp(-abs(uv.y - horizon) * 16.0) * .72);

  vec2 sunPos = vec2(.54, horizon + .09 + sin(t * .12) * .004);
  vec2 sunVec = (uv - sunPos) * vec2(ar * 1.12, 1.35);
  float sun = exp(-dot(sunVec, sunVec) * 16.0);
  float halo = exp(-length(sunVec) * 4.5);
  col += vec3(1.,.80,.58) * sun * .65;
  col += vec3(.95,.72,.54) * halo * .14;

  float cloud = fbm(vec2(uv.x * 2.6 - t * .012, uv.y * 4.0 + 1.3));
  float veil = smoothstep(.46, .86, cloud);
  veil *= smoothstep(horizon + .02, 1.0, uv.y) * (1.0 - smoothstep(horizon + .34, 1.0, uv.y));
  col = mix(col, col + vec3(.09,.08,.07), veil * .18);
  return col;
}

float mountainRidge(float x) {
  float ridge = .49;
  ridge += (vn(vec2(x * 2.3, 1.4)) - .5) * .12;
  ridge += (vn(vec2(x * 5.8, 8.2)) - .5) * .04;
  ridge += sin(x * 2.4 + .8) * .015;
  return ridge;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res;
  float ar = u_res.x / u_res.y;
  float t = u_time;
  float horizon = .48;
  vec3 col = dawnSky(uv, horizon, ar, t);

  float ridge = mountainRidge(uv.x);
  float mountain = 1.0 - smoothstep(ridge - .006, ridge + .004, uv.y);
  vec3 mountainCol = mix(vec3(.06,.10,.12), vec3(.13,.16,.18), smoothstep(.0, 1.0, uv.x));
  mountainCol += vec3(.25,.18,.10) * exp(-abs(uv.x - .56) * 12.0) * .12;
  col = mix(col, mountainCol, mountain * .92);

  if (uv.y < horizon) {
    float depth = horizon - uv.y;
    float ripA = sin(uv.x * 25.0 - t * .55 + depth * 90.0) * .0035;
    float ripB = sin(uv.x * 12.0 + t * .35 + depth * 58.0) * .0060;
    float drift = (fbm(vec2(uv.x * 3.8, depth * 7.5 - t * .025)) - .5) * .010;
    vec2 reflUv = vec2(uv.x + ripA + drift, horizon + depth * .92 + ripB);
    vec3 refl = dawnSky(clamp(reflUv, vec2(0.0), vec2(1.0)), horizon, ar, t);
    float reflectFade = exp(-depth * 4.8);
    col = mix(vec3(.014,.044,.060), refl, reflectFade * .95);
    float path = exp(-abs(uv.x - .54 + ripA * 12.0) * 10.0);
    col += vec3(1.0,.74,.48) * path * reflectFade * .18;
    float crest = smoothstep(.84, 1.0, sin(depth * 145.0 + uv.x * 22.0 - t * .6) * .5 + .5);
    col += vec3(.36,.42,.48) * crest * .025 * reflectFade;
  }

  float mistBand = exp(-abs(uv.y - (horizon - .01)) * 24.0);
  float mistNoise = fbm(vec2(uv.x * 2.0 - t * .010, uv.y * 12.0 + 4.0));
  col += vec3(.74,.66,.56) * mistBand * smoothstep(.34, .86, mistNoise) * .12;

  vec2 s = uv * vec2(30., 14.);
  vec2 si = floor(s);
  vec2 sf = fract(s) - .5;
  float h = h2(si + vec2(12.4, 7.8));
  if (h > .94) {
    vec2 drift = vec2(
      sin(t * (.10 + h * .16) + h * 18.0),
      cos(t * (.09 + h * .12) + h * 10.0)
    ) * .18;
    float mote = 1.0 - smoothstep(.06, .26, length(sf - drift));
    float fade = smoothstep(horizon - .06, 1.0, uv.y) * (1.0 - smoothstep(.78, 1.0, uv.y));
    vec3 moteCol = mix(vec3(.78,.88,1.0), vec3(1.0,.84,.60), h2(si + 3.2));
    col += moteCol * mote * fade * .18;
  }

  vec2 vp = uv - .5;
  col *= clamp(1.0 - dot(vp * vec2(1.36, 1.12), vp * vec2(1.36, 1.12)) * .54, 0.0, 1.0);
  col = col / (col + .12);
  gl_FragColor = vec4(col, 1.0);
}
`;

  const SAKURA_BREEZE_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;

#define TAU 6.28318530718

// ── ハッシュ / ノイズ ──────────────────────────────────────────────────────────
float h1(float n){n=fract(n*.1031);n*=n+33.33;n*=n+n;return fract(n);}
float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1.,0.)),f.x),mix(h2(i+vec2(0.,1.)),h2(i+vec2(1.,1.)),f.x),f.y);}
// 2オクターブのfbm（旧4オクターブから最適化）
float fbm(vec2 p){return vn(p)*.60+vn(p*2.03+vec2(3.7,1.4))*.40;}

mat2 rot2(float a){float c=cos(a),s=sin(a);return mat2(c,-s,s,c);}

float sdSeg(vec2 p,vec2 a,vec2 b){vec2 pa=p-a,ba=b-a;return length(pa-ba*clamp(dot(pa,ba)/dot(ba,ba),0.,1.));}

// ── 花びら形状（先端が広く基部が細い逆卵形＋先端Vノッチ） ─────────────────────
// p: 花びらローカル座標（+y=先端, -y=茎）
float petalMask(vec2 p) {
  // y位置から先端までの正規化パラメータ（0=基部 1=先端）
  float q  = clamp((p.y + .14) / .46, 0.0, 1.0);
  // 先端ほど半幅が広がる（sqrt で二次的に広がる形）
  float hw = mix(.050, .230, sqrt(q));
  // 輪郭：ソフトな境界
  float body = 1.0 - smoothstep(hw - .022, hw + .022, abs(p.x));
  // 上下マスク：基部フェード + 先端カット
  float yMask = smoothstep(-.18, -.06, p.y) * (1.0 - smoothstep(.28, .38, p.y));
  // 先端のV字切れ込み（桜弁の特徴）
  float vd = abs(p.x) * 2.4 - (p.y - .22) * .55;
  float notch = 1.0 - smoothstep(-.01, .08, vd);
  return clamp(body * yMask * (1.0 - notch * .90), 0.0, 1.0);
}

// ── 夕暮れの桜空（1雲層・星なし） ────────────────────────────────────────────
vec3 sakuraSky(vec2 uv, float t, float ar) {
  // 水平線：珊瑚ピンク → 深藤 → 夜藍
  vec3 col = mix(vec3(.94,.70,.60), vec3(.56,.26,.48), smoothstep(.0,.36,uv.y));
  col = mix(col, vec3(.07,.04,.17), smoothstep(.32,.90,uv.y));

  // 太陽グロー（低め・輝度を抑えて花びらを目立たせる）
  float sd = length((uv - vec2(.64,.34)) * vec2(ar, 1.0));
  col += vec3(1.0,.90,.76) * exp(-sd*sd*10.) * .48;
  col += vec3(.86,.46,.30) * exp(-sd*2.8) * .16;

  // 薄雲（1層のみ・fbm1回）
  float cn = fbm(vec2(uv.x*2.8 - t*.006, uv.y*4.2 + 1.1));
  float cm = smoothstep(.26,.72,uv.y) * (1.0 - smoothstep(.62,.92,uv.y));
  col += mix(vec3(1.0,.82,.78), vec3(.86,.60,.74), uv.y*.8)
       * smoothstep(.50,.80,cn) * cm * .36;

  // 水平線グロー帯
  col += vec3(.26,.09,.15) * exp(-abs(uv.y - .18)*9.) * .16;

  return col;
}

// ── 山稜線（1層） ─────────────────────────────────────────────────────────────
float ridgeLine(float x) {
  return .30 + (vn(vec2(x*2.2, 1.3)) - .5)*.09 + (vn(vec2(x*5.4, 7.8)) - .5)*.026;
}

// ── 枝のシルエット（左右対称） ───────────────────────────────────────────────
float branchMask(vec2 uv) {
  float b = 0.0;
  // 左側
  b += 1.0 - smoothstep(.012,.022,sdSeg(uv, vec2(-.06,.99), vec2(.22,.82)));
  b += 1.0 - smoothstep(.009,.017,sdSeg(uv, vec2(.10,.88),  vec2(.32,.75)));
  b += 1.0 - smoothstep(.007,.013,sdSeg(uv, vec2(.20,.83),  vec2(.40,.71)));
  b += 1.0 - smoothstep(.006,.011,sdSeg(uv, vec2(.30,.77),  vec2(.46,.67)));
  b += 1.0 - smoothstep(.004,.009,sdSeg(uv, vec2(.26,.80),  vec2(.34,.73)));
  b += 1.0 - smoothstep(.004,.008,sdSeg(uv, vec2(.38,.72),  vec2(.48,.65)));
  // 右側
  b += 1.0 - smoothstep(.012,.022,sdSeg(uv, vec2(1.06,.97), vec2(.76,.80)));
  b += 1.0 - smoothstep(.009,.017,sdSeg(uv, vec2(.90,.86),  vec2(.68,.74)));
  b += 1.0 - smoothstep(.007,.013,sdSeg(uv, vec2(.78,.82),  vec2(.58,.70)));
  b += 1.0 - smoothstep(.006,.011,sdSeg(uv, vec2(.68,.75),  vec2(.52,.66)));
  b += 1.0 - smoothstep(.004,.009,sdSeg(uv, vec2(.72,.75),  vec2(.64,.68)));
  b += 1.0 - smoothstep(.004,.008,sdSeg(uv, vec2(.58,.69),  vec2(.50,.64)));
  return clamp(b, 0.0, 1.0);
}

// ── 枝上の花房グロー ──────────────────────────────────────────────────────────
vec3 blossomHalo(vec2 uv, vec2 center, float str, float seed, float ar, float t) {
  vec2 p  = (uv - center) * vec2(ar, 1.0);
  float r = length(p);
  float sh = .70 + .30 * sin(t * (.18 + h1(seed) * .26) + seed * 7.1);
  vec3 hi   = mix(vec3(1.0,.92,.96), vec3(.98,.76,.88), h1(seed + 2.0));
  vec3 deep = mix(vec3(.90,.56,.72), vec3(.72,.34,.56), h1(seed + 5.4));
  return (hi * exp(-r*r*str*1.4) + deep * exp(-r*r*str*.10) * .14) * sh;
}

vec3 branchBlossoms(vec2 uv, float ar, float t) {
  vec3 col = vec3(0.0);
  // 左右各6点
  col += blossomHalo(uv, vec2(.10,.90), 40., 1., ar, t) * .20;
  col += blossomHalo(uv, vec2(.19,.84), 54., 2., ar, t) * .18;
  col += blossomHalo(uv, vec2(.28,.78), 68., 3., ar, t) * .16;
  col += blossomHalo(uv, vec2(.37,.72), 76., 4., ar, t) * .14;
  col += blossomHalo(uv, vec2(.23,.81), 60., 9., ar, t) * .16;
  col += blossomHalo(uv, vec2(.41,.68), 70.,13., ar, t) * .14;
  col += blossomHalo(uv, vec2(.90,.89), 40., 5., ar, t) * .20;
  col += blossomHalo(uv, vec2(.81,.83), 54., 6., ar, t) * .18;
  col += blossomHalo(uv, vec2(.72,.77), 68., 7., ar, t) * .16;
  col += blossomHalo(uv, vec2(.62,.71), 76., 8., ar, t) * .14;
  col += blossomHalo(uv, vec2(.77,.79), 60.,10., ar, t) * .16;
  col += blossomHalo(uv, vec2(.56,.66), 70.,14., ar, t) * .14;
  return col;
}

// ── 舞い落ちる花びら（アルファ合成・2層×9枚） ───────────────────────────────
// 旧4層×14枚=56ループ → 2層×9枚=18ループ＋加算→α合成で色が鮮明に
vec3 fallingPetals(vec3 bg, vec2 uv, float t, float ar) {
  for (int layer = 0; layer < 2; layer++) {
    float lf  = float(layer);
    float amp = .028 + lf * .018;

    for (int i = 0; i < 9; i++) {
      float seed  = float(i) + lf * 31.7;
      float spd   = mix(.024, .074, h1(seed*4.1+2.)) * (1.0 + lf*.40);
      float tr    = fract(h1(seed*2.7+1.3) + t*spd);

      float py = 1.08 - tr * 1.22;
      float px = fract(
        h1(seed*8.3+5.1)
        + sin(t*(.34 + h1(seed+7.)*.62) + seed*5.7 + tr*(5.8+lf*1.4)) * amp
        + (tr - .5) * .040
      );

      vec2 p  = (uv - vec2(px, py)) * vec2(ar, 1.0);
      float sz = mix(.028, .058, h1(seed*6.2+9.4)) * (1.0 + lf*.46);
      p /= sz;
      p = rot2(seed*TAU + t*mix(-1.,1.,h1(seed*5.1+3.2))*(.28+lf*.18) + tr*4.6) * p;

      float pm   = petalMask(p);
      float fade = smoothstep(.02,.13,tr) * (1.0 - smoothstep(.80,1.0,tr));

      // 鮮やかな桜色：深みのあるローズピンク（ラベンダー空に埋まらないよう彩度高め）
      vec3 pc = mix(vec3(.96,.62,.78), vec3(.82,.34,.58), h1(seed*9.+4.8));
      // 中心に深紅の陰影
      pc = mix(pc, vec3(.60,.16,.40), exp(-length(p*.85)*1.3) * .38);
      // 縁の輝き（明るい桜色）
      pc += vec3(.18,.06,.10) * exp(-length(p)*1.6) * .14;

      // アルファ合成（遠層:0.60, 近層:0.88）→より不透明にして視認性向上
      float alpha = pm * fade * mix(.60, .88, lf);
      bg = mix(bg, pc, alpha);
      // 柔らかいグロー（加算）
      bg += vec3(.98,.86,.92) * exp(-length(p)*2.4) * .022 * fade * (.4 + lf*.6);
    }
  }
  return bg;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res;
  float ar = u_res.x / u_res.y;
  float t  = u_time;

  // ── 空 ──
  vec3 col = sakuraSky(uv, t, ar);

  // ── 山（1層・大気遠近付き） ──
  float r   = ridgeLine(uv.x);
  float mtn = 1.0 - smoothstep(r - .008, r + .006, uv.y);
  vec3 mc   = mix(vec3(.10,.06,.14), vec3(.20,.11,.18), uv.x);
  mc = mix(mc, mix(col, mc, .48), smoothstep(r - .14, r, uv.y) * .52);
  col = mix(col, mc, mtn * .94);

  // ── 山裾の霞 ──
  float mist = exp(-abs(uv.y - (r + .014)) * 18.0);
  col += vec3(.90,.72,.80) * mist * smoothstep(.28,.76, fbm(vec2(uv.x*2.2 - t*.007, uv.y*10.+2.2))) * .22;

  // ── 地面 ──
  float gnd = 1.0 - smoothstep(.08,.17, uv.y + (vn(vec2(uv.x*3., 2.1)) - .5)*.03);
  col = mix(col, mix(vec3(.05,.02,.04), vec3(.12,.05,.07), uv.x), gnd * .97);

  // 灯籠グロー
  col += vec3(1.0,.80,.44) * exp(-length((uv - vec2(.22,.13)) * vec2(ar*1.6,2.8)) * 5.4) * .22;
  col += vec3(1.0,.72,.36) * exp(-length((uv - vec2(.78,.15)) * vec2(ar*1.6,2.6)) * 5.8) * .18;

  // ── 枝 ──
  float br = branchMask(uv);
  col = mix(col, mix(vec3(.06,.02,.04), vec3(.12,.05,.07), uv.x), br * .96);
  col += branchBlossoms(uv, ar, t) * (1.0 - br * .12);

  // ── 花びら（アルファ合成） ──
  col = fallingPetals(col, uv, t, ar);

  // ── フィルムグレイン ──
  col += (vn(gl_FragCoord.xy * .58 + t * .14) - .5) * .008;

  // ── ビネット ──
  vec2 vp = uv - .5;
  col *= clamp(1.0 - dot(vp*vec2(1.24,1.06), vp*vec2(1.24,1.06)) * .46, 0.0, 1.0);

  // ── トーンマップ ＋ 彩度調整 ──
  col = col / (col + .10);
  float lum = dot(col, vec3(.299,.587,.114));
  col = mix(vec3(lum), col, 1.16);

  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
`;

  const EMERALD_CONSOLE_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;

float h1(float n){n=fract(n*.1031);n*=n+33.33;n*=n+n;return fract(n);}
float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1.,0.)),f.x),mix(h2(i+vec2(0.,1.)),h2(i+vec2(1.,1.)),f.x),f.y);}

float box(vec2 p, vec2 c, vec2 b) {
  vec2 d = abs(p - c) - b;
  return 1.0 - smoothstep(0.0, .05, max(d.x, d.y));
}

float glyph(vec2 uv, float seed) {
  float g = 0.0;
  float diagScaleA = 1.02 + (h1(seed + 8.0) - .5) * .44;
  float diagScaleB = 1.02 + (h1(seed + 9.0) - .5) * .44;
  float diagA = 1.0 - smoothstep(.09, .16, abs((uv.x - .5) + (uv.y - .5) * diagScaleA));
  float diagB = 1.0 - smoothstep(.09, .16, abs((uv.x - .5) - (uv.y - .5) * diagScaleB));
  float dotA = 1.0 - smoothstep(.05, .12, length(uv - vec2(.5, .5 + (h1(seed + 12.0) - .5) * .28)));

  diagA *= smoothstep(.08, .18, uv.y) * (1.0 - smoothstep(.82, .92, uv.y));
  diagB *= smoothstep(.08, .18, uv.y) * (1.0 - smoothstep(.82, .92, uv.y));

  g += step(.38, h1(seed + 1.0)) * box(uv, vec2(.50, .14), vec2(.24, .028));
  g += step(.52, h1(seed + 2.0)) * box(uv, vec2(.50, .50), vec2(.22, .026));
  g += step(.41, h1(seed + 3.0)) * box(uv, vec2(.50, .86), vec2(.24, .028));
  g += step(.46, h1(seed + 4.0)) * box(uv, vec2(.20, .30), vec2(.032, .18));
  g += step(.44, h1(seed + 5.0)) * box(uv, vec2(.80, .30), vec2(.032, .18));
  g += step(.48, h1(seed + 6.0)) * box(uv, vec2(.20, .70), vec2(.032, .18));
  g += step(.47, h1(seed + 7.0)) * box(uv, vec2(.80, .70), vec2(.032, .18));
  g += step(.64, h1(seed + 10.0)) * diagA * .90;
  g += step(.66, h1(seed + 11.0)) * diagB * .90;
  g += step(.72, h1(seed + 13.0)) * dotA;
  return clamp(g, 0.0, 1.0);
}

vec3 codeRainLayer(vec2 uv, float t, float density, float offset, float brightnessScale) {
  float ar = u_res.x / u_res.y;
  vec2 flowUv = uv;
  vec2 grid = vec2(44.0 * ar * density, 44.0 * density);
  vec2 pos;
  vec2 cell;
  vec2 local;
  float colId;
  float rowFromTop;
  float colSeed;
  float speed;
  float trail;
  float cycle;
  float head;
  float dist;
  float headGlow;
  float tail;
  float pulse;
  float frame;
  float seed;
  float cellGate;
  float symbol;
  float beam;
  float glowStrength;
  vec3 bodyCol;
  vec3 col;

  flowUv.x += sin(uv.y * (5.0 + density * 2.0) + t * .08 + offset) * (.0045 / max(density, .35));
  pos = flowUv * grid;
  cell = floor(pos);
  local = fract(pos);
  colId = cell.x;
  rowFromTop = grid.y - 1.0 - cell.y;
  colSeed = colId + offset * 37.13;
  speed = mix(7.0, 15.5, h1(colSeed * 1.71 + 4.0)) * (0.82 + density * .22);
  trail = mix(8.0, 22.0, h1(colSeed * 2.07 + 12.0));
  cycle = grid.y + trail + 6.0;
  head = mod(t * speed + h1(colSeed + 8.7) * cycle, cycle) - trail;
  dist = rowFromTop - head;

  if (dist < 0.0 || dist > trail) {
    return vec3(0.0);
  }

  headGlow = exp(-abs(dist) * 2.3);
  tail = exp(-dist * mix(.14, .24, h1(colSeed + 17.0)));
  pulse = .82 + .18 * sin(t * (.8 + h1(colSeed + 3.0) * 1.6) + colSeed);
  frame = floor(t * (8.0 + h1(colSeed + 22.0) * 12.0));
  seed = frame * 13.0 + rowFromTop * 19.0 + colSeed * 71.0;
  cellGate = step(.18, h1(seed + 2.0));
  symbol = glyph(local, seed) * cellGate;
  symbol = max(symbol, headGlow * (1.0 - smoothstep(.18, .42, length(local - vec2(.5)))));
  beam = exp(-abs(local.x - .5) * 8.0) * tail * (.05 + headGlow * .04);
  glowStrength = clamp(symbol * tail * pulse * brightnessScale, 0.0, 1.6);
  bodyCol = mix(vec3(.04,.24,.10), vec3(.20,.90,.38), clamp(glowStrength * 1.2, 0.0, 1.0));
  col = bodyCol * glowStrength;
  col += vec3(.88,1.0,.92) * symbol * headGlow * .35 * brightnessScale;
  col += vec3(.06,.32,.14) * beam * brightnessScale;
  return col;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res;
  float t = u_time;
  vec3 bgBot = vec3(.0008,.004,.002);
  vec3 bgTop = vec3(.004,.020,.010);
  vec3 col = mix(bgBot, bgTop, pow(uv.y, .8));
  float haze = vn(vec2(uv.x * 2.4 - t * .03, uv.y * 3.0 + 7.3));
  vec3 rain;
  float sweep;
  float scan;
  vec2 vp;

  haze += vn(vec2(uv.x * 5.6 + 3.1, uv.y * 8.4 - t * .06)) * .5;
  col += vec3(.00,.10,.04) * smoothstep(.52, .95, haze) * .08;
  col += vec3(.00,.15,.06) * exp(-length((uv - vec2(.5,.56)) * vec2(1.1,.75)) * 2.7) * .08;

  rain = codeRainLayer(uv, t * .92, .92, 0.0, 1.0);
  rain += codeRainLayer(uv * vec2(1.0, 1.02) + vec2(.02, 0.0), t * 1.08 + 4.0, 1.28, 17.0, .62);
  rain += codeRainLayer(uv * vec2(1.0, .98) - vec2(.018, 0.0), t * .74 + 11.0, .68, 41.0, .30);
  col += rain;

  sweep = exp(-abs(fract(t * .045 + uv.y * .25) - .5) * 18.0);
  col += vec3(.02,.14,.06) * sweep * .04;

  scan = .94 + .06 * sin(gl_FragCoord.y * 1.35);
  col *= scan;

  vp = uv - .5;
  col *= clamp(1.0 - dot(vp * vec2(1.25, 1.15), vp * vec2(1.25, 1.15)) * .58, 0.0, 1.0);
  col = col / (col + .16);
  gl_FragColor = vec4(col, 1.0);
}
`;

  const SHIROGANE_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;

float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float h1(float n){return h2(vec2(n,n*.6271));}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1.,0.)),f.x),mix(h2(i+vec2(0.,1.)),h2(i+vec2(1.,1.)),f.x),f.y);}

// 雪片：六弁輝き（cos6θをatan不要の多項式で計算）・シマー付き
// dens:密度 spd:落下速度 sz:半径 wnd:横揺れ seed:種
float snowFlake(vec2 uv,float t,float dens,float spd,float sz,float wnd,float seed){
  vec2 p=vec2(uv.x+sin(uv.y*2.6+t*.38+seed*4.1)*wnd, uv.y+t*spd)*dens;
  vec2 id=floor(p); vec2 st=fract(p)-.5;
  vec2 jit=vec2(h2(id+seed)-.5, h2(id+seed+vec2(3.1,7.7))-.5)*.68;
  vec2 d=st-jit; float r=length(d);
  float gate=step(.70,h2(id+seed+vec2(11.3,5.9)));
  // cos(6θ) = Re[(x+iy)^6]/r^6 : atan不使用・精度高・安価
  vec2 nd=d/max(r,.001); float x2=nd.x*nd.x,y2=nd.y*nd.y;
  float cos6=x2*x2*x2-15.*x2*x2*y2+15.*x2*y2*y2-y2*y2*y2;
  float hex=.70+.30*cos6*smoothstep(sz*.9,sz*.1,r);
  float shim=.78+.22*sin(t*(1.6+h1(h2(id+seed))*2.8)+h2(id+seed)*6.28);
  return smoothstep(sz,sz*.05,r)*gate*hex*shim;
}

void main(){
  vec2 uv=gl_FragCoord.xy/u_res;
  float ar=u_res.x/u_res.y;
  float t=u_time;

  // ── 深夜藍の空 ─────────────────────────────────────────────────────────────
  vec3 col=mix(vec3(.022,.040,.095),vec3(.006,.008,.045),uv.y*uv.y);

  // ── 淡いオーロラの残光（ごく繊細な蒼帯） ────────────────────────────────
  float aur=vn(vec2(uv.x*1.5+t*.018,uv.y*7.+2.8))
           +vn(vec2(uv.x*3.4-t*.012,uv.y*14.+5.))*.5;
  col+=vec3(.010,.022,.038)*smoothstep(.42,.84,aur)
      *smoothstep(.54,.62,uv.y)*(1.-smoothstep(.76,.92,uv.y));

  // ── 月（右上・満月寄り） ──────────────────────────────────────────────────
  vec2 mv=(uv-vec2(.74,.84))*vec2(ar,1.);
  float md=length(mv);
  float moon=smoothstep(.028,.024,md);
  float crat=vn(mv/.026*6.+1.8)*.036+vn(mv/.026*14.+4.2)*.018;
  col+=vec3(.92,.91,.82)*moon*(.96-crat*moon);
  // 月暈（内輪・外輪・霞散乱）
  col+=vec3(.56,.66,.88)*exp(-md*10.)*.07;
  col+=vec3(.28,.38,.68)*exp(-md*3.8)*.04;
  col+=vec3(.14,.20,.40)*exp(-md*1.4)*.025;

  // ── 星（2密度層・月明かりで自然に抑制） ─────────────────────────────────
  vec2 ss; vec2 si; vec2 sf; float hh; vec2 jstar;
  ss=uv*vec2(52.,30.); si=floor(ss); sf=fract(ss)-.5; hh=h2(si+10.);
  if(hh>.882){jstar=vec2(h2(si+.3)-.5,h2(si+.7)-.5)*.6;
    col+=vec3(.70,.82,1.)*smoothstep(.042,.0,length(sf-jstar))*(.5+.5*sin(t*(1.1+hh*2.)+hh*22.))*.44;}
  ss=uv*vec2(106.,61.); si=floor(ss); sf=fract(ss)-.5; hh=h2(si+50.);
  if(hh>.902){jstar=vec2(h2(si+10.3)-.5,h2(si+10.7)-.5)*.62;
    col+=vec3(.60,.74,.96)*smoothstep(.026,.0,length(sf-jstar))*.22;}

  // ── 雪雲（月をごく薄く覆う） ─────────────────────────────────────────────
  float cld=vn(vec2(uv.x*2.2+t*.005,uv.y*5.+1.2))*.6
           +vn(vec2(uv.x*4.8-t*.008,uv.y*10.+3.4))*.4;
  float cldM=smoothstep(.58,.82,uv.y)*(1.-smoothstep(.88,1.,uv.y));
  col+=vec3(.016,.022,.038)*smoothstep(.48,.78,cld)*cldM*.6;
  col+=vec3(.04,.06,.14)*exp(-md*2.8)*smoothstep(.48,.68,cld)*cldM*.3;

  // ── 雪山シルエット（雪帽付き） ────────────────────────────────────────────
  float ridge=.38+(vn(vec2(uv.x*2.2,1.4))-.5)*.13
             +(vn(vec2(uv.x*5.8,7.2))-.5)*.042
             +sin(uv.x*3.3+.9)*.016;
  float mtn=1.-smoothstep(ridge-.006,ridge+.005,uv.y);
  vec3 mtnCol=mix(vec3(.030,.044,.076),vec3(.054,.072,.110),uv.x);
  mtnCol+=vec3(.06,.08,.18)*exp(-abs(uv.x-.74)*5.)*.12;
  float cap=smoothstep(ridge+.016,ridge-.002,uv.y)*mtn;
  mtnCol=mix(mtnCol,vec3(.68,.78,.90),cap*.65);
  col=mix(col,mtnCol,mtn*.96);
  // 山稜境界の薄靄
  col+=vec3(.28,.38,.62)*exp(-abs(uv.y-ridge)*28.)*(1.-mtn)*.06;

  // ── 雪原（月明かりに照らされた青白い輝き） ───────────────────────────────
  float snowY=.16+(vn(vec2(uv.x*4.8,2.7))-.5)*.022;
  float gnd=1.-smoothstep(snowY-.006,snowY+.005,uv.y);
  vec3 snowGnd=mix(vec3(.26,.36,.58),vec3(.46,.58,.78),uv.y/max(snowY,.001));
  // 月光の反射筋
  snowGnd+=vec3(.08,.12,.26)*exp(-abs(uv.x-.74)*7.)*(1.-uv.y/max(snowY,.001))*.22;
  // 雪面凹凸テクスチャ
  snowGnd+=(vn(vec2(uv.x*22.+t*.006,uv.y*11.))-.5)*.020;
  col=mix(col,snowGnd,gnd*.97);
  // 積雪縁の微光
  col+=vec3(.42,.56,.76)*exp(-abs(uv.y-snowY)*18.)*(1.-gnd)*.06;

  // ── 降雪：3深度レイヤー（遠・中・近） ────────────────────────────────────
  // アスペクト比補正で円形な雪片を保証
  vec2 uvA=uv*vec2(ar,1.);
  float abv=1.-gnd; // 地面より上のみに降雪を表示
  // 遠景：細かく・速く・多く・淡い
  col+=vec3(.54,.66,.84)*snowFlake(uvA,t,88.,.058,.014,.005, 0.0)*abv*.26;
  // 中景：中程度
  col+=vec3(.70,.80,.94)*snowFlake(uvA,t,48.,.040,.022,.009,17.3)*abv*.42;
  // 近景：大きく・ゆっくり・月明かりで僅かに暖色
  col+=mix(vec3(.82,.88,.98),vec3(.92,.92,.86),exp(-abs(uv.x-.74)*4.)*.4)
      *snowFlake(uvA,t,22.,.026,.036,.015,37.8)*abv*.68;

  // ── フィルムグレイン（ごく微量） ─────────────────────────────────────────
  col+=(vn(gl_FragCoord.xy*.68+t*.16)-.5)*.005;

  // ── ビネット ─────────────────────────────────────────────────────────────
  vec2 vp=uv-.5;
  col*=clamp(1.-dot(vp*vec2(1.38,1.18),vp*vec2(1.38,1.18))*.50,0.,1.);

  // ── トーンマップ（暗部の柔らかさを保持） ────────────────────────────────
  col=col/(col+.08);

  gl_FragColor=vec4(clamp(col,0.,1.),1.);
}
`;

  const SCENES = [
    {
      id: 'night-sky',
      label: '夜空',
      emoji: '🌙',
      fragmentSource: NIGHT_SKY_FRAG
    },
    {
      id: 'rain-window',
      label: '雨の窓辺',
      emoji: '🌧️',
      fragmentSource: RAIN_WINDOW_FRAG
    },
    {
      id: 'dawn-lake',
      label: '朝凪',
      emoji: '🌅',
      fragmentSource: DAWN_LAKE_FRAG
    },
    {
      id: 'sakura-breeze',
      label: '花霞',
      emoji: '🌸',
      fragmentSource: SAKURA_BREEZE_FRAG
    },
    {
      id: 'emerald-console',
      label: '翠の端末',
      emoji: '🖥️',
      fragmentSource: EMERALD_CONSOLE_FRAG
    },
    {
      id: 'shirogane',
      label: '白銀夜',
      emoji: '❄️',
      fragmentSource: SHIROGANE_FRAG
    }
  ];

  const sceneMap = new Map(SCENES.map(function (scene) {
    return [scene.id, scene];
  }));

  const overlay = document.getElementById('zen-overlay');
  const canvas = document.getElementById('zen-canvas');
  const commentEl = document.getElementById('zen-comment');
  const commentWrap = document.getElementById('zen-comment-wrap');
  const closeBtn = document.getElementById('zen-close-btn');
  const fsBtn = document.getElementById('zen-fs-btn');
  const triggerBtn = document.getElementById('zen-mode-btn');
  const themeSwitcher = document.getElementById('zen-theme-switcher');

  if (!overlay || !canvas || !commentEl) {
    return;
  }

  let gl = null;
  let quadBuffer = null;
  let glReady = false;
  let raf = null;
  let sceneStartTime = null;
  const scenePrograms = new Map();
  let currentSceneState = null;
  let currentSceneId = getStoredSceneId();
  let comments = [];
  let commentIdx = 0;
  let slideTimer = null;
  const lunarPhase = getLunarPhase();

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
   * 保存済みのシーンIDを返す。
   * @returns {string} 利用可能なシーンID
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
   * 現在のシーンIDを保存する。
   * @param {string} sceneId - 保存するシーンID
   * @returns {void}
   */
  function storeSceneId(sceneId) {
    try {
      window.localStorage.setItem(STORAGE_KEY, sceneId);
    } catch (error) {
      console.warn('[ZenMode] localStorage write failed:', error);
    }
  }

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

    for (let i = out.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const tmp = out[i];
      out[i] = out[j];
      out[j] = tmp;
    }
    return out.length ? out : ['コメントがありません'];
  }

  /**
   * 次のコメントをフェードイン表示し、一定時間後にフェードアウトして次へ進める。
   * @returns {void}
   */
  function showNextComment() {
    if (!comments.length) {
      return;
    }

    const text = comments[commentIdx % comments.length];
    commentIdx += 1;

    commentEl.style.transition = 'none';
    commentEl.style.opacity = '0';
    commentEl.style.transform = 'translate3d(0, 24px, 0) scale(0.985)';
    commentEl.style.filter = 'blur(14px)';
    commentEl.textContent = text;
    pulseCommentAura();
    void commentEl.offsetHeight;
    commentEl.style.transition =
      'opacity 1.8s ease, transform 2.3s cubic-bezier(0.22, 1, 0.36, 1), filter 2.1s ease';
    commentEl.style.opacity = '1';
    commentEl.style.transform = 'translate3d(0, 0, 0) scale(1)';
    commentEl.style.filter = 'blur(0)';

    slideTimer = setTimeout(function () {
      commentEl.style.transition = 'opacity 1.4s ease, transform 1.8s ease, filter 1.8s ease';
      commentEl.style.opacity = '0';
      commentEl.style.transform = 'translate3d(0, -18px, 0) scale(1.015)';
      commentEl.style.filter = 'blur(10px)';
      slideTimer = setTimeout(showNextComment, 1500);
    }, 5200);
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
   * 指定タイプのGLSLシェーダーをコンパイルして返す。
   * @param {number} type - gl.VERTEX_SHADER または gl.FRAGMENT_SHADER
   * @param {string} src - GLSLソースコード
   * @returns {WebGLShader|null} コンパイル済みシェーダー
   */
  function compileShader(type, src) {
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
   * シーンに対応するGLプログラムを生成または取得する。
   * @param {{id: string, fragmentSource: string}} scene - 使用するシーン定義
   * @returns {{program: WebGLProgram, uniforms: {time: WebGLUniformLocation|null, res: WebGLUniformLocation|null, phase: WebGLUniformLocation|null}}|null} プログラム情報
   */
  function buildSceneProgram(scene) {
    const cached = scenePrograms.get(scene.id);
    if (cached) {
      return cached;
    }

    const vertexShader = compileShader(gl.VERTEX_SHADER, VERT);
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
    gl.bindAttribLocation(program, ATTR_POSITION, 'a_pos');
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
    scenePrograms.set(scene.id, entry);
    return entry;
  }

  /**
   * WebGLコンテキストを初期化する。
   * @returns {boolean} 初期化成功なら true
   */
  function initGL() {
    if (glReady) {
      return true;
    }

    try {
      gl = canvas.getContext('webgl', {
        alpha: false,
        antialias: false,
        depth: false,
        stencil: false,
        premultipliedAlpha: false,
        preserveDrawingBuffer: false,
        powerPreference: 'high-performance'
      }) || canvas.getContext('experimental-webgl');
      if (!gl) {
        return false;
      }

      quadBuffer = gl.createBuffer();
      if (!quadBuffer) {
        return false;
      }

      gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
      gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
        gl.STATIC_DRAW
      );
      gl.disable(gl.DEPTH_TEST);
      gl.disable(gl.BLEND);

      glReady = true;
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
      if (gl) {
        gl.viewport(0, 0, width, height);
      }
    }
  }

  /**
   * シーン切り替えボタンを描画する。
   * @returns {void}
   */
  function renderThemeButtons() {
    if (!themeSwitcher) {
      return;
    }

    themeSwitcher.textContent = '';
    SCENES.forEach(function (scene) {
      const button = document.createElement('button');
      const buttonLabel = `${scene.label}に切り替え`;
      button.type = 'button';
      button.className = 'zen-theme-btn';
      button.dataset.sceneId = scene.id;
      button.title = buttonLabel;
      button.setAttribute('aria-label', buttonLabel);
      button.setAttribute('aria-pressed', scene.id === currentSceneId ? 'true' : 'false');
      button.innerHTML = `<span class="zen-theme-emoji" aria-hidden="true">${scene.emoji}</span>`;
      button.addEventListener('click', function () {
        applyScene(scene.id);
      });
      themeSwitcher.appendChild(button);
    });
  }

  /**
   * 現在選択中のシーンに合わせてボタン状態を更新する。
   * @returns {void}
   */
  function updateThemeButtons() {
    if (!themeSwitcher) {
      return;
    }

    themeSwitcher.querySelectorAll('.zen-theme-btn').forEach(function (button) {
      const isActive = button.dataset.sceneId === currentSceneId;
      button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }

  /**
   * 隣のシーンへ切り替える。
   * @param {number} step - 前後方向。1で次、-1で前
   * @returns {void}
   */
  function selectAdjacentScene(step) {
    if (SCENES.length < 2) {
      return;
    }

    const currentIndex = SCENES.findIndex(function (scene) {
      return scene.id === currentSceneId;
    });
    const nextIndex = (currentIndex + step + SCENES.length) % SCENES.length;
    applyScene(SCENES[nextIndex].id);
  }

  /**
   * シーンを切り替えて、必要ならGLプログラムも差し替える。
   * @param {string} sceneId - 切り替え先のシーンID
   * @returns {void}
   */
  function applyScene(sceneId) {
    const nextScene = sceneMap.get(sceneId) || SCENES[0];
    currentSceneId = nextScene.id;
    overlay.dataset.zenScene = currentSceneId;
    storeSceneId(currentSceneId);
    updateThemeButtons();

    if (!glReady) {
      return;
    }

    const programEntry = buildSceneProgram(nextScene);
    if (!programEntry) {
      if (nextScene.id !== SCENES[0].id) {
        applyScene(SCENES[0].id);
        return;
      }

      canvas.style.display = 'none';
      currentSceneState = null;
      return;
    }

    canvas.style.display = 'block';
    gl.useProgram(programEntry.program);
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
    gl.enableVertexAttribArray(ATTR_POSITION);
    gl.vertexAttribPointer(ATTR_POSITION, 2, gl.FLOAT, false, 0, 0);
    currentSceneState = {
      scene: nextScene,
      programEntry
    };
    sceneStartTime = null;
  }

  /**
   * rAFコールバック。現在アクティブなシーンを描画する。
   * @param {number} ts - requestAnimationFrame のタイムスタンプ
   * @returns {void}
   */
  function render(ts) {
    raf = requestAnimationFrame(render);
    resizeCanvas();
    if (!glReady || !currentSceneState) {
      return;
    }

    if (sceneStartTime === null) {
      sceneStartTime = ts;
    }

    const elapsed = (ts - sceneStartTime) * 0.001;
    const {uniforms} = currentSceneState.programEntry;
    if (uniforms.time) {
      gl.uniform1f(uniforms.time, elapsed);
    }
    if (uniforms.res) {
      gl.uniform2f(uniforms.res, canvas.width, canvas.height);
    }
    if (uniforms.phase) {
      gl.uniform1f(uniforms.phase, lunarPhase);
    }
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  /**
   * Zenモードを開く。
   * @returns {void}
   */
  function openZen() {
    comments = collectComments();
    commentIdx = 0;
    if (slideTimer) {
      clearTimeout(slideTimer);
      slideTimer = null;
    }

    overlay.hidden = false;
    overlay.dataset.zenScene = currentSceneId;
    document.body.style.overflow = 'hidden';
    if (commentWrap) {
      commentWrap.classList.remove('is-pulsing');
    }

    if (initGL()) {
      resizeCanvas();
      applyScene(currentSceneId);
    } else {
      canvas.style.display = 'none';
    }

    if (raf === null) {
      raf = requestAnimationFrame(render);
    }
    showNextComment();
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
   * Zenモードを閉じる。
   * @returns {void}
   */
  function closeZen() {
    if (raf !== null) {
      cancelAnimationFrame(raf);
      raf = null;
    }
    if (slideTimer) {
      clearTimeout(slideTimer);
      slideTimer = null;
    }

    overlay.hidden = true;
    document.body.style.overflow = '';
    commentEl.style.opacity = '0';
    commentEl.style.transform = 'translate3d(0, 18px, 0) scale(0.985)';
    commentEl.style.filter = 'blur(12px)';
    if (commentWrap) {
      commentWrap.classList.remove('is-pulsing');
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
      if (overlay.requestFullscreen) {
        overlay.requestFullscreen().catch(function () {});
      }
      return;
    }
    document.exitFullscreen().catch(function () {});
  }

  /**
   * フルスクリーン状態に応じてボタン表示を更新する。
   * @returns {void}
   */
  function updateFsIcon() {
    if (!fsBtn) {
      return;
    }

    if (document.fullscreenElement) {
      fsBtn.innerHTML = '<i class="fa-solid fa-compress"></i>';
      fsBtn.title = '全画面を終了';
      fsBtn.setAttribute('aria-label', '全画面を終了');
      return;
    }

    fsBtn.innerHTML = '<i class="fa-solid fa-expand"></i>';
    fsBtn.title = 'フルスクリーン';
    fsBtn.setAttribute('aria-label', 'フルスクリーン');
  }

  renderThemeButtons();
  overlay.dataset.zenScene = currentSceneId;
  updateThemeButtons();
  updateFsIcon();

  if (triggerBtn) {
    triggerBtn.addEventListener('click', openZen);
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', closeZen);
  }
  if (fsBtn) {
    fsBtn.addEventListener('click', toggleFullscreen);
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
      closeZen();
      return;
    }
    if (event.key === 'ArrowRight') {
      selectAdjacentScene(1);
      return;
    }
    if (event.key === 'ArrowLeft') {
      selectAdjacentScene(-1);
    }
  });

  document.addEventListener('fullscreenchange', updateFsIcon);
})();
