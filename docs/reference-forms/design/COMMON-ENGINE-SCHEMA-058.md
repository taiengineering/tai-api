---
doc_id: TAI-DESIGN-COMMON-ENGINE-V0.3
title: TAI 서식 공통 렌더러 스키마 설계서
version: 0.3-DRAFT
status: PHASE_B2_L01_DOC — GPT 독립검증 대기
date: 2026-10-09
branch: docs/tai-reference-forms-charter-obj-20261008
scope: common-v1 스키마 블록 타입 정의, 가변 결재란 계약, 공통 assembler 계약, C002/C012 매핑 비교, 페이지 방향(orientation) 계약
wo: WO-REF01-059-B2-L01-DOC-001
supersedes: TAI-DESIGN-COMMON-ENGINE-V0.2
change_reason: WO-REF01-059-B2-L01 Landscape 엔진 구현 반영 — document.page.orientation 계약, A4 치수/콘텐츠 너비, DOCX 치수 전달 계약, repeat_table.min_row_height_mm, fail-closed 규칙 추가, 하위 호환성 명시
---

# TAI 서식 공통 렌더러 스키마 설계서 v0.3

## 0. 목적

여러 서식(C002, C012 등)을 단일 렌더러가 처리할 수 있도록 JSON 필드 명세의 구조와 공통 assembler 계약을 정의한다. 이 문서는 **설계 명세**이며, 생성기 구현은 Phase C에서 수행한다.

---

## 1. 스키마 식별자 및 최상위 구조

```
schema_version: "common-v1"
```

모든 서식 필드 명세 JSON의 `_meta.schema_version`에 기재한다.

### 1.1 최상위 구조

```json
{
  "_meta": {
    "schema_version": "common-v1",
    "form_type": "FORM | PLAN | CHECKLIST | ...",
    "source_id": "REF-Cxxx",
    ...
  },
  "document": {
    "title": "...",
    "doc_id": "...",
    "version": "...",
    "subject": "...",
    "creator": "...",
    "producer": "...",
    "page": {                         // optional — 생략 시 portrait 기본값
      "orientation": "landscape"      // "portrait" | "landscape"
    }
  },
  "sections": [ <block>, <block>, ... ]
}
```

렌더러는 다음 순서로 처리한다:
1. `document.title`로 제목 행을 **항상 첫 번째**로 렌더링한다 — `sections` 배열에 `title` 항목 없음.
2. `sections` 배열을 순서대로 처리한다.

---

### 1.2 페이지 방향 계약

#### 1.2.1 orientation 필드

| 속성 | 위치 | 타입 | 기본값 | 허용값 |
|---|---|---|---|---|
| `orientation` | `document.page.orientation` | string | `"portrait"` | `"portrait"`, `"landscape"` |

- `document.page` key 자체가 없으면 portrait 적용 (C002/C012/C003 하위 호환).
- `document.page` key 존재 + `orientation` key 없으면 portrait 적용.
- `document.page.orientation` key 존재 + invalid value (null / empty string / 숫자 등) → **오류 발생 (fail-closed)**.

#### 1.2.2 A4 용지 치수 및 콘텐츠 너비

| 방향 | 용지 | 콘텐츠 너비 | 콘텐츠 높이 |
|---|---|---|---|
| portrait | 210 × 297mm | **170mm** (여백 20mm × 양측) | 257mm |
| landscape | 297 × 210mm | **257mm** (여백 20mm × 양측) | 170mm |

#### 1.2.3 PDF 엔진 처리 (Python — common_v1_engine.py)

- Portrait: `reportlab.lib.pagesizes.A4` (210 × 297mm)
- Landscape: `reportlab.lib.pagesizes.landscape(A4)` (297 × 210mm)
- `_canvas_factory(page_w)` 클로저로 푸터 중앙 좌표를 orientation별로 계산.

#### 1.2.4 DOCX 엔진 처리 (Node.js — common_v1_engine.cjs)

