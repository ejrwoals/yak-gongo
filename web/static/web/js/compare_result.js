/* '내 시급 비교' 결과 페이지 — query string의 근무조건을 근무형태로 분류하고,
 * 같은 근무형태의 전국·지역 분포(#dashboard-data의 compare 섹션)에서 퍼센타일을 계산해 렌더한다.
 * 분류 규칙은 백엔드 dashboard_stats.py 및 입력 페이지(compare.js)와 동일하게 맞춘다. */
(() => {
  const payload = JSON.parse(document.getElementById('dashboard-data').textContent);
  const C = window.Charts;
  const $ = id => document.getElementById(id);
  const cats = (payload.data && payload.data.categories) || [];
  const byKey = Object.fromEntries(cats.map(c => [c.key, c]));
  const q = new URLSearchParams(location.search);

  // '다시 계산하기'는 현재 입력값을 그대로 들고 계산기로 복귀
  $('recalc-btn').href = $('recalc-btn').getAttribute('href') + location.search;

  const fnum = v => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
  function showEmpty(msg) {
    $('empty-msg').textContent = msg;
    $('empty').hidden = false;
    $('result').hidden = true;
    $('classify-banner').style.display = 'none';
  }

  // 근무형태별 색상 (홈 페이지 카테고리 색과 동일)
  const CAT_COLOR = { fulltime: '#2E6FB0', weekend: '#C5891B', etc: '#3C9A5C', onetime: '#7B5BC4' };
  function classifyReason(key, h) {
    if (key === 'onetime') return '하루·단기 대체 근무(일회성)를 선택하셔서 일회성 단기로 분류됐어요. 같은 일회성 공고끼리 시급을 비교합니다.';
    if (key === 'weekend') return '평일 근무 없이 주말에만 근무해서 주말 파트로 분류됐어요. 같은 주말 파트 공고와 비교합니다.';
    if (key === 'fulltime') return '주당 ' + h + '시간(36시간 이상)이라 풀타임으로 분류됐어요. 같은 풀타임 공고와 비교합니다.';
    return '주당 ' + h + '시간(36시간 미만)이라 기타 파트로 분류됐어요. 같은 기타 파트 공고와 비교합니다.';
  }

  if (cats.length === 0) return showEmpty('현재 비교용 통계 데이터가 없습니다. 잠시 후 다시 시도해 주세요.');

  const wt = q.get('wt') === 'onetime' ? 'onetime' : 'long';
  const wage = fnum(q.get('wage'));
  const region = q.get('region') || '서울';
  if (wage == null || wage <= 0) return showEmpty('입력된 시급이 없습니다. 계산기에서 다시 입력해 주세요.');

  // ---- 주당 근무시간 (models.py save()와 동일) ----
  function computeHours() {
    const wdS = fnum(q.get('wds')), wdE = fnum(q.get('wde')), wdD = fnum(q.get('wdd'));
    const weS = fnum(q.get('wes')), weE = fnum(q.get('wee')), weD = fnum(q.get('wed'));
    let wd = null, we = null;
    if (wdS != null && wdE != null && wdD != null) wd = (wdE - wdS) * wdD;
    if (weS != null && weE != null && weD != null) we = (weE - weS) * weD;
    if (wd == null && we == null) return null;
    return { hours: (wd || 0) + (we || 0), wdDays: wdD || 0, weDays: weD || 0 };
  }

  // ---- 근무형태 분류 (dashboard_stats.py 정의와 일치) ----
  function classify(sched) {
    if (wt === 'onetime') return 'onetime';
    if (sched.wdDays === 0 && sched.weDays > 0) return 'weekend';
    if (sched.hours >= 36) return 'fulltime';
    return 'etc';
  }

  // 상위% = 내 시급보다 더 주는 공고 비율
  const topPercent = (vals, x) => Math.round(vals.reduce((c, v) => c + (v > x ? 1 : 0), 0) / vals.length * 100);

  let key, hours = null;
  if (wt === 'onetime') {
    key = 'onetime';
  } else {
    const sched = computeHours();
    if (!sched) return showEmpty('근무 시간 정보가 없습니다. 계산기에서 다시 입력해 주세요.');
    hours = sched.hours;
    key = classify(sched);
  }

  const cat = byKey[key];
  if (!cat || !cat.national.vals.length) return showEmpty('해당 근무형태의 비교 데이터가 부족합니다.');
  const reg = (cat.regions || []).find(r => r.nm === region);

  // ---- 분류 결과 배너 ----
  const roundHours = key === 'onetime' ? null : Math.round(hours * 10) / 10;
  const col = CAT_COLOR[key] || '#3C9A5C';
  $('classify-name').textContent = cat.name;
  $('classify-name').style.background = col;
  $('classify-accent').style.background = col;
  $('classify-reason').textContent = classifyReason(key, roundHours);
  $('res-hours').textContent = key === 'onetime' ? '시간 무관' : '주당 ' + roundHours + '시간';
  $('res-region').textContent = region;
  $('res-wage').textContent = '내 시급 ' + wage.toFixed(2) + '만원';

  function pctSentence(pct, pool) {
    const diff = wage - pool.mean;
    const cmp = diff >= 0
      ? '평균보다 <b style="color:#138255;">+' + diff.toFixed(2) + '만원</b> 높아요'
      : '평균보다 <b style="color:#D9483B;">' + diff.toFixed(2) + '만원</b> 낮아요';
    return '공고 ' + pool.n.toLocaleString() + '건 중 ' + pct + '%만 더 높은 시급입니다. (평균 ' + pool.mean.toFixed(2) + '만원, ' + cmp + ')';
  }

  // ---- 전국 카드 ----
  const natPct = topPercent(cat.national.vals, wage);
  $('card-nat-label').textContent = '전국 ' + cat.name + ' 공고 중';
  $('nat-pct').textContent = natPct;
  $('nat-desc').innerHTML = pctSentence(natPct, cat.national);

  // ---- 지역 카드 ----
  const regOk = reg && reg.vals.length >= 5;
  if (regOk) {
    const regPct = topPercent(reg.vals, wage);
    $('card-reg-label').textContent = region + ' ' + cat.name + ' 공고 중';
    $('reg-big').innerHTML = '상위 <span style="color:#2E6FB0;">' + regPct + '</span><span style="font-size:18px;">%</span>';
    $('reg-desc').innerHTML = pctSentence(regPct, reg);
  } else {
    $('card-reg-label').textContent = region + ' ' + cat.name;
    $('reg-big').innerHTML = '<span style="font-size:17px; font-weight:700; color:#9AA098;">표본 부족</span>';
    $('reg-desc').textContent = '해당 지역·근무형태 공고 수가 적어(' + ((reg && reg.n) || 0) + '건) 지역 비교는 생략합니다.';
  }

  // ---- 분포 차트 ----
  const groups = [{ label: '전국', mean: cat.national.mean, n: cat.national.n, vals: cat.national.vals }];
  if (regOk) groups.push({ label: region, mean: reg.mean, n: reg.n, vals: reg.vals });
  $('chart-compare').append(C.buildCompare(groups, wage));

  // ---- 근무시간 대비 시급 (일회성 제외) ----
  if (key !== 'onetime' && cat.pts && cat.pts.length && hours != null) {
    $('chart-hours').append(C.buildHoursScatter(cat.pts, cat.reg, { x: hours, y: wage }));
    if (cat.reg) {
      const pred = cat.reg.slope * hours + cat.reg.intercept, v = $('hours-verdict');
      if (wage >= pred) { v.textContent = '근무시간을 감안하면 평균보다 시급이 높은 편이에요 ▲'; v.style.color = '#138255'; }
      else { v.textContent = '근무시간을 감안하면 평균보다 시급이 낮은 편이에요 ▼'; v.style.color = '#D9483B'; }
    }
    $('hours-section').hidden = false;
  }

  $('result').hidden = false;
})();
