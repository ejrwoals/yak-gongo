"""
LLM 파이프라인 Task 1~5 실행 함수.
Primary pipeline: Google Gemini API
Error fallback (runner 외부에서 선택): OpenAI GPT-4o
"""
import json
import re

from google import genai
from google.genai import types

from .usage import add_response
from .prompts import (
    QUERY_TASK_1, FEW_SHOT_1,
    QUERY_TASK_2, FEW_SHOT_2,
    QUERY_TASK_3, FEW_SHOT_3,
    QUERY_TASK_4, FEW_SHOT_4,
    QUERY_TASK_5, FEW_SHOT_5,
)


def _call_gemini(query: str, body: str, client: genai.Client, model_name: str,
                 few_shot: str | None = None, usage: dict | None = None) -> str | None:
    """Gemini API 호출 래퍼 (google-genai SDK).

    usage 가 주어지면 응답의 토큰 사용량을 그 accumulator 에 합산한다(과금 추적용).
    """
    if few_shot:
        query = query + '\n예시(few-shot) :\n' + few_shot + '\n'

    prompt = query + body
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        add_response(usage, response)
        return response.text
    except Exception as e:
        print(f'[Gemini ERROR] {e}')
        return None


def extract_json(response: str | None) -> tuple[dict | None, str | None]:
    """LLM 응답 문자열에서 JSON dict를 추출."""
    if not response:
        return None, None

    pattern = re.compile(r'\{.*\}', re.DOTALL)
    match = pattern.search(response)
    if not match:
        return None, None

    json_string = match.group()
    # raw_decode: 첫 번째 유효한 JSON 객체만 파싱하고 뒤의 텍스트는 무시
    # strict=False: 문자열 값 안의 이스케이프되지 않은 제어문자(개행 등)도 허용
    decoder = json.JSONDecoder(strict=False)
    try:
        obj, _ = decoder.raw_decode(json_string)
        return obj, json_string
    except json.JSONDecodeError:
        pass

    # 1차 실패 시에만 JS 스타일 주석 제거 후 재시도.
    # (주석 제거 정규식은 문자열 값 안의 '//'(예: 근무 표기 '토,일 // 월')도 지워
    #  멀쩡한 응답을 깨뜨리므로, 정상 파싱이 안 될 때의 폴백으로만 적용한다.)
    stripped = re.sub(r'//.*?(?=\n)|/\*.*?\*/', '', json_string, flags=re.S)
    try:
        obj, _ = decoder.raw_decode(stripped)
        return obj, stripped
    except json.JSONDecodeError as e:
        print(f'[JSON PARSE ERROR] {e}\n{json_string[:200]}')
        return None, json_string


def run_task_1(body: str, client: genai.Client, model_name: str, usage: dict | None = None) -> dict | None:
    """Task 1: 급여 정보 및 일회성 근무 여부 추출."""
    raw = _call_gemini(QUERY_TASK_1, body, client, model_name, FEW_SHOT_1, usage)
    result, _ = extract_json(raw)
    return result


def run_task_2(body: str, client: genai.Client, model_name: str, usage: dict | None = None) -> dict | None:
    """Task 2: 일회성 근무 출퇴근 시각 및 시급 계산."""
    raw = _call_gemini(QUERY_TASK_2, body, client, model_name, FEW_SHOT_2, usage)
    result, _ = extract_json(raw)
    return result


def run_task_3(body: str, client: genai.Client, model_name: str, usage: dict | None = None) -> dict | None:
    """Task 3: 지속성 근무 출퇴근 시각 추출."""
    raw = _call_gemini(QUERY_TASK_3, body, client, model_name, FEW_SHOT_3, usage)
    result, _ = extract_json(raw)
    return result


def run_task_4(body: str, task3_result: dict, client: genai.Client, model_name: str, usage: dict | None = None) -> dict | None:
    """Task 4: Task 3 결과물을 비판적으로 검토하여 수정."""
    prev_json_str = json.dumps(task3_result, ensure_ascii=False, indent=2)
    query = QUERY_TASK_4.format(prev_json_str)
    raw = _call_gemini(query, body, client, model_name, FEW_SHOT_4, usage)
    result, _ = extract_json(raw)
    return result


def run_task_5(body: str, client: genai.Client, model_name: str, usage: dict | None = None) -> dict | None:
    """Task 5: 복리후생 정보 추출 (월차, 경력 요구, 식사 관련)."""
    raw = _call_gemini(QUERY_TASK_5, body, client, model_name, FEW_SHOT_5, usage)
    result, _ = extract_json(raw)
    return result
