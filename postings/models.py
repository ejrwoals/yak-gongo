from django.db import models


class JobPosting(models.Model):
    # --- Identity ---
    url = models.URLField(unique=True)
    platform = models.CharField(max_length=50, blank=True)
    created_at = models.DateField(null=True, blank=True, verbose_name='공고 날짜')
    inserted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name='수정 시각')

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
    user_comment = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['big_category']),
            models.Index(fields=['platform']),
            models.Index(fields=['has_error']),
        ]

    def save(self, *args, **kwargs):
        self.has_error = bool(self.gpt_error_log)
        # hours_per_week가 없으면 근무 시간 정보로 자동 계산
        if self.hours_per_week is None:
            weekday_h = None
            weekend_h = None
            if self.weekday_start_time is not None and self.weekday_end_time is not None and self.weekday_work_days is not None:
                weekday_h = (self.weekday_end_time - self.weekday_start_time) * self.weekday_work_days
            if self.weekend_start_time is not None and self.weekend_end_time is not None and self.weekend_work_days is not None:
                weekend_h = (self.weekend_end_time - self.weekend_start_time) * self.weekend_work_days
            total = (weekday_h or 0) + (weekend_h or 0)
            if weekday_h is not None or weekend_h is not None:
                self.hours_per_week = total
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.platform}] {self.title[:40]}"


class AdminCheck(models.Model):
    """관리자가 검토 완료한 공고 기록. 레코드 존재 = 검토 완료, 없음 = 미검토."""
    SOURCE_ADMIN = 'admin'
    SOURCE_LLM = 'llm'
    SOURCE_AGENT = 'agent'
    SOURCE_CHOICES = [
        (SOURCE_ADMIN, '관리자 검토'),
        (SOURCE_LLM, 'LLM 자동 검토'),
        (SOURCE_AGENT, '대화형 agent 검토'),
    ]

    posting = models.OneToOneField(JobPosting, on_delete=models.CASCADE, related_name='admin_check')
    checked_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default=SOURCE_ADMIN,
        verbose_name='검토 주체',
    )

    def __str__(self):
        return f"checked({self.source}): {self.posting_id}"


class AgentReviewSession(models.Model):
    """대화형 agent 검토 1회의 영구 기록(트랜스크립트 + 적용된 변경 + 생성 코멘트).

    한 공고를 시점을 달리해 여러 번 검토할 수 있으므로 ForeignKey(다대일)로 둔다.
    """
    posting = models.ForeignKey(
        JobPosting, on_delete=models.CASCADE, related_name='agent_sessions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    transcript = models.JSONField(default=list)        # [{role:'user'|'model'|'tool', ...}]
    applied_changes = models.JSONField(default=list)   # [{field, old, new}] 누적
    generated_comment = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"agent_session({self.posting_id}) @ {self.created_at:%Y-%m-%d %H:%M}"


class DashboardSnapshot(models.Model):
    """웹 대시보드용 통계 스냅샷. 최신 row가 현재 노출되는 대시보드 데이터.

    admin의 '대시보드 업데이트' 버튼이 DB 전체를 집계해 한 row를 추가한다.
    created_at이 프론트의 "Last Update"로 쓰인다.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    data = models.JSONField(default=dict)            # compute_dashboard_data() 결과
    posting_count = models.IntegerField(default=0)   # 집계 대상 공고 수 (관리 목록 표시용)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"dashboard_snapshot @ {self.created_at:%Y-%m-%d %H:%M} ({self.posting_count}건)"


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
    total_errors = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    log_output = models.TextField(blank=True)

    # 어떤 파라미터로 크롤링했는지 기록 (재현·추적용).
    # yakdap 전용: start_id부터 step 간격으로 count개 순회.
    start_id = models.IntegerField(null=True, blank=True, verbose_name='시작 ID')
    count = models.IntegerField(null=True, blank=True, verbose_name='수집 개수')
    step = models.IntegerField(null=True, blank=True, verbose_name='스텝')
    # 실제로 마지막까지 수집 성공한 공고 ID(yakdap). 크래시로 중간에 멈춰도
    # 이 값 다음부터 이어서 크롤링하면 빠짐없이 진행된다.
    last_scraped_id = models.IntegerField(null=True, blank=True, verbose_name='마지막 성공 ID')
    # pharm_recruit 전용: 선택한 지역 대분류 목록(복수).
    big_categories = models.JSONField(default=list, blank=True, verbose_name='지역 대분류')

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.source} | {self.started_at:%Y-%m-%d %H:%M} | {self.status}"


class RawPosting(models.Model):
    """크롤링 결과를 LLM 처리 전에 보관하는 스테이징 레코드.

    스크래핑 단계가 공고를 한 건씩 즉시 여기에 저장하므로, 도중에 멈춰도
    이미 긁은 공고는 남는다. LLM 처리 단계는 status='pending'인 레코드만
    순회하여 JobPosting을 생성하고 status를 갱신한다. 따라서 두 단계 모두
    멱등(idempotent)하며 재실행만으로 이어서 진행된다.
    """
    STATUS_PENDING = 'pending'
    STATUS_PROCESSED = 'processed'
    STATUS_SKIPPED = 'skipped_no_salary'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = [
        (STATUS_PENDING, '처리 대기'),
        (STATUS_PROCESSED, 'JobPosting 생성 완료'),
        (STATUS_SKIPPED, '급여 미명시로 건너뜀'),
        (STATUS_ERROR, '처리 중 에러'),
    ]

    # --- Raw posting content (스크래퍼가 반환하는 dict 키와 동일) ---
    url = models.URLField(unique=True)
    platform = models.CharField(max_length=50, blank=True)
    created_at = models.DateField(null=True, blank=True, verbose_name='공고 날짜')
    title = models.TextField(blank=True)
    pharmacy_name = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    big_category = models.CharField(max_length=50, blank=True)

    # --- 처리 상태 추적 ---
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True,
    )
    error_log = models.TextField(blank=True)
    run = models.ForeignKey(
        PipelineRun, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='raw_postings', verbose_name='스크래핑 회차',
    )
    scraped_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-scraped_at']
        indexes = [
            models.Index(fields=['status']),
        ]

    def to_raw_dict(self) -> dict:
        """스크래퍼 dict와 동일한 형태로 반환 (process 단계에서 사용)."""
        return {
            'url': self.url,
            'platform': self.platform,
            'created_at': self.created_at,
            'title': self.title,
            'pharmacy_name': self.pharmacy_name,
            'body': self.body,
            'city': self.city,
            'big_category': self.big_category,
        }

    def __str__(self):
        return f"[{self.status}] {self.title[:40]}"
