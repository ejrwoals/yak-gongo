"""Supabase JWT 기반 로그인 게이트 (배포본 전용).

Supabase가 발급한 access_token(JWT)을 'sb-access-token' 쿠키에서 읽어
서명을 검증한다 → 유효한 Google 로그인이면 통과.
미인증 요청은 /login/ 으로 리다이렉트한다.

서명 검증은 두 방식을 자동 지원한다:
- 비대칭(ES256/RS256): Supabase 공개키(JWKS)로 검증 — 새 JWT Signing Keys
- 대칭(HS256): Legacy JWT Secret 으로 검증 — 구형 프로젝트 대비 fallback
토큰 헤더의 alg 를 보고 알아서 고른다.

약사 자격(role) 검증은 아직 하지 않는다.
settings.AUTH_GATE_ENABLED 로 전체 게이트를 켜고 끈다(베타=켬).
"""
import jwt
from jwt import PyJWKClient
from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect

# 인증 없이 접근 가능한 경로 (로그인 화면·정적파일·헬스체크)
EXEMPT_PREFIXES = ('/login', '/logout', '/static/', '/healthz')


class SupabaseAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, 'AUTH_GATE_ENABLED', False)
        self.secret = getattr(settings, 'SUPABASE_JWT_SECRET', '')
        url = getattr(settings, 'SUPABASE_URL', '').rstrip('/')
        self.jwks_url = f'{url}/auth/v1/.well-known/jwks.json' if url else ''
        self._jwks_client = None

    def __call__(self, request):
        if not self.enabled or request.path.startswith(EXEMPT_PREFIXES):
            return self.get_response(request)
        if self._valid(request.COOKIES.get('sb-access-token', '')):
            return self.get_response(request)
        return redirect(f"/login/?next={quote(request.path)}")

    def _jwks(self):
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(self.jwks_url)
        return self._jwks_client

    def _valid(self, token):
        if not token:
            return False
        try:
            alg = jwt.get_unverified_header(token).get('alg', '')
            if alg in ('ES256', 'RS256'):
                if not self.jwks_url:
                    return False
                key = self._jwks().get_signing_key_from_jwt(token).key
            elif alg == 'HS256':
                if not self.secret:
                    return False
                key = self.secret
            else:
                return False
            # exp 는 자동 검증됨. Supabase JWT 는 aud='authenticated'.
            jwt.decode(token, key, algorithms=[alg], audience='authenticated')
            return True
        except Exception:
            return False
