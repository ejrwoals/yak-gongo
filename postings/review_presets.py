"""
리뷰 대시보드 프리셋 정의.

각 프리셋은 특정 검토 시나리오에 맞는 필터, 컬럼, 편집 가능 필드를 정의한다.
"""
from collections import OrderedDict

from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce

# ── 필드 메타데이터 ──────────────────────────────────────────
# type: 'bool' → checkbox, 'float' → number input, 'char' → text input,
#       'text' → textarea (expandable only), 'date' / 'datetime' → read-only display

FIELD_META = {
    'title':              {'label': '제목',       'type': 'char'},
    'pharmacy_name':      {'label': '약국명',     'type': 'char'},
    'platform':           {'label': '플랫폼',     'type': 'char'},
    'created_at':         {'label': '공고 날짜',  'type': 'date'},
    'inserted_at':        {'label': '등록 시각',  'type': 'datetime'},
    'url':                {'label': 'URL',        'type': 'char'},
    'is_salary_disclosed':{'label': '급여 명시',  'type': 'bool'},
    'is_one_time_work':   {'label': '일회성',     'type': 'bool'},
    'one_time_hourly_wage':{'label': '일회성 시급','type': 'float'},
    'wage_type':          {'label': '급여 유형',  'type': 'char'},
    'wage_raw':           {'label': '원본 급여',  'type': 'float'},
    'net_hourly_wage':    {'label': '세후 시급',  'type': 'float'},
    'net_salary':         {'label': '세후 월급',  'type': 'float'},
    'weekday_work_days':  {'label': '평일 근무일','type': 'float'},
    'weekend_work_days':  {'label': '주말 근무일','type': 'float'},
    'weekday_start_time': {'label': '평일 출근',  'type': 'float'},
    'weekday_end_time':   {'label': '평일 퇴근',  'type': 'float'},
    'weekend_start_time': {'label': '주말 출근',  'type': 'float'},
    'weekend_end_time':   {'label': '주말 퇴근',  'type': 'float'},
    'hours_per_week':     {'label': '주당 시간',  'type': 'float'},
    'hours_per_month':    {'label': '월 시간',    'type': 'float'},
    'city':               {'label': '지역',       'type': 'char'},
    'big_category':       {'label': '대분류',     'type': 'char'},
    'has_error':          {'label': '에러',       'type': 'bool'},
    'error_corrected':    {'label': '교정 완료',  'type': 'bool'},
    'user_reviewed':      {'label': '리뷰',       'type': 'bool'},
    'user_comment':       {'label': '코멘트',     'type': 'text'},
    'gpt_error_log':      {'label': '에러 로그',  'type': 'text'},
    'gpt_summary':        {'label': 'GPT 요약',   'type': 'text'},
    'body':               {'label': '원문',       'type': 'text'},
    # annotated
    'total_work_days':    {'label': '총 근무일',  'type': 'float'},
}


# ── 3단계 공통 베이스 필터 ──
_STEP3_BASE = {'has_error': False, 'user_reviewed': False}

# ── 공통 편집 가능 필드 (2·3단계 확장 영역) ──
_COMMON_EXPAND_EDITABLE = [
    'weekday_work_days', 'weekend_work_days',
    'weekday_start_time', 'weekday_end_time',
    'weekend_start_time', 'weekend_end_time',
    'hours_per_week', 'hours_per_month',
    'net_hourly_wage', 'net_salary',
    'wage_type', 'wage_raw',
    'is_one_time_work', 'one_time_hourly_wage',
    'city', 'big_category',
    'error_corrected', 'user_reviewed',
    'user_comment',
]

# ── 프리셋 정의 ──────────────────────────────────────────────
# columns: 테이블에 표시할 필드 (순서대로)
# editable: 편집 가능 필드 (columns에 있으면 테이블에서, 없으면 확장 영역에서 편집)
# expandable: 확장 영역에 읽기 전용으로 표시할 필드
# default_sort / default_sort_dir: 기본 정렬
# nulls_first: True이면 null 값을 먼저 표시 (기본 False)

