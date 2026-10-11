# WO-058 Phase B-R2 — 공통 엔진 설계 보완 보고서

Date: 2026-10-09
Goal: G-muzv7o29-b4a5ab
Branch: docs/tai-reference-forms-charter-obj-20261008
Status: PHASE_B_R2_COMPLETE — GPT 독립검증 대기
Supersedes: WO-058-B-R1-REPORT.md

---

## 0. R2 작업 배경

Phase B-R1 GPT 검증에서 공통 엔진 설계 불완전으로 CONDITIONAL FAIL 판정. 3가지 지적:

| 지적 | 내용 | R2 수정 |
|---|---|---|
| R05 PARTIAL | 결재 열 너비 가변 미검증 | 생성기 코드 조사 + 가변 열 너비 계약 명세 |
| R04 PARTIAL | C002 basic_info 블록 미정의 | basic_info 블록 타입 추가 |
| R08 FAIL | 공통 assembler가 NICE_TO_HAVE로 분류 | MANDATORY로 격상, 계약 명세 |

---

## 1. R2-01: 결재란 가변 열 너비 조사

### 1.1 PDF 생성기 (`gen_c002_pdf.py`) 조사 결과

| 위치 | 코드 | 결함 |
|---|---|---|
| line 60 | `APPR_CELL_W = APPROVAL_W / 3` | 제수 3 하드코딩 |
| line 122 | `['', '', '']` | 서명 행 빈 셀 3개 하드코딩 |
| line 123 | `colWidths=[APPR_CELL_W] * 3` | 너비 배열 3개 하드코딩 |

C012 (2역할) 적용 시: 열 수는 2개여야 하나 코드는 3열 테이블을 생성 → 구조 오류 발생.

### 1.2 DOCX 생성기 (`gen_c002_docx.cjs`) 조사 결과

| 위치 | 코드 | 결함 |
|---|---|---|
| line 27 | `const APPR_CELL_W = Math.round(APPROVAL_W / 3)` | 제수 3 하드코딩 |
| line 127 | `apprF.map(f => hdrCell(f.label, APPR_CELL_W, 6))` | 셀 수는 동적, **너비 30mm 고정** |
| line 131 | `apprF.map(() => new TableCell({...}))` | 셀 수 동적 ✓, 너비 `APPR_CELL_W` = 30mm 고정 |

DOCX는 셀 수는 `apprF.map()`으로 동적이므로 C012에서 2칸 생성은 되나 너비가 30mm/칸 (C012는 45mm/칸이어야 함).

### 1.3 가변 열 너비 계약 (Phase C 적용 대상)

```
APPR_CELL_W = approval_section['total_width_mm'] / len(approval_section['fields'])
```

구현 위치: 각 생성기의 `build_approval(section)` 함수 내부 계산. 전역 상수 제거.

---

## 2. R2-02: 공통 스키마 완성

### 2.1 basic_info 블록 추가

c002_fields.json에 `basic_info` 최상위 키 존재 확인. 이를 common-v1 블록 타입으로 정의:

```json
{
  "type": "basic_info",
  "layout": "2col_2row",
  "fields": [ {"id":"N01","label":"..."}, ... ]
}
```

C002 common-v1 표현(설계 비교용)에 포함. C012 기본 서식에는 없음.

### 2.2 repeat_table 열 너비

c002_fields.json의 `plan_table.columns[].width_mm` 이미 존재 확인 (line 39–45). 공통 스키마가 이를 따른다:

```json
"columns": [
  {"id":"F05","label":"목표·세부\n추진계획","width_mm":56,"align":"left"},
  ...
]
```

Phase C에서 `build_repeat_table(section)` 구현 시 `columns[i]['width_mm'] * mm` 사용. `COL_WIDTHS` 상수 의존 금지.

### 2.3 블록 검증 규칙 추가

- 알 수 없는 `type` → ValueError/Error (fail-closed)
- `requiredness=UNVERIFIED` → 렌더링 스킵 금지
- 필수 속성 누락 → 오류

---

## 3. R2-03: 공통 assembler MANDATORY 격상

**변경 전 (B-R1)**: assembler JSON-driven화 = NICE_TO_HAVE (GAP-05).  
**변경 후 (B-R2)**: assembler = **MANDATORY**. 서식별 별도 조립 함수 금지.

### 3.1 assembler 계약 요약

1. `build_title(fields)` 항상 첫 번째 — sections 외부 처리
2. `sections` 배열 순서대로 처리
3. 각 블록 `type`에 따라 빌더 함수 호출
4. 알 수 없는 type → 오류 (fail-closed)
5. `requiredness` 무관하게 모든 필드 렌더링

### 3.2 C002 생성기와의 관계

C002 기존 생성기(`buildDoc()` / `generate()`)는 변경 금지. C002는 flat JSON 구조를 사용하며 sections 배열 없음. C012부터 common assembler를 사용하는 새 생성기를 작성한다.

---

## 4. R2-04: 스키마 일치성 확인

### 4.1 c012_fields.json vs 설계서 블록 순서 대조

