"""
3단계 비에러 이상치 공고를 LLM(Gemini)으로 재검산하는 서비스.

리뷰 대시보드의 '🤖 LLM으로 자동 검토' 버튼이 호출한다. 공고당 Gemini 1회 호출로
이미 추출되어 저장된 값이 본문과 일치하는지 판정하고:
  - 일치   → AdminCheck(source='llm') 생성 (검토 완료, 3단계 집합에서 제외)
  - 불일치 → gpt_error_log 기록 → JobPosting.save() 가 has_error=True 설정 (2단계로 이동)

기존 추출 파이프라인(prompts/tasks)을 재실행하지 않고, 도메인 규칙만 압축한
단일 검산 프롬프트를 사용한다. JSON 파싱은 pipeline.tasks.extract_json 을 재사용한다.
"""
from google.genai import types

from pipeline.tasks import extract_json

from .models import AdminCheck
from .review_presets import REVIEW_PRESETS, VERIFY_PRESET_KEYS  # noqa: F401 (재노출)


VERIFY_SYSTEM_PROMPT = """당신은 약국 약사 구인 공고 데이터의 검수 전문가입니다.
이미 추출되어 DB에 저장된 값들이 공고 본문과 일치하는지 '검증'하는 것이 임무입니다.
새로 추출하지 말고, 주어진 값이 본문과 맞는지 틀린지만 판정하세요.

[도메인 규칙]
- 급여(wage_raw) 단위는 '만원'(=10000원). 예) 5,000,000원 → 500, 35,000원 → 3.5. 범위로 적혔으면 최소값 기준.
- 급여 유형(wage_type): 시급(hourly)/월급(monthly)/연봉(annual)/일급(daily). 명시 없으면 월급.
- 세전/세후: '세전'·'세전계약'이면 세전, '실수령'·'세후'면 세후. 단서가 없으면 세후로 간주.
  net_salary/net_hourly_wage 는 세전 공고라면 세금 환산이 적용된 '세후' 값이어야 하며 보통 원금(wage_raw)보다 작다.
- 일회성 근무(is_one_time_work): 특정 날짜·단기(1일~2개월)·대타면 true. 매주 반복이면 false.
- 일회성 시급(one_time_hourly_wage) 단위 '만원'. 일당/총액으로 적혔으면 근무시간으로 나눠 시급으로 환산.
- 시각은 24시간제 실수. 오전 9시=9.0, 오후 6시 30분=18.5. 명시 없으면 null.
- 평일 근무일(weekday_work_days)은 0~5. 주말 근무일(weekend_work_days)은 0/0.5/1/2 (격주 토요일=0.5).
- 본문에 정보가 없는 항목은 null 이어야 한다. 지어내면 안 된다.

[중요] net_salary/net_hourly_wage 는 다른 값에서 계산되는 파생값이다. 이 값들이 직접 틀렸다고 보지 말고,
원천 값(wage_raw, wage_type, 세전/세후, 근무일, 시각)이 본문과 다를 때 그 '원천 필드'를 지적하라.

[출력 형식] 반드시 아래 JSON 객체 '하나만' 출력. JSON 외의 다른 텍스트는 금지.
- 모든 값이 본문과 일치하면:
{"is_correct": true, "wrong_fields": [], "explanation": ""}
- 틀린 값이 있으면 (틀린 항목마다 현재값/제안값/사유 포함):
{"is_correct": false,
 "wrong_fields": [
   {"field": "<DB 필드명>", "current": <현재값>, "suggested": <옳다고 보는 값>, "reason": "<본문 근거>"}
 ],
 "explanation": "<불일치 전체 요약>"}

field 에는 반드시 아래 DB 필드명만 사용하세요:
wage_raw, wage_type, is_one_time_work, one_time_hourly_wage,
weekday_work_days, weekend_work_days, weekday_start_time, weekday_end_time,
weekend_start_time, weekend_end_time, net_salary, net_hourly_wage

reason 은 한 문장(40자 이내)으로 간결하게 쓰세요. 장황하게 설명하지 마세요.
"""

# Gemini 호출 설정: JSON 강제 + thinking 비활성화(출력 토큰 절약) + 넉넉한 출력 한도.
# 출력 한도가 작으면 wrong_fields 가 많은 공고에서 JSON 이 잘려(MAX_TOKENS) 파싱 실패한다.
_GEN_CONFIG = types.GenerateContentConfig(
    response_mime_type='application/json',
    max_output_tokens=8192,
    temperature=0.0,
    thinking_config=types.ThinkingConfig(thinking_budget=0),
)


