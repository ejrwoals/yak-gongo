# 파생 필드 자동 재계산 계획 (Derived Fields Recompute)

## 배경 / 문제

`AI agent 대화형 검토`에서 모델이 `update_posting_fields` 도구로 필드를 수정할 때,
**파생 필드까지 LLM이 직접 손계산한 값**을 그대로 DB에 써넣고 있다. 파생 필드는
원래 파이프라인에서 결정론적 공식으로 산출되는 값인데, LLM이 매번 다시 계산하면
파이프라인 원본과 **미세하게 어긋난 값**이 누적된다.

### 실제로 관찰된 드리프트

| 필드 | LLM이 써넣은 값 | 파이프라인 정답 | 원인 |
|---|---|---|---|
| `hours_per_month` | 26.09 | `6 × 4.34 = 26.04` | LLM이 다른 환산 계수(≈4.348) 사용 |
| `net_salary` | 108.86 | 회귀 공식 적용값 | LLM이 `net_hourly × hours` 단순 곱셈 |
| `net_hourly_wage` | (올림 누락) | `ceil_hourly_wage` 보정값 | 올림 보정 미적용 |

## 파생 관계 정리

| 필드 | 성격 | 재계산 입력 | 레거시 DB에 입력 있음? |
|---|---|---|---|
| `hours_per_week` | 순수 산술 | 근무일 × (퇴근−출근) | ✓ |
| `hours_per_month` | 순수 산술 | `hours_per_week × 4.34` | ✓ |
| `net_hourly_wage` | 산술 | `ceil(net_salary ÷ hours_per_month)` | ✓ |
| `net_salary` | **세금 변환** | 세전 gross + `is_after_tax` + `wage_type` | ✗ (버려짐) |

> 핵심: `net_salary`만 세금 변환이라 별도 입력이 필요하고, 나머지 셋은 이미 DB에
> 있는 값만으로 100% 재계산된다. 관찰된 드리프트의 대부분은 산술 cascade 필드에서 발생한다.

### 정규 함수 (단일 출처)

재계산은 파이프라인과 **동일한 함수**를 재사용해 드리프트를 원천 차단한다.

- `pipeline/salary.py :: calculate_net_salary` — 세전 월급 → 세후 월급 (2차 회귀)
- `pipeline/salary.py :: to_net_salary` — 세전/세후 분기 변환
- `pipeline/salary.py :: ceil_hourly_wage` — 시급 올림 보정
- `hours_per_month = hours_per_week × 4.34` — 월 환산 계수 (`pipeline/runner.py`)

## is_after_tax 문제

`is_after_tax`·세전 원본 급여(`wage`)·`wage_type`은 `pipeline/runner.py`의 Task1 추출 시
계산되지만 **DB에 일부러 저장하지 않는다**(현행 주석: "세후 환산 계산에만 쓰는 중간값").
net_salary를 만든 뒤 버려지므로, 나중에 net_salary를 처음부터 재계산할 수 없다.

→ 해결: 이미 계산하는 그 중간값을 **버리지 말고 저장**한다. 단, 레거시 행은 이 값이
없으므로 아래 "레거시 / Backfill 전략"으로 별도 처리한다.

---

## 구현 현황 (Interim — 마이그레이션 없이 선반영)

마이그레이션 없이 즉시 정확도를 올릴 수 있는 부분을 먼저 반영했다. 모두 `postings/review_agent.py` 중심.

**완료**
- **세전→세후 환산 위임** (`net_salary_pretax` 가상 필드): 본문이 세전 금액을 제시하면 모델은
  net_salary 대신 net_salary_pretax 로 세전 월급을 제안하고, 서버 `_normalize_updates()` 가
  파이프라인 공식(`salary.py :: calculate_net_salary`)으로 net_salary 로 환산한다. 별도 '도구'가
  아니라 update_posting_fields 의 인자로 처리 → 함수 선언은 하나로 유지(아래 주의 참고).
- **파생 필드 편집 금지**: `hours_per_week`·`hours_per_month`·`net_hourly_wage` 를
  `AGENT_EDITABLE_FIELDS` 에서 제외(`AGENT_DERIVED_FIELDS`). 패널·스냅샷에는 `AGENT_VISIBLE_FIELDS`
  로 계속 표시하되 `(자동계산)` 으로 표기.
- **승인 직후 자동 재계산**: `recompute_derived()` 를 `apply_update()` 에 통합. 기반 입력값
  반영 후 파이프라인 공식으로 파생 필드를 다시 채우고, 변경분을 `auto=True` diff 로 UI 노출.
