---
wo: WO-MAPPING-003
class: records
type: validation
scope: canonical
project: test-universe
title: Sector Decision Policy Validation
version: 1
status: active
owner: taiwang
---

# SECTOR DECISION POLICY VALIDATION (FROZEN) — WO-MAPPING-003

> 목적: 새 sector 결정이 아니라, **현재 Evidence만으로 어디까지 sector 결정이 가능한지 경계를 확정.** 각 분류에 '결정 가능/불가'만 기록. sector 추가·Draft/DB 수정·추론 없음.
> Input: Evidence Sheet(1f8c9fb2), Mapping Policy(93f102d2), Sector Draft(4a3de887: A3/B313/C59).

## STEP 1 — A 3건 재검증
세 건 모두 원문 적용범위 조문에 "건설공사" 직접 명시 → CONSTRUCTION 원문 직결 재확인:
- 건설공사 안전보건대장 작성 고시("총공사금액 50억원 이상 건설공사에 적용")
- 건설업 산업안전보건관리비 계상 기준("법 제2조제11호의 건설공사 중…에 적용")
- 내진설계 일반 KDS 17("「건설산업기본법」…건설공사의 내진설계에 적용")
→ A 재검증 PASS. 원문이 sector 직접 지시. 추론 0.

## STEP 2 — B(UNRESOLVED 313) 이유 분류 (판단 없음)
```text
U-04 모법 위임만            130   자체 적용대상 없이 "○○법에 따라" 위임
U-01 sector 직접 명시 없음  112   원문에 sector 지시 없음
U-02 시설만 존재            44    건축물/승강기 등 시설만, sector 아님
U-05 적용범위 복합           11   복수 시설 언급
U-03 업종만 존재             9    제조업/가공업/중소기업 등 업종만
U-00 원문 근거 미확보         7    적용대상 원문 자체 없음
```

## STEP 3 — C(MULTI_TARGET 59) 이유 분류
```text
M-04 소방 공통기준  58   NFTC/NFPC 화재안전기술기준(시설 불문)
M-03 전 시설         1   전 시설 대상
```

## STEP 4 — Validation (현재 Evidence만으로 결정 가능한가)
```text
[결정 가능] A (건설공사 원문 직결)        → sector=CONSTRUCTION 원문 직접 지시
[결정 불가] U-00 원문 근거 미확보          → 적용대상 원문 없음
[결정 불가] U-01 sector 직접 명시 없음     → 정책 규칙 필요
[결정 불가] U-02 시설만 존재              → 시설→sector 번역 규칙(도메인 판단) 필요
[결정 불가] U-03 업종만 존재              → 업종→sector 번역 규칙 필요
[결정 불가] U-04 모법 위임만              → 모법의 sector를 별도 확인해야
[결정 불가] U-05 적용범위 복합            → 단일 sector 규칙 필요
[결정 불가] M-03 전 시설                 → 단일 sector 아님(MULTI 유지)
[결정 불가] M-04 소방 공통기준            → 시설 불문 전 sector(MULTI 유지)
```

## STEP 5 — 경계 확정 (Validation Report)
```text
Decision Possible : 3   (A, 건설공사 원문 직결)
Decision Impossible : 372 (B 313 + C 59)
  → 372건은 정책 규칙(적용대상→sector 기준표, 도메인 판단) 없이 결정 불가
```

### 결정 불가의 해소 경로 (관측 — 다음 WO 입력, 판단 아님)
- U-04 모법 위임만(130): 모법이 이미 매핑돼 있으면 모법 sector 상속으로 결정 가능해질 수 있음 → 가장 기계적. 단 모법 매핑 확인이 선행.
- U-02 시설만(44)·U-03 업종만(9): '시설→sector'·'업종→sector' 번역 기준표(도메인 판단)가 서면 결정 가능.
- U-01 명시 없음(112)·U-05 복합(11): 원문만으로 불가.
- M-04 소방(58)·M-03 전시설(1): 본질적 MULTI — 억지 단일화 금지, MULTI 유지가 정답.

## Freeze
- A Validation·B Validation·C Validation·Decision Possible(3)·Decision Impossible(372) 확정.
- sector 추가 0 · Draft 수정 0 · DB 수정 0 · 추론 0 · Pattern 자동결정 0.

## 다음 (WO-MAPPING-004)
```text
Sector Policy Approval → Sector Rule → Draft Revision
```
- U-04(모법 상속)·U-02/U-03(번역 기준표) 순으로 도메인 판단 기준을 세워 결정 불가 372를 단계적으로 해소. M-04 소방은 MULTI 유지.

## 상태 (Obs-004 커버리지 파이프라인)
```text
① Inventory(375)            ✓ WO-CHG-004
② Evidence Sheet(368)        ✓ WO-COVERAGE-001 (1f8c9fb2)
③ Mapping Policy(패턴)        ✓ WO-MAPPING-001 (93f102d2)
④ Sector Draft(A3/B313/C59)   ✓ WO-MAPPING-002 (4a3de887)
⑤ Policy Validation(경계 확정)  ✓ WO-MAPPING-003 ← 현재
⑥ Policy Approval → Rule      ← WO-MAPPING-004
⑦ DB 반영 CHG + Verify        ← WO-CHG-005
```
