from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from postings.models import AdminCheck, JobPosting

# 레거시 검토 기록임을 나타내는 표식 시각.
LEGACY_CHECKED_AT = timezone.make_aware(datetime(2000, 1, 1, 0, 0, 0))


class Command(BaseCommand):
    help = (
        "레거시 데이터에서 넘어온 user_reviewed=True 공고에 AdminCheck를 백필한다. "
        "checked_at은 레거시 표식으로 2000-01-01로 설정한다."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='실제로 생성하지 않고 대상 건수만 출력한다.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # user_reviewed=True 이면서 아직 AdminCheck가 없는 공고.
        target_ids = list(
            JobPosting.objects.filter(
                user_reviewed=True, admin_check__isnull=True
            ).values_list('id', flat=True)
        )

        self.stdout.write(f"백필 대상: {len(target_ids)}건")

        if dry_run:
            self.stdout.write(self.style.WARNING("dry-run: 변경 없음"))
            return

        if not target_ids:
            self.stdout.write(self.style.SUCCESS("대상 없음. 종료."))
            return

        with transaction.atomic():
            # auto_now_add=True 때문에 bulk_create 시점에는 현재 시각이 들어간다.
            AdminCheck.objects.bulk_create(
                [AdminCheck(posting_id=pk) for pk in target_ids]
            )
            # .update()는 pre_save(auto_now_add)를 우회하므로 레거시 시각으로 덮어쓴다.
            updated = AdminCheck.objects.filter(
                posting_id__in=target_ids
            ).update(checked_at=LEGACY_CHECKED_AT)

        self.stdout.write(
            self.style.SUCCESS(
                f"AdminCheck {updated}건 생성 완료 (checked_at={LEGACY_CHECKED_AT:%Y-%m-%d})"
            )
        )
