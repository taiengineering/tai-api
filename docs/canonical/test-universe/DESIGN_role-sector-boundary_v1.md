---
wo: WO-WIRING-004
class: plans
type: design
scope: canonical
project: test-universe
title: Role-to-Sector Boundary Contract
version: 1
status: active
owner: taiwang
---

# ROLE-TO-SECTOR BOUNDARY CONTRACT — WO-WIRING-004

> DESIGN_BLOCKED 차단 원인(Role→sectors[] 변환 계약 부재)의 **경계만 확정.** 실제 sector 값 결정 **없음.** 코드·DB·Pattern·Mapping 수정 **0.**
> 엔진 DB wrfcedzgdrfupenzqhur · 엔진 코드 taiengineering/tai-api.

## 판정: READY_FOR_WIRING_SELECTION

## STEP 1 — Blocker Statement (고정)
```text
Runtime은 law_id → sectors[]를 요구하지만, 현재 검증 자산은 law(law_name) → Role
까지만 제공하며, Role → sectors[] 변환 계약이 존재하지 않는다.
```
(다른 원인 추가 없음)

## STEP 2 — Layer Ownership
```text
pattern_dictionary  → Pattern Layer          (pattern_id, trigger, role)
role_mapping        → Role Layer             (law_name, value, role, pattern_id, evidence_articles)
sector_standard     → Sector Standard Layer  (BUILDING/INDUSTRIAL/CONSTRUCTION/SPECIAL_FACILITY)
law_sector_mapping  → Law-Sector Mapping     (law_id, sectors[] = Runtime Producer)
allowed_draft_ids   → Runtime Filter Result  (_load_sector_allowed_draft_ids 출력)
★ Role Layer가 law_sector_mapping을 직접 수정하지 않음(경계 계층 경유).
```

## STEP 3 — Boundary Input Contract (실제 자산 기준)
```text
law_name          YES     role_mapping.law_name
role              YES     role_mapping.role / pattern_dictionary.role
pattern_id        YES     role_mapping.pattern_id / pattern_dictionary.pattern_id
evidence_article  YES     role_mapping.evidence_articles
evidence_value    YES     role_mapping.value
role_status       PARTIAL role 값에 REGULATED/FACILITY/UNRESOLVED 포함(별도 status 컬럼 없음)
law_id            NO      role_mapping엔 없음 → Boundary가 law_name→law_id 해소 책임
★ 지시서 예시의 law_id는 실제 자산에 없음 → 추가 안 함, law_name으로 기록.
```

## STEP 4 — Boundary Output Contract (상태값만)
```text
law_id            Runtime 계약 키 (law_sector_mapping.law_id)
sectors[]         형식만 정의. 실제값 이번 WO 안 채움
decision_status   DECIDED / MULTI_TARGET / UNRESOLVED / NOT_APPLICABLE
decision_evidence 근거(evidence_articles 등)
decision_version  결정 버전(감사추적)
```

## STEP 5 — Responsibility Matrix
```text
판단                       책임
원문에서 Role 추출          Pattern/Role Layer
Role 검증                  Role Verification
law_name→law_id 해소       Boundary (신규 책임)
Role→sectors 변환          Mapping Policy (신규 책임, 현재 부재=R-01)
sector 표준값 관리          sector_standard
특정 법령의 sector 결정      Mapping Policy
Runtime 필터링             _load_sector_allowed_draft_ids()
★ Role 추출(Pattern/Role Layer) ≠ Sector 결정(Mapping Policy). 분리 확정.
```

## STEP 6 — Fallback Contract
```text
DECIDED        → 승인된 sectors[] 사용
MULTI_TARGET   → 승인된 복수 sectors[] 사용
UNRESOLVED     → 기존 law_sector_mapping 유지 (억지 sector화 금지)
NOT_APPLICABLE → 기존 law_sector_mapping 유지
변환 결과 없음  → 기존 law_sector_mapping 유지
★ 새 결과가 기존 운영 law_sector_mapping 값을 자동 덮어쓰지 않음.
```

## STEP 7 — Candidate Re-evaluation (WIRING-003 재대조)
```text
C1 _load_sector_allowed_draft_ids  CONTRACT_MISMATCH  (Runtime 필터 ↔ Mapping Policy 책임 혼재)
C2 law_sector_mapping 데이터         BOUNDARY_COMPATIBLE (경계 출력 그대로 반영, Mapping Policy 소유, Fallback 안전; law_name→law_id 해소 선행 전제)
C3 통과판정 로직                      CONTRACT_MISMATCH  (Runtime 필터가 Sector 결정 침범)
C4 sector_standard                 OWNERSHIP_VIOLATION (표준값 관리 ↔ 법령별 결정 책임 다름)
C5 sieve_clause                    CONTRACT_MISMATCH  (현 진단경로 미연결)
★ 최적 후보 미선택. C2가 유일 BOUNDARY_COMPATIBLE로 판정만.
```

## STEP 8 — Independent Review
```text
[PASS] Role/Sector 계층 미혼재 (STEP5 분리, C1/C3 혼재 배제)
[PASS] Runtime 계약 law_id→sectors[] 유지 (C2만 호환)
[PASS] UNRESOLVED 억지 sector화 안 됨 (Fallback: 기존 유지)
[PASS] 기존 law_sector_mapping Fallback 보존 (자동 덮어쓰기 금지)
```

## STEP 9 — 판정: READY_FOR_WIRING_SELECTION
```text
경계 계약 확정: Input(law_name,role,pattern_id,evidence_articles,value,role_status)
  → [Boundary: law_name→law_id 해소 + Role→sectors 변환(Mapping Policy)]
  → Output(law_id, sectors[], decision_status, evidence, version)
  → Fallback(UNRESOLVED/없음 → 기존 유지)
후보 재대조: C2만 BOUNDARY_COMPATIBLE.

확정된 것: 책임·입력·출력·Fallback 경계.
미정(의도적, 다음 WO): 실제 sectors[] 값 · Role→sectors 규칙(Mapping Policy).
추가 선행 과제: law_name→law_id 해소(role_mapping엔 law_id 없음).
실제 sector 값 결정: 0건.
```

## 산출물
```text
role_sector_boundary_contract.md · boundary_input_output.csv · responsibility_matrix.csv
fallback_contract.md · candidate_contract_review.csv
```

## 규율 준수
- 실제 sector 결정 0 · Role별 sector 지정 0 · 신규 Pattern/Rule/Exception 0 · 재분류 0 · Injection 최종 선택 0 · 코드/DB/law_sector_mapping/Pattern/Mapping 수정 0.

## 상태 (WIRING 진행)
```text
STEP1 무엇을 읽는가        ✓ WO-WIRING-001 STEP1
STEP2 무엇을 기대하는가    ✓ WO-WIRING-002 (Contract Complete)
STEP3 어디에 연결 가능한가  ✓ WO-WIRING-003 (C2 COMPATIBLE)
STEP3.5 경계 계약          ✓ WO-WIRING-004 (READY_FOR_WIRING_SELECTION) ← 현재
다음                      : Wiring Selection(C2 확정) → Mapping Policy(Role→sectors 규칙+law_name→law_id) → IMPLEMENT
```
