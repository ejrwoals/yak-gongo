import json
import threading

import django.db
from django.contrib import admin
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from rangefilter.filters import DateRangeFilterBuilder, NumericRangeFilterBuilder

from .dashboard_stats import compute_dashboard_data
from .dataframe import build_dataframe
from .forms import PipelineRunForm
from .models import (
    AdminCheck,
    AgentReviewSession,
    DashboardSnapshot,
    JobPosting,
    PipelineRun,
    RawPosting,
)
from .review_presets import (
    FIELD_META,
    REVIEW_PRESETS,
    VERIFY_PRESET_KEYS,
    get_grouped_presets,
    get_preset_queryset,
    get_sort_expression,
)

# admin 홈에 '공고 리뷰 대시보드' 진입점을 추가한 커스텀 index 템플릿
admin.site.index_template = 'admin/index_with_dashboard.html'

# run_id → threading.Event 매핑 (카카오 로그인 대기용)
_login_events: dict[int, threading.Event] = {}


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    change_form_template = 'admin/postings/jobposting/change_form.html'

    list_display = (
        'title_short', 'created_at', 'platform', 'city',
        'hourly_wage_display', 'net_salary_display', 'is_one_time_work_display', 'admin_check_display', 'has_error',
        'link_display',
    )
    list_display_links = ('title_short',)
    list_filter = (
        ('created_at', DateRangeFilterBuilder(title='공고 날짜')),
        'is_salary_disclosed', 'is_one_time_work', 'platform', 'big_category',
        'has_error',
        ('net_hourly_wage', NumericRangeFilterBuilder(title='시급(세후)')),
    )
    search_fields = ('title', 'pharmacy_name', 'city', 'url')
    ordering = ('-created_at',)
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('admin_check')

    @admin.display(description='검토', boolean=True)
    def admin_check_display(self, obj):
        return hasattr(obj, 'admin_check')

    readonly_fields = ('url', 'inserted_at', 'gpt_output_log', 'gpt_error_log', 'body')

    fieldsets = (
        ('기본 정보', {
            'fields': ('url', 'platform', 'created_at', 'inserted_at', 'title', 'pharmacy_name', 'city', 'big_category'),
        }),
        ('급여', {
            'fields': ('is_salary_disclosed', 'net_hourly_wage', 'net_salary', 'is_one_time_work', 'one_time_hourly_wage'),
        }),
        ('근무 일정', {
            'fields': (
                'weekday_work_days', 'weekday_start_time', 'weekday_end_time',
                'weekend_work_days', 'weekend_start_time', 'weekend_end_time',
                'hours_per_week', 'hours_per_month',
            ),
        }),
        ('복리후생', {
            'fields': ('monthly_leave', 'experience_required', 'meal_info'),
        }),
        ('LLM 결과', {
            'fields': ('llm_model', 'gpt_summary', 'gpt_output_log', 'gpt_error_log'),
            'classes': ('collapse',),
        }),
        ('검토 / 품질', {
            'fields': ('has_error', 'user_comment'),
        }),
        ('원문', {
            'fields': ('body',),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='공고 제목')
    def title_short(self, obj):
        return obj.title[:45] if obj.title else '-'

    @admin.display(description='시급(세후)')
    def hourly_wage_display(self, obj):
        if obj.is_one_time_work:
            return obj.one_time_hourly_wage if obj.one_time_hourly_wage is not None else '-'
        return obj.net_hourly_wage if obj.net_hourly_wage is not None else '-'

    @admin.display(description='월급(세후)')
    def net_salary_display(self, obj):
        if obj.net_salary is not None:
            return f'{obj.net_salary:.2f}'
        return '-'

    @admin.display(description='일회성', boolean=True)
    def is_one_time_work_display(self, obj):
        return obj.is_one_time_work

    @admin.display(description='링크')
    def link_display(self, obj):
        if obj.url:
            return format_html('<a href="{}" target="_blank">링크</a>', obj.url)
        return '-'


    # ── 리뷰 대시보드 커스텀 뷰 ────────────────────────────────

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('review/', self.admin_site.admin_view(self.review_page_view),
                 name='jobposting_review'),
            path('review/data/', self.admin_site.admin_view(self.review_data_view),
                 name='jobposting_review_data'),
            path('review/save/', self.admin_site.admin_view(self.review_save_view),
                 name='jobposting_review_save'),
            path('review/mark-reviewed/', self.admin_site.admin_view(self.review_mark_view),
                 name='jobposting_review_mark'),
            path('review/counts/', self.admin_site.admin_view(self.review_counts_view),
                 name='jobposting_review_counts'),
            # pre-단계: 크롤링 / LLM 프로세싱
            path('review/prestage/scrape-form/', self.admin_site.admin_view(self.prestage_scrape_form_view),
                 name='jobposting_prestage_scrape_form'),
            path('review/prestage/scrape-start/', self.admin_site.admin_view(self.prestage_scrape_start_view),
                 name='jobposting_prestage_scrape_start'),
            path('review/prestage/pending/', self.admin_site.admin_view(self.prestage_pending_view),
                 name='jobposting_prestage_pending'),
            path('review/prestage/process-one/', self.admin_site.admin_view(self.prestage_process_one_view),
                 name='jobposting_prestage_process_one'),
            path('review/verify-candidates/', self.admin_site.admin_view(self.review_verify_candidates_view),
                 name='jobposting_review_verify_candidates'),
            path('review/auto-verify/', self.admin_site.admin_view(self.review_auto_verify_view),
                 name='jobposting_review_auto_verify'),
            path('review/agent-context/', self.admin_site.admin_view(self.review_agent_context_view),
                 name='jobposting_review_agent_context'),
            path('review/agent-chat/', self.admin_site.admin_view(self.review_agent_chat_view),
                 name='jobposting_review_agent_chat'),
            path('review/agent-tool/', self.admin_site.admin_view(self.review_agent_tool_view),
                 name='jobposting_review_agent_tool'),
            path('review/agent-finish/', self.admin_site.admin_view(self.review_agent_finish_view),
                 name='jobposting_review_agent_finish'),
        ]
        return custom + urls

    def review_page_view(self, request):
        """리뷰 대시보드 메인 페이지."""
        context = {
            **self.admin_site.each_context(request),
            'title': '공고 리뷰 대시보드',
            'opts': self.model._meta,
            'grouped_presets': get_grouped_presets(),
            'verify_preset_keys_json': json.dumps(VERIFY_PRESET_KEYS),
            'presets_json': json.dumps({
                key: {
                    'label': p['label'],
                    'description': p.get('description', ''),
                    'columns': p['columns'],
                    'default_sort': p['default_sort'],
                    'default_sort_dir': p['default_sort_dir'],
                }
                for key, p in REVIEW_PRESETS.items()
            }),
        }
        return render(request, 'admin/postings/jobposting/review_dashboard.html', context)

    def review_data_view(self, request):
        """AJAX: 프리셋에 맞는 테이블 HTML fragment 반환."""
        preset_key = request.GET.get('preset', '')
        if preset_key not in REVIEW_PRESETS:
            return JsonResponse({'error': 'invalid preset'}, status=400)

        preset = REVIEW_PRESETS[preset_key]
        sort_field = request.GET.get('sort', preset['default_sort'])
        sort_dir = request.GET.get('sort_dir', preset['default_sort_dir'])
        page_num = request.GET.get('page', '1')

        # 정렬 필드 검증 (모든 프리셋에서 등록/수정 시각으로도 정렬 가능)
        valid_sort_fields = preset['columns'] + ['inserted_at', 'updated_at']
        if sort_field not in valid_sort_fields:
            sort_field = preset['default_sort']
        if sort_dir not in ('asc', 'desc'):
            sort_dir = 'asc'

        qs = get_preset_queryset(preset_key, JobPosting.objects.all())
        sort_expr = get_sort_expression(sort_field, sort_dir, preset_key)
        qs = qs.order_by(sort_expr)

        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(page_num)

        # 컬럼 메타 빌드
        columns_meta = []
        for field_name in preset['columns']:
            meta = FIELD_META.get(field_name, {'label': field_name, 'type': 'char'})
            columns_meta.append({
                'field': field_name,
                'label': meta['label'],
                'type': meta['type'],
                'editable': field_name in preset.get('editable', []),
            })

        # 확장 영역의 편집 가능 필드 (columns에 없는 editable 필드)
        expand_editable = [
            f for f in preset.get('editable', [])
            if f not in preset['columns']
        ]

        # 행 데이터 빌드
        rows = []
        for posting in page_obj:
            cells = []
            for col in columns_meta:
                value = getattr(posting, col['field'], None)
                display = self._format_display(value, col['type'], col['field'])
                cells.append({
                    'field': col['field'],
                    'type': col['type'],
                    'value': value,
                    'display': display,
                    'editable': col['editable'],
                })

            # 확장 영역 데이터
            expandable_readonly = {}
            for field in preset.get('expandable', []):
                expandable_readonly[field] = {
                    'label': FIELD_META.get(field, {}).get('label', field),
                    'value': getattr(posting, field, '') or '',
                }
            expandable_edit = {}
            for field in expand_editable:
                meta = FIELD_META.get(field, {'label': field, 'type': 'char'})
                expandable_edit[field] = {
                    'label': meta['label'],
                    'type': meta['type'],
                    'value': getattr(posting, field, None),
                }

            rows.append({
                'pk': posting.pk,
                'cells': cells,
                'expandable_readonly': expandable_readonly,
                'expandable_edit': expandable_edit,
                'reviewed': posting.is_reviewed,
                'url': posting.url,
            })

        has_expandable = bool(preset.get('expandable') or expand_editable)
        total_cols = len(columns_meta) + 2 + (1 if has_expandable else 0)  # checkbox + actions + expand

        context = {
            'rows': rows,
            'columns_meta': columns_meta,
            'page_obj': page_obj,
            'has_expandable': has_expandable,
            'total_cols': total_cols,
            'preset_key': preset_key,
        }
        return render(request, 'admin/postings/jobposting/review_table_fragment.html', context)

    def review_save_view(self, request):
        """AJAX POST: 단건 저장."""
        if request.method != 'POST':
            return JsonResponse({'ok': False, 'error': 'POST only'}, status=405)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid JSON'}, status=400)

        pk = data.get('pk')
        fields = data.get('fields', {})
        preset_key = data.get('preset', '')

        if not pk or not fields:
            return JsonResponse({'ok': False, 'error': 'pk and fields required'}, status=400)

        # 프리셋의 editable 목록으로 허용 필드 검증
        allowed = set()
        if preset_key in REVIEW_PRESETS:
            allowed = set(REVIEW_PRESETS[preset_key].get('editable', []))

        try:
            posting = JobPosting.objects.get(pk=pk)
        except JobPosting.DoesNotExist:
            return JsonResponse({'ok': False, 'error': 'not found'}, status=404)

        for field_name, value in fields.items():
            if allowed and field_name not in allowed:
                continue
            meta = FIELD_META.get(field_name)
            if not meta:
                continue
            converted = self._convert_value(value, meta['type'])
            setattr(posting, field_name, converted)

        posting.save()  # 검토 완료 표시는 mark-reviewed(AdminCheck) 경로에서 별도 처리
        return JsonResponse({'ok': True})

    def review_mark_view(self, request):
        """AJAX POST: 벌크 리뷰 완료 처리."""
        if request.method != 'POST':
            return JsonResponse({'ok': False, 'error': 'POST only'}, status=405)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid JSON'}, status=400)

        pks = data.get('pks', [])
        if not pks:
            return JsonResponse({'ok': False, 'error': 'pks required'}, status=400)

        existing_qs = AdminCheck.objects.filter(posting_id__in=pks)
        existing_ids = set(existing_qs.values_list('posting_id', flat=True))
        new_checks = [AdminCheck(posting_id=pk, source=AdminCheck.SOURCE_ADMIN)
                      for pk in pks if pk not in existing_ids]
        AdminCheck.objects.bulk_create(new_checks)
        # 사람이 직접 검토 → 기존 LLM 자동 검토 건은 'admin' 으로 승격
        upgraded = existing_qs.filter(source=AdminCheck.SOURCE_LLM).update(source=AdminCheck.SOURCE_ADMIN)
        return JsonResponse({'ok': True, 'count': len(new_checks), 'upgraded': upgraded})

    def review_counts_view(self, request):
        """AJAX: 프리셋별 건수 + pre-단계 대기 건수 반환."""
        base_qs = JobPosting.objects.all()
        counts = {}
        for key in REVIEW_PRESETS:
            counts[key] = get_preset_queryset(key, base_qs).count()
        # pre-2단계: LLM 처리 대기(RawPosting status=pending) 건수
        counts['pending_raw'] = RawPosting.objects.filter(
            status=RawPosting.STATUS_PENDING
        ).count()
        return JsonResponse(counts)

    # ── pre-단계: 크롤링 / LLM 프로세싱 ──────────────────────────
    def prestage_scrape_form_view(self, request):
        """AJAX GET: pre-1단계 크롤링 실행 폼 fragment."""
        already_running = PipelineRun.objects.filter(status='running').first()
        form = PipelineRunForm(initial={
            'source': 'yakdap',
            'start_id': 38800, 'count': 100, 'step': 2, 'year': 2026,
            'big_categories': ['서울'], 'headless': True,
        })
        ctx = {'form': form, 'already_running': already_running}
        if already_running:
            ctx['running_status_url'] = reverse('admin:pipelinerun_status', args=[already_running.id])
            ctx['running_confirm_url'] = reverse('admin:pipelinerun_confirm_login', args=[already_running.id])
        return render(request, 'admin/postings/jobposting/prestage_scrape_form.html', ctx)

    def prestage_scrape_start_view(self, request):
        """AJAX POST: 크롤링(스크래핑)만 백그라운드 실행. RawPosting까지만 저장."""
        if request.method != 'POST':
            return JsonResponse({'ok': False, 'error': 'POST only'}, status=405)
        already_running = PipelineRun.objects.filter(status='running').first()
        if already_running:
            return JsonResponse({
                'ok': False, 'error': f'이미 실행 중인 작업이 있습니다 (Run #{already_running.id})',
                'log_url': reverse('admin:pipelinerun_log', args=[already_running.id]),
                'status_url': reverse('admin:pipelinerun_status', args=[already_running.id]),
                'confirm_url': reverse('admin:pipelinerun_confirm_login', args=[already_running.id]),
            }, status=409)
        form = PipelineRunForm(request.POST)
        if not form.is_valid():
            return JsonResponse({'ok': False, 'error': '입력값 오류', 'detail': form.errors}, status=400)

        kwargs = form.get_command_kwargs()
        kwargs['dry_run'] = True  # 크롤링만: RawPosting까지만 저장하고 LLM은 pre-2단계에서
        run = PipelineRun.objects.create(
            source=kwargs['source'], status='running', log_output='크롤링 시작...\n',
        )
        _start_pipeline_thread(run.id, kwargs)
        return JsonResponse({
            'ok': True, 'run_id': run.id,
            'log_url': reverse('admin:pipelinerun_log', args=[run.id]),
            'status_url': reverse('admin:pipelinerun_status', args=[run.id]),
            'confirm_url': reverse('admin:pipelinerun_confirm_login', args=[run.id]),
        })

    PENDING_SORT_FIELDS = [
        ('scraped_at', '수집 시각'),
        ('title', '제목'),
        ('pharmacy_name', '약국'),
        ('platform', '플랫폼'),
        ('city', '지역'),
    ]

    def prestage_pending_view(self, request):
        """AJAX GET: pre-2단계 — LLM 처리 대기(RawPosting pending) 목록 fragment."""
        MAX_ROWS = 500
        valid = {f for f, _ in self.PENDING_SORT_FIELDS}
        sort = request.GET.get('sort', 'scraped_at')
        if sort not in valid:
            sort = 'scraped_at'
        sort_dir = request.GET.get('sort_dir', 'asc')
        if sort_dir not in ('asc', 'desc'):
            sort_dir = 'asc'
        order = ('-' if sort_dir == 'desc' else '') + sort

        qs = RawPosting.objects.filter(status=RawPosting.STATUS_PENDING).order_by(order, 'id')
        total = qs.count()
        rows = list(qs[:MAX_ROWS])
        sort_options = [
            {'value': f, 'label': label, 'selected': f == sort}
            for f, label in self.PENDING_SORT_FIELDS
        ]
        return render(request, 'admin/postings/jobposting/prestage_pending.html', {
            'rows': rows,
            'total': total,
            'truncated': total > MAX_ROWS,
            'max_rows': MAX_ROWS,
            'sort_options': sort_options,
            'sort_dir': sort_dir,
        })

    def prestage_process_one_view(self, request):
        """AJAX POST: pending RawPosting 한 건을 LLM 처리하여 JobPosting 생성.

        진행 모달이 항목을 하나씩 호출한다. 결과 dict(status/title/note)를 반환.
        """
        if request.method != 'POST':
            return JsonResponse({'ok': False, 'error': 'POST only'}, status=405)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid JSON'}, status=400)

        raw_id = data.get('id')
        if not raw_id:
            return JsonResponse({'ok': False, 'error': 'id required'}, status=400)

        raw = RawPosting.objects.filter(id=raw_id).first()
        if raw is None:
            return JsonResponse({'ok': True, 'result': {
                'id': raw_id, 'status': 'skipped', 'note': '대상 없음', 'title': '',
            }})
        if raw.status != RawPosting.STATUS_PENDING:
            return JsonResponse({'ok': True, 'result': {
                'id': raw_id, 'status': 'skipped', 'note': '이미 처리됨', 'title': raw.title,
            }})

        from django.conf import settings
        from google import genai
        from pipeline.stages import process_raw_posting

        if not settings.GOOGLE_API_KEY:
            return JsonResponse({'ok': False, 'error': 'GOOGLE_API_KEY 미설정'}, status=500)

        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        result = process_raw_posting(raw, client, settings.LLM_MODEL, log=lambda m: None)
        return JsonResponse({'ok': True, 'result': result})

    def review_verify_candidates_view(self, request):
        """AJAX GET: 현재 프리셋의 LLM 자동 검토 대상 공고 id 목록 반환."""
        preset_key = request.GET.get('preset', '')
        if preset_key not in VERIFY_PRESET_KEYS:
            return JsonResponse({'error': 'invalid preset'}, status=400)
        items = [
            {'id': r['id'], 'title': (r['title'] or '').strip()[:60]}
            for r in get_preset_queryset(preset_key, JobPosting.objects.all()).values('id', 'title')
        ]
        return JsonResponse({'items': items, 'total': len(items)})

    def review_auto_verify_view(self, request):
        """AJAX POST: 주어진 공고 id 배치를 LLM(Gemini)으로 검산.

        맞으면 AdminCheck(source='llm') 생성, 틀리면 gpt_error_log 기록(→ has_error=True).
        """
        if request.method != 'POST':
            return JsonResponse({'ok': False, 'error': 'POST only'}, status=405)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'invalid JSON'}, status=400)

        preset_key = data.get('preset', '')
        ids = data.get('ids', [])
        if preset_key not in VERIFY_PRESET_KEYS:
            return JsonResponse({'ok': False, 'error': 'invalid preset'}, status=400)
        if not ids:
            return JsonResponse({'ok': False, 'error': 'ids required'}, status=400)

        # 지연 import: Django 로드 시 google-genai 까지 끌어오지 않도록
        from django.conf import settings
        from google import genai
        from .review_verify import apply_verdict, verify_posting

        if not settings.GOOGLE_API_KEY:
            return JsonResponse({'ok': False, 'error': 'GOOGLE_API_KEY 미설정'}, status=500)

        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        model_name = settings.LLM_MODEL

        results = []
        counts = {'ok': 0, 'error': 0, 'failed': 0, 'skipped': 0}
        for pk in ids:
            posting = JobPosting.objects.filter(pk=pk).select_related('admin_check').first()
            if posting is None:
                results.append({'id': pk, 'status': 'failed', 'title': '', 'note': '공고 없음'})
                counts['failed'] += 1
                continue
            title = (posting.title or '').strip()[:50]
            # 이미 처리된 건(에러 표시됨 or 검토 완료)은 건너뜀
            if posting.has_error or AdminCheck.objects.filter(posting_id=pk).exists():
                results.append({'id': pk, 'status': 'skipped', 'title': title, 'note': '이미 처리됨'})
                counts['skipped'] += 1
                continue
            note = ''
            try:
                verdict = verify_posting(posting, preset_key, client, model_name)
                status = apply_verdict(posting, verdict)
                if status == 'error':
                    # gpt_error_log 첫 줄(요약)을 진행 로그용 사유로
                    note = (posting.gpt_error_log or '').strip().split('\n', 1)[0][:120]
                elif status == 'failed':
                    note = verdict.get('_fail', 'LLM 응답 파싱 실패') if isinstance(verdict, dict) else 'LLM 응답 없음'
            except Exception as e:  # noqa: BLE001 - 한 건 실패가 배치 전체를 막지 않도록
                status = 'failed'
                note = str(e)[:120]
                print(f'[auto-verify ERROR] pk={pk}: {e}')
            results.append({'id': pk, 'status': status, 'title': title, 'note': note})
            if status in counts:
                counts[status] += 1

        # 주의: counts 를 최상위로 펼치면 'ok' 키가 성공 플래그와 충돌하므로 'counts' 로 감싼다.
        return JsonResponse({'ok': True, 'results': results, 'counts': counts})

    # ── 대화형 agent 검토 (3단계 에러 케이스) ──────────────────

    def review_agent_context_view(self, request):
        """AJAX GET ?id=: 모달 좌측 정보 패널용 케이스 컨텍스트."""
        from .review_agent import field_snapshot
        pk = request.GET.get('id')
        posting = JobPosting.objects.filter(pk=pk).first()
        if posting is None:
            return JsonResponse({'error': 'not found'}, status=404)
        return JsonResponse({
            'id': posting.pk,
            'title': (posting.title or '').strip(),
            'fields': field_snapshot(posting),
            'gpt_error_log': posting.gpt_error_log or '',
            'body': posting.body or '',
            'is_reviewed': AdminCheck.objects.filter(posting_id=pk).exists(),
            'url': posting.url,
        })

    def _agent_prepare(self, request):
        """POST 검증 + posting 로드 + Gemini 클라이언트 준비. (ok, payload | JsonResponse)."""
        if request.method != 'POST':
            return False, JsonResponse({'ok': False, 'error': 'POST only'}, status=405)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return False, JsonResponse({'ok': False, 'error': 'invalid JSON'}, status=400)
        posting = JobPosting.objects.filter(pk=data.get('id')).first()
        if posting is None:
            return False, JsonResponse({'ok': False, 'error': 'not found'}, status=404)

        from django.conf import settings
        if not settings.GOOGLE_API_KEY:
            return False, JsonResponse({'ok': False, 'error': 'GOOGLE_API_KEY 미설정'}, status=500)
        from google import genai
        client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        return True, (posting, client, settings.LLM_MODEL, data)

    def review_agent_chat_view(self, request):
        """AJAX POST {id, messages}: 한 턴 진행(제안만, DB 미변경)."""
        ok, payload = self._agent_prepare(request)
        if not ok:
            return payload
        posting, client, model_name, data = payload
        from .review_agent import field_snapshot, propose_turn
        try:
            result = propose_turn(posting, data.get('messages') or [], client, model_name)
        except Exception as e:  # noqa: BLE001
            print(f'[agent-chat ERROR] pk={posting.pk}: {e}')
            return JsonResponse({'ok': False, 'error': str(e)[:200]}, status=500)
        result['ok'] = True
        result['fields'] = field_snapshot(posting)
        return JsonResponse(result)

    def review_agent_tool_view(self, request):
        """AJAX POST {id, messages, tool_call, decision, note}: 권한 박스 결정 처리.

        이 엔드포인트만 DB를 변경한다(approved 인 경우에만).
        """
        ok, payload = self._agent_prepare(request)
        if not ok:
            return payload
        posting, client, model_name, data = payload
        decision = data.get('decision')
        if decision not in ('approved', 'rejected'):
            return JsonResponse({'ok': False, 'error': 'invalid decision'}, status=400)
        from .review_agent import apply_turn, field_snapshot
        try:
            result = apply_turn(
                posting, data.get('messages') or [], data.get('tool_call') or {},
                decision, client, model_name, note=data.get('note') or '',
            )
        except Exception as e:  # noqa: BLE001
            print(f'[agent-tool ERROR] pk={posting.pk}: {e}')
            return JsonResponse({'ok': False, 'error': str(e)[:200]}, status=500)
        posting.refresh_from_db()
        result['ok'] = True
        result['fields'] = field_snapshot(posting)
        return JsonResponse(result)

    def review_agent_finish_view(self, request):
        """AJAX POST {id, messages}: 검토 완료 — 코멘트 생성 + AdminCheck + 세션 영구 저장.

        gpt_error_log 는 보존하므로 has_error 는 유지된다(결정 1). AdminCheck 생성만으로
        error_review 큐(admin_check__isnull=True)에서 빠진다.
        """
        ok, payload = self._agent_prepare(request)
        if not ok:
            return payload
        posting, client, model_name, data = payload
        messages = data.get('messages') or []
        from .review_agent import collect_applied_changes, generate_comment
        try:
            comment = generate_comment(posting, messages, client, model_name)
        except Exception as e:  # noqa: BLE001
            print(f'[agent-finish ERROR] pk={posting.pk}: {e}')
            comment = '[대화형 검토] 검토 완료.'
        posting.user_comment = comment
        posting.save()
        AdminCheck.objects.get_or_create(
            posting=posting, defaults={'source': AdminCheck.SOURCE_AGENT},
        )
        AgentReviewSession.objects.create(
            posting=posting,
            transcript=messages,
            applied_changes=collect_applied_changes(messages),
            generated_comment=comment,
        )
        return JsonResponse({'ok': True, 'comment': comment})

    @staticmethod
    def _format_display(value, field_type, field_name=''):
        """셀 표시 값 포맷팅."""
        if value is None:
            return '-'
        if field_type == 'bool':
            return 'Y' if value else 'N'
        if field_type == 'float':
            if isinstance(value, float):
                return f'{value:.2f}' if value % 1 else str(int(value))
            return str(value)
        if field_type == 'date':
            return value.strftime('%m/%d') if hasattr(value, 'strftime') else str(value)
        if field_type == 'datetime':
            return value.strftime('%m/%d %H:%M') if hasattr(value, 'strftime') else str(value)
        if field_type == 'char' and field_name == 'title':
            return str(value)[:40] if value else '-'
        return str(value) if value else ''

    @staticmethod
    def _convert_value(value, field_type):
        """클라이언트에서 받은 값을 모델 필드 타입에 맞게 변환."""
        if field_type == 'bool':
            if isinstance(value, bool):
                return value
            return str(value).lower() in ('true', '1', 'on', 'yes')
        if field_type == 'float':
            if value is None or value == '' or value == 'null':
                return None
            return float(value)
        if field_type in ('char', 'text'):
            return str(value) if value is not None else ''
        return value


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ('source', 'started_at', 'finished_at', 'total_scraped', 'total_processed', 'total_errors', 'status')
    list_filter = ('source', 'status')
    ordering = ('-started_at',)
    readonly_fields = ('started_at',)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('log/<int:run_id>/', self.admin_site.admin_view(self.run_log_view), name='pipelinerun_log'),
            path('status/<int:run_id>/', self.admin_site.admin_view(self.run_status_view), name='pipelinerun_status'),
            path('confirm-login/<int:run_id>/', self.admin_site.admin_view(self.confirm_login_view), name='pipelinerun_confirm_login'),
        ]
        return custom + urls

    def run_log_view(self, request, run_id):
        """실행 로그 확인 페이지."""
        try:
            run = PipelineRun.objects.get(id=run_id)
        except PipelineRun.DoesNotExist:
            return redirect('../')
        context = {
            **self.admin_site.each_context(request),
            'title': f'파이프라인 로그 #{run_id}',
            'run': run,
            'opts': self.model._meta,
        }
        return render(request, 'admin/postings/pipelinerun/run_log.html', context)

    def run_status_view(self, request, run_id):
        """AJAX: 현재 실행 상태 + 로그 반환."""
        try:
            run = PipelineRun.objects.get(id=run_id)
        except PipelineRun.DoesNotExist:
            return JsonResponse({'error': 'not found'}, status=404)
        return JsonResponse({
            'status': run.status,
            'log_output': run.log_output,
            'total_scraped': run.total_scraped,
            'total_processed': run.total_processed,
            'total_errors': run.total_errors,
            'started_at': run.started_at.strftime('%Y-%m-%d %H:%M:%S') if run.started_at else None,
            'finished_at': run.finished_at.strftime('%Y-%m-%d %H:%M:%S') if run.finished_at else None,
            'waiting_login': run_id in _login_events and not _login_events[run_id].is_set(),
        })

    def confirm_login_view(self, request, run_id):
        """AJAX: 카카오 로그인 완료 신호를 보낸다."""
        event = _login_events.get(run_id)
        if event and not event.is_set():
            event.set()
            return JsonResponse({'ok': True})
        return JsonResponse({'ok': False, 'message': '대기 중인 로그인이 없습니다.'})


