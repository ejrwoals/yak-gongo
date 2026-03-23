"""
통계 차트 생성 함수들.
각 함수는 ORM으로 데이터를 쿼리한 뒤 matplotlib으로 차트를 그리고,
base64 인코딩된 PNG 문자열을 반환한다.
"""
import io
import base64

import matplotlib
matplotlib.use('Agg')  # headless 환경 (웹 서버)에서 필요
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

from django.db.models import Count, Avg, F

from postings.models import JobPosting

# ── 한글 폰트 설정 ──────────────────────────────────────────────────
# macOS 기본 한글 폰트 (AppleGothic) 사용. 없으면 기본 폰트로 폴백.
def _setup_korean_font():
    korean_fonts = ['AppleGothic', 'NanumGothic', 'Malgun Gothic', 'UnDotum']
    available = {f.name for f in fm.fontManager.ttflist}
    for font in korean_fonts:
        if font in available:
            plt.rcParams['font.family'] = font
            break
    plt.rcParams['axes.unicode_minus'] = False

_setup_korean_font()

REGION_ORDER = ['서울', '인천', '경기 중부', '경기 외곽', '지방']
REGION_COLORS = {
    '서울': '#4472C4',
    '인천': '#ED7D31',
    '경기 중부': '#A9D18E',
    '경기 외곽': '#FFD966',
    '지방': '#9DC3E6',
}


def _fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return encoded


def chart_postings_by_region() -> str:
    """지역 대분류별 공고 수 막대 그래프."""
    qs = (
        JobPosting.objects
        .values('big_category')
        .annotate(count=Count('id'))
    )
    data = {row['big_category']: row['count'] for row in qs}

    labels = [r for r in REGION_ORDER if r in data]
    counts = [data[r] for r in labels]
    colors = [REGION_COLORS.get(r, '#cccccc') for r in labels]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, counts, color=colors)
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                f'{count}개', ha='center', va='bottom', fontsize=11)
    ax.set_title('구인 공고수 - 지역 대분류 별\n', fontsize=16, fontweight='bold')
    ax.set_xlabel('\n지역 대분류')
    ax.set_ylabel('공고 수\n')
    ax.set_ylim(0, max(counts) * 1.12 if counts else 10)
    fig.tight_layout()
    return _fig_to_base64(fig)


def chart_one_time_vs_continuous() -> str:
    """일회성 vs 지속성 근무 공고 수 막대 그래프."""
    total = JobPosting.objects.count()
    one_time = JobPosting.objects.filter(is_one_time_work=True).count()
    continuous = JobPosting.objects.filter(is_one_time_work=False).count()
    unknown = total - one_time - continuous

    labels, counts = [], []
    if continuous:
        labels.append('지속성 근무')
        counts.append(continuous)
    if one_time:
        labels.append('일회성 근무')
        counts.append(one_time)
    if unknown:
        labels.append('미분류')
        counts.append(unknown)

    fig, ax = plt.subplots(figsize=(5, 5))
    bars = ax.bar(labels, counts, color=['#4472C4', '#ED7D31', '#aaaaaa'][:len(labels)])
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f'{count}개', ha='center', va='bottom', fontsize=11)
    ax.set_title('구인 공고수 - 일회성 vs 지속성 근무', fontsize=14, fontweight='bold')
    ax.set_ylabel('공고 수\n')
    ax.set_ylim(0, max(counts) * 1.12 if counts else 10)
    fig.tight_layout()
    return _fig_to_base64(fig)


def chart_hours_per_week_histogram() -> str:
    """주당 근무 시간 히스토그램 (지속성 근무 전체)."""
    hours = list(
        JobPosting.objects
        .filter(is_one_time_work=False, hours_per_week__isnull=False)
        .values_list('hours_per_week', flat=True)
    )
    if not hours:
        return ''

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(hours, bins=30, color='#4472C4', edgecolor='white', alpha=0.8)
    ax.axvline(np.mean(hours), color='red', linestyle='--', linewidth=1.5,
               label=f'평균 {np.mean(hours):.1f}h')
    ax.set_title('주당 근무 시간 Histogram\n', fontsize=16, fontweight='bold')
    ax.set_xlabel('\n주당 근무 시간 (시간)')
    ax.set_ylabel('공고 수\n')
    ax.legend()
    fig.tight_layout()
    return _fig_to_base64(fig)


