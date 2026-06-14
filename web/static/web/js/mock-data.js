/*
 * Mock 데이터 모듈 — 차트 빌더(charts.js)의 입력을 생성한다.
 * 실데이터 연동 시 이 파일이 반환하는 값만 실데이터로 교체하면 된다.
 * (차트 빌더는 데이터 입력과 분리된 순수 함수로 유지)
 */
window.MockData = (() => {
  // ===== 메인(홈) 페이지 =====
  const home = {
    lastUpdate: '2026-03-25',
    totalPostings: 3444,
    // 지역별 평균 시급 (만원)
    regionAvg: [
      { name: '서울', v: 3.13 }, { name: '경기', v: 3.20 }, { name: '인천', v: 3.18 },
      { name: '부산', v: 3.30 }, { name: '대구', v: 3.28 }, { name: '대전', v: 3.35 },
      { name: '광주', v: 3.40 }, { name: '강원', v: 3.55 }, { name: '경북', v: 3.45 },
      { name: '제주', v: 3.62 },
    ],
    // 근무형태별 평균 시급 (만원)
    categoryAvg: [
      { name: '전국 평균', v: 3.16, color: '#A0A096' },
      { name: '풀타임', v: 2.67, color: '#2E6FB0' },
      { name: '주말 파트', v: 3.66, color: '#C5891B' },
      { name: '기타 파트', v: 3.24, color: '#3C9A5C' },
      { name: '일회성 단기', v: 3.44, color: '#7B5BC4' },
    ],
  };

  // ===== 풀타임 상세 페이지 =====
  // 지역별 평균 시급 표 + 분포 그래프 입력 (만원)
  const fulltimeRegionMeans = [
    { nm: '서울', mn: 2.39, n: 137 },
    { nm: '인천', mn: 2.71, n: 74 },
    { nm: '경기중부', mn: 2.61, n: 119 },
    { nm: '경기외곽', mn: 2.70, n: 125 },
    { nm: '지방', mn: 2.85, n: 216 },
  ];
  const fulltimeRegionMeansSev = [
    { nm: '서울', mn: 2.59, n: 137 },
    { nm: '인천', mn: 2.94, n: 74 },
    { nm: '경기중부', mn: 2.83, n: 119 },
    { nm: '경기외곽', mn: 2.92, n: 125 },
    { nm: '지방', mn: 3.09, n: 216 },
  ];

  let _fulltime = null;

  // 시드 고정 난수로 생성하는 mock 산점도/분포 데이터
  function getFulltimeData() {
    if (_fulltime) return _fulltime;
    let s = (0x9e3779b9 ^ 20260612) | 0;
    const rnd = () => {
      s = (s + 0x6D2B79F5) | 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const gauss = () => { let x = 0; for (let i = 0; i < 4; i++) x += rnd(); return (x / 4 - 0.5) * 2; };

    // 풀타임 주당 근무시간 히스토그램: [[시간, 공고수], …]
    const hist = [[36,15],[37,11],[38,21],[39,13],[40,49],[41,17],[42,23],[43,15],[44,21],[45,94],[46,43],[47,88],[48,37],[49,33],[50,69],[51,19],[52,42],[53,12],[54,17],[55,18],[56,8],[57,2],[58,2],[59,2],[60,2]];

    // 산점도 점: [{x:근무시간, y:시급, month:월급, region, col}, …]
    const pts = [];
    for (const [hr, cnt] of hist) {
      const n = Math.max(1, Math.round(cnt * 0.72));
      for (let i = 0; i < n; i++) {
        const x = hr + (rnd() - 0.5) * 0.85;
        let y = (-0.0219 * hr + 3.691) + gauss() * 0.5;
        if (rnd() < 0.06) y += gauss() * 0.6; // occasional outliers like the real scatter
        y = Math.max(1.95, Math.min(4.65, y));
        pts.push({ x, y });
      }
    }
    const rw = [['서울',0.20,'#B0203A'],['인천',0.11,'#E8843C'],['경기중부',0.18,'#E9CE54'],['경기외곽',0.19,'#6FB7E0'],['지방',0.32,'#2E3E8F']];
    for (const p of pts) {
      const r = rnd(); let a = 0; p.col = '#2E3E8F'; p.region = '지방';
      for (const [nm, wt, col] of rw) { a += wt; if (r <= a) { p.col = col; p.region = nm; break; } }
      p.month = 9.2 * p.x + 188 + gauss() * 68;
    }

    // 지역별 분포(IQR) 그래프 입력: [{nm, mn:평균, n, vals:[{y, j}]}, …]
    const stripGen = (mean, n) => {
      const arr = []; const m = Math.max(10, Math.round(n * 0.7));
      for (let i = 0; i < m; i++) arr.push({ y: mean + gauss() * 0.27, j: (rnd() - 0.5) });
      return arr;
    };
    const dist = fulltimeRegionMeans.map(({ nm, mn, n }) => ({ nm, mn, n, vals: stripGen(mn, n) }));
    const distSev = fulltimeRegionMeansSev.map(({ nm, mn, n }) => ({ nm, mn, n, vals: stripGen(mn, n) }));

    // 전체(파트+풀타임) 히스토그램: [시간1공고수, …] (1~60h) — 참고 토글용
    const fullHist = [4,120,173,142,87,46,54,81,36,95,65,29,20,26,37,15,11,43,20,107,46,9,27,38,16,31,20,7,42,9,15,12,12,15,10,15,11,21,13,49,17,23,15,21,94,43,88,37,33,69,19,42,12,17,18,8,2,2,2,2];
    const fullPts = [];
    fullHist.forEach((cnt, idx) => {
      const hr = idx + 1;
      const n = Math.max(1, Math.round(cnt * 0.4));
      for (let i = 0; i < n; i++) {
        const x = hr + (rnd() - 0.5) * 0.85;
        let y = (-0.0210 * hr + 3.645) + gauss() * 0.5;
        if (hr < 16) y += Math.abs(gauss()) * 0.55 * (16 - hr) / 15;
        if (rnd() < 0.05) y += gauss() * 0.7;
        y = Math.max(1.85, Math.min(5.7, y));
        fullPts.push({ x, y });
      }
    });

    _fulltime = { hist, pts, dist, distSev, fullHist, fullPts };
    return _fulltime;
  }

  return { home, fulltimeRegionMeans, fulltimeRegionMeansSev, getFulltimeData };
})();
