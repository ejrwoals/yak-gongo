"""
3단계 에러 케이스 재검토를 위한 '대화형 agent 검토' 서비스.

리뷰 대시보드에서 공고를 선택해 'AI agent 대화형 검토'를 열면, 현재 DB 필드 / 공고 원문 /
에러 로그를 모두 context로 가진 Gemini agent와 대화하며 잘못된 필드를 바로잡는다.

설계(plan §3, §4):
- 매 호출마다 현재 DB 스냅샷을 system_instruction 에 재주입한다(stateless 서버, stale 방지).
- 모델은 구조화 출력(JSON: message + updates)으로 답한다. updates 가 비어있지 않으면 서버는
  '실행하지 않고' 제안(diff)만 돌려준다. 실제 DB 변경은 사용자가 UI 권한 박스에서 승인했을 때
  apply_turn() 경로에서만 일어난다. (function-calling 은 Gemini thinking 과 충돌해 쓰지 않는다.)
- 약국 도메인 지식은 review_verify.DOMAIN_RULES 를 공유해 검산과 수정 기준을 일치시킨다.

Gemini 호출 패턴은 review_verify.py 를, 값 변환은 admin._convert_value 의 의미를 따른다.
"""
import json
import uuid

from google.genai import types

from .review_presets import FIELD_META, _COMMON_EXPAND_EDITABLE
from .review_verify import DOMAIN_RULES, _values_equal

# 모달 패널·스냅샷에 보여줄 전체 필드(값 확인용). 모델은 이 값들을 근거로 추론한다.
AGENT_VISIBLE_FIELDS = list(_COMMON_EXPAND_EDITABLE)

# 파생 필드: 기반 입력값에서 결정론적으로 자동 계산되므로 agent 직접 편집을 막는다.
# 승인된 수정 반영 직후 recompute_derived() 가 파이프라인 공식으로 다시 채운다.
AGENT_DERIVED_FIELDS = ['hours_per_week', 'hours_per_month', 'net_hourly_wage']

# agent 가 수정 제안할 수 있는 필드 = 표시 필드 − 파생 필드.
AGENT_EDITABLE_FIELDS = [f for f in AGENT_VISIBLE_FIELDS if f not in AGENT_DERIVED_FIELDS]
_EDITABLE_SET = set(AGENT_EDITABLE_FIELDS)

# 가상 입력 필드: 본문이 '세전' 금액을 제시할 때 모델이 net_salary 대신 이 필드로 세전 월급을
# 넘기면, 서버가 파이프라인 공식(calculate_net_salary)으로 세후로 환산해 net_salary 에 반영한다.
# (별도 계산기 '도구'를 두면 함수 호출이 늘어 Gemini thinking 과 충돌, MALFORMED 유발 →
#  세전 환산은 가상 필드 위임으로 처리한다. 출력 자체도 function-calling 이 아니라 구조화 출력.)
PRETAX_FIELD = 'net_salary_pretax'

# 빈 history(모달 최초 오픈) 일 때 agent 가 먼저 브리핑하도록 주입하는 트리거 user 턴.
INITIAL_BRIEF_TRIGGER = (
    '이 에러 케이스를 검토해 주세요. 에러 로그·현재 DB값·본문을 근거로 무엇이 왜 틀렸는지 '
    '간결히 브리핑하고, 고쳐야 할 부분이 있으면 수정안을 제시해 주세요.'
)

