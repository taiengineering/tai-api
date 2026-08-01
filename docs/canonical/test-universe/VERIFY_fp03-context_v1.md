---
wo: WO-VERIFY-003
class: records
type: verification
scope: canonical
project: test-universe
title: FP-03 Context Verification
version: 1
status: active
owner: taiwang
---

# FP-03 CONTEXT VERIFICATION (FROZEN) — WO-VERIFY-003

> FP-03(맥락 부족) 7건을 전량 원문으로 검증. 규칙 일반화 가능 vs 개별 판단의 경계 확정. 목록·Exception·번역표·sector·DB 수정 없음. 매칭은 WO-CHG-007 수정본 사용.
> Input: FP-03 7건, 원문 Evidence, 기존 393.

## 판정: PASSED — 부분 일반화 가능(패턴 A), 단 적용은 대상 성격 판단(Policy)

## STEP 1 — FP-03 Inventory (CHG-007 매칭 후 남은 7건)
```text
1. 어린이놀이시설 안전관리법          [어린이] → {BUILDING,INDUSTRIAL}
2. 어린이놀이시설 안전관리법 시행규칙  [어린이] → {BUILDING,INDUSTRIAL}
3. 어린이놀이시설 안전관리법 시행령    [어린이] → {BUILDING,INDUSTRIAL}
4. 건설기계 안전기준에 관한 규칙       [전기]   → {CONSTRUCTION}
5. 수도용 자재와 제품의 위생안전기준 인증규칙 [전기] → {BUILDING,INDUSTRIAL}
6. 제품안전기본법                    [전기]   → {INDUSTRIAL}
7. 제품안전기본법 시행령              [전기]   → {INDUSTRIAL}
```

## STEP 2 — Context Reading (원문 직접, 추론 없음)
- 어린이놀이시설법: "어린이놀이시설의 **설치·유지·보수**" → 규율대상=놀이시설(시설물). '어린이'는 시설 수식어.
- 건설기계 안전기준: "「건설기계관리법」…**건설기계**의 구조·규격·성능" → 규율대상=건설기계. '전기'는 부품 맥락.
- 수도용 자재 인증규칙: "「수도법」…**수도용 자재와 제품**의 인증" → 규율대상=수도용 자재. '전기'는 자재 예시.
- 제품안전기본법: "**제품의 안전성 확보** 기본사항" → 규율대상=제품 일반. 특정 대상 없음, '전기'는 예시로 스침.

## STEP 3 — Root Cause Classification
```text
CTX-01 시설/대상 우선 : 5 (어린이놀이시설 3·건설기계 1·수도용자재 1)
CTX-04 목적 우선      : 2 (제품안전기본법 2)
CTX-02/03/05         : 0
```

## STEP 4 — Common Pattern
- **부분 공통 — 2개 패턴:**
  - **패턴 A (CTX-01, 5건):** 키워드가 규율대상(시설/기계/자재)을 수식하거나 부품 맥락. 키워드는 대상에 부수, 대상의 성격 아님.
  - **패턴 B (CTX-04, 2건):** 제품안전 일반, 특정 대상 없이 키워드가 예시로 스침.
- **공통점:** 7건 모두 키워드가 "규율 대상 자체의 특수성"이 아님 → EX-01(대상 특수성) 조건 미충족.

## STEP 5 — Replay (CHG-007 수정 매칭)
- 단어 경계 매칭 후 남은 FP = 정확히 7건 = 전부 FP-03. FP-01 0건.
- **매칭 교정이 FP-01만 제거하고 FP-03만 남김 — 두 원인이 데이터에서 완전 분리 확인.**

## STEP 6 — Independent Review (일반화 vs 개별)
- **패턴 A(5건): 부분 일반화 가능.** "키워드가 시설/기계/자재를 수식하고 규율대상이 그 시설이면 EX-01 아님". 단 '어린이놀이시설=시설물(어린이=취약계층 아님)' 판단은 도메인 지식 → 규칙화하려면 Policy.
- **패턴 B(2건): 개별에 가까움.** "제품안전 일반"은 목적이 광범위, 규칙보다 개별 확인.
- **결론:** FP-03은 순수 규칙으로 완전 일반화 불가. 부분 패턴(A)은 있으나 적용은 대상 성격 판단(Policy) 필요. **7건 모두 "키워드 존재 ≠ 대상 특수성"** = EX-01 규칙에 "키워드가 규율대상 자체인가(수식 아님)" 확인 조건이 필요함을 시사.

## STEP 7 — Independent Audit
```text
Inventory     : PASS (7 전량)
Context       : PASS (7 원문 정독, 규율대상 확인)
Classification: PASS (CTX-01 5·CTX-04 2, 나머지 0)
Replay        : PASS (CHG-007 후 FP-03 7만 남음)
Review        : PASS (부분 일반화, 대상 성격은 Policy)
핵심: 7건 모두 키워드가 대상을 수식만 함(어린이→놀이시설, 전기→제품/자재). 대상 특수성 아님.
```

## STEP 8 — Freeze
```text
FP-03 Inventory     : 7건 (어린이놀이시설 3·건설기계 1·수도용자재 1·제품안전 2)
Context Report      : 규율대상 = 시설/기계/자재/제품(키워드는 수식·예시)
Classification Matrix: CTX-01 5 · CTX-04 2
Replay Report       : CHG-007 매칭 후 FP-03 7만 잔존, FP-01 0
Review              : 부분 일반화(패턴 A) 가능, 적용은 Policy
Audit               : PASS
```

## 결론 — 경계 확정
- **FP-03은 매칭 문제가 아니라 "키워드 존재 ≠ 대상 특수성" 문제.** 어린이(놀이시설 수식)·전기(제품/자재 예시)는 규율대상의 성격이 아님.
- **부분 일반화 가능(패턴 A 5건):** "키워드가 규율대상을 수식하면 EX-01 제외" 규칙은 세울 수 있으나, 그 판단(어린이놀이시설=시설물)은 도메인 지식 → Policy.
- **패턴 B 2건은 개별 확인.**
- **EX-01 규칙 개선 방향(시사, 결정 아님):** "대상 키워드가 규율대상 자체의 성격인가, 아니면 대상을 수식/예시하는가"를 구분하는 조건 필요. 이는 다음 WO(EX-01 목록/규칙 정제 또는 번역표)에서 Policy로 다룸.
- 본 WO는 경계만 확정. 목록·Exception·번역표 미수정.

## Exit Criteria 점검
```text
[v] FP-03 7건 전량 확인
[v] Context 완료 (원문 정독)
[v] Root Cause 완료 (CTX-01 5·CTX-04 2)
[v] Replay 완료 (FP-03 7만 잔존)
[v] Review PASS
[v] Audit PASS
[v] Freeze 완료
```

## 상태 (Obs-004 커버리지 파이프라인)
```text
⑯ FP Analysis               ✓ WO-VERIFY-002 (FP-01 75%·FP-03 25%)
⑰ Matching Correction(FP-01) ✓ WO-CHG-007 (FP 28→7, FN +0)
⑱ FP-03 Context Verify       ✓ WO-VERIFY-003 (CTX-01 5·CTX-04 2, 부분 일반화) ← 현재
⑲ EX-01 규칙 정제(수식 구분)  ← 다음 (Policy: 키워드가 대상 성격인가 수식인가)
⑳ 번역표 수립                ← 그 후
㉑ DB 반영 CHG + Verify       ← WO-CHG-005
```
