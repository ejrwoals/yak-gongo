from django.shortcuts import render

from .charts import (
    chart_postings_by_region,
    chart_one_time_vs_continuous,
    chart_hours_per_week_histogram,
    chart_weekend_hourly_wage_by_region,
    chart_fulltime_hourly_wage_by_region,
    get_summary_stats,
)


def dashboard(request):
    context = {
        'stats': get_summary_stats(),
        'chart_region': chart_postings_by_region(),
        'chart_one_time': chart_one_time_vs_continuous(),
        'chart_hours': chart_hours_per_week_histogram(),
        'chart_weekend_wage': chart_weekend_hourly_wage_by_region(),
        'chart_fulltime_wage': chart_fulltime_hourly_wage_by_region(),
    }
    return render(request, 'stats/dashboard.html', context)
