/* 지역 분류 기준 모달 — 트리거(id=region-modal-open) 클릭 시 열고, 지도를 처음 한 번 그린다.
 * 모달 마크업은 web/_region_modal.html partial, 지도는 RegionMap(korea-regions.js + region-map.js)에 의존한다.
 * 여러 페이지(home 제외)에서 공통으로 사용. */
(() => {
  const modal = document.getElementById('region-modal');
  const open = document.getElementById('region-modal-open');
  const close = document.getElementById('region-modal-close');
  if (!modal || !open) return;

  let mapsDrawn = false;
  const drawMaps = () => {
    if (mapsDrawn || !window.RegionMap) return;
    window.RegionMap.renderRegionMap('capital', document.getElementById('region-map-capital'));
    window.RegionMap.renderRegionMap('nation', document.getElementById('region-map-nation'));
    mapsDrawn = true;
  };
  const openModal = () => { modal.hidden = false; document.body.style.overflow = 'hidden'; drawMaps(); };
  const closeModal = () => { modal.hidden = true; document.body.style.overflow = ''; };

  open.addEventListener('click', openModal);
  if (close) close.addEventListener('click', closeModal);
  modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !modal.hidden) closeModal(); });
})();
