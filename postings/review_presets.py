"""
리뷰 대시보드 프리셋 정의.

각 프리셋은 특정 검토 시나리오에 맞는 필터, 컬럼, 편집 가능 필드를 정의한다.
"""
from collections import OrderedDict

from django.db.models import Exists, F, OuterRef, Q, Value
from django.db.models.functions import Coalesce, Floor

from .models import AdminCheck

# ── 필드 메타데이터 ──────────────────────────────────────────
# type: 'bool' → checkbox, 'float' → number input, 'char' → text input,
#       'text' → textarea (expandable only), 'date' / 'datetime' → read-only display

FIELD_META = {
    'title':              {'label': '제목',       'type': 'char'},
    'pharmacy_name':      {'label': '약국명',     'type': 'char'},
    'platform':           {'label': '플랫폼',     'type': 'char'},
    'created_at':         {'label': '공고 날짜',  'type': 'date'},
    'inserted_at':        {'label': '등록 시각',  'type': 'datetime'},
    'updated_at':         {'label': '수정 시각',  'type': 'datetime'},
    'url':                {'label': 'URL',        'type': 'char'},
    'is_salary_disclosed':{'label': '급여 명시',  'type': 'bool'},
    'is_one_time_work':   {'label': '일회성',     'type': 'bool'},
    'one_time_hourly_wage':{'label': '일회성 시급','type': 'float'},
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
    'is_reviewed':        {'label': '검토',       'type': 'bool'},  # AdminCheck(admin) 존재 여부 (읽기전용 주석)
    'user_comment':       {'label': '코멘트',     'type': 'text'},
    'gpt_error_log':      {'label': '에러 로그',  'type': 'text'},
    'body':               {'label': '원문',       'type': 'text'},
    # annotated
    'total_work_days':    {'label': '총 근무일',  'type': 'float'},
}


# ── 2단계(outlier 검토) 공통 베이스 필터 ──
_STEP3_BASE = {'has_error': False, 'admin_check__isnull': True}

# ── LLM 자동 검토 버튼을 노출할 outlier 검토 프리셋 ──
# empty_city 는 city 가 LLM 추출이 아니라 geo/mapping 변환 결과라 검산 대상에서 제외.
VERIFY_PRESET_KEYS = ['workdays_outlier', 'onetime_wage', 'salary_missing', 'pretax_check']

