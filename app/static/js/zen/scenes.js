/* zen/scenes.js – GLSLシェーダー定数とシーン定義 */

export const VERT = `
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

const MATRIX_RAIN_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;

float h1(float n){n=fract(n*.1031);n*=n+33.33;n*=n+n;return fract(n);}
float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}

float glyph(vec2 uv,float seed){
  vec2 g=floor(uv*vec2(5.,7.));
  float px=step(.42,h2(g+seed*vec2(17.3,37.7)));
  float ex=smoothstep(.0,.10,uv.x)*smoothstep(1.,.90,uv.x);
  float ey=smoothstep(.0,.07,uv.y)*smoothstep(1.,.93,uv.y);
  return px*ex*ey;
}

vec3 rain(vec2 uv,float t,float cols,float spd,float seed,float bright){
  float ar=u_res.x/u_res.y;
  float cw=1./cols;
  float ch=cw*ar;
  float rows=1./ch;

  float ci=floor(uv.x*cols);
  float ri=floor((1.-uv.y)/ch);
  vec2 cuv=vec2(fract(uv.x*cols),fract((1.-uv.y)/ch));

  float cs=h1(ci*.3714+seed);
  float speed=(3.+cs*9.)*spd;
  float slen=9.+h1(ci+seed+50.)*18.;
  float per=rows+slen;
  float ph=h1(ci*.529+seed)*per;
  float headR=mod(t*speed+ph,per)-slen;
  float dist=ri-headR;

  float inS=step(0.,dist)*(1.-step(slen,dist));
  float fade=pow(clamp(1.-dist/slen,0.,1.),1.7)*inS;
  float isHead=inS*(1.-smoothstep(0.,1.5,dist));

  float cT=floor(t*(2.+h1(ci*.77+ri*.013+seed)*5.));
  float cId=h1(ci*137.3+ri*59.7+cT*19.7+seed);
  float px=glyph(cuv,cId);

  float gap=.055;
  float brd=smoothstep(0.,gap,cuv.x)*smoothstep(1.,1.-gap,cuv.x)*
            smoothstep(0.,gap,cuv.y)*smoothstep(1.,1.-gap,cuv.y);

  vec3 headCol=vec3(.78,1.,.83);
  vec3 hiCol  =vec3(.09,1.,.26);
  vec3 midCol =vec3(.02,.52,.10);
  vec3 dimCol =vec3(.0,.16,.03);

  vec3 tc=mix(dimCol,mix(midCol,hiCol,fade),fade);
  vec3 fc=mix(tc,headCol,isHead*.88);
  vec3 col=fc*px*brd*fade*bright;

  vec2 gu=cuv-.5;
  float cg=exp(-dot(gu,gu)*7.)*fade*.20;
  col+=vec3(.03,.55,.13)*cg*bright;

  return col;
}

void main(){
  vec2 uv=gl_FragCoord.xy/u_res;
  float t=u_time;

  vec3 col=vec3(0.);
  col+=rain(uv,t,90.,.38,100.,.30);
  col+=rain(uv,t,58.,1.0,  0.,1.0);
  col+=rain(uv,t,34.,1.8,200.,.45);

  col+=vec3(.0,.015,.004)*(1.3-uv.y*.6);

  float scan=1.-.04*pow(sin(gl_FragCoord.y*3.14159),2.);
  col*=scan;

  vec2 vp=uv-.5;
  col*=clamp(1.-dot(vp*vec2(1.5,1.3),vp*vec2(1.5,1.3))*.85,0.,1.);

  col=col/(col+.05);
  gl_FragColor=vec4(col,1.);
}
`;

const SNOW_DAY_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;

float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1,0)),f.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),f.x),f.y);}

float snow(vec2 uv,float t,float density,float speed,float sz,float wind,float seed){
  vec2 p=uv+vec2(t*wind*.015+sin(t*.17+seed)*.030,t*speed);
  p*=density;
  vec2 id=floor(p),st=fract(p)-.5;
  float acc=0.;
  for(int i=-1;i<=1;i++){
    for(int j=-1;j<=1;j++){
      vec2 nid=id+vec2(float(i),float(j));
      float h=h2(nid+seed*.31);
      if(h>.30){
        vec2 jit=vec2(h2(nid+seed+.1)-.5,h2(nid+seed+.2)-.5)*.72;
        jit.x+=sin(h*45.2+t*(.25+h*.45))*.09;
        vec2 d=st-vec2(float(i),float(j))-jit;
        float s=.68+.32*sin(t*(.7+h*1.4)+h*28.3);
        acc+=(1.-smoothstep(0.,sz,length(d)))*s*(.55+h*.45);
      }
    }
  }
  return clamp(acc,0.,1.);
}

