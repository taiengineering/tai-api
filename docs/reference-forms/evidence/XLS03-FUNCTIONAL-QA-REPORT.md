---
wo: WO-REF01-XLS03-FUNCTIONAL-QA-REPAIR-003
date: 2026-10-11
status: BUILD_COMPLETE
correction_of: WO-REF01-XLS03-BULK-XLSX-BUILD-001
publication: NOT_FOR_PUBLICATION
---

# XLS03 기능 QA 교정 보고서

WO-REF01-XLS03-FUNCTIONAL-QA-REPAIR-003 FIX-A~E 완결 증거.

---

## 1. 교정 결과 요약

| 항목 | 결과 |
|------|------|
| 빌드 대상 | 118 |
| 빌드 성공 | 118 / 0 ERROR |
| 유효성 검사 PASS | 118 / 118 |
| 필드 커버리지 PASS | 118 / 118 |
| pytest | **188 passed / 0 failed** |
| 기존 PDF/DOCX 변경 | 0건 |

---

## 2. FIX-A — CHECKLIST 입력 검증 수정

**문제**: 모든 데이터 열에 ○/× 적용
**교정**: label이 `결과|여부|유무|확인 (+(입력))?$` 패턴으로 끝나는 열에만 적용

| 서식 | 수정 전 | 수정 후 |
|------|--------|--------|
| CITYGAS-01 | 4개 열 전체 | C열만 (점검결과) |
| REF-C067 | 5개 열 전체 | E열만 (확인) |
| PRA-22-09 | 6개 열 전체 | E/F열 (여부·확인) |
| RP-17 | 5개 열 전체 | C열만 (이수 여부) |

검증 regex: `(결과|여부|유무|확인)\s*(\(입력\))?\s*$`

테스트: `test_citygas01_only_result_col_validated` / `test_result_suffix_regex` (16개 파라미터)

---

## 3. FIX-B — 행 추가 및 누적 기능

**문제**: 고정 행 수에 필터/검증 범위 한정
**교정**: repeat_table → Excel Table (TableStyleMedium2)

| 항목 | 변경 내용 |
|------|---------|
| 데이터 구조 | Excel Table (자동 확장) |
| 행 사전 할당 | max(default_rows × 4, 60) 행 |
| 자동 필터 | Table 내장 (ws.auto_filter 미사용) |
| 데이터 유효성 | 전체 할당 행 적용 |
| 인쇄 범위 | `A1:{col}{row+200}` + fitToPage=1 |

테스트: `test_excel_table_present` / `test_table_row_count_exceeds_default`

---

## 4. FIX-C — 계산식 의미 검증 (전면 제거)

**문제**: `_NUMERIC_KEYWORDS` 기반 SUM 자동 생성
**교정**: 모든 SUM 수식 제거. 수식 생성 로직 삭제.

| 서식 유형 | 이전 | 이후 |
|---------|------|------|
| CALC_AGG 비금지 (10건) | SUM 수식 생성 | 수동 입력 전용 |
| FORMULA_DIRECTION_UNVERIFIED (3건) | SUM 금지 | SUM 금지 (유지) |
| 비율/달성률 열 | SUM 적용됨 | 제거 |

테스트: `test_no_sum_formulas` (CHW-02, P-20, P-26, REF-C016, GOV-10)

---

## 5. FIX-D — 섹션 정의 순서 렌더링 + 필드 커버리지

**문제**: 타입 그룹별 복잡한 index 비교 → 동일 콘텐츠 섹션 순서 오류 가능
**교정**: sections[] 정의 순서 그대로 렌더링

추가 수정:
- `approval` 섹션 level label 렌더링 추가 (REF-C016: `연간 교육계획`)
- 필드 커버리지 검증기 `xlsx_field_coverage.py` 신설

| 검증 항목 | 결과 |
|---------|------|
| 118종 basic_info 필드 | 118/118 PASS |
| 118종 repeat_table 컬럼 | 118/118 PASS |
| 118종 labeled_grid 레이블 | 118/118 PASS |
| 118종 freeform/approval 레이블 | 118/118 PASS |

테스트: `test_field_coverage_all_118` / `test_ref_c016_approval_label_rendered`

---

## 6. FIX-E — 문서 메타데이터

모든 .xlsx 파일에 다음 메타데이터 포함:
- `title`: 서식명
- `description`: `TAI-FORM | {rid} | INTERNAL_POC_ONLY | LEGAL_REVIEW_PENDING | RIGHTS_UNVERIFIED | GPT_REVIEW_REQUIRED`
- `creator`: TAI

테스트: `test_document_metadata`

---

## 7. pytest 188/188 PASS

```
pytest test_xlsx_builder.py
  188 passed / 0 failed
  (구버전 156 → 교정 후 188)
```

테스트 분류:
| 범주 | 건수 |
|------|------|
| Registry/JSON | 5 |
| 기본 빌드 | 12 |
| 제목·메타데이터 | 6 |
| Excel Table (FIX-B) | 9 |
| Checklist validation (FIX-A) | 22 |
| 수식 금지 (FIX-C) | 8 |
| 섹션 순서/필드 (FIX-D) | 7 |
| 전수 Validation | 118 |
| **합계** | **188** |

---

## 8. 미검증 사항 (UNVERIFIED)

| 항목 | 상태 |
|------|------|
| Excel GUI 실제 입력·저장·재열기 | UNVERIFIED |
| 사용자 행 추가 후 Table 확장 GUI 확인 | UNVERIFIED |
| 인쇄 출력·PDF 변환 레이아웃 | UNVERIFIED |
| REF-C002 어댑터 필드 시각 배치 | UNVERIFIED |
| REF-C067 `점검 결과(양호/불량/해당없음)` 별도 드롭다운 | NOT_IMPLEMENTED |

---

## 9. 기존 파일 불변

```
output/*.pdf  → 147건 변경 없음
output/*.docx → 145건 변경 없음
scripts/*.json → 변경 없음
common_v1_engine.py → 변경 없음
batch_build.py → 변경 없음
```

---

## 10. 법률·권리·공개 HOLD 유지

모든 서식: `LEGAL_REVIEW_PENDING | RIGHTS_UNVERIFIED | INTERNAL_POC_ONLY | GPT_REVIEW_REQUIRED`
