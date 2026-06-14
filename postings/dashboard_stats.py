"""웹 대시보드용 통계 계산.

`one_click_statistics`(노션 차트 생성기)와 동일한 필터·정의를 사용하되,
matplotlib/노션 의존성 없이 프론트엔드가 필요로 하는 수치·데이터셋만 산출한다.
결과 dict가 DashboardSnapshot.data로 저장되어 웹 페이지에 그대로 임베드된다.

정의(노션 코드와 일치):
- 풀타임      : 시간/week >= 36 & 일회성 근무 여부 == 'No'
- 주말 파트   : 일회성 'No' & 주말 근무 일수 != 0 & 평일 근무 일수 == 0
- 기타 파트   : 일회성 'No' & 시간/week < 36 & (주말 파트 아님)
- 일회성 단기 : 일회성 근무 여부 == 'Yes'  (시급 = '일회성 근무 시급')
- 지역 5분류  : '지역 대분류'  = 서울 / 인천 / 경기 중부 / 경기 외곽 / 지방
- 퇴직금 보정 : 시급 × 13/12  (1년 근무 시 1개월분 퇴직금)
"""
import numpy as np
import pandas as pd

REGION_ORDER = ['서울', '인천', '경기 중부', '경기 외곽', '지방']
WAGE = '시급(엄밀히)'        # 지속성 근무 세후 시급 (만원)
ONE_TIME_WAGE = '일회성 근무 시급'
HOURS = '시간/week'
SALARY = '세후 월급'        # 세후 월급 (만원)


