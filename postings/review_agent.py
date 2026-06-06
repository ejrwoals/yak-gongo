"""
3단계 에러 케이스 재검토를 위한 '대화형 agent 검토' 서비스.

리뷰 대시보드에서 공고를 선택해 'AI agent 대화형 검토'를 열면, 현재 DB 필드 / 공고 원문 /
에러 로그를 모두 context로 가진 Gemini agent와 대화하며 잘못된 필드를 바로잡는다.

설계(plan §3, §4):
- 매 호출마다 현재 DB 스냅샷을 system_instruction 에 재주입한다(stateless 서버, stale 방지).
- 모델이 update_posting_fields 도구 호출을 emit 하면 서버는 '실행하지 않고' 제안(diff)만 돌려준다.
  실제 DB 변경은 사용자가 UI 권한 박스에서 승인했을 때 apply_turn() 경로에서만 일어난다.
- 약국 도메인 지식은 review_verify.DOMAIN_RULES 를 공유해 검산과 수정 기준을 일치시킨다.

Gemini 호출 패턴은 review_verify.py 를, 값 변환은 admin._convert_value 의 의미를 따른다.
"""
import uuid

from google.genai import types

from .review_presets import FIELD_META, _COMMON_EXPAND_EDITABLE
from .review_verify import DOMAIN_RULES, _values_equal

# agent 가 수정할 수 있는 필드 (error_review editable 전체 = _COMMON_EXPAND_EDITABLE)
AGENT_EDITABLE_FIELDS = list(_COMMON_EXPAND_EDITABLE)
_EDITABLE_SET = set(AGENT_EDITABLE_FIELDS)

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
- 값이 '명확히 틀렸고' 정답이 '본문으로 하나로 확정'되며 '실제로 바꿀 필드가 하나 이상' 있을 때 수정을 제안한다. 이때 '제안'은 항상 같은 답변 안에서 update_posting_fields 도구를 호출해 표현한다 — 바꿀 필드를 도구 인자에 담아 호출하는 것이 곧 제안이다. 근거를 짧게 설명한 뒤 그 설명과 함께 도구를 호출하면 되고, 승인 여부는 UI 권한 박스가 처리한다.
- 모든 값이 본문과 일치하면 도구 없이 텍스트로 '정상 — 수정할 필드 없음'이라고 결론을 전한다.
- 다음 경우에는 도구 호출 대신 '먼저 사용자에게 의견을 묻는다':
  · 본문이 여러 해석을 허용해 값이 하나로 확정되지 않을 때(복수 시나리오·선택·협의 가능 등).
  · 본문 근거가 부족해 추측이 필요할 때.
  · 에러 로그의 타당성에 대한 판단이 갈릴 때.
  이때는 무엇이 모호한지·어떤 선택지가 있는지 설명하고 사용자의 결정을 기다린다.
- 수정은 이번 에러와 직접 관련된 필드에 한해 '꼭 필요한 최소한'만 한다. 이미 본문과 맞는 값은 그대로 둔다.
- 본문에 근거가 있는 값만 채우고, 근거가 없는 항목은 null 로 둔다.
- 승인되어 반영되면 결과를 한국어로 짧게 확인하고, 거부되면 사유를 묻거나 대안을 제시한다.
- 답변은 한국어로 간결하게. 숫자 단위는 만원, 시각은 24시간제 실수(오전 9시=9.0, 오후 6시 30분=18.5)이다.

수정 가능한 필드(이외 필드는 변경 불가):
""" + ', '.join(AGENT_EDITABLE_FIELDS) + """
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


def _plain(obj):
    """Gemini function_call.args 의 proto 컨테이너를 순수 dict/list 로 변환."""
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    try:  # MapComposite / RepeatedComposite 등
        if hasattr(obj, 'items'):
            return {k: _plain(v) for k, v in obj.items()}
        if hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):
            return [_plain(v) for v in obj]
    except Exception:  # noqa: BLE001
        pass
    return obj


# ── 정보 패널 / 스냅샷 ──

def field_snapshot(posting):
    """모달 좌측 정보 패널용: 편집 가능 필드 현재값 목록."""
    out = []
    for f in AGENT_EDITABLE_FIELDS:
        meta = FIELD_META.get(f, {'label': f, 'type': 'char'})
        out.append({
            'field': f,
            'label': meta['label'],
            'value': _display(getattr(posting, f, None), meta['type']),
        })
    return out


