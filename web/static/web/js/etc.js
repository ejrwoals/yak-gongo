/* 기타 파트 상세 페이지 — 서버 스냅샷(#dashboard-data)을 입력으로 차트(Charts)와 표를 마운트한다. */
(() => {
  const payload = JSON.parse(document.getElementById('dashboard-data').textContent);
  const d = payload.data;
  const C = window.Charts;

  if (!d) {
    const c = document.getElementById('etc-count');
    if (c) c.textContent = '—';
    const w = document.getElementById('etc-avg-wage');
    if (w) w.textContent = '—';
    window.UI.initToggles();
    return;
  }

  const REGION_COLOR = {
    '서울': '#B0203A', '인천': '#E8843C', '경기 중부': '#E9CE54', '경기 외곽': '#6FB7E0', '지방': '#2E3E8F',
  };
  const pts = d.pts.map(p => ({ ...p, col: REGION_COLOR[p.region] || '#2E3E8F' }));
  // 기타 파트 산점도: 근무시간 0~38h, 시급축 ~5.8, 회귀선 1~35h 구간
  const scOpts = { xRange: [0, 38], xStep: 2, wageRange: [1.8, 5.8], lineRange: [1, 35] };

  const mount = (id, svg) => { const el = document.getElementById(id); if (el) el.append(svg); };

  document.getElementById('etc-avg-wage').textContent = d.avgWage != null ? d.avgWage.toFixed(2) : '—';
  document.getElementById('etc-count').textContent = d.count.toLocaleString();

  mount('chart-hist', C.buildHistogram(d.hist));
  mount('chart-scatter-all', C.buildScatter(pts, 'all', d.regression.wage, scOpts));
  mount('chart-monthly', C.buildScatter(pts, 'month', d.regression.month, { xRange: [0, 38], xStep: 2, lineRange: [1, 35] }));
  mount('chart-regional', C.buildScatter(pts, 'region', d.regression.wage, scOpts));
  mount('chart-bubble', C.buildViolin(d.dist));

  // 지역별 평균값 표
  const tdL = 'border:1px solid #E6E6DF; padding:10px 14px; font-weight:700; color:#454C43;';
  const tdR = 'border:1px solid #E6E6DF; padding:10px 14px; color:#3A4138;';
  document.getElementById('etc-table-means').innerHTML = d.regionMeans.map(({ nm, mn }) =>
    `<tr><td style="${tdL}">${nm}</td><td style="${tdR}">${mn.toFixed(2)}</td></tr>`).join('');

  window.UI.initToggles();
})();