def _start_pipeline_thread(run_id: int, kwargs: dict):
    """백그라운드 thread에서 run_pipeline management command를 실행한다."""
    # yakdap인 경우 카카오 로그인 대기용 이벤트 생성
    if kwargs.get('source') == 'yakdap':
        event = threading.Event()
        _login_events[run_id] = event
    else:
        event = None

    def _target():
        django.db.close_old_connections()
        try:
            import io
            from postings.management.commands.run_pipeline import Command as RunPipelineCommand
            cmd = RunPipelineCommand(stdout=io.StringIO())
            cmd_kwargs = dict(kwargs)
            cmd_kwargs['run_id'] = run_id
            cmd_kwargs['login_event'] = event
            cmd.handle(**cmd_kwargs)
        except Exception as e:
            try:
                run = PipelineRun.objects.get(id=run_id)
                run.status = 'failed'
                run.finished_at = timezone.now()
                run.log_output += f'\n[FATAL ERROR] {e}\n'
                run.save()
            except Exception:
                pass
        finally:
            _login_events.pop(run_id, None)
            django.db.close_old_connections()

    t = threading.Thread(target=_target, daemon=True)
    t.start()


@admin.register(RawPosting)
class RawPostingAdmin(admin.ModelAdmin):
    list_display = ('title', 'platform', 'status', 'city', 'scraped_at', 'processed_at')
    list_filter = ('status', 'platform', 'big_category')
    search_fields = ('url', 'title', 'pharmacy_name')
    ordering = ('-scraped_at',)
    readonly_fields = ('scraped_at', 'processed_at')


