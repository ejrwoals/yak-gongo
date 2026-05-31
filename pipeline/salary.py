"""
급여 계산 유틸리티.
원본: llm_step2_error_fallback.py (세후 공식 부분)
"""
from decimal import Decimal, ROUND_CEILING

_CENT = Decimal('0.01')


def ceil_hourly_wage(value):
    """시급을 소수점 셋째 자리에서 올림하여 둘째 자리까지의 float 로 보정.

    계산식이 시급을 구조적으로 살짝 낮게 평가하므로(예: 실제 4.0 → 3.993),
    올림으로 보정한다. 셋째 자리가 0이면 올림이 no-op 이라 값이 그대로 유지된다(예: 4.28 → 4.28).
    float 부동소수 오차로 값이 한 단계 더 튀지 않도록 Decimal(str(x)) 로 변환한다.
    세후 시급(net_hourly_wage)·일회성 시급(one_time_hourly_wage) 양쪽에 사용한다.
    """
    if value is None:
        return None
    return float(Decimal(str(value)).quantize(_CENT, rounding=ROUND_CEILING))


def calculate_net_salary(gross_monthly: float) -> float:
    """
    세전 월급(만원) → 세후 월급(만원) 변환.
    네이버 세금 계산기 샘플링 기반 2차 회귀 공식.
    y = 5.35 + 0.904394x - 0.000143950695x²
    """
    return 5.35 + 0.904394 * gross_monthly - 0.000143950695 * (gross_monthly ** 2)


def to_net_salary(wage: float, is_after_tax: bool) -> float:
    """
    세전/세후 여부에 따라 세후 월급을 반환.
    이미 세후면 그대로, 세전이면 공식으로 변환.
    """
    if is_after_tax:
        return wage
    return calculate_net_salary(wage)
