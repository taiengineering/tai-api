---
wo: WO-AUDIT-002
class: records
type: audit
scope: canonical
project: test-universe
title: Audit Blind Spot Verification
version: 1
status: active
owner: taiwang
---

# AUDIT-OF-AUDIT — WO-AUDIT-002 Audit Blind Spot Verification

> WO-AUDIT-001(6279242f)의 결과를 신뢰하지 않는다는 전제로, 감사가 무엇을 검증하지 못했는지(Blind Spot)만 찾는다. Mapping/Policy/Draft/DB/sector 수정 없음, 새 규칙 없음, 추론 없음.

## 판정: KEEP WITH LIMITATION

## STEP 1-2 — Audit-001이 실제 검증한 범위
- A 3건: **전수**. 원문 적용범위에 "건설공사" 명시 vs sector=CONSTRUCTION 일치 → PASS.
- C 59건: **전수**. 소방공통/4종+시설 = MULTI → PASS.
- B: **표본** 66/302(층화 20%+, seed45). 원문에 "건설공사" 없음 = UNRESOLVED 정당 → PASS.
- **검증 방법의 본질:** 모든 판정이 "원문 적용범위에 '건설공사' 문자열이 있는가"라는 단일 기준에 의존.
- **PASS 제외 범위(Audit가 명시적으로 대상 아님):** "B가 최종 어느 sector인가"(결정 불가), B 원문미확보 7.

## STEP 3 — Blind Spot 목록 (판단 없이, 목록만)
- **BS-1** Audit가 "건설공사" 문자열만 sector 직접지시로 인정 → 다른 sector "...에 적용" 표현 미검증.
- **BS-2** Evidence 추출 정확성 미검증(coverage_evidence.csv를 주어진 것으로 신뢰).
- **BS-3** C 소방 판정이 법령 title(NFTC/NFPC) 기준 — 원문 적용범위 대조 아님.
- **BS-4** Inventory(375) 모집단 정확성 미검증.
- **BS-5** Pattern 분류·U/M 이유분류 자체의 타당성 미재검증(분류 결과만 대조).

## STEP 4-5 — 영향도 + KEEP 영향 (Evidence만)
| BS | 영향도 | KEEP 영향 | Evidence |
|---|---|---|---|
| BS-1 | MEDIUM | **POSSIBLE IMPACT** | B 중 3건이 "건축물에 적용"/"에만 적용" 형태 보유(에너지원단위 목표관리 고시·전기용품 안전기준 KC·표면처리업종 고시). Audit의 단일 키워드 기준이 미검출. 실제 직접지시라면 A가 늘어야 함 → 분류 정확성 판정 부분 흔들림 |
| BS-2 | MEDIUM | **POSSIBLE IMPACT** | 원문확보 368 중 111개가 목적/적용범위 조문 0개 = 적용대상이 타 조문에 있거나 추출 누락 가능. 추출 불완전 시 B의 UNRESOLVED 근거(원문에 sector 없음)가 약해짐 |
| BS-3 | LOW | NO IMPACT | 58/59 title 판정이나, 소방=전 시설 적용은 WO-MAPPING-001에서 원문 다패턴으로 이미 확인 → title이어도 결론 동일 |
| BS-4 | LOW | NO IMPACT | 미매핑 모집단 375는 WO-CHG-004에서 SQL(768중 375) 근거 확보. Audit 미재확인일 뿐 결론 불변 |
| BS-5 | LOW | NO IMPACT | 이유코드(U-04 등)는 다음 정책 입력용이지 A/B/C 경계엔 무관 → KEEP 불변 |

- POSSIBLE IMPACT: 2 (BS-1, BS-2) · NO IMPACT: 3 (BS-3,4,5) · UNKNOWN: 0.

## STEP 6 — 최종 판정: KEEP WITH LIMITATION
- Audit-001의 KEEP은 유지하되, 두 한계 하에서:
  - **BS-1:** Audit의 sector 직접지시 검증이 "건설공사" 단일 키워드에 국한 → B 중 다른 sector 직접지시(3건)를 놓쳤을 수 있음. A=3이 하한일 가능성.
  - **BS-2:** Evidence 추출(coverage_evidence.csv)의 완전성이 감사되지 않음 → 111개 조문 0개 법령의 적용대상이 추출 밖에 있을 수 있음.
- 이 한계는 KEEP을 뒤집지 않음(REVIEW REQUIRED 아님): A/C 판정은 원문 직접 대조로 견고, B 표본 0 FAIL. 그러나 무조건 KEEP도 아님 — BS-1/BS-2가 POSSIBLE IMPACT.

## 다음 (관측 — 판단 아님, 다음 WO 입력)
- BS-1: 다음 Mapping WO에서 sector 직접지시 인정 표현을 "건설공사"에서 확장(건축물/사업장 등 원문 "...에 적용" 형태)해 B 3건 재검토.
- BS-2: Evidence 추출 필터를 목적/적용범위 외 조문까지 확장해 111개 조문0 법령 재추출 검토.
- 둘 다 본 WO 범위 밖(Audit만). Mapping·추출 수정은 별도 WO.

## 상태 (Obs-004 커버리지 파이프라인)
```text
① Inventory(375)            ✓ WO-CHG-004
② Evidence Sheet(368)        ✓ WO-COVERAGE-001 (1f8c9fb2)
③ Mapping Policy(패턴)        ✓ WO-MAPPING-001 (93f102d2)
④ Sector Draft(A3/B313/C59)   ✓ WO-MAPPING-002 (4a3de887)
⑤ Policy Validation(경계)      ✓ WO-MAPPING-003 (4ee1e717)
⑥ Independent Audit(KEEP)     ✓ WO-AUDIT-001 (6279242f)
⑦ Audit Blind Spot           ✓ WO-AUDIT-002 (KEEP WITH LIMITATION) ← 현재
⑧ Policy Approval → Rule      ← WO-MAPPING-004 (BS-1/BS-2 반영)
⑨ DB 반영 CHG + Verify        ← WO-CHG-005
```
