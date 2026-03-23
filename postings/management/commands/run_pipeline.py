"""
management command: python manage.py run_pipeline --source <yakdap|pharm_recruit>

yakdap 예시:
    python manage.py run_pipeline --source yakdap --start-id 38800 --count 100 --step 2 --year 2024

pharm_recruit 예시:
    python manage.py run_pipeline --source pharm_recruit --big-category 서울
"""
import io
import sys
import threading

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from google import genai

from postings.models import JobPosting, PipelineRun
from pipeline.runner import process_posting
from geo.mapping import normalize_city, assign_big_category


class Command(BaseCommand):
    help = '공고를 스크래핑하고 LLM 파이프라인으로 처리하여 DB에 저장합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--source', required=True, choices=['yakdap', 'pharm_recruit'])
        # yakdap 전용
        parser.add_argument('--start-id', type=int, default=38800)
        parser.add_argument('--count', type=int, default=100)
        parser.add_argument('--step', type=int, default=2)
        parser.add_argument('--year', type=int, default=2024)
        # pharm_recruit 전용
        parser.add_argument('--big-category', type=str, default='서울')
        # 공통
        parser.add_argument('--headless', action='store_true', default=False)
        parser.add_argument('--dry-run', action='store_true', default=False,
                            help='스크래핑만 하고 LLM 처리 및 DB 저장은 건너뜁니다.')
        # Admin UI 연동용: 미리 생성된 PipelineRun ID
        parser.add_argument('--run-id', type=int, default=None,
                            help='Admin UI에서 미리 생성된 PipelineRun ID (내부용)')

    def handle(self, *args, **options):
        source = options['source']
        dry_run = options['dry_run']
        run_id = options['run_id']

        existing_urls: set[str] = set(
            JobPosting.objects.values_list('url', flat=True)
        )
        self.stdout.write(f'기존 URL {len(existing_urls)}개 로드 완료')

        login_event = options.get('login_event')

        # 스크래핑 단계용 로그 콜백 (DB에 실시간 기록)
        def _scrape_log(msg: str):
            self.stdout.write(msg)
            if run_id:
                try:
                    run = PipelineRun.objects.get(id=run_id)
                    run.log_output += msg + '\n'
                    run.save(update_fields=['log_output'])
                except PipelineRun.DoesNotExist:
                    pass

        # ── 스크래핑 ──────────────────────────────────────────────
        if source == 'yakdap':
            from scraper.yakdap import scrape
            raw_postings = scrape(
                start_id=options['start_id'],
                count=options['count'],
                step=options['step'],
                year=options['year'],
                headless=options['headless'],
                existing_urls=existing_urls,
                login_event=login_event,
                log=_scrape_log,
            )
        else:
            from scraper.pharm_recruit import scrape
            raw_postings = scrape(
                big_category=options['big_category'],
                headless=options['headless'],
                existing_urls=existing_urls,
                log=_scrape_log,
            )

        self.stdout.write(f'스크래핑 완료: {len(raw_postings)}개')

        if dry_run:
            dry_log_lines = [f'스크래핑 완료: {len(raw_postings)}개\n']
            for i, raw in enumerate(raw_postings, start=1):
                line = (
                    f'[{i}/{len(raw_postings)}] '
                    f'{raw.get("title", "(제목 없음)")} | '
                    f'{raw.get("pharmacy_name", "")} | '
                    f'{raw.get("city", "")} | '
                    f'{raw.get("url", "")}'
                )
                self.stdout.write(line)
                dry_log_lines.append(line + '\n')
            dry_log_lines.append('[dry-run] LLM 처리 및 DB 저장 건너뜀\n')
            self.stdout.write('[dry-run] LLM 처리 및 DB 저장 건너뜀')
            if run_id:
                run = PipelineRun.objects.get(id=run_id)
                run.total_scraped = len(raw_postings)
                run.status = 'done'
                run.finished_at = timezone.now()
                run.log_output += ''.join(dry_log_lines)
                run.save()
            return

        # ── PipelineRun 레코드 준비 ───────────────────────────────
        if run_id:
            run = PipelineRun.objects.get(id=run_id)
            run.total_scraped = len(raw_postings)
            run.log_output += f'스크래핑 완료: {len(raw_postings)}개\n'
            run.save()
        else:
            run = PipelineRun.objects.create(
                source=source,
                started_at=timezone.now(),
                total_scraped=len(raw_postings),
                status='running',
                log_output=f'스크래핑 완료: {len(raw_postings)}개\n',
            )

        # ── 로그 누적 헬퍼 ────────────────────────────────────────
        _log_buffer = []
        _log_lock = threading.Lock()

        def _flush_log(force=False):
            with _log_lock:
                if _log_buffer and (force or len(_log_buffer) >= 10):
                    run.log_output += ''.join(_log_buffer)
                    _log_buffer.clear()
                    run.save(update_fields=['log_output', 'total_processed', 'total_errors'])

        def _log(msg: str):
            self.stdout.write(msg)
            with _log_lock:
                _log_buffer.append(msg + '\n')

        # ── LLM 파이프라인 ─────────────────────────────────────────
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model_name = settings.LLM_MODEL

        total_processed = 0
        total_errors = 0

        for idx, raw in enumerate(raw_postings, start=1):
            url = raw['url']
            title = raw.get('title', '')

            if JobPosting.objects.filter(url=url).exists():
                _log(f'[SKIP] {url}')
                _flush_log()
                continue

            _log(f'\n{"━"*10} [{idx}/{len(raw_postings)}] {"━"*10}')
            _log(f'URL  : {url}')
            _log(f'제목 : {title}')

            body = raw.get('body', '')

            # stdout 캡처 (tasks/validator의 print() 포함)
            captured = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured
            try:
                pipeline_result = process_posting(body, client, model_name, log=_log)
            except Exception as e:
                sys.stdout = old_stdout
                _log(f'[PIPELINE ERROR] {url}: {e}')
                total_errors += 1
                run.total_errors = total_errors
                _flush_log(force=True)
                continue
            finally:
                sys.stdout = old_stdout
                captured_text = captured.getvalue()
                if captured_text.strip():
                    _log(f'[stdout] {captured_text.strip()}')

            # 지역 정규화
            city_raw = raw.get('city', '')
            city = normalize_city(city_raw) or city_raw
            big_category = raw.get('big_category') or assign_big_category(city)

            posting = JobPosting(
                url=url,
                platform=raw.get('platform', ''),
                created_at=raw.get('created_at') or None,
                title=title,
                pharmacy_name=raw.get('pharmacy_name', ''),
                body=body,
                city=city,
                big_category=big_category,
                **pipeline_result,
            )
            posting.save()
            total_processed += 1
            run.total_processed = total_processed

            if pipeline_result.get('has_error'):
                total_errors += 1
                run.total_errors = total_errors
                _log('  → 저장 완료 (has_error=True)')
            else:
                _log('  → 저장 완료 ✓')

            _flush_log()

        # ── 완료 처리 ─────────────────────────────────────────────
        _log(f'\n{"="*40}')
        _log(f'완료: {total_processed}개 저장, {total_errors}개 에러')
        run.finished_at = timezone.now()
        run.status = 'done'
        _flush_log(force=True)
        run.save()

        self.stdout.write(
            self.style.SUCCESS(f'완료: {total_processed}개 저장, {total_errors}개 에러')
        )
