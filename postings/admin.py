from django.contrib import admin
from .models import JobPosting, PipelineRun


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = (
        'title_short', 'platform', 'big_category', 'city',
        'hourly_wage', 'created_at', 'user_reviewed', 'has_error',
    )
    list_display_links = ('title_short',)
    list_filter = ('big_category', 'platform', 'has_error', 'error_corrected', 'user_reviewed', 'is_one_time_work')
    search_fields = ('title', 'pharmacy_name', 'city', 'url')
    ordering = ('-created_at',)
    list_per_page = 50

    # 리뷰 필드는 목록에서 바로 수정 가능
    list_editable = ('user_reviewed',)

    readonly_fields = ('url', 'inserted_at', 'gpt_output_log', 'gpt_error_log', 'body')

    fieldsets = (
        ('기본 정보', {
            'fields': ('url', 'platform', 'created_at', 'inserted_at', 'title', 'pharmacy_name', 'city', 'big_category'),
        }),
        ('급여', {
            'fields': ('is_salary_disclosed', 'wage_type', 'wage_raw', 'hourly_wage', 'net_salary', 'is_one_time_work', 'one_time_hourly_wage'),
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


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ('source', 'started_at', 'finished_at', 'total_scraped', 'total_processed', 'total_errors', 'status')
    list_filter = ('source', 'status')
    ordering = ('-started_at',)
    readonly_fields = ('started_at',)