AGENT_SYSTEM_PROMPT = """당신은 약국 약사 구인 공고 데이터의 검수를 돕는 대화형 보조 agent입니다.
'에러 케이스'(자동 검산에서 본문과 불일치가 발견된 공고)를 사용자와 대화하며 바로잡는 것이 임무입니다.

""" + DOMAIN_RULES + """

[작업 방식 — 가장 중요]
- 에러 로그는 '이전 자동 검산이 의심한 가설'로 취급하고, 공고 본문과 도메인 규칙에 비추어 네가 직접 다시 검증한다:
  · 에러 로그의 지적이 타당한지, 제안하려는 값이 본문 근거로 맞는지 스스로 재계산·재확인한다.
  · 에러 로그가 타당하면 수정을 제안하고, 에러 로그가 틀렸거나 과하면 "이 지적은 맞지 않다"고 분명히 말하며 현재값을 그대로 둔다.
- 첫 턴 브리핑은 ① 에러 로그 요지 ② 본문 대조 결과(맞음/틀림/불확실 중 너의 판단과 근거)를 간결히 제시한다.
- 출력은 항상 JSON 으로 한다: message 에는 한국어 설명·브리핑을, updates 에는 바꿀 필드 목록을 담는다(각 항목 field/value/reason).
- 값이 '명확히 틀렸고' 정답이 '본문으로 하나로 확정'되며 '실제로 바꿀 필드가 하나 이상' 있을 때 updates 에 그 필드들을 담아 제안한다. message 에 근거를 짧게 설명하고, 승인 여부는 UI 권한 박스가 처리한다.
- 모든 값이 본문과 일치하면 updates 를 빈 배열로 두고, message 에 '정상 — 수정할 필드 없음'이라고 결론을 전한다.
- 다음 경우에는 수정 제안 대신 'updates 를 비우고 먼저 사용자에게 의견을 묻는다':
  · 본문이 여러 해석을 허용해 값이 하나로 확정되지 않을 때(복수 시나리오·선택·협의 가능 등).
  · 본문 근거가 부족해 추측이 필요할 때.
  · 에러 로그의 타당성에 대한 판단이 갈릴 때.
  이때는 무엇이 모호한지·어떤 선택지가 있는지 설명하고 사용자의 결정을 기다린다.
- 수정은 이번 에러와 직접 관련된 필드에 한해 '꼭 필요한 최소한'만 한다. 이미 본문과 맞는 값은 그대로 둔다.
- 본문에 근거가 있는 값만 채우고, 근거가 없는 항목은 null 로 둔다.
- 급여 환산 기준:
  · 세전→세후 환산 공식(시스템 파이프라인과 동일): 세후월급 = 5.35 + 0.904394 × 세전월급 − 0.000143950695 × 세전월급². (네이버 세금계산기 표본으로 피팅한 회귀식이라 4대보험·소득세 공제가 이 식에 이미 반영돼 있다. 환산을 설명할 때는 이 식을 근거로 든다.)
  · 본문이 '세전(세금 전) 월급·연봉'을 제시한 경우, 저장된 net_salary 가 맞다고 가정하지 말고 위 식으로 세후 기대값을 직접 검산한다. 그 세전 월 금액(연봉이면 12로 나눈 값)을 net_salary_pretax 로 제안하면 시스템이 정확히 환산해 net_salary 에 반영한다. 저장값이 기대값과 사실상 같으면(약 3% 허용 오차) 변경이 일어나지 않고, 차이가 그보다 크면 교정 제안된다.
  · 본문이 이미 세후 금액을 말하거나, 일급·시급처럼 실제 받는 금액(실수령)으로 제시된 경우에는 그 세후 값을 net_salary 필드로 그대로 제안한다.
- 승인되어 반영되면 결과를 한국어로 짧게 확인하고, 거부되면 사유를 묻거나 대안을 제시한다.
- 답변은 한국어로 간결하게. 숫자 단위는 만원, 시각은 24시간제 실수(오전 9시=9.0, 오후 6시 30분=18.5)이다.

수정 가능한 필드(이외 필드는 변경 불가):
""" + ', '.join(AGENT_EDITABLE_FIELDS) + """
추가로 net_salary_pretax(세전 월급 입력 → 시스템이 세후로 환산)도 제안할 수 있다.

파생 필드(""" + ', '.join(AGENT_DERIVED_FIELDS) + """)는 시스템이 자동 계산한다. 기반 입력값(근무 일정·net_salary)만 제안하면, 승인 즉시 시스템이 파이프라인과 동일한 공식으로 이 값들을 다시 채운다. 따라서 기반 입력값을 바로잡는 데 집중한다.
"""


# ── 값 변환/표시 (admin._convert_value 와 같은 의미, 순환 import 회피 위해 로컬 구현) ──

def _convert(field, value):
    """클라이언트/모델이 보낸 값을 FIELD_META 타입에 맞게 변환."""
    t = FIELD_META.get(field, {'type': 'char'}).get('type', 'char')
    if t == 'bool':
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ('true', '1', 'y', 'yes', 'on', 't')
    if t == 'float':
        if value is None or str(value).strip().lower() in ('', 'null', 'none', '-'):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    # char / text
    return '' if value is None else str(value)