- 회귀 테스트: `postings/tests.py` (편집 금지·세전 환산·재계산·관찰된 26.04 케이스).

> **주의 (Gemini MALFORMED_FUNCTION_CALL → 구조화 출력으로 전환)**: agent 는 원래 function-calling
> (`update_posting_fields`)으로 수정안을 받았는데, Gemini 2.5 Flash 는 '함수호출 + thinking' 조합에서
> MALFORMED 을 자주 낸다. 측정값(케이스 3196, 첫 브리핑 턴): 함수선언 2개+thinking ≈ 25–50%,
> 1개+thinking ≈ 12%, thinking off ≈ 0%, **구조화 출력(response_schema)+thinking ≈ 0% (12/12)**.
> `update_posting_fields` 는 외부 함수가 아니라 '필드 목록 받아내기'였으므로 function-calling 을 버리고
> **response_schema(JSON: message + updates)** 로 전환했다. 제약 디코딩이라 형식 오류가 구조적으로
> 불가능하고 thinking 도 유지된다. history 복원은 function part 없이 순수 텍스트로 재구성한다.

**남음 (이 문서의 본 계획)**
- §1·§2 모델 필드(`is_after_tax` 등) 저장 → `net_salary` 까지 완전 결정론 (마이그레이션 필요).
- 레거시 backfill 명령(Phase 2).

→ 현 상태로도 관찰된 드리프트(26.09, 올림 누락, net_hourly 손계산)는 **전 행에서 제거**된다.
`net_salary` 자체의 세전 회귀 정확도만 본 계획의 남은 단계로 완성한다.

---

## 구현 계획

### 1. 모델 + 마이그레이션 (`postings/models.py`)

세 개의 nullable 필드 추가 (레거시 영향 0):

```python
is_after_tax       = models.BooleanField(null=True, blank=True)   # 세후 금액 여부
gross_monthly_wage = models.FloatField(null=True, blank=True)     # 세전 월 환산 급여(만원)
wage_type          = models.CharField(max_length=20, blank=True)  # monthly/yearly/hourly
```

### 2. 파이프라인 저장 (`pipeline/runner.py`)

이미 계산하는 중간값을 `result` dict에 추가하면 `run_pipeline.py`의 `JobPosting(**pipeline_result)`로 자동 저장된다.

```python
result['is_after_tax']       = bool(is_after_tax)
result['gross_monthly_wage'] = monthly_gross
result['wage_type']          = wage_type
```

기존 "DB에는 저장하지 않는다" 주석은 저장하는 방향으로 갱신.

### 3. 결정론적 재계산 함수 (`pipeline/salary.py` 또는 헬퍼)

```
recompute_derived(posting):
    # 일회성 근무·급여 미명시는 해당 파생 필드를 건드리지 않는다.
    1. hours_per_week  ← 근무일/시각 (있을 때만)
    2. hours_per_month = hours_per_week × 4.34
    3. net_salary:
         - 입력값(gross + is_after_tax + wage_type) 있으면 → to_net_salary()로 재계산
           · wage_type=monthly/yearly → hours 변화에 불변
           · wage_type=hourly         → hours 변화에 비례 (gross = hourly × hours_per_month)
         - 입력값 없으면(레거시) → 기존 net_salary 유지
    4. net_hourly_wage = ceil_hourly_wage(net_salary ÷ hours_per_month)
    5. one_time_hourly_wage = ceil_hourly_wage(one_time_hourly_wage)
```

### 4. 승인 흐름 내 back-fill (`postings/review_agent.py :: apply_update`)

승인된 base 필드를 `setattr`한 **직후**, 같은 호출 안에서 `recompute_derived(posting)` 실행.
별도 2차 tool call 불필요. 반환 diff에 사용자 승인분 + 자동 재계산분을 함께 표시한다.

### 5. agent editable 재구성 (`postings/review_presets.py` + 시스템 프롬프트)

`_COMMON_EXPAND_EDITABLE`에서 시스템이 채우는 필드를 제거:

- 제거: `hours_per_week`, `hours_per_month`, `net_hourly_wage`
- 유지: `net_salary` (본문 판단 필요), 일정/근무 형태/`one_time_hourly_wage`
- 추가 검토: `is_after_tax`(모델이 세전/세후 오판을 교정할 수 있도록)

시스템 프롬프트에 "파생 필드는 시스템이 자동 계산하니 기반 입력값만 제안하라" 명시.

