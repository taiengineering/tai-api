# inspection_sets.py 서비스 레이어 분리 — Cursor 작업지시서

> 대상: `routers/inspection_sets.py` (38KB, ~850줄)
> 규칙: `docs/DEV_RULES_SERVICE_LAYER.md` 필수 준수
> 브랜치: `dev` (main 직접 push 금지)
> 목표: 38KB → 라우터 15KB 이내

---

## 현재 구조 분석

| 영역 | 줄수(약) | 내용 |
|------|----------|------|
| 상수 | ~30줄 | `DELTA_MAP`, `REPEAT_TYPE_MAP`, `UNIT_KO`, `CHECK_TYPE_MAP` |
| 순수 헬퍼 | ~90줄 | `_get_delta`, `_next_planned_from`, `_build_next_schedule_row`, `_build_items_for_set`, `_meets_4_conditions`, `_build_law_engine_row` |
| 비즈니스 함수 | ~60줄 | `_run_generate_law_engine` |
| Pydantic 모델 | ~50줄 | 6개 |
| 엔드포인트 | ~600줄 | 13개 |

---

## 분리 계획

### 파일 1: `schemas/inspection_sets.py` (~50줄)

```
AnchorBody, BulkAnchorBody, AnchorBulkItem, AnchorBulkPatchBody
ManualInspectionSetBody, InspectionSetPatchBody
```

### 파일 2: `services/inspection_sets_helpers.py` (~120줄)

상수 + 순수 함수 (DB 호출 없음):
```
DELTA_MAP, REPEAT_TYPE_MAP, UNIT_KO, CHECK_TYPE_MAP
get_delta, next_planned_from, build_next_schedule_row
build_items_for_set, meets_4_conditions, build_law_engine_row
```

### 파일 3: `services/inspection_sets_svc.py` (~250줄)

비즈니스 로직 (DB 포함). `from fastapi import` 금지:
```
run_generate_law_engine, create_manual_set, set_anchor_bulk
bulk_update_anchors, generate_all_items, patch_set
update_anchor, generate_items_for_set, get_sets_list
get_preview_schedule, generate_schedules_for_factory, generate_schedules_all
```

### 파일 4: `routers/inspection_sets.py` (~150줄)

HTTP만 담당.

---

## 실행 순서

### STEP 0: 테스트

`tests/test_inspection_sets_current.py` 최소 5개:
1. `_get_delta("month", 3)` → `relativedelta(months=3)`
2. `_next_planned_from` — 과거 기준일에서 미래 일자
3. `_meets_4_conditions` — 4조건 충족 True
4. `_meets_4_conditions` — assignee 누락 False
5. `_build_law_engine_row` — 필수 필드
6. `ManualInspectionSetBody` — 검증

### STEP 1~5: 스키마 → 헬퍼 → 서비스 → 라우터 슬림화 → 테스트 보강

매 단계 `pytest` PASS 확인.

---

## 절대 하지 말 것

- 테스트 없이 분리 시작
- 날짜 계산 로직 변경 금지 — 100% 그대로 이동
- 라우터에서 SQL 실행
- 서비스에서 `from fastapi import`
- 400줄 초과
- main push 금지
- API 응답 구조 변경

## 완료 기준

| 항목 | 기준 |
|------|------|
| `routers/inspection_sets.py` | 15KB 이내 |
| `services/inspection_sets_helpers.py` | 10KB 이내 |
| `services/inspection_sets_svc.py` | 15KB 이내 |
| `schemas/inspection_sets.py` | 5KB 이내 |
| 테스트 | 최소 10개 PASS |
| 브랜치 | dev |

## 커밋 단위

```
1. feat: STEP 0 — inspection_sets 현재 동작 테스트 6+개
2. refactor: STEP 1 — schemas/inspection_sets.py
3. refactor: STEP 2 — inspection_sets_helpers.py
4. refactor: STEP 3 — inspection_sets_svc.py
5. refactor: STEP 4 — 라우터 슬림화
6. test: STEP 5 — 테스트 보강
```