- `layoutCtx()` 반환값: `{ pageW, pageH, contentW, orientation }`
- **치수 전달 계약**: docx 라이브러리에 항상 **표준 A4 세로 치수(210×297mm)**를 전달하고, `PageOrientation.LANDSCAPE`로 방향을 지정한다. 라이브러리가 내부에서 w/h를 교환하여 OOXML에 기록한다.

```
입력 (layoutCtx 반환): pageW=mm(210), pageH=mm(297), orientation=LANDSCAPE
라이브러리 내부 swap →
OOXML 출력: w:w=16837(297mm), w:h=11905(210mm), w:orient=landscape
```

- Portrait: `pageW=mm(210), pageH=mm(297), orientation=PORTRAIT` → OOXML: `w:w=11905, w:h=16837`

#### 1.2.5 하위 호환성

`document.page` 없는 기존 서식(C002/C012/C003)은 portrait으로 자동 처리된다. 기존 출력물에 변화 없음.

---

## 2. C002 레거시 구조와 common-v1의 관계

**현재 상태**: `c002_fields.json`은 flat 구조 (`document / basic_info / approval / corporate_goal / plan_table` 최상위 키)를 사용하며 `sections` 배열이 없다. **이 파일은 변경하지 않는다.**

**공통 스키마 표현 가능 확인**: C002를 common-v1 sections 형식으로 표현하면 아래와 같다. 이는 설계 비교용이며 실제 파일 변경이 아니다.

```json
// C002 if expressed in common-v1 (DESIGN ONLY — c002_fields.json NOT changed)
{
  "_meta": { "schema_version": "common-v1", ... },
  "document": { "title": "안전보건 목표 및 추진계획서", ... },
  "sections": [
    {
      "type": "approval",
      "total_width_mm": 90,
      "fields": [
        {"id": "F01", "label": "작성"},
        {"id": "F02", "label": "검토"},
        {"id": "F03", "label": "승인"}
      ]
    },
    {
      "type": "basic_info",
      "layout": "2col_2row",
      "fields": [
        {"id": "N01", "label": "사업장명"},
        {"id": "N02", "label": "작성일"},
        {"id": "N03", "label": "문서번호"},
        {"id": "N04", "label": "적용 연도"}
      ]
    },
    {
      "type": "freeform_area",
      "id": "F04",
      "label": "전사 목표",
      "min_height_mm": 22
    },
    {
      "type": "repeat_table",
      "default_row_count": 5,
      "columns": [
        {"id": "F05", "label": "목표·세부\n추진계획", "width_mm": 56, "align": "left"},
        {"id": "F06", "label": "추진일정",             "width_mm": 26, "align": "center"},
        {"id": "F07", "label": "성과지표",             "width_mm": 22, "align": "left"},
        {"id": "F08", "label": "담당부서",             "width_mm": 26, "align": "center"},
        {"id": "F09", "label": "예산\n(만원)",         "width_mm": 22, "align": "right"},
        {"id": "F10", "label": "달성률",               "width_mm": 18, "align": "center"}
      ]
    }
  ]
}
```

이로써 C002와 C012 **모두** common-v1 sections 형식으로 표현 가능하다.

---

## 3. 블록 타입 정의

### 3.1 `approval` — 결재란

```json
{
  "type": "approval",
  "total_width_mm": 90,
  "min_header_height_mm": 7,
  "min_sign_height_mm": 15,
  "fields": [
    { "id": "AP01", "label": "신청", "requiredness": "UNVERIFIED" },
    { "id": "AP02", "label": "허가", "requiredness": "UNVERIFIED" }
  ]
}
```

#### 가변 열 너비 계약 (R2-01)

```
cell_width = total_width_mm / len(fields)
```

- C002 (3열): `90mm / 3 = 30mm`
- C012 (2열): `90mm / 2 = 45mm`

**현재 생성기 결함 확인:**

