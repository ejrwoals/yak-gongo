"""
2단계 outlier 검토 공고를 LLM(Gemini)으로 재검산하는 서비스.

리뷰 대시보드의 '🤖 LLM으로 자동 검토' 버튼이 호출한다. 공고당 Gemini 1회 호출로
이미 추출되어 저장된 값이 본문과 일치하는지 판정하고:
  - 일치   → AdminCheck(source='llm') 생성 (검토 완료, 2단계 집합에서 제외)
  - 불일치 → gpt_error_log 기록 → JobPosting.save() 가 has_error=True 설정 (3단계 에러 케이스 재검토로 이동)

기존 추출 파이프라인(prompts/tasks)을 재실행하지 않고, 도메인 규칙만 압축한
단일 검산 프롬프트를 사용한다. JSON 파싱은 pipeline.tasks.extract_json 을 재사용한다.
"""
from google.genai import types

from pipeline.tasks import extract_json

from .models import AdminCheck
from .review_presets import REVIEW_PRESETS, VERIFY_PRESET_KEYS  # noqa: F401 (재노출)


# 약국 구인공고 도메인 지식. 검산(verify)과 대화형 수정(agent)이 같은 기준을 쓰도록 공유 상수로 둔다.
DOMAIN_RULES = """[도메인 규칙]
- 세전/세후: '세전'·'세전계약'이면 세전, '실수령'·'세후'면 세후. 단서가 없으면 세후로 간주.
  net_salary/net_hourly_wage 는 세전 공고라면 세금 환산이 적용된 '세후' 값이어야 하며 보통 원금보다 작다.
- 일회성 근무(is_one_time_work): 일회성/지속성을 가르는 기준은 '반복 여부'이지 빈도가 아니다.
  한 번으로 끝나면(특정 날짜·단기 1일~2개월·대타) true, 정기적으로 반복되면 빈도가 아무리 낮아도 false.
- 일회성 시급(one_time_hourly_wage) 단위 '만원'. 일당/총액으로 적혔으면 근무시간으로 나눠 시급으로 환산.
- ★ 근무 형태별로 채워지는 급여·일정 필드가 정해져 있다(파이프라인 동작). 각 형태에서 '해당하는 필드만' 검토 대상으로 본다:
  · 일회성 근무(is_one_time_work=True): 급여는 one_time_hourly_wage 한 필드로 표현한다.
    이때 net_hourly_wage·net_salary·평일/주말 근무일·출퇴근 시각은 '지속성 근무 전용' 필드라 null 인 상태가 정상값이다.
    → 일회성 공고는 일회성 판단과 one_time_hourly_wage 만 본문과 대조한다.
  · 지속성 근무(is_one_time_work=False): 급여는 net_hourly_wage·net_salary 로, 일정은 평일/주말 근무일·출퇴근 시각으로 표현한다.
    이때 one_time_hourly_wage 는 null 인 상태가 정상값이다.
    → 지속성 공고는 이 급여·일정 필드들을 본문과 대조한다.
- 시각은 24시간제 실수. 오전 9시=9.0, 오후 6시 30분=18.5. 명시 없으면 null.
- 근무일수(평일 weekday_work_days 0~5, 주말 weekend_work_days 0~2)는 각 요일을 '실제로 근무하는 주의 비율'로
  환산해 합산한 '주당 평균'이다. 매주=1, 격주=0.5, 월1회=0.25, 월2회=0.5.
  핵심: '근무'로 적혔든 '휴무'로 적혔든 결국 '근무하는 주의 비율'로 따진다 — '격주 휴무'는 격주로 나오는 것이므로
  그 요일은 0.5다. 0 은 아예 한 번도 나오지 않는 요일에만 쓴다.
  예) 월화수금 매주 + 목·토 각 격주휴무 → 평일 4+0.5=4.5, 주말 0.5.
  주말도 합산형이라 '토 매주 + 일 월2회 = 1.5'처럼 합산값이 정상이다(0.25, 1.5 등 어떤 합산값도 가능).
- 출퇴근 시각은 근무일 구성에 종속된 '근무일수 가중평균'이다.
  각 요일의 가중치 = 그 요일 자체의 근무 빈도(매주=1, 격주=0.5, 월2회=0.5, 월1회=0.25)이다.
  각 요일이 실제로 몇 번 나오는지로 가중치를 정한다.
  예1) 토 매주(가중치 1, 9시) + 일 매주(가중치 1, 9.5시) → 주말 출근 = (9×1 + 9.5×1)/(1+1) = 9.25.
  예2) 토 매주(가중치 1, 9시) + 일 월2회(가중치 0.5, 10시) → 주말 출근 = (9×1 + 10×0.5)/1.5 = 9.333.
  ★ 양일을 '매주' 근무로 택했으면 두 요일 가중치가 모두 1 이므로 단순평균이다(가중치는 그 요일의 근무 빈도 그대로 둔다).
  weekend_work_days 를 바꾸면 weekend_start_time/weekend_end_time 도 그 구성에 맞게 다시 계산한다.
  평일 시각(weekday_*)도 평일 근무일 구성에 대한 가중평균이다. 시각과 근무일수는 한 묶음으로 본다.
- 본문에 정보가 없는 항목은 null 로 둔다(본문에 근거가 있는 값만 채운다).

[net_hourly_wage 판정 — 중요] (지속성 근무, is_one_time_work=False 인 경우에 적용)
- net_hourly_wage 는 다른 값에서 계산되는 세후 시급(파생값)이다. 본문에서 계산되는 세후 시급과 일치하면 정상이다.
- 지속성 근무에서는 급여 형태와 무관하게 (세후 급여)÷(월 근무시간)으로 도출되어 항상 존재한다.
  (일회성 근무는 위 '근무 형태별 필드' 규칙대로 one_time_hourly_wage 로만 급여를 보며, net_hourly_wage 는 null 이 정상값이다.)
- 월 근무시간은 출근~퇴근 시각의 차이로 계산한다(점심·휴게 시간을 포함한 gross 기준). net_hourly_wage 도 이 gross 시간으로 나눈 값이다.
- 계산 결과가 저장값과 약 3% 이내로 비슷하면 일치로 간주하라(반올림·환산 공식 차이를 흡수하는 허용 오차).

[현재값이 사실상 맞으면 정상으로 인정한다]
- 제안하려는 값(suggested)이 현재값(current)과 사실상 같으면 그 필드는 정상이다 — wrong_fields 에서 제외하라.
- 근무일·시각에서 0 과 null(없음)은 의미가 같다. 둘을 동일하게 취급하고 정상으로 인정하라.
- 본문이 한 값을 여러 형태로 제시하면(대표값과 괄호 보정값, 범위 등), 현재값이 그중 하나에 근거하면 정답으로 인정하라.
- '선택·협의·조정 가능'한 옵션은 복수 정답이다. 각 선택지마다 그에 따라오는 종속 필드 전체를 그 선택에 맞게
  일관되게 채운 값이면 모두 정답으로 인정하라. 여러 선택지의 값이 한 레코드에 섞였을 때만 틀린 것이다.
- 틀린 필드가 하나도 없으면 반드시 is_correct=true 로 답하라.

[복수 해석이 가능할 때 — 시나리오 일관성만 검증]
- 본문이 여러 해석을 허용하면, '하나의 시나리오'를 골라 모든 필드를 그 시나리오로 일관되게 채운다.
  임무는 현재 저장값들이 그렇게 한 시나리오로 일관되게 채워졌는지만 판정하는 것이다.

- ★ 양자택일(OR)은 한 옵션을 골라 그 옵션으로 모든 필드를 채운다(평균 대신 택일).
  '토일 양일 근무, 토요일만 근무 둘다 가능'처럼 둘 중 택일하는 옵션은 서로 배타적이다.
  이걸 평균낸 값(예: 토만=1, 토일=2 → 1.5)은 어느 해석에도 없는 무효값이다.
  ↔ 반면 '토 매주 + 일 월2회'처럼 둘 다 실제로 발생하면 합산 1.5 는 정상이다(AND, 합산형).
  즉 1.5 자체는 합산형이면 정상, 양자택일 평균이면 무효 — 본문이 'OR'인지 'AND'인지로 판단하라.

- ★ 양자택일이 동등하게 명시돼 우열을 가릴 수 없으면, '더 많이 일하는' 최대(풀) 시나리오를 채택하라.
  (예: 토 9시·일 9.5시, '토만 vs 토일 양일' → 토일 양일 채택: weekend_work_days=2,
   두 요일 모두 매주이므로 가중치 1·1, 주말 출근 = (9+9.5)/2 = 9.25.)

- 판정 기준:
  · 현재값들이 '한 시나리오'로 근무일수·출근·퇴근이 모두 모순 없이 설명되면 is_correct=true.
  · 양자택일을 평균냈거나(예: 1.5), 근무일수는 해석A·시각은 해석B인 '혼합'이면 is_correct=false.
    (예: weekend_work_days=1.5 인데 weekend_start_time=9 → 일요일이 빠진 토요일 단독 시각이라 모순.)
- 혼합/평균으로 판정하면, 위 컨벤션(최대 시나리오)으로 통일한 값을 suggested 로 제시하라.
  근무일 구성을 정하면 그 구성으로 가중평균한 시각을 함께 제시한다."""


