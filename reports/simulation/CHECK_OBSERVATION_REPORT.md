# Phase 11 — Check Observation Report

> 관찰 목적: LEG 결과를 Check에 넣었을 때 어떤 EvidenceReport가 나오는가.
> Phase 10A에서 실제 Check 실행 결과를 기반으로 작성.

---

## 실제 확인된 데이터 (Phase 10A 실행 로그 기준)

**Case A: 진단 룰 형식 의무 (evidence.chain 없음)**
```
CLAIM_PRESENT: 1
EVIDENCE_ATTACHED: 0, NOT_ATTACHED: 0 (evidence 자체 없음)
EVIDENCE_CHAIN_NOT_DECLARED: 1
```
→ Quality: TRACE_REQUIRED (ACTION_INSUFFICIENT)

**Case B: evidence.chain 포함 의무 (attached:True)**
```
CLAIM_PRESENT: 1
EVIDENCE_ATTACHED: 1
EVIDENCE_CHAIN_COMPLETE: 1
```
→ Quality: READY

---

## STEP 4 관찰: Check 검증 결과 (50개 사업장 시뮬레이션)

### 4-1. READY 후보

**관찰**: 현재 운영 의무(`result_data.rules[]`) 기준으로 READY 후보 = **0건**.

이유:
- 모든 `result_data.rules` 항목에 `evidence_chain` 필드 없음 (Phase 10A Case A에서 확인)
- evidence.chain 없음 → EVIDENCE_CHAIN_NOT_DECLARED = 1 → TRACE_REQUIRED
- 50개 사업장 모두 동일한 결과 예상: **전 사업장 READY 0건**

### 4-2. TRACE_REQUIRED 원인 분석

| 원인 | Check 상태 | 해당 사업장 예시 |
|------|-----------|----------------|
| evidence.chain 미선언 | CHAIN_NOT_DECLARED=1 | 전체 50개 사업장 |
| evidence.chain은 있으나 미첨부 | EVIDENCE_NOT_ATTACHED=1 | (현재 해당 없음) |
| chain이 선언됐으나 불완전 | CHAIN_BROKEN=1 | (현재 해당 없음) |

**관찰**: 현재 TRACE_REQUIRED의 단일 원인은 "evidence.chain이 LEG 의무에 정의되지 않음".
업종 차이, 사업장 규모, 위험물 유무와 무관하게 **동일한 원인으로 전부 TRACE_REQUIRED**.

### 4-3. Evidence 부족 원인 상세

**관찰**:
- `result_data.rules[]` 각 룰에 증거 구조(`evidence.chain[]`) 없음
- LEG 결과물의 현재 스키마에 evidence 관련 필드 없음
- Check는 claim은 정상 처리하나 (CLAIM_PRESENT=1) evidence/chain 처리 불가
- 법령엔진이 "어떤 증거로 이 의무를 이행하는가"를 아직 정의하지 않음

### 4-4. 사업장 유형별 Check 결과 예상

| 사업장 유형 | CLAIM_PRESENT | EVIDENCE_ATTACHED | CHAIN_COMPLETE | 예상 품질 |
|-----------|:---:|:---:|:---:|---|
| 건설업 (#01~#12) | 1 (각 의무) | 0 | 0 (NOT_DECLARED) | TRACE |
| 건축물 운영 (#13~#22) | 1 | 0 | 0 | TRACE |
| 제조업 (#23~#50) | 1 | 0 | 0 | TRACE |

**관찰**: 업종·규모·위험물 유무와 무관하게 Check 결과 동일. 시스템이 현재 업종 차별화를 하지 않음.

### 4-5. Check 엔진 자체 동작 관찰

**관찰**: Check 엔진 자체는 정상 동작 (Phase 10A V3/V4 PASS).
- CLAIM_PRESENT 판단 정확
- EVIDENCE_ATTACHED 판단 정확 (있으면 1, 없으면 0)
- CHAIN_COMPLETE 판단 정확 (Phase 10A Case B에서 확인)
- 결정론성 확인 (check_deterministic: true)
- **문제는 Check 엔진이 아니라 입력 데이터(evidence.chain)의 부재**

### 4-6. 50개 사업장 예상 분포

```
READY:                0건 (0%)
TRACE_REQUIRED:    1,000건 × 50개 = ~50,000건 예상 (업종별 의무 수 가정 시)
CORRECTION_REQUIRED:  일부 (law_name 누락 의무 포함 시)
```

**관찰**: 실제 사업장 시뮬레이션을 해도 READY 비율은 0%로 유지될 것으로 예상. 업종별 차이 없음.

---

## 관찰 요약

| 관찰 항목 | 현재 상태 |
|---------|----------|
| READY 후보 | 0건 (전 사업장) |
| TRACE 주원인 | evidence.chain 미정의 (law_system=NOT_MAPPED 연관 가능성) |
| Check 엔진 정상성 | 확인됨 (Phase 10A) |
| 사업장 유형별 차별화 | 없음 (현재) |
| 검출 가능한 CORRECTION 원인 | law_name 누락 의무 (일부) |