float bokeh(vec2 uv,float t,float density,float speed,float sz,float wind,float seed){
  vec2 p=uv+vec2(t*wind*.020+sin(t*.12+seed)*.050,t*speed);
  p*=density;
  vec2 id=floor(p),st=fract(p)-.5;
  float acc=0.;
  for(int i=-1;i<=1;i++){
    for(int j=-1;j<=1;j++){
      vec2 nid=id+vec2(float(i),float(j));
      float h=h2(nid+seed*.31);
      if(h>.40){
        vec2 jit=vec2(h2(nid+seed+.1)-.5,h2(nid+seed+.2)-.5)*.65;
        jit.x+=sin(h*29.8+t*(.18+h*.28))*.12;
        vec2 d=st-vec2(float(i),float(j))-jit;
        acc+=exp(-dot(d,d)/(sz*sz))*(.45+h*.55);
      }
    }
  }
  return clamp(acc,0.,1.);
}

void main(){
  vec2 uv=gl_FragCoord.xy/u_res;
  float ar=u_res.x/u_res.y;
  float t=u_time;
  float tc=t*.35;

  // 暗い曇り空グラデーション（地平線・地面なし）
  vec3 col=mix(vec3(.08,.10,.17),vec3(.20,.23,.30),pow(1.-uv.y,.7));

  // ゆっくり流れる雲テクスチャ
  float c=vn(vec2(uv.x*1.8+tc*.008,uv.y*2.4));
  c+=vn(vec2(uv.x*4.5-tc*.005,uv.y*6.8+2.0))*.50;
  c+=vn(vec2(uv.x*10.+tc*.003,uv.y*14.))*.25;
  c/=1.75;
  col+=vec3(.010,.012,.020)*smoothstep(.38,.78,c);

  // 多層パララックス雪
  vec2 uvA=uv*vec2(ar,1.);
  float sn0=snow(uvA,t,38.,.018,.014,-.30, 0.0);
  float sn1=snow(uvA,t,24.,.030,.022,-.60,43.7);
  float sn2=snow(uvA,t,15.,.050,.036,-1.00,89.1);
  float sn3=snow(uvA,t, 9.,.080,.055,-1.50,137.4);
  float sn4=bokeh(uvA,t, 4.5,.120,.090,-2.00,207.6);

  vec3 sc=vec3(0.);
  sc+=vec3(.52,.58,.72)*sn0*.30;
  sc+=vec3(.68,.74,.86)*sn1*.52;
  sc+=vec3(.82,.88,.95)*sn2*.76;
  sc+=vec3(.91,.95,.99)*sn3*.94;
  sc+=vec3(.95,.97,1.00)*sn4*.70;
  col+=sc;

  // ポストプロセッシング

  // 1. ブルーム — 明るい雪粒の周囲に発光
  float lum=dot(sc,vec3(.299,.587,.114));
  col+=sc*smoothstep(.26,.72,lum)*.58;

  // 2. ビネット（映画的・強め）
  vec2 vp=uv-.5;
  col*=1.-dot(vp*vec2(1.5,1.3),vp*vec2(1.5,1.3))*.88;

  // 3. フィルミックトーンマッピング（ACES近似）
  col=col*(2.51*col+.03)/(col*(2.43*col+.59)+.14);

  // 4. 冷色カラーグレーディング
  col.r*=.87;
  col.g*=.93;
  col.b=min(col.b*1.08,1.);

  // 5. フィルムグレイン（微細）
  float grain=h2(gl_FragCoord.xy+vec2(floor(t*30.)*17.3,floor(t*30.)*31.7))*.030-.015;
  col+=grain;

  gl_FragColor=vec4(clamp(col,0.,1.),1.);
}
`;

// 蛍火: 5層の生物発光パーティクルが有機的なリサジュー軌道で漂う深森の夜
// 最適化: PCGハッシュ(テクスチャ不使用) / exp()SDF / 空セル枝刈り / 解析的ブルーム
const HOTARUBI_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;

float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1,0)),f.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),f.x),f.y);}

// 蛍1層: Lissajous軌道パーティクル
// thr > 0 で空セルを枝刈りし exp() 呼び出しを削減
float flyLayer(vec2 uv,float t,float dens,float sz,float seed,float thr){
  vec2 p=uv*dens;
  vec2 id=floor(p);
  vec2 st=fract(p)-.5;
  float acc=0.;
  for(int ii=-1;ii<=1;ii++){
    for(int jj=-1;jj<=1;jj++){
      vec2 nid=id+vec2(float(ii),float(jj));
      float h=h2(nid+seed);
      if(h>thr){
        float hx=h2(nid+seed+.31);
        float hy=h2(nid+seed+.74);
        float ph=h2(nid+seed+1.17)*6.28318;
        // 黄金比・√2 の周波数比で非周期的な有機的軌跡
        float fx=.42+hx*.78;
        float fy=.37+hy*.72;
        vec2 pos=(vec2(hx,hy)-.5)*.48+vec2(
          sin(t*fx+ph)*.11+sin(t*fx*1.618+ph*1.31)*.05,
          cos(t*fy+ph*.89)*.10+cos(t*fy*1.414+ph*.61)*.04
        );
        vec2 d=st-vec2(float(ii),float(jj))-pos;
        // 生物発光の拍動: 完全消灯なし
        float pulse=.32+.68*max(0.,sin(t*(1.2+h*2.6)+h*37.3));
        acc+=exp(-dot(d,d)/(sz*sz))*pulse*(.28+h*.72);
      }
    }
  }
  return clamp(acc,0.,1.);
}

void main(){
  vec2 uv=gl_FragCoord.xy/u_res;
  float ar=u_res.x/u_res.y;
  float t=u_time*.38;
  vec2 uvA=uv*vec2(ar,1.);

  // 夜の深森: 頂点=深藍, 地平=暗緑
  vec3 col=mix(vec3(.003,.005,.018),vec3(.005,.012,.010),pow(1.-uv.y,.55));
  // 画面外月光による地平線のかすかな蒼い光
  col+=vec3(.018,.022,.028)*exp(-abs(uv.y-.30)*8.)*.5;

  // 揺らぐ霧 (2層FBM)
  float mist=vn(uvA*vec2(1.3,2.8)+vec2(t*.055,0.))
           +vn(uvA*vec2(4.0,5.8)-vec2(t*.034,0.))*.50;
  float mistMask=pow(1.-uv.y,1.5)*.70;
  col+=vec3(.005,.011,.007)*mist*mistMask;

  // 木立シルエット (上部キャノピー)
  float treeH=vn(vec2(uv.x*3.6,0.))*.16
             +vn(vec2(uv.x*9.2,0.))*.05
             +vn(vec2(uv.x*21.,0.))*.02;
  float treeTop=.75+treeH;
  col=mix(col,vec3(.001,.003,.002),smoothstep(treeTop-.016,treeTop,uv.y)*.97);

  // 地面の下草
  float groundH=vn(vec2(uv.x*5.8,9.4))*.06
               +vn(vec2(uv.x*15.,9.4))*.022;
  float groundLine=.075+groundH;
  col=mix(col,vec3(.001,.003,.002),1.-smoothstep(groundLine,groundLine+.020,uv.y));

  // 5深度層の蛍 (遠=密小暗 → 近=粗大明)
  float f0=flyLayer(uvA,t,17.,.018, 0.0,.80);
  float f1=flyLayer(uvA,t,11.,.027,47.,.76);
  float f2=flyLayer(uvA,t, 7.,.040,93.,.72);
  float f3=flyLayer(uvA,t,4.5,.058,141.,.68);
  float f4=flyLayer(uvA,t,2.8,.082,185.,.62);

  // 開空マスク: キャノピーと地面の間だけ飛翔
  float openAir=smoothstep(treeTop,treeTop-.10,uv.y)
               *smoothstep(groundLine,groundLine+.14,uv.y);

  // 生物発光カラーランプ: 遠=冷ティール → 近=暖黄緑
  vec3 c0=vec3(.06,.70,.44);
  vec3 c1=vec3(.16,.82,.36);
  vec3 c2=vec3(.36,.90,.26);
  vec3 c3=vec3(.60,.94,.16);
  vec3 c4=vec3(.80,.97,.08);

  vec3 ff=c0*f0*.11+c1*f1*.22+c2*f2*.48+c3*f3*.80+c4*f4*1.05;
  ff*=openAir;
  col+=ff;

  // 解析的ブルーム: 2乗輝度→ソフトハロ
  float lum=dot(ff,vec3(.299,.587,.114));
  col+=(c2*.55+c3*.45)*lum*lum*2.8;
  // 最前景蛍のタイトコア発光
  col+=c4*f4*f4*openAir*.60;

  // 地面霧の蓄積発光 (霧に蛍の緑光が滲む)
  col+=vec3(.04,.09,.03)*pow(1.-uv.y,2.5)*mistMask*.40;

  // ビネット
  vec2 vp=uv-.5;
  col*=clamp(1.-dot(vp*vec2(1.32,1.14),vp*vec2(1.32,1.14))*.78,0.,1.);

  // ACESフィルミックトーンマッピング
  col=col*(2.51*col+.03)/(col*(2.43*col+.59)+.14);

  // 深森夜カラーグレード: 赤抑制・緑強調
  col.r*=.78;col.g=min(col.g*1.08,1.);col.b*=.90;

  // 微細フィルムグレイン
  col+=h2(gl_FragCoord.xy+vec2(floor(t*19.)*11.3,floor(t*19.)*23.7))*.018-.009;
  gl_FragColor=vec4(clamp(col,0.,1.),1.);
}
`;

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   業火 (Inferno) — 戦場の炎シェーダー
   ドメインワープFBM炎 + 上昇火の粉パーティクル + 煙
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
const INFERNO_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;
uniform float u_phase;

