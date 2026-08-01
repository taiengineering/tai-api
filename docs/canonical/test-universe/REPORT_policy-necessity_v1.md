---
wo: WO-POLICY-001
class: records
type: report
scope: canonical
project: test-universe
title: Policy Necessity Verification
version: 1
status: active
owner: taiwang
---

# REPORT (FROZEN) — WO-POLICY-001 Policy Necessity Verification

> Policy Required 항목이 실제로 정책 결정이 필요한지 검증. 새 정책·sector 결정·DB 수정 없음. 결과: 기존 Rule/Evidence로 해결 가능한 것(P0/P1) = 0, Truly Policy Required(P2) = 372.

## 판정: PASSED — 정책 축소 불가 (372 전부 Truly Policy Required)

## STEP 1 — Policy Required 재검증 대상
- B 313(UNRESOLVED) + C 59(MULTI_TARGET) + Evidence 미확보 7. '사람이 결정해야 하는가 vs 기존 데이터로 가능한가'를 Evidence로만 확인.

## STEP 2 — Existing Evidence Search (전수 조사)
- **모법 상속 조사:** 미매핑 법령의 모법(시행령/규칙 제거한 본법)이 이미 law_sector_mapping에 매핑됐는지 → **0건**.
- **형제 상속 조사:** 미매핑 법령과 같은 base_name(고시/규정 포함)을 가진 '이미 매핑된' 형제 존재 → **0건**.
- **구조 확인(결정적):** 미매핑 375 중 "시행령/시행규칙" 이름을 가진 법령 = **0개**(total_sub=0).

## STEP 3 — Existing Rule Inheritance
- 상속 가능 여부: **불가.** 미매핑 집합에 모법-자법(시행령/규칙) 관계가 존재하지 않음. 상속의 앵커가 될 '매핑된 친척'이 0.
- 이유(구조적): 미매핑 375는 대부분 고시(314)·기술기준(STANDARD 42)·법(16)·기타(3). 고시/기술기준(NFTC·KC 규격·검사수수료 기준 등)은 특정 모법의 시행령이 아니라 독립 규격 → 상속할 부모가 구조적으로 없음.
- WO-MAPPING-003의 U-04(모법 위임 130) 재해석: 조문 본문에 "○○법에 따라" 위임 표현이 있었을 뿐, 법령 자체는 시행령/규칙이 아님 → 상속 대상 아님.

## STEP 4 — Policy Candidate Reduction
```text
P0 (Existing Rule Exists)   : 0   동일 법령 매핑 없음(미매핑이므로 당연)
P1 (Existing Rule Reusable) : 0   부모/형제 매핑 0, 상속 불가
P2 (Truly Policy Required)  : 372 (B 313 + C 59) — 전부 도메인 판단 필요
(+ Evidence 미확보 7은 매핑 대상 여부 자체가 운영 판단 → P2 상위 범주)
```

## STEP 5 — Independent Review
- "기존 규칙을 못 찾은 것 아닌가?" 검증: base_name 정규화(시행령/규칙 제거)로 본법 매칭 + 형제(고시/규정 포함)까지 확대 조사. 그래도 0.
- 매칭 실패 가능성 점검 → STEP6에서 확정.

## STEP 6 — Independent Audit
- 조사 누락 점검: 모법 매칭이 "매칭 방법 한계 때문에 0"인지 확인 → **total_sub=0**(미매핑에 시행령/규칙 자체가 없음)이 매칭 한계가 아니라 **데이터 구조상 상속 대상 부재**임을 증명. parent_absent/unmapped/mapped 모두 0(모집단이 0이므로).
- Rule/Family/Parent 누락 없음: 상속 앵커가 존재하지 않음을 구조로 확인.
- 결론: P1=0은 조사 부실이 아니라 실제 구조.

## STEP 7 — Freeze
```text
Existing Rule Found : 0 (P0)
Reusable Rule       : 0 (P1) — 모법·형제 매핑 0, 미매핑에 시행령/규칙 0
Remaining Policy    : 372 (P2, B313+C59) + 미확보 7
Evidence            : policy_inherit_out.csv(모법상속 0)·policy_sibling_out(형제 0)·policy_parent_out(total_sub 0)
Review              : PASS (기존 규칙 확대 조사 후 0)
Audit               : PASS (P1=0이 매칭 한계 아닌 구조적 부재임을 확인)
```

## 결론
- **정책 축소 불가.** 기존 Evidence/Rule로 결정 가능한 항목(P0/P1)이 0이므로, Policy Required 372는 전부 실제로 정책 결정(도메인 판단)이 필요하다.
- 이는 검증의 성공: "혹시 기존 데이터로 될 것"을 전수 조사해 0임을 확정 → 남은 372는 확실히 사람의 판단 대상.
- 상속 경로(U-04 모법 상속)가 유효하지 않음이 드러났으므로, 다음 정책 WO는 '모법 상속' 대신 '적용대상→sector 기준표'(도메인 판단)를 직접 세워야 함.

## Exit Criteria 점검
```text
[v] Existing Rule 전수 조사 (모법·형제·구조)
[v] Reusable Rule 식별 (0건)
[v] Truly Policy Required만 남김 (372)
[v] Review PASS
[v] Audit PASS
[v] Freeze 완료
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
① Inventory(375)            ✓ WO-CHG-004
② Evidence Sheet(368)        ✓ WO-COVERAGE-001
③ Mapping Policy(패턴)        ✓ WO-MAPPING-001
④ Sector Draft(A3/B313/C59)   ✓ WO-MAPPING-002
⑤ Policy Validation(경계)      ✓ WO-MAPPING-003
⑥ Independent Audit           ✓ WO-AUDIT-001
⑦ Audit Blind Spot            ✓ WO-AUDIT-002
⑧ Evidence Chain Audit        ✓ WO-AUDIT-003
⑨ Policy Independent Fix      ✓ WO-CHG-006 (BS-1 RESOLVED)
⑩ Policy Necessity(372 확정)   ✓ WO-POLICY-001 (P1=0, 축소 불가) ← 현재
⑪ Sector 기준표(도메인 판단)    ← WO-MAPPING-004 (운영자 기준 필요)
⑫ DB 반영 CHG + Verify        ← WO-CHG-005
```