### 영향 파일 요약

- `postings/models.py` (+ 마이그레이션 1개)
- `pipeline/runner.py`
- `pipeline/salary.py` (recompute 헬퍼)
- `postings/review_agent.py`
- `postings/review_presets.py`

---

## 레거시 / Backfill 전략

레거시 행은 `is_after_tax`/`gross_monthly_wage`/`wage_type`이 없다. 단계적으로 처리한다.

### Phase 0 — 즉시 (backfill 불필요)

산술 cascade 재계산(§3의 1·2·4·5)은 레거시 행에도 **이미 있는 값**만 쓰므로,
배포 즉시 전 행에서 `hours_per_week`/`hours_per_month`/`net_hourly_wage` 드리프트가 사라진다.
**관찰된 드리프트의 대부분이 여기서 해결**된다. net_salary는 기존값을 앵커로 유지.

### Phase 1 — going forward (신규 행)

신규 파이프라인 실행분은 §2로 입력값이 저장되어 net_salary까지 완전 결정론적.

### Phase 2 — 레거시 소급 backfill (관리 명령)

`net_salary`까지 레거시에 소급 적용하려면 입력값을 복원해야 한다. 본문이 DB에 저장돼
있으므로 **Task1만 재실행**해 복원한다.

신규 관리 명령 `backfill_salary_inputs` 설계:

- **대상 선정**: `is_after_tax__isnull=True` AND `is_salary_disclosed=True` AND `body` 비어있지 않음.
  (일회성/급여 미명시는 net_salary가 null이 정상이라 제외)
- **복원**: 저장된 `body`에 `run_task_1()` 재실행 → `is_after_tax`/`급여 유형`/`급여` 회수.
  전체 파이프라인이 아닌 Task1 단일 호출이라 비용 최소.
- **검증 게이트 (중요)**: 회수한 입력으로 `to_net_salary()` 재계산한 값을 **기존 저장된
  net_salary와 대조**.
  - 허용 오차(±0.1만원, 도메인 규칙) 이내 → 입력값 저장. net_salary는 정규값으로 갱신(선택).
  - 오차 초과 → **덮어쓰지 않고 리포트에 플래그**. 사람/agent 재검토 큐로 보냄.
  - (불일치를 조용히 덮어쓰지 않는 것이 안전 원칙)
- **운영 속성**:
  - 멱등성: `is_after_tax__isnull=True` 행만 처리 → 중복 실행 안전, 중단 후 재개 가능.
  - 배치 + 레이트리밋: LLM 호출이므로 `--limit`, `--sleep` 옵션.
  - `--dry-run`: 저장 없이 일치율·플래그 건수만 리포트.
  - 로그: 처리/일치/플래그/스킵 카운트를 `PipelineRun` 또는 별도 리포트로 남김.

```
python manage.py backfill_salary_inputs --dry-run            # 영향 파악
python manage.py backfill_salary_inputs --limit 200 --sleep 0.5
```

### Backfill 의사결정 요약

| 데이터 | net_salary 정확도 | 필요 작업 |
|---|---|---|
| 신규 (Phase 1 이후) | 완전 결정론 | 없음 |
| 레거시 + Phase 0 | 기존값 유지 (이미 검증된 세후값) | 없음 |
| 레거시 + Phase 2 | 완전 결정론 (검증 통과분) | Task1 재실행 backfill |

---

## 엣지 케이스

- **일회성 근무** (`is_one_time_work=True`): `net_hourly_wage`/`net_salary`는 null이 정상.
  recompute는 이 필드를 건드리지 않고 `one_time_hourly_wage`에만 올림 보정.
- **급여 미명시**: 모든 급여 파생 필드 null → 스킵.
- **일정 정보 없음**: 출퇴근 시각 부재 시 `hours_per_week` 계산 불가 → 기존값/ null 유지.
- **월급제·연봉제** (`wage_type` monthly/yearly): net_salary는 hours 변화에 불변.
- **시급제** (`wage_type` hourly): net_salary는 hours 변화에 비례.

## 검증 / 테스트

- `postings/tests.py`: `recompute_derived`가 파이프라인 산출값과 일치하는지 골든 케이스 비교.
- 관찰된 두 케이스(net_salary 69.52 / 108.x)를 회귀 테스트로 고정.
- 일회성·급여미명시·일정누락 가드 케이스.
- backfill 검증 게이트(허용 오차 이내/초과 분기) 단위 테스트.
