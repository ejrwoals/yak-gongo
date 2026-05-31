"""
3단계 비에러 이상치 공고를 LLM(Gemini)으로 일괄 자동 검토하는 관리 커맨드.

웹 대시보드의 '🤖 LLM으로 자동 검토' 버튼과 동일 로직(verify_posting/apply_verdict)을
CLI 로 실행한다. 대량 일괄 처리·디버깅용.

사용 예:
    .venv/bin/python manage.py auto_verify_step3                      # 4개 프리셋 전체
    .venv/bin/python manage.py auto_verify_step3 --preset workdays_outlier
    .venv/bin/python manage.py auto_verify_step3 --limit 20
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from postings.models import AdminCheck, JobPosting
from postings.review_presets import VERIFY_PRESET_KEYS, get_preset_queryset
from postings.review_verify import apply_verdict, verify_posting


class Command(BaseCommand):
    help = '3단계 비에러 이상치 공고를 LLM(Gemini)으로 일괄 자동 검토'

    def add_arguments(self, parser):
        parser.add_argument('--preset', choices=VERIFY_PRESET_KEYS, default=None,
                            help='특정 프리셋만 검토 (생략 시 4개 전체)')
        parser.add_argument('--limit', type=int, default=None, help='최대 처리 건수')

    def handle(self, *args, **options):
        if not settings.GOOGLE_API_KEY:
            raise CommandError('GOOGLE_API_KEY 가 설정되지 않았습니다.')

        from google import genai
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model_name = settings.LLM_MODEL

        preset_keys = [options['preset']] if options['preset'] else list(VERIFY_PRESET_KEYS)

        # 프리셋별 후보 id 수집 (중복 제거, 입력 순서 보존)
        seen = set()
        plan = []  # [(preset_key, id), ...]
        for key in preset_keys:
            for pk in get_preset_queryset(key, JobPosting.objects.all()).values_list('id', flat=True):
                if pk in seen:
                    continue
                seen.add(pk)
                plan.append((key, pk))
        if options['limit']:
            plan = plan[:options['limit']]

        total = len(plan)
        self.stdout.write(f'검토 대상: {total}건')
        counts = {'ok': 0, 'error': 0, 'failed': 0, 'skipped': 0}

        for i, (key, pk) in enumerate(plan, 1):
            posting = JobPosting.objects.filter(pk=pk).first()
            if posting is None or posting.has_error or AdminCheck.objects.filter(posting_id=pk).exists():
                counts['skipped'] += 1
                continue
            try:
                verdict = verify_posting(posting, key, client, model_name)
                status = apply_verdict(posting, verdict)
            except Exception as e:  # noqa: BLE001
                status = 'failed'
                self.stderr.write(f'  pk={pk} ERROR: {e}')
            counts[status] = counts.get(status, 0) + 1
            self.stdout.write(f'[{i}/{total}] pk={pk} ({key}) → {status}')

        self.stdout.write(self.style.SUCCESS(
            f"완료 · 정상 {counts['ok']} · 에러 {counts['error']} "
            f"· 실패 {counts['failed']} · 스킵 {counts['skipped']}"
        ))
