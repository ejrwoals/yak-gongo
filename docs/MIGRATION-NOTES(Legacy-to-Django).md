# Legacy → Django 마이그레이션 변경 노트

## 개요

기존 코드는 Google Colab에서 실행하던 Jupyter Notebook을 `.py`로 변환한 파일들이었다.
셀 단위로 쌓인 코드가 하나의 거대한 파일에 들어있는 구조로, 재사용·유지보수가 어려웠다.
이를 Django 기반의 모듈화된 웹 애플리케이션으로 전면 리팩토링했다.

---

## 1. 데이터 저장소

| 항목 | Legacy | 현재 |
|---|---|---|
| 저장소 | Notion 데이터베이스 | SQLite (`data/db.sqlite3`) |
| 인터페이스 | Notion API (`requests`) | Django ORM |
| 검토 UI | Notion 페이지 직접 편집 | Django Admin |
| 데이터 조회 | Notion 필터/정렬 | Admin list_filter, search |

### 마이그레이션 경로

```
Notion → CSV export → one-time-data-migration/ → yakkook.json / output_error.json
                                                          ↓
                                           scripts/migrate_json_to_sqlite.py
                                                          ↓
                                                  data/db.sqlite3 (3,454건)
```

변환 시 처리한 타입:
- 한국어 날짜 `2024년 9월 19일` → ISO `2024-09-19`
- `'Yes'/'No'/'TRUE'/'FALSE'` → `bool`
- `NaN` → `None`
- URL 기준 중복 제거 (`get_or_create`)

---

## 2. LLM 파이프라인

### 모델 변천사

| 시기 | 모델 | 방식 |
|---|---|---|
| 초기 | `yanolja/EEVE-Korean-Instruct-10.8B-v1.0` | 로컬 실행 (Colab GPU) |
| 중기 | `gemini-1.5-pro-latest` | Gemini API |
| 현재 | `gemini-1.5-flash-latest` | Gemini API (`google-genai`) |

### 에러 처리 방식 변화

**Legacy (2단계 분리 배치)**
```
step1: Gemini/로컬LLM으로 전체 처리
       → has_error=True 건 → output_error.csv 저장
step2: output_error.csv를 GPT-4o로 재처리 (수동 실행)
       → Notion 레코드 업데이트
```

**현재 (Admin 수동 검토)**
```
run_pipeline: Gemini로 전체 처리
              → has_error=True 건은 DB에 그대로 저장
              → Admin에서 관리자가 직접 검토 후 user_reviewed 체크
```

(폴백 LLM 로직은 아직 구현하지 않았다.)

### 파이프라인 흐름

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

### SDK 변경

| 항목 | Legacy | 현재 |
|---|---|---|
| 패키지 | `google-generativeai` (deprecated) | `google-genai` |
| 클라이언트 | `genai.GenerativeModel(model)` | `genai.Client()` |
| API 호출 | `model.generate_content(prompt)` | `client.models.generate_content(model, ...)` |

---

## 3. 코드 구조

### Legacy 파일 구성

```
llm_step1_primary_runner.py   ← 6,000+ 줄 단일 파일
                                  (스크래핑 + LLM + 검증 + Notion 업로드 전부 포함)
llm_step2_error_fallback.py   ← 에러 건 GPT-4o 재처리
statistics.py                 ← 통계 분석 및 차트 (Jupyter 변환)
scraper/scrape_yakdap.py      ← 약문약답 스크래퍼
scraper/scrape_pharm_recruit.py ← 팜리크루트 스크래퍼
```

### 현재 모듈 구성

```
pipeline/
  prompts.py      ← Task 1~5 프롬프트 + few-shot (순수 데이터)
  tasks.py        ← Gemini API 호출 함수 (run_task_1~5)
  validator.py    ← error_check() 검증 로직
  salary.py       ← 세전→세후 급여 환산 (이차회귀식)
  runner.py       ← 파이프라인 오케스트레이터

geo/
  mapping.py      ← 주소 정규화, big_category 분류

scraper/
  yakdap.py       ← 약문약답 스크래퍼 (list[RawPosting] 반환)
  pharm_recruit.py ← 팜리크루트 스크래퍼 (list[RawPosting] 반환)

postings/
  models.py       ← JobPosting, PipelineRun Django 모델
  admin.py        ← Admin 커스터마이징
  management/commands/run_pipeline.py ← Django management command

stats/
  charts.py       ← 통계 차트 (base64 PNG)
  views.py        ← 대시보드 뷰
  templates/      ← HTML 템플릿
```

---

## 4. 실행 방식

| 항목 | Legacy | 현재 |
|---|---|---|
| 실행 환경 | Google Colab (노트북) | 로컬 Django 서버 |
| 파이프라인 실행 | 셀 직접 실행 | `python manage.py run_pipeline --source yakdap` |
| 패키지 관리 | `pip install` (셀 내 직접) | `uv pip install -r requirements.txt` |
| 환경변수 | Colab secrets / 하드코딩 | `.env` + `python-dotenv` |

---

## 5. 주요 설정값 (`config/settings.py`)

| 항목 | 값 |
|---|---|
| `LLM_MODEL` | `gemini-1.5-flash-latest` (env 오버라이드 가능) |
| `FALLBACK_LLM_MODEL` | `gpt-4o` |
| `MIN_HOURLY_WAGE` | 1.8 (만원) |
| `MAX_HOURLY_WAGE` | 5.5 (만원) |
| `MAX_WORK_HOURS_PER_WEEK` | 56 |
| `WEEKS_PER_MONTH` | 4.34 |

---

## 6. 지역 분류 (`geo/mapping.py`)

| big_category | 해당 지역 |
|---|---|
| 서울 | 서울 전 구 |
| 경기 중부 | 성남, 수원, 용인, 화성, 안양, 과천 등 |
| 경기 외곽 | 평택, 안산, 시흥, 파주, 양주 등 |
| 인천 | 인천 전 구 |
| 지방 | 그 외 전국 |