def _display(value, field_type):
    """diff/패널 표시용 문자열."""
    if value is None:
        return '—'
    if field_type == 'bool':
        return 'Y' if value else 'N'
    if field_type == 'float':
        if isinstance(value, float):
            return f'{value:.2f}'.rstrip('0').rstrip('.') if value % 1 else str(int(value))
        return str(value)
    s = str(value)
    return s if s.strip() else '—'


# ── 정보 패널 / 스냅샷 ──

def field_snapshot(posting):
    """모달 좌측 정보 패널용: 현재값 목록(파생 필드 포함). 파생 필드는 자동계산 표시."""
    out = []
    for f in AGENT_VISIBLE_FIELDS:
        meta = FIELD_META.get(f, {'label': f, 'type': 'char'})
        out.append({
            'field': f,
            'label': meta['label'],
            'value': _display(getattr(posting, f, None), meta['type']),
            'derived': f in AGENT_DERIVED_FIELDS,
        })
    return out


def _snapshot_text(posting):
    """system_instruction 에 재주입하는 현재 DB 스냅샷 + 에러 로그 + 본문."""
    posting_date = getattr(posting, 'created_at', None)
    lines = [
        '[공고 날짜]',
        f'{posting_date:%Y-%m-%d (%a)}' if posting_date else '(없음)',
        '',
        '[현재 DB 저장값] (파생 필드는 자동계산 — 직접 수정 불가)',
    ]
    for f in AGENT_VISIBLE_FIELDS:
        meta = FIELD_META.get(f, {'label': f})
        tag = ' [자동계산]' if f in AGENT_DERIVED_FIELDS else ''
        lines.append(f'- {f} ({meta["label"]}){tag}: {getattr(posting, f, None)!r}')
    lines += [
        '',
        '[에러 로그 (gpt_error_log)]',
        (posting.gpt_error_log or '(없음)'),
        '',
        '[공고 제목]',
        (posting.title or '(없음)'),
        '',
        '[공고 본문]',
        (posting.body or '(본문 없음)'),
    ]
    return '\n'.join(lines)


# ── 응답 스키마 / 호출 설정 ──

def _response_schema():
    """구조화 출력 스키마: message(브리핑/설명) + updates(수정안 목록).

    function-calling 대신 response_schema(제약 디코딩)를 쓴다 — Gemini 2.5 의
    MALFORMED_FUNCTION_CALL(thinking+함수호출 조합) 을 구조적으로 회피하면서 thinking 을 유지한다.
    """
    return types.Schema(
        type='OBJECT',
        properties={
            'message': types.Schema(
                type='STRING',
                description='사용자에게 보여줄 한국어 브리핑/설명. 수정안이 없어도 항상 채운다.',
            ),
            'updates': types.Schema(
                type='ARRAY',
                description='제안할 수정 필드 목록. 바꿀 필드가 없으면 빈 배열. 이미 맞는 값은 넣지 말 것.',
                items=types.Schema(
                    type='OBJECT',
                    properties={
                        'field': types.Schema(type='STRING', description='DB 필드명'),
                        'value': types.Schema(
                            type='STRING',
                            description='새 값을 문자열로. 숫자/불리언도 문자열로 적고, 값 없음은 "null".',
                        ),
                        'reason': types.Schema(type='STRING', description='본문 근거(한 문장)'),
                    },
                    required=['field', 'value'],
                ),
            ),
        },
        required=['message', 'updates'],
    )


