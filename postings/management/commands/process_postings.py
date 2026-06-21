"""management command: pending RawPosting을 LLM 처리하여 JobPosting을 생성.

    python manage.py process_postings

status='pending'인 RawPosting만 처리하며, 각 건은 처리 후 status가 갱신된다.
도중에 멈춰도 재실행하면 아직 pending인 것부터 이어서 처리한다(resume).
크롤링은 별도 명령(scrape_postings)이 담당한다.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from postings.models import PipelineRun, RawPosting
from pipeline.stages import process_stage


class Command(BaseCommand):
    help = 'pending RawPosting을 LLM 파이프라인으로 처리하여 JobPosting을 생성합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--run-id', type=int, default=None,
                            help='로그를 기록할 PipelineRun ID (내부용). 없으면 새로 생성.')

    def handle(self, *args, **options):
        run_id = options['run_id']

        pending = RawPosting.objects.filter(status=RawPosting.STATUS_PENDING).count()
        if pending == 0:
            self.stdout.write('처리할 pending RawPosting이 없습니다.')
            return

        if run_id:
            run = PipelineRun.objects.get(id=run_id)
        else:
            run = PipelineRun.objects.create(
                source='process',
                status='running',
                total_scraped=pending,
                log_output=f'LLM 처리 시작: pending {pending}개\n',
            )

        buffer = []

        def _log(msg: str):
            self.stdout.write(msg)
            buffer.append(msg + '\n')
            if len(buffer) >= 10:
                run.log_output += ''.join(buffer)
                buffer.clear()
                run.save(update_fields=['log_output', 'total_processed', 'total_errors'])

        try:
            stats = process_stage(run, log=_log)
        except Exception as e:
            run.log_output += ''.join(buffer) + f'\n[FATAL ERROR] {e}\n'
            run.status = 'failed'
            run.finished_at = timezone.now()
            run.save()
            raise

        run.log_output += ''.join(buffer)
        run.status = 'done'
        run.finished_at = timezone.now()
        run.save()

        msg = f"완료: {stats['processed']}개 저장, {stats['errors']}개 에러"
        if stats['skipped']:
            msg += f", {stats['skipped']}개 급여 미명시 건너뜀"
        self.stdout.write(self.style.SUCCESS(msg))