| 생성기 | 결함 위치 | 결함 내용 |
|---|---|---|
| PDF `gen_c002_pdf.py` line 60 | `APPR_CELL_W = APPROVAL_W / 3` | 제수(divisor) 3 하드코딩 |
| PDF line 122–123 | `['', '', '']`, `colWidths=[APPR_CELL_W] * 3` | 3열 행과 너비 하드코딩 |
| DOCX `gen_c002_docx.cjs` line 27 | `Math.round(APPROVAL_W / 3)` | 제수 3 하드코딩 |
| DOCX lines 127–135 | `hdrCell(..., APPR_CELL_W)` | 셀 수는 `apprF.map()`으로 동적이나 너비 30mm 고정 |

**Phase C 구현 계약:**

```python
# PDF — build_approval(section)
appr = section['fields']
n = len(appr)
cell_w = section['total_width_mm'] * mm / n
inner = Table(
    [[P(f['label'], S_HDR) for f in appr],
     ['' for _ in appr]],           # dynamic: not hardcoded 3
    colWidths=[cell_w] * n,         # dynamic: not hardcoded 3
    rowHeights=[section.get('min_header_height_mm', 7)*mm,
                section.get('min_sign_height_mm', 15)*mm],
)
```

```js
// DOCX — buildApproval(section)
const apprF = section.fields;
const cellW = Math.round(mm(section.total_width_mm) / apprF.length);  // dynamic
// rows already use apprF.map() — keep as-is, pass cellW per iteration
```

**requiredness 보존 규칙**: `requiredness=UNVERIFIED` 필드는 렌더링을 건너뛰지 않는다. 모든 필드는 requiredness 값과 무관하게 렌더링된다.

**현재 구현 상태**: C002 생성기에서 `fields.approval.fields`를 읽어 `f.label`을 사용하므로 레이블은 JSON 기반 ✓. 단, 열 너비 하드코딩 수정 필요 (Phase C).

---

### 3.2 `basic_info` — 기본 정보 행

```json
{
  "type": "basic_info",
  "layout": "2col_2row",
  "fields": [
    { "id": "N01", "label": "사업장명",   "requiredness": "UNVERIFIED" },
    { "id": "N02", "label": "작성일",     "requiredness": "UNVERIFIED" },
    { "id": "N03", "label": "문서번호",   "requiredness": "UNVERIFIED" },
    { "id": "N04", "label": "적용 연도",  "requiredness": "UNVERIFIED" }
  ]
}
```

- `layout` 값: `"2col_2row"` (기본) — N열 2행 배치.
- `fields` 순서: 좌상→우상→좌하→우하.
- C012 기본 서식에는 없음 (D05 결정: 신규 제안 필드 제외).

**현재 구현 상태**: C002 전용 `buildBasicInfo(fields)` / `build_basic_info(fields)` 존재. `fields.basic_info.fields` 배열을 소비하나 ID (N01/N02/N03/N04)를 하드코딩. **GAP-04: 파라미터화 필요 (Phase C 이후).**

---

### 3.3 `labeled_grid` — 2열 그리드 기본정보

```json
{
  "type": "labeled_grid",
  "section_label": "작업 기본 정보",
  "row_height_mm": 7,
  "rows": [
    [
      { "id": "F01", "label": "작업종류", "requiredness": "UNVERIFIED" },
      { "id": "F02", "label": "신청부서(업체명)", "requiredness": "UNVERIFIED" }
    ]
  ]
}
```

- `rows`: 행 배열. 각 행은 정확히 2개 셀.
- `section_label` 존재 시 전체너비 헤더 행 선행.
- 열 너비: `CONTENT_W / 2 = 85mm`.

**현재 구현 상태**: **없음** — **GAP-01 신규 빌더 필요.**

---

### 3.4 `freeform_area` — 전체너비 자유 기재란

```json
{
  "type": "freeform_area",
  "id": "F09",
  "label": "작업내용",
  "min_height_mm": 20,
  "requiredness": "UNVERIFIED"
}
```

- 전체 너비 170mm, 라벨 헤더 행(7mm) + 기재 공간 행(`min_height_mm`).
- `id` 및 `requiredness`: 렌더링에 영향 없는 메타데이터. `requiredness=UNVERIFIED`여도 렌더링.