def _normalize_updates(updates):
    """모델이 보낸 수정 목록을 실제 필드로 정규화한다.

    가상 입력 net_salary_pretax(세전 월급) → net_salary(세후, 파이프라인 공식 환산).
    별도 계산기 '도구' 없이도 세전→세후 환산을 결정론적으로 처리한다.
    """
    from pipeline.salary import calculate_net_salary
    out = []
    for u in updates:
        if not isinstance(u, dict):
            continue
        if u.get('field') == PRETAX_FIELD:
            try:
                gross = float(u.get('value'))
            except (TypeError, ValueError):
                continue  # 숫자가 아니면 무시
            net = round(calculate_net_salary(gross), 2)
            # 모델은 세전 기준으로 제안하지만 저장값은 세후다. 환산이 일어났다는
            # 사실을 reason 맨 앞에 항상 붙여 "왜 91이 86.46이 됐는지" 혼란을 막는다.
            note = f'세전 {gross:g}만원을 세후 {net:g}만원으로 자동 환산'
            extra = (u.get('reason') or '').strip()
            reason = f'{note} ({extra})' if extra else note
            out.append({'field': 'net_salary', 'value': str(net), 'reason': reason})
        else:
            out.append(u)
    return out


def _config(posting, temperature=0.2):
    # thinking 토큰이 출력 한도를 함께 쓰므로, 답변이 MAX_TOKENS 로 잘리지 않도록 한도를 넉넉히 둔다.
    # function-calling 대신 response_schema(구조화 출력)를 쓴다: Gemini 2.5 는 '함수호출 + thinking'
    # 조합에서 MALFORMED_FUNCTION_CALL 을 ~12% 낸다(측정값). 제약 디코딩은 형식 오류가 구조적으로
    # 불가능해 thinking 을 켠 채로도 실패하지 않는다. 세전→세후 환산은 net_salary_pretax 가상 필드로 위임.
    return types.GenerateContentConfig(
        system_instruction=AGENT_SYSTEM_PROMPT + '\n\n' + _snapshot_text(posting),
        response_mime_type='application/json',
        response_schema=_response_schema(),
        temperature=temperature,
        max_output_tokens=16384,
        thinking_config=types.ThinkingConfig(thinking_budget=2048),
    )


def _is_empty_or_malformed(response):
    """본문(JSON 텍스트)이 없는 응답인지 판정. 단, MAX_TOKENS·SAFETY 는 재시도해도
    회복되지 않으므로 False 로 두어 그대로 사용자에게 사유를 보여준다."""
    cand = None
    try:
        cand = response.candidates[0]
    except (AttributeError, IndexError, TypeError):
        cand = None
    try:
        if (response.text or '').strip():
            return False
    except Exception:  # noqa: BLE001
        pass
    fr = ''
    try:
        fr = str(cand.finish_reason or '') if cand else ''
    except Exception:  # noqa: BLE001
        fr = ''
    return 'MAX_TOKENS' not in fr and 'SAFETY' not in fr


def _generate(client, model_name, posting, contents):
    """모델 호출. 빈 응답은 확률적 실패라 온도를 올려가며 최대 3회 재시도한다.
    (구조화 출력이라 형식 오류는 발생하지 않는다.) 마지막 응답을 그대로 반환한다."""
    temps = (0.2, 0.6, 1.0)
    response = None
    for i, temp in enumerate(temps):
        response = client.models.generate_content(
            model=model_name, contents=contents, config=_config(posting, temp),
        )
        if not _is_empty_or_malformed(response):
            return response
        print(f'[agent RETRY] attempt={i + 1}/{len(temps)} empty/malformed → 재시도')
    return response


# ── history(브라우저 보유) ↔ Gemini contents 복원 ──

def _trigger_content():
    return types.Content(role='user', parts=[types.Part(text=INITIAL_BRIEF_TRIGGER)])


def _proposal_summary(tc):
    """모델 제안(tool_call)의 변경 내역을 한 줄 텍스트로 요약(history 복원용)."""
    changed = [d for d in (tc.get('diff') or []) if d.get('changed')]
    if not changed:
        return ''
    desc = ', '.join(f'{d["label"]} {d["current"]}→{d["proposed"]}' for d in changed)
    return f'[제안한 수정] {desc}'


