/* 메인(홈) 페이지 — 서버 스냅샷(#dashboard-data)을 입력으로 동적 영역을 렌더한다.
 * 색상 등 순수 표현 값은 프론트에 유지하고, 수치만 스냅샷에서 가져온다. */
(() => {
  const payload = JSON.parse(document.getElementById('dashboard-data').textContent);
  const data = payload.data;

  // 카테고리 색상 (표현 값 — 데이터와 분리)
  const CAT_COLOR = {
    '전체': '#56564F', '전국 평균': '#A0A096', '풀타임': '#2E6FB0', '주말 파트': '#C5891B',
    '기타 파트': '#3C9A5C', '일회성 단기': '#7B5BC4',
  };

  if (!data) {
    const el = document.getElementById('total-postings');
    if (el) el.textContent = '—';
    document.getElementById('last-update').textContent = '데이터 없음 (admin에서 대시보드 업데이트 필요)';
    return;
  }

  const { totalPostings, categoryAvg } = data;
  const fmt = v => (v == null ? '—' : v.toFixed(2));

  document.getElementById('total-postings').textContent = totalPostings.toLocaleString();
  document.getElementById('last-update').textContent = payload.lastUpdate || '—';
  document.querySelectorAll('[data-cat-avg]').forEach(el => {
    const cat = categoryAvg.find(c => c.name === el.dataset.catAvg);
    if (cat) el.textContent = fmt(cat.v);
  });
  // 세부 분류 토글 — 분류별 공고 수
  document.querySelectorAll('[data-cat-count]').forEach(el => {
    const cat = categoryAvg.find(c => c.name === el.dataset.catCount);
    if (cat && cat.n != null) el.textContent = cat.n.toLocaleString();
  });

  // 그래프 더보기 — 전국(장기 근무) 근무시간-시급 산점도 3종
  const ov = data.overview;
  if (ov && window.Charts) {
    const REGION_COLOR = {
      '서울': '#B0203A', '인천': '#E8843C', '경기 중부': '#E9CE54', '경기 외곽': '#6FB7E0', '지방': '#2E3E8F',
    };
    // 월급은 시급 × 시간 × 4.34 로 환산 (노션 plot_monthly_wage와 동일)
    const ovPts = ov.pts.map(p => ({ ...p, col: REGION_COLOR[p.region] || '#2E3E8F', month: p.x * p.y * 4.34 }));
    const scOpts = { xRange: [0, 62], xStep: 5, wageRange: [1.8, 5.8], lineRange: [1, 60] };
    const C = window.Charts;
    document.getElementById('ov-count').textContent = ov.count.toLocaleString();
    document.getElementById('ov-chart-region').append(C.buildScatter(ovPts, 'region', ov.regression, scOpts));
    document.getElementById('ov-chart-month').append(C.buildScatter(ovPts, 'month', ov.regression, { xRange: [0, 62], xStep: 5, lineRange: [1, 60], monthCurve: true, colorByRegion: true }));
  }

  // 지역별 평균 시급 비교 — 근무형태 칩 선택 → 전국 + 5개 지역 막대
  const byCategory = data.byCategory || [];
  let selCat = byCategory.length ? byCategory[0].name : null;
  const chipsEl = document.getElementById('cat-chips');
  const barsEl = document.getElementById('cat-region-bars');

  function renderCat() {
    const cat = byCategory.find(c => c.name === selCat);
    const color = CAT_COLOR[cat.name] || '#169A60';

    chipsEl.innerHTML = byCategory.map(c => {
      const sel = c.name === selCat;
      const col = CAT_COLOR[c.name] || '#169A60';
      return `<button data-cat="${c.name}" style="padding:7px 14px; border-radius:999px; font-size:13px; font-weight:700; letter-spacing:-0.3px; background:${sel ? col : '#FFFFFF'}; color:${sel ? '#FFFFFF' : '#56605A'}; border:1px solid ${sel ? col : '#E2E2DC'}; transition:all .18s;">${c.name}</button>`;
    }).join('');
    chipsEl.querySelectorAll('[data-cat]').forEach(btn => {
      btn.addEventListener('click', () => { selCat = btn.dataset.cat; renderCat(); });
    });

    // 전국 + 5개 지역
    const rows = [{ nm: '전국', v: cat.national, national: true }].concat(cat.regions.map(r => ({ nm: r.nm, v: r.v })));
    const vals = rows.map(r => r.v).filter(v => v != null);
    const min = Math.min(...vals) - 0.2, max = Math.max(...vals) + 0.1;
    const scale = v => Math.max(8, Math.min(100, ((v - min) / (max - min)) * 100)) + '%';
    barsEl.innerHTML = rows.map(r => {
      const isN = r.national;
      const barColor = isN ? color : color + '66';
      const sep = isN ? 'padding-bottom:12px; margin-bottom:2px; border-bottom:1px dashed #E6E6E0;' : '';
      return `
      <div style="display:flex; align-items:center; gap:14px; ${sep}">
        <span style="width:58px; flex:none; font-size:13.5px; font-weight:${isN ? 800 : 700}; letter-spacing:-0.5px; color:${isN ? '#1E2420' : '#828A80'};">${r.nm}</span>
        <div style="flex:1; height:20px; background:#F1F2EF; border-radius:7px; overflow:hidden;">
          <div style="height:100%; width:${r.v == null ? '0%' : scale(r.v)}; background:${barColor}; border-radius:7px; transition:all .4s ease;"></div>
        </div>
        <span style="width:58px; flex:none; text-align:right; font-size:13.5px; font-weight:800; color:${isN ? color : '#8A938B'};">${fmt(r.v)}<span style="font-size:10px; font-weight:600; margin-left:2px;">만원</span></span>
      </div>`;
    }).join('');
  }

  if (selCat) renderCat();

  // 그래프 더보기 모달 (열기/닫기 — 버튼·X·배경 클릭·ESC)
  const gModal = document.getElementById('graph-modal');
  const gOpen = document.getElementById('graph-modal-open');
  const gClose = document.getElementById('graph-modal-close');
  if (gModal && gOpen) {
    const openModal = () => { gModal.hidden = false; document.body.style.overflow = 'hidden'; };
    const closeModal = () => { gModal.hidden = true; document.body.style.overflow = ''; };
    gOpen.addEventListener('click', openModal);
    if (gClose) gClose.addEventListener('click', closeModal);
    gModal.addEventListener('click', e => { if (e.target === gModal) closeModal(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !gModal.hidden) closeModal(); });
  }

  // 지역 분류 기준 모달 (열기/닫기 — 버튼·X·배경 클릭·ESC)
  const rModal = document.getElementById('region-modal');
  const rOpen = document.getElementById('region-modal-open');
  const rClose = document.getElementById('region-modal-close');
  if (rModal && rOpen) {
    let mapsDrawn = false;
    const drawMaps = () => {
      if (mapsDrawn || !window.RegionMap) return;
      window.RegionMap.renderRegionMap('capital', document.getElementById('region-map-capital'));
      window.RegionMap.renderRegionMap('nation', document.getElementById('region-map-nation'));
      mapsDrawn = true;
    };
    const openModal = () => { rModal.hidden = false; document.body.style.overflow = 'hidden'; drawMaps(); };
    const closeModal = () => { rModal.hidden = true; document.body.style.overflow = ''; };
    rOpen.addEventListener('click', openModal);
    if (rClose) rClose.addEventListener('click', closeModal);
    rModal.addEventListener('click', e => { if (e.target === rModal) closeModal(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !rModal.hidden) closeModal(); });
  }

  window.UI.initToggles();
})();
