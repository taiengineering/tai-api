---
wo: WO-AUDIT-003
class: records
type: audit
scope: canonical
project: test-universe
title: Evidence Chain Independent Audit
version: 1
status: active
owner: taiwang
---

# EVIDENCE CHAIN AUDIT — WO-AUDIT-003

> WO-AUDIT-002가 찾은 Blind Spot(POSSIBLE IMPACT: BS-1 Evidence 추출·BS-2 건설공사 기준)을 실제 원문 체인까지 독립 검증. 정책·sector·DB 수정 없음, 추론 없음, 기준 옳고그름 판단 없음(실제 사용 기준만 확인).
> Input: 법령 원문(law_article DB), Evidence Sheet(coverage_evidence), Sector Draft(4a3de887), Audit(6279242f), Blind Spot(c1ff0055).
> 참고: WO-AUDIT-002에 HIGH 없음(BS-1/BS-2 MEDIUM/POSSIBLE) → POSSIBLE IMPACT 항목과 표본 규칙을 대상으로 수행.

## 판정: KEEP WITH LIMITATION

## STEP 1-3 — Evidence 체인 + Evidence Sheet 표본 감사 + 추출 정확도
- **표본 선정 규칙:** 목적/적용범위 조문 0개 법령 111개에서 seed103 무작위 15개.
- 각 표본의 **원문 전체 조문**을 DB에서 조회해 적용범위 조문 존재 여부 대조.
- **결과: 15/15 PASS.** 원문에 적용/목적/대상/범위 조문 제목 전무:
  - 전기용품 안전기준 KC 시리즈(11건): 조문이 "전문" 1개 — 기술규격 전체가 한 덩어리, 적용범위 조문 없음.
  - 공정시험기준(빛공해·실내공기질): 본문 외부 참조("상단 메뉴") — DB에 적용범위 조문 없음.
  - 전기용품 부적합시 처리기준: "처리기준"·"재검토기한"만. 증축형 리모델링 안전진단기준: 절차 조문만.
- **추출 정확도:** Evidence Sheet가 놓친 게 아니라 원문 자체에 적용범위 조문 없음 → 추출은 원문 의미 보존(누락·오인용 없음). BS-2의 "추출 누락" 우려가 이 표본에서 실현 안 됨.

## STEP 4 — BS-2(건설공사→A 기준) 감사
- A 3건 모두 적용범위 조문에 "건설공사" 존재, 적용범위 내 타 sector 어휘 0.
```text
건설공사 안전보건대장 고시     : 건설공사 O, 타어휘 [] → CONSTRUCTION
건설업 산업안전보건관리비 기준  : 건설공사 O, 타어휘 [] → CONSTRUCTION
내진설계 일반 KDS 17          : 건설공사 O, 타어휘 [] → CONSTRUCTION
```
- **단일 기준 일치. 암묵 기준(타 sector 어휘로 판정) 없음. Report와 실제 판정 로직 일치.** (기준의 옳고그름은 판단 안 함 — 실제 사용 기준만 확인.)

## STEP 5 — B 표본 선정 감사
- seed45 재현 → U-01 22·U-02 8·U-03 5·U-04 26·U-05 5 = **66, Audit-001 기록과 정확히 일치(재현 가능).**
- 각 분류 max(5,20%) 비례 표본 → 특정 U-분류 편중 없음. 표본 선정 규칙 명시·재현·무편향 확인.

## STEP 6 — Blind Spot 재평가
```text
BS-1 (Evidence 추출 정확성) : REDUCED
   표본 15/15 원문 대조 PASS. 111개 조문0 법령은 추출 누락이 아니라 원문 자체에
   적용범위 조문 없음. 표본이라 전수 아님 → RESOLVED 아닌 REDUCED.
BS-2 (건설공사 단일 기준)    : REDUCED
   A 3건 건설공사 기준으로만 판정·암묵기준 0·Report-로직 일치 확인.
   단 '타 sector 직접지시를 A로 인정할지'(AUDIT-002 BS-1)는 정책 미결 → 그 부분 UNCHANGED.
표본 선정 재현성            : RESOLVED (seed45 완전 재현, 편향 없음)
```

## STEP 7 — Audit Reliability 재판정: KEEP WITH LIMITATION
- Audit 신뢰성이 이전보다 향상(BS-1/BS-2 REDUCED, 표본 재현성 RESOLVED). REVIEW REQUIRED 아님.
- 그러나 완전 KEEP 아님: BS-1은 표본 검증(전수 아님), '타 sector 직접지시(건축물에 적용 등 3건)를 A로 볼지'는 정책 미결(UNCHANGED)로 남음.

## 남은 한계 (다음 WO 입력, 판단 아님)
- BS-1 전수화: 111개 조문0 법령 전량을 원문 대조하면 REDUCED→RESOLVED 가능(별도 WO).
- BS-2 잔여: '건축물에 적용/에만 적용' 형태 3건(AUDIT-002)을 A 기준에 포함할지 = WO-MAPPING-004 정책 결정.

## 상태 (Obs-004 커버리지 파이프라인)
```text
① Inventory(375)            ✓ WO-CHG-004
② Evidence Sheet(368)        ✓ WO-COVERAGE-001
③ Mapping Policy(패턴)        ✓ WO-MAPPING-001
④ Sector Draft(A3/B313/C59)   ✓ WO-MAPPING-002
⑤ Policy Validation(경계)      ✓ WO-MAPPING-003
⑥ Independent Audit(KEEP)     ✓ WO-AUDIT-001
⑦ Audit Blind Spot            ✓ WO-AUDIT-002 (KEEP WITH LIMITATION)
⑧ Evidence Chain Audit        ✓ WO-AUDIT-003 (KEEP WITH LIMITATION, BS-1/BS-2 REDUCED) ← 현재
⑨ Policy Approval → Rule      ← WO-MAPPING-004
⑩ DB 반영 CHG + Verify        ← WO-CHG-005
```
