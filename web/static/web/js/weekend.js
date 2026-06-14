/* 주말 파트 상세 페이지 — 서버 스냅샷(#dashboard-data)을 입력으로 차트(Charts)와 표를 마운트한다. */
(() => {
  const payload = JSON.parse(document.getElementById('dashboard-data').textContent);
  const d = payload.data;
  const C = window.Charts;

  if (!d) {
    const c = document.getElementById('wk-count');
    if (c) c.textContent = '—';
    const w = document.getElementById('wk-avg-wage');
    if (w) w.textContent = '—';
    window.UI.initToggles();
    return;
  }

  const mount = (id, svg) => { const el = document.getElementById(id); if (el) el.append(svg); };

  document.getElementById('wk-avg-wage').textContent = d.avgWage != null ? d.avgWage.toFixed(2) : '—';
  document.getElementById('wk-count').textContent = d.count.toLocaleString();

  mount('chart-hist', C.buildHistogram(d.hist));
  mount('chart-date-all', C.buildDateScatter(d.dateScatter, d.avgWage, { byRegion: false }));
  mount('chart-date-region', C.buildDateScatter(d.dateScatter, d.avgWage, { byRegion: true, yPadTop: 0.7 }));
  mount('chart-bubble', C.buildBubble(d.bubble, d.regionMeans, {}));
  // 나의 시급 비교: 동일 버블 차트 + 예시 별표 (지방, 3.7만원) — 노션과 동일
  mount('chart-my-bubble', C.buildBubble(d.bubble, d.regionMeans, { star: { region: '지방', y: 3.7 } }));

  // 지역별 평균값 표
  const tdL = 'border:1px solid #E6E6DF; padding:10px 14px; font-weight:700; color:#454C43;';
  const tdR = 'border:1px solid #E6E6DF; padding:10px 14px; color:#3A4138;';
  document.getElementById('wk-table-means').innerHTML = d.regionMeans.map(({ nm, mn }) =>
    `<tr><td style="${tdL}">${nm}</td><td style="${tdR}">${mn.toFixed(2)}</td></tr>`).join('');

  window.UI.initToggles();
})();
