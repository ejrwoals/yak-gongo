"""프로덕션(Cloud Run) 설정.

공개 '얼마줄약'(약사 시급 리포트)만 서빙하는 경량·무상태 배포본.
- 데이터는 번들된 스냅샷 JSON에서 읽는다 (로컬 DB 불필요)
- 관리자·크롤러·파이프라인 앱은 포함하지 않는다 (무거운 의존성 제거)
- 정적 파일은 whitenoise가 직접 서빙한다
"""
import os

from .settings import *  # noqa: F401,F403
from .settings import TEMPLATES

DEBUG = False

# Cloud Run 커스텀 도메인 + *.run.app. deploy.sh가 ALLOWED_HOSTS 를 주입한다.
ALLOWED_HOSTS = os.environ.get(
    'ALLOWED_HOSTS', 'gongo.chajjaem.dev,.run.app',
).split(',')

CSRF_TRUSTED_ORIGINS = [
    'https://gongo.chajjaem.dev',
    'https://*.run.app',
]

# 배포본은 스냅샷 JSON 파일에서만 데이터를 읽는다 → DB 접근 없음
SNAPSHOT_FROM_FILE = True

# 공개 페이지만 서빙: 관리자/파이프라인 앱 제외 → pandas/selenium/genai 등 불필요
INSTALLED_APPS = [
    'django.contrib.staticfiles',
    'web',
]

# DB·세션이 필요 없는 정적 렌더 경로 + Supabase 로그인 게이트
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.common.CommonMiddleware',
    'web.middleware.SupabaseAuthMiddleware',
]

# 로그인 게이트 on/off (베타=켬). 정식 오픈 시 AUTH_GATE=0 으로 공개 전환.
AUTH_GATE_ENABLED = os.environ.get('AUTH_GATE', '1') == '1'

# 공개 템플릿은 auth/messages 컨텍스트를 쓰지 않는다 (+ Supabase 설정 주입)
TEMPLATES[0]['OPTIONS']['context_processors'] = [
    'django.template.context_processors.request',
    'web.context_processors.supabase',
]

# 정적 파일: whitenoise 압축 + 해시(캐시버스팅)
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Cloud Run 프록시 뒤에서 HTTPS 인식
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
