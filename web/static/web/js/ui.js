/*
 * 공통 UI — 펼침/접힘 토글.
 * 버튼: data-toggle="key", 패널: data-panel="key" (초기 상태는 hidden 속성으로 지정)
 * 버튼 안의 캐럿 아이콘에 data-caret을 붙이면 열림 상태에서 90도 회전한다.
 */
window.UI = (() => {
  function initToggles(root = document) {
    root.querySelectorAll('[data-toggle]').forEach(btn => {
      const panel = root.querySelector('[data-panel="' + btn.dataset.toggle + '"]');
      if (!panel) return;
      btn.addEventListener('click', () => {
        panel.hidden = !panel.hidden;
        const caret = btn.querySelector('[data-caret]');
        if (caret) caret.style.transform = panel.hidden ? 'rotate(0deg)' : 'rotate(90deg)';
      });
    });
  }
  return { initToggles };
})();
