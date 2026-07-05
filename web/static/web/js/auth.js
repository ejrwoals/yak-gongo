// 게이트된 페이지의 인증 유지 + 우측 상단 프로필 배너 + 로그아웃 모달.
// - access_token을 'sb-access-token' 쿠키에 미러링 (서버 미들웨어가 검증)
// - 토큰 자동 갱신 시 쿠키도 갱신 → 만료 튕김 방지
// - #profile-banner 에 구글 프로필 사진(원형) + 닉네임 표시, 클릭 시 로그아웃 모달
(function () {
  if (!window.SUPABASE_URL) return;
  var sb = supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY);

  function persist(session) {
    if (!session) return;
    document.cookie = "sb-access-token=" + session.access_token +
      "; path=/; max-age=" + (session.expires_in || 3600) + "; samesite=lax; secure";
  }

  function userInfo(session) {
    var u = session && session.user;
    if (!u) return null;
    var m = u.user_metadata || {};
    return {
      name: m.full_name || m.name || m.user_name || u.email || '사용자',
      email: u.email || '',
      avatar: m.avatar_url || m.picture || ''
    };
  }

  function paintAvatar(el, info, fontSize) {
    if (!el) return;
    if (info.avatar) {
      el.style.backgroundImage = 'url("' + info.avatar + '")';
      el.textContent = '';
    } else {
      el.textContent = (info.name.trim()[0] || 'U').toUpperCase();
      if (fontSize) el.style.fontSize = fontSize;
    }
  }

  function renderProfile(info) {
    var banner = document.getElementById('profile-banner');
    if (!banner || !info) return;
    paintAvatar(document.getElementById('profile-avatar'), info);
    var nm = document.getElementById('profile-name');
    if (nm) nm.textContent = info.name;
    banner.onclick = function () { openModal(info); };
  }

  // ── 로그아웃 모달 ─────────────────────────────────────────────
  var overlay = null;
  function buildModal() {
    overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed; inset:0; background:rgba(20,28,22,0.38); display:none; align-items:center; justify-content:center; z-index:1000; font-family:inherit;';
    overlay.innerHTML =
      '<div style="width:300px; max-width:calc(100vw - 40px); background:#fff; border-radius:18px; padding:26px 24px; box-shadow:0 16px 48px rgba(0,0,0,.22); text-align:center;">' +
        '<div id="pm-avatar" style="width:60px; height:60px; border-radius:50%; margin:0 auto 14px; background:linear-gradient(150deg,#CFE9DA,#A6D8BE); background-size:cover; background-position:center; display:flex; align-items:center; justify-content:center; font-size:22px; font-weight:800; color:#0F7A4C;"></div>' +
        '<div id="pm-name" style="font-size:17px; font-weight:800; color:#222; letter-spacing:-0.3px;"></div>' +
        '<div id="pm-email" style="font-size:13px; color:#8A908A; margin-top:4px;"></div>' +
        '<button id="pm-logout" style="margin-top:20px; width:100%; padding:12px; border:1px solid #F0D3D3; border-radius:12px; background:#fff; color:#C0392B; font-size:15px; font-weight:700; cursor:pointer;">로그아웃</button>' +
        '<button id="pm-close" style="margin-top:8px; width:100%; padding:10px; border:none; background:none; color:#9AA098; font-size:13px; cursor:pointer;">닫기</button>' +
      '</div>';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) hideModal(); });
    overlay.querySelector('#pm-close').onclick = hideModal;
    overlay.querySelector('#pm-logout').onclick = function () { window.gongoLogout(); };
  }
  function openModal(info) {
    if (!overlay) buildModal();
    paintAvatar(overlay.querySelector('#pm-avatar'), info, '22px');
    overlay.querySelector('#pm-name').textContent = info.name;
    overlay.querySelector('#pm-email').textContent = info.email;
    overlay.style.display = 'flex';
  }
  function hideModal() { if (overlay) overlay.style.display = 'none'; }

  // ── 세션 동기화 ───────────────────────────────────────────────
  function refresh(session) {
    persist(session);
    renderProfile(userInfo(session));
  }

  sb.auth.getSession().then(function (res) { refresh(res.data.session); });
  sb.auth.onAuthStateChange(function (event, session) {
    if (session) refresh(session);
    if (event === 'SIGNED_OUT') {
      document.cookie = "sb-access-token=; path=/; max-age=0";
      location.href = '/login/';
    }
  });

  window.gongoLogout = function () { location.href = '/logout/'; };
})();
