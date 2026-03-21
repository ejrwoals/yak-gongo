"""
급여 계산 유틸리티.
원본: llm_step2_error_fallback.py (세후 공식 부분)
"""


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
