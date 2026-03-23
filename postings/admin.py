import threading

import django.db
from django.contrib import admin
from django.core.management import call_command
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import path
from django.utils import timezone

from .forms import PipelineRunForm
from .models import JobPosting, PipelineRun

# run_id → threading.Event 매핑 (카카오 로그인 대기용)
_login_events: dict[int, threading.Event] = {}


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = (
        'title_short', 'platform', 'big_category', 'city',
        'hourly_wage_display', 'created_at', 'user_reviewed', 'has_error',
    )
    list_display_links = ('title_short',)
    list_filter = ('big_category', 'platform', 'has_error', 'error_corrected', 'user_reviewed', 'is_one_time_work', 'is_salary_disclosed')
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
            'fields': ('has_error', 'error_corrected', 'user_reviewed', 'user_comment'),
        }),
        ('원문', {
            'fields': ('body',),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='공고 제목')
    def title_short(self, obj):
        return obj.title[:45] if obj.title else '-'

    @admin.display(description='NET HOURLY WAGE')
    def hourly_wage_display(self, obj):
        if obj.is_one_time_work:
            return obj.one_time_hourly_wage if obj.one_time_hourly_wage is not None else '-'
        return obj.net_hourly_wage if obj.net_hourly_wage is not None else '-'


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
            path('log/<int:run_id>/', self.admin_site.admin_view(self.run_log_view), name='pipelinerun_log'),
            path('status/<int:run_id>/', self.admin_site.admin_view(self.run_status_view), name='pipelinerun_status'),
            path('confirm-login/<int:run_id>/', self.admin_site.admin_view(self.confirm_login_view), name='pipelinerun_confirm_login'),
        ]
        return custom + urls

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
