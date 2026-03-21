"""
LLM 출력값 검증 함수 모음.
원본: llm_step1_primary_runner.py (lines 53~313)
globals() 의존성을 제거하고 순수 함수로 리팩토링.
"""
from django.conf import settings


def error_message(message: str, error_history: str) -> str:
    print(message)
    return error_history + message + '\n'


def compare_values(value_1, value_2, threshold: float = 0.1) -> bool:
    """
    두 값이 비슷한지 판단 (LLM 계산 오류 체크용).
    threshold 비율 이상 차이나면 False 반환.
    """
    if not isinstance(value_1, (int, float)) or not isinstance(value_2, (int, float)):
        return False
    return abs(value_1 - value_2) / (value_1 + 0.0001) < threshold


def error_check(d: dict, error_history: str = '') -> tuple[str, float | None, float | None]:
    """
    LLM 출력 dict를 검증하여 에러 메시지와 계산된 주당 근무 시간, 시급을 반환.

    Args:
        d: LLM 출력 dict. 다음 키를 포함해야 함:
            급여, 시급, 일회성 근무 시급, 일회성 근무 여부, 급여 유형,
            평일/주말 근무 일수, 출퇴근 시각, 주당/월 총 근무 시간
        error_history: 누적 에러 메시지 문자열

    Returns:
        (error_history, total_work_hours_per_week, hourly_wage)
    """
    Min_hourly_wage = getattr(settings, 'MIN_HOURLY_WAGE', 1.8)
    Max_hourly_wage = getattr(settings, 'MAX_HOURLY_WAGE', 5.5)
    Max_work_per_week = getattr(settings, 'MAX_WORK_HOURS_PER_WEEK', 56)
    DIFF_THRESHOLD = 0.1

    total_work_hours_per_week = None
    hourly_wage = None

    if not isinstance(d.get('급여'), (float, int)):
        if not isinstance(d.get('시급'), (float, int)):
            if not isinstance(d.get('일회성 근무 시급'), (float, int)):
                msg = '[ ERROR ] "급여", "시급", "일회성 근무 시급" 값이 모두 없습니다. 급여 명시 여부 재확인 필요.'
                error_history = error_message(msg, error_history)
                return error_history, total_work_hours_per_week, hourly_wage

    # ── 일회성 근무 ──────────────────────────────────────────
    if d.get('일회성 근무 여부'):
        one_time_wage = d.get('일회성 근무 시급')
        wage = d.get('급여')
        if not isinstance(one_time_wage, (float, int)):
            if not isinstance(wage, (float, int)):
                msg = '[ ERROR ] 일회성 근무 시급 값이 없습니다.'
                error_history = error_message(msg, error_history)
            else:
                msg = '[ ERROR ] "일회성 근무 시급"은 없고 "급여"만 있습니다. 일회성 근무라면 시급으로 환산 필요.'
                error_history = error_message(msg, error_history)
        else:
            if not (Min_hourly_wage <= one_time_wage <= Max_hourly_wage):
                msg = f'[ ERROR ] 일회성 근무 시급 {one_time_wage}만원이 정상 범위({Min_hourly_wage}~{Max_hourly_wage})를 벗어났습니다.'
                error_history = error_message(msg, error_history)
        return error_history, total_work_hours_per_week, hourly_wage

    # ── 지속성 근무 ──────────────────────────────────────────
    wage_type_list = [
        'yearly', 'annual', 'monthly', 'weekly', 'daily', 'hourly',
        'yearly wage', 'yearly salary', 'annual wage', 'annual salary',
        'monthly wage', 'weekly wage', 'daily wage', 'hourly wage',
        '연봉', '월급', '주급', '일급', '일당', '시급',
    ]
    wage_type = None
    if d.get('급여 유형') is not None:
        wage_type = str(d['급여 유형']).lower()
        if wage_type not in wage_type_list:
            msg = '[ ERROR ] 급여 유형이 올바르지 않아 monthly로 대체합니다.'
            error_history = error_message(msg, error_history)
            d['급여 유형'] = 'monthly'
            wage_type = 'monthly'

    # 근무일수 기본값 처리
    if not isinstance(d.get('평일 근무 일수'), (float, int)):
        d['평일 근무 일수'] = 0
    if not isinstance(d.get('평일 출근 시각'), (float, int)):
        d['평일 출근 시각'] = None
    if not isinstance(d.get('평일 퇴근 시각'), (float, int)):
        d['평일 퇴근 시각'] = None
    if not isinstance(d.get('주말 근무 일수'), (float, int)):
        d['주말 근무 일수'] = 0
    if not isinstance(d.get('주말 출근 시각'), (float, int)):
        d['주말 출근 시각'] = None
    if not isinstance(d.get('주말 퇴근 시각'), (float, int)):
        d['주말 퇴근 시각'] = None

    total_days = d['평일 근무 일수'] + d['주말 근무 일수']
    if total_days == 0:
        msg = '[ ERROR ] 평일/주말 근무 일수가 모두 0입니다.'
        error_history = error_message(msg, error_history)
        return error_history, total_work_hours_per_week, hourly_wage

    if d['평일 근무 일수'] > 5 or d['주말 근무 일수'] > 2:
        msg = f'[ ERROR ] 평일 근무 일수({d["평일 근무 일수"]}) 또는 주말 근무 일수({d["주말 근무 일수"]})가 범위를 초과했습니다.'
        error_history = error_message(msg, error_history)

    # 평일 근무 시간 계산
    if all([d['평일 근무 일수'], d.get('평일 출근 시각'), d.get('평일 퇴근 시각')]):
        total_weekday_work_hours = (d['평일 퇴근 시각'] - d['평일 출근 시각']) * d['평일 근무 일수']
    else:
        total_weekday_work_hours = 0

    # 주말 근무 시간 계산
    if all([d['주말 근무 일수'], d.get('주말 출근 시각'), d.get('주말 퇴근 시각')]):
        total_weekend_work_hours = (d['주말 퇴근 시각'] - d['주말 출근 시각']) * d['주말 근무 일수']
    else:
        total_weekend_work_hours = 0

    total_work_hours_per_week = total_weekday_work_hours + total_weekend_work_hours
    total_work_hours_per_month = total_work_hours_per_week * 4.34

    if total_work_hours_per_month == 0:
        if d.get('주당 총 근무 시간'):
            total_work_hours_per_week = d['주당 총 근무 시간']
            total_work_hours_per_month = d['주당 총 근무 시간'] * 4.34
        elif d.get('월 총 근무 시간'):
            total_work_hours_per_month = d['월 총 근무 시간']
            total_work_hours_per_week = d['월 총 근무 시간'] / 4.34
        else:
            msg = '[ ERROR ] 총 근무시간이 0시간입니다. 근무 요일/출퇴근 시각 재확인 필요.'
            error_history = error_message(msg, error_history)
            return error_history, total_work_hours_per_week, hourly_wage

    if total_work_hours_per_week > Max_work_per_week:
        msg = f'[ ERROR ] 주당 근무시간이 {total_work_hours_per_week}시간으로 {Max_work_per_week}시간을 초과했습니다.'
        error_history = error_message(msg, error_history)

    if total_work_hours_per_week < 0:
        msg = '[ ERROR ] 주당 근무시간이 음수입니다. 야간근무 퇴근시각 표기 확인 필요 (익일 1시 → 25로 표기).'
        error_history = error_message(msg, error_history)

    work_hours_per_day = total_work_hours_per_week / total_days

    # 시급 계산
    wage = d.get('급여')
    if isinstance(wage, (float, int)):
        if wage_type in ['monthly', 'monthly wage', '월급', None]:
            hourly_wage = wage / total_work_hours_per_month
        elif wage_type in ['weekly', 'weekly wage', '주급']:
            hourly_wage = wage / total_work_hours_per_week
        elif wage_type in ['daily', 'daily wage', '일급', '일당']:
            hourly_wage = wage / work_hours_per_day
        elif wage_type in ['hourly', 'hourly wage', '시급']:
            hourly_wage = wage
        elif wage_type in ['yearly', 'yearly wage', 'annual', 'annual wage', 'annual salary', 'yearly salary', '연봉']:
            hourly_wage = wage / 12 / total_work_hours_per_month
        else:
            hourly_wage = wage / total_work_hours_per_month
    else:
        sigan = d.get('시급')
        if isinstance(sigan, (float, int)):
            hourly_wage = sigan
        else:
            msg = '[ ERROR ] "급여"와 "시급" 값이 모두 없습니다.'
            error_history = error_message(msg, error_history)
            return error_history, total_work_hours_per_week, hourly_wage

    if hourly_wage is not None and not (Min_hourly_wage <= hourly_wage <= Max_hourly_wage):
        msg = f'[ ERROR ] 시급 {hourly_wage:.2f}만원이 정상 범위({Min_hourly_wage}~{Max_hourly_wage})를 벗어났습니다.'
        error_history = error_message(msg, error_history)

    return error_history, total_work_hours_per_week, hourly_wage
