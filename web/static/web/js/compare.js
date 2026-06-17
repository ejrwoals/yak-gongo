/* '내 시급 비교' 입력 페이지 — 근무조건을 검증한 뒤 결과 페이지(/compare/result/)로 이동한다.
 * 입력값은 query string으로 넘기며, 결과 페이지에서 같은 값으로 분류·퍼센타일을 계산한다.
 * 결과 페이지의 '다시 계산하기'로 돌아오면 query string으로 폼을 그대로 복원한다. */
(() => {
  const $ = id => document.getElementById(id);
  let worktype = 'long'; // 'long' | 'onetime'

  function setWorktype(wt) {
    worktype = wt;
    document.querySelectorAll('[data-worktype]').forEach(b =>
      b.setAttribute('aria-pressed', String(b.dataset.worktype === wt)));
    $('schedule-block').hidden = (wt === 'onetime');
  }
  document.querySelectorAll('[data-worktype]').forEach(btn =>
    btn.addEventListener('click', () => setWorktype(btn.dataset.worktype)));

  // ---- 주당 근무시간 계산 (models.py save()와 동일) ----
  const num = el => { const v = parseFloat(el.value); return Number.isFinite(v) ? v : null; };
  function computeHours() {
    const wdS = num($('wd-start')), wdE = num($('wd-end')), wdD = num($('wd-days'));
    const weS = num($('we-start')), weE = num($('we-end')), weD = num($('we-days'));
    let wd = null, we = null;
    if (wdS != null && wdE != null && wdD != null) wd = (wdE - wdS) * wdD;
    if (weS != null && weE != null && weD != null) we = (weE - weS) * weD;
    if (wd == null && we == null) return null;
    return { hours: (wd || 0) + (we || 0) };
  }
  const liveHours = () => {
    const r = computeHours();
    $('hours-out').textContent = r ? (Math.round(r.hours * 10) / 10) : '—';
  };
  const SCHED = ['wd-start', 'wd-end', 'wd-days', 'we-start', 'we-end', 'we-days'];
  SCHED.forEach(id => $(id).addEventListener('input', liveHours));

  // ---- query string ↔ 폼 ----
  const PARAMS = { wt: null, wds: 'wd-start', wde: 'wd-end', wdd: 'wd-days', wes: 'we-start', wee: 'we-end', wed: 'we-days', region: 'region', wage: 'my-wage' };

  // 결과 페이지에서 돌아온 경우 폼 복원
  (function prefill() {
    const q = new URLSearchParams(location.search);
    if (![...q.keys()].length) return;
    if (q.get('wt') === 'onetime') setWorktype('onetime');
    Object.entries(PARAMS).forEach(([key, id]) => {
      if (!id || !q.has(key)) return;
      $(id).value = q.get(key);
    });
    liveHours();
  })();

  const error = msg => { const e = $('form-error'); e.textContent = msg; e.hidden = false; };

  // ---- 검증 후 결과 페이지로 이동 ----
  $('calc-btn').addEventListener('click', () => {
    $('form-error').hidden = true;
    const wage = num($('my-wage'));
    if (wage == null || wage <= 0) return error('내 시급(만원)을 입력해 주세요. (예: 3.0)');
    if (worktype === 'long' && !computeHours()) return error('평일 또는 주말 근무 시간(출근·퇴근·일수)을 입력해 주세요.');

    const q = new URLSearchParams();
    q.set('wt', worktype);
    q.set('region', $('region').value);
    q.set('wage', String(wage));
    if (worktype === 'long') {
      SCHED.forEach((id, i) => {
        const key = ['wds', 'wde', 'wdd', 'wes', 'wee', 'wed'][i];
        if ($(id).value !== '') q.set(key, $(id).value);
      });
    }
    location.href = $('calc-btn').dataset.resultUrl + '?' + q.toString();
  });
})();
