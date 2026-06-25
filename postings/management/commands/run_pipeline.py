"""management command: 크롤링 + LLM 처리를 한 번에 실행하는 오케스트레이터.

    python manage.py run_pipeline --source yakdap --start-id 38800 --count 100 --step 2 --year 2024
    python manage.py run_pipeline --source pharm_recruit --big-category 서울 --year 2026

내부적으로 두 단계를 순서대로 실행한다:
  1) scrape_stage  : 공고를 크롤링하여 RawPosting(스테이징)으로 즉시 저장
  2) process_stage : pending RawPosting을 LLM 처리하여 JobPosting 생성

두 단계 모두 멱등하므로 도중에 멈춰도 같은 명령을 다시 실행하면 이어서 진행된다.
단계를 따로 돌리려면 scrape_postings / process_postings 명령을 사용한다.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from postings.models import PipelineRun
from pipeline.stages import scrape_stage, process_stage


class Command(BaseCommand):
    help = '공고를 스크래핑하고 LLM 파이프라인으로 처리하여 DB에 저장합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True, choices=['yakdap', 'pharm_recruit'])
        # yakdap 전용
        parser.add_argument('--start-id', type=int, default=38800)
        parser.add_argument('--count', type=int, default=100)
        parser.add_argument('--step', type=int, default=2)
        parser.add_argument('--year', type=int, default=None,
                            help='등록일 연도 폴백 (기본: 현재 연도). 약문약답은 공고에 적힌 연도를 우선 사용.')
        # pharm_recruit 전용
        parser.add_argument('--big-category', type=str, nargs='+', default=['서울'])
        parser.add_argument('--pharm-count', type=int, default=None,
                            help='팜리크루트 수집 개수 한도 (None=전체). 선택 지역·도시 별로 균등 분배.')
        # 공통
        parser.add_argument('--headless', action='store_true', default=False)
        parser.add_argument('--dry-run', action='store_true', default=False,
                            help='스크래핑(RawPosting 저장)만 하고 LLM 처리는 건너뜁니다.')
        # Admin UI 연동용: 미리 생성된 PipelineRun ID
        parser.add_argument('--run-id', type=int, default=None,
                            help='Admin UI에서 미리 생성된 PipelineRun ID (내부용)')

    def handle(self, *args, **options):
        source = options['source']
        dry_run = options['dry_run']
        run_id = options['run_id']
        login_event = options.get('login_event')

        if run_id:
            run = PipelineRun.objects.get(id=run_id)
        else:
            run = PipelineRun.objects.create(
                source=source,
                status='running',
                log_output='파이프라인 시작...\n',
            )

        # 로그를 stdout + run.log_output에 기록.
        # 대시보드/로그 패널이 거의 실시간으로 보이도록 한 줄마다 즉시 DB에 반영한다.
        buffer = []

        def _log(msg: str):
            self.stdout.write(msg)
            run.log_output += msg + '\n'
            run.save(update_fields=['log_output', 'total_scraped', 'total_processed', 'total_errors'])

        def _flush():
            if buffer:
                run.log_output += ''.join(buffer)
                buffer.clear()
            run.save()

        try:
            # ── 1단계: 스크래핑 → RawPosting ──────────────────────────
            scrape_stage(source, options, run, login_event=login_event, log=_log)

            if dry_run:
                _log('[dry-run] LLM 처리 건너뜀 (RawPosting까지만 저장)')
                run.status = 'done'
                run.finished_at = timezone.now()
                _flush()
                self.stdout.write(self.style.SUCCESS(f'[dry-run] 스크래핑 완료: {run.total_scraped}개'))
                return

            # ── 2단계: pending RawPosting → LLM → JobPosting ──────────
            stats = process_stage(run, log=_log)
        except Exception as e:
            _log(f'\n[FATAL ERROR] {e}')
            run.status = 'failed'
            run.finished_at = timezone.now()
            _flush()
            raise

        run.status = 'done'
        run.finished_at = timezone.now()
        _flush()

        msg = f"완료: {stats['processed']}개 저장, {stats['errors']}개 에러"
        if stats['skipped']:
            msg += f", {stats['skipped']}개 급여 미명시 건너뜀"
        self.stdout.write(self.style.SUCCESS(msg))
