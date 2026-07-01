# 약국 구인공고 분석 시스템 (yak-gongo)

약문약답·팜리크루트 두 플랫폼의 약사 구인공고를 수집하고, Google Gemini LLM으로 급여·근무 일정·복리후생 정보를 자동 추출하여 SQLite에 저장하는 Django 기반 분석 시스템.

## 목적

- **개인 리뷰 워크플로우**: Django Admin에서 LLM 추출 결과를 확인·수정·체크
- **통계 공유**: 자체 웹 프론트엔드(`web` 앱)의 홈·근무 유형별 페이지에서 시급·지역·근무 유형별 통계를 외부에 공개

---

## 목차

1. [프로젝트 구조](#프로젝트-구조)
2. [초기 설정](#초기-설정)
3. [환경 변수](#환경-변수)
4. [공고 수집 및 처리 (run_pipeline)](#공고-수집-및-처리)
5. [Django Admin 리뷰 워크플로우](#django-admin-리뷰-워크플로우)
6. [웹 대시보드 (web 앱)](#웹-대시보드)
7. [Notion 통계 생성](#notion-통계-생성)
8. [모듈별 설명](#모듈별-설명)
9. [LLM 파이프라인 상세](#llm-파이프라인-상세)
10. [데이터 모델](#데이터-모델)
11. [LLM 비용 모니터링](#llm-비용-모니터링)
12. [일회성 데이터 마이그레이션](#일회성-데이터-마이그레이션)

---

## 프로젝트 구조

```
yak-gongo/
├── config/                  # Django 프로젝트 설정
│   ├── settings.py
│   └── urls.py
│
├── postings/                # 핵심 앱: 공고 DB + Admin
│   ├── models.py            # JobPosting, RawPosting, AdminCheck, AgentReviewSession, PipelineRun, DashboardSnapshot, LLMUsageEvent
│   ├── admin.py             # Admin 커스터마이징 + 리뷰 대시보드 pre-단계(크롤링·LLM 프로세싱) UI + 대시보드 스냅샷 갱신 버튼 + Token Usage 통계 페이지 + LLMUsageEvent admin (admin 홈 index_template도 교체)
│   ├── review_presets.py    # 리뷰 대시보드 프리셋 정의 (탭별 필터·컬럼, LLM 검토 대상/포커스)
│   ├── review_verify.py     # 2단계 outlier 공고 LLM(Gemini) 재검산 서비스 (DOMAIN_RULES 공유 상수)
│   ├── review_agent.py      # 3단계 에러 케이스 대화형 agent 검토 서비스 (Gemini multi-turn + 구조화 출력, 파생 필드 서버 재계산)
│   ├── dataframe.py         # build_dataframe() — DB → 통계 호환 pandas DataFrame (run_statistics·웹 대시보드 공유)
│   ├── dashboard_stats.py   # compute_dashboard_data() — 웹 대시보드용 통계 산출 (matplotlib/Notion 의존성 없는 순수 계산)
│   ├── forms.py             # PipelineRunForm (크롤링 실행 폼)
│   ├── apps.py              # 서버 시작 시 orphan PipelineRun 정리
│   ├── management/commands/
│   │   ├── scrape_postings.py  # 1단계: 크롤링하여 RawPosting(pending)으로 저장
│   │   ├── process_postings.py # 2단계: pending RawPosting을 LLM 처리하여 JobPosting 생성
│   │   ├── run_pipeline.py  # 1·2단계를 순서대로 실행하는 오케스트레이터
│   │   ├── run_statistics.py # DB → DataFrame 변환 후 Notion 통계 차트 생성
│   │   ├── auto_verify_step3.py # 2단계 outlier 공고 LLM 일괄 자동 검토 (CLI)
│   │   └── ceil_hourly_wages.py # 시급 올림 보정 일괄 적용 (1회성)
│   ├── templatetags/
│   │   └── usage_extras.py   # kfmt 필터 — 토큰 수 k/M 축약 표시
│   └── templates/admin/
│       ├── index_with_dashboard.html         # admin 홈에 "공고 리뷰 대시보드"·"Token Usage" 진입 버튼 추가 (admin.site.index_template)
│       └── postings/
│           ├── jobposting/
│           │   ├── review_dashboard.html        # 리뷰 대시보드 (pre-단계 + 프리셋 탭 + "대시보드 업데이트" 버튼)
│           │   ├── prestage_scrape_form.html     # pre-1단계: 크롤링 실행 폼 fragment
│           │   ├── prestage_pending.html         # pre-2단계: LLM 처리 대기 목록 fragment
│           │   └── token_usage.html             # LLM 토큰/비용 통계 페이지 (날짜·단계·모델별 집계)
│           └── pipelinerun/
│               └── run_log.html     # 실시간 로그 폴링 페이지
│
├── pipeline/                # LLM 파이프라인 (비즈니스 로직)
│   ├── prompts.py           # 5개 task 프롬프트 / few-shot
│   ├── tasks.py             # run_task_1() ~ run_task_5() — Gemini API 호출
│   ├── runner.py            # process_posting() — 단일 공고 오케스트레이터
│   ├── stages.py            # scrape_stage / process_stage / process_raw_posting — 2단계 파이프라인 공통 로직
│   ├── validator.py         # error_check() — LLM 출력 일관성 검증
│   ├── salary.py            # to_net_salary() — 세후 월급 계산, ceil_hourly_wage() — 시급 올림 보정
│   ├── pricing.py           # PRICING 단가표 + compute_cost() — 토큰 → USD 비용 (settings.LLM_PRICING으로 덮어쓰기 가능)
│   └── usage.py             # 토큰 사용량 캡처(extract_usage)·누적(accumulator)·기록(record_llm_usage) 유틸
│
├── scraper/                 # 웹 스크래퍼 (Selenium)
│   ├── yakdap.py            # 약문약답 스크래퍼 (on_item 콜백으로 건별 중간 저장 지원)
│   └── pharm_recruit.py     # 팜리크루트 스크래퍼 (자동 페이지네이션, on_item 콜백)
│   # pharm_recruit_urls.json — 초기 설정 시 생성 필요 (아래 참고)
│
├── geo/
│   └── mapping.py           # 주소 → 지역코드, 지역 대분류 변환
│
├── web/                     # 외부 공개 웹 프론트엔드 앱
│   ├── views.py             # 최신 DashboardSnapshot을 읽어 페이지별 섹션을 템플릿에 임베드
│   ├── urls.py              # / · /compare/ · /compare/result/ · /method/ · /fulltime/ · /weekend/ · /etc/ · /onetime/
│   ├── templates/web/       # home·compare·compare_result·method·fulltime·weekend·etc·onetime.html
│   │                        #   + _region_modal.html (지역 분류 기준 모달, 여러 페이지에서 include)
│   └── static/web/js/
│       ├── charts.js        # 순수 SVG 차트 빌더 (데이터 입력과 분리된 순수 함수)
│       ├── home.js / fulltime.js / weekend.js / etc.js / onetime.js  # 페이지별 데이터 바인딩
│       ├── compare.js / compare_result.js  # "내 시급 비교" 입력 폼·결과 페이지 (퍼센타일 계산)
│       ├── region-modal.js  # "지역 분류 기준" 모달 열기/닫기 (공유)
│       └── ui.js            # 토글 등 인터랙션
│
├── notion-stats/            # Notion 연동 통계 (차트 생성 + Notion 업로드)
│   └── one_click_statistics.py  # 30종 이상 차트 생성 및 Notion 페이지 업데이트
│
├── legacy-files/               # 일회성 스크립트 모음 (레거시)
│   └── one-time-data-migration/
│       ├── convert_pharm_urls.py        # 팜리크루트 URL JSON 생성 스크립트
│       └── migrate_json_to_sqlite.py    # 기존 JSON 데이터 → SQLite (1회성)
│
├── data/
│   └── db.sqlite3           # SQLite DB
│
├── dev.sh                   # 개발 서버 실행 스크립트 (migrate + runserver)
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

### 4. 팜리크루트 URL 데이터 생성

팜리크루트 스크래퍼는 `scraper/pharm_recruit_urls.json` 파일에서 지역별 URL을 로드한다. 이 파일은 `.gitignore`에 의해 버전 관리에서 제외되므로, 최초 1회 생성이 필요하다.

```bash
python legacy-files/one-time-data-migration/convert_pharm_urls.py
cp legacy-files/one-time-data-migration/pharm_recruit_urls.json scraper/
```

### 5. DB 마이그레이션

```bash
python manage.py migrate
```

`data/db.sqlite3` 파일이 생성된다.

### 6. 관리자 계정 생성

```bash
python manage.py createsuperuser
```

### 7. 서버 실행

`dev.sh` 스크립트를 사용하면 마이그레이션 적용 후 개발 서버가 한 번에 실행된다. 포트를 인자로 넘길 수 있으며 생략 시 8011번을 사용한다.

```bash
./dev.sh          # http://127.0.0.1:8011
./dev.sh 8080     # 포트 지정
```

스크립트는 프로젝트 루트의 `.venv` 가상환경(`/.venv/bin/python`)을 사용한다. `.venv`가 없으면 안내 메시지를 출력하고 종료한다.

직접 실행하려면:

```bash
python manage.py runserver 8011
```

- Admin: http://localhost:8011/admin/
- 웹 대시보드: http://localhost:8011/

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
LLM_MODEL=gemini-2.5-flash               # 사용할 Gemini 모델

# Notion 통계 업로드 (run_statistics 커맨드 사용 시 필요)
NOTION_TOKEN=your-notion-integration-token
```

- **GOOGLE_API_KEY** 발급: [Google AI Studio](https://aistudio.google.com/) → 'Get API key'
- **NOTION_TOKEN** 발급: [Notion Integrations](https://www.notion.so/my-integrations) → 내부 통합 생성 후 토큰 복사

> **LLM 토큰 단가**: 비용 계산 단가표는 `pipeline/pricing.py`의 `DEFAULT_PRICING`(USD/1M tokens)에 두며, 필요 시 `settings.LLM_PRICING` dict로 모델별 `(입력, 출력)` 단가를 덮어쓸 수 있다 ([LLM 비용 모니터링](#llm-비용-모니터링) 참고).

---

## 공고 수집 및 처리

수집·처리는 **재개 가능(resumable)·멱등(idempotent)**한 두 단계로 나뉘며, 그 사이에 `RawPosting` 스테이징 테이블을 둔다.

- **1단계 (크롤링)**: 스크래퍼가 공고를 한 건 긁을 때마다 즉시 `RawPosting(status=pending)`으로 저장한다. 도중에 멈추거나 크래시해도 이미 긁은 공고는 보존되며, 다시 실행하면 (이미 `JobPosting`/`RawPosting`에 있는 URL은 건너뛰고) 끊긴 지점부터 이어서 크롤링한다.
- **2단계 (LLM 처리)**: `status=pending`인 `RawPosting`만 LLM 파이프라인으로 처리해 `JobPosting`을 생성하고, 각 건의 status를 `processed` / `skipped_no_salary` / `error`로 갱신한다. 도중에 멈춰도 재실행하면 아직 `pending`인 것부터 이어서 처리한다.

두 단계의 공통 로직은 `pipeline/stages.py`(`scrape_stage` / `process_stage` / `process_raw_posting`)에 있고, 세 가지 방식으로 실행할 수 있다.

| 실행 방식 | 동작 |
|---|---|
| `scrape_postings` 커맨드 | 1단계만 (크롤링 → RawPosting) |
| `process_postings` 커맨드 | 2단계만 (pending RawPosting → JobPosting) |
| `run_pipeline` 커맨드 | 1단계 → 2단계를 순서대로 실행하는 오케스트레이터 |
| 리뷰 대시보드 pre-단계 (Admin UI) | 1·2단계를 각각 버튼으로 실행 ([아래](#admin에서-파이프라인-실행) 참고) |

아래 옵션 표는 `scrape_postings`(1단계)와 `run_pipeline`(1+2단계)이 공유한다. `process_postings`(2단계)는 옵션 없이 실행하면 모든 pending RawPosting을 처리한다.

### 약문약답 수집

```bash
# 1단계 + 2단계를 한 번에
python manage.py run_pipeline \
    --source yakdap \
    --start-id 38800 \
    --count 100 \
    --step 2

# 단계를 따로 돌리기
python manage.py scrape_postings --source yakdap --start-id 38800 --count 100 --step 2
python manage.py process_postings   # 1단계 완료 후 별도로
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--start-id` | 탐색 시작 공고 ID | `38800` |
| `--count` | 탐색할 공고 수 | `100` |
| `--step` | ID 증가 간격 | `2` |
| `--year` | 등록일 연도 폴백값. 약문약답은 공고에 적힌 연도("2024년 11월 22일")를 우선 쓰고, 연도가 없거나(월·일만 표시) 상대 표기("어제 오전 8:17")인 경우 이 값으로 보정한다 | 현재 연도 |

명령어 실행 시 브라우저가 열리고 카카오 로그인 화면이 나타난다. 로그인을 완료한 뒤 터미널에서 Enter를 누르면 수집이 시작된다. Admin UI에서 실행하는 경우에는 로그 페이지에서 **로그인 완료** 버튼을 클릭한다.

### 팜리크루트 수집

```bash
python manage.py run_pipeline \
    --source pharm_recruit \
    --big-category 서울 인천 \
    --pharm-count 50
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--big-category` | 수집할 지역 대분류 (복수 지정 가능) | `서울` |
| `--pharm-count` | 수집 개수 한도. 선택 지역/도시별로 균등 분배 | 전체 |
| `--year` | 등록일 연도 (팜리크루트는 월/일만 표시되므로 이 값으로 보정) | 현재 연도 |

`--big-category`에 가능한 값: `서울`, `인천`, `경기 중부`, `경기 외곽`, `지방`

각 대분류에 포함되는 세부 지역(도시)은 `scraper/pharm_recruit_urls.json`에 정의되어 있다. `--pharm-count`를 지정하면 총 수집 개수를 선택한 대분류 수로 나누고, 다시 각 대분류 내 도시 수로 나눠 균등 분배한다.

### 공통 옵션

| 옵션 | 설명 |
|---|---|
| `--headless` | 브라우저 창 없이 백그라운드 실행 |
| `--dry-run` | (`run_pipeline` 전용) 1단계 크롤링만 하고 2단계 LLM 처리는 건너뜀 — `RawPosting`까지만 저장한다 |
| `--run-id` | Admin UI에서 미리 생성된 PipelineRun ID (내부용, 수동 사용 불필요) |

> `--dry-run`은 `run_pipeline`을 `scrape_postings`처럼(크롤링만) 동작시킨다. RawPosting은 그대로 남으므로 이후 `process_postings`로 LLM 처리를 이어갈 수 있다.

### 처리 흐름

```
[1단계] 스크래핑 (Selenium)
    ↓
중복 URL 자동 스킵 (JobPosting + RawPosting과 비교)
    ↓
공고 1건마다 즉시 RawPosting(status=pending) 저장  ← 여기까지가 scrape_postings / --dry-run
    │
    │  (도중에 멈춰도 보존, 재실행하면 이어서 진행)
    ↓
[2단계] pending RawPosting을 한 건씩 LLM 처리           ← 여기부터가 process_postings
    ↓
LLM 파이프라인 (Gemini API, 공고당 최대 5회 호출)
    ├─ Task 1: 급여 유형·금액, 일회성 여부
    │     └─ 급여 미명시 → 저장 건너뜀 (None 반환, RawPosting status=skipped_no_salary)
    ├─ Task 2: 일회성 근무 시급 계산 (일회성인 경우)
    ├─ Task 3: 평일·주말 출퇴근 시각 추출 (지속성인 경우)
    ├─ Task 4: Task 3 결과 검증·수정
    └─ Task 5: 복리후생 (월차, 경력, 식사)
    ↓
validator.error_check(): 주당 근무 시간 재계산 및 오류 감지
    ↓
salary.to_net_salary(): 세후 월급 산출 → 세후 시급(net_hourly_wage) = 세후 월급 / 월 근무 시간
    ↓
salary.ceil_hourly_wage(): 세후 시급·일회성 시급을 소수점 셋째 자리에서 올림(둘째 자리까지) 보정
    ↓
JobPosting DB 저장 + RawPosting status=processed (에러 시 error)
    ↓
PipelineRun 이력 기록
```

---

## Django Admin 리뷰 워크플로우

http://localhost:8011/admin/ 접속 후 사용.

**리뷰 대시보드 진입 경로**: ① admin 홈(`/admin/`) 상단의 **📋 공고 리뷰 대시보드 열기** 버튼(`index_with_dashboard.html` 커스텀 index 템플릿), 또는 ② **Postings > Job postings** 상단 **리뷰 대시보드** 링크.

### Admin에서 파이프라인 실행

수집·처리 두 단계는 **리뷰 대시보드** 상단의 **pre-단계** 영역에서 실행한다 (프리셋 탭 위, 점선으로 구분된 보라색 탭 두 개).

**pre-1단계: 공고 크롤링** (`크롤링 실행` 버튼)

1. 버튼을 누르면 인라인 크롤링 폼이 펼쳐진다. 소스(약문약답/팜리크루트)와 옵션을 입력한다.
   - 약문약답 선택 시 `headless`는 자동 비활성화됨 (카카오 로그인 필요)
   - 팜리크루트 선택 시 지역 대분류 복수 선택 + 수집 개수 한도 설정 가능
2. **크롤링 시작** → 백그라운드 thread에서 `run_pipeline --dry-run`(크롤링만) 실행 → `RawPosting`까지만 저장. 페이지 이동 없이 **대시보드 하단(`#table-container`)에 실시간 로그 패널**이 인라인으로 표시된다(`status/<id>/`를 1초 간격으로 폴링). 별도 로그 페이지로 이동하지 않는다.
3. 약문약답의 경우, 로그 패널 안에 카카오 로그인 안내와 **로그인 완료** 버튼이 인라인으로 나타나며, 브라우저에서 로그인을 마친 뒤 이 버튼을 누르면 스크래핑이 시작된다. 완료되면 패널에 **← 크롤링 설정으로 돌아가기** 버튼이 떠 크롤링 폼으로 되돌아갈 수 있다(이어서 pre-2단계 처리 대기 탭에서 LLM 처리).

**pre-2단계: LLM 프로세싱** (`처리 대기 [N]` 버튼)

1. 버튼의 배지에 처리 대기(`status=pending`) `RawPosting` 건수가 표시된다. 누르면 대시보드 하단에 설명 박스와 함께 대기 목록 표가 펼쳐진다(페이지당 25행 페이지네이션). 표는 프리셋 컨트롤바와 동일한 레이아웃(정렬 좌 / 액션 우)으로, 수집 시각·공고일(`created_at`)·제목·약국·플랫폼·지역 기준 정렬(오름/내림)을 지원한다(기본 정렬은 공고일 내림차순). 정렬 컨트롤 옆의 **📊 날짜별 분포 보기** 버튼을 누르면 대기 공고를 공고일(`created_at`)별로 집계한 히스토그램 모달이 뜬다(`prestage/pending-histogram/`가 최소~최대 날짜 사이의 0건 날짜까지 채운 `[{date, count}]`와 날짜 미상 건수를 반환). 지역 컬럼은 원본 `city`(약문약답은 전체 주소, 팜리크루트는 짧은 지역)를 `geo.mapping.normalize_city`로 정규화한 값(`city_display`)을 보여주며, 각 행의 **상세 ↗** 링크는 해당 `RawPosting` admin 변경 페이지로 연결된다.
2. 전체 또는 체크한 행만 선택해 처리하면, LLM 자동 검토와 동일한 **실시간 진행 모달**이 뜨고 한 건씩 LLM 처리한다(건당 `prestage/process-one/` 호출 → `pipeline.stages.process_raw_posting`). 각 건은 저장/급여 미명시 건너뜀/에러로 집계된다. 모달 행에는 추출된 핵심 필드(시급·월급·지역·근무형태·주당 시간, `pipeline.stages._summary_fields`)가 인라인으로 표시되고, 행을 클릭하면 5-task 처리 단계 요약(`process_posting`이 모은 `steps`)이 펼쳐진다. 완료 후 대기 목록과 배지가 자동 갱신된다.

pre-단계 상세 패널(크롤링 폼·로그·대기 목록)은 프리셋 상세와 동일한 하단 영역(`#table-container`)에 렌더되며, 프리셋 탭과 상호 토글된다. 동시에 하나의 크롤링만 실행 가능하며, 이미 실행 중이면 실행 중인 작업 로그를 (페이지 이동 없이) 같은 패널에서 볼지 묻는다. 크롤링과 LLM 프로세싱이 분리돼 있어, 크롤링 도중 멈춰도 RawPosting은 남고 나중에 pre-2단계로 이어서 처리할 수 있다.

**Admin 커스텀 URL:**

| URL 패턴 | 설명 |
|---|---|
| `jobposting/review/prestage/scrape-form/` | AJAX GET: pre-1단계 크롤링 실행 폼 fragment |
| `jobposting/review/prestage/scrape-start/` | AJAX POST: 크롤링(스크래핑)만 백그라운드 실행 |
| `jobposting/review/prestage/pending/` | AJAX GET: pre-2단계 처리 대기 RawPosting 목록 fragment |
| `jobposting/review/prestage/pending-histogram/` | AJAX GET: 처리 대기 RawPosting을 공고일별로 집계한 히스토그램 데이터 |
| `jobposting/review/prestage/process-one/` | AJAX POST: pending RawPosting 한 건을 LLM 처리 |
| `pipelinerun/log/<id>/` | 실시간 로그 확인 페이지 |
| `pipelinerun/status/<id>/` | AJAX 상태 + 로그 JSON 엔드포인트 |
| `pipelinerun/confirm-login/<id>/` | AJAX 카카오 로그인 완료 신호 엔드포인트 |

> **Postings > Pipeline runs** 목록은 실행 이력·로그 확인 전용이다 (별도 커스텀 버튼·실행 폼 페이지 없이 기본 changelist + 로그 확인 URL만 제공). Notion 통계 생성은 `run_statistics` 커맨드로 실행한다 ([Notion 통계 생성](#notion-통계-생성) 참고).

서버가 재시작되면 `postings/apps.py`에서 비정상 종료된 `running` 상태의 PipelineRun을 자동으로 `failed`로 변경한다.

### 공고 목록 화면

**Postings > Job postings** 클릭.

- **목록 컬럼**: 공고 제목, 등록일, 플랫폼, 지역, 시급(세후), 월급(세후), 일회성 여부, 검토 여부, 에러 여부, 원문 링크
  - 시급(세후) 컬럼은 일회성 근무이면 `one_time_hourly_wage`, 지속성이면 `net_hourly_wage`를 자동 표시
  - 검토 여부(`검토`) 컬럼은 해당 공고에 `AdminCheck` 레코드가 존재하는지(`hasattr(obj, 'admin_check')`)를 표시하는 읽기 전용 boolean이다
- **필터** (우측 사이드바): 등록일 범위, 급여 명시 여부, 일회성/지속성, 플랫폼, 지역 대분류, 에러 여부, 시급(세후) 범위
- **검색**: 공고 제목, 약국 이름, 지역, URL
- **에러 공고 필터링**: `has_error = True`로 필터 → LLM이 의심스럽다고 판단한 공고만 모아서 검토

### 공고 상세 화면

섹션별로 그룹화된 필드:

| 섹션 | 주요 필드 |
|---|---|
| 기본 정보 | 플랫폼, 등록일, 약국 이름, 지역, 지역 대분류 |
| 급여 | 급여 명시 여부, 급여 유형, 원본 급여, 세후 시급, 세후 월급, 일회성 여부, 일회성 시급 |
| 근무 일정 | 평일/주말 근무 일수, 출퇴근 시각, 주당·월별 근무 시간 |
| 복리후생 | 월차, 경력 요구, 식사 관련 |
| LLM 결과 | 모델명, 요약문, 상세 로그 (접기/펼치기) |
| 검토 / 품질 | 에러 여부, 개인 코멘트 (검토 완료 여부는 별도 필드가 아니라 `AdminCheck` 존재로 판정) |
| 원문 | 공고 본문 전체 (접기/펼치기) |

### 용어 정의: '에러'와 '이상치'

리뷰 워크플로우의 두 용어를 가르는 진짜 기준은 **"무엇이 잡느냐"**다. 에러는 자동 검증 코드가 잡아 DB에 저장하는 플래그이고, 이상치는 리뷰 대시보드가 사람 검토용으로 거르는 쿼리 필터다.

| | **에러 (error)** | **이상치 (outlier)** |
|---|---|---|
| 의미 | 자동 검증이 잡은, 값이 틀렸거나 계산이 불가능한 케이스 | 자동 검증이 다루지 않는 항목이거나, 통계적으로 드물어 사람 확인이 필요한 값 (유효할 수도 있음) |
| 잡는 주체 | ① `pipeline/validator.py`의 `error_check()` (추출 시)<br>② `postings/review_verify.py` (LLM 자동 검토 불일치) | 리뷰 대시보드 프리셋 `postings/review_presets.py` (쿼리 필터) |
| 저장 여부 | `has_error=True`로 **DB에 저장** (`has_error = bool(gpt_error_log)`) | 저장 안 됨 — 매번 필터로 산출 |
| 검토 단계 | 3단계: 에러 케이스 재검토 (`error_review`) | 2단계: outlier 검토 (`has_error=False`인 공고만 대상) |

핵심은 **"에러냐"가 곧 "validator가 그 항목을 검사하느냐"**라는 점이다. 그래서 "물리적으로 불가능 = 에러"가 항상 성립하진 않는다:

- **빈 `city`** → **이상치** (에러 아님). `city`는 LLM 추출이 아니라 `geo/mapping.py`가 주소를 변환한 결과라 validator 범위 밖이다. 빈 값 = 매핑 사전에 없는 주소 → "사람이 직접 입력"할 매핑 보완 과제이지 추출 오류가 아니다.
- **소수점 근무일(예: 0.5)** → **이상치** (에러 아님). 격주 근무를 평균낸 정상 표현이므로(격주 평일 1일 = 0.5), 드물어서 한 번 확인하면 좋을 뿐 틀린 값이 아니다.
- **음수 근무일** → **에러**. 물리적으로 불가능하므로 `validator.py`의 `error_check()`가 명시적으로 잡는다.

**항목별 임계값 비교** — 같은 항목이라도 에러 경계와 이상치 경계가 다르다. 에러 기준은 `validator.py`(상수는 `settings.py`의 `MIN_HOURLY_WAGE=1.8` / `MAX_HOURLY_WAGE=5.5` / `MAX_WORK_HOURS_PER_WEEK=56`), 이상치 기준은 `review_presets.py`:

| 항목 | 에러 (`has_error=True`) | 이상치 (대시보드 필터) |
|---|---|---|
| 지속성 시급 | 1.8 ~ 5.5만원 밖 (또는 급여·시급 둘 다 없음) | 2.0 ~ 4.0만원 밖, 또는 시급/월급 `null` |
| 일회성 시급 | 1.8 ~ 5.5만원 밖 | 2.5 ~ 4.0만원 밖, 또는 `null` |
| 평일 근무일 | 음수, 합이 0, 또는 > 5 | 소수점(비정수) |
| 주말 근무일 | 음수, 또는 > 2 | 0.5 / 1 / 2 외의 값 (0 제외) |
| 주당 근무시간 | 0시간, > 56시간, 또는 음수(야간 표기 오류) | (직접 기준 없음) |
| 급여 유형 | 알 수 없는 유형 → `monthly`로 대체하며 에러 기록 | — |
| 세전/세후 | — | 본문에 "세전" 포함 |
| 지역(`city`) | — | 빈 문자열 (`geo/mapping` 변환 실패) |

> **임계값 폭이 다른 이유:** 에러는 "불가능" 경계라 폭이 넓고(시급 1.8~5.5), 이상치는 "전형적" 범위라 더 좁다(지속성 2.0~4.0). 예컨대 시급 **4.5만원**은 에러는 아니지만(1.8~5.5 안) 이상치로는 잡혀(2.0~4.0 밖) 사람이 한 번 확인한 뒤 맞으면 그대로 통과한다. 시급 **5.8만원**은 범위를 완전히 벗어나 `has_error=True`가 되어 3단계 재검토로 간다.

### 리뷰 대시보드 (프리셋 기반)

**Postings > Job postings** 상단의 **리뷰 대시보드** 링크로 진입. 단계별 프리셋 탭이 제공되며, 각 탭은 특정 검토 시나리오에 맞는 필터·컬럼·인라인 편집 필드를 자동 구성한다.

| 단계 | 탭 이름 | 필터 조건 |
|---|---|---|
| 1단계: 사전 점검 | 급여 미공개 | `is_salary_disclosed=False` & `AdminCheck` 미존재 |
| 2단계: outlier 검토 | 근무일 이상치 | 평일 근무일이 비정수(소수점), 주말 근무일이 0.5/1/2 외 (음수·평일>5는 에러로 분리) |
| 2단계: outlier 검토 | 일회성 시급 검토 | 일회성 근무이면서 시급 null / < 2.5 / > 4.0 |
| 2단계: outlier 검토 | 지속성 시급 검토 | 지속성 근무이면서 시급/월급 null 또는 시급 < 2.0 / > 4.0 |
| 2단계: outlier 검토 | 세전 확인 | 지속성 근무이면서 본문에 "세전" 포함 |
| 2단계: outlier 검토 | 지역 미분류 | `city`가 빈 문자열 |
| 3단계: 에러 케이스 재검토 | 에러 미검토 | `has_error=True` & `AdminCheck` 미존재 |
| 최종 점검 | 검토완료/코멘트 누락 | 검토 완료(`AdminCheck` 존재)인데 코멘트 누락, 또는 미검토인데 코멘트 있음 |

2단계(outlier 검토) 탭들은 `has_error=False` & `AdminCheck` 미존재인 공고만 대상으로 한다. 자동 검산(2단계)에서 본문과 불일치가 발견된 공고는 `has_error=True`가 되어 3단계(에러 케이스 재검토)로 넘어간다.

프리셋 정의는 `postings/review_presets.py`의 `REVIEW_PRESETS`에서 관리한다.

**검토 워크플로우 예시:**
1. `has_error=True` 필터로 에러 공고 목록 확인
2. 공고 클릭 → LLM 요약문과 원문 비교
3. 시급이 잘못 계산된 경우 직접 수정
4. 행을 선택해 **검토 완료** (벌크) 처리 → `AdminCheck(source='admin')` 생성으로 검토 완료 기록

검토 완료 여부는 별도 boolean 필드가 아니라 모든 프리셋에 공통 주석(`is_reviewed` = `AdminCheck` 존재 여부, source 무관)으로 노출되며, 검토 완료된 행은 `reviewed` 클래스로 강조된다.

정렬은 모든 프리셋에서 프리셋 컬럼 외에 등록 시각(`inserted_at`)·수정 시각(`updated_at`)으로도 가능하다.

### LLM 자동 검토 (2단계 outlier 프리셋)

2단계: outlier 검토 프리셋 중 LLM 추출값을 재검산할 수 있는 4개 탭(`근무일 이상치`, `일회성 시급 검토`, `지속성 시급 검토`, `세전 확인`)에는 **🤖 LLM으로 자동 검토** 버튼이 노출된다 (`지역 미분류`는 `city`가 LLM 추출이 아니라 `geo/mapping` 변환 결과라 제외). LLM 검토 대상 프리셋 목록은 `review_presets.py`의 `VERIFY_PRESET_KEYS`로 관리한다.

동작 방식:

1. 버튼을 누르면 현재 프리셋의 후보 공고를 모아 실시간 진행 모달이 뜬다. 처리 건수 한도를 지정하거나, 표에서 체크한 행만 검토할 수 있다.
2. 공고당 Gemini 1회 호출로, **새로 추출하지 않고** 이미 DB에 저장된 값이 본문과 일치하는지만 판정한다. 기존 추출 파이프라인(prompts/tasks)을 재실행하지 않고 도메인 규칙(`review_verify.DOMAIN_RULES`)만 압축한 단일 검산 프롬프트(`review_verify.VERIFY_SYSTEM_PROMPT`)를 사용한다. 프리셋별 `verify_focus` 힌트로 검토 중점을 안내한다.
3. 판정 결과에 따라:
   - **일치** → `AdminCheck(source='llm')` 생성 → 검토 완료로 처리되어 2단계 outlier 집합에서 빠진다. 합격 사유(`explanation`)를 `[LLM 합격] ...` 형태로 `user_comment`에 기록하되, 사람이 남긴 기존 코멘트는 덮어쓰지 않는다 (불일치 시 사유를 `gpt_error_log`에 남기는 것과 대칭).
   - **불일치** → 틀린 필드/제안값/사유를 `gpt_error_log`에 기록 → `save()`가 `has_error=True`로 설정 → **3단계(에러 케이스 재검토)로 이동**하여 사람이 직접(또는 대화형 agent로) 수정한다.
   - **실패**(JSON 파싱 실패, MAX_TOKENS, 빈 응답 등) → 변경 없이 사유만 모달 로그에 표시.
4. 이미 처리된 공고(`has_error=True` 또는 `AdminCheck` 존재)는 건너뛴다. 모달은 항목별 로그(제목 + 사유)와 함께 중지/닫기를 지원한다.

핵심 로직은 `postings/review_verify.py`의 `verify_posting()` / `apply_verdict()`에 있으며, 웹 버튼과 CLI 커맨드(`auto_verify_step3`)가 동일 로직을 공유한다.

**Admin 커스텀 URL (리뷰 대시보드):**

| URL 패턴 | 설명 |
|---|---|
| `review/verify-candidates/` | AJAX GET: 현재 프리셋의 LLM 검토 대상 공고 id·제목 목록 |
| `review/auto-verify/` | AJAX POST: 주어진 공고 id 배치를 Gemini로 검산하고 결과 반환 |

> 사람이 대시보드에서 **검토 완료**(`mark-reviewed/`)를 실행하면, 기존 `AdminCheck(source='llm')`은 `source='admin'`으로 승격된다 (검토 주체 추적).

### AI agent 대화형 검토 (3단계 에러 케이스 재검토)

3단계: 에러 케이스 재검토(`에러 미검토`) 탭에서 행을 하나 선택하면 **💬 AI agent 대화형 검토** 버튼이 활성화된다. 자동 검산에서 본문과 불일치가 잡혀 `has_error=True`가 된 공고를, 사람이 일일이 필드를 고치는 대신 Gemini agent와 대화하며 바로잡는 방식이다.

동작 방식:

1. 버튼을 누르면 채팅 모달이 열린다. 좌측에는 케이스 컨텍스트(현재 DB 필드 스냅샷 + 공고 본문 + 에러 로그)가, 우측에는 대화창이 표시된다. agent는 첫 턴에 에러 로그·현재 DB값·본문을 근거로 **무엇이 왜 틀렸는지 브리핑**하고 수정안을 제시한다.
2. agent는 같은 도메인 지식(`review_verify.DOMAIN_RULES`)을 공유하므로 자동 검산과 동일한 기준으로 판단한다. 매 호출마다 현재 DB 스냅샷을 system_instruction에 재주입해(서버는 stateless) 값이 오래되지 않도록 한다.
3. 수정이 필요하면 agent가 **구조화 출력**(`{message, updates}` JSON)으로 바꿀 필드 목록을 내보낸다. 서버는 이를 **즉시 실행하지 않고** 변경 제안(diff 카드)만 돌려준다 — Claude Code 스타일의 권한 박스에서 사람이 결정한다. 선택지는 두 가지다:
   - **예, 적용** (Enter / Y): 제안된 변경을 실제 DB에 반영한다.
   - **아니요, 다르게 해주세요** (Esc / N): 인라인 입력창이 열려 어떻게 다르게 하고 싶은지 바로 적는다. 그 지시(`note`)가 거부 결과와 함께 모델에 전달되어, 모델이 사유를 되묻는 중간 단계 없이 한 번에 대안을 제시한다. (입력 없이 보내면 단순 거부로 처리되어 모델이 다른 방법을 제안한다.)
4. **✓ 검토 완료**를 누르면 전체 대화를 근거로 `user_comment`를 생성하고, `AdminCheck(source='agent')`를 생성하며, 대화 전체(트랜스크립트 + 적용된 변경 + 생성 코멘트)를 `AgentReviewSession`으로 영구 저장한다. `gpt_error_log`는 보존되어 `has_error`는 유지되지만, `AdminCheck` 생성만으로 `에러 미검토` 큐(`admin_check__isnull=True`)에서 빠진다.

**왜 function calling이 아니라 구조화 출력인가:** Gemini 2.5는 `thinking + function calling` 조합에서 `MALFORMED_FUNCTION_CALL`을 빈번히(측정 ~12%) 낸다. 응답을 `response_schema`(제약 디코딩, `{message, updates}`)로 강제하면 형식 오류가 구조적으로 불가능해, thinking을 켠 채로도 실패하지 않는다. 검토 완료 코멘트 생성(`generate_comment`)은 반대로 thinking을 끄고(`thinking_budget=0`) 토큰 한도를 높여 코멘트가 잘리지 않게 한다.

**파생 필드는 agent가 직접 수정하지 못한다 (서버 재계산):** `hours_per_week` · `hours_per_month` · `net_hourly_wage`(`AGENT_DERIVED_FIELDS`)는 LLM이 직접 손계산하면 오차가 생기므로 편집 대상에서 제외된다. agent는 기반 입력값(근무 일정, `net_salary`)만 제안하고, 승인된 수정이 반영된 직후 서버가 `recompute_derived()`로 파이프라인과 동일한 공식(주당 시간 = (퇴근−출근)×근무일, 월 시간 = 주당×4.34, 세후 시급 = `ceil_hourly_wage(세후 월급 ÷ 월 시간)`)을 적용해 이 값들을 결정론적으로 다시 채운다. 자동 재계산된 변경분도 diff(`auto=True`)에 표시된다.

**세전→세후 환산은 가상 필드로 위임 + 검산:** 본문이 세전 금액을 제시하면 agent가 `net_salary`를 직접 계산하지 않고 가상 입력 필드 `net_salary_pretax`(세전 월급, 연봉이면 ÷12)로 제안한다. 서버가 `_normalize_updates()`에서 파이프라인 공식(`pipeline.salary.calculate_net_salary`)으로 세후 월급을 환산해 `net_salary`에 반영한다. 이때 diff의 reason 맨 앞에 `세전 91만원을 세후 86.46만원으로 자동 환산` 같은 환산 안내를 항상 붙여(모델이 자체 reason을 줘도 그 앞에 덧붙임) "왜 제안값이 모델이 말한 세전 금액과 다른지" 혼란을 막는다. (별도 계산기 도구를 두면 함수 호출이 늘어 thinking과 충돌하므로 가상 필드로 처리.) system_instruction에 세후 환산 회귀식(`세후월급 = 5.35 + 0.904394 × 세전월급 − 0.000143950695 × 세전월급²`)을 명시해, agent가 저장된 `net_salary`를 그냥 신뢰하지 않고 본문의 세전 금액으로 기대 세후값을 직접 검산하게 한다 — 저장값이 기대값과 허용 오차 안이면 변경이 일어나지 않고, 벗어나면 `net_salary_pretax`로 교정을 제안한다(환산 드리프트 적발). 회귀식에 4대보험·소득세 공제가 이미 반영돼 있으므로 별도 공제 메커니즘을 환각하지 않도록 못박았다.

수정 제안 가능한 필드는 `error_review` 프리셋의 편집 가능 필드에서 파생 필드를 뺀 `review_agent.AGENT_EDITABLE_FIELDS`(`= AGENT_VISIBLE_FIELDS − AGENT_DERIVED_FIELDS`)와 가상 필드 `net_salary_pretax`로 한정된다. 모달 좌측 패널에는 파생 필드를 포함한 전체 값(`AGENT_VISIBLE_FIELDS`)이 `[자동계산]` 표시와 함께 노출된다. 핵심 로직은 `postings/review_agent.py`(`propose_turn` / `apply_turn` / `generate_comment` / `build_contents` / `apply_update` / `recompute_derived` / `_normalize_updates`)에 있다.

**값 동일 판정 허용 오차(`review_verify._values_equal`):** 자동 검산의 "현재값이 사실상 맞으면 정상"(wrong_fields 제외) 판정과 agent diff(제안값이 현재값과 같으면 변경으로 치지 않음)는 같은 `_values_equal()`을 공유한다. 허용 오차는 스케일 무관 **상대 3%**(`abs(a−b) ≤ 0.03 × max(|a|,|b|)`)로 통일돼 있다 — 월급 400만원이면 ±12만원, 시급 3.5만원이면 ±0.1만원 수준으로 단위 크기에 비례해 자동 조정된다. (고정 ±0.1만원 절대 오차를 쓰던 이전 방식은 월급 스케일에서 지나치게 빡빡했다.) LLM이 읽는 `DOMAIN_RULES`에도 "약 3% 이내면 일치"로 동일하게 기술돼 있다.

**Admin 커스텀 URL (대화형 agent 검토):**

| URL 패턴 | 설명 |
|---|---|
| `review/agent-context/` | AJAX GET ?id=: 모달 좌측 패널용 케이스 컨텍스트(필드 스냅샷·본문·에러 로그) |
| `review/agent-chat/` | AJAX POST {id, messages}: 한 턴 진행 — 제안만, **DB 미변경** |
| `review/agent-tool/` | AJAX POST {id, messages, tool_call, decision, note}: 권한 박스 결정 처리. 이 엔드포인트만 (승인 시) DB를 변경한다. 거부 시 `note`(사용자가 적은 수정 방향)가 있으면 모델에 함께 전달한다 |
| `review/agent-finish/` | AJAX POST {id, messages}: 검토 완료 — 코멘트 생성 + `AdminCheck(source='agent')` + `AgentReviewSession` 영구 저장 |

### 시급 올림 보정 일괄 적용

시급 계산식이 시급을 구조적으로 살짝 낮게 평가해(예: 실제 4.0 → 3.993 저장) LLM 자동 검토에서 불필요하게 '틀림'으로 잡히는 문제가 있었다. `ceil_hourly_wages` 커맨드로 기존 데이터의 세후 시급(`net_hourly_wage`)·일회성 시급(`one_time_hourly_wage`)을 소수점 셋째 자리에서 올림(둘째 자리까지) 보정한다. 신규 수집분은 파이프라인에서 자동 보정된다.

```bash
# 변경 없이 미리보기
python manage.py ceil_hourly_wages --dry-run

# 실제 적용 (bulk_update 사용 → save() 부작용 없이 시급만 갱신)
python manage.py ceil_hourly_wages
```

### LLM 자동 검토 일괄 실행 (CLI)

웹 대시보드 버튼과 동일 로직을 CLI로 일괄 실행한다 (대량 처리·디버깅용).

```bash
python manage.py auto_verify_step3                       # 4개 프리셋 전체
python manage.py auto_verify_step3 --preset workdays_outlier
python manage.py auto_verify_step3 --limit 20
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--preset` | 특정 프리셋만 검토 (`VERIFY_PRESET_KEYS` 중 하나) | 4개 전체 |
| `--limit` | 최대 처리 건수 | 전체 |

`GOOGLE_API_KEY` 설정이 필요하다 ([환경 변수](#환경-변수) 참고).

---

## 웹 대시보드

`web` 앱이 제공하는 자체 공개 프론트엔드다. http://localhost:8011/ 에서 확인한다. 모든 시급은 세후 기준이다.

### 페이지 구성

| URL | 페이지 | 내용 |
|---|---|---|
| `/` | 홈 | 분석 공고 수, 근무 유형(전국·풀타임·주말 파트·기타 파트·일회성)별 평균 시급, 지역 5분류별 평균 시급 |
| `/compare/` | 내 시급 비교 (입력) | 사용자가 근무 일정(평일/주말 출퇴근 시각·근무일)·지역·본인 세후 시급을 입력하는 폼. 검증 후 입력값을 query string으로 결과 페이지에 전달 |
| `/compare/result/` | 내 시급 비교 (결과) | 입력 근무조건을 근무형태(풀타임/주말/기타/일회성)로 분류해, 같은 근무형태의 전국·해당 지역 시급 분포 대비 **퍼센타일**(상위 몇 %)을 계산. 바이올린 차트(내 시급 아래 영역 초록)와 "주당 근무시간 대비 시급" 산점도(회귀선 + 내 위치 별표)로 표시 |
| `/method/` | 데이터 처리 방법 | 일반 사용자용 방법론 안내. 수집 파이프라인(Gemini LLM 추출 → 자동 검증 → 검토(LLM 자동·대화형 agent·관리자) → DB)을 SVG 플로우차트로 설명하고, 시급↔월급 환산(한 달 = 4.34주)·주당 근무시간 산정((퇴근−출근)×근무일수) 규칙을 정리. 차트 없이 스냅샷의 공고 수·갱신일만 사용 |
| `/fulltime/` | 풀타임 | 주당 36시간 이상 지속성 근무. 근무시간 히스토그램·시급/월급 산점도(회귀선)·지역별 평균/분포(바이올린), 퇴직금 보정(시급 ×13/12) 토글 |
| `/weekend/` | 주말 파트 | 평일 근무 0 & 주말 근무가 있는 공고. 히스토그램·등록일별 산점도·지역별 평균·분포(바이올린) |
| `/etc/` | 기타 파트 | 36시간 미만 지속성 근무 중 주말 파트가 아닌 공고. 히스토그램·산점도(회귀선)·지역별 평균·분포(바이올린) |
| `/onetime/` | 일회성 단기 | 일회성 근무(시급은 `one_time_hourly_wage`). 등록일별 산점도·지역별 평균·분포(바이올린)·장기 vs 일회성 분포 비교 |

근무 유형 분류·지역 5분류·퇴직금 보정 등의 정의는 Notion 차트 생성기(`one_click_statistics.py`)와 동일하며, 그 정의를 matplotlib/Notion 의존성 없이 순수 계산으로 옮긴 것이 `postings/dashboard_stats.py`다.

**"내 시급 비교" 퍼센타일 계산**: 결과 페이지는 서버 집계 없이 클라이언트에서 계산한다. `compare.js`가 입력값을 query string으로 넘기면, `compare_result.js`가 (1) 주당 근무시간을 `(퇴근−출근)×근무일`로 계산하고 근무형태(주말 근무만 있으면 주말 파트, 36시간 이상이면 풀타임, 그 외 기타 파트, 일회성 선택 시 일회성)로 **백엔드와 동일한 규칙으로 분류**한 뒤, (2) 스냅샷의 `compare` 섹션에 담긴 해당 근무형태의 전국·지역 시급 값 배열에서 "내 시급보다 더 주는 공고 비율"(상위 %)을 구한다. 지역 표본이 5건 미만이면 지역 비교는 생략한다.

### 데이터 파이프라인 (스냅샷 방식)

웹 페이지는 DB를 매 요청마다 집계하지 않고, 관리자가 명시적으로 만든 **스냅샷**을 읽어 렌더한다.

```
DashboardSnapshot 갱신 (리뷰 대시보드 "대시보드 업데이트" 버튼)
    ↓
postings/dataframe.build_dataframe()      # DB 전체 → 통계 호환 DataFrame
    ↓
postings/dashboard_stats.compute_dashboard_data(df)  # 페이지별 수치·데이터셋 dict 산출
    ↓
DashboardSnapshot(data=…, posting_count=…) 저장 (created_at = "Last Update")
    ↓
web/views: 최신 스냅샷의 해당 섹션을 json_script로 템플릿에 임베드
    ↓
정적 JS(charts.js + 페이지별 *.js)가 임베드된 데이터로 SVG 차트 렌더
```

- **갱신 방법**: 리뷰 대시보드의 **최종 점검** 프리셋 그룹에 있는 **대시보드 업데이트** 버튼(`dashboardsnapshot_update` URL)을 누르면 현재 DB 전체를 집계해 새 스냅샷 한 건이 추가된다. 항상 가장 최근 스냅샷이 노출된다.
- **차트 렌더링**: `web/static/web/js/charts.js`는 데이터 입력과 분리된 순수 SVG 빌더(`buildHistogram`, `buildScatter`, `buildBubble`, 시급 분포용 `buildViolin`, "내 시급 비교"용 `buildCompare`/`buildHoursScatter` 등)로, 입력 형태만 맞으면 실데이터/목업 어느 쪽이든 동일하게 렌더한다. 페이지별 `*.js`가 임베드 데이터를 각 빌더에 바인딩한다. 근무 유형별 페이지의 지역 시급 분포는 바이올린 차트(`buildViolin`: 폭=시급대 공고 밀도, 흰 박스=IQR·중앙값, 빨간 사각형=평균)로 렌더한다.

---

## Notion 통계 생성

DB의 전체 공고 데이터를 기반으로 상세 통계 차트를 생성하고, Notion 페이지에 자동 업로드하는 기능이다.

### 사용법

```bash
# 차트 생성 + Notion 업로드
python manage.py run_statistics

# 차트만 생성 (Notion 업로드 건너뜀)
python manage.py run_statistics --skip-notion

# 차트 저장 경로 지정
python manage.py run_statistics --output-dir /path/to/output
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--output-dir` | 차트 이미지 저장 디렉토리 | `notion-stats/output/` |
| `--skip-notion` | Notion 업로드를 건너뛰고 차트 파일만 생성 | `False` |

### 동작 흐름

1. Django DB에서 `JobPosting` 전체 데이터를 DataFrame으로 변환
2. `notion-stats/one_click_statistics.py`의 `run()` 함수를 호출하여 차트 생성
3. 생성된 차트 이미지를 Notion 페이지에 업로드 (--skip-notion 미사용 시)

`.env`에 `NOTION_TOKEN` 설정이 필요하다 ([환경 변수](#환경-변수) 참고).

---

## 모듈별 설명

### `pipeline/`

| 파일 | 역할 |
|---|---|
| `prompts.py` | `QUERY_TASK_1~5`, `FEW_SHOT_1~5` 상수 — 프롬프트 문자열만 관리 |
| `tasks.py` | `run_task_1()~run_task_5()` — Gemini API 호출 후 JSON 파싱, `extract_json()` 포함 (`raw_decode`로 첫 번째 유효 JSON만 추출) |
| `runner.py` | `process_posting(body, client, model_name, log=None)` — 5개 task 오케스트레이션, `JobPosting` 필드 dict 반환. 급여 미명시 공고는 `None`을 반환하여 저장을 건너뜀. `log` 콜백을 전달하면 각 단계별 상세 로그를 받을 수 있음. 반환 dict에는 UI 현황판용 `steps`(task별 `{task, detail, error}` 요약 목록, DB 필드가 아니라 호출부에서 `pop`해 사용)도 포함된다 |
| `stages.py` | 2단계 파이프라인 공통 로직. `scrape_stage()` — 크롤링하여 `RawPosting(pending)` 저장. `process_stage()` — pending RawPosting을 일괄 LLM 처리. `process_raw_posting(raw, client, ...)` — 단일 RawPosting 처리 단위 함수(일괄 처리와 대시보드 건별 처리가 공유). 대시보드 모달용으로 `process_posting`의 `steps`와 핵심 추출 필드 요약(`_summary_fields`: 시급·월급·지역·근무형태·주당 시간)을 반환 dict에 실어 보낸다. 모두 멱등하다 |
| `validator.py` | `error_check(d, error_history)` — 시급·근무 시간 일관성 검증, 주당 근무 시간 재계산 |
| `salary.py` | `to_net_salary(wage, is_after_tax)` — 세전이면 2차 회귀 공식으로 세후 변환. `calculate_net_salary(gross_monthly)` — 세전 월급 → 세후 월급 환산(공식 본체, 대화형 agent의 세전 환산도 이 함수를 공유). `ceil_hourly_wage(value)` — 시급을 소수점 셋째 자리에서 올림(둘째 자리까지) 보정 |
| `pricing.py` | `DEFAULT_PRICING`(모델별 USD/1M tokens 단가) + `compute_cost(model, in, out)` — 토큰 수 → USD. `settings.LLM_PRICING`으로 덮어쓰기 가능, 미등록 모델은 prefix 매칭 후 flash 폴백 |
| `usage.py` | LLM 토큰 사용량 캡처/기록 유틸. `extract_usage(response)`(출력 = candidates + thoughts), `new_accumulator()`·`add_response()`(단계 내 호출 누적), `record_llm_usage(stage, model, acc, ...)`(`LLMUsageEvent` 1 row 기록 + `JobPosting` 비용 캐시 `F()` 증분, `failed`는 건너뜀) |

**직접 사용 예시:**

```python
from google import genai
from django.conf import settings
from pipeline.runner import process_posting

client = genai.Client(api_key=settings.GOOGLE_API_KEY)
result = process_posting(body="공고 본문 텍스트", client=client, model_name=settings.LLM_MODEL)
# result는 JobPosting 필드에 대응하는 dict, 급여 미명시이면 None

# 로그 콜백을 전달하면 처리 단계별 상세 로그를 받을 수 있다
result = process_posting(body="...", client=client, model_name=settings.LLM_MODEL, log=print)
```

### `scraper/`

| 파일 | 역할 |
|---|---|
| `yakdap.py` | `scrape(start_id, count, step, year=None, ..., on_item=None, on_error=None)` → `list[dict]`. `on_error(item_id, exc)`는 건별 수집 실패를 알려 호출부가 `PipelineRun.total_errors`에 집계하게 한다. 약문약답이 styled-components 해시 클래스(`sc-*`)를 쓰므로 재배포 시 깨지지 않도록, 시맨틱 클래스(`title-container`, `detail__pharmacy-name`, `detail__pharmacy-address`, `detail__message`)와 표는 라벨 텍스트 기반 XPath(급여·근무시간)로 선택한다 (`main` 기준 앵커). 등록일은 `_parse_created_at()`이 절대형(`2024년 11월 22일`)·상대형(`어제 오전 8:17`, `N시간 전`, `N분 전`, 시각만 `오전 8:36`=오늘)을 모두 `YYYY-MM-DD`로 변환한다. 절대형에 연도가 없으면 `year`(폴백, `None`이면 현재 연도)를 쓴다 |
| `pharm_recruit.py` | `scrape(big_category, year=None, ..., on_item=None)` → `list[dict]`, 자동 페이지네이션, 도시별 수집 한도(`category_limit`) 지원. 팜리크루트는 월/일만 표시되므로 등록일 연도는 `year`(`None`이면 현재 연도)로 보정한다. 중복 URL 스킵 시에도 로그를 남겨 재크롤링 진행 상황이 끊겨 보이지 않는다 |
| `pharm_recruit_urls.json` | `CITY_URL_DICT` 데이터 (big_category → city → URL 매핑). `.gitignore` 대상이므로 [초기 설정](#초기-설정) 참고하여 생성 필요 |

반환 dict의 키: `url`, `platform`, `created_at`, `title`, `pharmacy_name`, `body`, `city`, `big_category`. yakdap 레코드는 추가로 `source_id`(공고 숫자 ID)를 담아, 크롤링 진행 중 `PipelineRun.last_scraped_id` 갱신과 다음 회차 시작 ID 이어받기에 쓰인다.

`on_item` 콜백을 전달하면 공고 1건을 수집할 때마다 그 dict로 호출되어, 전체 리스트 반환을 기다리지 않고 건별 중간 저장(스테이징 단계의 `RawPosting` 저장)을 할 수 있다.

### `geo/mapping.py`

```python
from geo.mapping import normalize_city, assign_big_category

city = normalize_city("서울특별시 강남구 역삼동")  # → "서울-강남구"
big = assign_big_category("서울-강남구")            # → "서울"
```

- `conversion_dict`: 약 130개의 전체 주소 → 지역 코드 매핑 (정확 일치 → prefix 매칭 순으로 탐색)
- `big_category_dict`: 지역 코드 → 5개 대분류 매핑

### `postings/dataframe.py` · `postings/dashboard_stats.py`

웹 대시보드와 Notion 통계가 공유하는 통계 계산 모듈.

| 파일 | 역할 |
|---|---|
| `dataframe.py` | `build_dataframe()` — Django DB의 `JobPosting`을 통계 스크립트 호환 형식(한글 컬럼명, boolean → `Yes`/`No`)의 pandas DataFrame으로 변환. `run_statistics` 커맨드와 `dashboard_stats`가 함께 사용 |
| `dashboard_stats.py` | `compute_dashboard_data(df)` — 위 DataFrame을 받아 웹 페이지별(home/fulltime/weekend/etc/onetime) 수치·데이터셋과 "내 시급 비교"용 `compare` 섹션(근무형태별 전국·지역 시급 값 배열 + 근무시간-시급 산점도·회귀)을 담은 JSON 직렬화 가능한 dict 반환. `DashboardSnapshot.data`로 저장됨. matplotlib/Notion 의존성이 없는 순수 계산 |

```python
from postings.dataframe import build_dataframe
from postings.dashboard_stats import compute_dashboard_data

df = build_dataframe()
data = compute_dashboard_data(df)   # {'home': {...}, 'fulltime': {...}, ..., 'compare': {...}}
```

---

## LLM 파이프라인 상세

### Task 분기 구조

```
Task 1: 급여 정보 추출
    ├─ 급여 미명시 → None 반환 (저장 건너뜀)
    ├─ is_one_time_work = True
    │       └─ Task 2: 일회성 시급 계산
    └─ is_one_time_work = False
            ├─ Task 3: 출퇴근 시각 추출
            └─ Task 4: Task 3 결과 검토·수정
Task 5: 복리후생 추출 (급여 명시 공고만)
```

### 시급 계산 기준

- **지속성 근무**: 세전 시급 = 급여 / 월 근무 시간 (월 근무 시간 = 주당 근무 시간 × 4.34). 세후 월급 산출 후 `세후 시급 = 세후 월급 / 월 근무 시간`으로 최종 시급(net_hourly_wage) 결정
- **근무 시간은 gross 기준**: 주당 근무 시간은 `(퇴근 시각 − 출근 시각) × 근무 일수`로 계산하며, 점심·휴게 시간을 빼지 않은 출퇴근 시각 사이의 전체 시간이다. 따라서 net_hourly_wage도 이 gross 시간으로 나눈 값이다. (급여 형태가 월급·연봉이어도 net_hourly_wage는 항상 이렇게 도출되는 파생값이다.)
- **일회성 근무**: Task 2에서 LLM이 직접 계산
- 시급 유효 범위: `1.8만원 ~ 5.5만원` (settings.py에서 조정 가능)
- 주당 최대 근무 시간: `56시간`
- **시급 올림 보정**: 계산식이 시급을 구조적으로 살짝 낮게 평가하므로(예: 실제 4.0 → 3.993), 세후 시급·일회성 시급을 소수점 셋째 자리에서 올림(둘째 자리까지)하여 저장한다 (`salary.ceil_hourly_wage`). 셋째 자리가 0이면 올림이 적용되지 않아 값이 그대로 유지된다(예: 4.28 → 4.28)

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
| `inserted_at` | DateTimeField | DB 저장 시각 (`auto_now_add`) |
| `updated_at` | DateTimeField | 마지막 수정 시각 (`auto_now`) |
| `title` | TextField | 공고 제목 |
| `pharmacy_name` | CharField | 약국 이름 |
| `body` | TextField | 공고 본문 (LLM 입력 원문) |
| `city` | CharField | 지역 코드 (예: `서울-강남구`) |
| `big_category` | CharField | 지역 대분류 (예: `서울`) |
| `is_salary_disclosed` | BooleanField | 급여 명시 여부 |
| `is_one_time_work` | BooleanField | 일회성 근무 여부 |
| `one_time_hourly_wage` | FloatField | 일회성 근무 시급 (만원) |
| `net_hourly_wage` | FloatField | 세후 시급 (만원) |
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
| `has_error` | BooleanField | 에러 발생 여부 — `gpt_error_log`가 비어 있지 않으면 `save()` 시 자동으로 `True` 설정 |
| `user_comment` | TextField | 개인 메모. LLM 자동 검토 합격 시 `[LLM 합격] ...` 사유가 기록될 수 있음 (기존 사람 코멘트는 보존) |
| `llm_cost_usd` | FloatField | 이 공고에 든 LLM 누적 비용(USD). `LLMUsageEvent` 합계의 비정규화 캐시 — 단계(process→verify→agent)가 쌓일수록 커진다 (목록 정렬·"비싼 공고" 식별용) |
| `llm_total_tokens` | IntegerField | 이 공고에 든 LLM 누적 토큰. 위와 동일한 비정규화 캐시 |

> `llm_cost_usd`·`llm_total_tokens`는 표시·정렬용 비정규화 캐시이며 진실의 출처는 `LLMUsageEvent`다. 기록 시점에 `F()` 증분으로 더해진다 ([LLM 비용 모니터링](#llm-비용-모니터링) 참고).

> 검토 완료 여부는 더 이상 `JobPosting`의 boolean 필드가 아니다. 별도의 `AdminCheck` 레코드 존재 여부가 단일 판정 기준이며, 쿼리에서는 `is_reviewed`(= `Exists(AdminCheck)`, source 무관) 주석으로 사용한다.

### RawPosting

크롤링 결과를 LLM 처리 **전에** 보관하는 스테이징 레코드. 1단계(크롤링)가 공고를 한 건씩 즉시 여기에 저장하므로 도중에 멈춰도 긁은 것은 남고, 2단계(LLM 처리)는 `status='pending'`인 레코드만 순회해 `JobPosting`을 만든다. 두 단계 모두 멱등하게 만드는 핵심 모델이다 ([공고 수집 및 처리](#공고-수집-및-처리) 참고). 콘텐츠 필드(`url`·`platform`·`created_at`·`title`·`pharmacy_name`·`body`·`city`·`big_category`)는 스크래퍼가 반환하는 dict 키와 동일하다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `url` | URLField (unique) | 공고 원본 URL (중복 스킵 기준) |
| `body` 등 콘텐츠 필드 | — | 스크래퍼 dict와 동일 (`platform`, `created_at`, `title`, `pharmacy_name`, `city`, `big_category` 포함) |
| `status` | CharField (choices, db_index) | `pending`(처리 대기) / `processed`(JobPosting 생성 완료) / `skipped_no_salary`(급여 미명시로 건너뜀) / `error`(처리 중 에러). 기본값 `pending` |
| `error_log` | TextField | 처리 중 예외 발생 시 메시지 |
| `run` | ForeignKey → PipelineRun (null) | 이 레코드를 만든 크롤링 회차 |
| `scraped_at` | DateTimeField | 크롤링 저장 시각 (`auto_now_add`) |
| `processed_at` | DateTimeField (null) | LLM 처리 완료 시각 |

### AdminCheck

관리자 검토 완료 기록이자 **"검토 완료"의 단일 진실 공급원(single source of truth)**. **레코드 존재 = 검토 완료**, 레코드 없음 = 미검토. 리뷰 대시보드에서 **검토 완료**(`mark-reviewed/`)를 실행하면, 또는 LLM 자동 검토에서 값이 본문과 일치할 때 자동 생성된다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `posting` | OneToOneField → JobPosting | 검토 대상 공고 (1:1) |
| `checked_at` | DateTimeField | 검토 완료 시각 (자동 기록) |
| `source` | CharField (choices) | 검토 주체 — `admin`(관리자 직접 검토) / `llm`(LLM 자동 검토) / `agent`(대화형 agent 검토). 기본값 `admin` |

사람이 대시보드에서 **검토 완료**를 실행하면 기존 `source='llm'` 레코드는 `source='admin'`으로 승격된다.

### AgentReviewSession

대화형 agent 검토 1회의 영구 기록(트랜스크립트 + 적용된 변경 + 생성 코멘트). 한 공고를 시점을 달리해 여러 번 검토할 수 있으므로 `posting`은 ForeignKey(다대일)다. `에러 미검토` 탭에서 **✓ 검토 완료** 시 생성된다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `posting` | ForeignKey → JobPosting | 검토 대상 공고 (N:1) |
| `created_at` | DateTimeField | 세션 생성 시각 (`auto_now_add`) |
| `transcript` | JSONField | 대화 전체 (`[{role, ...}]`) |
| `applied_changes` | JSONField | 승인되어 반영된 변경 누적 (`[{field, old, new}]`) |
| `generated_comment` | TextField | 검토 완료 시 생성된 `user_comment` |

### PipelineRun

크롤링(스크래핑) 실행 이력. Admin에서 `Postings > Pipeline runs`에서 확인. LLM 처리는 대시보드가 `RawPosting`을 건별로 돌리며 `PipelineRun`을 거치지 않으므로, 이 모델은 "어떤 파라미터로 무엇을 몇 건 긁었는지"를 기록한다.

| 필드 | 설명 |
|---|---|
| `source` | `yakdap` / `pharm_recruit` (크롤링), 또는 `process` (`process_postings` 단독 실행) |
| `started_at` | 실행 시작 시각 |
| `finished_at` | 완료 시각 |
| `total_scraped` | 스크래핑된(신규 저장된) 공고 수 |
| `total_errors` | 실패한 공고 수. 크롤링 건별 수집 실패(`scrape`의 `on_error` 콜백)와 LLM 처리 실패를 모두 집계한다 |
| `status` | `running` / `done` / `failed` |
| `log_output` | 실행 중 누적되는 상세 로그. 대시보드 로그 패널에 거의 실시간으로 보이도록 한 줄마다 즉시 DB에 반영된다 |
| `start_id` · `count` · `step` | yakdap 전용. `start_id`부터 `step` 간격으로 `count`개를 순회한 크롤링 파라미터 (재현·추적용) |
| `last_scraped_id` | yakdap 전용. 이번 회차에서 **실제로 수집에 성공한 가장 큰 공고 ID**. 스크래퍼가 건별 콜백으로 넘기는 `source_id`(공고 숫자 ID)의 최댓값을 크롤링 중 계속 갱신해 저장하므로, 도중에 크래시로 멈춰도 어디까지 긁었는지 남는다. 다음 크롤링의 시작 ID 이어받기 기준이 된다 |
| `big_categories` | pharm_recruit 전용 JSONField. 이번 회차에 수집한 지역 대분류 목록(복수) |

크롤링 파라미터(`start_id`/`count`/`step`/`big_categories`)는 `pipeline/stages.scrape_param_fields(options)`가 옵션에서 추출해 run 생성 시 채운다. `last_scraped_id`는 파라미터가 아니라 크롤링 진행 중 `scrape_stage`의 `on_item`이 갱신한다. Admin 목록에는 `params_summary` 컬럼으로 한 줄 요약되며, yakdap 회차는 끝에 `(마지막 성공 {last_scraped_id})`가 덧붙는다.

**크롤링 시작 ID 이어받기**: 리뷰 대시보드의 pre-1단계 크롤링 폼(`prestage_scrape_form_view`)은 yakdap 시작 ID 기본값을 **가장 최근 yakdap 회차의 `last_scraped_id + step`**으로 채운다. `start_id + count*step` 같은 추정이 아니라 실제로 성공한 마지막 ID 기준이라, 직전 실행이 도중에 크래시했어도 빠짐없이 이어진다. 가장 최근 회차만 보므로 과거에 한 번 건드린 동떨어진 ID(아웃라이어)에 휩쓸리지 않고 현재 진행 구간을 잇는다. `count`·`step`도 그 회차에서 이어받으며, `last_scraped_id`가 없으면(한 건도 못 긁고 끝난 회차) 그 회차의 `start_id`부터 다시 시도한다. 지역 대분류 기본값은 마지막 pharm_recruit 회차 선택을 따른다.

### DashboardSnapshot

웹 대시보드용 통계 스냅샷. **최신 레코드가 현재 노출되는 대시보드 데이터**다. 리뷰 대시보드 **최종 점검** 그룹의 **대시보드 업데이트** 버튼이 DB 전체를 집계해 한 레코드를 추가한다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `created_at` | DateTimeField | 스냅샷 생성 시각 (`auto_now_add`) — 프론트의 "Last Update" |
| `data` | JSONField | `compute_dashboard_data()` 결과 (페이지별 통계 dict) |
| `posting_count` | IntegerField | 집계 대상 공고 수 (관리 목록 표시용) |

### LLMUsageEvent

LLM 한 작업 단위(**공고 1건 × 단계 1개**)의 토큰/비용 기록. 비용 추적의 **single source of truth**다. 단계 내부의 여러 Gemini 호출(예: process 단계의 Task 1~5)은 합산해 1 row로 남긴다. 자세한 정책은 [LLM 비용 모니터링](#llm-비용-모니터링) 참고.

| 필드 | 타입 | 설명 |
|---|---|---|
| `created_at` | DateTimeField (db_index) | 기록 시각 (`auto_now_add`) |
| `stage` | CharField (choices) | `process`(pre-2 프로세싱) / `verify`(LLM 자동 검토) / `agent`(대화형 agent 검토) |
| `model` | CharField | 사용한 Gemini 모델명 |
| `job_posting` | ForeignKey → JobPosting (null) | 대상 공고. skipped(급여 미명시)는 JobPosting이 없어 `None` |
| `raw_posting_id` | IntegerField (null) | skipped 등 JobPosting이 없을 때의 원문 ID |
| `status` | CharField | `ok` / `error`(저장 성공+검산 경고) / `skipped`(급여 미명시). `failed`(파이프라인 예외 중단)는 **기록하지 않음** |
| `api_calls` | IntegerField | 단계 내부 Gemini 호출 횟수 |
| `input_tokens` | IntegerField | 입력(프롬프트) 토큰 |
| `output_tokens` | IntegerField | 출력 토큰 = candidates + thoughts(사고 토큰) |
| `total_tokens` | IntegerField | 총 토큰 |
| `cost_usd` | FloatField | 기록 시점 단가(`pipeline.pricing`)로 계산해 박아넣은 **스냅샷** 비용. 단가가 나중에 바뀌어도 과거 row는 소급 변경되지 않는다 (토큰이 원본, 비용은 파생 → 필요 시 토큰 × 새 단가로 백필 가능) |

---

## LLM 비용 모니터링

Gemini API는 입력/출력 토큰을 따로 과금하므로, 파이프라인의 LLM 사용량과 비용을 추적하는 시스템을 둔다. 비용 추적의 진실의 출처는 `LLMUsageEvent` 모델이며, 세 호출 경로가 모두 이를 통해 기록된다.

### 기록 단위와 규칙

- **공고 1건 × 단계 1개 = 이벤트 1 row.** 단계 내부의 여러 Gemini 호출은 합산한다 (예: process 단계의 Task 1~5는 한 row).
- 단계는 세 가지: `process`(pre-2 프로세싱), `verify`(LLM 자동 검토), `agent`(대화형 agent 검토). agent 세션은 매 턴 누적 토큰 + 코멘트 생성 토큰을 합산해 "세션당 1 이벤트"로 남긴다.
- 정상 완료만 기록한다: `ok` / `error`(저장 성공 + 검산 경고) / `skipped`(급여 미명시). `failed`(파이프라인 예외로 중단)는 기록하지 않는다.
- skipped는 JobPosting이 없으므로 `job_posting=None`, `raw_posting_id`만 남는다. 전체 비용 = 모든 row 합, DB 등록 공고만 = `job_posting__isnull=False` 필터.

### 토큰 캡처와 비용 계산

- 토큰은 Gemini 응답의 `usage_metadata`에서 뽑는다 (`pipeline/usage.py`의 `extract_usage`). 출력 토큰은 `candidates + thoughts`(사고 토큰; 과금 대상)를 합산한다. 세 호출 경로가 usage accumulator dict를 함께 넘겨받아 단계 내 호출을 누적한 뒤 `record_llm_usage`로 1 row를 남긴다.
- 단가표는 `pipeline/pricing.py`의 `DEFAULT_PRICING`(USD/1M tokens)에 두고 `compute_cost`로 계산한다. `settings.LLM_PRICING` dict로 모델별 `(입력, 출력)` 단가를 덮어쓸 수 있으며, 미등록 모델은 prefix 매칭(예: `gemini-2.5-flash-preview-*`) 후 flash 폴백 단가를 쓴다.
- **비용은 기록 시점 단가로 계산해 `cost_usd`에 고정 저장하는 스냅샷이다.** 단가가 나중에 바뀌어도 과거 row의 비용은 소급 변경되지 않고(그때 실제로 낸 비용 보존), 통계 페이지도 저장된 `cost_usd`를 합산할 뿐 재계산하지 않는다. 토큰 수가 영구 진실이라 단가표가 바뀌면 토큰 × 새 단가로 백필(재계산)할 수 있다.
- 기록 시 `JobPosting.llm_cost_usd`·`llm_total_tokens` 비정규화 캐시도 `F()` 증분으로 함께 더해진다 (목록 정렬·"비싼(까다로운) 공고" 식별용).

### UI

- **처리/검토 모달**: pre-2 프로세싱·LLM 자동 검토 모달의 각 행에 해당 공고의 토큰/비용이 축약 표시된다(예: `22.9k`, `usage_extras.kfmt` 필터).
- **Token Usage 통계 페이지** (`review/token-usage/`): admin 홈(`/admin/`)의 **💰 Token Usage** 버튼으로 진입. `LLMUsageEvent`를 **날짜별·단계별·모델별**로 집계해 이벤트 수·고유 공고 수·입출력/총 토큰·총비용과 **공고당 평균 비용**(총비용 ÷ 처리한 고유 공고 수)을 보여준다. skipped 비용도 총비용에 포함되어 평균에 부대비용으로 반영된다.
- **공고 목록**: `JobPosting` 목록에 **LLM 비용** 컬럼(`llm_cost_usd` 기준 정렬 가능)이 추가되고, 상세 화면에 "LLM 비용 (누적)" 접이식 섹션이 있다.
- **LLMUsageEvent admin**: `Postings > Llm usage events`에서 개별 이벤트를 조회한다(읽기 전용, 수기 추가 불가). 단계·상태·모델·기록 일시로 필터하며, 각 행에서 대상 공고/원문 상세로 가는 링크 버튼을 제공한다.

`django.contrib.humanize`를 `INSTALLED_APPS`에 추가해 숫자 포매팅을 보조한다.

---

## 일회성 데이터 마이그레이션

과거 데이터를 현재 스키마로 옮기기 위한 1회성 스크립트들은 `legacy-files/one-time-data-migration/`에 모여 있다.

### JSON → SQLite 임포트

기존 Notion 데이터를 JSON으로 변환한 파일이 `data/` 폴더에 있을 경우 아래 스크립트로 SQLite에 한 번에 임포트할 수 있다.

```bash
# 파일명을 인자로 지정 (data/ 디렉토리 내 JSON 파일)
python legacy-files/one-time-data-migration/migrate_json_to_sqlite.py yakkook.json
python legacy-files/one-time-data-migration/migrate_json_to_sqlite.py output_error.json
```

- `output_error.json`, `output_error_3.json` 파일은 자동으로 `error_corrected=True`로 삽입
- 그 외 파일은 `error_corrected=False`로 삽입
- 중복 URL은 `get_or_create`로 자동 스킵
- 한국어 날짜 형식(`2024년 9월 19일`) 자동 변환
- `"TRUE"` / `"FALSE"` 문자열 → Python bool 자동 변환
- NaN → None 자동 변환

### 레거시 AdminCheck 백필 (완료된 1회성 작업)

과거 JSON 임포트로 들어온 검토 완료 공고들은 (이제는 제거된) 구 `user_reviewed=True` 플래그만 있고 그에 대응하는 `AdminCheck` 레코드가 없었다. `AdminCheck` 존재 여부를 검토 완료의 단일 기준으로 전환하면서, 이 공고들에 `AdminCheck`를 일괄 생성하는 1회성 백필을 수행한 뒤 `user_reviewed` 필드를 폐기(migration 0008)했다. 백필 레코드의 `checked_at`은 레거시 표식으로 `2000-01-01`(KST)로 설정해 일반 검토 기록과 구분했다. 이미 완료된 작업으로, 관련 1회성 커맨드는 코드베이스에서 제거되었다.