# 검산 시 LLM 에게 보여줄 현재 추출값 필드 (필드명, 사람용 라벨)
_VALUE_FIELDS_COMMON = [
    ('is_one_time_work', '일회성 근무'),
    ('wage_raw', '원본 급여(만원)'),
    ('wage_type', '급여 유형'),
    ('net_salary', '세후 월급(만원)'),
    ('net_hourly_wage', '세후 시급(만원)'),
]
_VALUE_FIELDS_ONETIME = [
    ('one_time_hourly_wage', '일회성 시급(만원)'),
]
_VALUE_FIELDS_CONTINUOUS = [
    ('weekday_work_days', '평일 근무일'),
    ('weekend_work_days', '주말 근무일'),
    ('weekday_start_time', '평일 출근'),
    ('weekday_end_time', '평일 퇴근'),
    ('weekend_start_time', '주말 출근'),
    ('weekend_end_time', '주말 퇴근'),
]


def _current_value_lines(posting):
    fields = list(_VALUE_FIELDS_COMMON)
    fields += _VALUE_FIELDS_ONETIME if posting.is_one_time_work else _VALUE_FIELDS_CONTINUOUS
    return '\n'.join(
        f'- {name} ({label}): {getattr(posting, name, None)}'
        for name, label in fields
    )


def build_user_prompt(posting, focus):
    """본문 + 현재 추출값 + 프리셋 포커스 힌트로 user 프롬프트를 구성."""
    parts = []
    if focus:
        parts.append(f'[이번 검토 중점] {focus}\n')
    parts.append('[현재 DB에 저장된 추출값]')
    parts.append(_current_value_lines(posting))
    parts.append('\n[공고 본문]')
    parts.append(posting.body or '(본문 없음)')
    return '\n'.join(parts)


def verify_posting(posting, preset_key, client, model_name):
    """Gemini 1회 호출로 검산. verdict dict(또는 파싱 실패 시 None) 반환."""
    focus = REVIEW_PRESETS.get(preset_key, {}).get('verify_focus', '')
    prompt = VERIFY_SYSTEM_PROMPT + '\n' + build_user_prompt(posting, focus)
    response = client.models.generate_content(
        model=model_name, contents=prompt, config=_GEN_CONFIG,
    )
    text = response.text or ''
    verdict, _ = extract_json(text)
    if verdict is not None:
        return verdict

    # 파싱 실패 — 사유를 진단해 반환 (apply_verdict 가 'failed' 로 처리)
    reason = 'JSON 파싱 실패'
    try:
        fr = str(response.candidates[0].finish_reason)
        if 'MAX_TOKENS' in fr:
            reason = '응답이 너무 길어 잘림(MAX_TOKENS)'
        elif 'SAFETY' in fr:
            reason = '안전 필터 차단(SAFETY)'
        elif not text:
            reason = '빈 응답'
    except Exception:  # noqa: BLE001
        pass
    return {'_fail': reason}


def _format_log(verdict):
    """verdict 를 gpt_error_log 문자열로 조립 (사람이 2단계에서 읽고 수정용)."""
    lines = ['[LLM 검토] ' + (verdict.get('explanation') or '값이 본문과 불일치합니다.')]
    for wf in verdict.get('wrong_fields') or []:
        if not isinstance(wf, dict):
            continue
        lines.append(
            f"- {wf.get('field', '?')}: {wf.get('current')} → {wf.get('suggested')} "
            f"({wf.get('reason', '')})"
        )
    return '\n'.join(lines)


def apply_verdict(posting, verdict):
    """판정을 DB에 적용. 'ok' | 'error' | 'failed' 반환."""
    if not isinstance(verdict, dict) or 'is_correct' not in verdict:
        return 'failed'

    if verdict.get('is_correct') is True:
        AdminCheck.objects.get_or_create(
            posting=posting, defaults={'source': AdminCheck.SOURCE_LLM}
        )
        return 'ok'

    if verdict.get('is_correct') is False:
        posting.gpt_error_log = _format_log(verdict)
        posting.save()  # save() 가 gpt_error_log 를 보고 has_error=True 로 설정
        return 'error'

    return 'failed'