/* ── ハッシュ & スムーズノイズ ── */
float h1(float n){n=fract(n*.1031);n*=n+33.33;n*=n+n;return fract(n);}
float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1,0)),f.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),f.x),f.y);}

/* ── 4オクターブFBM アンロール済み ── */
float fbm4(vec2 p){
  float v=0.;
  v+=.500*vn(p);p=p*2.13+vec2(7.2,3.8);
  v+=.250*vn(p);p=p*2.13+vec2(7.2,3.8);
  v+=.125*vn(p);p=p*2.13+vec2(7.2,3.8);
  v+=.063*vn(p);
  return v*.941;
}

/* ── 上昇火の粉パーティクル レイヤー ──
   【最適化】
   - exp() → max(0,1-d²/sz²)² 二乗フォールオフ: 超越関数を排除
   - 密度カリング if(r1>.22): ~22%の空セルを早期スキップ(HOTARUBIと同手法)
     → grid cellはwavefront幅より大きいため分岐一致率が高く効率的
   【動き】
   - rise y幅 ×0.82 → ×1.6: セル境界を越えて高速上昇
   - 2周波ゆれ: sin(速)＋cos(遅)で蝶のような有機的ゆらぎ
   - spd 2.5〜3×高速化 */
float emberLayer(vec2 uv,float t,float dens,float sz,float seed,float spd){
  vec2 p=uv*dens;
  vec2 id=floor(p);
  vec2 st=fract(p)-.5;
  float acc=0.;
  float sz2=sz*sz;
  for(int ii=-1;ii<=1;ii++){
    for(int jj=-1;jj<=1;jj++){
      vec2 nid=id+vec2(float(ii),float(jj));
      float r1=h2(nid+seed);
      /* 密度カリング: スパースセルをスキップ */
      if(r1>.22){
        float r2=h2(nid+seed+5.1);
        float r3=h2(nid+seed+9.7);
        float r4=h2(nid+seed+14.3);
        /* 高速上昇フェーズ */
        float rise=fract(r1*1.9+t*spd*(0.5+r2*.8));
        /* 2周波横ゆれ: 速い揺れ＋遅いドリフト */
        float drift=(r3-.5)*.28
                   +sin(t*(2.8+r2*1.2)+r1*6.28)*.18
                   +cos(t*(1.1+r4*.7) +r3*3.14)*.08;
        /* y: セルを跨いで高速上昇 (移動幅 0.82→1.6 で約2倍) */
        vec2 pos=vec2(drift,(rise-.5)*1.6);
        vec2 d=st-vec2(float(ii),float(jj))-pos;
        /* 二乗フォールオフ (exp不使用) */
        float g=max(0.,1.-dot(d,d)/sz2);
        float br=(1.-rise*.55)*(0.35+r1*.65)
                *smoothstep(0.,.06,rise)*smoothstep(1.,.65,rise);
        acc+=g*g*br;
      }
    }
  }
  return clamp(acc,0.,1.);
}