def _snapshot_text(posting):
    """system_instruction 에 재주입하는 현재 DB 스냅샷 + 에러 로그 + 본문."""
    posting_date = getattr(posting, 'created_at', None)
    lines = [
        '[공고 날짜]',
        f'{posting_date:%Y-%m-%d (%a)}' if posting_date else '(없음)',
        '',
        '[현재 DB 저장값] (수정 가능 필드)',
    ]
    for f in AGENT_EDITABLE_FIELDS:
        meta = FIELD_META.get(f, {'label': f})
        lines.append(f'- {f} ({meta["label"]}): {getattr(posting, f, None)!r}')
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


# ── 도구 선언 / 호출 설정 ──

def _tool():
    return types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name='update_posting_fields',
            description=(
                '공고의 DB 필드 수정안을 제안한다. 실제 반영은 사용자 승인 후에만 일어난다. '
                '바꿔야 할 필드만 포함하라(이미 맞는 값은 넣지 말 것).'
            ),
            parameters=types.Schema(
                type='OBJECT',
                properties={
                    'updates': types.Schema(
                        type='ARRAY',
                        description='수정할 필드 목록',
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
                required=['updates'],
            ),
        ),
    ])


def _config(posting, temperature=0.2):
    # thinking 토큰이 출력 한도를 함께 쓰므로, 답변이 MAX_TOKENS 로 잘리지 않도록 한도를 넉넉히 둔다.
    return types.GenerateContentConfig(
        system_instruction=AGENT_SYSTEM_PROMPT + '\n\n' + _snapshot_text(posting),
        tools=[_tool()],
        temperature=temperature,
        max_output_tokens=16384,
        thinking_config=types.ThinkingConfig(thinking_budget=2048),
    )


def _is_empty_or_malformed(response):
    """본문/함수호출이 모두 없는 응답인지 판정. 단, MAX_TOKENS·SAFETY 는 재시도해도
    회복되지 않으므로 False 로 두어 그대로 사용자에게 사유를 보여준다."""
    cand = None
    try:
        cand = response.candidates[0]
        parts = cand.content.parts or []
    except (AttributeError, IndexError, TypeError):
        parts = []
    has_content = any(
        getattr(p, 'function_call', None)
        or (getattr(p, 'text', None) and not getattr(p, 'thought', False))
        for p in parts
    )
    if has_content:
        return False
    fr = ''
    try:
        fr = str(cand.finish_reason or '') if cand else ''
    except Exception:  # noqa: BLE001
        fr = ''
    return 'MAX_TOKENS' not in fr and 'SAFETY' not in fr


def _generate(client, model_name, posting, contents):
    """모델 호출. MALFORMED_FUNCTION_CALL·빈 응답은 확률적 실패라, 온도를 올려가며
    최대 3회 재시도해 회복을 노린다. 마지막 응답을 그대로 반환한다."""
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


def build_contents(messages):
    """프런트 history 를 Gemini contents(function_call/response part 포함)로 복원."""
    if not messages:
        return [_trigger_content()]

    contents = []
    for m in messages:
        role = m.get('role')
        if role == 'user':
            contents.append(types.Content(role='user', parts=[types.Part(text=m.get('text', ''))]))
        elif role == 'model':
            parts = []
            if m.get('text'):
                parts.append(types.Part(text=m['text']))
            tc = m.get('tool_call')
            if tc:
                parts.append(types.Part.from_function_call(
                    name=tc.get('name', 'update_posting_fields'),
                    args=(tc.get('args') or {}),
                ))
            if parts:
                contents.append(types.Content(role='model', parts=parts))
        elif role == 'tool':
            result = m.get('result')
            if not result:
                dec = m.get('decision', 'unknown')
                result = _reject_result(m.get('note')) if dec == 'rejected' else {'status': dec}
            contents.append(types.Content(role='user', parts=[types.Part.from_function_response(
                name=m.get('name', 'update_posting_fields'),
                response=result,
            )]))
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