# ── 공통 편집 가능 필드 (확장 영역) ──
_COMMON_EXPAND_EDITABLE = [
    'weekday_work_days', 'weekend_work_days',
    'weekday_start_time', 'weekend_start_time',
    'weekday_end_time', 'weekend_end_time',
    'hours_per_week', 'hours_per_month',
    'net_hourly_wage', 'net_salary',
    'is_one_time_work', 'one_time_hourly_wage',
    'city', 'big_category',
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
                     'is_salary_disclosed', 'is_reviewed'],
        'editable': ['is_salary_disclosed'],
        'expandable': [],
        'default_sort': 'updated_at',
        'default_sort_dir': 'desc',
    }),

    # ── 2단계: outlier 검토 ──
    ('workdays_outlier', {
        'label': '근무일 이상치',
        'description': '평일 근무일이 소수점(비정수)이거나 주말 근무일이 0.5/1/2 외의 값인 공고. 음수·초과(평일>5)는 validator 에러로 분리된다. 총 근무일 기준 정렬로 탐색.',
        'group': '2단계: outlier 검토',
        'verify_focus': '특히 평일/주말 근무 일수가 본문과 정확히 일치하는지 집중 검토하세요. 출퇴근 시각도 함께 확인.',
        'columns': ['title', 'pharmacy_name', 'weekday_work_days', 'weekend_work_days',
                     'total_work_days', 'hours_per_week', 'is_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body'],
        'default_sort': 'total_work_days',
        'default_sort_dir': 'asc',
    }),

    ('onetime_wage', {
        'label': '일회성 시급 검토',
        'description': 'is_one_time_work=True이면서 시급이 null이거나 2.5~4.0 범위를 벗어난 공고.',
        'group': '2단계: outlier 검토',
        'verify_focus': '특히 일회성 시급(만원, 일당/총액이면 근무시간으로 나눠 환산)이 본문과 일치하는지, 일회성 근무 여부 판단이 맞는지 집중 검토하세요.',
        'columns': ['title', 'pharmacy_name', 'one_time_hourly_wage', 'is_one_time_work',
                     'is_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body'],
        'default_sort': 'one_time_hourly_wage',
        'default_sort_dir': 'asc',
        'nulls_first': True,
    }),

    # ── 2단계: 지속성 급여 ──
    ('salary_missing', {
        'label': '지속성 시급 검토',
        'description': 'is_one_time_work=False이면서 net_hourly_wage/net_salary가 null이거나 시급이 2.0~4.0 범위를 벗어난 공고.',
        'group': '2단계: outlier 검토',
        'verify_focus': '특히 급여 금액·급여 유형(시급/월급/연봉)·세전세후 구분이 본문과 정확히 일치하는지 집중 검토하세요.',
        'columns': ['title', 'pharmacy_name', 'net_hourly_wage', 'net_salary',
                     'is_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body'],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'asc',
    }),
    ('pretax_check', {
        'label': '세전 확인',
        'description': '본문에 "세전"이 포함된 공고. 세전→세후 환산이 제대로 적용되었는지 확인.',
        'group': '2단계: outlier 검토',
        'verify_focus': '특히 본문이 "세전" 금액을 명시했는데 세후로 잘못 처리되지 않았는지(net_salary가 원본 급여보다 적절히 작은지) 집중 검토하세요.',
        'columns': ['title', 'pharmacy_name', 'net_hourly_wage', 'net_salary',
                     'is_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body'],
        'default_sort': 'inserted_at',
        'default_sort_dir': 'asc',
    }),

    # ── 2단계: 지역 ──
    ('empty_city', {
        'label': '지역 미분류',
        'description': 'city가 빈 문자열인 공고. geo/mapping.py의 conversion_dict에 없는 주소일 가능성. 직접 입력 필요.',
        'group': '2단계: outlier 검토',
        'columns': ['title', 'pharmacy_name', 'city', 'big_category', 'platform',
                     'is_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body'],
        'default_sort': 'updated_at',
        'default_sort_dir': 'desc',
    }),

    # ── 3단계: 에러 케이스 재검토 ──
    ('error_review', {
        'label': '에러 미검토',
        'description': 'has_error=True & 미검토(AdminCheck 없음). 에러 로그를 확인하고, 값이 맞으면 확인 처리, 틀리면 수정 후 저장.',
        'group': '3단계: 에러 케이스 재검토',
        'columns': ['title', 'platform', 'created_at', 'net_hourly_wage', 'net_salary',
                     'weekday_work_days', 'weekend_work_days',
                     'is_one_time_work', 'one_time_hourly_wage',
                     'is_reviewed'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['gpt_error_log', 'body'],
        'default_sort': 'updated_at',
        'default_sort_dir': 'desc',
    }),

    # ── 최종 점검 ──
    ('final_check', {
        'label': '검토완료/코멘트 누락',
        'description': '검토 완료(AdminCheck)인데 코멘트 누락, 또는 미검토인데 코멘트가 있는 공고.',
        'group': '최종 점검',
        'columns': ['title', 'pharmacy_name', 'has_error',
                     'is_reviewed', 'user_comment'],
        'editable': _COMMON_EXPAND_EDITABLE,
        'expandable': ['body'],
        'default_sort': 'updated_at',
        'default_sort_dir': 'desc',
    }),
])

