/* 메인(홈) 페이지 — 서버 스냅샷(#dashboard-data)을 입력으로 동적 영역을 렌더한다.
 * 색상 등 순수 표현 값은 프론트에 유지하고, 수치만 스냅샷에서 가져온다. */
(() => {
  const payload = JSON.parse(document.getElementById('dashboard-data').textContent);
  const data = payload.data;

  // 카테고리 색상 (표현 값 — 데이터와 분리)
  const CAT_COLOR = {
    '전국 평균': '#A0A096', '풀타임': '#2E6FB0', '주말 파트': '#C5891B',
    '기타 파트': '#3C9A5C', '일회성 단기': '#7B5BC4',
  };

  if (!data) {
    const el = document.getElementById('total-postings');
    if (el) el.textContent = '—';
    document.getElementById('last-update').textContent = '데이터 없음 (admin에서 대시보드 업데이트 필요)';
    return;
  }

  const { totalPostings, categoryAvg, regionAvg } = data;
  const fmt = v => (v == null ? '—' : v.toFixed(2));

  document.getElementById('total-postings').textContent = totalPostings.toLocaleString();
  document.getElementById('last-update').textContent = payload.lastUpdate || '—';
  document.querySelectorAll('[data-cat-avg]').forEach(el => {
    const cat = categoryAvg.find(c => c.name === el.dataset.catAvg);
    if (cat) el.textContent = fmt(cat.v);
  });

  // 근무형태별 평균 시급 막대 (그래프 토글)
  const catVals = categoryAvg.map(c => c.v).filter(v => v != null);
  const catMin = Math.min(...catVals) - 0.4, catMax = Math.max(...catVals) + 0.1;
  const catScale = v => Math.max(8, Math.min(100, ((v - catMin) / (catMax - catMin)) * 100)) + '%';
  document.getElementById('cat-bars').innerHTML = categoryAvg.map(c => `
    <div style="display:flex; align-items:center; gap:14px;">
      <span style="width:74px; flex:none; font-size:13px; font-weight:700; color:#5C635A; letter-spacing:-0.3px;">${c.name}</span>
      <div style="flex:1; height:16px; background:#F1F1EE; border-radius:8px; overflow:hidden;">
        <div style="height:100%; width:${c.v == null ? '0%' : catScale(c.v)}; background:${CAT_COLOR[c.name] || '#A0A096'}; border-radius:8px; transition:width .5s ease;"></div>
      </div>
      <span style="width:44px; flex:none; text-align:right; font-size:13.5px; font-weight:800; color:#3A4138;">${fmt(c.v)}</span>
    </div>`).join('');

  // 지역별 평균 시급 비교 (칩 선택 → 막대 하이라이트). 스케일은 데이터 범위로 동적 산출.
  let region = regionAvg.length ? regionAvg[0].name : null;
  const regVals = regionAvg.map(r => r.v).filter(v => v != null);
  const regMin = Math.min(...regVals) - 0.15, regMax = Math.max(...regVals) + 0.1;
  const scale = v => Math.max(8, Math.min(100, ((v - regMin) / (regMax - regMin)) * 100)) + '%';
  const sorted = [...regionAvg].sort((a, b) => b.v - a.v);
  const chipsEl = document.getElementById('region-chips');
  const barsEl = document.getElementById('region-bars');

  function renderRegions() {
    chipsEl.innerHTML = regionAvg.map(r => {
      const sel = r.name === region;
      return `<button data-region="${r.name}" style="padding:7px 14px; border-radius:999px; font-size:13px; font-weight:700; letter-spacing:-0.3px; background:${sel ? '#169A60' : '#FFFFFF'}; color:${sel ? '#FFFFFF' : '#56605A'}; border:1px solid ${sel ? '#169A60' : '#E2E2DC'}; transition:all .18s;">${r.name}</button>`;
    }).join('');
    chipsEl.querySelectorAll('[data-region]').forEach(btn => {
      btn.addEventListener('click', () => { region = btn.dataset.region; renderRegions(); });
    });

    barsEl.innerHTML = regionAvg.map(r => {
      const sel = r.name === region;
      return `
      <div style="display:flex; align-items:center; gap:14px;">
        <span style="width:58px; flex:none; font-size:13.5px; font-weight:700; letter-spacing:-0.5px; color:${sel ? '#1E2420' : '#828A80'};">${r.name}</span>
        <div style="flex:1; height:20px; background:#F1F2EF; border-radius:7px; overflow:hidden;">
          <div style="height:100%; width:${scale(r.v)}; background:${sel ? '#169A60' : '#CDD8D0'}; border-radius:7px; transition:all .4s ease;"></div>
        </div>
        <span style="width:58px; flex:none; text-align:right; font-size:13.5px; font-weight:800; color:${sel ? '#0F7A4C' : '#8A938B'};">${fmt(r.v)}<span style="font-size:10px; font-weight:600; margin-left:2px;">만원</span></span>
      </div>`;
    }).join('');

    const selObj = regionAvg.find(r => r.name === region);
    const rank = sorted.findIndex(r => r.name === region) + 1;
    document.getElementById('sel-name').textContent = region;
    document.getElementById('sel-rank').textContent = '전국 ' + rank + '위 / ' + regionAvg.length + '개 지역';
    document.getElementById('sel-value').textContent = fmt(selObj.v);
  }

  if (region) renderRegions();
  window.UI.initToggles();
})();
