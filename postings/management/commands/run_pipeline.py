"""
management command: python manage.py run_pipeline --source <yakdap|pharm_recruit>

yakdap 예시:
    python manage.py run_pipeline --source yakdap --start-id 38800 --count 100 --step 2 --year 2024

pharm_recruit 예시:
    python manage.py run_pipeline --source pharm_recruit --big-category 서울
"""
import django
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

    def handle(self, *args, **options):
        source = options['source']
        dry_run = options['dry_run']

        existing_urls: set[str] = set(
            JobPosting.objects.values_list('url', flat=True)
        )
        self.stdout.write(f'기존 URL {len(existing_urls)}개 로드 완료')

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
            )
        else:
            from scraper.pharm_recruit import scrape
            raw_postings = scrape(
                big_category=options['big_category'],
                headless=options['headless'],
                existing_urls=existing_urls,
            )

        self.stdout.write(f'스크래핑 완료: {len(raw_postings)}개')

        if dry_run:
            self.stdout.write('[dry-run] LLM 처리 및 DB 저장 건너뜀')
            return

        # ── LLM 파이프라인 ─────────────────────────────────────────
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model_name = settings.LLM_MODEL

        run = PipelineRun.objects.create(
            source=source,
            started_at=timezone.now(),
            total_scraped=len(raw_postings),
            status='running',
        )

        total_processed = 0
        total_errors = 0

        for raw in raw_postings:
            url = raw['url']
            if JobPosting.objects.filter(url=url).exists():
                self.stdout.write(f'[SKIP] {url}')
                continue

            body = raw.get('body', '')
            try:
                pipeline_result = process_posting(body, client, model_name)
            except Exception as e:
                self.stderr.write(f'[PIPELINE ERROR] {url}: {e}')
                total_errors += 1
                continue

            # 지역 정규화
            city_raw = raw.get('city', '')
            city = normalize_city(city_raw) or city_raw
            big_category = raw.get('big_category') or assign_big_category(city)

            posting = JobPosting(
                url=url,
                platform=raw.get('platform', ''),
                created_at=raw.get('created_at') or None,
                title=raw.get('title', ''),
                pharmacy_name=raw.get('pharmacy_name', ''),
                body=body,
                city=city,
                big_category=big_category,
                **pipeline_result,
            )
            posting.save()
            total_processed += 1

            status = 'ERROR' if pipeline_result.get('has_error') else 'OK'
            if pipeline_result.get('has_error'):
                total_errors += 1
            self.stdout.write(f'[{status}] {url}')

        run.finished_at = timezone.now()
        run.total_processed = total_processed
        run.total_errors = total_errors
        run.status = 'done'
        run.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'완료: {total_processed}개 저장, {total_errors}개 에러'
            )
        )
