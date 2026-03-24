#!/usr/bin/env python
"""
One-time migration: yakkook.json + output_error.json → SQLite (via Django ORM)

Usage:
    python scripts/migrate_json_to_sqlite.py
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Django setup
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from postings.models import JobPosting


def parse_bool(value) -> bool | None:
    """'Yes'/'No'/'TRUE'/'FALSE'/True/False/None → bool or None"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ('yes', 'true', '1', 'o', 'o'):
        return True
    if s in ('no', 'false', '0', 'x'):
        return False
    return None


def parse_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        import math
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def parse_date(value) -> str | None:
    """'2024년 9월 19일' or '2024-09-19' → '2024-09-19' or None"""
    if not value or str(value).strip() in ('', 'nan', 'None'):
        return None
    s = str(value).strip()
    # '2024년 9월 19일' 형식
    if '년' in s:
        try:
            dt = datetime.strptime(s, '%Y년 %m월 %d일')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            try:
                # '2024년 9월 19일' without zero-padding
                import re
                m = re.match(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', s)
                if m:
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            except Exception:
                pass
    # 'YYYY-MM-DD' 형식
    if len(s) == 10 and s[4] == '-':
        return s
    return None


def clean_str(value) -> str:
    if value is None:
        return ''
    s = str(value).strip()
    return '' if s.lower() in ('nan', 'none') else s


def record_to_posting(record: dict, force_error_corrected: bool = False) -> dict:
    """JSON record dict → JobPosting field dict"""
    return dict(
        url=clean_str(record.get('링크')),
        platform=clean_str(record.get('플랫폼')),
        created_at=parse_date(record.get('등록일')),
        title=clean_str(record.get('공고 제목')),
        pharmacy_name=clean_str(record.get('약국 명칭')),
        body=clean_str(record.get('본문')),
        city=clean_str(record.get('지역')),
        big_category=clean_str(record.get('지역 대분류')),
        is_salary_disclosed=parse_bool(record.get('공고에 급여 명시 여부')),
        is_one_time_work=parse_bool(record.get('일회성 근무 여부')),
        one_time_hourly_wage=parse_float(record.get('일회성 근무 시급')),
        wage_raw=None,  # 원본 CSV에 wage_type 별도 컬럼 없음
        wage_type='',
        net_hourly_wage=parse_float(record.get('시급(엄밀히)')),
        net_salary=parse_float(record.get('세후 월급')),
        weekday_work_days=parse_float(record.get('평일 근무 일수')),
        weekday_start_time=parse_float(record.get('평일 출근 시각')),
        weekday_end_time=parse_float(record.get('평일 퇴근 시각')),
        weekend_work_days=parse_float(record.get('주말 근무 일수')),
        weekend_start_time=parse_float(record.get('주말 출근 시각')),
        weekend_end_time=parse_float(record.get('주말 퇴근 시각')),
        hours_per_week=parse_float(record.get('시간/week')),
        hours_per_month=parse_float(record.get('시간/month')),
        monthly_leave=clean_str(record.get('월차')),
        experience_required=clean_str(record.get('경력 요구')),
        meal_info=clean_str(record.get('식사 관련')),
        llm_model=clean_str(record.get('LLM model')),
        gpt_summary=clean_str(record.get('GPT 요약문')),
        gpt_output_log=clean_str(record.get('GPT 2nd Run')),
        gpt_error_log=clean_str(record.get('GPT Error')),
        error_corrected=force_error_corrected or parse_bool(record.get('Error 교정 작업')) or False,
        user_reviewed=parse_bool(record.get('내가 검토시 체크')) or False,
        user_comment=clean_str(record.get('내 코멘트')),
    )


def load_json(path: Path) -> list[dict]:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def migrate(json_path: Path, force_error_corrected: bool = False) -> tuple[int, int]:
    """Returns (inserted, skipped) counts."""
    records = load_json(json_path)
    inserted = skipped = 0

    for record in records:
        fields = record_to_posting(record, force_error_corrected=force_error_corrected)
        url = fields.pop('url')
        if not url:
            skipped += 1
            continue

        _, created = JobPosting.objects.get_or_create(url=url, defaults=fields)
        if created:
            inserted += 1
        else:
            skipped += 1

    return inserted, skipped


if __name__ == '__main__':
    data_dir = BASE_DIR / 'data'

    print('=== yakkook.json 마이그레이션 ===')
    ins, skip = migrate(data_dir / 'yakkook.json')
    print(f'  삽입: {ins}  /  스킵(중복): {skip}')

    print('\n=== output_error.json 마이그레이션 ===')
    ins, skip = migrate(data_dir / 'output_error.json', force_error_corrected=True)
    print(f'  삽입: {ins}  /  스킵(중복): {skip}')

    total = JobPosting.objects.count()
    print(f'\n총 DB 레코드: {total}')