VERIFY_SYSTEM_PROMPT = """당신은 약국 약사 구인 공고 데이터의 검수 전문가입니다.
이미 추출되어 DB에 저장된 값들이 공고 본문과 일치하는지 '검증'하는 것이 임무입니다.
이미 저장된 값을 본문과 대조해 맞는지 틀린지만 판정하는 검증 작업입니다.

""" + DOMAIN_RULES + """

[출력 형식] 아래 JSON 객체 '하나만' 출력하세요. 출력은 오직 이 JSON 뿐입니다.
- 모든 값이 본문과 일치하면 (explanation 에 '왜 맞다고 판단했는지' 근거를 한두 문장으로 채운다.
  핵심 값이 본문의 어느 서술과 어떻게 맞는지 구체적으로 적는다):
{"is_correct": true, "wrong_fields": [], "explanation": "<합격 근거 요약>"}
- 틀린 값이 있으면 (틀린 항목마다 현재값/제안값/사유 포함):
{"is_correct": false,
 "wrong_fields": [
   {"field": "<DB 필드명>", "current": <현재값>, "suggested": <옳다고 보는 값>, "reason": "<본문 근거>"}
 ],
 "explanation": "<불일치 전체 요약>"}

field 에는 반드시 아래 DB 필드명만 사용하세요(이 목록에 있는 필드만 검토 대상입니다):
is_one_time_work, one_time_hourly_wage,
weekday_work_days, weekend_work_days, weekday_start_time, weekday_end_time,
weekend_start_time, weekend_end_time, net_hourly_wage

reason 은 한 문장(40자 이내)으로 간결하게 쓰세요.
"""