def chart_weekend_hourly_wage_by_region() -> str:
    """지역별 주말 파트 시급 bubble chart."""
    qs = list(
        JobPosting.objects
        .filter(
            is_one_time_work=False,
            weekend_work_days__gt=0,
            weekday_work_days=0,
            net_hourly_wage__isnull=False,
            big_category__in=REGION_ORDER,
        )
        .values('big_category', 'net_hourly_wage')
    )
    if not qs:
        return ''

    import pandas as pd
    df = pd.DataFrame(qs)
    df['net_hourly_wage'] = df['net_hourly_wage'].round(1)

    grouped = df.groupby(['big_category', 'net_hourly_wage']).size().reset_index(name='count')
    means = df.groupby('big_category')['net_hourly_wage'].mean()
    ns = df.groupby('big_category')['net_hourly_wage'].count()

    # categorical order
    cat_type = pd.CategoricalDtype(REGION_ORDER, ordered=True)
    grouped['big_category'] = grouped['big_category'].astype(cat_type)
    grouped = grouped.sort_values('big_category')

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(grouped['big_category'].astype(str), grouped['net_hourly_wage'],
               s=grouped['count'] * 50, color='black', alpha=0.2)
    for i, row in grouped.iterrows():
        ax.text(str(row['big_category']), row['net_hourly_wage'], str(row['count']),
                ha='center', va='center', fontsize=10)

    for region in means.index:
        if region in REGION_ORDER:
            ax.plot(region, means[region], 'rs', markersize=8)
            ax.text(region, means[region], f'  {means[region]:.2f}', fontsize=12,
                    ha='left', color='red')
            y_min = df['net_hourly_wage'].min()
            ax.text(region, y_min - 0.15, f'n={ns[region]}', ha='center', fontsize=10)

    ax.set_title('주말(토,일) 파트 시급\n', fontsize=16, fontweight='bold')
    ax.set_xlabel('\n지역 대분류')
    ax.set_ylabel('시급(단위 : 만원)\n')
    y_range = df['net_hourly_wage'].max() - df['net_hourly_wage'].min()
    ax.set_ylim(df['net_hourly_wage'].min() - 0.3, df['net_hourly_wage'].max() + 0.3)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _fig_to_base64(fig)


def chart_fulltime_hourly_wage_by_region() -> str:
    """지역별 풀타임 시급 bubble chart."""
    qs = list(
        JobPosting.objects
        .filter(
            is_one_time_work=False,
            weekday_work_days__gte=4,
            net_hourly_wage__isnull=False,
            big_category__in=REGION_ORDER,
        )
        .values('big_category', 'net_hourly_wage')
    )
    if not qs:
        return ''

    import pandas as pd
    df = pd.DataFrame(qs)
    df['net_hourly_wage'] = df['net_hourly_wage'].round(1)

    grouped = df.groupby(['big_category', 'net_hourly_wage']).size().reset_index(name='count')
    means = df.groupby('big_category')['net_hourly_wage'].mean()
    ns = df.groupby('big_category')['net_hourly_wage'].count()

    cat_type = pd.CategoricalDtype(REGION_ORDER, ordered=True)
    grouped['big_category'] = grouped['big_category'].astype(cat_type)
    grouped = grouped.sort_values('big_category')

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(grouped['big_category'].astype(str), grouped['net_hourly_wage'],
               s=grouped['count'] * 50, color='black', alpha=0.2)
    for i, row in grouped.iterrows():
        ax.text(str(row['big_category']), row['net_hourly_wage'], str(row['count']),
                ha='center', va='center', fontsize=10)

    for region in means.index:
        if region in REGION_ORDER:
            ax.plot(region, means[region], 'rs', markersize=8)
            ax.text(region, means[region], f'  {means[region]:.2f}', fontsize=12,
                    ha='left', color='red')
            y_min = df['net_hourly_wage'].min()
            ax.text(region, y_min - 0.15, f'n={ns[region]}', ha='center', fontsize=10)

    ax.set_title('풀타임 근무 시급\n', fontsize=16, fontweight='bold')
    ax.set_xlabel('\n지역 대분류')
    ax.set_ylabel('시급(단위 : 만원)\n')
    ax.set_ylim(df['net_hourly_wage'].min() - 0.3, df['net_hourly_wage'].max() + 0.3)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _fig_to_base64(fig)


def get_summary_stats() -> dict:
    """대시보드 상단 요약 수치."""
    from django.db.models import Avg
    total = JobPosting.objects.count()
    continuous = JobPosting.objects.filter(is_one_time_work=False)
    weekend = continuous.filter(weekend_work_days__gt=0, weekday_work_days=0)
    fulltime = continuous.filter(weekday_work_days__gte=4)

    return {
        'total': total,
        'continuous_count': continuous.count(),
        'one_time_count': JobPosting.objects.filter(is_one_time_work=True).count(),
        'weekend_mean_wage': weekend.aggregate(v=Avg('net_hourly_wage'))['v'],
        'fulltime_mean_wage': fulltime.aggregate(v=Avg('net_hourly_wage'))['v'],
    }
