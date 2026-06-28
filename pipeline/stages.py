"""파이프라인 2단계 공통 로직.

scrape_stage  : 공고를 크롤링하여 RawPosting(status=pending)으로 즉시 저장.
process_stage : pending RawPosting을 LLM 처리하여 JobPosting을 생성.

두 단계 모두 멱등(idempotent)하다. 도중에 멈춰도 이미 저장된 RawPosting/
JobPosting은 남으며, 재실행하면 끊긴 지점부터 이어서 진행된다.

- scrape_stage: JobPosting/RawPosting에 이미 있는 URL은 건너뛴다.
- process_stage: status='pending'인 RawPosting만 처리한다.
"""
import io
import sys

from django.conf import settings
from django.utils import timezone

from google import genai

from postings.models import JobPosting, PipelineRun, RawPosting
from pipeline.runner import process_posting
from geo.mapping import normalize_city, assign_big_category


def _default_log(msg: str):
    print(msg)


def scrape_param_fields(options: dict) -> dict:
    """PipelineRun에 기록할 스크래핑 파라미터 필드를 옵션에서 추출한다.

    yakdap → start_id/count/step, pharm_recruit → big_categories.
    run 생성 시 **scrape_param_fields(options) 형태로 펼쳐 넣는다.
    """
    if options.get('source') == 'yakdap':
        return {
            'start_id': options.get('start_id'),
            'count': options.get('count'),
            'step': options.get('step'),
        }
    big = options.get('big_categories') or options.get('big_category') or []
    if isinstance(big, str):
        big = [big]
    return {'big_categories': list(big)}


# ── 스크래핑 단계 ──────────────────────────────────────────────────────────
def scrape_stage(source: str, options: dict, run: PipelineRun, login_event=None, log=None) -> int:
    """공고를 크롤링하여 RawPosting으로 즉시 저장한다. 저장된(신규) 건수를 반환.

    이미 JobPosting 또는 RawPosting에 존재하는 URL은 스크래퍼 단계에서 스킵되므로,
    재실행 시 끊긴 지점부터 크롤링을 이어간다.
    """
    log = log or _default_log

    existing_urls: set[str] = set(JobPosting.objects.values_list('url', flat=True))
    existing_urls |= set(RawPosting.objects.values_list('url', flat=True))
    log(f'기존 URL {len(existing_urls)}개 로드 완료 (JobPosting + RawPosting)')

    saved = 0
    errors = 0

    def on_error(item_id, exc):
        """스크래핑 건별 실패를 run.total_errors에 집계한다."""
        nonlocal errors
        errors += 1
        if run is not None:
            run.total_errors = errors
            run.save(update_fields=['total_errors'])

    def on_item(record: dict):
        nonlocal saved
        _, created = RawPosting.objects.update_or_create(
            url=record['url'],
            defaults={
                'platform': record.get('platform', ''),
                'created_at': record.get('created_at') or None,
                'title': record.get('title', ''),
                'pharmacy_name': record.get('pharmacy_name', ''),
                'body': record.get('body', ''),
                'city': record.get('city', ''),
                'big_category': record.get('big_category', ''),
                'status': RawPosting.STATUS_PENDING,
                'run': run,
            },
        )
        if created:
            saved += 1
            if run is not None:
                run.total_scraped = saved
                run.save(update_fields=['total_scraped'])

    if source == 'yakdap':
        from scraper.yakdap import scrape
        scrape(
            start_id=options['start_id'],
            count=options['count'],
            step=options['step'],
            year=options.get('year'),
            headless=options['headless'],
            existing_urls=existing_urls,
            login_event=login_event,
            log=log,
            on_item=on_item,
            on_error=on_error,
        )
    else:
        import math as _math
        from scraper.pharm_recruit import scrape
        big_categories = options.get('big_categories') or options.get('big_category') or ['서울']
        if isinstance(big_categories, str):
            big_categories = [big_categories]
        pharm_count = options.get('pharm_count')
        per_category = (
            _math.ceil(pharm_count / len(big_categories)) if pharm_count else None
        )
        for big_cat in big_categories:
            limit_msg = f' (최대 {per_category}개)' if per_category else ' (전체)'
            log(f'[{big_cat}] 스크래핑 시작{limit_msg}')
            scrape(
                big_category=big_cat,
                year=options.get('year'),
                headless=options['headless'],
                existing_urls=existing_urls,
                category_limit=per_category,
                log=log,
                on_item=on_item,
            )

    done_msg = f'스크래핑 완료: {saved}개 신규 저장 (RawPosting)'
    if errors:
        done_msg += f', {errors}개 수집 실패'
    log(done_msg)
    return saved


