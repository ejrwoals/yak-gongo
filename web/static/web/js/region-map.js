/*
 * 지역 분류 지도 렌더러.
 * window.KOREA_REGIONS (viewBox + 지역별 SVG path)로 대한민국 지도를 그리고
 * 5개 대분류(서울·인천·경기 중부·경기 외곽·지방)에 따라 색을 칠한다.
 *   - renderRegionMap('capital', el) : 수도권 확대 지도
 *   - renderRegionMap('nation',  el) : 전국 지도 (수도권 위치 표시)
 */
window.RegionMap = (() => {
  const COLORS = {
    '서울': '#B0203A',
    '인천': '#E8843C',
    '경기 중부': '#E9CE54',
    '경기 외곽': '#6FB7E0',
    '지방': '#2E3E8F',
  };
  const ORDER = ['지방', '경기 외곽', '경기 중부', '인천', '서울'];
  // 수도권 확대 영역 (전체 viewBox 좌표계 기준 bbox + 여백)
  const CAPITAL_BOX = { x: -8, y: 50, w: 462, h: 250 };

  function paths(strokeW) {
    const data = window.KOREA_REGIONS;
    return ORDER.map(r => {
      const d = data.regions[r];
      if (!d) return '';
      return `<path d="${d}" fill="${COLORS[r]}" stroke="#FBFBF8" stroke-width="${strokeW}" stroke-linejoin="round"/>`;
    }).join('');
  }

  function renderRegionMap(mode, el) {
    if (!el || !window.KOREA_REGIONS) return;
    const data = window.KOREA_REGIONS;
    const [W, H] = data.viewBox;
    let svg;
    if (mode === 'capital') {
      const b = CAPITAL_BOX;
      svg = `<svg viewBox="${b.x} ${b.y} ${b.w} ${b.h}" width="100%" preserveAspectRatio="xMidYMid meet" style="display:block;">${paths(0.7)}</svg>`;
    } else {
      const b = CAPITAL_BOX;
      const bx = Math.max(b.x, 3);
      const bw = Math.min(b.x + b.w, W - 3) - bx;
      const box = `<rect x="${bx}" y="${b.y}" width="${bw}" height="${b.h}" fill="none" stroke="#1E2420" stroke-width="4" rx="6"/>`;
      svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" style="display:block;">${paths(0.5)}${box}</svg>`;
    }
    el.innerHTML = svg;
  }

  return { renderRegionMap, COLORS };
})();
