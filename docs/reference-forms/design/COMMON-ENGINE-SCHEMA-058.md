---
doc_id: TAI-DESIGN-COMMON-ENGINE-V0.1
title: TAI 서식 공통 렌더러 스키마 설계서
version: 0.1-DRAFT
status: PHASE_B_R1_DRAFT — GPT 독립검증 대기
date: 2026-10-09
branch: docs/tai-reference-forms-charter-obj-20261008
scope: common-v1 스키마 블록 타입 정의 및 C002/C012 매핑 비교
wo: WO-058 Phase B-R1
---

# TAI 서식 공통 렌더러 스키마 설계서 v0.1

## 0. 목적

여러 서식(C002, C012 등)을 단일 렌더러가 처리할 수 있도록, JSON 필드 명세의 `sections` 배열에서 사용하는 블록 타입(block type)을 정의한다. 이 문서는 **설계 명세**이며, 생성기 구현은 Phase C에서 수행한다.

---

## 1. 스키마 식별자

```
schema_version: "common-v1"
```

모든 서식 필드 명세 JSON의 `_meta.schema_version`에 기재한다.

---

## 2. 최상위 구조

```json
{
  "_meta": {
    "wo": "...",
    "form_type": "FORM | PLAN | CHECKLIST | ...",
    "source_id": "REF-Cxxx",
    "schema_version": "common-v1",
    ...
  },
  "document": {
    "title": "...",
    "doc_id": "...",
    "version": "...",
    "subject": "...",
    "creator": "...",
    "producer": "..."
  },
  "sections": [ <block>, <block>, ... ]
}
```

렌더러는 `sections` 배열을 순서대로 처리한다. 각 블록은 `type` 키로 분기한다.

---

## 3. 블록 타입 정의

### 3.1 `title`

문서 제목 행. 170mm 전체 너비, 중앙 굵은 글씨.

```json
{
  "type": "title"
}
```

렌더러는 `document.title`을 읽어 출력한다. 별도 데이터 필드 없음.

**현재 구현 상태**: `buildTitle(fields)` / `build_title(fields)` — C002에서 이미 구현됨. 그대로 재사용.

---

### 3.2 `approval`

결재란. 우측 정렬 90mm 테이블. 헤더 행(레이블) + 서명 행.

```json
{
  "type": "approval",
  "total_width_mm": 90,
  "min_header_height_mm": 7,
  "min_sign_height_mm": 15,
  "fields": [
    { "id": "AP01", "label": "레이블1", "source": "...", "requiredness": "UNVERIFIED" },
    { "id": "AP02", "label": "레이블2", "source": "...", "requiredness": "UNVERIFIED" }
  ]
}
```

- `fields` 배열의 길이로 열 수를 결정 (C002=3열, C012=2열).
- 열 너비 = `total_width_mm / fields.length`.
- 레이블은 `f.label`에서 읽음 — 하드코딩 없음.

**현재 구현 상태**: `buildApproval(fields)` / `build_approval(fields)` — C002에서 이미 구현됨. `fields.approval.fields` 배열을 그대로 소비하는 구조. C012에서는 `sections`의 `approval` 블록 `fields` 배열을 동일 방식으로 전달하면 됨. **코드 수정 불필요 (GAP-03 = NONE 재확인).**

---

### 3.3 `labeled_grid`

2열 그리드 기본정보 섹션. 각 셀에 라벨+기재란.

```json
{
  "type": "labeled_grid",
  "section_label": "섹션 제목 (선택)",
  "row_height_mm": 7,
  "rows": [
    [
      { "id": "F01", "label": "라벨A", "source": "...", "requiredness": "UNVERIFIED" },
      { "id": "F02", "label": "라벨B", "source": "...", "requiredness": "UNVERIFIED" }
    ],
    ...
  ]
}
```

- `rows`는 행 배열. 각 행은 정확히 2개의 셀 객체를 가진다.
- 열 너비: `CONTENT_W / 2` = 85mm (각 열).
- `section_label` 존재 시 상단 전체너비 헤더 행 추가.

**현재 구현 상태**: **없음** — C002에 유사 패턴 없음. **GAP-01 신규 빌더 필요.**

예상 인터페이스:
```python
# PDF
def build_labeled_grid(section_label, rows, col_half_w=CONTENT_W/2, row_h=ROW_H_INFO):
    """rows: [[{id, label}, {id, label}], ...]"""
```
```js
// DOCX
function buildLabeledGrid(sectionLabel, rows, colHalfW = mm(85), rowH = ROW_H_INFO)
```

---

### 3.4 `freeform_area`

전체 너비 자유 기재란. 라벨 헤더 행 + 빈 기재 공간 행.

```json
{
  "type": "freeform_area",
  "id": "F09",
  "label": "작업내용",
  "source": "...",
  "min_height_mm": 20,
  "requiredness": "UNVERIFIED"
}
```

- 전체 너비 170mm.
- `min_height_mm`로 기재 공간 최소 높이 제어.
- 라벨 헤더 행 높이: 7mm (ROW_H_INFO).