**현재 구현 상태**: C002 `build_corporate_goal()` / `buildCorporateGoal()` 패턴 동일하나 "전사목표" 하드코딩. **GAP-02: 파라미터화 필요.**

---

### 3.5 `repeat_table` — 반복 테이블

```json
{
  "type": "repeat_table",
  "default_row_count": 5,
  "min_row_height_mm": 10,
  "extra_rows_note": "※ 행이 부족할 경우 추가하십시오.",
  "columns": [
    { "id": "F05", "label": "목표·세부\n추진계획", "width_mm": 56, "align": "left" },
    { "id": "F06", "label": "추진일정",             "width_mm": 26, "align": "center" }
  ]
}
```

- `columns[].width_mm`으로 열 너비 지정 (JSON 기반). `COL_WIDTHS` 상수 의존 금지.
- C002 `columns`에 이미 `width_mm` 존재 (c002_fields.json line 39–45) ✓.
- 단, `gen_c002_pdf.py`의 `COL_WIDTHS = [56,26,22,26,22,18]` 상수는 아직 `columns[].width_mm`을 읽지 않음. **GAP-08: Phase C 이후 연동.**

#### `min_row_height_mm` 선택 속성

| 속성 | 타입 | 기본값 | 허용 범위 |
|---|---|---|---|
| `min_row_height_mm` | number | **14** | 양수(> 0) |

- 생략 시 기본값 14mm 적용. 음수·0 → 오류 발생 (fail-closed).
- 용도: landscape 서식에서 행 수 × 행 높이가 content_h(170mm)를 초과하지 않도록 조정.
  - 예) REF-C014: 10행 × 10mm = 100mm + 제목/헤더 ~28mm ≈ 128mm < 170mm → 1페이지.
- 기존 서식(C002/C003): 미기재 → 14mm 적용, 기존 출력 불변.

---

## 4. 공통 assembler 계약 (MANDATORY)

서식별 별도 조립 함수 작성은 금지한다. C012 생성기는 반드시 아래 공통 assembler를 사용한다.

### 4.1 assembler 계약

```python
# PDF (gen_c012_pdf.py — Phase C 구현)
def assemble(fields, ex_rows=None):
    """
    Returns list of ReportLab flowables.
    Title is always first (from document.title).
    Sections are processed in array order.
    Unknown block type → ValueError (fail-closed).
    """
    story = []
    story.append(build_title(fields))        # always first — not in sections
    story.append(Spacer(1, 1*mm))

    for section in fields.get('sections', []):
        t = section['type']
        if   t == 'approval':      story.append(build_approval(section))
        elif t == 'basic_info':    story.append(build_basic_info(section))
        elif t == 'labeled_grid':  story.append(build_labeled_grid(section))
        elif t == 'freeform_area': story.append(build_freeform_area(section))
        elif t == 'repeat_table':  story += build_repeat_table(section, ex_rows)
        else:
            raise ValueError(f"Unsupported block type: {t!r}")  # fail-closed
        story.append(Spacer(1, 1*mm))

    return story
```

```js
// DOCX (gen_c012_docx.cjs — Phase C 구현)
function assemble(fields, exRows) {
  const children = [buildTitle(fields), spacer0()];

  for (const section of (fields.sections ?? [])) {
    switch (section.type) {
      case 'approval':      children.push(buildApproval(section));         break;
      case 'basic_info':    children.push(buildBasicInfo(section));         break;
      case 'labeled_grid':  children.push(buildLabeledGrid(section));       break;
      case 'freeform_area': children.push(buildFreeformArea(section));      break;
      case 'repeat_table':  children.push(...buildRepeatTable(section, exRows)); break;
      default:
        throw new Error(`Unsupported block type: ${section.type}`); // fail-closed
    }
    children.push(spacer());
  }
  return children;
}
```

### 4.2 fail-closed 규칙

