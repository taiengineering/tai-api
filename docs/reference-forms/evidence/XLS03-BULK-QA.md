---
wo: WO-REF01-XLS03-BULK-XLSX-BUILD-001
date: 2026-10-11
status: BUILD_COMPLETE
publication: NOT_FOR_PUBLICATION
---

# XLS03 일괄 XLSX 제작 QA 증거

WO-REF01-XLS03-BULK-XLSX-BUILD-001 Phase A–F 완결 증거.

---

## 1. 제작 요약

| 항목 | 수치 |
|------|------|
| 제작 대상 | 118 |
| 제작 완료 | 118 |
| ERROR | 0 |
| 기존 PDF 수 (output/) | 147 |
| 기존 DOCX 수 (output/) | 145 |
| 기존 파일 변경 | 0 |
| 신규 XLSX 수 (output/xlsx/) | 118 |

---

## 2. 디자인 유형별 현황

| 디자인 유형 | 건수 |
|-----------|------|
| CUMULATIVE | 29 |
| CALC_AGG | 13 |
| DATE_STATUS | 11 |
| CHECKLIST | 30 |
| DAILY_LOG | 8 |
| DOC_TABLE | 24 |
| PLAN_EVAL | 3 |
| **합계** | **118** |

---

## 3. FORMULA_DIRECTION_UNVERIFIED 계산식 통제

| research_id | 조치 |
|-------------|------|
| CHW-03 | 모든 데이터 셀 INPUT(연분홍), 수식 없음 (NOFORMULA) |
| REF-C029 | 모든 데이터 셀 INPUT(연분홍), 수식 없음 (NOFORMULA) |
| REF-C004 | 모든 데이터 셀 INPUT(연분홍), 수식 없음 (NOFORMULA) |

pytest `test_no_formulas_in_forbidden` — 3건 전원 PASS.

---

## 4. 공통 XLSX 기능 검증 (pytest 156/156 PASS)

| 기능 | 검증 방법 | 결과 |
|------|---------|------|
| 파일 생성 (.xlsx 유효) | openpyxl load + sheetnames | PASS |
| 제목 행 (A1 비어있지 않음) | ws.cell(1,1).value | PASS |
| 자동 필터 | ws.auto_filter.ref | PASS |
| 틀 고정 (freeze_panes) | ws.freeze_panes | PASS |
| 인쇄 영역 | ws.print_area | PASS |
| FORMULA_DIRECTION 수식 금지 | cell.value.startswith("=") 검사 | PASS (3건) |
| CHECKLIST 데이터 유효성 | ws.data_validations (○/×) | PASS |
| validate_xlsx() 전수 검사 | 118건 전원 PASS | PASS |

```
pytest test_xlsx_builder.py
  156 passed / 0 failed
```

---

## 5. 공통 XLSX 구현 사항

### 셀 색상 규칙
| 색상 | 코드 | 용도 |
|------|------|------|
| 연청색 | DCE6F1 | INPUT (일반 입력 셀) |
| 연황색 | FFF2CC | CALC_AGG 입력 셀 |
| 연분홍 | FFCCCC | NOFORMULA (계산 방향 미검증) |
| 연녹색 | E2EFDA | CHECKLIST 데이터 셀 |
| 어두운 파랑 | 1F3864 | 제목 행 배경 |
| 중간 파랑 | 2F5496 | repeat_table 헤더 |
| 연회색 | D9D9D9 | basic_info 레이블 |

### Excel 기능
- 헤더 행 틀 고정 (freeze_panes)
- repeat_table 자동 필터
- CHECKLIST: ○/× 드롭다운 데이터 유효성
- CALC_AGG (비금지): 수치 컬럼에 SUM 수식 행 추가
- 인쇄 방향: JSON page.orientation (landscape/portrait) 적용
- 인쇄 영역: 모든 사용 행/열 지정
- fitToWidth=1 (1페이지 가로 맞춤)

### REF-C002 레거시 어댑터
xlsx_schema_adapter.py가 c002_fields.json (plan_table 구조)을
common-v1 sections 형식으로 변환. c002_fields.json 변경 없음.

---

## 6. 신규 파일 목록

```
docs/reference-forms/xlsx/
  xlsx_builder.py          (신규)
  xlsx_schema_adapter.py   (신규)
  xlsx_registry.py         (신규 — 118건 레지스트리)
  xlsx_validation.py       (신규)
  run_xlsx_build.py        (신규)
  test_xlsx_builder.py     (신규)

docs/reference-forms/output/xlsx/
  TAI-FORM-*.xlsx × 118   (신규)

docs/reference-forms/evidence/
  XLS03-118-BUILD-RESULT.csv  (신규)
  XLS03-BULK-QA.md            (신규)
```

---

## 7. 기존 파일 불변 증거

```
output/*.pdf  → 147건 변경 없음
output/*.docx → 145건 변경 없음
scripts/*.json → 변경 없음
common_v1_engine.py → 변경 없음
batch_build.py → 변경 없음
```

---

## 8. 미검증 사항

| 항목 | 내용 |
|------|------|
| WORD_INTERACTIVE_QA | Excel 실제 입력·저장·재열기 검증 미수행 |
| 화면 표시 QA | Excel GUI에서 레이아웃 시각 확인 미수행 |
| 인쇄 출력 QA | 실제 인쇄 또는 PDF 변환 후 레이아웃 확인 미수행 |
| REF-C002 어댑터 필드 순서 | gen_c002_pdf.py 렌더링과 시각 일치 여부 미확인 |

---

## 9. 법률·권리·공개 HOLD 유지

| 항목 | 상태 |
|------|------|
| legal_review_status | PENDING (전체) |
| rights_status | RIGHTS_UNVERIFIED (전체) |
| publication_status | INTERNAL_POC_ONLY (전체) |
| design_gate_status | GPT_REVIEW_REQUIRED (전체) |
