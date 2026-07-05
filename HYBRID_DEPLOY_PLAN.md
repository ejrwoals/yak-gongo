# 하이브리드 배포 아키텍처 계획

> 공개용 "얼마줄약"(약사 시급 리포트) 페이지는 Cloud Run으로 배포하고,
> 크롤링 · LLM · 데이터 가공은 로컬 관리자 서버에서만 수행하는 구조.

---

## 1. 결론 먼저: 가능하다 ✅

현재 코드 구조상 이 하이브리드는 **깔끔하게 구현 가능**하다. 근거는 다음과 같다.

- 공개 페이지(`web` 앱)가 런타임에 DB에서 실제로 읽는 데이터는 **오직 최신 `DashboardSnapshot` 한 행**뿐이다.
  - [web/views.py](web/views.py) 의 `_latest_snapshot()` → `DashboardSnapshot.objects.order_by('-created_at').first()`
  - 이 스냅샷의 `data`(JSON) 하나로 home / fulltime / weekend / etc / onetime / compare 전 페이지가 렌더된다.
- `/compare/result/` 는 **이미 브라우저에서 계산**한다(퍼센타일·분류 전부 client-side). 백엔드 API가 필요 없다.
  - [web/static/web/js/compare_result.js](web/static/web/js/compare_result.js)
- 나머지 무거운 것들(JobPosting · RawPosting 원본, 어드민, 크롤러, LLM 호출, `selenium`/`pandas`/`google-genai` 등)은 **전부 관리자 전용**이라 배포본에 포함할 필요가 없다.

따라서 배포본은 **"web 앱 + 스냅샷 JSON 하나"** 로 극단적으로 가벼워질 수 있다.

---

## 2. 핵심 아이디어: 스냅샷을 "배포 아티팩트"로 분리

현재: 공개 페이지가 **로컬 SQLite의 `DashboardSnapshot` 테이블**을 읽는다.

변경: 공개 페이지가 **번들된 JSON 파일 `web/snapshot/latest.json`** 을 읽도록 추상화한다.

```
[로컬 관리자]                                   [Cloud Run 배포본]
JobPosting(원본 수천건)                          (DB 없음 / 원본 없음)
  ↓ build_dataframe + compute_dashboard_data
DashboardSnapshot (SQLite)  ──export──▶  web/snapshot/latest.json  ──▶  web 앱이 이 파일을 읽어 렌더
```

이렇게 하면:
- 배포본에 **SQLite DB 자체를 넣지 않아도 된다** → 36MB 원본 데이터(크롤링 원문, LLM 로그, 비용 등)가 공개 서버로 새어나갈 위험 제거.
- 배포 이미지가 극도로 가벼워짐 → Cloud Run 콜드스타트 빠르고 저렴.
- `web` 앱이 `postings` 모델/DB에 대한 런타임 의존을 잃음 → 배포본 `requirements`에서 selenium/pandas/genai 전부 제거 가능.

### 대안 비교 (참고)

| 방식 | 장점 | 단점 | 채택 |
|---|---|---|---|
| **A. 스냅샷 JSON 아티팩트** | 배포본 초경량, 원본 데이터 노출 0, 의존성 최소 | 스냅샷 로딩 추상화 코드 필요 | ✅ **권장** |
| B. 전체 Django + SQLite 통째 배포 | 코드 변경 거의 없음 | 36MB 원본·어드민이 공개 서버에 올라감(보안·용량), Cloud Run 파일시스템은 휘발성이라 쓰기 안 됨 | ❌ |
| C. 완전 정적(HTML) 호스팅 | 서버조차 불필요 | Django 템플릿을 정적으로 프리렌더해야 함, compare 폼 라우팅 재작성 필요 | 보류 |

> C안도 이론적으로 매력적이지만(페이지가 거의 정적이라), 네가 Cloud Run을 원했고 기존 Django 템플릿을 그대로 재사용하는 게 마이그레이션 비용이 가장 낮다. 우선 A안으로 간다.

---

## 3. 배포본 구성 요소

Cloud Run에 올라갈 최소 Django 앱:

- **INSTALLED_APPS**: `web` + Django 최소 세트. `postings`는 (모델 참조 때문에) 넣되, 파이프라인/크롤러 코드는 import되지 않으므로 무해. 다만 스냅샷을 JSON에서 읽으면 `postings` 모델 의존조차 끊을 수 있다(4번 참조).
- **정적 파일**: `whitenoise`로 Django가 직접 서빙(별도 nginx/CDN 불필요).
- **WSGI 서버**: `gunicorn`.
- **DB**: 공개 페이지는 세션/로그인/DB 불필요. 이상적으로는 **DB 없이** 동작.
  - Django가 기본적으로 DB를 요구하지만, 공개 라우트는 ORM을 안 타게 만들면 마이그레이션조차 불필요. (안전하게는 컨테이너 내부에 빈 ephemeral SQLite 하나 두고 `migrate`만 돌려도 됨. 데이터는 안 씀.)
