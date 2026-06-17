from django.shortcuts import render
from django.utils import timezone

from postings.models import DashboardSnapshot


def _latest_snapshot():
    return DashboardSnapshot.objects.order_by('-created_at').first()


def _page(request, template, section):
    """최신 스냅샷에서 한 섹션(home/fulltime)을 떼어 템플릿에 전달."""
    snap = _latest_snapshot()
    payload = {
        'data': (snap.data.get(section) if snap else None),
        'lastUpdate': (timezone.localtime(snap.created_at).strftime('%Y-%m-%d') if snap else None),
    }
    return render(request, template, {'dashboard': payload})


def home(request):
    return _page(request, 'web/home.html', 'home')


def compare(request):
    return _page(request, 'web/compare.html', 'compare')


def compare_result(request):
    return _page(request, 'web/compare_result.html', 'compare')


def fulltime(request):
    return _page(request, 'web/fulltime.html', 'fulltime')


def weekend(request):
    return _page(request, 'web/weekend.html', 'weekend')


def etc(request):
    return _page(request, 'web/etc.html', 'etc')


def onetime(request):
    return _page(request, 'web/onetime.html', 'onetime')