# Gemini 호출 설정: JSON 강제 + thinking 활성화(격주·가중평균·시나리오 일관성 등 다단계 추론 정확도).
# thinking 토큰이 출력 한도를 함께 쓰므로, JSON 이 잘리지(MAX_TOKENS) 않도록 max_output_tokens 를 넉넉히 둔다.
_GEN_CONFIG = types.GenerateContentConfig(
    response_mime_type='application/json',
    max_output_tokens=16384,
    temperature=0.0,
    thinking_config=types.ThinkingConfig(thinking_budget=4096),
)


# 검산 시 LLM 에게 보여줄 현재 추출값 필드 (필드명, 사람용 라벨)
# COMMON 은 두 형태 공통, 나머지는 근무 형태별로만 보여준다(일회성↔지속성 필드 혼동 방지).
_VALUE_FIELDS_COMMON = [
    ('is_one_time_work', '일회성 근무'),
]

# wrong_fields 에 등장하더라도 무시할 필드 (검토 대상 아님)
_IGNORED_FIELDS = {'net_salary'}


# 값 동일 판정 허용 오차: 스케일 무관하게 상대 3% 로 통일한다.
# (월급 400만원이면 ±12만원, 시급 3.5만원이면 ±0.105만원 — 단위 크기에 비례해 자동 조정.)
_REL_TOL = 0.03  # 3%


