/* 풀타임 상세 페이지 — 서버 스냅샷(#dashboard-data)을 입력으로 차트(Charts)와 표를 마운트한다.
 * 지역 색상은 표현 값이라 프론트에 유지하고, 좌표·회귀계수 등 수치는 스냅샷에서 가져온다. */
(() => {
  const payload = JSON.parse(document.getElementById('dashboard-data').textContent);
  const d = payload.data;
  const C = window.Charts;

  if (!d) {
    const c = document.getElementById('ft-count');
    if (c) c.textContent = '—';
    const w = document.getElementById('ft-avg-wage');
    if (w) w.textContent = '—';
    window.UI.initToggles();
    return;
  }

  const REGION_COLOR = {
    '서울': '#B0203A', '인천': '#E8843C', '경기 중부': '#E9CE54', '경기 외곽': '#6FB7E0', '지방': '#2E3E8F',
  };
  // 산점도 점에 지역 색상 부여 (표현 값)
  const pts = d.pts.map(p => ({ ...p, col: REGION_COLOR[p.region] || '#2E3E8F' }));

  const mount = (id, svg) => { const el = document.getElementById(id); if (el) el.append(svg); };

  document.getElementById('ft-avg-wage').textContent = d.avgWage != null ? d.avgWage.toFixed(2) : '—';
  document.getElementById('ft-count').textContent = d.count.toLocaleString();

  mount('chart-hist', C.buildHistogram(d.hist));
  mount('chart-scatter-all', C.buildScatter(pts, 'all', d.regression.wage));
  mount('chart-monthly', C.buildScatter(pts, 'month', d.regression.month));
  mount('chart-regional', C.buildScatter(pts, 'region', d.regression.wage));
  mount('chart-dist', C.buildViolin(d.dist));
  mount('chart-dist-sev', C.buildViolin(d.distSev));

  mount('chart-full-hist', C.buildFullHistogram(d.fullHist));
  mount('chart-full-scatter', C.buildFullScatter(d.fullPts, d.fullRegression));

  // 지역별 평균값 표 2종 (분포 차트와 같은 데이터 소스)
  const tdL = 'border:1px solid #E6E6DF; padding:10px 14px; font-weight:700; color:#454C43;';
  const tdR = 'border:1px solid #E6E6DF; padding:10px 14px; color:#3A4138;';
  const rows = list => list.map(({ nm, mn }) =>
    `<tr><td style="${tdL}">${nm}</td><td style="${tdR}">${mn.toFixed(2)}</td></tr>`).join('');
  document.getElementById('table-means').innerHTML = rows(d.regionMeans);
  document.getElementById('table-means-sev').innerHTML = rows(d.regionMeansSev);

  window.UI.initToggles();
})();