**현재 구현 상태**: C002의 `buildCorporateGoal(fields)` / `build_corporate_goal(fields)` 패턴과 동일하나 "전사목표" 하드코딩됨. **GAP-02: 파라미터화 필요.**

예상 인터페이스:
```python
# PDF
def build_freeform_area(label, min_height_mm=20):
    """라벨 헤더 행 + 빈 기재 공간 행"""
```
```js
// DOCX
function buildFreeformArea(label, minHeightMm = 20)
```

---

### 3.5 `repeat_table`

다중 행 반복 테이블 (계획표, 목록표 등). C002 `plan_table`이 이 유형.

```json
{
  "type": "repeat_table",
  "default_row_count": 10,
  "extra_rows_note": "... (선택)",
  "columns": [
    { "id": "C01", "label": "열 제목", "width_mm": 56, "align": "left" },
    ...
  ]
}
```

**현재 구현 상태**: `buildPlanTable(fields, exRows)` / `build_plan_table(fields)` — C002에서 구현됨. `COL_WIDTHS`가 C002 전용으로 하드코딩됨. `columns[].width_mm`으로 구동하도록 파라미터화 필요 — **GAP-08 (Phase C 이후 검토).**

---

## 4. C002 vs C012 공통 스키마 비교

| 섹션 순서 | C002 블록 타입 | C002 블록 내용 | C012 블록 타입 | C012 블록 내용 |
|---|---|---|---|---|
| 1 | `title` | 안전보건관리 계획서 | `title` | 안전작업 허가서 |
| 2 | `approval` | 작성/검토/승인 (3역할) | `approval` | 신청/허가 (2역할) |
| 3 | `basic_info` (미분류) | N01~N04 2행 4필드 | — (없음) | 기본 서식에서 제외 |
| 4 | `freeform_area` | 전사목표 (단일) | `labeled_grid` | F01~F08 2열 4행 그리드 |
| 5 | `repeat_table` | 6열 계획표 | `freeform_area` | 작업내용 F09 (20mm) |
| 6 | — | — | `freeform_area` | 안전조치사항 F10 (30mm) |

**공통 블록 재사용**: `title` (100%), `approval` (레이블/칸수만 다름, 코드 동일).

**C002 전용 미분류 블록**: `basic_info` — common-v1에 아직 미정의. C002 기존 구현(`buildBasicInfo`) 유지. C012에는 해당 섹션 없음 → 영향 없음.

---

## 5. 렌더러 조립 로직 (assembler) — Phase C 설계 방향

현재 `buildDoc()` / `generate()`는 섹션 순서를 함수 호출로 하드코딩한다.

Phase C에서 `sections` 배열을 순회하며 `type`에 따라 빌더 함수를 호출하는 공통 assembler로 교체 가능:

```js
// 개념 코드 (구현 아님)
for (const section of fields.sections) {
  switch (section.type) {
    case 'title':         children.push(buildTitle(fields)); break;
    case 'approval':      children.push(buildApproval(section)); break;
    case 'labeled_grid':  children.push(buildLabeledGrid(section)); break;
    case 'freeform_area': children.push(buildFreeformArea(section.label, section.min_height_mm)); break;
    case 'repeat_table':  children.push(buildRepeatTable(section, exRows)); break;
  }
}
```

**GAP-05**: 이 assembler 교체는 **NICE_TO_HAVE** — C012 전용 생성기는 하드코딩 assembler로도 구현 가능. 5형식 이상 확장 시 중요.

---

## 6. Phase C 착수 전 최소 GAP 해소 목록

| GAP ID | 분류 | 설명 | 영향 서식 | 우선순위 |
|---|---|---|---|---|
| GAP-01 | 신규 빌더 | `labeled_grid` 빌더 — 2열 그리드 정보 섹션 | PDF + DOCX | **REQUIRED** |
| GAP-02 | 파라미터화 | `freeform_area` 빌더 — `build_corporate_goal` 파라미터화 | PDF + DOCX | **REQUIRED** |
| GAP-03 | — | `approval` 이미 JSON-driven — 코드 수정 불필요 | — | **NONE** |
| GAP-04 | 선택 | `basic_info` 파라미터화 — C012에 basic_info 없으므로 C012 착수에 불필요 | PDF + DOCX | **NOT REQUIRED for C012** |
| GAP-05 | 아키텍처 | assembler JSON-driven화 | PDF + DOCX | NICE_TO_HAVE |
| GAP-06 | 인프라 | `package.json` scripts 다중 서식 지원 | Node.js | **REQUIRED** |
| GAP-07 | 인프라 | Python entry point 다중 서식 지원 | Python | **REQUIRED** |

**Phase C 착수 조건**: GAP-01, GAP-02, GAP-06, GAP-07 해소 + 이 문서 GPT 독립검증 PASS.

---

## 7. 제약 사항

- 이 문서는 설계 명세이며 구현 코드가 아님
- Phase C 구현은 GPT 독립검증 PASS + 블로커(SOURCE_FIELDS_UNVERIFIED / LEGAL_REVIEW_PENDING / RIGHTS_UNVERIFIED) 해소 방침 결정 후 착수
- c002_fields.json 기존 구조 변경 금지 (C002 기존 생성기 호환성 유지)
