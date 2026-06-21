"""management command: 공고를 크롤링하여 RawPosting(스테이징)으로 저장.

    python manage.py scrape_postings --source yakdap --start-id 38800 --count 100 --step 2 --year 2024
    python manage.py scrape_postings --source pharm_recruit --big-category 서울 --year 2026

공고를 한 건씩 즉시 RawPosting에 저장하므로 도중에 멈춰도 긁은 것은 남는다.
재실행하면 이미 저장된 URL은 건너뛰고 이어서 크롤링한다.
LLM 처리는 별도 명령(process_postings)이 담당한다.
"""
import threading

from django.core.management.base import BaseCommand
from django.utils import timezone

from postings.models import PipelineRun
from pipeline.stages import scrape_stage


class Command(BaseCommand):
    help = '공고를 크롤링하여 RawPosting 스테이징 테이블에 저장합니다. (LLM 처리는 process_postings)'

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True, choices=['yakdap', 'pharm_recruit'])
        # yakdap 전용
        parser.add_argument('--start-id', type=int, default=38800)
        parser.add_argument('--count', type=int, default=100)
        parser.add_argument('--step', type=int, default=2)
        parser.add_argument('--year', type=int, default=2024)
        # pharm_recruit 전용
        parser.add_argument('--big-category', type=str, nargs='+', default=['서울'])
        parser.add_argument('--pharm-count', type=int, default=None,
                            help='팜리크루트 수집 개수 한도 (None=전체). 선택 지역·도시 별로 균등 분배.')
        # 공통
        parser.add_argument('--headless', action='store_true', default=False)
        parser.add_argument('--run-id', type=int, default=None,
                            help='Admin UI에서 미리 생성된 PipelineRun ID (내부용)')

    def handle(self, *args, **options):
        source = options['source']
        run_id = options['run_id']
        login_event = options.get('login_event')

        if run_id:
            run = PipelineRun.objects.get(id=run_id)
        else:
            run = PipelineRun.objects.create(
                source=source,
                status='running',
                log_output='스크래핑 시작...\n',
            )

        # 로그를 stdout + run.log_output(버퍼링)에 기록
        buffer = []

        def _log(msg: str):
            self.stdout.write(msg)
            buffer.append(msg + '\n')
            if len(buffer) >= 10:
                run.log_output += ''.join(buffer)
                buffer.clear()
                run.save(update_fields=['log_output'])

        try:
            saved = scrape_stage(source, options, run, login_event=login_event, log=_log)
        except Exception as e:
            run.log_output += ''.join(buffer) + f'\n[SCRAPE ERROR] {e}\n'
            run.status = 'failed'
            run.finished_at = timezone.now()
            run.save()
            raise

        run.log_output += ''.join(buffer)
        run.status = 'done'
        run.finished_at = timezone.now()
        run.save()

        self.stdout.write(self.style.SUCCESS(f'스크래핑 완료: {saved}개 신규 RawPosting 저장'))
