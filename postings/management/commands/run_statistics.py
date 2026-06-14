import sys
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from postings.dataframe import build_dataframe


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
