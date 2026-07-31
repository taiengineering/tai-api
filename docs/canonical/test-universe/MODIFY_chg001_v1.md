---
wo: WO-E2E-CHG001-LOOP-001
class: records
type: change
scope: canonical
project: test-universe
title: CHG-001 Minimal Modification (Rule Data) v1
version: 1
status: proposed
owner: taiwang
---

# MODIFY — CHG-001 최소 수정안 (Rule Data) v1

> E2E Improvement Loop STEP 2. 가설 검증용 최소 수정. **Code 미변경. Master(law_sector_mapping) 미변경.**
> 근거: REPORT_engine-cause-investigation_v1.md (Consumer·Compiler·Rule Gate 반증; 역전 locus = draft 매칭 임계값).
> STEP 1 읽기 불가 → 현재 근거로 진행(지시 조항). 정확한 row는 apply-time에 런타임에서 확정.

## 수정 계층 / 범위
- 계층: **Rule Data — `engine_isolated.draft_slot`**. 단일 row(또는 매핑 1건). 우선순위 Object→Config→**Rule Data**(여기)→Master→Code 중 Rule Data가 최소 단위.
- 무접촉: 다른 draft, Code, `law_sector_mapping`(Master), Object/Config. (BUILDING은 소형이 전기·승강기를 받으므로 sector 게이트는 이미 해당 법령 허용 → Master 수정 불필요.)

## 근거(현재 확보된 것)
소형 건축물(floor_area 400, workers 12)은 전기·승강기 대표의무 포함, 대형(floor_area 12000, workers 150)은 미포함. 두 profile 간 엔진 도달 차등 필드는 `total_floor_area/building_area`·`worker_count/employee_count` 뿐(전기용량·승강기수는 양쪽 0, floor_count·용도 동일). → 매칭된 전기·승강기 draft의 IF_NUMERIC이 **규모 상한**으로 걸려 대형을 배제 = 규모 역전.

## 수정안 (택1, 최소·가역)
- **A안 (임계값 교정)**: 해당 draft의 IF_NUMERIC row에서, 대형을 배제하는 **상한(operator ≤/<)**을 법 취지(규모↑ ⇒ 대표의무 유지)대로 교정 — 상한 상향(대형 preset 초과) 또는 하한(≥)으로 정정. **정확히 1 row.**
- **B안 (매핑 추가)**: 대형 규모용 전기·승강기 draft 매핑 **1건 추가**. (A안이 단일 draft의 오설정이 아니라 규모 tier 누락으로 판명될 때.)
- apply-time 확정: 소형 building profile(PF-0021)을 Runner로 돌려 매칭된 전기·승강기 대표 draft_id 포착 → 그 draft의 IF_NUMERIC row가 A안 대상.

## Rollback
- 수정 전 원본 `(draft_id, part_id, binding_field, operator, value, unit)` 기록.
- Rollback = 원본 복원. BEFORE_BASELINE_V1는 불변 기준선으로 유지.

## 판정 게이트 (STEP 5–7 연동)
- KEEP: 대형 건축물이 전기·승강기 대표의무 획득 **AND** 소형·타 sector 무변화.
- REVISE: 대형은 개선됐으나 과범위 변화(예: 비건축물 영향) 발생.
- ROLLBACK: 개선 없음 또는 Regression 손상.
