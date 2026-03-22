# 약국 구인공고 분석 시스템 (yak-gongo)

약문약답·팜리크루트 두 플랫폼의 약사 구인공고를 수집하고, Google Gemini LLM으로 급여·근무 일정·복리후생 정보를 자동 추출하여 SQLite에 저장하는 Django 기반 분석 시스템.

## 목적

- **개인 리뷰 워크플로우**: Django Admin에서 LLM 추출 결과를 확인·수정·체크
- **통계 공유**: `/stats/` 페이지에서 시급·지역·근무 유형별 통계를 외부에 공개

---

## 목차

1. [프로젝트 구조](#프로젝트-구조)
2. [초기 설정](#초기-설정)
3. [환경 변수](#환경-변수)
4. [공고 수집 및 처리 (run_pipeline)](#공고-수집-및-처리)
5. [Django Admin 리뷰 워크플로우](#django-admin-리뷰-워크플로우)
6. [통계 대시보드](#통계-대시보드)
7. [모듈별 설명](#모듈별-설명)
8. [LLM 파이프라인 상세](#llm-파이프라인-상세)
9. [데이터 모델](#데이터-모델)
10. [일회성 데이터 마이그레이션](#일회성-데이터-마이그레이션)

---

## 프로젝트 구조

```
yak-gongo/
├── config/                  # Django 프로젝트 설정
│   ├── settings.py
│   └── urls.py
│
├── postings/                # 핵심 앱: 공고 DB + Admin
│   ├── models.py            # JobPosting, PipelineRun
│   ├── admin.py             # Admin 커스터마이징 + 파이프라인 실행 UI
│   ├── forms.py             # PipelineRunForm (Admin 실행 폼)
│   ├── apps.py              # 서버 시작 시 orphan PipelineRun 정리
│   ├── management/commands/
│   │   └── run_pipeline.py  # 수집 + LLM 처리 일괄 실행 명령어
│   └── templates/admin/postings/pipelinerun/
│       ├── change_list.html # 파이프라인 실행 버튼이 추가된 목록
│       ├── run_pipeline.html# 실행 옵션 폼 페이지
│       └── run_log.html     # 실시간 로그 폴링 페이지
│
├── pipeline/                # LLM 파이프라인 (비즈니스 로직)
│   ├── prompts.py           # 5개 task 프롬프트 / few-shot
│   ├── tasks.py             # run_task_1() ~ run_task_5() — Gemini API 호출
│   ├── runner.py            # process_posting() — 단일 공고 오케스트레이터
│   ├── validator.py         # error_check() — LLM 출력 일관성 검증
│   └── salary.py            # to_net_salary() — 세후 월급 계산
│
├── scraper/                 # 웹 스크래퍼 (Selenium)
│   ├── yakdap.py            # 약문약답 스크래퍼
│   └── pharm_recruit.py     # 팜리크루트 스크래퍼 + 지역-URL 매핑
│
├── geo/
│   └── mapping.py           # 주소 → 지역코드, 지역 대분류 변환
│
├── stats/                   # 외부 공개 통계 앱
│   ├── charts.py            # matplotlib 차트 → base64 PNG
│   ├── views.py             # dashboard 뷰
│   ├── urls.py
│   └── templates/stats/
│       └── dashboard.html   # 통계 대시보드 페이지
│
├── scripts/
│   └── migrate_json_to_sqlite.py  # 기존 JSON 데이터 → SQLite (1회성)
│
├── data/
│   └── db.sqlite3           # SQLite DB
│
└── requirements.txt
```

---

## 초기 설정

### 1. Python 환경 생성

[uv](https://github.com/astral-sh/uv)를 사용한다.

```bash
uv venv --python 3.12
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows
```

### 2. 패키지 설치

```bash
uv pip install -r requirements.txt
```

### 3. 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성한다 (아래 [환경 변수](#환경-변수) 참고).

### 4. DB 마이그레이션

```bash
python manage.py migrate
```

`data/db.sqlite3` 파일이 생성된다.

### 5. 관리자 계정 생성

```bash
python manage.py createsuperuser
```

### 6. 서버 실행

```bash
python manage.py runserver
```

- Admin: http://localhost:8000/admin/
- 통계 대시보드: http://localhost:8000/stats/

---

## 환경 변수

프로젝트 루트의 `.env` 파일에 다음 변수를 설정한다.

```dotenv
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# LLM API
GOOGLE_API_KEY=your-google-api-key       # Gemini API (필수)
LLM_MODEL=gemini-1.5-flash-latest        # 사용할 Gemini 모델
OPENAI_API_KEY=your-openai-api-key       # GPT-4o fallback용 (선택)
FALLBACK_LLM_MODEL=gpt-4o
```

**GOOGLE_API_KEY** 발급: [Google AI Studio](https://aistudio.google.com/) → 'Get API key'

---

## 공고 수집 및 처리

`run_pipeline` management command 하나로 스크래핑 → LLM 처리 → DB 저장이 순서대로 실행된다.

### 약문약답 수집

```bash
python manage.py run_pipeline \
    --source yakdap \
    --start-id 38800 \
    --count 100 \
    --step 2 \
    --year 2024
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--start-id` | 탐색 시작 공고 ID | `38800` |
| `--count` | 탐색할 공고 수 | `100` |
| `--step` | ID 증가 간격 | `2` |
| `--year` | 등록일 연도 (약문약답은 월/일만 표시됨) | `2024` |

명령어 실행 시 브라우저가 열리고 카카오 로그인 화면이 나타난다. 로그인을 완료한 뒤 터미널에서 Enter를 누르면 수집이 시작된다.

### 팜리크루트 수집

```bash
python manage.py run_pipeline \
    --source pharm_recruit \
    --big-category 서울
```

`--big-category`에 가능한 값: `서울`, `인천`, `경기 중부`, `경기 외곽`, `지방`

각 대분류에 포함되는 세부 지역은 `scraper/pharm_recruit.py`의 `CITY_URL_DICT`에 정의되어 있다.

### 공통 옵션

| 옵션 | 설명 |
|---|---|
| `--headless` | 브라우저 창 없이 백그라운드 실행 |
| `--dry-run` | 스크래핑만 하고 LLM 처리·DB 저장은 건너뜀 (URL 확인용) |
| `--run-id` | Admin UI에서 미리 생성된 PipelineRun ID (내부용, 수동 사용 불필요) |

### 처리 흐름

```
스크래핑 (Selenium)
    ↓
중복 URL 자동 스킵 (기존 DB와 비교)
    ↓
LLM 파이프라인 (Gemini API, 공고당 최대 5회 호출)
    ├─ Task 1: 급여 유형·금액, 일회성 여부
    ├─ Task 2: 일회성 근무 시급 계산 (일회성인 경우)
    ├─ Task 3: 평일·주말 출퇴근 시각 추출 (지속성인 경우)
    ├─ Task 4: Task 3 결과 검증·수정
    └─ Task 5: 복리후생 (월차, 경력, 식사)
    ↓
validator.error_check(): 주당 근무 시간, 시급 재계산 및 오류 감지
    ↓
salary.to_net_salary(): 세후 월급 산출
    ↓
JobPosting DB 저장
    ↓
PipelineRun 이력 기록
```

---

## Django Admin 리뷰 워크플로우

http://localhost:8000/admin/ 접속 후 사용.

### Admin에서 파이프라인 실행

**Postings > Pipeline runs** 목록 상단의 **파이프라인 실행** 버튼을 클릭하면 브라우저에서 바로 수집 + LLM 처리를 실행할 수 있다.

1. 소스(약문약답/팜리크루트) 선택 및 옵션 입력
2. **실행** 버튼 클릭 → 백그라운드 thread에서 `run_pipeline` 커맨드 실행
3. 자동으로 실시간 로그 페이지(`/log/<id>/`)로 이동하여 진행 상황 확인 (AJAX 폴링)

동시에 하나의 파이프라인만 실행 가능하며, 이미 실행 중인 경우 경고 메시지가 표시된다.

**Admin 커스텀 URL:**

| URL 패턴 | 설명 |
|---|---|
| `pipelinerun/run/` | 파이프라인 실행 폼 페이지 |
| `pipelinerun/log/<id>/` | 실시간 로그 확인 페이지 |
| `pipelinerun/status/<id>/` | AJAX 상태 + 로그 JSON 엔드포인트 |

서버가 재시작되면 `postings/apps.py`에서 비정상 종료된 `running` 상태의 PipelineRun을 자동으로 `failed`로 변경한다.

### 공고 목록 화면

**Postings > Job postings** 클릭.

- **필터** (우측 사이드바): 지역 대분류, 플랫폼, 에러 여부, 검토 여부, 일회성/지속성
- **검색**: 공고 제목, 약국 이름, 지역, URL
- **`검토 완료` 체크박스**: 목록에서 바로 체크·저장 가능 (별도 페이지 이동 불필요)
- **에러 공고 필터링**: `has_error = True`로 필터 → LLM이 의심스럽다고 판단한 공고만 모아서 검토

### 공고 상세 화면

섹션별로 그룹화된 필드:

| 섹션 | 주요 필드 |
|---|---|
| 기본 정보 | 플랫폼, 등록일, 약국 이름, 지역, 지역 대분류 |
| 급여 | 급여 명시 여부, 급여 유형, 원본 급여, 시급, 세후 월급 |
| 근무 일정 | 평일/주말 근무 일수, 출퇴근 시각, 주당·월별 근무 시간 |
| 복리후생 | 월차, 경력 요구, 식사 관련 |
| LLM 결과 | 모델명, 요약문, 상세 로그 (접기/펼치기) |
| 검토 / 품질 | 에러 여부, 에러 교정 완료, 검토 완료, 개인 코멘트 |
| 원문 | 공고 본문 전체 (접기/펼치기) |

**검토 워크플로우 예시:**
1. `has_error=True` 필터로 에러 공고 목록 확인
2. 공고 클릭 → LLM 요약문과 원문 비교
3. 시급이 잘못 계산된 경우 직접 수정
4. `error_corrected` 체크 → `user_reviewed` 체크 → 저장

---

## 통계 대시보드

http://localhost:8000/stats/ 에서 공개용 통계 페이지를 확인할 수 있다.

### 제공 차트

| 차트 | 설명 |
|---|---|
| 지역 대분류별 공고 수 | 서울·인천·경기 중부·경기 외곽·지방 비교 |
| 일회성 vs 지속성 근무 | 근무 유형별 공고 비율 |
| 주당 근무 시간 히스토그램 | 지속성 근무 전체의 근무 시간 분포 |
| 주말 파트 시급 (지역별) | 주말만 근무하는 공고의 지역별 시급 버블 차트 |
| 풀타임 시급 (지역별) | 평일 4일 이상 근무 공고의 지역별 시급 버블 차트 |

상단 요약 수치: 전체 공고 수, 지속성/일회성 건수, 주말 파트·풀타임 평균 시급

---

## 모듈별 설명

### `pipeline/`

| 파일 | 역할 |
|---|---|
| `prompts.py` | `QUERY_TASK_1~5`, `FEW_SHOT_1~5` 상수 — 프롬프트 문자열만 관리 |
| `tasks.py` | `run_task_1()~run_task_5()` — Gemini API 호출 후 JSON 파싱, `extract_json()` 포함 |
| `runner.py` | `process_posting(body, client, model_name, log=None)` — 5개 task 오케스트레이션, `JobPosting` 필드 dict 반환. `log` 콜백을 전달하면 각 단계별 상세 로그를 받을 수 있음 |
| `validator.py` | `error_check(d, error_history)` — 시급·근무 시간 일관성 검증, 주당 근무 시간·시급 재계산 |
| `salary.py` | `to_net_salary(wage, is_after_tax)` — 세전이면 2차 회귀 공식으로 세후 변환 |

**직접 사용 예시:**

```python
from google import genai
from django.conf import settings
from pipeline.runner import process_posting

client = genai.Client(api_key=settings.GOOGLE_API_KEY)
result = process_posting(body="공고 본문 텍스트", client=client, model_name=settings.LLM_MODEL)
# result는 JobPosting 필드에 대응하는 dict

# 로그 콜백을 전달하면 처리 단계별 상세 로그를 받을 수 있다
result = process_posting(body="...", client=client, model_name=settings.LLM_MODEL, log=print)
```

### `scraper/`

| 파일 | 역할 |
|---|---|
| `yakdap.py` | `scrape(start_id, count, step, year, ...)` → `list[dict]` |
| `pharm_recruit.py` | `scrape(big_category, ...)` → `list[dict]`, `CITY_URL_DICT` 내장 |

반환 dict의 키: `url`, `platform`, `created_at`, `title`, `pharmacy_name`, `body`, `city`, `big_category`

### `geo/mapping.py`

```python
from geo.mapping import normalize_city, assign_big_category

city = normalize_city("서울특별시 강남구 역삼동")  # → "서울-강남구"
big = assign_big_category("서울-강남구")            # → "서울"
```

- `conversion_dict`: 약 130개의 전체 주소 → 지역 코드 매핑
- `big_category_dict`: 지역 코드 → 5개 대분류 매핑

### `stats/charts.py`

각 함수는 Django ORM으로 데이터를 조회하여 matplotlib 차트를 base64 PNG로 반환한다. 한글 폰트는 시스템에 설치된 `AppleGothic` → `NanumGothic` → `Malgun Gothic` 순으로 자동 선택된다.

```python
from stats.charts import chart_postings_by_region, get_summary_stats

b64_png = chart_postings_by_region()   # <img src="data:image/png;base64,{b64_png}">
stats   = get_summary_stats()          # dict: total, continuous_count, ...
```

---

## LLM 파이프라인 상세

### Task 분기 구조

```
Task 1: 급여 정보 추출
    ├─ is_one_time_work = True
    │       └─ Task 2: 일회성 시급 계산
    └─ is_one_time_work = False
            ├─ Task 3: 출퇴근 시각 추출
            └─ Task 4: Task 3 결과 검토·수정
Task 5: 복리후생 추출 (항상 실행)
```

### 시급 계산 기준

- **지속성 근무**: `시급 = 급여 / 월 근무 시간`, 월 근무 시간 = 주당 근무 시간 × 4.34
- **일회성 근무**: Task 2에서 LLM이 직접 계산
- 시급 유효 범위: `1.8만원 ~ 5.5만원` (settings.py에서 조정 가능)
- 주당 최대 근무 시간: `56시간`

### 세후 월급 공식

네이버 세금 계산기 샘플링 기반 2차 회귀:

```
세후 월급 = 5.35 + 0.904394 × 세전월급 - 0.000143950695 × 세전월급²
```

단위: 만원. `LLM이 세후 금액이라고 답한 경우`에는 변환 없이 그대로 저장.

---

## 데이터 모델

### JobPosting

| 필드 | 타입 | 설명 |
|---|---|---|
| `url` | URLField (unique) | 공고 원본 URL |
| `platform` | CharField | `약문약답` / `팜리크루트` |
| `created_at` | DateField | 공고 등록일 |
| `inserted_at` | DateTimeField | DB 저장 시각 (자동) |
| `title` | TextField | 공고 제목 |
| `pharmacy_name` | CharField | 약국 이름 |
| `body` | TextField | 공고 본문 (LLM 입력 원문) |
| `city` | CharField | 지역 코드 (예: `서울-강남구`) |
| `big_category` | CharField | 지역 대분류 (예: `서울`) |
| `is_salary_disclosed` | BooleanField | 급여 명시 여부 |
| `is_one_time_work` | BooleanField | 일회성 근무 여부 |
| `one_time_hourly_wage` | FloatField | 일회성 근무 시급 (만원) |
| `wage_type` | CharField | `monthly` / `yearly` / 기타 |
| `wage_raw` | FloatField | LLM이 추출한 원본 급여 (만원) |
| `hourly_wage` | FloatField | 계산된 시급 (만원) |
| `net_salary` | FloatField | 세후 월급 (만원) |
| `weekday_work_days` | FloatField | 평일 근무 일수 |
| `weekday_start_time` | FloatField | 평일 출근 시각 (소수 시간, 예: 9.0) |
| `weekday_end_time` | FloatField | 평일 퇴근 시각 |
| `weekend_work_days` | FloatField | 주말 근무 일수 |
| `weekend_start_time` | FloatField | 주말 출근 시각 (소수 시간) |
| `weekend_end_time` | FloatField | 주말 퇴근 시각 |
| `hours_per_week` | FloatField | 주당 총 근무 시간 |
| `hours_per_month` | FloatField | 월 총 근무 시간 |
| `monthly_leave` | CharField | 월차 정보 |
| `experience_required` | TextField | 경력 요구 사항 |
| `meal_info` | TextField | 식사 제공 여부 등 |
| `llm_model` | CharField | 처리에 사용된 LLM 모델명 |
| `gpt_summary` | TextField | LLM 생성 요약문 |
| `gpt_output_log` | TextField | 각 task 원본 출력 로그 |
| `gpt_error_log` | TextField | 에러 발생 시 상세 메시지 |
| `has_error` | BooleanField | 에러 발생 여부 (LLM 또는 validator) |
| `error_corrected` | BooleanField | 수동 교정 완료 여부 |
| `user_reviewed` | BooleanField | 개인 검토 완료 여부 |
| `user_comment` | TextField | 개인 메모 |

### PipelineRun

파이프라인 실행 이력. Admin에서 `Postings > Pipeline runs`에서 확인.

| 필드 | 설명 |
|---|---|
| `source` | `yakdap` / `pharm_recruit` |
| `started_at` | 실행 시작 시각 |
| `finished_at` | 완료 시각 |
| `total_scraped` | 스크래핑된 공고 수 |
| `total_processed` | DB에 저장된 공고 수 |
| `total_errors` | 에러 발생 공고 수 |
| `status` | `running` / `done` / `failed` |
| `log_output` | 실행 중 누적되는 상세 로그 (Admin 실시간 로그 페이지에서 표시) |

---

## 일회성 데이터 마이그레이션

기존 Notion 데이터를 JSON으로 변환한 파일이 `data/` 폴더에 있을 경우 아래 스크립트로 SQLite에 한 번에 임포트할 수 있다.

```bash
python scripts/migrate_json_to_sqlite.py
```

- `data/yakkook.json`: 메인 데이터 (3,444행)
- `data/output_error.json`: 에러 교정 데이터 → `error_corrected=True`로 삽입
- 중복 URL은 `get_or_create`로 자동 스킵
- 한국어 날짜 형식(`2024년 9월 19일`) 자동 변환
- `"TRUE"` / `"FALSE"` 문자열 → Python bool 자동 변환
- NaN → None 자동 변환
