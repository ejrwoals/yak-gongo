"""
단일 공고를 처리하는 파이프라인 오케스트레이터.

사용 예:
    from google import genai
    from django.conf import settings

    client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    result = process_posting(body, client, model_name=settings.LLM_MODEL)
"""
from google import genai

from .tasks import run_task_1, run_task_2, run_task_3, run_task_4, run_task_5
from .validator import error_check
from .salary import to_net_salary


def process_posting(body: str, client: genai.Client, model_name: str = '') -> dict:
    """
    공고 본문을 LLM 5-task 파이프라인으로 처리하여 구조화된 결과를 반환.

    Returns:
        dict with keys matching JobPosting model fields.
        has_error=True if any task failed or validation found issues.
    """
    result = {
        'llm_model': model_name,
        'gpt_summary': '',
        'gpt_output_log': '',
        'gpt_error_log': '',
        'has_error': False,
        # salary
        'is_salary_disclosed': None,
        'is_one_time_work': None,
        'one_time_hourly_wage': None,
        'wage_type': '',
        'wage_raw': None,
        'hourly_wage': None,
        'net_salary': None,
        # schedule
        'weekday_work_days': None,
        'weekday_start_time': None,
        'weekday_end_time': None,
        'weekend_work_days': None,
        'weekend_start_time': None,
        'weekend_end_time': None,
        'hours_per_week': None,
        'hours_per_month': None,
        # benefits
        'monthly_leave': '',
        'experience_required': '',
        'meal_info': '',
    }

    error_history = ''

    # ── Task 1: 급여 & 일회성 근무 여부 ─────────────────────────
    t1 = run_task_1(body, client, model_name)
    if not t1:
        result['has_error'] = True
        result['gpt_error_log'] = '[Task1 FAIL] LLM 응답 없음 또는 JSON 파싱 실패'
        return result

    is_salary = t1.get('공고에 급여 명시 여부', False)
    is_one_time = t1.get('일회성 근무 여부', False)
    is_after_tax = t1.get('세후 금액 여부', True)
    wage_type = t1.get('급여 유형') or ''
    wage = t1.get('급여')

    result['is_salary_disclosed'] = bool(is_salary)
    result['is_one_time_work'] = bool(is_one_time)
    result['wage_type'] = str(wage_type) if wage_type else ''
    result['wage_raw'] = wage
    result['gpt_output_log'] += f'[T1] {t1}\n'

    # ── Task 2 또는 Task 3+4 분기 ────────────────────────────────
    if is_one_time:
        t2 = run_task_2(body, client, model_name)
        if t2:
            result['one_time_hourly_wage'] = t2.get('일회성 근무 시급')
            result['gpt_output_log'] += f'[T2] {t2}\n'

            check_dict = {
                '급여': wage,
                '시급': None,
                '일회성 근무 시급': result['one_time_hourly_wage'],
                '일회성 근무 여부': True,
            }
            error_history, _, _ = error_check(check_dict, error_history)
        else:
            error_history += '[Task2 FAIL] LLM 응답 없음\n'

    else:
        # Task 3: 지속성 근무 출퇴근 시각
        t3 = run_task_3(body, client, model_name)
        if not t3:
            error_history += '[Task3 FAIL] LLM 응답 없음\n'
            t3 = {}

        result['gpt_output_log'] += f'[T3] {t3}\n'

        # Task 4: Task3 결과 검토
        t4 = run_task_4(body, t3, client, model_name)
        final = t4 if t4 else t3
        result['gpt_output_log'] += f'[T4] {final}\n'

        result['weekday_work_days'] = final.get('평일 근무 일수')
        result['weekday_start_time'] = final.get('평일 출근 시각')
        result['weekday_end_time'] = final.get('평일 퇴근 시각')
        result['weekend_work_days'] = final.get('주말 근무 일수')
        result['weekend_start_time'] = final.get('주말 출근 시각')
        result['weekend_end_time'] = final.get('주말 퇴근 시각')

        check_dict = {
            '급여': wage,
            '시급': None,
            '급여 유형': wage_type,
            '일회성 근무 여부': False,
            '평일 근무 일수': result['weekday_work_days'],
            '평일 출근 시각': result['weekday_start_time'],
            '평일 퇴근 시각': result['weekday_end_time'],
            '주말 근무 일수': result['weekend_work_days'],
            '주말 출근 시각': result['weekend_start_time'],
            '주말 퇴근 시각': result['weekend_end_time'],
            '주당 총 근무 시간': None,
            '월 총 근무 시간': None,
            '평일 총 근무 시간': None,
            '주말 총 근무 시간': None,
        }
        error_history, hours_per_week, hourly_wage = error_check(check_dict, error_history)

        result['hours_per_week'] = hours_per_week
        result['hours_per_month'] = hours_per_week * 4.34 if hours_per_week else None
        result['hourly_wage'] = hourly_wage

        # 세후 월급 계산
        if is_salary and isinstance(wage, (int, float)) and result['hours_per_month']:
            try:
                wt = str(wage_type).lower() if wage_type else ''
                if wt in ('monthly', 'monthly wage', '월급', ''):
                    monthly_gross = wage
                elif wt in ('yearly', 'annual', 'annual salary', 'yearly salary', '연봉'):
                    monthly_gross = wage / 12
                else:
                    monthly_gross = hourly_wage * result['hours_per_month'] if hourly_wage else None

                if monthly_gross is not None:
                    result['net_salary'] = to_net_salary(monthly_gross, bool(is_after_tax))
            except Exception:
                pass

    # ── Task 5: 복리후생 ─────────────────────────────────────────
    t5 = run_task_5(body, client, model_name)
    if t5:
        result['monthly_leave'] = str(t5.get('월차') or '')
        result['experience_required'] = str(t5.get('경력 요구') or '')
        result['meal_info'] = str(t5.get('식사 관련') or '')
        result['gpt_output_log'] += f'[T5] {t5}\n'

    # 요약문 생성
    hw = result.get('hourly_wage')
    result['gpt_summary'] = (
        f"급여{'명시' if result['is_salary_disclosed'] else '미명시'} | "
        f"{'일회성' if result['is_one_time_work'] else '지속성'}"
        + (f" | 시급 {hw:.2f}만원" if hw else '')
    )

    if error_history:
        result['gpt_error_log'] = error_history
        result['has_error'] = True

    return result
