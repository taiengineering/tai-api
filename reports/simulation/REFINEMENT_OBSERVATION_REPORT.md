# Phase 11 — Refinement Observation Report

> 관찰 목적: Check 결과를 Quality Evaluator에 넣었을 때 3상태 분포가 어떻게 나오는가.
> Phase 10 실제 실행 결과 + Phase 10B 검증 결과 기반.

---

## 실제 데이터 기반 현황 (Phase 10 실행 로그)

- **적재된 의무 수**: 1,000건 (1개 사업장 기준)
- **READY**: 0건 (0%)
- **TRACE_REQUIRED**: 1,000건 (100%)
- **CORRECTION_REQUIRED**: 0건 (0%)
- **fully_classified**: true
- **주요 reason**: EVIDENCE_INSUFFICIENT (1,000건 모두)
- **admin_obligation_queue**: 0건 (CORRECTION 없으므로)

---

## STEP 5 관찰: 정제 결과 분포

### 5-1. 50개 사업장 예상 분포

**관찰**: 현재 시스템 상태에서 50개 사업장 전체를 시뮬레이션해도:

| 상태 | 예상 비율 | 근거 |
|------|---------|------|
| READY | 0% | evidence.chain 없음 → 전부 TRACE |
| TRACE_REQUIRED | ~95~100% | CHAIN_NOT_DECLARED → ACTION_INSUFFICIENT |
| CORRECTION_REQUIRED | ~0~5% | law_name/article 누락 의무 (일부 업종) |

**관찰**: 50개 사업장을 다 넣어도 READY는 나오지 않을 것으로 예상. 업종 다양화가 품질 분포에 영향 없음.

### 5-2. TRACE_REQUIRED 분석

**reason 분포 예상**:

| reason | 예상 비율 | 의미 |
|--------|---------|------|
| EVIDENCE_INSUFFICIENT | ~50% | evidence.chain 자체 없음 |
| ACTION_INSUFFICIENT | ~50% | chain 선언 없음 (CHAIN_NOT_DECLARED) |

**관찰**: Phase 10 실제 결과는 `EVIDENCE_INSUFFICIENT` 1,000건. Check에서 evidence 항목이 0일 때 evaluator가 EVIDENCE_INSUFFICIENT로 분류하는지 ACTION_INSUFFICIENT로 분류하는지는 관측 케이스에 따라 다를 수 있음. Phase 10A에서 CHAIN_NOT_DECLARED가 관찰됐으므로 ACTION_INSUFFICIENT 비율도 존재할 것으로 예상.

### 5-3. CORRECTION_REQUIRED 발생 조건 관찰

**관찰**: 50개 사업장 중 CORRECTION이 발생할 수 있는 케이스:

| 케이스 | CORRECTION 원인 예상 | 사업장 예시 |
|-------|-------------------|----------|
| law_name 없는 의무 | LAW_LINK_ERROR | 전체 (일부 룰에 법령 누락 가능) |
| 동일 rule_code 중복 | DUPLICATE_OBLIGATION | 복수 공장 배치 시 |
| 구조 오류 의무 | DATA_ERROR | 비정상 result_data |

**관찰**: 실제 1,000개 룰 중 `law_system = "NOT_MAPPED"` 룰이 있음 (Phase 10에서 확인). 이런 룰에 law_article이 비어있을 경우 LAW_LINK_ERROR(CORRECTION) 발생 가능.

### 5-4. Admin Queue 관찰

**현재 상태** (실제 적재 후 확인):
- admin_obligation_queue_total: 0건
- CORRECTION_REQUIRED가 없으므로 큐도 없음

**50개 사업장 시뮬레이션 시 예상**:
- law_name 누락 의무가 있는 경우에만 큐 발생
- 현재 진단 데이터 품질에 따라 수십 건 발생 가능

### 5-5. 실제 운영 가능한 의무

**관찰**: "스케줄 생성 가능한 의무" = READY = **현재 0건**.

50개 사업장에서 어떤 사업장도 실제 운영(스케줄 생성)으로 연결되지 않음. 이것은 시스템 오류가 아니라 **evidence.chain이 아직 연결되지 않은 상태의 정직한 반영**.

### 5-6. 업종별 READY 가능성 관찰

| 업종 | READY 가능 조건 | 현재 여부 |
|------|--------------|----------|
| 건설업 | evidence.chain에 안전관리계획서·작업허가서 등 연결 시 | ❌ 미연결 |
| 화학공장 | PSM 서류·안전장치 검사서 evidence 연결 시 | ❌ 미연결 |
| 제조업 | 위험기계 검사서·안전인증서 evidence 연결 시 | ❌ 미연결 |
| 병원 | 의료가스 안전관리 증빙 evidence 연결 시 | ❌ 미연결 |

**관찰**: 업종별로 연결되어야 하는 evidence의 종류는 다르나, **어떤 업종도 현재 evidence가 없어** READY가 불가.

---

## 관찰 요약

| 관찰 항목 | 현재 상태 |
|---------|----------|
| 전체 READY | 0건 |
| 실제 운영 가능 의무 | 0건 |
| TRACE 주원인 | evidence.chain 미연결 |
| CORRECTION 발생 가능성 | law_name 누락 의무에 한해 |
| Admin Queue | 0건 (CORRECTION 없음) |
| 업종 다양화 효과 | 분포 변화 없음 (동일 원인) |
| 시스템 정상성 | 평가기 자체는 정상 (Phase 10B 확인) |
