"""Django DB → 통계 스크립트 호환 pandas DataFrame 변환.

run_statistics 명령어와 웹 대시보드 통계(dashboard_stats)가 공유한다.
"""
import pandas as pd
from django.db.models import Exists, OuterRef

from postings.models import AdminCheck, JobPosting


def build_dataframe(exclude_pending_review: bool = False) -> pd.DataFrame:
    """JobPosting 데이터를 읽어 통계 스크립트 호환 형식의 DataFrame으로 변환.

    exclude_pending_review=True 이면 아직 검토되지 않은 채 2·3단계 문제 큐
    (outlier·에러)에 걸린 공고를 집계에서 제외한다. 검토 완료(AdminCheck) 또는
    아무 큐에도 걸리지 않은 정상 공고만 남는다. 대시보드 스냅샷 생성에 사용.
    """
    qs = JobPosting.objects.all()
    if exclude_pending_review:
        from postings.review_presets import pending_review_pks
        qs = qs.exclude(pk__in=pending_review_pks(JobPosting.objects.all()))
    qs = qs.annotate(is_reviewed=Exists(
        AdminCheck.objects.filter(posting=OuterRef('pk'))
    )).values(
        'title', 'created_at', 'platform', 'url', 'pharmacy_name',
        'big_category', 'city', 'experience_required', 'monthly_leave',
        'is_salary_disclosed', 'is_reviewed', 'llm_model',
        'is_one_time_work', 'one_time_hourly_wage', 'net_hourly_wage', 'net_salary',
        'hours_per_week', 'weekday_work_days',
        'weekday_start_time', 'weekday_end_time', 'weekend_work_days',
        'weekend_start_time', 'weekend_end_time',
        'body', 'gpt_summary', 'gpt_output_log', 'user_comment',
    )
    df = pd.DataFrame(list(qs))

    df = df.rename(columns={
        'title':                '공고 제목',
        'created_at':           '등록일',
        'platform':             '플랫폼',
        'url':                  '링크',
        'pharmacy_name':        '약국 명칭',
        'big_category':         '지역 대분류',
        'city':                 '지역',
        'experience_required':  '경력 요구',
        'monthly_leave':        '월차',
        'llm_model':            'LLM model',
        'one_time_hourly_wage': '일회성 근무 시급',
        'net_hourly_wage':      '시급(엄밀히)',
        'net_salary':           '세후 월급',
        'hours_per_week':       '시간/week',
        'weekday_work_days':    '평일 근무 일수',
        'weekday_start_time':   '평일 출근 시각',
        'weekday_end_time':     '평일 퇴근 시각',
        'weekend_work_days':    '주말 근무 일수',
        'weekend_start_time':   '주말 출근 시각',
        'weekend_end_time':     '주말 퇴근 시각',
        'body':                 '본문',
        'gpt_summary':          'GPT 요약문',
        'gpt_output_log':       'GPT 2nd Run',
        'user_comment':         '내 코멘트',
    })

    # Boolean → "Yes"/"No" 문자열 변환 (통계 스크립트가 문자열로 비교함)
    for src_col, dst_col in [
        ('is_salary_disclosed', '공고에 급여 명시 여부'),
        ('is_one_time_work',    '일회성 근무 여부'),
        ('is_reviewed',         '내가 검토시 체크'),
    ]:
        df[dst_col] = df[src_col].map({True: 'Yes', False: 'No', None: None})
    df = df.drop(columns=['is_salary_disclosed', 'is_one_time_work', 'is_reviewed'])

    # 파생 컬럼
    df['주당 근무 일수'] = df['평일 근무 일수'].fillna(0) + df['주말 근무 일수'].fillna(0)

    return df