def get_preset_queryset(preset_key, base_qs):
    """프리셋 키에 해당하는 필터와 어노테이션을 적용한 queryset을 반환한다."""
    p = REVIEW_PRESETS[preset_key]
    # 모든 프리셋에 '검토 완료' 여부(AdminCheck 존재, source 무관)를 주석으로 노출한다.
    # 컬럼 표시(is_reviewed)·final_check 필터에서 공통으로 사용. 사람/LLM 자동 검토 모두 '검토 완료'로 본다.
    qs = base_qs.annotate(is_reviewed=Exists(
        AdminCheck.objects.filter(posting=OuterRef('pk'))
    ))

    if preset_key == 'salary_undisclosed':
        qs = qs.filter(is_salary_disclosed=False, admin_check__isnull=True)

    elif preset_key == 'error_review':
        qs = qs.filter(has_error=True, admin_check__isnull=True)

    elif preset_key == 'workdays_outlier':
        # 음수·초과(평일>5, 주말>2)는 validator가 에러(has_error=True)로 잡아 _STEP3_BASE에서 이미 제외된다.
        # 여기서는 에러가 아닌 '비표준 소수점' 근무일(격주 등)만 사람 검토 대상으로 띄운다.
        qs = qs.filter(**_STEP3_BASE).filter(
            Q(weekday_work_days__isnull=False) & ~Q(weekday_work_days=Floor('weekday_work_days')) |
            Q(weekend_work_days__isnull=False,
              weekend_work_days__gt=0) &
            ~Q(weekend_work_days__in=[0.5, 1, 2])
        ).annotate(
            total_work_days=(
                Coalesce(F('weekday_work_days'), Value(0.0)) +
                Coalesce(F('weekend_work_days'), Value(0.0))
            ),
        )

    elif preset_key == 'onetime_wage':
        qs = qs.filter(**_STEP3_BASE, is_one_time_work=True).filter(
            Q(one_time_hourly_wage__isnull=True) |
            Q(one_time_hourly_wage__lt=2.5) |
            Q(one_time_hourly_wage__gt=4.0)
        )

    elif preset_key == 'salary_missing':
        qs = qs.filter(**_STEP3_BASE, is_one_time_work=False).filter(
            Q(net_hourly_wage__isnull=True) | Q(net_salary__isnull=True) |
            Q(net_hourly_wage__lt=2.0) | Q(net_hourly_wage__gt=4.0)
        )

    elif preset_key == 'pretax_check':
        qs = qs.filter(**_STEP3_BASE, is_one_time_work=False, body__contains='세전')


    elif preset_key == 'empty_city':
        qs = qs.filter(**_STEP3_BASE, city='')

    elif preset_key == 'final_check':
        # 사람 검토 완료(is_reviewed)와 코멘트 유무가 어긋난 공고.
        qs = qs.filter(
            Q(is_reviewed=True, user_comment='') |
            Q(is_reviewed=False) & ~Q(user_comment='')
        )

    return qs


# ── 대시보드 집계 제외 대상: 미검토 문제 큐 ──────────────────────────
# 2단계(outlier 검토) + 3단계(에러 재검토) 그룹의 모든 큐. 이 큐들은 전부
# admin_check__isnull=True(미검토)를 조건으로 하므로, 검토 완료(AdminCheck 존재)
# 공고는 어떤 경우에도 이 집합에 들어가지 않는다.
PENDING_REVIEW_PRESET_KEYS = [
    key for key, p in REVIEW_PRESETS.items()
    if p['group'].startswith('2단계') or p['group'].startswith('3단계')
]


def pending_review_pks(base_qs):
    """미검토 상태로 2·3단계 문제 큐에 걸린 공고 PK 집합.

    각 큐 정의를 get_preset_queryset 로 그대로 재사용하므로 리뷰 대시보드의
    큐 카운트와 정확히 일치한다. 대시보드 통계에서 이 공고들을 제외하는 데 쓴다.
    """
    pks = set()
    for key in PENDING_REVIEW_PRESET_KEYS:
        pks.update(get_preset_queryset(key, base_qs).values_list('pk', flat=True))
    return pks


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
