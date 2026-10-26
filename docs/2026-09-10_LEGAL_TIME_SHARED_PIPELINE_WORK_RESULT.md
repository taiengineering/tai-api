# TAI SAFE 법정시간 Shared Pipeline 작업결과서

**SaaS · PAID Web · PAID Excel 공통 법정시간 구조 및 운영주기 분리**

- 작성일: 2026-09-10
- 기준 저장소: `taiengineering/tai-api`
- 기준 main: `d3777b6a56834c05718344ba73fc44f3a9cf322c`
- 성격: 작업결과서(문서 전용). 코드/DB/배포 변경 없음.
- 범위 밖: `/diagnosis-step1` 재설계, 3-sector common finalizer, 법령 내용/coverage, Check Layer, FREE/PAID action-first UI 일반 작업.

---

## 1. 문서 목적 (비개발자용)

법령에는 이행 시기·주기를 나타내는 다양한 표현이 있다.

```
"매년"   "6개월마다"   "즉시"   "상시"   "14일 이내"
```

과거에는 이 법정시간을 SaaS·유료 Web·유료 Excel이 **각자 따로 해석**할 위험이 있었다. 그럴 경우:

- 같은 법령인데 화면마다 다른 결과
- 유지보수 코드 중복
- 법적 원문 훼손(임의 trim/재작성)
- 법정주기와 회사 운영주기 혼동

이 발생할 수 있었다.

이번 작업은 이를 다음 구조로 통합했다.

```
ONE official source
+ ONE shared legal_time_normalizer
+ channel-specific presentation only
```

즉 **법령엔진이 준 동일한 시기·주기 원문을 하나의 공통 모듈이 구조화**하고, SaaS·유료 Web·Excel은 그 동일한 결과를 각 화면 목적에 맞게 표시만 한다.

---

## 2. 최종 Architecture

```
official full_result
└─ obligations_raw[]
   ├─ obligation_detail.when
   └─ enrichment.inspection_cycle
                │
                ▼
      legal_time_normalizer
                │
      legal_time_normalized
        ┌───────┼─────────┐
        ▼       ▼         ▼
      SaaS   PAID Web   PAID Excel
```

**채널별 legal-time parser = 0.** 세 채널 모두 동일한 공통 normalizer를 소비한다.

---

## 3. Source of Truth (공식 법정시간 원천)

```
timing ← full_result.obligations_raw[].obligation_detail.when
cycle  ← full_result.obligations_raw[].enrichment.inspection_cycle
```

Shared helper: `services/legal_time_normalizer.py`

주요 함수:

```
normalize_legal_time_text(text)
normalize_obligation_legal_time(raw_obligation)
```

---

## 4. Normalizer 핵심 계약

```
PURE / deterministic
DB = 0 · HTTP = 0 · LLM = 0 · LEGAL reinterpretation = 0
```

원칙:

```
source_text = 입력 원문 EXACT (trim/재작성 금지)
```

판정 가능한 **명시 패턴만** `NORMALIZED`, 그 외는 `RAW_ONLY`로 원문 보존한다. 애매하거나 복합적인 문장을 억지로 해석하지 않는다.

---

## 5. 지원 구조

normalized 유형:

```
RECURRING · EVENT_DEADLINE · CONTINUOUS · IMMEDIATE · ONE_TIME
```

상태:

```
NORMALIZED · RAW_ONLY
```

operator:

```
EVERY · WITHIN · BEFORE
```

unit:

```
DAY · WEEK · MONTH · QUARTER · HALF_YEAR · YEAR
```

---

## 6. 예시

```
"1년에 1회"    → RECURRING / EVERY / value 1 / YEAR
"14일 이내"    → EVENT_DEADLINE / WITHIN / value 14 / DAY
"즉시"         → IMMEDIATE
"상시"         → CONTINUOUS
"정기적으로"   → RAW_ONLY (source_text 보존)
```

---

## 7. 가장 중요한 정책 — 법정시간 ≠ SaaS 운영일정

법령의 시간 표현은 **회사 운영주기와 다르다.**

```
법령:      "매년 1회"
          ↓
시스템:    legal_time_normalized.cycle = RECURRING / EVERY / 1 / YEAR

그러나:
  cycle_unit · cycle_value · schedule_anchor_date · next_planned_date
  = 자동 확정하지 않음
```

법정시간은 "법이 요구하는 시기"의 구조화 결과일 뿐이고, 실제 회사가 관리할 운영주기(cycle_unit/value)와 기준일(anchor)·다음점검일(next_planned_date)은 **사용자가 확인 후 직접 설정**한다.