def build_contents(messages):
    """프런트 history 를 Gemini contents(순수 텍스트)로 복원.

    구조화 출력 방식이라 function_call/response part 가 없다. 모델 턴은 브리핑 텍스트(+제안 요약),
    승인/거부 결과는 시스템 안내 user 턴으로 재구성한다.
    """
    if not messages:
        return [_trigger_content()]

    contents = []
    for m in messages:
        role = m.get('role')
        if role == 'user':
            contents.append(types.Content(role='user', parts=[types.Part(text=m.get('text', ''))]))
        elif role == 'model':
            chunks = []
            if m.get('text'):
                chunks.append(m['text'])
            tc = m.get('tool_call')
            if tc:
                summary = _proposal_summary(tc)
                if summary:
                    chunks.append(summary)
            if chunks:
                contents.append(types.Content(role='model', parts=[types.Part(text='\n'.join(chunks))]))
        elif role == 'tool':
            contents.append(types.Content(role='user', parts=[types.Part(text=_outcome_text(m))]))
    # 브리핑이 서버에서 시작돼 history 가 model 턴으로 시작하면, 맨 앞에 트리거 user 턴을 보강한다.
    if contents and contents[0].role != 'user':
        contents.insert(0, _trigger_content())
    return contents


def _empty_reason(response, cand):
    """텍스트·function_call 이 모두 없을 때 사유를 진단해 사용자용 메시지로 반환."""
    fr = ''
    try:
        fr = str(cand.finish_reason or '')
    except Exception:  # noqa: BLE001
        pass
    # 콘솔 진단 로그 (usage 포함)
    usage = getattr(response, 'usage_metadata', None)
    print(f'[agent EMPTY] finish_reason={fr} usage={usage}')
    if 'MAX_TOKENS' in fr:
        return '응답이 한도를 초과해 잘렸습니다(MAX_TOKENS). 다시 시도하거나 더 짧게 요청해 주세요.'
    if 'SAFETY' in fr:
        return '안전 필터에 의해 응답이 차단되었습니다(SAFETY).'
    if 'RECITATION' in fr:
        return '응답이 인용 정책으로 차단되었습니다(RECITATION). 다시 시도해 주세요.'
    if 'MALFORMED_FUNCTION_CALL' in fr:
        return '모델이 수정안(함수 호출)을 만들다 형식 오류가 났습니다(재시도했으나 회복 실패). 다시 시도해 주세요.'
    return '모델이 빈 응답을 반환했습니다. 다시 시도해 주세요.'


def _parse_response(response):
    """구조화 출력(JSON 텍스트)을 {message, updates} 로 파싱. 실패 시 (None, [])."""
    try:
        text = (response.text or '').strip()
    except Exception:  # noqa: BLE001
        text = ''
    if not text:
        return None, []
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return None, []  # 제약 디코딩이라 거의 없음. 안전망.
    message = (obj.get('message') or '').strip() if isinstance(obj, dict) else ''
    updates = obj.get('updates') if isinstance(obj, dict) else None
    updates = [u for u in (updates or []) if isinstance(u, dict)]
    return message, updates


def _interpret(posting, response):
    """Gemini 응답을 {type:'message'|'tool_request', ...} 로 해석. DB 변경 없음."""
    cand = None
    try:
        cand = response.candidates[0]
    except (AttributeError, IndexError, TypeError):
        cand = None
    message, updates = _parse_response(response)
    diff = build_diff(posting, updates)
    fr = ''
    try:
        fr = str(cand.finish_reason or '') if cand else ''
    except Exception:  # noqa: BLE001
        fr = ''
    print(f'[agent INTERPRET] finish={fr} msg_len={len(message or "")} '
          f'updates={len(updates)} changed={[d["field"] for d in diff if d.get("changed")]}')

    # 실제로 바뀌는 필드가 있으면 제안. 빈 목록·현재값과 동일하면 일반 답변으로 처리.
    if any(d.get('changed') for d in diff):
        return {
            'type': 'tool_request',
            'text': message,
            'tool_call': {
                'id': uuid.uuid4().hex[:12],
                'name': 'update_posting_fields',
                'args': {'updates': updates},
                'diff': diff,
            },
        }
    if message:
        return {'type': 'message', 'reply': message}
    return {'type': 'message', 'reply': _empty_reason(response, cand)}


# ── diff / 적용 ──

def build_diff(posting, updates):
    """제안값을 현재값과 대비한 diff(권한 박스 렌더용). DB 변경 없음."""
    diff = []
    for u in _normalize_updates(updates):
        field = u.get('field')
        if field not in _EDITABLE_SET:
            continue
        meta = FIELD_META.get(field, {'label': field, 'type': 'char'})
        current = getattr(posting, field, None)
        proposed = _convert(field, u.get('value'))
        diff.append({
            'field': field,
            'label': meta['label'],
            'current': _display(current, meta['type']),
            'proposed': _display(proposed, meta['type']),
            'reason': (u.get('reason') or '').strip(),
            'changed': not _values_equal(current, proposed),
        })
    return diff