| 순서 | c012_fields.json sections | REF-C012-FIELD-SPEC-058.md v0.2 레이아웃 |
|---|---|---|
| (제목) | `document.title` (sections 외부) | 안전작업 허가서 (최상단) |
| 1 | `approval`: AP01 신청 / AP02 허가 | 결재란 신청/허가 2칸 우측 90mm |
| 2 | `labeled_grid`: F01~F08 4행 | 작업기본정보 2열 그리드 4행 |
| 3 | `freeform_area`: F09 작업내용 20mm | 작업내용 최소 20mm |
| 4 | `freeform_area`: F10 안전조치사항 30mm | 안전조치사항 최소 30mm |

**일치 ✓**: 블록 순서 및 내용 설계서와 JSON 완전 일치.

### 4.2 원본 관찰 vs TAI 추가 레이아웃 구분

| 항목 | 구분 |
|---|---|
| F01~F10 (작업종류~안전조치사항) | NATIVE_HWP_BODYTEXT_LABEL — 원본 관찰 텍스트 |
| AP01 신청, AP02 허가 | NATIVE_HWP_BODYTEXT_LABEL — OF-04/OF-11 매핑 |
| `labeled_grid` 2열 배치 | TAI 레이아웃 추정 — SOURCE_FIELDS_UNVERIFIED (원본 표 구조 미확인) |
| `freeform_area` min_height_mm | TAI 설계값 — 법적 필수 확인 전 UNVERIFIED |

---

## 5. R2-05: Goal 확인

| 항목 | 확인 결과 |
|---|---|
| PRJ 조회 | `mcp__claude_ai_guri-cf__goal` action=show code=`G-muzv7o29-b4a5ab` |
| 상태 | **ACTIVE** |
| 제목 | "WO-058 Phase A REF-C012 안전작업허가서 READ ONLY 조사" |
| opened_at | 2026-10-08 18:23:45 UTC |
| project | tai-api |
| 판정 | **VERIFIED** — Goal 활성 확인됨. 제목이 Phase A 기준이나 WO-058 전체(A/B/C) 포괄 |

---

## 6. GAP 목록 (B-R2 최종)

| GAP ID | B-R1 분류 | B-R2 변경 | Phase C 필수 |
|---|---|---|---|
| GAP-01 | REQUIRED | 변경 없음 | **REQUIRED** |
| GAP-02 | REQUIRED | 변경 없음 | **REQUIRED** |
| GAP-03 | NONE | → **REQUIRED (열 너비 한정)** | **REQUIRED** |
| GAP-04 | NOT REQUIRED for C012 | 변경 없음 | NOT REQUIRED |
| GAP-05 | NICE_TO_HAVE | → **MANDATORY** | **REQUIRED** |
| GAP-06 | REQUIRED | 변경 없음 | **REQUIRED** |
| GAP-07 | REQUIRED | 변경 없음 | **REQUIRED** |
| GAP-08 | (신규) | repeat_table 열 너비 columns[] 연동 | NOT REQUIRED (C012 미사용) |

**Phase C 최소 착수 조건**: GAP-01/02/03/05/06/07 해소.

---

## 7. 수정 산출물

| 파일 | 변경 내용 |
|---|---|
| `design/COMMON-ENGINE-SCHEMA-058.md` | v0.2 수정 — 가변 결재 너비 계약, basic_info 블록, repeat_table width_mm, 공통 assembler MANDATORY, fail-closed 규칙, C002 common-v1 표현 |
| `qa/WO-058-B-R2-REPORT.md` | 신규 — 이 보고서 |

**변경 없음**: c012_fields.json, REF-C012-FIELD-SPEC-058.md, c002_fields.json, gen_c002_pdf.py, gen_c002_docx.cjs.

---

## 8. GPT 독립검증 요청 항목

| # | 검증 항목 |
|---|---|
| V01 | 결재 가변 열 너비 계약 `APPR_CELL_W = total_width_mm / len(fields)` 이 PDF(line60/122/123)·DOCX(line27/127/131) 결함을 올바르게 해소하는가? |
| V02 | basic_info 블록 타입 정의가 c002_fields.json의 flat 구조를 올바르게 common-v1로 표현하는가? |
| V03 | repeat_table에서 `columns[].width_mm` JSON 기반 계약이 현재 `COL_WIDTHS` 상수와의 차이를 올바르게 해소하는가? |
| V04 | 공통 assembler 계약(title 항상 첫 번째 + sections 순서 처리 + fail-closed)이 C012 Phase C 생성기에 충분한 명세인가? |
| V05 | C002 flat JSON을 common-v1 sections로 표현한 매핑표가 c002_fields.json 내용과 정확히 일치하는가? |
| V06 | GAP-03 격상(NONE → REQUIRED 열 너비 한정), GAP-05 격상(NICE_TO_HAVE → MANDATORY) 이 타당한가? |
| V07 | R2-04 일치성 확인 결과 — c012_fields.json과 REF-C012-FIELD-SPEC-058.md v0.2의 블록 순서·내용이 일치한다는 판정이 정확한가? |
| V08 | Goal `G-muzv7o29-b4a5ab` ACTIVE VERIFIED로 Goal ID 불일치 문제가 해소됐는가? |