def _values_equal(a, b):
    """current 와 suggested 가 사실상 같은 값인지 판단.

    - 숫자: 허용 오차 = 3% × max(|a|,|b|). None 은 0 으로 본다(근무일/시각에서
      '값 없음'과 0 은 의미 차이 없음). 둘 다 0 이면 정확히 같을 때만 동일로 본다.
    - 문자열: 공백·대소문자 무시 비교. None 은 빈 문자열로 본다.
    """
    # 숫자 비교 (None → 0)
    try:
        fa = float(0 if a is None else a)
        fb = float(0 if b is None else b)
        return abs(fa - fb) <= _REL_TOL * max(abs(fa), abs(fb))
    except (TypeError, ValueError):
        pass
    # 문자열 비교 (None → '')
    return str(a or '').strip().lower() == str(b or '').strip().lower()


def _clean_wrong_fields(verdict):
    """검토 대상이 아니거나(current==suggested 포함) 무시 필드인 항목을 제거한 리스트 반환."""
    cleaned = []
    for wf in verdict.get('wrong_fields') or []:
        if not isinstance(wf, dict):
            continue
        if wf.get('field') in _IGNORED_FIELDS:
            continue
        if _values_equal(wf.get('current'), wf.get('suggested')):
            continue
        cleaned.append(wf)
    return cleaned
_VALUE_FIELDS_ONETIME = [
    ('one_time_hourly_wage', '일회성 시급(만원)'),
]
_VALUE_FIELDS_CONTINUOUS = [
    ('net_salary', '세후 월급(만원)'),
    ('net_hourly_wage', '세후 시급(만원)'),
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


def _format_pass_comment(verdict, is_truly_correct):
    """합격 판정 사유를 user_comment 용 문자열로 조립."""
    if is_truly_correct:
        expl = (verdict.get('explanation') or '').strip()
        return '[LLM 합격] ' + (expl or '추출값이 본문과 일치함.')
    # is_correct=false 였지만 지적 항목이 모두 오탐(현재값과 동일)으로 걸러진 경우
    return '[LLM 합격] 자동 점검에서 지적된 항목이 모두 현재값과 동일(오탐)로 확인됨.'


def apply_verdict(posting, verdict):
    """판정을 DB에 적용. 'ok' | 'error' | 'failed' 반환."""
    if not isinstance(verdict, dict) or 'is_correct' not in verdict:
        return 'failed'

    # 무시 필드·current==suggested 항목을 걸러낸다.
    # 걸러낸 뒤 진짜 틀린 필드가 없으면 LLM 이 is_correct=false 라 했어도 '정상'으로 본다.
    real_wrong = _clean_wrong_fields(verdict)

    if verdict.get('is_correct') is True or not real_wrong:
        # 합격 사유를 코멘트에 기록 (사람이 남긴 기존 코멘트는 덮어쓰지 않는다).
        if not (posting.user_comment or '').strip():
            posting.user_comment = _format_pass_comment(
                verdict, is_truly_correct=verdict.get('is_correct') is True
            )
            posting.save()
        AdminCheck.objects.get_or_create(
            posting=posting, defaults={'source': AdminCheck.SOURCE_LLM}
        )
        return 'ok'

    verdict['wrong_fields'] = real_wrong
    posting.gpt_error_log = _format_log(verdict)
    posting.save()  # save() 가 gpt_error_log 를 보고 has_error=True 로 설정
    return 'error'