def recompute_derived(posting):
    """파생 필드를 파이프라인과 동일한 공식으로 결정론적 재계산해 채운다.

    agent 가 직접 편집할 수 없는 hours_per_week·hours_per_month·net_hourly_wage 를
    기반 입력값(근무 일정·net_salary)으로부터 다시 계산한다. net_salary 자체는 본문 판단
    (세전이면 net_salary_pretax 위임으로 환산된)의 결과라 여기서 만들지 않고 입력으로 쓴다.
    """
    from pipeline.salary import ceil_hourly_wage

    def _span(start, end, days):
        if start is not None and end is not None and days is not None:
            return (end - start) * days
        return None

    # 1) 주당 근무시간 = 평일 + 주말, 각 (퇴근-출근) × 근무일. 일정 단서가 있을 때만 갱신.
    weekday_h = _span(posting.weekday_start_time, posting.weekday_end_time, posting.weekday_work_days)
    weekend_h = _span(posting.weekend_start_time, posting.weekend_end_time, posting.weekend_work_days)
    if weekday_h is not None or weekend_h is not None:
        posting.hours_per_week = (weekday_h or 0) + (weekend_h or 0)

    # 2) 월 근무시간 = 주당 × 4.34 (pipeline/runner.py 와 동일한 환산 계수)
    if posting.hours_per_week is not None:
        posting.hours_per_month = posting.hours_per_week * 4.34

    # 3) 세후 시급 = ceil(세후 월급 ÷ 월 근무시간). 지속성 근무 + 값이 갖춰졌을 때만.
    if (not posting.is_one_time_work
            and posting.net_salary is not None
            and posting.hours_per_month):
        posting.net_hourly_wage = ceil_hourly_wage(posting.net_salary / posting.hours_per_month)


def apply_update(posting, updates):
    """수정안을 실제 DB에 반영(승인된 경우에만 호출). 반환 [{field,label,old,new}].

    기반 필드 반영 직후 recompute_derived() 로 파생 필드를 자동 재계산한다.
    자동 변경분도 diff(auto=True)에 포함해 권한 박스/패널에 노출한다.
    """
    applied = []
    for u in _normalize_updates(updates):
        field = u.get('field')
        if field not in _EDITABLE_SET:
            continue
        meta = FIELD_META.get(field)
        if not meta:
            continue
        old = getattr(posting, field, None)
        new = _convert(field, u.get('value'))
        setattr(posting, field, new)
        applied.append({
            'field': field,
            'label': meta['label'],
            'old': _display(old, meta['type']),
            'new': _display(new, meta['type']),
        })

    # 파생 필드 자동 재계산 — 변경된 것만 diff 에 추가.
    before = {f: getattr(posting, f, None) for f in AGENT_DERIVED_FIELDS}
    recompute_derived(posting)
    for f in AGENT_DERIVED_FIELDS:
        old, new = before[f], getattr(posting, f, None)
        if not _values_equal(old, new):
            meta = FIELD_META.get(f, {'label': f, 'type': 'float'})
            applied.append({
                'field': f,
                'label': meta['label'],
                'old': _display(old, meta['type']),
                'new': _display(new, meta['type']),
                'auto': True,
            })

    if applied:
        posting.save()
    return applied


# ── 턴 진행 ──

def propose_turn(posting, messages, client, model_name):
    """한 턴 진행. tool_request(제안) 또는 message 반환. DB 변경 없음."""
    response = _generate(client, model_name, posting, build_contents(messages))
    return _interpret(posting, response)