def _interpret(posting, response):
    """Gemini 응답을 {type:'message'|'tool_request', ...} 로 해석. DB 변경 없음."""
    text_parts, fcall = [], None
    cand = None
    try:
        cand = response.candidates[0]
        parts = cand.content.parts or []
    except (AttributeError, IndexError, TypeError):
        parts = []
    for p in parts:
        if getattr(p, 'function_call', None):
            fcall = p.function_call
        # thinking(thought) 파트는 본문이 아니므로 제외
        elif getattr(p, 'text', None) and not getattr(p, 'thought', False):
            text_parts.append(p.text)
    text = '\n'.join(text_parts).strip()
    try:
        fr = str(cand.finish_reason or '') if cand else ''
    except Exception:  # noqa: BLE001
        fr = ''
    print(f'[agent INTERPRET] parts={len(parts)} fcall={bool(fcall)} '
          f'finish={fr} text_len={len(text)}')
    # SDK 의 통합 text 프로퍼티로 한 번 더 보강(파트 구조가 달라도 안전)
    if not text and not fcall:
        try:
            text = (response.text or '').strip()
        except Exception:  # noqa: BLE001
            text = ''

    if fcall is not None:
        args = _plain(fcall.args) if fcall.args else {}
        updates = args.get('updates') or []
        updates = [u for u in (_plain(u) for u in updates) if isinstance(u, dict)]
        diff = build_diff(posting, updates)
        print(f'[agent INTERPRET] fcall updates={updates} '
              f'changed={[d["field"] for d in diff if d.get("changed")]}')
        # 실제로 바뀌는 필드가 있을 때만 도구 제안. 빈 호출이나 현재값과 동일한 호출은 일반 답변으로 처리.
        if any(d.get('changed') for d in diff):
            return {
                'type': 'tool_request',
                'text': text,
                'tool_call': {
                    'id': uuid.uuid4().hex[:12],
                    'name': fcall.name or 'update_posting_fields',
                    'args': {'updates': updates},
                    'diff': diff,
                },
            }
        return {'type': 'message', 'reply': text or '검토 결과, 본문과 일치하여 수정할 필드가 없습니다.'}
    if text:
        return {'type': 'message', 'reply': text}
    return {'type': 'message', 'reply': _empty_reason(response, cand)}


# ── diff / 적용 ──

def build_diff(posting, updates):
    """제안값을 현재값과 대비한 diff(권한 박스 렌더용). DB 변경 없음."""
    diff = []
    for u in updates:
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


def apply_update(posting, updates):
    """수정안을 실제 DB에 반영(승인된 경우에만 호출). 반환 [{field,label,old,new}]."""
    applied = []
    for u in updates:
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
    if applied:
        posting.save()
    return applied


# ── 턴 진행 ──

def propose_turn(posting, messages, client, model_name):
    """한 턴 진행. tool_request(제안) 또는 message 반환. DB 변경 없음."""
    response = _generate(client, model_name, posting, build_contents(messages))
    return _interpret(posting, response)


def _reject_result(note):
    """거부 결과(function_response). 사용자가 방향을 적었으면 그 지시를 함께 전달."""
    note = (note or '').strip()
    if note:
        return {'status': 'rejected', 'user_instruction': note}
    return {'status': 'rejected', 'note': '사용자가 이 수정 제안을 거부했습니다.'}


def apply_turn(posting, messages, tool_call, decision, client, model_name, note=''):
    """권한 박스 결정 처리. 승인 시에만 DB 변경 후 모델 후속 응답을 받아 반환.

    거부 시 note 가 있으면 사용자의 수정 방향을 모델에 바로 전달해, 사유를 되묻는
    중간 단계 없이 대안을 제시하도록 한다.
    messages 는 모델 tool_call 턴까지 포함하고 그 뒤 function_response 는 아직 없는 상태여야 한다.
    반환: _interpret 결과 + {'applied': [...]}.
    """
    if decision == 'approved':
        updates = (tool_call.get('args') or {}).get('updates') or []
        applied = apply_update(posting, updates)
        result = {'status': 'applied', 'applied_count': len(applied)}
    else:
        applied = []
        result = _reject_result(note)

    contents = build_contents(messages)
    contents.append(types.Content(role='user', parts=[types.Part.from_function_response(
        name=tool_call.get('name', 'update_posting_fields'),
        response=result,
    )]))
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
