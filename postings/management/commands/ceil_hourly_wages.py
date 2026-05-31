"""
시급 일괄 올림 보정 (1회성).

계산식이 시급을 구조적으로 살짝 낮게 평가해(예: 실제 4.0 → 3.993 으로 저장),
LLM 자동 검토에서 불필요하게 '틀림'으로 잡히는 문제가 있었다.
세후 시급(net_hourly_wage)·일회성 시급(one_time_hourly_wage) 를 **소수점 셋째 자리에서 올림**하여
둘째 자리까지로 보정한다. 셋째 자리가 0이면 올림이 no-op 이라 값이 그대로 유지된다(예: 4.28 → 4.28).

사용:
    .venv/bin/python manage.py ceil_hourly_wages --dry-run   # 미리보기
    .venv/bin/python manage.py ceil_hourly_wages             # 실제 적용
"""
from django.core.management.base import BaseCommand

from pipeline.salary import ceil_hourly_wage
from postings.models import JobPosting

_FIELDS = ['net_hourly_wage', 'one_time_hourly_wage']


class Command(BaseCommand):
    help = 'net_hourly_wage·one_time_hourly_wage 를 소수점 셋째 자리에서 올림(둘째 자리까지) 보정'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='변경 없이 미리보기만')

    def handle(self, *args, **options):
        dry = options['dry_run']

        for field in _FIELDS:
            qs = JobPosting.objects.filter(**{f'{field}__isnull': False})
            total = qs.count()
            to_update = []
            shown = 0
            for p in qs.iterator():
                old = getattr(p, field)
                new = ceil_hourly_wage(old)
                if new != old:
                    if shown < 10:
                        self.stdout.write(f'  [{field}] #{p.id}: {old} -> {new}')
                        shown += 1
                    setattr(p, field, new)
                    to_update.append(p)

            changed = len(to_update)
            if changed > shown:
                self.stdout.write(f'  ... 외 {changed - shown}건')

            if dry:
                self.stdout.write(f'[DRY-RUN] {field}: 대상 {total}건 중 {changed}건 변경 예정')
                continue

            # bulk_update 는 save() 를 호출하지 않으므로 has_error/updated_at 부작용 없이 해당 시급만 갱신
            JobPosting.objects.bulk_update(to_update, [field], batch_size=500)
            self.stdout.write(self.style.SUCCESS(f'{field}: {total}건 중 {changed}건 보정'))
