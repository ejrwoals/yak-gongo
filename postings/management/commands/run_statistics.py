import sys
import os

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

from postings.models import JobPosting


def build_dataframe() -> pd.DataFrame:
    """Django DB에서 JobPosting 데이터를 읽어 통계 스크립트 호환 형식의 DataFrame으로 변환."""
    qs = JobPosting.objects.values(
        'title', 'created_at', 'platform', 'url', 'pharmacy_name',
        'big_category', 'city', 'experience_required', 'monthly_leave',
        'is_salary_disclosed', 'user_reviewed', 'llm_model',
        'is_one_time_work', 'one_time_hourly_wage', 'net_hourly_wage', 'net_salary',
        'hours_per_week', 'weekday_work_days',
        'weekday_start_time', 'weekday_end_time', 'weekend_work_days',
        'weekend_start_time', 'weekend_end_time',
        'body', 'gpt_summary', 'gpt_output_log', 'user_comment',
    )
    df = pd.DataFrame(list(qs))

    df = df.rename(columns={
        'title':                '공고 제목',
        'created_at':           '등록일',
        'platform':             '플랫폼',
        'url':                  '링크',
        'pharmacy_name':        '약국 명칭',
        'big_category':         '지역 대분류',
        'city':                 '지역',
        'experience_required':  '경력 요구',
        'monthly_leave':        '월차',
        'llm_model':            'LLM model',
        'one_time_hourly_wage': '일회성 근무 시급',
        'net_hourly_wage':      '시급(엄밀히)',
        'net_salary':           '세후 월급',
        'hours_per_week':       '시간/week',
        'weekday_work_days':    '평일 근무 일수',
        'weekday_start_time':   '평일 출근 시각',
        'weekday_end_time':     '평일 퇴근 시각',
        'weekend_work_days':    '주말 근무 일수',
        'weekend_start_time':   '주말 출근 시각',
        'weekend_end_time':     '주말 퇴근 시각',
        'body':                 '본문',
        'gpt_summary':          'GPT 요약문',
        'gpt_output_log':       'GPT 2nd Run',
        'user_comment':         '내 코멘트',
    })

    # Boolean → "Yes"/"No" 문자열 변환 (통계 스크립트가 문자열로 비교함)
    for src_col, dst_col in [
        ('is_salary_disclosed', '공고에 급여 명시 여부'),
        ('is_one_time_work',    '일회성 근무 여부'),
        ('user_reviewed',       '내가 검토시 체크'),
    ]:
        df[dst_col] = df[src_col].map({True: 'Yes', False: 'No', None: None})
    df = df.drop(columns=['is_salary_disclosed', 'is_one_time_work', 'user_reviewed'])

    # 파생 컬럼
    df['주당 근무 일수'] = df['평일 근무 일수'].fillna(0) + df['주말 근무 일수'].fillna(0)

    return df


class Command(BaseCommand):
    help = '통계 차트를 생성하고 Notion 페이지를 업데이트합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default=None,
            help='차트 저장 디렉토리 (기본값: notion-stats/output/)',
        )
        parser.add_argument(
            '--skip-notion',
            action='store_true',
            default=False,
            help='Notion 업로드를 건너뜁니다 (차트만 생성).',
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir'] or str(
            settings.BASE_DIR / 'notion-stats' / 'output'
        )
        os.makedirs(output_dir, exist_ok=True)

        self.stdout.write('DB에서 데이터 로드 중...')
        df = build_dataframe()
        self.stdout.write(f'데이터 로드 완료: {len(df)}개 공고')

        # notion-stats 디렉토리를 sys.path에 추가하여 one_click_statistics 모듈 import
        stats_dir = str(settings.BASE_DIR / 'notion-stats')
        if stats_dir not in sys.path:
            sys.path.insert(0, stats_dir)

        import one_click_statistics as stats_module
        stats_module.run(
            df=df,
            output_dir=output_dir,
            skip_notion=options['skip_notion'],
        )

        self.stdout.write(self.style.SUCCESS('통계 생성 완료!'))
