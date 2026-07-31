---
wo: WO-E2E-LOOP-CHG-001
class: records
type: runbook
scope: canonical
project: test-universe
title: CHG-001 E2E Improvement Loop v1
version: 1
status: active
owner: taiwang
---

# RUNBOOK — CHG-001 E2E Improvement Loop v1

> Mode: E2E Improvement (Investigation 종료). 목적은 원인 100% 증명이 아니라 **품질 개선 확인**.
> Loop: Measure → Hypothesis → Modify → Runner → After → Semantic Diff → Regression → Keep/Rollback.
> "수정" = 식별된 계층의 최소 수정(우선순위 Object→Configuration→Rule Data→Master→Code). **Code 아님이 기본.**
> Goal: G-ms8eq55a-6b36f2 · Input: REPORT_engine-cause-investigation_v1.md · REPORT_engine-data-access_v1.md
> Before: BEFORE_BASELINE_V1 (checksum d2d2e39f...) 불변 · Rollback 기준선.

## 대상 — CHG-001 (건축물 규모 역전)

대형 건축물(대표 PF-0019 obl107 · PF-0023 obl102, 법령 18)은 전기·승강기 대표의무 **미포함**, 소형(PF-0021·0025·0026 obl28, 법령 14)은 **포함**. 건축물 전기·승강기 coverage = 3/29.

## 실행 배치 (누가 어디서)

| 스텝 | 실행 위치 |
|---|---|
| 1 Measure(Before) · 2 Hypothesis · 6 Diff · 7 Regression · 8 판정 | **Cloud (Claude)** |
| 2 Measure(draft_slot 조회) · 3 Modify · 4 Runner · 5 After Snapshot | **On-your-computer** (production project_ref + 로컬 런타임 — Runner/Baseline과 동일 방식) |

## 루프 스텝

### 1. Measure — Before (Cloud, 완료)
- 지표: 대형 건축물 profile의 전기·승강기 대표의무 포함 수 = **0** (목표 > 0).
- 건축물 전기·승강기 coverage = **3/29**.
- 출처: Freeze된 BEFORE_BASELINE_V1 (불변).

### 2. Hypothesis / 수정 대상 계층 (Rule Data)
- 계층: **Rule Data = `engine_isolated.draft_slot`**. (Cause Investigation: Rule Gate는 sector=BUILDING scale-blind → 역전 아님; law_sector_mapping은 소형이 전기·승강기를 받으므로 BUILDING에 해당 법령 허용됨 → 역전은 draft 매칭 임계값 수준.)
- On-your-computer Measure: 소형이 매칭한 전기·승강기 draft의 `draft_slot` IF_NUMERIC rows(`binding_field, operator, value, unit`) 조회.
- 가설: 해당 draft의 IF_NUMERIC이 연면적/인원 **상한**(예: total_floor_area ≤ X, 또는 worker band)으로 걸려 대형이 제외됨 → "규모↑ = 의무↑" 상식과 역전.
- 최소 수정 후보(택1, Rule Data): (a) 문제 draft_slot row의 operator/value 교정, 또는 (b) 대형 규모용 전기·승강기 draft 매핑 추가. **Code 미변경.**

### 3. Modify — 최소 (On-your-computer)
- 식별된 `draft_slot` row **1건만** 수정(또는 매핑 1건 추가).
- **Before value 기록(rollback용).** 다른 draft·sector 무접촉.

### 4. Runner (On-your-computer)
- 영향 profile 재실행 — 최소 건축물 29건(대형 대표 PF-0019·0023 포함), 권장 전체 112.

### 5. After Snapshot (On-your-computer)
- `after_snapshot_chg001_v1` 생성 → Cloud로 전달.

### 6. Semantic Diff (Cloud)
- Before vs After. 확인: (i) 대형 건축물 전기·승강기 대표의무 **포함으로 전환**됐는가(목표 개선), (ii) 그 외 의무의 의도치 않은 변화 유무.

### 7. Regression (Cloud)
- 나머지 111 profile 스냅샷 무변화 확인: 소형 건축물의 전기·승강기 **유지**, 타 sector(제조·건설·특수) **무영향**.

### 8. Keep / Rollback 판정 (Cloud)
- 개선 O **AND** Regression 무손상 → **Keep**(수정 반영, After를 새 baseline 후보로).
- 그 외 → **Rollback**(기록한 Before value 복원). 실패도 유효한 루프 결과.

## 진행 전제 (충족)
- 수정 대상 계층 식별: Rule Data(draft_slot) ✅
- Rollback 가능: Before value 기록 + BEFORE_BASELINE_V1 존재 ✅
- Before Snapshot 존재: Freeze ✅
- UNKNOWN(정확한 draft_slot 값)은 스텝 2 Measure로 해소 — 별도 Investigation WO 아님.