REVIEW_PRESETS = OrderedDict([
    # ── 1단계: 사전 점검 ──
    ('salary_undisclosed', {
        'label': '급여 미공개',
        'description': 'is_salary_disclosed = False 인 공고. 이론상 파이프라인에서 걸러져야 하지만 혹시 누락된 건이 있는지 확인.',
        'group': '1단계: 사전 점검',
        'columns': ['title', 'pharmacy_name', 'platform', 'created_at', 'inserted_at',
                     'is_salary_disclosed', 'user_reviewed'],
        'editable': ['is_salary_disclosed', 'user_reviewed'],
        'expandable': [],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'asc',
    }),

    # ── 2단계: 에러 검토 ──
    ('error_review', {
        'label': '에러 미검토',
        'description': 'has_error=True & user_reviewed=False. 에러 로그를 확인하고, 값이 맞으면 확인 처리, 틀리면 수정 후 저장.',
        'group': '2단계: 에러 검토',
        'columns': ['title', 'platform', 'created_at', 'net_hourly_wage', 'net_salary',
                     'weekday_work_days', 'weekend_work_days',
                     'is_one_time_work', 'one_time_hourly_wage',
                     'error_corrected', 'user_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['gpt_error_log', 'gpt_summary', 'body'],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'asc',
    }),

    # ── 3단계: 근무일 이상치 ──
    ('workdays_outlier', {
        'label': '근무일 이상치',
        'description': '평일 근무일 <1 또는 >5, 주말 근무일이 0/0.5/1/2 외의 값인 공고. 총 근무일 기준 정렬로 이상치 탐색.',
        'group': '3단계: 비에러 이상치',
        'columns': ['title', 'pharmacy_name', 'weekday_work_days', 'weekend_work_days',
                     'total_work_days', 'hours_per_week', 'user_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body', 'gpt_summary'],
        'default_sort': 'total_work_days',
        'default_sort_dir': 'asc',
    }),

    # ── 3단계: 일회성 분류 확인 ──
    ('onetime_true', {
        'label': '일회성 분류 확인',
        'description': 'is_one_time_work=True인 공고. 제목과 비교하여 일회성이 아닌데 잘못 분류된 건이 있는지 확인.',
        'group': '3단계: 비에러 이상치',
        'columns': ['title', 'pharmacy_name', 'is_one_time_work', 'one_time_hourly_wage',
                     'user_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body', 'gpt_summary'],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'asc',
    }),
    ('onetime_false', {
        'label': '비일회성 분류 확인',
        'description': 'is_one_time_work=False인 공고. 제목과 비교하여 실제로는 단기/일회성인데 체크가 안 된 건이 있는지 확인.',
        'group': '3단계: 비에러 이상치',
        'columns': ['title', 'pharmacy_name', 'is_one_time_work', 'net_hourly_wage',
                     'user_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body', 'gpt_summary'],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'asc',
    }),
    ('onetime_wage', {
        'label': '일회성 시급 검토',
        'description': 'is_one_time_work=True인 공고를 시급 기준 정렬. 시급 누락(null) 건이 먼저 표시되고, 이상 시급 값을 탐색.',
        'group': '3단계: 비에러 이상치',
        'columns': ['title', 'pharmacy_name', 'one_time_hourly_wage', 'is_one_time_work',
                     'user_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body', 'gpt_summary'],
        'default_sort': 'one_time_hourly_wage',
        'default_sort_dir': 'asc',
        'nulls_first': True,
    }),

    # ── 3단계: 지속성 급여 ──
    ('salary_missing', {
        'label': '지속성 급여 누락',
        'description': 'is_one_time_work=False이면서 net_hourly_wage 또는 net_salary가 null인 공고. 세후 급여 계산이 누락된 건.',
        'group': '3단계: 비에러 이상치',
        'columns': ['title', 'pharmacy_name', 'net_hourly_wage', 'net_salary',
                     'wage_raw', 'wage_type', 'user_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body', 'gpt_summary'],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'asc',
    }),
    ('pretax_check', {
        'label': '세전 확인',
        'description': '본문에 "세전"이 포함된 공고. 세전→세후 환산이 제대로 적용되었는지 확인.',
        'group': '3단계: 비에러 이상치',
        'columns': ['title', 'pharmacy_name', 'net_hourly_wage', 'net_salary',
                     'wage_raw', 'user_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body', 'gpt_summary'],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'asc',
    }),
    ('salary_sort', {
        'label': '지속성 시급 정렬',
        'description': 'is_one_time_work=False인 전체 공고를 세후 시급 기준 정렬. 오름차순/내림차순으로 이상치 탐색.',
        'group': '3단계: 비에러 이상치',
        'columns': ['title', 'pharmacy_name', 'net_hourly_wage', 'net_salary',
                     'wage_type', 'hours_per_week', 'user_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body', 'gpt_summary'],
        'default_sort': 'net_hourly_wage',
        'default_sort_dir': 'asc',
    }),

    # ── 3단계: 지역 ──
    ('empty_city', {
        'label': '지역 미분류',
        'description': 'city가 빈 문자열인 공고. geo/mapping.py의 conversion_dict에 없는 주소일 가능성. 직접 입력 필요.',
        'group': '3단계: 비에러 이상치',
        'columns': ['title', 'pharmacy_name', 'city', 'big_category', 'platform',
                     'user_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body'],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'asc',
    }),

    # ── 최종 점검 ──
    ('reviewed_no_comment', {
        'label': '리뷰 완료+코멘트 누락',
        'description': 'user_reviewed=True인데 user_comment가 비어 있는 공고. 실수로 코멘트를 빠뜨린 건이 아닌지 재확인.',
        'group': '최종 점검',
        'columns': ['title', 'pharmacy_name', 'has_error', 'error_corrected',
                     'user_reviewed', 'user_comment'],
        'editable': ['user_comment'],
        'expandable': [],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'desc',
    }),
    ('unreviewed_with_comment', {
        'label': '미리뷰+코멘트 있음',
        'description': 'user_reviewed=False인데 user_comment가 있는 공고. 코멘트를 남겼으면 리뷰한 것이므로 user_reviewed=True로 변경.',
        'group': '최종 점검',
        'columns': ['title', 'pharmacy_name', 'has_error', 'user_reviewed', 'user_comment'],
        'editable': ['user_reviewed'],
        'expandable': [],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'desc',
    }),
])

def get_preset_queryset(preset_key, base_qs):
    """프리셋 키에 해당하는 필터와 어노테이션을 적용한 queryset을 반환한다."""
    p = REVIEW_PRESETS[preset_key]
    qs = base_qs

    if preset_key == 'salary_undisclosed':
        qs = qs.filter(is_salary_disclosed=False)

    elif preset_key == 'error_review':
        qs = qs.filter(has_error=True, user_reviewed=False)

    elif preset_key == 'workdays_outlier':
        qs = qs.filter(**_STEP3_BASE).filter(
            Q(weekday_work_days__lt=1) | Q(weekday_work_days__gt=5) |
            Q(weekend_work_days__isnull=False,
              weekend_work_days__gt=0) &
            ~Q(weekend_work_days__in=[0.5, 1, 2])
        ).annotate(
            total_work_days=(
                Coalesce(F('weekday_work_days'), Value(0.0)) +
                Coalesce(F('weekend_work_days'), Value(0.0))
            ),
        )

    elif preset_key == 'onetime_true':
        qs = qs.filter(**_STEP3_BASE, is_one_time_work=True)

    elif preset_key == 'onetime_false':
        qs = qs.filter(**_STEP3_BASE, is_one_time_work=False)

    elif preset_key == 'onetime_wage':
        qs = qs.filter(**_STEP3_BASE, is_one_time_work=True)

    elif preset_key == 'salary_missing':
        qs = qs.filter(**_STEP3_BASE, is_one_time_work=False).filter(
            Q(net_hourly_wage__isnull=True) | Q(net_salary__isnull=True)
        )

    elif preset_key == 'pretax_check':
        qs = qs.filter(**_STEP3_BASE, body__contains='세전')

    elif preset_key == 'salary_sort':
        qs = qs.filter(**_STEP3_BASE, is_one_time_work=False)

    elif preset_key == 'empty_city':
        qs = qs.filter(**_STEP3_BASE, city='')

    elif preset_key == 'reviewed_no_comment':
        qs = qs.filter(user_reviewed=True, user_comment='')

    elif preset_key == 'unreviewed_with_comment':
        qs = qs.filter(user_reviewed=False).exclude(user_comment='')

    return qs


def get_sort_expression(sort_field, sort_dir, preset_key):
    """정렬 필드와 방향에 맞는 Django ORM order_by 표현식을 반환한다."""
    preset = REVIEW_PRESETS[preset_key]
    nulls_first = preset.get('nulls_first', False)

    f_expr = F(sort_field)
    if sort_dir == 'desc':
        return f_expr.desc(nulls_last=True)
    if nulls_first and sort_field == preset.get('default_sort'):
        return f_expr.asc(nulls_first=True)
    return f_expr.asc(nulls_last=True)


def get_grouped_presets():
    """프리셋을 그룹별로 묶어서 반환한다. [(group_name, [(key, preset), ...]), ...]"""
    groups = OrderedDict()
    for key, preset in REVIEW_PRESETS.items():
        group = preset['group']
        if group not in groups:
            groups[group] = []
        groups[group].append((key, preset))
    return list(groups.items())
