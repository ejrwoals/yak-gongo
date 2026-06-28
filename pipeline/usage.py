"""
LLM 토큰 사용량 캡처 + 기록 유틸.

세 호출 경로(pre-2 프로세싱 / auto-verify / agent)가 공통으로 쓴다:
- extract_usage()      : Gemini 응답에서 토큰 수를 뽑는다(출력 = candidates + thoughts).
- new_accumulator()    : 한 작업 단위(공고×단계) 동안 여러 호출을 합산할 dict.
- add_response()       : 응답 하나를 accumulator 에 합산(api_calls += 1).
- record_llm_usage()   : accumulator 를 LLMUsageEvent 로 영구 기록 + JobPosting 캐시 증분.

기록 규칙: status='failed'(파이프라인 예외로 중단) 는 기록하지 않는다.
공고 1건 × 단계 1개 = 이벤트 1 row(단계 내부 호출은 합산).
"""


def extract_usage(response) -> dict:
    """Gemini 응답의 usage_metadata 에서 토큰 수를 추출.

    출력 토큰은 candidates + thoughts(사고 토큰; 과금 대상)를 합산한다.
    필드가 없거나 None 이면 0 으로 본다.
    """
    meta = getattr(response, 'usage_metadata', None)
    if meta is None:
        return {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
    prompt = getattr(meta, 'prompt_token_count', 0) or 0
    candidates = getattr(meta, 'candidates_token_count', 0) or 0
    thoughts = getattr(meta, 'thoughts_token_count', 0) or 0
    total = getattr(meta, 'total_token_count', 0) or 0
    output = candidates + thoughts
    if not total:
        total = prompt + output
    return {'input_tokens': prompt, 'output_tokens': output, 'total_tokens': total}


def new_accumulator() -> dict:
    """한 작업 단위 동안 토큰/호출수를 누적할 dict."""
    return {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0, 'api_calls': 0}


def merge_usage(acc: dict | None, one: dict) -> None:
    """토큰 dict 하나를 accumulator 에 합산(api_calls += 1). acc 가 None 이면 무시."""
    if acc is None:
        return
    acc['input_tokens'] += one.get('input_tokens', 0)
    acc['output_tokens'] += one.get('output_tokens', 0)
    acc['total_tokens'] += one.get('total_tokens', 0)
    acc['api_calls'] += 1


def add_response(acc: dict | None, response) -> None:
    """Gemini 응답 하나의 usage 를 accumulator 에 합산."""
    merge_usage(acc, extract_usage(response))


def record_llm_usage(stage, model, acc, *, job_posting=None, raw_posting_id=None, status='ok'):
    """accumulator 를 LLMUsageEvent 로 기록하고 JobPosting 비용 캐시를 증분한다.

    status='failed'(예외 중단)면 아무것도 기록하지 않고 None 을 반환한다.
    반환: 생성된 LLMUsageEvent (또는 None).
    """
    if status == 'failed':
        return None
    acc = acc or new_accumulator()

    # 지연 import: Django 앱 로드 시점 순환/조기 로드 방지.
    from django.db.models import F
    from postings.models import JobPosting, LLMUsageEvent
    from pipeline.pricing import compute_cost

    cost = compute_cost(model, acc['input_tokens'], acc['output_tokens'])
    event = LLMUsageEvent.objects.create(
        stage=stage,
        model=model or '',
        job_posting=job_posting,
        raw_posting_id=raw_posting_id,
        status=status or '',
        api_calls=acc.get('api_calls', 0),
        input_tokens=acc['input_tokens'],
        output_tokens=acc['output_tokens'],
        total_tokens=acc['total_tokens'],
        cost_usd=cost,
    )
    if job_posting is not None:
        # 비정규화 누적 캐시(단계가 쌓이면 값이 커짐). 동시성 안전하게 F() 증분.
        JobPosting.objects.filter(pk=job_posting.pk).update(
            llm_cost_usd=F('llm_cost_usd') + cost,
            llm_total_tokens=F('llm_total_tokens') + acc['total_tokens'],
        )
    return event
