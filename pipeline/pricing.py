"""
LLM 토큰 단가표 + 비용 계산.

Gemini API는 입력/출력 토큰을 따로 과금한다. 출력 토큰에는 thinking(사고) 토큰이
포함되며, usage 캡처 단계에서 output = candidates + thoughts 로 합산해 넘겨받는다.

단가는 USD/1M tokens 기준. 기본값은 코드에 두되 settings.LLM_PRICING 으로 덮어쓸 수 있다.
요금은 공급사가 변경할 수 있으므로 실제 청구액과 주기적으로 대조한다.

★ 단가표 변경의 영향 범위(스냅샷 정책):
  - 비용은 LLMUsageEvent 기록 시점에 이 표로 계산해 cost_usd 컬럼에 고정 저장된다.
  - 따라서 이 표를 바꿔도 '과거' 이벤트 비용은 소급 변경되지 않고, '이후' 새 이벤트에만 적용된다.
  - 과거를 새 단가로 재계산하려면 저장된 토큰 수로 백필하면 된다(토큰이 원본, 비용은 파생).
  자세한 정책은 postings.models.LLMUsageEvent docstring 참고.
"""
from django.conf import settings

# {model_name: (input_usd_per_1M, output_usd_per_1M)}  — paid tier, 텍스트 입력 기준.
# 출력 단가에는 thinking(사고) 토큰이 포함된다 → usage 캡처에서 output = candidates + thoughts.
# 공식 요금표(ai.google.dev/gemini-api/docs/pricing) 대조 확인: 2026-06.
# 주의: gemini-2.5-pro 는 프롬프트 200k 초과 시 더 비싸다($2.50/$15.00). 본 파이프라인은
# 공고 본문이 짧아 항상 ≤200k 구간이므로 그 단가를 쓴다. audio 입력은 더 비싸나 사용 안 함.
DEFAULT_PRICING = {
    'gemini-2.5-flash': (0.30, 2.50),
    'gemini-2.5-flash-lite': (0.10, 0.40),
    'gemini-2.5-pro': (1.25, 10.00),
    'gemini-2.0-flash': (0.10, 0.40),
}

# 미등록 모델의 폴백 단가(0이면 비용 0으로 집계됨을 방지하기 위해 flash 기준을 쓴다).
_FALLBACK = (0.30, 2.50)


def _rate(model_name: str) -> tuple[float, float]:
    """모델명에 대한 (입력, 출력) 단가(USD/1M). settings.LLM_PRICING 우선."""
    table = {**DEFAULT_PRICING, **getattr(settings, 'LLM_PRICING', {})}
    if model_name in table:
        return tuple(table[model_name])
    # 'gemini-2.5-flash-preview-..' 처럼 접미사가 붙은 변형은 prefix 매칭으로 흡수.
    for key, rate in table.items():
        if model_name and model_name.startswith(key):
            return tuple(rate)
    return _FALLBACK


def compute_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """입력/출력 토큰 수로 USD 비용 산출. 출력 토큰은 thinking 포함값을 받는다."""
    in_rate, out_rate = _rate(model_name)
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate
