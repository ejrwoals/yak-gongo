"""Supabase JWT + 초대코드 기반 로그인 게이트 (배포본 전용).

두 계층으로 접근을 통제한다:

1. 인증(JWT): Supabase가 발급한 access_token(JWT)을 'sb-access-token' 쿠키에서 읽어
   서명을 검증한다 → 유효한 Google 로그인이면 1차 통과.
   서명 검증은 두 방식을 자동 지원한다:
   - 비대칭(ES256/RS256): Supabase 공개키(JWKS)로 검증 — 새 JWT Signing Keys
   - 대칭(HS256): Legacy JWT Secret 으로 검증 — 구형 프로젝트 대비 fallback
   토큰 헤더의 alg 를 보고 알아서 고른다.

2. 초대코드(access): JWT가 유효해도, public.users.invite_code 가 비어 있으면
   아직 초대코드를 통과하지 않은 유저다 → 앱 화면 접근을 막고 /login/ 으로 돌린다
   (로그인 페이지가 코드 입력 UI를 띄운다). 이 서버측 확인이 "코드 없는 유저의
   데이터 접근 차단"의 실제 경계다 — 클라이언트 라우트 가드만으로는 유효 JWT 보유자가
   URL 직접 접근으로 우회할 수 있기 때문이다. 실제 검증/부여는 DB의 claim_invite RPC가
   전담하고, 여기서는 그 결과(invite_code 유무)만 읽는다.

미인증/미부여 요청은 /login/ 으로 리다이렉트한다.

settings.AUTH_GATE_ENABLED 로 인증 게이트 전체를,
settings.INVITE_GATE_ENABLED 로 초대코드 요구를 각각 켜고 끈다(베타=켬).
"""
import json
import logging
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

import jwt
from jwt import PyJWKClient

from django.conf import settings
from django.shortcuts import redirect

logger = logging.getLogger(__name__)

# 인증 없이 접근 가능한 경로 (로그인 화면·정적파일·헬스체크)
EXEMPT_PREFIXES = ('/login', '/logout', '/static/', '/healthz')


class SupabaseAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, 'AUTH_GATE_ENABLED', False)
        self.invite_gate = getattr(settings, 'INVITE_GATE_ENABLED', False)
        self.secret = getattr(settings, 'SUPABASE_JWT_SECRET', '')
        self.anon = getattr(settings, 'SUPABASE_ANON_KEY', '')
        url = getattr(settings, 'SUPABASE_URL', '').rstrip('/')
        self.jwks_url = f'{url}/auth/v1/.well-known/jwks.json' if url else ''
        self.rest_users_url = f'{url}/rest/v1/users' if url else ''
        self._jwks_client = None
        # 부여 확인 캐시(uid → 만료 시각). 관리자가 DB에서 invite_code를 NULL로 되돌려
        # 권한을 "회수"할 수 있으므로 부여는 단조가 아니다 → 영구 캐시는 회수를 무시하는
        # 보안 구멍이 된다. 기본 TTL=0(캐시 없음)으로 매 요청 재검증하여 회수를 즉시 반영한다.
        # DB 부하가 문제되면 INVITE_GATE_CACHE_TTL(초)로 짧게 캐시할 수 있다(그만큼 회수 지연).
        self._cache_ttl = int(getattr(settings, 'INVITE_GATE_CACHE_TTL', 0) or 0)
        self._granted = {}

    def __call__(self, request):
        if not self.enabled or request.path.startswith(EXEMPT_PREFIXES):
            return self.get_response(request)

        payload = self._decode(request.COOKIES.get('sb-access-token', ''))
        if payload is None:
            return redirect(f"/login/?next={quote(request.path)}")

        # 인증 통과. 초대코드 게이트가 켜져 있으면 부여 여부까지 확인한다.
        if self.invite_gate:
            token = request.COOKIES.get('sb-access-token', '')
            if not self._has_access(payload.get('sub', ''), token):
                return redirect(f"/login/?next={quote(request.path)}")

        return self.get_response(request)

    def _jwks(self):
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(self.jwks_url)
        return self._jwks_client

    def _decode(self, token):
        """JWT 서명·만료 검증. 유효하면 payload(dict), 아니면 None."""
        if not token:
            return None
        try:
            alg = jwt.get_unverified_header(token).get('alg', '')
            if alg in ('ES256', 'RS256'):
                if not self.jwks_url:
                    return None
                key = self._jwks().get_signing_key_from_jwt(token).key
            elif alg == 'HS256':
                if not self.secret:
                    return None
                key = self.secret
            else:
                return None
            # exp 는 자동 검증됨. Supabase JWT 는 aud='authenticated'.
            return jwt.decode(token, key, algorithms=[alg], audience='authenticated')
        except Exception:
            return None

    def _has_access(self, uid, token):
        """이 유저가 초대코드를 통과했는지(public.users.invite_code IS NOT NULL) 확인.

        유저 자신의 access_token으로 PostgREST를 호출해 RLS("own data" SELECT 정책)
        범위 안에서 자기 행만 읽는다 → service_role 비밀키 불필요. 오류 시 fail-closed
        (미부여로 간주)하여 JWT 게이트와 동일하게 막는다.

        기본적으로 매 요청 DB를 재검증한다 → 관리자가 invite_code를 NULL로 되돌리면
        (권한 회수) 다음 요청부터 즉시 차단된다. TTL이 설정된 경우에만 그 시간 동안 캐시한다.
        """
        if not uid or not self.rest_users_url:
            return False
        if self._cache_ttl > 0:
            exp = self._granted.get(uid)
            if exp is not None and exp > time.monotonic():
                return True
        try:
            req = Request(
                f"{self.rest_users_url}?id=eq.{quote(uid)}&select=invite_code",
                headers={
                    'apikey': self.anon,
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/json',
                },
            )
            with urlopen(req, timeout=3) as resp:
                rows = json.loads(resp.read().decode('utf-8'))
        except Exception:
            logger.warning('invite access check failed for user %s', uid, exc_info=True)
            self._granted.pop(uid, None)  # 오류 시 낡은 캐시를 신뢰하지 않음
            return False

        granted = bool(rows and rows[0].get('invite_code'))
        if granted:
            if self._cache_ttl > 0:
                self._granted[uid] = time.monotonic() + self._cache_ttl
        else:
            # 미부여이거나 권한이 회수됨 → 낡은 캐시 즉시 제거.
            self._granted.pop(uid, None)
        return granted