- **설정 분리**: `config/settings_prod.py` (또는 `DJANGO_ENV` 분기).
  - `DEBUG=False`
  - `ALLOWED_HOSTS = ['*.run.app', '<커스텀도메인>']`
  - 어드민 URL 비활성화 (배포본에서 `/admin/` 라우트 제거)
  - `SECRET_KEY`는 환경변수/Secret Manager
  - `GOOGLE_API_KEY` 등 LLM 키는 **배포본에 절대 포함 안 함**

### 새로 추가할 파일

```
Dockerfile                     # 경량 python 이미지 + gunicorn + whitenoise
requirements-web.txt           # django, gunicorn, whitenoise, python-dotenv 만
config/settings_prod.py        # 프로덕션 설정 (또는 settings.py 내 DJANGO_ENV 분기)
deploy.sh                      # 스냅샷 export → 빌드 → Cloud Run 배포
.gcloudignore                  # data/, .venv/, scraper/, pipeline/ 등 제외
web/snapshot/latest.json       # export된 스냅샷 (gitignore 대상, 빌드시 생성)
```

---

## 4. 코드 변경 지점 (최소 침습)

### 4-1. 스냅샷 로딩 추상화 — [web/views.py](web/views.py)

지금:
```python
def _latest_snapshot():
    return DashboardSnapshot.objects.order_by('-created_at').first()
```

변경(개념):
```python
def _latest_snapshot_data():
    # 프로덕션: 번들된 JSON 파일에서 읽음 (DB 불필요)
    if settings.SNAPSHOT_FROM_FILE:
        return _load_snapshot_file()      # web/snapshot/latest.json
    # 로컬: 기존대로 DB에서
    snap = DashboardSnapshot.objects.order_by('-created_at').first()
    return {'data': snap.data, 'posting_count': snap.posting_count,
            'created_at': snap.created_at} if snap else None
```

- `data`, `posting_count`, `created_at(lastUpdate)` 세 가지만 있으면 모든 뷰가 동작한다.
- 로컬/프로덕션 동작을 `settings.SNAPSHOT_FROM_FILE` 플래그로 분기.

### 4-2. 스냅샷 export 관리 명령 — 신규 `postings/management/commands/export_snapshot.py`

```
manage.py export_snapshot  →  최신 DashboardSnapshot을 web/snapshot/latest.json 으로 덤프
                              ({data, posting_count, created_at} 포함)
```

`deploy.sh`가 빌드 직전에 이걸 호출한다.

### 4-3. `web` 앱을 postings에서 디커플 (선택, 권장)

`_latest_snapshot_data()`가 파일 모드일 땐 `DashboardSnapshot` 모델을 import하지 않도록 지연 import 처리 → 배포본이 `postings` 앱·DB 없이도 뜬다.

> 이 3개 변경은 **기존 로컬 동작을 전혀 깨지 않는다**(플래그 off가 기본).

---

## 5. "대시보드 업데이트" 버튼 → 배포 연동

현재 흐름([postings/admin.py](postings/admin.py) `update_view`):
1. `build_dataframe()` → 전체 JobPosting 읽기
2. `compute_dashboard_data(df)` → 통계 계산
3. `DashboardSnapshot.objects.create(...)` → 새 스냅샷 저장

여기에 **배포 트리거**를 어떻게 붙일지 두 가지 안:

### 안 (가) — 버튼이 곧 배포 (원래 네 아이디어)
`update_view` 마지막에 `deploy.sh`를 `subprocess`로 실행(백그라운드 스레드).
- 장점: 클릭 한 번 = 배포 완료. UX 단순.
- 단점: 배포는 수십 초~수 분 걸리고 gcloud 인증·빌드가 필요 → 웹 요청 안에서 돌리면 취약. 실패 시 피드백이 admin 화면에 안 뜸.
- 보완: 백그라운드 스레드로 던지고, 로그를 파일/`PipelineRun` 유사 모델에 남겨 admin에서 상태 확인.

### 안 (나) — 스냅샷 저장과 배포 분리 (권장)
- 버튼은 지금처럼 **스냅샷만 저장**(로컬 확인용).
- admin에 **별도 "배포하기" 버튼**을 두거나, 터미널에서 `./deploy.sh` 수동 실행.
- 장점: 스냅샷을 로컬에서 먼저 검수하고, 만족스러울 때만 배포. 배포 실패가 데이터 갱신과 분리됨.
- 절충안: "대시보드 업데이트" 버튼 옆에 체크박스 `[ ] 배포까지 실행` 을 둔다.

