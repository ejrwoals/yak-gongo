"""공개 페이지가 읽는 대시보드 스냅샷 로더.

로컬(관리자): DB의 최신 DashboardSnapshot에서 읽는다.
배포본(Cloud Run): 번들된 JSON 파일에서 읽는다 → DB 불필요, stateless.
분기는 settings.SNAPSHOT_FROM_FILE 플래그로 제어한다.
"""
import json

from django.conf import settings


def get_latest_snapshot():
    """정규화된 스냅샷 dict 반환, 없으면 None.

    반환 형태: {'data': {...}, 'posting_count': int, 'last_update': 'YYYY-MM-DD'}
    """
    if getattr(settings, 'SNAPSHOT_FROM_FILE', False):
        return _load_from_file()
    return _load_from_db()


def _load_from_db():
    """로컬: DB에서 최신 스냅샷을 읽는다."""
    from django.utils import timezone
    # 배포본에는 postings 앱이 없으므로 DB 모드에서만 지연 import 한다.
    from postings.models import DashboardSnapshot

    snap = DashboardSnapshot.objects.order_by('-created_at').first()
    if not snap:
        return None
    return {
        'data': snap.data,
        'posting_count': snap.posting_count,
        'last_update': timezone.localtime(snap.created_at).strftime('%Y-%m-%d'),
    }


def _load_from_file():
    """배포본: 번들된 스냅샷 JSON에서 읽는다 (DB 접근 없음)."""
    path = settings.SNAPSHOT_FILE_PATH
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding='utf-8'))
    return {
        'data': raw.get('data'),
        'posting_count': raw.get('posting_count'),
        'last_update': raw.get('last_update'),
    }