void main(){
  vec2 uv=gl_FragCoord.xy/u_res;
  float ar=u_res.x/u_res.y;
  float t=u_time*.65;

  /* ── 漆黒の空 + 地平線の紅蓮グロー ── */
  vec3 col=mix(vec3(.006,.001,.0),vec3(0.),uv.y);
  col+=vec3(.22,.028,.001)*pow(max(0.,1.-uv.y/.20),2.0);
  col+=vec3(.08,.007,.0)*pow(max(0.,1.-uv.y/.54),3.0);

  /* ── 熱揺らぎ歪み ── */
  vec2 uvA=uv*vec2(ar,1.);
  float shimX=vn(uvA*vec2(2.4,3.9)+vec2(t*.53,-t*.78))*.046
             +vn(uvA*vec2(5.7,7.3)-vec2(t*.36,t*.50))*.017;
  vec2 fuv=vec2(uv.x+shimX/ar,uv.y);
  vec2 fuvA=vec2(fuv.x*ar,fuv.y);

  /* ── 炎本体 ── ドメインワープFBM */
  /* yFlame: 画面下=1, 炎最大高(flameH)=0, それ以上=負 → 炎が下から広がる */
  float flameH=.50;
  float yFlame=1.-uv.y/flameH;
  vec2 fp=vec2(fuvA.x*.88,yFlame*1.72-t*.88);
  float warp=fbm4(fp+vec2(t*.14,0.));
  float fn=fbm4(fp+warp*.48);

  float fmask=clamp(fn*.78+yFlame*.56-.24,0.,1.);

  /* 温度 → カラーランプ: 暗赤 → 深紅 → 橙 → 黄橙 → 黄白 → 白 */
  float heat=clamp(fn*.92+yFlame*.32,0.,1.);
  vec3 fCol=vec3(.08,.0,.0);
  fCol=mix(fCol,vec3(.64,.04,.0), smoothstep(.0,.26,heat));
  fCol=mix(fCol,vec3(1.,.22,.01),smoothstep(.26,.46,heat));
  fCol=mix(fCol,vec3(1.,.58,.04),smoothstep(.46,.64,heat));
  fCol=mix(fCol,vec3(1.,.84,.12),smoothstep(.64,.79,heat));
  fCol=mix(fCol,vec3(1.,1.,.65), smoothstep(.79,.91,heat));
  fCol=mix(fCol,vec3(1.,1.,1.),  smoothstep(.91,1.,heat));
  col=mix(col,fCol,clamp(fmask*2.8,0.,1.));

  /* ── 火の粉パーティクル 3層 ──
     sz: 二乗フォールオフはGaussianより急なため×1.3補正
     spd: 2.5〜3×高速化で上昇を視覚的に明確に */
  float e0=emberLayer(fuvA,t,5.5,.024,1.70,.50)*1.3;
  float e1=emberLayer(fuvA,t,9.0,.016,5.30,.72)*.9;
  float e2=emberLayer(fuvA,t,3.5,.038,11.1,.36)*1.6;
  float emb=clamp(e0+e1+e2,0.,1.);
  /* 炎本体底部を隠し、上部では自然に消える */
  float embFade=smoothstep(.06,.18,uv.y)*smoothstep(.96,.75,uv.y);
  vec3 embCol=mix(vec3(1.,.48,.03),vec3(1.,.78,.16),clamp(e0+e2*1.5,0.,1.));
  col+=embCol*emb*embFade*2.2;
  /* 解析的ブルーム */
  col+=embCol*.38*emb*emb*embFade;

  /* ── 煙 (炎上部の暗い揺らぎ) ── */
  float smkF=smoothstep(.38,.70,uv.y)*smoothstep(.92,.42,uv.y);
  vec2 sp=vec2(fuv.x*.9+t*.032,uv.y*1.1-t*.08);
  float sn=vn(sp)*.6+vn(sp*2.1+vec2(3.1,7.4))*.4;
  col=mix(col,col*vec3(.05,.025,.01),sn*smkF*.85);

  /* ── ビネット ── */
  vec2 vp=uv-.5;
  col*=clamp(1.-dot(vp*vec2(1.1,.9),vp*vec2(1.1,.9))*.55,0.,1.);

  /* ── ACESフィルミックトーンマッピング ── */
  col=col*(2.51*col+.03)/(col*(2.43*col+.59)+.14);

  /* ── 微細フィルムグレイン ── */
  col+=h2(gl_FragCoord.xy+floor(t*24.)*vec2(11.3,23.7))*.016-.008;

  gl_FragColor=vec4(clamp(col,0.,1.),1.);
}
`;

const HAKKOU_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;
uniform float u_phase;

float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1,0)),f.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),f.x),f.y);}

/* アスペクト補正距離 */
float adist(vec2 a, vec2 b, float ar) {
  vec2 d = a - b;
  return length(vec2(d.x * ar, d.y));
}

/* 1波源からの減衰サイン波 */
float ripple(vec2 p, vec2 src, float ar, float fq, float spd, float t) {
  float d = adist(p, src, ar);
  return sin(d * fq - t * spd) / (1.0 + d * 5.0);
}

/* 5波源の干渉場 — fqBase でチャンネルごとに虹色ずれ */
float waveField(vec2 p, float ar, float t, float fqBase) {
  float w = 0.0;
  w += ripple(p, vec2(0.50 + cos(t*0.072        )*0.26, 0.50 + sin(t*0.055        )*0.20), ar, fqBase,      1.10, t);
  w += ripple(p, vec2(0.50 + cos(t*0.061+1.257  )*0.24, 0.50 + sin(t*0.048+1.257  )*0.19), ar, fqBase+1.4, 1.25, t);
  w += ripple(p, vec2(0.50 + cos(t*0.083+2.513  )*0.21, 0.50 + sin(t*0.066+2.513  )*0.18), ar, fqBase+2.9, 1.08, t);
  w += ripple(p, vec2(0.50 + cos(t*0.057+3.770  )*0.28, 0.50 + sin(t*0.044+3.770  )*0.21), ar, fqBase+0.7, 1.18, t);
  w += ripple(p, vec2(0.50 + cos(t*0.077+5.027  )*0.18, 0.50 + sin(t*0.060+5.027  )*0.17), ar, fqBase+2.2, 1.32, t);
  return w * 0.20;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res;
  float ar = u_res.x / u_res.y;
  float t = u_time * 0.36;

  /* ── 樽型収差: 端ほど R 外・B 内へずれる ── */
  vec2 ctr = uv - 0.5;
  float barrel = dot(ctr, ctr);
  vec2 uvR = uv + ctr * barrel * 0.050;
  vec2 uvB = uv - ctr * barrel * 0.034;

  /* ── 干渉コースティクス (チャンネル別周波数 → 虹色縞) ── */
  float str = 0.038;
  vec3 col = vec3(
    0.978 + waveField(uvR, ar, t, 12.0) * str,
    0.975 + waveField(uv,  ar, t, 13.5) * str,
    0.970 + waveField(uvB, ar, t, 15.1) * str
  );

  /* ── 漂うパステルカラーハゼ (ローズ / スカイ / ラベンダー) ── */
  float ts = u_time * 0.045;
  vec2 b0 = vec2(0.50 + cos(ts        )*0.27, 0.50 + sin(ts*0.73        )*0.21);
  vec2 b1 = vec2(0.50 + cos(ts*0.67+2.1)*0.25, 0.50 + sin(ts*0.81+1.3)*0.20);
  vec2 b2 = vec2(0.50 + cos(ts*0.53+4.3)*0.23, 0.50 + sin(ts*0.62+2.7)*0.21);
  vec2 e0 = uv - b0; float g0 = exp(-dot(vec2(e0.x*ar,e0.y),vec2(e0.x*ar,e0.y)) / 0.058);
  vec2 e1 = uv - b1; float g1 = exp(-dot(vec2(e1.x*ar,e1.y),vec2(e1.x*ar,e1.y)) / 0.048);
  vec2 e2 = uv - b2; float g2 = exp(-dot(vec2(e2.x*ar,e2.y),vec2(e2.x*ar,e2.y)) / 0.040);
  col = mix(col, vec3(0.980, 0.920, 0.930), g0 * 0.18);
  col = mix(col, vec3(0.920, 0.940, 0.980), g1 * 0.15);
  col = mix(col, vec3(0.950, 0.910, 0.980), g2 * 0.14);

  /* ── 紙の繊維グレイン ── */
  col -= vn(uv * 200.0) * 0.007 + vn(uv * 480.0) * 0.003;

  /* ── ビネット ── */
  col *= 1.0 - dot(ctr * vec2(1.3, 1.0), ctr * vec2(1.3, 1.0)) * 0.65;

  /* ── 時間変化フィルムグレイン ── */
  col += (h2(gl_FragCoord.xy + floor(u_time * 24.0) * vec2(13.1, 29.7)) - 0.5) * 0.010;

  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
`;

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ヴェイパーウェーブ — レトロフューチャー夢幻シェーダー
   80年代の夢: 透遠グリッド + レトロ太陽 + ネオン山脈
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
const VAPORWAVE_FRAG = `
precision mediump float;
uniform float u_time;
uniform vec2 u_res;
uniform float u_phase;

float h1(float n){n=fract(n*.1031);n*=n+33.33;n*=n+n;return fract(n);}
float h2(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yzx+33.33);return fract((q.x+q.y)*q.z);}
float vn(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h2(i),h2(i+vec2(1,0)),f.x),mix(h2(i+vec2(0,1)),h2(i+vec2(1,1)),f.x),f.y);}

void main(){
  vec2 uv=gl_FragCoord.xy/u_res;
  float ar=u_res.x/u_res.y;
  float t=u_time*.75;
  float HZ=.44; /* 地平線 y */

  /* ── 深紫インディゴ空グラデーション ── */
  float skyT=max(0.,( uv.y-HZ)/(1.-HZ));
  vec3 col=mix(
    vec3(.60,.03,.45),   /* 地平: ネオンマゼンタ */
    vec3(.04,.01,.22),   /* 頂点: 深インディゴ */
    pow(skyT,.52)
  );
  /* 星雲状の微細着色 */
  float neb=vn(vec2(uv.x*ar*1.6+t*.05,uv.y*2.1))*.50
           +vn(vec2(uv.x*ar*3.2-t*.03,uv.y*4.0+2.3))*.22;
  col+=mix(vec3(.20,0.,.65),vec3(.55,0.,.75),neb)*.09*skyT;

  /* ── 星 ── */
  float starFade=smoothstep(0.,.28,skyT);
  vec2 sGrid=uv*vec2(ar*75.,75.);
  vec2 sID=floor(sGrid);
  vec2 sST=fract(sGrid)-.5;
  float sr1=h2(sID),sr2=h2(sID+7.31),sr3=h2(sID+13.09);
  float hasStar=step(.81,sr1);
  float twinkle=.52+.48*sin(t*(1.7+sr2*4.2)+sr1*6.28);
  float sD=length(sST-vec2(sr2-.5,sr3-.5)*.52);
  float starBr=max(0.,1.-sD*24.)*hasStar*twinkle;
  vec3 starCol=mix(vec3(.92,.75,1.),vec3(.1,.95,1.),step(.88,sr2));
  starCol=mix(starCol,vec3(1.,.55,1.),step(.94,sr3));
  col+=starCol*starBr*starFade*.88;

  /* ── レトロウェーブ太陽 ── */
  float sunR=.195;
  vec2 sVec=vec2((uv.x-.5)*ar,uv.y-HZ);
  float sDist=length(sVec);
  float inSun=1.-smoothstep(sunR-.004,sunR+.006,sDist);
  float abvHz=step(HZ,uv.y);

  /* グラデーション: 頂=ゴールデン → 中=オレンジ → 底=ホットピンク */
  float sunNY=sVec.y/sunR; /* -1=底面, +1=頂面 */
  vec3 sunG=mix(
    vec3(.95,.03,.58),
    mix(vec3(1.,.38,.04),vec3(1.,.90,.04),smoothstep(0.,1.,sunNY)),
    smoothstep(-1.,0.,sunNY)
  );

  /* ヴェネチアンブラインドストライプ (下部60%に水平帯) */
  float sunUVY=(sunNY+1.)*.5; /* 0=底, 1=頂 */
  float stripeZone=1.-smoothstep(.57,.63,sunUVY);
  float solidStripe=step(.42,fract(sunUVY*9.));
  float sunMask=inSun*abvHz*mix(1.,solidStripe,stripeZone);
  col=mix(col,sunG,sunMask);

  /* 太陽外側グロー */
  float outerD=max(0.,sDist-sunR);
  col+=vec3(.88,.05,.68)*max(0.,1.-outerD/(sunR*.75))*(1.-inSun)*abvHz*.52;
  col+=vec3(1.,.45,.08)*max(0.,1.-outerD/(sunR*.28))*(1.-inSun)*abvHz*.26;

  /* ── ネオン山脈シルエット ── */
  float mx=uv.x*ar*2.5;
  float mh=.06*(.48+.30*sin(mx*2.+.6)+.20*sin(mx*5.1-1.3)
                   +.13*sin(mx*10.7+2.)+.07*sin(mx*21.4-.5));
  float mountTop=HZ+max(0.,mh);
  float inMt=smoothstep(-.001,.003,mountTop-uv.y)*abvHz;
  float ridge=(1.-smoothstep(.001,.007,abs(uv.y-mountTop)))*abvHz;
  col=mix(col,vec3(.06,0.,.20),inMt);
  col+=vec3(.75,0.,1.)*ridge*.75;   /* ネオンパープル稜線 */
  col+=vec3(.90,0.,.80)*ridge*.35;  /* 外側グロー */

  /* ── 透視グリッドフロア ── */
  float belowHz=1.-abvHz;
  float fY=max(.001,HZ-uv.y);
  float floorT=fY/HZ; /* 0=地平, 1=手前 */

  float px=(uv.x-.5)*ar/fY;
  float pz=.42/fY+t*4.5; /* 前進スクロール */
  float gx=abs(fract(px*.28+.5)-.5);
  float gz=abs(fract(pz*.28+.5)-.5);
  float lT=.023;
  float grid=max(1.-smoothstep(0.,lT,gx),1.-smoothstep(0.,lT,gz));

  /* シアン(地平)→ホットピンク(手前)グラデーション */
  vec3 gridC=mix(vec3(.04,.85,1.),vec3(1.,.04,.78),floorT);
  vec3 floorBase=vec3(.018,.004,.095);
  float pulse=.80+.20*pow(sin(u_time*.35)*.5+.5,2.5);
  vec3 floorCol=mix(floorBase,gridC*pulse,grid*.87);
  floorCol+=gridC*grid*.28*pulse; /* ネオングロー */
  /* ソフトグロー帯 */
  floorCol+=gridC*(1.-smoothstep(0.,lT*3.5,min(gx,gz)))*.10;
  /* 地平霧 */
  floorCol=mix(floorCol,vec3(.28,.02,.28),max(0.,1.-floorT*2.3)*.72);
  col=mix(col,floorCol,belowHz);

  /* ── 地平線輝線 ── */
  col+=vec3(1.,.25,.90)*(1.-smoothstep(0.,.004,abs(uv.y-HZ)))*.90;

  /* ── CRTスキャンライン ── */
  col*=.80+.20*sin(gl_FragCoord.y*3.14159);

  /* ── 散発グリッチライン ── */
  float gT=floor(u_time*.6);
  float gActive=step(.91,h1(gT*1.618));
  float gW=.004+h1(gT*2.72)*.009;
  float isGlitch=gActive*(1.-smoothstep(gW*.4,gW,abs(uv.y-h1(gT*3.14))));
  col+=mix(vec3(0.,.9,1.),vec3(1.,0.,.9),h1(gT))*isGlitch*.48;

  /* ── フィルムグレイン ── */
  col+=(h2(gl_FragCoord.xy+floor(u_time*22.)*vec2(14.3,28.9))-.5)*.018;

  /* ── ビネット ── */
  vec2 vp=uv-.5;
  col*=1.-dot(vp*vec2(1.3,1.05),vp*vec2(1.3,1.05))*.78;

  /* ── 彩度ブースト (ヴェイパーウェーブ鮮やかさ) ── */
  float lum=dot(col,vec3(.299,.587,.114));
  col=mix(vec3(lum),col,1.58);

  gl_FragColor=vec4(clamp(col,0.,1.),1.);
}
`;

export const SCENES = [
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
    id: 'matrix-rain',
    label: '電脳雨',
    emoji: '💻',
    fragmentSource: MATRIX_RAIN_FRAG
  },
  {
    id: 'snow-day',
    label: '雪の一日',
    emoji: '❄️',
    fragmentSource: SNOW_DAY_FRAG
  },
  {
    id: 'hotarubi',
    label: '蛍火',
    emoji: '✨',
    fragmentSource: HOTARUBI_FRAG
  },
  {
    id: 'inferno',
    label: '業火',
    emoji: '🔥',
    fragmentSource: INFERNO_FRAG
  },
  {
    id: 'hakkou',
    label: '白光',
    emoji: '🤍',
    fragmentSource: HAKKOU_FRAG
  },
  {
    id: 'vaporwave',
    label: 'ヴェイパー',
    emoji: '🌆',
    fragmentSource: VAPORWAVE_FRAG
  }
];

export const sceneMap = new Map(SCENES.map(function (scene) {
  return [scene.id, scene];
}));
