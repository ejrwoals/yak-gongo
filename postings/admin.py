import json
import threading

import django.db
from django.contrib import admin
from django.core.management import call_command
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html
from rangefilter.filters import DateRangeFilterBuilder, NumericRangeFilterBuilder

from .forms import PipelineRunForm
from .models import AdminCheck, JobPosting, PipelineRun
from .review_presets import (
    FIELD_META,
    REVIEW_PRESETS,
    get_grouped_presets,
    get_preset_queryset,
    get_sort_expression,
)

# run_id → threading.Event 매핑 (카카오 로그인 대기용)
_login_events: dict[int, threading.Event] = {}


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    change_list_template = 'admin/postings/jobposting/change_list.html'

    list_display = (
        'title_short', 'created_at', 'platform', 'city',
        'hourly_wage_display', 'net_salary_display', 'is_one_time_work_display', 'user_reviewed', 'has_error',
        'link_display',
    )
    list_display_links = ('title_short',)
    list_filter = (
        ('created_at', DateRangeFilterBuilder(title='공고 날짜')),
        'is_salary_disclosed', 'is_one_time_work', 'platform', 'big_category',
        'has_error', 'user_reviewed',
        ('net_hourly_wage', NumericRangeFilterBuilder(title='시급(세후)')),
    )
    search_fields = ('title', 'pharmacy_name', 'city', 'url')
    ordering = ('-created_at',)
    list_per_page = 50

    list_editable = ('user_reviewed',)

    readonly_fields = ('url', 'inserted_at', 'gpt_output_log', 'gpt_error_log', 'body')

    fieldsets = (
        ('기본 정보', {
            'fields': ('url', 'platform', 'created_at', 'inserted_at', 'title', 'pharmacy_name', 'city', 'big_category'),
        }),
        ('급여', {
            'fields': ('is_salary_disclosed', 'wage_type', 'wage_raw', 'net_hourly_wage', 'net_salary', 'is_one_time_work', 'one_time_hourly_wage'),
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
            'fields': ('has_error', 'user_reviewed', 'user_comment'),
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
        ]
        return custom + urls

    def review_page_view(self, request):
        """리뷰 대시보드 메인 페이지."""
        context = {
            **self.admin_site.each_context(request),
            'title': '공고 리뷰 대시보드',
            'opts': self.model._meta,
            'grouped_presets': get_grouped_presets(),
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

        # 정렬 필드 검증
        valid_sort_fields = preset['columns'] + ['inserted_at']
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
                'user_reviewed': posting.user_reviewed,
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

        posting.save()  # save()가 user_reviewed=True면 AdminCheck 자동 생성
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

        existing = set(AdminCheck.objects.filter(posting_id__in=pks).values_list('posting_id', flat=True))
        new_checks = [AdminCheck(posting_id=pk) for pk in pks if pk not in existing]
        AdminCheck.objects.bulk_create(new_checks)
        count = len(new_checks)
        return JsonResponse({'ok': True, 'count': count})

    def review_counts_view(self, request):
        """AJAX: 프리셋별 건수 반환."""
        base_qs = JobPosting.objects.all()
        counts = {}
        for key in REVIEW_PRESETS:
            counts[key] = get_preset_queryset(key, base_qs).count()
        return JsonResponse(counts)

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

    change_list_template = 'admin/postings/pipelinerun/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('run/', self.admin_site.admin_view(self.run_pipeline_view), name='pipelinerun_run'),
            path('run-statistics/', self.admin_site.admin_view(self.run_statistics_view), name='pipelinerun_run_statistics'),
            path('log/<int:run_id>/', self.admin_site.admin_view(self.run_log_view), name='pipelinerun_log'),
            path('status/<int:run_id>/', self.admin_site.admin_view(self.run_status_view), name='pipelinerun_status'),
            path('confirm-login/<int:run_id>/', self.admin_site.admin_view(self.confirm_login_view), name='pipelinerun_confirm_login'),
        ]
        return custom + urls

    def run_statistics_view(self, request):
        """백그라운드에서 run_statistics 실행 후 목록으로 복귀."""
        def _target():
            django.db.close_old_connections()
            try:
                call_command('run_statistics')
            except Exception:
                pass
            finally:
                django.db.close_old_connections()

        threading.Thread(target=_target, daemon=True).start()
        self.message_user(request, '통계 생성을 백그라운드에서 시작했습니다. 잠시 후 Notion 페이지를 확인하세요.')
        return redirect('../')

    def run_pipeline_view(self, request):
        """파이프라인 실행 폼 페이지."""
        already_running = PipelineRun.objects.filter(status='running').first()

        if request.method == 'POST':
            form = PipelineRunForm(request.POST)
            if form.is_valid():
                if already_running:
                    self.message_user(request, f'이미 실행 중인 파이프라인이 있습니다. (Run #{already_running.id})', level='warning')
                else:
                    kwargs = form.get_command_kwargs()
                    run = PipelineRun.objects.create(
                        source=kwargs['source'],
                        status='running',
                        log_output='파이프라인 시작...\n',
                    )
                    _start_pipeline_thread(run.id, kwargs)
                    return redirect(f'../log/{run.id}/')
        else:
            form = PipelineRunForm(initial={
                'source': 'yakdap',
                'start_id': 38800,
                'count': 100,
                'step': 2,
                'year': 2026,
                'big_categories': ['서울'],
                'headless': True,
            })

        context = {
            **self.admin_site.each_context(request),
            'title': '파이프라인 실행',
            'form': form,
            'already_running': already_running,
            'opts': self.model._meta,
        }
        return render(request, 'admin/postings/pipelinerun/run_pipeline.html', context)

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


@admin.register(AdminCheck)
class AdminCheckAdmin(admin.ModelAdmin):
    list_display = ('posting', 'checked_at')
    list_filter = (('checked_at', DateRangeFilterBuilder(title='검토 일시')),)
    ordering = ('-checked_at',)
    readonly_fields = ('posting', 'checked_at')