---

## 8. A-GUARDED 원칙

```
legal text → schedule 자동 생성 금지
```

- 사용자가 확인해서 운영주기를 설정해야 한다.
- `EVENT_DEADLINE · CONTINUOUS · IMMEDIATE · ONE_TIME · RAW_ONLY` 는 반복 운영주기를 **자동 제안하지 않는다.**
- 오직 `cycle.status == NORMALIZED ∧ type == RECURRING ∧ operator == EVERY` 인 경우에만 운영주기를 "제안"하고, 사용자가 명시적으로 클릭해야 저장된다.

---

## 9. SaaS 적용 결과

관련 구조:

```
inspection_sets
legal_operation_presentation   (canonical row snapshot)
legal_time_normalized          (read-model 런타임 파생)
```

read-model: `services/inspection_sets_svc/legal_time_read_model.py`

SaaS는 `legal_operation_presentation.timing` / `.cycle` 을 shared `normalize_legal_time_text` 에 넣어 `legal_time_normalized` 를 파생한다(GET `/inspection-sets` 응답에 additive).

---

## 10. SaaS UI 정책 (tai-admin)

관련 경로: `vue3/src/pages/inspection-anchor/`
관련 main: `48b154f51c59162dc5dfd4e94803aa30129ec6ee`

UI 동작:

- 법정 시기 원문 표시(주기/시점 각각, 문장 합성 0)
- canonical 운영주기 미설정 상태 표시("운영주기를 먼저 설정")
- 조건이 확실한 `RECURRING/EVERY` 만 "이 주기로 설정" 추천
- 사용자가 명시적으로 클릭해야 운영주기 저장
- 서버 `next_planned_date` 가 다음점검일의 SoT
- 브라우저에서 임의 next-date 계산 금지(canonical row)
- 일정 시작(anchor/next/confirmed) 후에는 운영주기 변경 불가

---

## 11. Operation Cycle

관련 API:

```
PATCH /inspection-sets/{inspection_set_id}/operation-cycle
```

관련 main: `1d8d4d6ca5c85bb70d43d29158d47a28e6e52b6e`

저장 대상:

```
cycle_unit · cycle_value
```

의미: **법령 해석값이 아니라 사용자가 확인한 회사 운영주기.** canonical row(source=LEGAL_ENGINE ∧ legal_obligation_atom_id NOT NULL)에만 허용하고, 일정이 이미 시작된 row는 변경을 거부(409)한다. cycle 외 컬럼(status/anchor/next/schedule)은 변경하지 않는다.

---

## 12. PAID 적용 결과

관련 최종 main: `d3777b6a56834c05718344ba73fc44f3a9cf322c`

PAID materializer(`services/paid_result_materializer.py`)는 공식 `obligations_raw` materialize 지점에서 `normalize_obligation_legal_time(raw_ob)` 를 직접 적용하여 `legal_time_normalized` 를 additive로 붙인다.

중요:

```
기존 PAID timing parser 결과를 새 shared legal-time의 입력으로 사용하지 않음.
raw obligation(obligation_detail.when / enrichment.inspection_cycle)을 직접 입력한다.
```

---

## 13. PAID Public Projection

`services/paid_result_public_projection_svc.py`

책임:

```
legal_time_normalized pass-through only
```

금지: normalizer 실행 · 시간 parsing · 재해석. (pick/rename/filter/count 역할만 유지)

---

## 14. PAID Excel

`services/paid_result_excel_v1.py` — **formatter only.**

기존 컬럼 보존:

```
when · inspection_cycle · raw_cycle · conflict
```

신규 additive(기존 컬럼 뒤, Obligations·Schedule 두 시트):

```
legal_timing_{source_text,status,type,operator,value,unit,basis_text}
legal_cycle_{source_text,status,type,operator,value,unit,basis_text}
```

총 14개 normalized 컬럼. Excel 내부: **시간 parsing = 0, normalizer call = 0** (normalized 노드를 cell로 평탄화하여 표시만).

---

## 15. SaaS / PAID Parity (핵심 검증)

동일 raw obligation에 대해:

```
PAID:  normalize_obligation_legal_time(raw_ob)
SaaS:  map_operation_presentation(raw_ob) → attach_legal_time_normalized(...)
```

결과:

```
deep equality = PASS
```

두 mapper(`map_diagnosis_presentation` / `map_operation_presentation`)의 timing/cycle 소스가 동일(`obligation_detail.when` / `enrichment.inspection_cycle`)하고, 둘 다 같은 shared normalizer를 거치므로 **동일 법령 → 동일 법정시간 normalized 결과**가 보장된다.