def _outcome_text(m):
    """승인/거부 결과를 모델에 전달할 시스템 안내 user 턴 텍스트로 변환."""
    if m.get('decision') == 'approved':
        applied = m.get('applied') or []
        if applied:
            desc = ', '.join(
                f'{a.get("label", a.get("field"))} {a.get("old")}→{a.get("new")}' for a in applied)
            return f'[시스템] 위 수정안이 승인되어 반영되었습니다. 적용: {desc}'
        return '[시스템] 승인되었으나 실제로 변경된 필드는 없습니다.'
    note = (m.get('note') or '').strip()
    if note:
        return f'[시스템] 사용자가 수정안을 거부하고 다음 방향을 요청했습니다: {note}'
    return '[시스템] 사용자가 이 수정 제안을 거부했습니다.'


def apply_turn(posting, messages, tool_call, decision, client, model_name, note=''):
    """권한 박스 결정 처리. 승인 시에만 DB 변경 후 모델 후속 응답을 받아 반환.

    거부 시 note 가 있으면 사용자의 수정 방향을 모델에 바로 전달해, 사유를 되묻는
    중간 단계 없이 대안을 제시하도록 한다.
    messages 는 모델 제안 턴까지 포함하고 그 뒤 결과 턴은 아직 없는 상태여야 한다.
    반환: _interpret 결과 + {'applied': [...]}.
    """
    if decision == 'approved':
        updates = (tool_call.get('args') or {}).get('updates') or []
        applied = apply_update(posting, updates)
    else:
        applied = []

    contents = build_contents(messages)
    outcome = {'decision': decision, 'applied': applied, 'note': note}
    contents.append(types.Content(role='user', parts=[types.Part(text=_outcome_text(outcome))]))
    response = _generate(client, model_name, posting, contents)
    interp = _interpret(posting, response)
    interp['applied'] = applied
    return interp


# ── 검토 완료: 코멘트 생성 / 누적 변경 집계 ──

def _format_transcript(messages):
    lines = []
    for m in messages:
        role = m.get('role')
        if role == 'user':
            lines.append(f'[사용자] {m.get("text", "")}')
        elif role == 'model':
            if m.get('text'):
                lines.append(f'[agent] {m["text"]}')
            tc = m.get('tool_call')
            if tc:
                changed = [d for d in (tc.get('diff') or []) if d.get('changed')]
                desc = ', '.join(f'{d["label"]} {d["current"]}→{d["proposed"]}' for d in changed)
                lines.append(f'[agent 제안] {desc or "(변경 없음)"}')
        elif role == 'tool':
            dec = m.get('decision')
            if dec == 'approved':
                applied = m.get('applied') or []
                desc = ', '.join(f'{a.get("label", a.get("field"))} {a.get("old")}→{a.get("new")}' for a in applied)
                lines.append(f'[적용됨] {desc or "(없음)"}')
            elif dec == 'rejected':
                note = (m.get('note') or '').strip()
                lines.append(f'[거부됨] 요청: {note}' if note else '[거부됨]')
    return '\n'.join(lines)


def collect_applied_changes(messages):
    """세션 동안 승인되어 적용된 변경을 누적 집계(AgentReviewSession.applied_changes 용)."""
    out = []
    for m in messages:
        if m.get('role') == 'tool' and m.get('decision') == 'approved':
            out.extend(m.get('applied') or [])
    return out


def generate_comment(posting, messages, client, model_name):
    """대화를 바탕으로 user_comment 1~3문장 요약 생성."""
    sys = (
        '아래는 약국 구인공고 에러 케이스에 대한 대화형 검토 기록입니다. '
        '이 대화를 바탕으로 무엇을 어떻게 검토/수정했는지 1~3문장의 한국어로 요약하세요. '
        '반드시 "[대화형 검토]" 로 시작하고, 요약 문장만 출력하세요(군더더기 금지).'
    )
    transcript = _format_transcript(messages) or '(대화 없음)'
    response = client.models.generate_content(
        model=model_name,
        contents=[types.Content(role='user', parts=[types.Part(text=transcript)])],
        config=types.GenerateContentConfig(
            # 1~3문장 요약이라 thinking 불필요. thinking 을 끄고(예산 0) 한도를 넉넉히 둬
            # 코멘트가 MAX_TOKENS 로 문장 중간에 잘리지 않도록 한다.
            system_instruction=sys, temperature=0.3, max_output_tokens=2048,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    text = (response.text or '').strip()
    if not text:
        return '[대화형 검토] 검토 완료.'
    return text if text.startswith('[대화형 검토]') else '[대화형 검토] ' + text
