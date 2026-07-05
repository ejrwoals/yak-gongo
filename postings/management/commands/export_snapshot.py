"""최신 DashboardSnapshot을 web/snapshot/latest.json 으로 export.

배포(deploy.sh) 직전에 실행되어, Cloud Run 배포본이 DB 없이 읽을
정적 스냅샷 아티팩트를 만든다.
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from postings.models import DashboardSnapshot


class Command(BaseCommand):
    help = "최신 대시보드 스냅샷을 web/snapshot/latest.json 으로 내보낸다 (배포 아티팩트)."

    def handle(self, *args, **options):
        snap = DashboardSnapshot.objects.order_by('-created_at').first()
        if not snap:
            self.stderr.write(self.style.ERROR(
                "스냅샷이 없습니다. 먼저 어드민에서 '대시보드 업데이트'를 실행하세요."
            ))
            return

        payload = {
            'data': snap.data,
            'posting_count': snap.posting_count,
            'last_update': timezone.localtime(snap.created_at).strftime('%Y-%m-%d'),
        }

        out_path = settings.SNAPSHOT_FILE_PATH
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        self.stdout.write(self.style.SUCCESS(
            f"스냅샷 export 완료 → {out_path} "
            f"(공고 {snap.posting_count}건, 기준일 {payload['last_update']})"
        ))