---

## 16. 주요 Git 이력

| 단계 | 내용 | main SHA |
|---|---|---|
| STEP 4B-4A | shared legal-time normalizer | `e3e2b32d` (short) |
| STEP 4B-4B | SaaS legal-time read-model | `f37cfbab` (short) |
| STEP 4B-4C | INDUSTRIAL C-10 + canonical wiring | `0e189349d810fd8aa5d2e1d2ce10d8d475c0b428` |
| STEP 4B-4D-A | operation-cycle API (tai-api) | `1d8d4d6ca5c85bb70d43d29158d47a28e6e52b6e` |
| STEP 4B-4D-B | operation-cycle/legal-time UI (tai-admin) | `48b154f51c59162dc5dfd4e94803aa30129ec6ee` |
| WO-LEG-COMMON-FINALIZER-001 | 3-sector 공통 finalizer (tai-api) | `df1071d3e67514326e0d1d3d44286f8a3aabc98c` |
| WO-PAID-TIME-001 | PAID Web/Excel shared normalizer (tai-api, PR #311) | `d3777b6a56834c05718344ba73fc44f3a9cf322c` |

Railway deployment (WO-PAID-TIME-001): `44d0d0aa-91c0-4a29-90ec-9c0bf7f82054`

> 참고: `e3e2b32d` / `f37cfbab` 는 세션 기록의 short SHA이며, 임의로 full SHA로 확장하지 않는다. 나머지는 full SHA로 확인된 값이다.

---

## 17. 테스트 증거 (WO-PAID-TIME-001)

```
self fixture (tests/test_paid_time_shared_normalizer_v1.py) = 16 passed
repo pytest (normalizer · read_model · presentation mapper · paid materializer/projection/excel/web·excel route + 관련 paid suite) = 388 passed / 0 failed
```

중요 검증 항목:

```
source_text EXACT ("  매년  " 공백 보존, trim 0)
SaaS == PAID deep equality
projection parser 0
Excel parser 0
기존 Excel columns 보존 (prefix EXACT)
기존 PAID R10/R11 timing semantic 유지
official obligations_raw only (다른 원본 미참조)
```

> 테스트 숫자(16 / 388·0)는 실행 receipt 기준이며, GitHub CI(Unit Tests)는 별도로 SUCCESS 확인됨. "CI가 그 숫자를 그대로 실행" 이라는 의미는 아니다(증거 구분 보존).

---

## 18. Production 상태

```
tai-api main = d3777b6a56834c05718344ba73fc44f3a9cf322c
Railway deployment = 44d0d0aa-91c0-4a29-90ec-9c0bf7f82054
Railway = SUCCESS

WO-PAID-TIME-001 = RELEASE PASS / CLOSED
```

---

## 19. Deferred / Non-blocking

```
SaaS canonical production visual smoke = DEFERRED OBSERVATION = NON-BLOCKING
```

이유: production에 적절한 canonical INSPECT fixture가 자연스럽게 존재하지 않았음(기존 LEGAL_ENGINE row 326건은 전부 legacy; INDUSTRIAL 공식 seam은 발화 확인됐으나 대상 진단 결과에 INSPECT 의무가 없었음). deterministic non-production contract verification은 이미 수행(86 fixture PASS). **이 항목 때문에 법정시간 파이프라인 작업을 다시 OPEN하지 않는다.**

---

## 20. Scope Boundary

이 결과서에 다음 작업을 섞지 않는다.

```
/diagnosis-step1 재설계   (다른 작업창에서 진행 중, 본 결과서 범위 밖)
3-sector common finalizer
법령 내용 / coverage
Check Layer
FREE/PAID action-first UI 일반 작업
```

---

## 21. 최종 결론 (비개발자용)

TAI SAFE의 법정시간은 이제 SaaS와 유료진단에서 따로 해석하지 않는다.

법령엔진이 제공한 동일한 시기·주기 원문을 하나의 공통 모듈이 구조화하고, SaaS·유료 Web·Excel은 그 동일한 결과를 각 화면 목적에 맞게 보여준다.

또한 법에서 말하는 시기와 회사가 실제 관리할 운영일정을 분리하여, 시스템이 법정 문구를 임의로 일정으로 확정하지 않도록 하였다.

따라서 앞으로 법정시간 해석 정책을 변경해야 할 경우, 채널별 코드를 각각 수정할 필요 없이 **공통 normalizer 한 곳만 관리**하면 된다.
