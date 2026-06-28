"""토큰 사용량 표시용 템플릿 필터."""
from django import template

register = template.Library()


@register.filter
def kfmt(value):
    """큰 토큰 수를 k/M 으로 축약. 22896 → '22.9k', 1_200_000 → '1.2M', 940 → '940'."""
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        return value
    a = abs(n)
    if a >= 1_000_000:
        return f'{n / 1_000_000:.1f}M'
    if a >= 1_000:
        return f'{n / 1_000:.1f}k'
    return str(int(n))
