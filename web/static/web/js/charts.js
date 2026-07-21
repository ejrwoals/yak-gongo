/*
 * 차트 빌더 모듈 — 데이터 입력과 분리된 순수 함수들.
 * 각 함수는 입력 데이터(점 배열·회귀계수 등)만 받아 SVG 엘리먼트를 반환한다.
 * 실데이터/мock 어느 쪽이든 같은 형태의 입력만 주면 동일하게 렌더된다.
 */
window.Charts = (() => {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const FONT = 'Pretendard Variable, Pretendard, sans-serif';

  // React.createElement 대응 SVG 엘리먼트 헬퍼 (camelCase 속성 → kebab-case)
  function h(tag, attrs, ...children) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null) continue;
      if (k === 'style' && typeof v === 'object') { Object.assign(node.style, v); continue; }
      const name = k === 'viewBox' ? k : k.replace(/[A-Z]/g, c => '-' + c.toLowerCase());
      node.setAttribute(name, v);
    }
    for (const child of children.flat()) {
      if (child == null) continue;
      node.append(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return node;
  }

  const svgRoot = (W, H, e) =>
    h('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', style: { display: 'block' }, fontFamily: FONT }, e);

  // 축 상한을 보기 좋은 값으로 올림 (예: 82→100, 187→200)
  function niceCeil(v) {
    if (v <= 0) return 1;
    const pow = Math.pow(10, Math.floor(Math.log10(v)));
    const n = v / pow;
    const nice = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
    return nice * pow;
  }

  // [from, to] 사이를 step 간격으로 (to 포함) 채운 눈금 배열
  function ticks(from, to, step) {
    const out = [];
    for (let v = from; v <= to + 1e-9; v += step) out.push(Math.round(v * 1000) / 1000);
    return out;
  }

  function quantile(sorted, q) {
    if (!sorted.length) return null;
    const pos = (sorted.length - 1) * q, base = Math.floor(pos), rest = pos - base;
    return sorted[base + 1] !== undefined ? sorted[base] + rest * (sorted[base + 1] - sorted[base]) : sorted[base];
  }

  const regLabel = (reg) => 'y = ' + reg.slope.toFixed(4) + 'x ' + (reg.intercept < 0 ? '- ' + Math.abs(reg.intercept).toFixed(3) : '+ ' + reg.intercept.toFixed(3));

  // 주당 근무시간 히스토그램 — 입력: [[시간, 공고수], …]
  function buildHistogram(hist) {
    const W = 960, H = 430, L = 56, R = 24, T = 34, B = 56, pw = W - L - R, ph = H - T - B;
    const maxCnt = hist.reduce((m, [, c]) => Math.max(m, c), 0);
    const ymax = niceCeil(maxCnt), yt = ticks(0, ymax, ymax / 5);
    const slot = pw / hist.length, bw = slot * 0.58;
    const e = [];
    e.push(h('rect', { x: L, y: T, width: pw, height: ph, fill: '#FFFFFF', stroke: '#D9D9D2' }));
    yt.forEach(v => { const y = T + ph - (v / ymax) * ph; e.push(h('line', { x1: L, y1: y, x2: L + pw, y2: y, stroke: '#EDEDE7' })); e.push(h('text', { x: L - 8, y: y + 4, textAnchor: 'end', fontSize: 11, fill: '#9A9A92' }, String(v))); });
    hist.forEach(([hr, cnt], i) => {
      const cx = L + i * slot + slot / 2, bh = (cnt / ymax) * ph, by = T + ph - bh;
      e.push(h('rect', { x: cx - bw / 2, y: by, width: bw, height: bh, fill: '#DCC04E', rx: 1 }));
      e.push(h('text', { x: cx, y: by - 5, textAnchor: 'middle', fontSize: 10, fill: '#6B6B62' }, cnt + '개'));
      e.push(h('text', { x: cx, y: T + ph + 15, textAnchor: 'middle', fontSize: 9.5, fill: '#8A8A82' }, String(hr)));
    });
    e.push(h('text', { x: L + pw / 2, y: H - 6, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62' }, '주당 근무 시간 (단위 : 시간)'));
    e.push(h('text', { x: 15, y: T + ph / 2, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62', transform: 'rotate(-90 15 ' + (T + ph / 2) + ')' }, '공고 수'));
    return svgRoot(W, H, e);
  }

  // 시급/월급/지역 산점도 — 입력: pts [{x, y, month, region, col}], mode 'all'|'month'|'region', reg {slope, intercept}
  // opts (선택): {xRange:[min,max], xStep, wageRange:[min,max], lineRange:[from,to]} — 기본값은 풀타임 기준
  function buildScatter(pts, mode, reg, opts) {
    opts = opts || {};
    const W = 960, H = 500, L = 60, R = 28, T = 34, B = 56, pw = W - L - R, ph = H - T - B;
    const month = mode === 'month';
    const xmin = opts.xRange ? opts.xRange[0] : 33;
    const xmax = opts.xRange ? opts.xRange[1] : 62;
    const xStep = opts.xStep || 1;
    const lineFrom = opts.lineRange ? opts.lineRange[0] : 36;
    const lineTo = opts.lineRange ? opts.lineRange[1] : 60;
    let ymin, ymax, yt;
    if (month) {
      const ms = pts.map(p => p.month).filter(v => v != null);
      ymin = Math.floor(Math.min(...ms) / 50) * 50;
      ymax = Math.ceil(Math.max(...ms) / 50) * 50;
      yt = ticks(ymin, ymax, 50);
    } else {
      const wr = opts.wageRange || [1.8, 4.7];
      ymin = wr[0]; ymax = wr[1];
      yt = ticks(Math.ceil(ymin * 2) / 2, Math.floor(ymax * 2) / 2, 0.5);
    }
    const mapX = x => L + ((x - xmin) / (xmax - xmin)) * pw;
    const mapY = y => T + (1 - ((y - ymin) / (ymax - ymin))) * ph;
    const regY = x => reg.slope * x + reg.intercept;
    const e = [];
    e.push(h('rect', { x: L, y: T, width: pw, height: ph, fill: '#ECECE9' }));
    for (let xi = xmin; xi <= xmax; xi += xStep) { const x = mapX(xi); e.push(h('line', { x1: x, y1: T, x2: x, y2: T + ph, stroke: '#E0E0DB' })); e.push(h('text', { x, y: T + ph + 15, textAnchor: 'middle', fontSize: 9, fill: '#8A8A82' }, String(xi))); }
    yt.forEach(v => { const y = mapY(v); e.push(h('line', { x1: L, y1: y, x2: L + pw, y2: y, stroke: '#E0E0DB' })); e.push(h('text', { x: L - 8, y: y + 4, textAnchor: 'end', fontSize: 11, fill: '#8A8A82' }, month ? String(v) : v.toFixed(1))); });
    if (!month) {
      const band = 0.11, top = [], bot = [];
      for (let x = lineFrom; x <= lineTo; x += 2) { top.push([mapX(x), mapY(regY(x) + band)]); bot.push([mapX(x), mapY(regY(x) - band)]); }
      e.push(h('polygon', { points: top.concat(bot.reverse()).map(p => p.join(',')).join(' '), fill: 'rgba(226,59,46,0.13)' }));
    }
    const regionColored = mode === 'region' || opts.colorByRegion;
    pts.forEach(p => { const v = month ? p.month : p.y; e.push(h('circle', { cx: mapX(p.x), cy: mapY(Math.max(ymin, Math.min(ymax, v))), r: 3, fill: regionColored ? p.col : 'rgba(55,55,55,0.40)', opacity: regionColored ? 0.82 : 1 })); });
    const rc = month ? '#2F6FE0' : '#E23B2E';
    if (month && opts.monthCurve) {
      // 월급 회귀 곡선: (시급회귀선) × 시간 × 4.34 (노션 plot_monthly_wage와 동일)
      const pl = [];
      for (let x = lineFrom; x <= lineTo; x += 1) pl.push([mapX(x), mapY((reg.slope * x + reg.intercept) * x * 4.34)]);
      e.push(h('polyline', { points: pl.map(p => p.join(',')).join(' '), fill: 'none', stroke: rc, strokeWidth: 3, strokeLinecap: 'round', strokeLinejoin: 'round' }));
    } else {
      e.push(h('line', { x1: mapX(lineFrom), y1: mapY(regY(lineFrom)), x2: mapX(lineTo), y2: mapY(regY(lineTo)), stroke: rc, strokeWidth: 3, strokeLinecap: 'round' }));
    }
    // 회귀선 수식 — region 모드는 우상단 지역 범례를 피해 그 아래에 배치
    if (!month) e.push(h('text', { x: L + pw - 14, y: mode === 'region' ? T + 138 : T + 58, textAnchor: 'end', fontSize: 14, fill: '#E23B2E', fontWeight: 600 }, '회귀선: ' + regLabel(reg)));
    if (regionColored) {
      // 월급 차트(month)는 우상단에 회귀선 범례가 있으므로 지역 범례를 좌상단에 둔다
      const lx = month ? (L + 14) : (L + pw - 150), ly = T + 12;
      const items = [['서울', '#B0203A'], ['인천', '#E8843C'], ['경기 중부', '#E9CE54'], ['경기 외곽', '#6FB7E0'], ['지방', '#2E3E8F']];
      e.push(h('rect', { x: lx - 10, y: ly - 10, width: 150, height: 118, fill: '#FFFFFF', stroke: '#D9D9D2', rx: 4 }));
      e.push(h('text', { x: lx, y: ly + 4, fontSize: 11, fill: '#555', fontWeight: 600 }, '지역 분류'));
      items.forEach(([nm, col], i) => { const yy = ly + 24 + i * 18; e.push(h('circle', { cx: lx + 6, cy: yy - 4, r: 4, fill: col })); e.push(h('text', { x: lx + 18, y: yy, fontSize: 11, fill: '#555' }, nm)); });
    }
    if (month) {
      const lx = L + pw - 150, ly = T + 10;
      e.push(h('rect', { x: lx - 10, y: ly - 8, width: 150, height: 30, fill: '#FFFFFF', stroke: '#D9D9D2', rx: 4 }));
      e.push(h('line', { x1: lx, y1: ly + 7, x2: lx + 24, y2: ly + 7, stroke: '#2F6FE0', strokeWidth: 3 }));
      e.push(h('text', { x: lx + 30, y: ly + 11, fontSize: 11, fill: '#555' }, 'regression line'));
    }
    e.push(h('text', { x: L + pw / 2, y: H - 6, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62' }, '주당 근무 시간 (단위 : 시간)'));
    e.push(h('text', { x: 15, y: T + ph / 2, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62', transform: 'rotate(-90 15 ' + (T + ph / 2) + ')' }, month ? '월급 (단위 : 만 원)' : '시급 (단위 : 만 원)'));
    return svgRoot(W, H, e);
  }

  // 지역별 분포(IQR) 그래프 — 입력: groups [{nm, mn, n, vals:[시급…]}], ymax, opts {xLabel}
  function buildStrip(groups, ymax, opts) {
    opts = opts || {};
    const W = 960, H = 500, L = 60, R = 28, T = 30, B = 74, pw = W - L - R, ph = H - T - B;
    const ymin = 1.8, yt = [];
    for (let v = 2.0; v <= ymax - 0.05; v += 0.5) yt.push(v);
    const mapY = y => T + (1 - ((y - ymin) / (ymax - ymin))) * ph;
    const colW = pw / groups.length;
    const e = [];
    e.push(h('rect', { x: L, y: T, width: pw, height: ph, fill: '#ECECE9' }));
    yt.forEach(v => { const y = mapY(v); e.push(h('line', { x1: L, y1: y, x2: L + pw, y2: y, stroke: '#E0E0DB' })); e.push(h('text', { x: L - 8, y: y + 4, textAnchor: 'end', fontSize: 11, fill: '#8A8A82' }, v.toFixed(1))); });
    groups.forEach((g, i) => {
      const cx = L + i * colW + colW / 2;
      // 결정적 지터(데이터 순서 기반)로 점을 좌우로 흩뿌림 — 표현용, 데이터와 무관.
      // hash의 소수부만 떼어 [-0.5, 0.5) 범위로 만들어 각 지역 칸 안쪽에만 분포시킨다.
      g.vals.forEach((y, k) => {
        const r = Math.sin((k + 1) * 12.9898) * 43758.5453;
        const j = (r - Math.floor(r)) - 0.5;
        e.push(h('circle', { cx: cx + j * colW * 0.46, cy: mapY(Math.max(ymin, Math.min(ymax, y))), r: 2.4, fill: 'rgba(45,45,45,0.5)' }));
      });
      const sorted = [...g.vals].sort((a, b) => a - b);
      const q1 = quantile(sorted, 0.25), q3 = quantile(sorted, 0.75);
      e.push(h('rect', { x: cx - 26, y: mapY(q3), width: 52, height: mapY(q1) - mapY(q3), fill: '#F4EBA6', opacity: 0.72, stroke: '#D9C84E' }));
      e.push(h('rect', { x: cx - 4, y: mapY(g.mn) - 4, width: 8, height: 8, fill: '#E23B2E' }));
      e.push(h('text', { x: cx + 30, y: mapY(g.mn) + 4, fontSize: 13, fill: '#E23B2E', fontWeight: 600 }, g.mn.toFixed(2)));
      e.push(h('text', { x: cx, y: T + ph + 18, textAnchor: 'middle', fontSize: 10.5, fill: '#8A8A82' }, 'n = ' + g.n));
      e.push(h('text', { x: cx, y: T + ph + 36, textAnchor: 'middle', fontSize: 11.5, fill: '#555' }, g.nm));
    });
    const lx = L + pw - 178, ly = T + 12;
    e.push(h('rect', { x: lx - 10, y: ly - 10, width: 180, height: 58, fill: '#FFFFFF', stroke: '#D9D9D2', rx: 4 }));
    e.push(h('text', { x: lx, y: ly + 4, fontSize: 10.5, fill: '#777' }, '근무형태 : 지속성'));
    e.push(h('circle', { cx: lx + 6, cy: ly + 22, r: 3.5, fill: 'rgba(45,45,45,0.6)' }));
    e.push(h('text', { x: lx + 18, y: ly + 26, fontSize: 11, fill: '#555' }, '구인 공고'));
    e.push(h('rect', { x: lx + 1, y: ly + 35, width: 11, height: 11, fill: '#F4EBA6', stroke: '#D9C84E' }));
    e.push(h('text', { x: lx + 18, y: ly + 45, fontSize: 11, fill: '#555' }, 'IQR (interquartile range)'));
    e.push(h('text', { x: L + pw / 2, y: H - 8, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62' }, opts.xLabel || '지역 대분류'));
    e.push(h('text', { x: 15, y: T + ph / 2, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62', transform: 'rotate(-90 15 ' + (T + ph / 2) + ')' }, '시급 (단위 : 만 원)'));
    return svgRoot(W, H, e);
  }

  // 전체(파트+풀타임) 히스토그램 — 입력: [시간1공고수, …] (1~60h)
  function buildFullHistogram(fh) {
    const W = 960, H = 440, L = 56, R = 24, T = 34, B = 58, pw = W - L - R, ph = H - T - B;
    const ymax = niceCeil(Math.max(...fh)), yt = ticks(0, ymax, ymax / 7);
    const slot = pw / fh.length, bw = slot * 0.6;
    const e = [];
    e.push(h('rect', { x: L, y: T, width: pw, height: ph, fill: '#FFFFFF', stroke: '#D9D9D2' }));
    yt.forEach(v => { const y = T + ph - (v / ymax) * ph; e.push(h('line', { x1: L, y1: y, x2: L + pw, y2: y, stroke: '#EDEDE7' })); e.push(h('text', { x: L - 7, y: y + 4, textAnchor: 'end', fontSize: 10, fill: '#9A9A92' }, String(Math.round(v)))); });
    fh.forEach((cnt, i) => {
      const hr = i + 1, cx = L + i * slot + slot / 2, bh = (cnt / ymax) * ph, by = T + ph - bh;
      e.push(h('rect', { x: cx - bw / 2, y: by, width: bw, height: bh, fill: hr < 36 ? '#2C4C8C' : '#DCC04E' }));
      e.push(h('text', { x: cx, y: by - 4, textAnchor: 'middle', fontSize: 6, fill: '#7A7A72' }, cnt + '개'));
      e.push(h('text', { x: cx, y: T + ph + 13, textAnchor: 'middle', fontSize: 6.5, fill: '#8A8A82' }, String(hr)));
    });
    e.push(h('text', { x: L + pw / 2, y: H - 6, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62' }, '주당 근무 시간 (단위 : 시간)'));
    e.push(h('text', { x: 15, y: T + ph / 2, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62', transform: 'rotate(-90 15 ' + (T + ph / 2) + ')' }, '공고 수'));
    return svgRoot(W, H, e);
  }

  // 전체 근무시간-시급 산점도 — pts [{x, y}], reg {slope, intercept}
  function buildFullScatter(pts, reg) {
    const W = 960, H = 520, L = 60, R = 28, T = 34, B = 58, pw = W - L - R, ph = H - T - B;
    const xmin = 0, xmax = 62, ymin = 1.8, ymax = 5.8;
    const yt = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5];
    const mapX = x => L + ((x - xmin) / (xmax - xmin)) * pw;
    const mapY = y => T + (1 - ((y - ymin) / (ymax - ymin))) * ph;
    const regY = x => reg.slope * x + reg.intercept;
    const e = [];
    e.push(h('rect', { x: L, y: T, width: pw, height: ph, fill: '#ECECE9' }));
    for (let xi = 0; xi <= 60; xi += 5) { const x = mapX(xi); e.push(h('line', { x1: x, y1: T, x2: x, y2: T + ph, stroke: '#E0E0DB' })); e.push(h('text', { x, y: T + ph + 15, textAnchor: 'middle', fontSize: 10, fill: '#8A8A82' }, String(xi))); }
    yt.forEach(v => { const y = mapY(v); e.push(h('line', { x1: L, y1: y, x2: L + pw, y2: y, stroke: '#E0E0DB' })); e.push(h('text', { x: L - 8, y: y + 4, textAnchor: 'end', fontSize: 11, fill: '#8A8A82' }, v.toFixed(1))); });
    const band = 0.1, top = [], bot = [];
    for (let x = 1; x <= 60; x += 2) { top.push([mapX(x), mapY(regY(x) + band)]); bot.push([mapX(x), mapY(regY(x) - band)]); }
    e.push(h('polygon', { points: top.concat(bot.reverse()).map(p => p.join(',')).join(' '), fill: 'rgba(226,59,46,0.13)' }));
    // 36시간 기준으로 풀타임(노랑)·그 미만(파랑) 색 구분 — 위 히스토그램과 일관
    const PART = '#2C4C8C', FULL = '#DCC04E';
    pts.forEach(p => { e.push(h('circle', { cx: mapX(p.x), cy: mapY(Math.max(ymin, Math.min(ymax, p.y))), r: 2.7, fill: p.x >= 36 ? FULL : PART, opacity: 0.55 })); });
    e.push(h('line', { x1: mapX(1), y1: mapY(regY(1)), x2: mapX(60), y2: mapY(regY(60)), stroke: '#E23B2E', strokeWidth: 3, strokeLinecap: 'round' }));
    e.push(h('text', { x: L + pw - 20, y: mapY(4.05), textAnchor: 'end', fontSize: 14, fill: '#E23B2E', fontWeight: 600 }, '회귀선: ' + regLabel(reg)));
    // 색상 범례
    const lx = L + 14, ly = T + 14;
    e.push(h('rect', { x: lx - 8, y: ly - 8, width: 150, height: 48, fill: '#FFFFFF', stroke: '#D9D9D2', rx: 4, opacity: 0.92 }));
    e.push(h('circle', { cx: lx + 4, cy: ly + 6, r: 4, fill: PART }));
    e.push(h('text', { x: lx + 16, y: ly + 10, fontSize: 11, fill: '#555' }, '파트타임 (< 36시간)'));
    e.push(h('circle', { cx: lx + 4, cy: ly + 26, r: 4, fill: FULL }));
    e.push(h('text', { x: lx + 16, y: ly + 30, fontSize: 11, fill: '#555' }, '풀타임 (≥ 36시간)'));
    e.push(h('text', { x: L + pw / 2, y: H - 6, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62' }, '주당 근무 시간 (단위 : 시간)'));
    e.push(h('text', { x: 15, y: T + ph / 2, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62', transform: 'rotate(-90 15 ' + (T + ph / 2) + ')' }, '시급 (단위 : 만 원)'));
    return svgRoot(W, H, e);
  }

  // 지역 색상 (RdYlBu 팔레트 기준 — 노션 등록일별/지역별 산점도와 동일)
  const REGION_COLOR = {
    '서울': '#B0203A', '인천': '#E8843C', '경기 중부': '#E9CE54', '경기 외곽': '#6FB7E0', '지방': '#2E3E8F',
  };

  // 등록일별 시급 산점도 — pts [{date:'YYYY-MM-DD', y, region}], mean, opts {byRegion, yPadTop}
  function buildDateScatter(pts, mean, opts) {
    opts = opts || {};
    const W = 960, H = 520, L = 60, R = 28, T = 30, B = 70, pw = W - L - R, ph = H - T - B;
    const days = pts.map(p => new Date(p.date).getTime());
    const xmin = Math.min(...days), xmax = Math.max(...days);
    const DAY = 86400000;
    const ys = pts.map(p => p.y);
    const ymin = Math.min(...ys) - 0.3, ymax = Math.max(...ys) + (opts.yPadTop || 0.3);
    const mapX = t => L + ((t - xmin) / (xmax - xmin || 1)) * pw;
    const mapY = y => T + (1 - ((y - ymin) / (ymax - ymin))) * ph;
    const yt = ticks(Math.ceil(ymin * 2) / 2, Math.floor(ymax * 2) / 2, 0.5);
    const e = [];
    e.push(h('rect', { x: L, y: T, width: pw, height: ph, fill: '#ECECE9' }));
    yt.forEach(v => { const y = mapY(v); e.push(h('line', { x1: L, y1: y, x2: L + pw, y2: y, stroke: '#E0E0DB' })); e.push(h('text', { x: L - 8, y: y + 4, textAnchor: 'end', fontSize: 11, fill: '#8A8A82' }, v.toFixed(1))); });
    // 월별 세로 눈금 (기간이 길면 라벨 간격을 벌려 ~12개 이하로)
    const d0 = new Date(xmin), end = new Date(xmax);
    const totalMonths = (end.getFullYear() - d0.getFullYear()) * 12 + (end.getMonth() - d0.getMonth()) + 1;
    const monthStep = Math.max(1, Math.ceil(totalMonths / 12));
    let m = new Date(d0.getFullYear(), d0.getMonth(), 1), mi = 0;
    while (m.getTime() <= end.getTime()) {
      const t = m.getTime();
      if (t >= xmin && mi % monthStep === 0) { const x = mapX(t); e.push(h('line', { x1: x, y1: T, x2: x, y2: T + ph, stroke: '#E0E0DB' })); e.push(h('text', { x, y: T + ph + 18, textAnchor: 'end', fontSize: 10, fill: '#8A8A82', transform: 'rotate(-45 ' + x + ' ' + (T + ph + 18) + ')' }, m.getFullYear() + '-' + String(m.getMonth() + 1).padStart(2, '0'))); }
      m = new Date(m.getFullYear(), m.getMonth() + 1, 1); mi++;
    }
    pts.forEach(p => { e.push(h('circle', { cx: mapX(new Date(p.date).getTime()), cy: mapY(Math.max(ymin, Math.min(ymax, p.y))), r: 3, fill: opts.byRegion ? (REGION_COLOR[p.region] || '#2E3E8F') : 'rgba(45,45,45,0.42)', opacity: opts.byRegion ? 0.82 : 1 })); });
    // 회귀 추세선 (빨강) — 최소제곱 (x: xmin 기준 경과일)
    const n = pts.length;
    let sx = 0, sy = 0, sxx = 0, sxy = 0;
    pts.forEach(p => { const x = (new Date(p.date).getTime() - xmin) / DAY; sx += x; sy += p.y; sxx += x * x; sxy += x * p.y; });
    const denom = n * sxx - sx * sx;
    const slope = denom ? (n * sxy - sx * sy) / denom : 0;
    const intercept = n ? (sy - slope * sx) / n : mean;
    const xSpan = (xmax - xmin) / DAY;
    const ry1 = intercept, ry2 = intercept + slope * xSpan;
    e.push(h('line', { x1: mapX(xmin), y1: mapY(ry1), x2: mapX(xmax), y2: mapY(ry2), stroke: '#E23B2E', strokeWidth: 2, opacity: 0.85 }));
    // 연간 변화량 (원 단위) — 추세선 끝점 옆 흰 배경 뱃지로 표기
    const perYearWon = Math.round(slope * 365 * 10000);
    const trendLabel = (perYearWon >= 0 ? '+' : '−') + Math.abs(perYearWon).toLocaleString() + '원/년';
    const kc = (trendLabel.match(/[가-힣]/g) || []).length;
    const bw = 20 + kc * 14 + (trendLabel.length - kc) * 8;
    const bx = L + pw - 4, by = mapY(ry2) - 10;
    e.push(h('rect', { x: bx - bw, y: by - 15, width: bw, height: 21, fill: '#FFFFFF', rx: 4, opacity: 0.75 }));
    e.push(h('text', { x: bx - 8, y: by, textAnchor: 'end', fontSize: 13, fill: '#E23B2E', fontWeight: 600 }, trendLabel));
    // 연도 경계(매년 1월 1일) 세로 구분선 — 연도 구분을 눈에 띄게 (옵션)
    if (opts.yearLines) {
      for (let yr = d0.getFullYear(); ; yr++) {
        const t = new Date(yr, 0, 1).getTime();
        if (t > xmax) break;
        if (t < xmin) continue;
        const x = mapX(t);
        e.push(h('line', { x1: x, y1: T, x2: x, y2: T + ph, stroke: '#8A9086', strokeWidth: 1.4, strokeDasharray: '6 5', opacity: 0.5 }));
        e.push(h('rect', { x: x - 21, y: T + 4, width: 42, height: 17, rx: 4, fill: '#FFFFFF', opacity: 0.85 }));
        e.push(h('text', { x, y: T + 16, textAnchor: 'middle', fontSize: 11, fill: '#6B7167', fontWeight: 700 }, yr + '년'));
      }
    }
    // 범례
    const items = opts.byRegion
      ? [['서울', REGION_COLOR['서울']], ['인천', REGION_COLOR['인천']], ['경기 중부', REGION_COLOR['경기 중부']], ['경기 외곽', REGION_COLOR['경기 외곽']], ['지방', REGION_COLOR['지방']], ['추세선', '#E23B2E']]
      : [['추세선', '#E23B2E']];
    const lineNames = { '추세선': 1 };
    const lh = 18, lw = 110, lx = L + pw - lw - 4, ly = T + 10;
    e.push(h('rect', { x: lx - 8, y: ly - 8, width: lw, height: items.length * lh + 6, fill: '#FFFFFF', stroke: '#D9D9D2', rx: 4, opacity: 0.92 }));
    items.forEach(([nm, col], i) => {
      const yy = ly + 6 + i * lh;
      if (lineNames[nm]) e.push(h('line', { x1: lx, y1: yy - 4, x2: lx + 14, y2: yy - 4, stroke: col, strokeWidth: 2 }));
      else e.push(h('circle', { cx: lx + 7, cy: yy - 4, r: 4, fill: col }));
      e.push(h('text', { x: lx + 20, y: yy, fontSize: 11, fill: '#555' }, nm));
    });
    e.push(h('text', { x: L + pw / 2, y: H - 8, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62' }, '공고 등록일'));
    e.push(h('text', { x: 15, y: T + ph / 2, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62', transform: 'rotate(-90 15 ' + (T + ph / 2) + ')' }, '시급 (단위 : 만 원)'));
    return svgRoot(W, H, e);
  }

  // 지역×시급 버블(원형) 차트 — bubble [{region, y, count}], regionMeans [{nm, mn, n}], opts {star:{region,y}}
  function buildBubble(bubble, regionMeans, opts) {
    opts = opts || {};
    const W = 860, H = 560, L = 62, R = 28, T = 30, B = 74, pw = W - L - R, ph = H - T - B;
    const regions = ['서울', '인천', '경기 중부', '경기 외곽', '지방'];
    const allY = bubble.map(b => b.y);
    const ymin = Math.min(...allY) - 0.3, ymax = Math.max(...allY) + 0.3;
    const colW = pw / regions.length;
    const cx = i => L + i * colW + colW / 2;
    const mapY = y => T + (1 - ((y - ymin) / (ymax - ymin))) * ph;
    const yt = ticks(Math.ceil(ymin * 2) / 2, Math.floor(ymax * 2) / 2, 0.5);
    const e = [];
    e.push(h('rect', { x: L, y: T, width: pw, height: ph, fill: '#ECECE9' }));
    yt.forEach(v => { const y = mapY(v); e.push(h('line', { x1: L, y1: y, x2: L + pw, y2: y, stroke: '#E0E0DB' })); e.push(h('text', { x: L - 8, y: y + 4, textAnchor: 'end', fontSize: 11, fill: '#8A8A82' }, v.toFixed(1))); });
    regions.forEach((_, i) => { const x = cx(i); e.push(h('line', { x1: x, y1: T, x2: x, y2: T + ph, stroke: '#E6E6E1' })); });
    // 버블 (넓이 ∝ count → 반지름 ∝ sqrt(count))
    bubble.forEach(b => {
      const i = regions.indexOf(b.region);
      if (i < 0) return;
      const r = Math.max(7, Math.sqrt(b.count) * 6.2);
      e.push(h('circle', { cx: cx(i), cy: mapY(b.y), r, fill: 'rgba(40,40,40,0.22)' }));
      e.push(h('text', { x: cx(i), y: mapY(b.y) + 4, textAnchor: 'middle', fontSize: Math.min(13, 7 + r * 0.18), fill: '#3A3A38' }, String(b.count)));
    });
    // 지역 평균(빨간 사각형) + 값 + n
    regionMeans.forEach(r => {
      const i = regions.indexOf(r.nm);
      if (i < 0) return;
      e.push(h('rect', { x: cx(i) - 5, y: mapY(r.mn) - 5, width: 10, height: 10, fill: '#E23B2E' }));
      e.push(h('text', { x: cx(i) + 12, y: mapY(r.mn) + 4, fontSize: 14, fill: '#E23B2E', fontWeight: 600 }, r.mn.toFixed(2)));
      e.push(h('text', { x: cx(i), y: T + ph + 18, textAnchor: 'middle', fontSize: 11, fill: '#8A8A82' }, 'n = ' + r.n));
      e.push(h('text', { x: cx(i), y: T + ph + 36, textAnchor: 'middle', fontSize: 12, fill: '#555', fontWeight: 600 }, r.nm));
    });
    // 나의 시급 별표 (옵션)
    if (opts.star) {
      const i = regions.indexOf(opts.star.region);
      if (i >= 0) {
        const sx = cx(i), sy = mapY(opts.star.y), srad = 12, sp = [];
        for (let k = 0; k < 10; k++) { const ang = -Math.PI / 2 + k * Math.PI / 5; const rr = k % 2 === 0 ? srad : srad * 0.45; sp.push([sx + rr * Math.cos(ang), sy + rr * Math.sin(ang)]); }
        e.push(h('polygon', { points: sp.map(p => p.join(',')).join(' '), fill: '#2438D8', stroke: '#fff', strokeWidth: 1.2 }));
      }
    }
    e.push(h('text', { x: L + pw / 2, y: H - 8, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62' }, '지역 대분류'));
    e.push(h('text', { x: 15, y: T + ph / 2, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62', transform: 'rotate(-90 15 ' + (T + ph / 2) + ')' }, '시급 (단위 : 만 원)'));
    return svgRoot(W, H, e);
  }

  // ── 바이올린 공용 헬퍼 ───────────────────────────────────────────
  // 히스토그램 → 가우시안 평활 밀도 (반폭 0~1로 정규화)
  function densityProfile(vals, ymin, ymax) {
    const bins = 44, hb = (ymax - ymin) / bins, c = new Array(bins).fill(0);
    vals.forEach(v => { let b = Math.floor((v - ymin) / hb); b = Math.max(0, Math.min(bins - 1, b)); c[b]++; });
    const sm = c.map((_, i) => { let s = 0, w = 0; for (let k = -4; k <= 4; k++) { const j = i + k; if (j < 0 || j >= bins) continue; const wk = Math.exp(-k * k / 6); s += c[j] * wk; w += wk; } return s / w; });
    const mx = Math.max(...sm, 1e-9);
    return sm.map((d, i) => ({ y: ymin + (i + 0.5) * hb, w: d / mx }));
  }
  const violinPoints = (cx, dens, hw, mapY) => dens.map(p => [cx + p.w * hw, mapY(p.y)])
    .concat(dens.slice().reverse().map(p => [cx - p.w * hw, mapY(p.y)]))
    .map(p => p.join(',')).join(' ');
  // IQR 박스 + 중앙값 + 5~95% 수염
  function boxOverlay(e, cx, vals, mapY, bw) {
    const s = [...vals].sort((a, b) => a - b);
    e.push(h('line', { x1: cx, y1: mapY(quantile(s, 0.95)), x2: cx, y2: mapY(quantile(s, 0.05)), stroke: '#6B7167', strokeWidth: 1.4 }));
    e.push(h('rect', { x: cx - bw, y: mapY(quantile(s, 0.75)), width: bw * 2, height: mapY(quantile(s, 0.25)) - mapY(quantile(s, 0.75)), fill: '#FFFFFF', opacity: 0.9, stroke: '#6B7167', strokeWidth: 1.3, rx: 2 }));
    e.push(h('line', { x1: cx - bw, y1: mapY(quantile(s, 0.5)), x2: cx + bw, y2: mapY(quantile(s, 0.5)), stroke: '#2A302A', strokeWidth: 2 }));
  }
  // 별표(흰 halo)
  function starAt(e, cx, cy, rad) {
    e.push(h('circle', { cx, cy, r: rad + 3, fill: '#fff', opacity: 0.95 }));
    const sp = [];
    for (let k = 0; k < 10; k++) { const ang = -Math.PI / 2 + k * Math.PI / 5; const rr = k % 2 === 0 ? rad : rad * 0.45; sp.push([cx + rr * Math.cos(ang), cy + rr * Math.sin(ang)]); }
    e.push(h('polygon', { points: sp.map(p => p.join(',')).join(' '), fill: '#2438D8', stroke: '#fff', strokeWidth: 1.3 }));
  }

  // "내 시급 비교" 바이올린 + 박스 — groups [{label, mean, n, vals}], myWage(만원)
  // 내 시급 아래는 초록으로 채워 '내가 이긴 비율'을 강조하고, 가로 점선 + 별표로 내 위치를 표시.
  function buildCompare(groups, myWage) {
    const W = 760, H = 470, L = 60, R = 28, T = 30, B = 70, pw = W - L - R, ph = H - T - B;
    const all = groups.flatMap(g => g.vals).concat([myWage]);
    let ymin = Math.min(...all), ymax = Math.max(...all);
    const pad = (ymax - ymin) * 0.1 || 0.5; ymin -= pad; ymax += pad;
    const mapY = y => T + (1 - ((y - ymin) / (ymax - ymin))) * ph;
    const clampY = y => mapY(Math.max(ymin, Math.min(ymax, y)));
    const colW = pw / groups.length;
    const hw = Math.min(colW * 0.40, 130);
    const myY = clampY(myWage);
    const e = [];

    e.push(h('defs', {}, h('clipPath', { id: 'cmp-below' }, h('rect', { x: L, y: myY, width: pw, height: T + ph - myY }))));
    e.push(h('rect', { x: L, y: T, width: pw, height: ph, fill: '#F4F4F0' }));
    ticks(Math.ceil(ymin * 2) / 2, Math.floor(ymax * 2) / 2, 0.5).forEach(v => {
      const y = mapY(v);
      e.push(h('line', { x1: L, y1: y, x2: L + pw, y2: y, stroke: '#E7E7E1' }));
      e.push(h('text', { x: L - 8, y: y + 4, textAnchor: 'end', fontSize: 11, fill: '#9AA098' }, v.toFixed(1)));
    });

    const centers = [];
    groups.forEach((g, i) => {
      const cx = L + i * colW + colW / 2; centers.push(cx);
      const pts = violinPoints(cx, densityProfile(g.vals, ymin, ymax), hw, mapY);
      e.push(h('polygon', { points: pts, fill: '#DADCD5', stroke: '#C2C5BD', strokeWidth: 1 }));
      e.push(h('polygon', { points: pts, fill: 'rgba(27,170,107,0.32)', clipPath: 'url(#cmp-below)' }));
      boxOverlay(e, cx, g.vals, mapY, 13);

      const my2 = mapY(g.mean), pillX = cx + 17, pillW = 42;
      e.push(h('rect', { x: cx - 4, y: my2 - 4, width: 8, height: 8, fill: '#E23B2E' }));
      e.push(h('rect', { x: pillX, y: my2 - 10, width: pillW, height: 20, rx: 6, fill: '#fff', stroke: '#F0C9C4' }));
      e.push(h('text', { x: pillX + pillW / 2, y: my2 + 4, textAnchor: 'middle', fontSize: 12, fill: '#E23B2E', fontWeight: 700 }, g.mean.toFixed(2)));

      e.push(h('text', { x: cx, y: T + ph + 18, textAnchor: 'middle', fontSize: 10.5, fill: '#9AA098' }, 'n = ' + g.n));
      e.push(h('text', { x: cx, y: T + ph + 38, textAnchor: 'middle', fontSize: 12.5, fill: '#555', fontWeight: 700 }, g.label));
    });

    e.push(h('line', { x1: L, y1: myY, x2: L + pw, y2: myY, stroke: '#2438D8', strokeWidth: 2, strokeDasharray: '7 4', opacity: 0.85 }));
    e.push(h('rect', { x: L + 4, y: myY - 19, width: 92, height: 17, rx: 5, fill: '#fff', opacity: 0.92, stroke: '#C9D0F2' }));
    e.push(h('text', { x: L + 9, y: myY - 6, fontSize: 12, fill: '#2438D8', fontWeight: 700 }, '내 시급 ' + myWage.toFixed(2)));
    centers.forEach(cx => starAt(e, cx, myY, 11));

    e.push(h('text', { x: 15, y: T + ph / 2, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62', transform: 'rotate(-90 15 ' + (T + ph / 2) + ')' }, '시급 (단위 : 만 원)'));
    return svgRoot(W, H, e);
  }

  // 지역별(또는 임의 그룹) 시급 분포 바이올린 + 박스 — groups [{nm, mn, n, vals}]
  // opts: {ymin, ymax}(생략 시 자동), star:{region, y}(예시 별표), xLabel(기본 '지역 대분류')
  function buildViolin(groups, opts) {
    opts = opts || {};
    const W = 960, H = 520, L = 60, R = 28, T = 30, B = 74, pw = W - L - R, ph = H - T - B;
    const all = groups.flatMap(g => g.vals).concat(opts.star ? [opts.star.y] : []);
    let ymin = opts.ymin != null ? opts.ymin : Math.min(...all);
    let ymax = opts.ymax != null ? opts.ymax : Math.max(...all);
    const span = (ymax - ymin) || 1;
    if (opts.ymin == null) ymin -= span * 0.06;
    if (opts.ymax == null) ymax += span * 0.06;
    const mapY = y => T + (1 - ((y - ymin) / (ymax - ymin))) * ph;
    const clampY = y => mapY(Math.max(ymin, Math.min(ymax, y)));
    const colW = pw / groups.length;
    const hw = Math.min(colW * 0.40, 135);
    const e = [];
    e.push(h('rect', { x: L, y: T, width: pw, height: ph, fill: '#ECECE9' }));
    ticks(Math.ceil(ymin * 2) / 2, Math.floor(ymax * 2) / 2, 0.5).forEach(v => {
      const y = mapY(v);
      e.push(h('line', { x1: L, y1: y, x2: L + pw, y2: y, stroke: '#E0E0DB' }));
      e.push(h('text', { x: L - 8, y: y + 4, textAnchor: 'end', fontSize: 11, fill: '#8A8A82' }, v.toFixed(1)));
    });
    groups.forEach((g, i) => {
      const cx = L + i * colW + colW / 2;
      e.push(h('polygon', { points: violinPoints(cx, densityProfile(g.vals, ymin, ymax), hw, mapY), fill: '#D8DAD3', stroke: '#C2C5BD', strokeWidth: 1 }));
      boxOverlay(e, cx, g.vals, mapY, 13);
      const my2 = mapY(g.mn), pillX = cx + 17, pillW = 44;
      e.push(h('rect', { x: cx - 4, y: my2 - 4, width: 8, height: 8, fill: '#E23B2E' }));
      e.push(h('rect', { x: pillX, y: my2 - 10, width: pillW, height: 20, rx: 6, fill: '#fff', stroke: '#F0C9C4' }));
      e.push(h('text', { x: pillX + pillW / 2, y: my2 + 4, textAnchor: 'middle', fontSize: 12.5, fill: '#E23B2E', fontWeight: 700 }, g.mn.toFixed(2)));
      e.push(h('text', { x: cx, y: T + ph + 20, textAnchor: 'middle', fontSize: 11, fill: '#8A8A82' }, 'n = ' + g.n));
      e.push(h('text', { x: cx, y: T + ph + 40, textAnchor: 'middle', fontSize: 12.5, fill: '#555', fontWeight: 700 }, g.nm));
    });
    if (opts.star) {
      const idx = groups.findIndex(g => g.nm === opts.star.region);
      if (idx >= 0) starAt(e, L + idx * colW + colW / 2, clampY(opts.star.y), 12);
    }
    e.push(h('text', { x: L + pw / 2, y: H - 8, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62' }, opts.xLabel || '지역 대분류'));
    e.push(h('text', { x: 15, y: T + ph / 2, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62', transform: 'rotate(-90 15 ' + (T + ph / 2) + ')' }, '시급 (단위 : 만 원)'));
    return svgRoot(W, H, e);
  }

  // 근무시간 대비 시급 산점도 — pts [{x:시간, y:시급}], reg {slope, intercept}, my {x, y}(내 위치 별표)
  // 회귀선(빨간선)은 그 근무시간대의 평균 시급. 별이 선보다 위면 시간 대비 시급이 높은 편.
  function buildHoursScatter(pts, reg, my) {
    const W = 760, H = 460, L = 60, R = 28, T = 30, B = 56, pw = W - L - R, ph = H - T - B;
    const xs = pts.map(p => p.x).concat(my ? [my.x] : []);
    const ys = pts.map(p => p.y).concat(my ? [my.y] : []);
    let xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
    const xpad = (xmax - xmin) * 0.06 || 1, ypad = (ymax - ymin) * 0.08 || 0.5;
    xmin -= xpad; xmax += xpad; ymin -= ypad; ymax += ypad;
    const mapX = x => L + ((x - xmin) / (xmax - xmin)) * pw;
    const mapY = y => T + (1 - ((y - ymin) / (ymax - ymin))) * ph;
    const clampY = y => mapY(Math.max(ymin, Math.min(ymax, y)));
    const e = [];
    e.push(h('rect', { x: L, y: T, width: pw, height: ph, fill: '#ECECE9' }));
    // x 눈금 (약 8개, 정수 간격)
    const xstep = Math.max(1, Math.round((xmax - xmin) / 8));
    for (let xv = Math.ceil(xmin / xstep) * xstep; xv <= xmax; xv += xstep) {
      const x = mapX(xv);
      e.push(h('line', { x1: x, y1: T, x2: x, y2: T + ph, stroke: '#E0E0DB' }));
      e.push(h('text', { x, y: T + ph + 15, textAnchor: 'middle', fontSize: 10, fill: '#8A8A82' }, String(xv)));
    }
    ticks(Math.ceil(ymin * 2) / 2, Math.floor(ymax * 2) / 2, 0.5).forEach(v => {
      const y = mapY(v);
      e.push(h('line', { x1: L, y1: y, x2: L + pw, y2: y, stroke: '#E0E0DB' }));
      e.push(h('text', { x: L - 8, y: y + 4, textAnchor: 'end', fontSize: 11, fill: '#8A8A82' }, v.toFixed(1)));
    });
    pts.forEach(p => e.push(h('circle', { cx: mapX(p.x), cy: clampY(p.y), r: 2.6, fill: 'rgba(55,55,55,0.34)' })));
    // 회귀선 + 밴드 (데이터 x 범위)
    if (reg) {
      const dxmin = Math.min(...pts.map(p => p.x)), dxmax = Math.max(...pts.map(p => p.x));
      const regY = x => reg.slope * x + reg.intercept, band = 0.11, top = [], bot = [];
      for (let x = dxmin; x <= dxmax; x += (dxmax - dxmin) / 24 || 1) { top.push([mapX(x), clampY(regY(x) + band)]); bot.push([mapX(x), clampY(regY(x) - band)]); }
      e.push(h('polygon', { points: top.concat(bot.reverse()).map(p => p.join(',')).join(' '), fill: 'rgba(226,59,46,0.13)' }));
      e.push(h('line', { x1: mapX(dxmin), y1: clampY(regY(dxmin)), x2: mapX(dxmax), y2: clampY(regY(dxmax)), stroke: '#E23B2E', strokeWidth: 3, strokeLinecap: 'round' }));
      e.push(h('text', { x: L + pw - 12, y: T + 22, textAnchor: 'end', fontSize: 12.5, fill: '#E23B2E', fontWeight: 600 }, '회귀선 = 시간대별 평균 시급'));
    }
    if (my) starAt(e, mapX(my.x), clampY(my.y), 12);
    e.push(h('text', { x: L + pw / 2, y: H - 6, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62' }, '주당 근무 시간 (단위 : 시간)'));
    e.push(h('text', { x: 15, y: T + ph / 2, textAnchor: 'middle', fontSize: 12, fill: '#6B6B62', transform: 'rotate(-90 15 ' + (T + ph / 2) + ')' }, '시급 (단위 : 만 원)'));
    return svgRoot(W, H, e);
  }

  return { buildHistogram, buildScatter, buildStrip, buildFullHistogram, buildFullScatter, buildDateScatter, buildBubble, buildCompare, buildViolin, buildHoursScatter };
})();