def _num(x):
    """numpy/pandas 스칼라를 JSON 직렬화 가능한 float/None으로."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), 4)


def _normalized_wage(df: pd.DataFrame) -> pd.Series:
    """일회성 공고는 '일회성 근무 시급'을, 그 외는 '시급(엄밀히)'를 쓴 통합 시급 컬럼."""
    wage = df[WAGE].copy()
    one_time = df['일회성 근무 여부'] == 'Yes'
    wage.loc[one_time] = df.loc[one_time, ONE_TIME_WAGE]
    return wage


def _fulltime(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df['일회성 근무 여부'] == 'No') & (df[HOURS] >= 36)].copy()


def _weekend(df: pd.DataFrame) -> pd.DataFrame:
    long = df[df['일회성 근무 여부'] == 'No']
    return long[(long['주말 근무 일수'] != 0) & (long['평일 근무 일수'] == 0)].copy()


def _etc_part(df: pd.DataFrame) -> pd.DataFrame:
    long = df[(df['일회성 근무 여부'] == 'No') & (df[HOURS] < 36)]
    return long[~((long['주말 근무 일수'] != 0) & (long['평일 근무 일수'] == 0))].copy()


def _region_means(df: pd.DataFrame, wage_col: str = WAGE):
    """지역 대분류별 평균 시급 + n수. REGION_ORDER 순서로 [{nm, mn, n}] 반환."""
    sub = df.dropna(subset=[wage_col])
    grouped = sub.groupby('지역 대분류', observed=True)[wage_col]
    means, counts = grouped.mean(), grouped.count()
    out = []
    for nm in REGION_ORDER:
        if nm in means.index and counts.get(nm, 0) > 0:
            out.append({'nm': nm, 'mn': _num(means[nm]), 'n': int(counts[nm])})
    return out


def _region_dist(df: pd.DataFrame, wage_col: str = WAGE):
    """지역 대분류별 분포: 평균·n수 + 실제 시급 값 배열(vals). 분포/IQR 차트 입력."""
    sub = df.dropna(subset=[wage_col])
    out = []
    for nm in REGION_ORDER:
        vals = sub.loc[sub['지역 대분류'] == nm, wage_col]
        if len(vals) == 0:
            continue
        out.append({
            'nm': nm,
            'mn': _num(vals.mean()),
            'n': int(len(vals)),
            'vals': [round(float(v), 3) for v in vals],
        })
    return out


def _histogram(df: pd.DataFrame):
    """정수 시간으로 반올림한 주당 근무시간 히스토그램: [[시간, 공고수], …] (시간 오름차순)."""
    hrs = df.dropna(subset=[HOURS])[HOURS].round().astype(int)
    freq = hrs.value_counts().sort_index()
    return [[int(h), int(c)] for h, c in freq.items()]


def _regression(x: pd.Series, y: pd.Series):
    """1차 회귀 slope/intercept. 점이 2개 미만이면 None."""
    mask = x.notna() & y.notna()
    if mask.sum() < 2:
        return None
    slope, intercept = np.polyfit(x[mask].astype(float), y[mask].astype(float), 1)
    return {'slope': round(float(slope), 6), 'intercept': round(float(intercept), 6)}


def _int_histogram(df: pd.DataFrame):
    """주당 근무시간 정수 절삭 히스토그램: [[시간, 공고수], …] (노션 astype(int)와 동일)."""
    hh = df.dropna(subset=[HOURS]).copy()
    hh['_hr'] = hh[HOURS].astype(int)
    return [[int(h), int(c)] for h, c in hh['_hr'].value_counts().sort_index().items()]


def _bubble(df: pd.DataFrame, wage_col: str = WAGE):
    """시급 0.1단위 반올림 후 (지역, 시급)별 공고 수: [{region, y, count}] (버블 차트 입력)."""
    sub = df.dropna(subset=[wage_col]).copy()
    sub['_w'] = sub[wage_col].round(1)
    grouped = sub.groupby(['지역 대분류', '_w'], observed=True).size()
    return [
        {'region': reg, 'y': round(float(w), 1), 'count': int(c)}
        for (reg, w), c in grouped.items() if reg in REGION_ORDER
    ]


def _weekend_section(df: pd.DataFrame) -> dict:
    """주말 파트 페이지 데이터. 노션 '주말 파트' 차트들과 동일한 정의.

    - 히스토그램 : 주말 공고의 주당 근무시간(정수 절삭) 분포
    - 등록일별 산점도 : x=등록일, y=시급, 지역색 + 평균선
    - 버블(원형) 차트 : (지역 대분류, 시급 0.1단위) 셀별 공고 수
    """
    wk = _weekend(df)

    # 등록일별 산점도: 시급·등록일 있는 공고
    ds_df = wk.dropna(subset=[WAGE, '등록일'])
    date_scatter = [{
        'date': (d.isoformat() if hasattr(d, 'isoformat') else str(d)),
        'y': round(float(w), 3),
        'region': (reg if reg in REGION_ORDER else '지방'),
    } for d, w, reg in zip(ds_df['등록일'], ds_df[WAGE], ds_df['지역 대분류'])]

    return {
        'avgWage': _mean_or_none(wk[WAGE]),
        'count': int(len(wk)),
        'hist': _int_histogram(wk),
        'dateScatter': date_scatter,
        'regionMeans': _region_means(wk),
        'bubble': _bubble(wk),
    }


def _etc_section(df: pd.DataFrame) -> dict:
    """기타 파트 페이지 데이터. 노션 '그 외 기타 파트' 차트들과 동일한 정의.

    - 히스토그램 : 기타 파트 공고의 주당 근무시간(정수 절삭) 분포
    - 시급/월급 산점도 : x=주당 근무시간, y=시급·월급 + 회귀선 (지역색 옵션)
    - 버블(원형) 차트 : (지역 대분류, 시급 0.1단위) 셀별 공고 수
    """
    etc = _etc_part(df)
    pts_df = etc.dropna(subset=[HOURS, WAGE])
    pts = [{
        'x': round(float(h), 2),
        'y': round(float(w), 3),
        'month': (None if pd.isna(m) else round(float(m), 1)),
        'region': (reg if reg in REGION_ORDER else '지방'),
    } for h, w, m, reg in zip(pts_df[HOURS], pts_df[WAGE], pts_df[SALARY], pts_df['지역 대분류'])]

    return {
        'avgWage': _mean_or_none(etc[WAGE]),
        'count': int(len(etc)),
        'hist': _int_histogram(etc),
        'pts': pts,
        'regression': {
            'wage': _regression(pts_df[HOURS], pts_df[WAGE]),
            'month': _regression(pts_df[HOURS], pts_df[SALARY]),
        },
        'regionMeans': _region_means(etc),
        'bubble': _bubble(etc),
    }


def _onetime_section(df: pd.DataFrame) -> dict:
    """일회성 단기 페이지 데이터. 노션 '일회성 단기 근무' 차트들과 동일한 정의.

    - 시급 컬럼은 '일회성 근무 시급' (지속성 시급이 아님)
    - 등록일별 산점도 + 버블(원형) 차트 + 장기 vs 일회성 IQR 비교
    """
    ot = df[df['일회성 근무 여부'] == 'Yes'].copy()
    W = ONE_TIME_WAGE

    ds_df = ot.dropna(subset=[W, '등록일'])
    date_scatter = [{
        'date': (d.isoformat() if hasattr(d, 'isoformat') else str(d)),
        'y': round(float(w), 3),
        'region': (reg if reg in REGION_ORDER else '지방'),
    } for d, w, reg in zip(ds_df['등록일'], ds_df[W], ds_df['지역 대분류'])]

    region_means = _region_means(ot, W)

    # 장기 근무(지속성, 시급엄밀히) vs 일회성 단기(일회성 시급) 분포 비교 (IQR strip)
    cont = df[df['일회성 근무 여부'] == 'No'][WAGE].dropna()
    onetime = ot[W].dropna()
    comparison = [
        {'nm': '장기 근무', 'mn': _num(cont.mean()), 'n': int(len(cont)),
         'vals': [round(float(v), 3) for v in cont]},
        {'nm': '일회성 단기 근무', 'mn': _num(onetime.mean()), 'n': int(len(onetime)),
         'vals': [round(float(v), 3) for v in onetime]},
    ]

    return {
        'avgWage': _mean_or_none(ot[W]),
        'totalCount': int(len(df)),
        'count': int(len(ot)),
        'dateScatter': date_scatter,
        'regionMeans': region_means,
        'bubble': _bubble(ot, W),
        'comparison': comparison,
    }


def _mean_or_none(series):
    s = series.dropna()
    return _num(s.mean()) if len(s) else None


def compute_dashboard_data(df: pd.DataFrame) -> dict:
    """전체 DataFrame → 대시보드 JSON payload (home + fulltime)."""
    full = _fulltime(df)
    weekend = _weekend(df)
    etc = _etc_part(df)
    one_time = df[df['일회성 근무 여부'] == 'Yes']

    norm_wage = _normalized_wage(df)

    # ---- 카테고리별 평균 시급 (만원) ----
    def _mean(series):
        s = series.dropna()
        return _num(s.mean()) if len(s) else None

    category_avg = [
        {'name': '전국 평균', 'v': _mean(norm_wage)},
        {'name': '풀타임', 'v': _mean(full[WAGE])},
        {'name': '주말 파트', 'v': _mean(weekend[WAGE])},
        {'name': '기타 파트', 'v': _mean(etc[WAGE])},
        {'name': '일회성 단기', 'v': _mean(one_time[ONE_TIME_WAGE])},
    ]

    # ---- 홈: 지역별(5분류) 평균 시급 (일회성 통합 시급 기준) ----
    df_norm = df.copy()
    df_norm[WAGE] = norm_wage
    home_region_avg = [
        {'name': r['nm'], 'v': r['mn']} for r in _region_means(df_norm)
    ]

    # ---- 풀타임 산점도: 실제 공고별 점 ----
    full_pts_df = full.dropna(subset=[HOURS, WAGE])
    pts = [{
        'x': round(float(h), 2),
        'y': round(float(w), 3),
        'month': (None if pd.isna(m) else round(float(m), 1)),
        'region': (reg if reg in REGION_ORDER else '지방'),
    } for h, w, m, reg in zip(
        full_pts_df[HOURS], full_pts_df[WAGE], full_pts_df[SALARY], full_pts_df['지역 대분류']
    )]

    # ---- 퇴직금 보정 풀타임 (시급 × 13/12) ----
    full_sev = full.copy()
    full_sev[WAGE] = full_sev[WAGE] * 13 / 12

    # ---- 전체(파트+풀타임) 히스토그램·산점도 (참고 토글) ----
    long = df[df['일회성 근무 여부'] == 'No']
    full_hist_df = long.dropna(subset=[HOURS])
    fh_freq = full_hist_df[HOURS].round().astype(int)
    fh_freq = fh_freq[(fh_freq >= 1) & (fh_freq <= 60)].value_counts()
    full_hist = [int(fh_freq.get(hr, 0)) for hr in range(1, 61)]

    full_scatter_df = long.dropna(subset=[HOURS, WAGE])
    full_scatter_pts = [
        {'x': round(float(h), 2), 'y': round(float(w), 3)}
        for h, w in zip(full_scatter_df[HOURS], full_scatter_df[WAGE])
    ]

    fulltime = {
        'avgWage': _mean(full[WAGE]),
        'count': int(len(full)),
        'hist': _histogram(full),
        'pts': pts,
        'regression': {
            'wage': _regression(full_pts_df[HOURS], full_pts_df[WAGE]),
            'month': _regression(full_pts_df[HOURS], full_pts_df[SALARY]),
        },
        'regionMeans': _region_means(full),
        'regionMeansSev': _region_means(full_sev),
        'dist': _region_dist(full),
        'distSev': _region_dist(full_sev),
        'fullHist': full_hist,
        'fullPts': full_scatter_pts,
        'fullRegression': _regression(full_scatter_df[HOURS], full_scatter_df[WAGE]),
    }

    return {
        'home': {
            'totalPostings': int(len(df)),
            'categoryAvg': category_avg,
            'regionAvg': home_region_avg,
        },
        'fulltime': fulltime,
        'weekend': _weekend_section(df),
        'etc': _etc_section(df),
        'onetime': _onetime_section(df),
    }
