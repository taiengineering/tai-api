---
wo: WO-REF01-XLS02-MAX-COVERAGE-SCOPE-001
date: 2026-10-11
status: SCOPE_FIXED
publication: NOT_FOR_PUBLICATION
---

# XLS02 범위 확정 QA 증거

WO-REF01-XLS02-MAX-COVERAGE-SCOPE-001 범위 산출물 정합성 검증.

---

## 1. 분류 집계 검증

| 구분 | 수량 | 기대값 | 결과 |
|------|------|--------|------|
| XLSX_BUILD | 118 | 118 | PASS |
| REUSE_EXISTING | 25 | 25 | PASS |
| NON_APPLICABLE | 25 | 25 | PASS |
| DOC_PDF_ONLY | 20 | 20 | PASS |
| NEEDS_REVIEW | 1 | 1 | PASS |
| **합계** | **189** | **189** | PASS |

## 2. 상호 배타성 검증

- 전체 ID: 189 / 고유 ID: 189 / 중복: 0 — PASS

## 3. XLSX_BUILD 서식 유형별

| document_type | 수량 | 기대 | 결과 |
|--------------|------|------|------|
| REGISTER | 28 | 28 | PASS |
| CHECKLIST | 35 | 35 | PASS |
| RECORD | 23 | 23 | PASS |
| PLAN | 16 | 16 | PASS |
| EVALUATION | 7 | 7 | PASS |
| FORM | 5 | 5 | PASS |
| REPORT | 4 | 4 | PASS |

## 4. B15 미등록 8건 포함 확인

| research_id | final_decision | 비고 |
|-------------|---------------|------|
| PRA-22-02 | XLSX_BUILD | B14 인벤토리 수정 없음 |
| PRA-22-06 | DOC_PDF_ONLY | B14 인벤토리 수정 없음 |
| PRA-22-08 | DOC_PDF_ONLY | B14 인벤토리 수정 없음 |
| PRA-22-09 | XLSX_BUILD | B14 인벤토리 수정 없음 |
| PRA-22-10 | XLSX_BUILD | B14 인벤토리 수정 없음 |
| REF-C022 | XLSX_BUILD | B14 인벤토리 수정 없음 |
| REF-C023 | XLSX_BUILD | B14 인벤토리 수정 없음 |
| REF-C067 | XLSX_BUILD | B14 인벤토리 수정 없음 |

## 5. REUSE → XLSX 연결 불가 항목 (5건)

대표 서식이 DOC_PDF_ONLY이므로 XLSX 연결 없음. 허위 연결 금지.

| 재사용 서식 | 대표 서식 | 대표 서식 결정 |
|-----------|---------|------------|
| MNT-02 | RP-02 | DOC_PDF_ONLY |
| PRA-22-07 | RP-10 | DOC_PDF_ONLY |
| REF-C035 | REF-C013 | DOC_PDF_ONLY |
| REF-C036 | REF-C015 | DOC_PDF_ONLY |
| REF-C068 | P-05 | DOC_PDF_ONLY |

## 6. 미확인 사항 유지

| 항목 | 상태 |
|------|------|
| REF-C029 빈도×강도 배점 기준 | FORMULA_UNVERIFIED — 수동 입력 |
| CHW-03 차이수량 계산 방향 | FORMULA_DIRECTION_UNVERIFIED |
| REF-C004 수량 단위 합산 | 미결정 — 수동 입력 |
| REF-C007 연도 컬럼 범위 | 미결정 — 수동 입력 |
| REF-C072 | NEEDS_REVIEW 유지 |

## 7. 기존 파일 불변 선언

```
변경 파일:
  XLS02-189-FINAL-SCOPE.csv     (신규)
  XLS02-118-BUILD-MANIFEST.md   (신규)
  XLS02-SCOPE-QA.md             (신규)

기존 파일 변경:
  scripts/*.json → 0건  output/*.pdf → 0건  output/*.docx → 0건
  evidence/B14-189-INVENTORY.csv → 0건
```

## 8. 다음 단계

GPT XLS02 독립검증 → Owner 승인 → XLS03 118종 일괄 제작
GPT 독립검증 전 XLSX 제작 시작 금지.