- 알 수 없는 `type` 값 → 오류 발생 (silent skip 금지)
- 블록 필수 속성 누락 → 오류 발생
- `requiredness=UNVERIFIED` → 렌더링 스킵 금지 (모든 필드 렌더링)
- `document.page.orientation` key 존재 + invalid value (null / empty string / 숫자) → 오류 발생
- `document.page.orientation` key 부재 → `"portrait"` 기본값 (오류 아님)
- `repeat_table.min_row_height_mm` 존재 + 음수 또는 0 → 오류 발생

### 4.3 블록 타입별 필수 속성

| 블록 타입 | 필수 속성 |
|---|---|
| `approval` | `type`, `total_width_mm`, `fields` (길이 ≥ 1) |
| `basic_info` | `type`, `fields` (길이 ≥ 1) |
| `labeled_grid` | `type`, `rows` (각 행 길이 = 2) |
| `freeform_area` | `type`, `label`, `min_height_mm` |
| `repeat_table` | `type`, `columns` (길이 ≥ 1), `default_row_count` |

---

## 5. C002 vs C012 공통 스키마 매핑표

| 섹션 순서 | C002 (common-v1 표현) | C012 (실제 c012_fields.json) |
|---|---|---|
| 제목 | `document.title` → build_title (sections 외부) | `document.title` → build_title (sections 외부) |
| 1 | `approval` — 작성/검토/승인 (3역할, 30mm/셀) | `approval` — 신청/허가 (2역할, 45mm/셀) |
| 2 | `basic_info` — N01~N04 2col×2row | (없음) |
| 3 | `freeform_area` — 전사목표 22mm | `labeled_grid` — F01~F08 4행 |
| 4 | `repeat_table` — 6열 계획표 | `freeform_area` — 작업내용 F09 20mm |
| 5 | (없음) | `freeform_area` — 안전조치사항 F10 30mm |

**결론**: 두 서식 모두 `approval`, `freeform_area` 블록을 공통으로 사용. 열 수·너비는 JSON 기반으로 결정. assembler 로직은 단일 코드로 처리 가능.

---

## 6. GAP 목록 (v0.2 최종)

| GAP ID | 분류 | 설명 | C012 Phase C 필수 여부 |
|---|---|---|---|
| GAP-01 | 신규 빌더 | `labeled_grid` 빌더 (PDF + DOCX) | **REQUIRED** |
| GAP-02 | 파라미터화 | `freeform_area` — `build_corporate_goal` 파라미터화 | **REQUIRED** |
| GAP-03 | — | NONE — approval 이미 JSON-driven (레이블). 단 열 너비 계산 수정 필요 | **REQUIRED (열 너비 한정)** |
| GAP-04 | 파라미터화 | `basic_info` 파라미터화 | NOT REQUIRED (C012 기본 서식에 없음) |
| GAP-05 | 아키텍처 | 공통 assembler — Phase C에서 **MANDATORY** | **REQUIRED** |
| GAP-06 | 인프라 | `package.json` scripts 다중 서식 지원 | **REQUIRED** |
| GAP-07 | 인프라 | Python entry point 다중 서식 지원 | **REQUIRED** |
| GAP-08 | 파라미터화 | `repeat_table` 열 너비 `columns[].width_mm` 연동 | NOT REQUIRED (C012에 repeat_table 없음) |

**v0.1 변경**: GAP-03을 "NONE"에서 "REQUIRED (열 너비 한정)"으로 격상. GAP-05를 "NICE_TO_HAVE"에서 "REQUIRED (MANDATORY)"로 격상.

---

## 7. 제약 사항

- 이 문서는 설계 명세이며 구현 코드가 아님
- `c002_fields.json` 변경 금지 (C002 기존 생성기 호환성 유지)
- C002 기존 생성기(`gen_c002_pdf.py`, `gen_c002_docx.cjs`) 변경 금지
- Phase C 구현 시 C012 생성기는 반드시 공통 assembler를 사용
- Phase C 착수 조건: GAP-01/02/03(열너비)/05/06/07 해소 + GPT 독립검증 PASS
