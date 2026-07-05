from django.http import HttpResponse
from django.shortcuts import render

from web.snapshot import get_latest_snapshot


def login_view(request):
    """Supabase Google 로그인 화면 (클라이언트 JS가 OAuth를 처리)."""
    return render(request, 'web/login.html')


def logout_view(request):
    """세션 쿠키를 지우고 클라이언트에서 Supabase signOut 후 로그인으로."""
    resp = render(request, 'web/logout.html')
    resp.delete_cookie('sb-access-token', path='/')
    return resp


def healthz(request):
    """인증 없이 접근 가능한 헬스체크."""
    return HttpResponse('ok')


def _page(request, template, section):
    """최신 스냅샷에서 한 섹션(home/fulltime)을 떼어 템플릿에 전달."""
    snap = get_latest_snapshot()
    payload = {
        'data': (snap['data'].get(section) if snap else None),
        'lastUpdate': (snap['last_update'] if snap else None),
    }
    return render(request, template, {'dashboard': payload})


def home(request):
    return _page(request, 'web/home.html', 'home')


def compare(request):
    return _page(request, 'web/compare.html', 'compare')


def compare_result(request):
    return _page(request, 'web/compare_result.html', 'compare')


def method(request):
    """데이터 처리 방법(시급 산출·수집 파이프라인) 안내 페이지."""
    snap = get_latest_snapshot()
    return render(request, 'web/method.html', {
        'postingCount': (snap['posting_count'] if snap else None),
        'lastUpdate': (snap['last_update'] if snap else None),
    })


def fulltime(request):
    return _page(request, 'web/fulltime.html', 'fulltime')


def weekend(request):
    return _page(request, 'web/weekend.html', 'weekend')


def etc(request):
    return _page(request, 'web/etc.html', 'etc')


def onetime(request):
    return _page(request, 'web/onetime.html', 'onetime')
