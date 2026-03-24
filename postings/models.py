from django.db import models


class JobPosting(models.Model):
    # --- Identity ---
    url = models.URLField(unique=True)
    platform = models.CharField(max_length=50, blank=True)
    created_at = models.DateField(null=True, blank=True, verbose_name='공고 날짜')
    inserted_at = models.DateTimeField(auto_now_add=True)

    # --- Raw posting content ---
    title = models.TextField(blank=True)
    pharmacy_name = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    big_category = models.CharField(max_length=50, blank=True)

    # --- LLM outputs: salary ---
    is_salary_disclosed = models.BooleanField(null=True, blank=True)
    is_one_time_work = models.BooleanField(null=True, blank=True)
    one_time_hourly_wage = models.FloatField(null=True, blank=True)
    wage_type = models.CharField(max_length=50, blank=True)
    wage_raw = models.FloatField(null=True, blank=True)
    net_hourly_wage = models.FloatField(null=True, blank=True)
    net_salary = models.FloatField(null=True, blank=True)

    # --- LLM outputs: schedule ---
    weekday_work_days = models.FloatField(null=True, blank=True)
    weekday_start_time = models.FloatField(null=True, blank=True)
    weekday_end_time = models.FloatField(null=True, blank=True)
    weekend_work_days = models.FloatField(null=True, blank=True)
    weekend_start_time = models.FloatField(null=True, blank=True)
    weekend_end_time = models.FloatField(null=True, blank=True)
    hours_per_week = models.FloatField(null=True, blank=True)
    hours_per_month = models.FloatField(null=True, blank=True)

    # --- LLM outputs: benefits ---
    monthly_leave = models.CharField(max_length=10, blank=True)
    experience_required = models.TextField(blank=True)
    meal_info = models.TextField(blank=True)

    # --- LLM metadata ---
    llm_model = models.CharField(max_length=100, blank=True)
    gpt_summary = models.TextField(blank=True)
    gpt_output_log = models.TextField(blank=True)
    gpt_error_log = models.TextField(blank=True)

    # --- Quality / audit flags ---
    has_error = models.BooleanField(default=False)
    error_corrected = models.BooleanField(default=False)
    user_reviewed = models.BooleanField(default=False, verbose_name='관리자 리뷰')
    user_comment = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['big_category']),
            models.Index(fields=['platform']),
            models.Index(fields=['has_error']),
            models.Index(fields=['user_reviewed']),
        ]

    def save(self, *args, **kwargs):
        self.has_error = bool(self.gpt_error_log)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.platform}] {self.title[:40]}"


class PipelineRun(models.Model):
    STATUS_CHOICES = [
        ('running', '실행 중'),
        ('done', '완료'),
        ('failed', '실패'),
    ]

    source = models.CharField(max_length=50)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    total_scraped = models.IntegerField(default=0)
    total_processed = models.IntegerField(default=0)
    total_errors = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    log_output = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.source} | {self.started_at:%Y-%m-%d %H:%M} | {self.status}"
