# Yak-Gongo 리팩토링 마스터 플랜

## 개요

약문약답·팜리크루트에서 수집한 약국 구인 공고 데이터를 분석하는 프로젝트를
Notion 기반 → **Django + SQLite** 기반으로 전면 리팩토링한다.

- **데이터 저장소**: Notion → SQLite (`data/db.sqlite3`)
- **데이터 검토 UI**: Django Admin (개인용)
- **통계 페이지**: Django 웹앱 (공개용)
- **LLM**: Google Gemini API (1차) + OpenAI GPT-4o (오류 폴백)
- **패키지 관리**: `uv`

---

## 아키텍처

```
yak-gongo/
├── config/             Django 프로젝트 설정
├── postings/           핵심 앱 — JobPosting 모델, Admin
├── pipeline/           LLM 파이프라인 (tasks, runner, validator, salary)
├── geo/                주소 정규화 (mapping.py)
├── scraper/            웹 스크래퍼 (yakdap.py, pharm_recruit.py)
├── stats/              통계 웹 페이지 앱
├── scripts/            일회성 스크립트 (DB 마이그레이션 등)
├── data/               SQLite DB, JSON/CSV 원본 데이터 (gitignore)
├── docs/               문서
└── legacy-files/       구 코드 보관 (gitignore)
```

---

## Phase 별 진행 현황

### Phase 1 — 데이터 분석 및 마이그레이션 설계 ✅
- 기존 Notion CSV 데이터 구조 파악
- `one-time-data-migration/`: CSV → JSON 변환 스크립트 작성
- 총 3,452건 데이터 확인

### Phase 2 — Django 프로젝트 초기 셋업 ✅
- Django 6.x 프로젝트 생성 (`config/`)
- `uv`로 가상환경 및 패키지 관리
- SQLite DB 경로 설정 (`data/db.sqlite3`)
- 한국어 로케일 적용 (`ko-kr`, `Asia/Seoul`)

### Phase 3 — 핵심 모델 설계 ✅
- `postings/models.py`: `JobPosting`, `PipelineRun` 모델
- 주요 필드 그룹:
  - 공고 기본 정보 (url, platform, title, pharmacy_name, body, city, big_category)
  - 급여 정보 (is_salary_disclosed, wage_type, hourly_wage, net_salary 등)
  - 근무 일정 (weekday/weekend work_days, start/end time, hours_per_week/month)
  - 복리후생 (monthly_leave, experience_required, meal_info)
  - LLM 메타데이터 (llm_model, gpt_summary, gpt_output_log, gpt_error_log)
  - 검토 정보 (has_error, user_reviewed, user_comment)

### Phase 4 — Django Admin 커스터마이징 ✅
- `postings/admin.py`: `JobPostingAdmin`
  - list_display, list_filter, search_fields 설정
  - fieldsets으로 섹션 분류 (급여/일정/복리후생/LLM/검토)
  - 긴 필드(body, gpt_output_log)는 collapsed
  - `user_reviewed` 인라인 편집 가능
- 서버 기동 후 Admin 정상 동작 확인 ✅

### Phase 5 — JSON → SQLite 마이그레이션 ✅
- `scripts/migrate_json_to_sqlite.py`
- `yakkook.json` (3,452건) + `output_error.json` (509건) 로드
- 한국어 날짜(`2024년 9월 19일`) → ISO 변환
- `'Yes'/'No'` → bool, `NaN` → None 변환
- `get_or_create`로 URL 기준 중복 제거
- 최종 **3,454건** 마이그레이션 완료

### Phase 6 — LLM 파이프라인 모듈화 ✅
- `pipeline/prompts.py`: Task 1~5 프롬프트 + few-shot 예시
- `pipeline/tasks.py`: Gemini API 호출 (`google-genai` 패키지)
  - `_call_gemini()` → `client.models.generate_content()`
  - `extract_json()`: 응답에서 JSON 파싱
  - `run_task_1/2/3/4/5()`
- `pipeline/validator.py`: LLM 출력 검증 및 파생값 계산
  - 시급 범위 체크 (1.8 ~ 5.5만원)
  - 주간 근무시간 상한 체크 (56시간)
- `pipeline/salary.py`: 세후 급여 역산
  - `y = 5.35 + 0.904394x - 0.000143950695x²` (이차회귀)
- `pipeline/runner.py`: 파이프라인 오케스트레이터
  - 일회성 공고: Task1 → Task2
  - 지속 공고: Task1 → Task3 → Task4
  - 공통: Task5 (복리후생)
- `geo/mapping.py`: 주소 정규화
  - `conversion_dict` (~130개 항목)
  - `assign_big_category()`: 서울/지방/경기중부/경기외곽/인천

### Phase 7 — 스크래퍼 모듈화 ✅
- `scraper/yakdap.py`: 약문약답 스크래퍼 → `list[RawPosting]` 반환
- `scraper/pharm_recruit.py`: 팜리크루트 스크래퍼 → `list[RawPosting]` 반환
- `postings/management/commands/run_pipeline.py`: Django management command

### Phase 8 — 통계 웹 페이지 ✅
- `stats/charts.py`: `legacy_statistics.py`의 차트 함수 이전
- `stats/views.py`: 통계 데이터 쿼리 및 렌더링
- `stats/templates/stats/dashboard.html`: 공개용 통계 대시보드

### Phase 9 — 정리 ✅
- Notion 의존성 완전 제거
- `.env.example` 작성
- README.md 정비

---

## LLM 파이프라인 흐름

```
공고 body 텍스트 입력
        │
   [Task 1] 급여 정보 + 일회성 여부 추출
        │
   is_one_time?
   ├── True  → [Task 2] 일회성 근무 일정 + 시급 계산
   └── False → [Task 3] 평일/주말 근무 일정 추출
                     │
               [Task 4] Task 3 결과 검토·보정
        │
   [Task 5] 복리후생 추출 (공통)
        │
   [validator] 급여·시간 일관성 검증 + 파생값 계산
        │
   [salary] 세전 → 세후 급여 환산
        │
   JobPosting 저장
```

---

## 주요 설정값 (`config/settings.py`)

| 항목 | 값 |
|---|---|
| `LLM_MODEL` | `gemini-1.5-flash-latest` (env 오버라이드 가능) |
| `FALLBACK_LLM_MODEL` | `gpt-4o` |
| `MIN_HOURLY_WAGE` | 1.8 (만원) |
| `MAX_HOURLY_WAGE` | 5.5 (만원) |
| `MAX_WORK_HOURS_PER_WEEK` | 56 |
| `WEEKS_PER_MONTH` | 4.34 |

---

## 지역 분류

| big_category | 해당 지역 |
|---|---|
| 서울 | 서울 전 구 |
| 경기 중부 | 성남, 수원, 용인, 화성, 안양, 과천 등 |
| 경기 외곽 | 평택, 안산, 시흥, 파주, 양주 등 |
| 인천 | 인천 전 구 |
| 지방 | 그 외 전국 |