> **권장: 안 (나)**. "로컬 스냅샷 갱신"과 "공개 배포"는 성격이 다른 작업이라 분리하는 게 안전하다. 검수 후 배포 흐름과도 자연스럽게 맞는다(이미지의 "최종 점검 → 대시보드 업데이트" 단계 뒤에 "배포" 한 스텝 추가).

---

## 6. `deploy.sh` 동작 시나리오

```bash
#!/usr/bin/env bash
set -euo pipefail

# 1. 최신 스냅샷을 JSON으로 export (로컬 DB → web/snapshot/latest.json)
.venv/bin/python manage.py export_snapshot

# 2. 정적 파일 collectstatic (whitenoise용)
.venv/bin/python manage.py collectstatic --noinput --settings=config.settings_prod

# 3. Cloud Run 배포 (Cloud Build가 Dockerfile로 이미지 빌드 → 배포)
gcloud run deploy yak-report \
  --source . \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --set-env-vars "DJANGO_ENV=prod,SNAPSHOT_FROM_FILE=1"
```

- `.gcloudignore`로 `data/`, `.venv/`, `scraper/`, `pipeline/`, `notion-stats/` 등 업로드 제외 → 원본 데이터·크롤러 코드가 클라우드로 안 감.
- 결과: `https://yak-report-xxxx.run.app` 로 공개.

---

## 7. 데이터 흐름 요약

```
[로컬 관리자 서버 — 배포 안 함]
  크롤링(selenium) → RawPosting → LLM(gemini) → JobPosting → 검수(admin)
        → "대시보드 업데이트" → DashboardSnapshot (SQLite)
                                        │
                                        │  ./deploy.sh (관리자가 검수 후 실행)
                                        ▼
                              export_snapshot → web/snapshot/latest.json
                                        │  gcloud run deploy --source .
                                        ▼
[Cloud Run — 공개]
  경량 Django(web 앱 only) + whitenoise + gunicorn
  latest.json 읽어 home/compare/카테고리 페이지 렌더 (DB·원본 없음)
```

---

## 8. 구현 체크리스트

- [ ] `web/views.py` 스냅샷 로딩을 `SNAPSHOT_FROM_FILE` 플래그로 추상화 (파일/DB 분기)
- [ ] `postings/management/commands/export_snapshot.py` 작성
- [ ] `config/settings_prod.py` (DEBUG off, ALLOWED_HOSTS, whitenoise, admin 제거, SECRET_KEY env)
- [ ] `requirements-web.txt` (django, gunicorn, whitenoise, python-dotenv)
- [ ] `Dockerfile` (python-slim + gunicorn 엔트리포인트)
- [ ] `.gcloudignore` (data/·크롤러·파이프라인·venv 제외)
- [ ] `deploy.sh` (export → collectstatic → gcloud run deploy)
- [ ] 배포본에서 `/admin/` 및 파이프라인 라우트 미포함 확인
- [ ] compare_result 등 client-side 페이지가 파일 스냅샷으로도 정상 동작하는지 로컬에서 `SNAPSHOT_FROM_FILE=1`로 검증
- [ ] (선택) admin "대시보드 업데이트" 옆 "배포하기" 액션 추가

---

## 9. 사전 준비물 (인프라)

- GCP 프로젝트 + 결제 계정
- `gcloud` CLI 설치 및 로그인 (`gcloud auth login`, `gcloud config set project ...`)
- Cloud Run + Cloud Build API 활성화
- (선택) 커스텀 도메인 매핑
- `SECRET_KEY`는 Secret Manager 또는 `--set-env-vars`로 주입

---

## 10. 리스크 · 유의사항

- **콜드스타트**: Cloud Run은 트래픽 없으면 인스턴스가 0으로 줄어 첫 요청이 느릴 수 있음(수백 ms~수 초). 공개 리포트 성격상 대체로 허용 가능. 필요시 `--min-instances=1`.
- **스냅샷-코드 정합성**: 템플릿/JS 구조가 바뀌면 스냅샷 JSON 스키마와 안 맞을 수 있음 → `data` 스키마를 바꿀 때 export 포맷도 함께 갱신.
- **배포 인증**: `deploy.sh`는 로컬 gcloud 인증에 의존. admin 버튼에서 subprocess로 돌릴 경우 실행 유저의 gcloud 인증이 필요(안 (나) 권장 이유).
- **캐시**: 브라우저/CDN 캐시 때문에 배포 후 갱신이 즉시 안 보일 수 있음 → 정적 파일 해시 붙이기(whitenoise가 처리) + HTML은 짧은 캐시.
```