@admin.register(AdminCheck)
class AdminCheckAdmin(admin.ModelAdmin):
    list_display = ('posting', 'source', 'checked_at')
    list_filter = ('source', ('checked_at', DateRangeFilterBuilder(title='검토 일시')),)
    ordering = ('-checked_at',)
    readonly_fields = ('posting', 'checked_at')


@admin.register(AgentReviewSession)
class AgentReviewSessionAdmin(admin.ModelAdmin):
    list_display = ('posting', 'created_at', 'generated_comment')
    list_filter = (('created_at', DateRangeFilterBuilder(title='검토 일시')),)
    ordering = ('-created_at',)
    readonly_fields = ('posting', 'created_at', 'transcript', 'applied_changes', 'generated_comment')


@admin.register(DashboardSnapshot)
class DashboardSnapshotAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'posting_count')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'posting_count', 'data')

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('update/', self.admin_site.admin_view(self.update_view),
                 name='dashboardsnapshot_update'),
        ]
        return custom + urls

    def update_view(self, request):
        """현재 DB 전체를 집계해 새 대시보드 스냅샷을 저장한다."""
        try:
            df = build_dataframe()
            data = compute_dashboard_data(df)
            DashboardSnapshot.objects.create(data=data, posting_count=int(len(df)))
            self.message_user(
                request,
                f'대시보드를 최신 데이터로 업데이트했습니다. (공고 {len(df)}건 집계)',
            )
        except Exception as e:
            self.message_user(request, f'대시보드 업데이트 실패: {e}', level='error')
        return redirect('../')

