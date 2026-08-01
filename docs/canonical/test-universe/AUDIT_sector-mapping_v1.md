---
wo: WO-AUDIT-001
class: records
type: audit
scope: canonical
project: test-universe
title: Sector Mapping 독립 감사
version: 1
status: active
owner: taiwang
---

# AUDIT REPORT — WO-AUDIT-001 Sector Mapping 독립 감사

> WO-MAPPING-001~003의 결론(A=3/B=313/C=59)을 신뢰하지 않는다는 전제로 독립 감사. 정책·Draft·DB 무수정. 새 Evidence 생성 없음. Claude 분류가 Evidence(원문)와 일치하는지만 검증.
> Input(그대로 사용): Inventory(375), Evidence Sheet(1f8c9fb2), Mapping Policy(93f102d2), Validation(4ee1e717), Sector Draft(4a3de887).

## 판정: KEEP

## STEP 2 — A=3 전수 감사
| 법령 | Claude sector | 원문 적용범위 | 판정 |
|---|---|---|---|
| 건설공사 안전보건대장 작성 고시 | CONSTRUCTION | 제3조 "총공사금액 50억원 이상인 건설공사에 적용" | PASS |
| 건설업 산업안전보건관리비 계상 기준 | CONSTRUCTION | 제3조 "법 제2조제11호의 건설공사 중…에 적용" | PASS |
| 내진설계 일반 KDS 17 | CONSTRUCTION | 1.2 "「건설산업기본법」…건설공사의 내진설계에 적용" | PASS |
**A: 3/3 PASS.** 세 건 모두 원문 적용범위에 "건설공사" 직접 명시, sector=CONSTRUCTION 일치. 추론 0.

## STEP 3 — B 표본 감사
- **표본 선정 규칙:** 5개 U-분류(U-01~U-05)에서 각 max(5, 20%) 층화 표본(소분류는 전수), seed=45. 편향 방지.
- 표본: U-01 22/112 · U-02 8/44 · U-03 5/9 · U-04 26/130 · U-05 5/11 = **총 66/302**.
- 각 표본의 원문 적용범위에 sector 직접 지시("건설공사" 등)가 있는지 대조 → 있으면 UNRESOLVED 오류(FAIL), 없으면 정당(PASS).
- **B: 66/66 PASS, FAIL 0.** 표본 전부 원문에 sector 직접 지시 없음 = UNRESOLVED 정당. Claude가 A였어야 할 것을 B로 놓친 사례 표본 내 미발견.

## STEP 4 — C=59 전수 감사
- 각 C가 정말 단일 sector 불가(소방 공통 OR 시설 4종+)인지 원문 대조.
- **C: 59/59 PASS, FAIL 0.** 내역: 소방 공통기준 58 + 4종+ 시설 1. 모두 MULTI_TARGET 정당.

## STEP 5 — Audit Accuracy
```text
A : 3 / 3 PASS
B : 66 / 66 PASS (표본, 층화 20%+)
C : 59 / 59 PASS (전수)
FAIL : 0건
```

## STEP 6 — FAIL 분석
- FAIL 0건 → 해당 없음.

## STEP 7 — Audit 결론
- **KEEP.** 원문 대조 감사에서 A 전수·C 전수·B 표본 모두 Evidence와 일치, FAIL 0.

## 감사의 한계 (정직 기록)
- B는 표본 감사(66/302 원문확보분). 표본 밖 미검출 FAIL 가능성은 통계적으로 배제 불가 — 단 층화 20%+에서 0 FAIL은 강한 신호.
- 본 감사는 "Claude가 결정 가능(A)한 것을 B/C로 놓쳤는가"(누락 방향) 및 "A/C 분류가 원문과 일치하는가"를 검증. "B가 최종적으로 어느 sector인가"는 이 단계에서 애초에 결정 불가(정책 규칙 미수립)이므로 감사 대상이 아님.
- B 원문미확보 7(군형법·난민법 등)은 표본 대상에서 제외(원문 없음 = UNRESOLVED 자명).

## 상태 (감사 결과 반영)
```text
Sector Draft(4a3de887) A3/B313/C59 = KEEP (독립 감사 PASS, FAIL 0)
Obs-004 커버리지 파이프라인 ⑤(Validation)까지 감사 통과.
다음: ⑥ WO-MAPPING-004 (Policy Approval → Rule → Draft Revision)
```