# ── LLM 처리 단계 ──────────────────────────────────────────────────────────
def process_stage(run: PipelineRun, log=None, client=None, model_name: str = '') -> dict:
    """pending RawPosting을 LLM 처리하여 JobPosting을 생성한다.

    각 RawPosting은 처리 결과에 따라 status가 갱신되므로, 도중에 멈춰도
    재실행하면 아직 pending인 것부터 이어서 처리한다.

    Returns:
        {'processed': int, 'errors': int, 'skipped': int}
    """
    log = log or _default_log

    if client is None:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    if not model_name:
        model_name = settings.LLM_MODEL

    # 처리 중 status를 갱신하므로, 대상 pk를 먼저 스냅샷으로 확보한다.
    pending_ids = list(
        RawPosting.objects.filter(status=RawPosting.STATUS_PENDING)
        .order_by('scraped_at')
        .values_list('id', flat=True)
    )
    total = len(pending_ids)
    log(f'LLM 처리 대기: {total}개')

    processed = 0
    errors = 0
    skipped = 0

    for idx, raw_id in enumerate(pending_ids, start=1):
        try:
            raw = RawPosting.objects.get(id=raw_id)
        except RawPosting.DoesNotExist:
            continue

        log(f'\n{"━"*10} [{idx}/{total}] {"━"*10}')
        result = process_raw_posting(raw, client, model_name, log=log)

        status = result['status']
        if status in ('ok', 'error'):
            processed += 1
            if status == 'error':
                errors += 1
        elif status == 'failed':
            errors += 1
        elif status == 'skipped':
            skipped += 1

        if run is not None:
            run.total_errors = errors
            run.save(update_fields=['total_errors'])

    log(f'\n{"="*40}')
    log(f'완료: {processed}개 저장, {errors}개 에러')
    if skipped:
        log(f'{skipped}개 급여 미명시 건너뜀')

    return {'processed': processed, 'errors': errors, 'skipped': skipped}


def process_raw_posting(raw, client, model_name: str = '', log=None) -> dict:
    """단일 RawPosting을 LLM 처리하여 JobPosting을 생성하고 status를 갱신한다.

    process_stage(일괄)와 대시보드의 건별 처리(진행 모달)가 공유하는 단위 처리 함수.

    Returns dict:
        {'id', 'title', 'status', 'note'}
        status ∈ {'ok'(저장 완료), 'error'(저장했으나 검산 에러), 'skipped'(급여 미명시),
                  'failed'(파이프라인 예외)}
    """
    log = log or _default_log

    if client is None:
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    if not model_name:
        model_name = settings.LLM_MODEL

    base = {'id': raw.id, 'title': raw.title}

    # 이미 JobPosting이 있으면(과거 직접 저장분 등) 처리 완료로 표시
    if JobPosting.objects.filter(url=raw.url).exists():
        raw.status = RawPosting.STATUS_PROCESSED
        raw.processed_at = timezone.now()
        raw.save(update_fields=['status', 'processed_at'])
        log(f'[SKIP] 이미 존재: {raw.url}')
        return {**base, 'status': 'ok', 'note': '이미 JobPosting 존재'}

    log(f'URL  : {raw.url}')
    log(f'제목 : {raw.title}')

    # stdout 캡처 (tasks/validator의 print() 포함)
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        pipeline_result = process_posting(raw.body, client, model_name, log=log)
    except Exception as e:
        sys.stdout = old_stdout
        log(f'[PIPELINE ERROR] {raw.url}: {e}')
        raw.status = RawPosting.STATUS_ERROR
        raw.error_log = str(e)
        raw.save(update_fields=['status', 'error_log'])
        return {**base, 'status': 'failed', 'note': str(e)}
    finally:
        sys.stdout = old_stdout
        captured_text = captured.getvalue()
        if captured_text.strip():
            log(f'[stdout] {captured_text.strip()}')

    if pipeline_result is None:
        raw.status = RawPosting.STATUS_SKIPPED
        raw.processed_at = timezone.now()
        raw.save(update_fields=['status', 'processed_at'])
        log('  → 급여 미명시, 저장 건너뜀')
        return {**base, 'status': 'skipped', 'note': '급여 미명시',
                'steps': [{'task': 'Task1 급여', 'detail': '급여 미명시 → 저장 건너뜀', 'error': False}]}

    # UI 현황판용 단계 요약은 DB 필드가 아니므로 JobPosting 생성 전에 분리한다.
    steps = pipeline_result.pop('steps', [])

    # 지역 정규화 (JobPosting 생성 시점에 수행)
    city_raw = raw.city
    city = normalize_city(city_raw) or city_raw
    big_category = raw.big_category or assign_big_category(city)

    posting = JobPosting(
        url=raw.url,
        platform=raw.platform,
        created_at=raw.created_at or None,
        title=raw.title,
        pharmacy_name=raw.pharmacy_name,
        body=raw.body,
        city=city,
        big_category=big_category,
        **pipeline_result,
    )
    posting.save()
    raw.status = RawPosting.STATUS_PROCESSED
    raw.processed_at = timezone.now()
    raw.save(update_fields=['status', 'processed_at'])

    fields = _summary_fields(posting)
    if pipeline_result.get('gpt_error_log'):
        log('  → 저장 완료 (has_error=True)')
        return {**base, 'status': 'error', 'note': pipeline_result.get('gpt_error_log', '')[:200],
                'steps': steps, 'fields': fields}
    log('  → 저장 완료 ✓')
    return {**base, 'status': 'ok', 'note': '', 'steps': steps, 'fields': fields}


def _summary_fields(posting) -> list[dict]:
    """현황판 행에 한 줄로 보여줄 핵심 추출 필드 (label/value 목록)."""
    fields = []
    wage = posting.one_time_hourly_wage if posting.is_one_time_work else posting.net_hourly_wage
    if wage:
        fields.append({'label': '시급', 'value': f'{wage:.2f}만'})
    if posting.net_salary:
        fields.append({'label': '월급', 'value': f'{posting.net_salary:.0f}만'})
    if posting.city:
        fields.append({'label': '지역', 'value': posting.city})
    fields.append({'label': '근무', 'value': '일회성' if posting.is_one_time_work else '지속성'})
    if not posting.is_one_time_work and posting.hours_per_week:
        fields.append({'label': '주당', 'value': f'{posting.hours_per_week:.0f}h'})
    return fields
