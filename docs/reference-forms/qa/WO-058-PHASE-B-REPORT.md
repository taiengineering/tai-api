# WO-058 Phase B — 설계 산출물 + 공통 엔진 Gap 분석 보고서

Date: 2026-10-09
Goal: G-muzv7o29-b4a5ab
Branch: docs/tai-reference-forms-charter-obj-20261008
Head: WO-058 Phase B commit (이 파일 포함)
Status: PHASE_B_COMPLETE — GPT 독립검증 대기

---

## 1. 189건 서식 분류 현황

출처: `evidence/REF01-DOCUMENT-TYPE-CLASSIFICATION-PROPOSAL-051.md` (WO-051 EVIDENCE_READY)

### 1.1 유형별 분포

| 유형 | 건수 | % | 비고 |
|---|---|---|---|
| CHECKLIST | 47 | 24.9% | 점검표/체크리스트류 |
| REGISTER | 34 | 18.0% | 대장/목록류 |
| RECORD | 33 | 17.5% | 기록/일지류 |
| **FORM** | **27** | **14.3%** | **허가서/신청서류 — REF-C012 포함** |
| EVALUATION | 14 | 7.4% | 평가표류 |
| PLAN | 13 | 6.9% | 계획서류 — REF-C002 포함 |
| REPORT | 10 | 5.3% | 보고서류 |
| REFERENCE | 10 | 5.3% | 절차서/규정류 |
| WORKFLOW_DIAGRAM | 1 | 0.5% | REF-C010 흐름도 |
| **TOTAL** | **189** | 100% | UNDETERMINED=0 |

### 1.2 구현 준비도 (OBJ-REF-01-IMPLEMENTATION-READY-DEFINITION-38.md 기준)

| 게이트 | 현황 |
|---|---|
| artifact_type DB 등록 | 0/189 (전부 NULL) |
| SOURCE_STRUCTURE_VERIFIED | 15행 (REF-C001~C005, C007~C009, C011~C016) |
| SOURCE_TEXT_PARTIAL | 1행 (REF-C006) |
| RESEARCH_REPORT_ONLY | 173행 |
| FIELD_SPEC_COMPLETE (게이트 4) | REF-C002: 완료 / REF-C012: Phase B 진행 중 / 나머지 187건: 미착수 |
| LEG_RIGHTS_CLEARED (게이트 3) | 0건 |
| BUILD_SPEC_READY (게이트 7) | 0건 |
| OWNER_APPROVED_TO_IMPLEMENT | 0건 |

**요약**: 189건 중 구현 착수 가능 수준(게이트 4 이상)은 REF-C002(ACCEPTED_FOR_NEXT_DESIGN_POC_WITH_LIMITATIONS) 1건뿐. REF-C012는 Phase B에서 게이트 4에 진입 중. 나머지 187건은 게이트 1(DISCOVERED) 수준.

---

## 2. 공통 생성 엔진 현황

현재 스크립트 상태:
- `gen_c002_pdf.py` — 425행, 13개 함수/클래스
- `gen_c002_docx.cjs` — 347행, 13개 함수
- 공통 엔진 모듈: **미존재** (per-form 단일 파일)
- `package.json`: c002 스크립트만 등록

### 2.1 기존 코드 재사용 분류

#### PDF (gen_c002_pdf.py) — 형태별 분류

| 구분 | 항목 | C012 재사용 가능 |
|---|---|---|
| **범용** | `register_fonts()` | YES — 그대로 |
| **범용** | `NumberedCanvas` | YES — 그대로 |
| **범용** | 색상 상수 (C_BLACK, C_HEADER_BG, C_ALT_BG, C_GRAY_TEXT) | YES |
| **범용** | `ROW_H_INFO=7mm`, `ROW_H_SIGN=15mm` | YES |
| **범용** | `mk_style()`, `P()` | YES |
| **범용** | `_BASE`, `ts()` | YES |
| **범용** | `build_title(fields)` | YES — title 키 구조 동일 |
| **범용** | `build_approval(fields)` | YES — 레이블만 교체 (신청/검토/허가) |
| **범용** | `SimpleDocTemplate` A4/20mm 설정 | YES |
| **범용** | `generate()` 뼈대 (JSON 로드 → build → doc.build) | YES — 구조 동일 |
| C002 전용 | `build_basic_info()` — N01/N02/N03/N04 2행 레이아웃 | NO — 구조 다름 |
| C002 전용 | `build_corporate_goal()` — 단일 셀 전사목표 | **PARTIAL** — C012 작업내용/안전조치에 유사 패턴 |
| C002 전용 | `build_plan_table()` + `_orphan_safe_plan_tables()` | NO |
| C002 전용 | `COL_WIDTHS = [56,26,22,26,22,18]` | NO |
| C002 전용 | `ROW_H_PLAN=14mm`, `ROW_H_GOAL=20mm` | PARTIAL (ROW_H_GOAL → F09/F10 min height) |

#### DOCX (gen_c002_docx.cjs) — 형태별 분류

| 구분 | 항목 | C012 재사용 가능 |
|---|---|---|
| **범용** | `border()`, `noBorder()`, `shading()` | YES |
| **범용** | `hdrCell()`, `bodyCell()`, `emptyCell()` | YES |
| **범용** | `buildTitle(fields)` | YES |
| **범용** | `buildApproval(fields)` Candidate B | YES — 레이블만 교체 |
| **범용** | `spacer0()`, `spacer()`, `buildFooter()` | YES |
| **범용** | `CONTENT_W=170mm`, `APPROVAL_W=90mm`, `ROW_H_SIGN=15mm`, `ROW_H_INFO=7mm` | YES |
| **범용** | `Document` + `sections` A4/20mm 설정 | YES |
| C002 전용 | `buildBasicInfo()` — N01-N04 2열 레이아웃 | NO — 필드 다름 |
| C002 전용 | `buildCorporateGoal()` — 단일 전체너비 셀 | **PARTIAL** — C012 F09/F10에 유사 |
| C002 전용 | `buildPlanTable()` — 6열 계획 테이블 | NO |
| C002 전용 | `COL_W = [56, 26, 22, 26, 22, 18].map(mm)` | NO |
| C002 전용 | `buildDoc()` assembler | NO — 섹션 구성 다름 |

**범용 코드 비율**: PDF ≈ 57% (7/12 함수 전체 재사용), DOCX ≈ 58% (6/10 함수 전체 재사용)

---

## 3. 공통 엔진 Gap 분석

### 3.1 GAP 목록

| GAP ID | 분류 | 설명 | 영향 형식 | 우선순위 |
|---|---|---|---|---|
| GAP-01 | **신규 빌더** | `grid_2col` 레이아웃 빌더 — 2열 그리드 정보 섹션 | PDF + DOCX | REQUIRED (C012) |
| GAP-02 | **신규 빌더** | `freeform_area` 레이아웃 빌더 — 전체너비 자유 기재란 (라벨+공간) | PDF + DOCX | REQUIRED (C012) |
| GAP-03 | **공통화** | `build_approval()` 레이블 파라미터화 — 현재 "작성/검토/승인" 하드코딩 | PDF + DOCX | REQUIRED (C012) |
| GAP-04 | **공통화** | `build_basic_info()` 필드 수/레이아웃 파라미터화 — 현재 C002 N01-N04 하드코딩 | PDF + DOCX | REQUIRED (C012) |
| GAP-05 | **공통화** | `buildDoc()` / `generate()` — form-specific 섹션 조립을 JSON-driven으로 교체 | PDF + DOCX | NICE_TO_HAVE (C 단계) |
| GAP-06 | **인프라** | `package.json` scripts — c002 전용 → 다중 서식 지원 | Node.js | REQUIRED (C012) |
| GAP-07 | **인프라** | Python entry point — c002 전용 인자 → 다중 서식 지원 | Python | REQUIRED (C012) |

### 3.2 GAP 상세

#### GAP-01: grid_2col 레이아웃 빌더

**없는 이유**: REF-C002에 2열 그리드 정보 섹션이 없음 (C002는 단순 2열 basic_info만 있음).

**필요한 이유**: REF-C012 F01~F08 8개 필드를 2열 그리드로 배치. 각 셀에 라벨(Bold) + 기재란(하단 밑줄 배경) 구조.

**예상 인터페이스 (PDF)**:
```python
def build_grid_section(section_label, rows, col_half_w=CONTENT_W/2, row_h=ROW_H_INFO):
    """rows: [[{id, label}, {id, label}], ...]"""
```

**예상 인터페이스 (DOCX)**:
```js
function buildGridSection(sectionLabel, rows, colHalfW = mm(85), rowH = ROW_H_INFO)
```

#### GAP-02: freeform_area 빌더

**없는 이유**: REF-C002의 `build_corporate_goal()`은 "전사 목표" 전용 하드코딩.

**필요한 이유**: REF-C012 F09(작업내용), F10(안전조치 사항) — 같은 패턴 2번 사용.

**해결**: `build_corporate_goal()` → `build_freeform_area(label, min_height_mm)` 파라미터화.

**예상 인터페이스 (PDF)**:
```python
def build_freeform_area(label, min_height_mm=20):
    """라벨 헤더 행 + 빈 기재 공간 행"""
```

**예상 인터페이스 (DOCX)**:
```js
function buildFreeformArea(label, minHeightMm = 20)
```

#### GAP-03: build_approval() 레이블 파라미터화

**현재 상태**: PDF `build_approval()` 내부에서 `f['label']` 를 fields JSON에서 읽음 → **이미 파라미터화됨**.

**C012 적용**: c012_fields.json에 `"label": "신청"/"검토"/"허가"` 기재 → 기존 `build_approval()` 그대로 동작.

**GAP 수준**: **NONE** — 코드 수정 불필요. JSON만 변경으로 해결.

#### GAP-04: build_basic_info() 파라미터화

**현재 상태**: PDF `build_basic_info()` 내부에서 N01/N02/N03/N04를 하드코딩으로 배열.

**C012 필요**: N01(허가번호)/N02(작성일) 2개 필드만, 단일 행.

**해결**: `build_basic_info()` → `basic_info.fields` + `basic_info.layout` 키를 소비하도록 일반화.
또는: C012 전용 `build_basic_info()` 함수를 신규 작성 (공통화는 Phase C 이후).

**GAP 수준**: **MEDIUM** — 공통화하면 좋지만 C012 전용 함수로도 단기 해결 가능.

#### GAP-05: 조립 함수 JSON-driven화

**현재**: `buildDoc()` / `generate()` 내부에서 섹션 순서 하드코딩.

**필요**: 각 서식이 자신의 섹션 목록을 JSON으로 선언 → 공통 assembler가 처리.

**GAP 수준**: **NICE_TO_HAVE** — 5형식 이상으로 확장 시 중요. Phase C에서 함께 설계.

---

## 4. REF-C012 Phase C 구현을 위한 최소 변경 목록

Phase C (개별 생성기 작성 단계) 착수 전 필요한 공통 엔진 수정:

| 항목 | 파일 | 변경 유형 |
|---|---|---|
| `build_freeform_area()` 추출 | `gen_c002_pdf.py` + 향후 공통 모듈 | `build_corporate_goal()` 파라미터화 |
| `buildFreeformArea()` 추출 | `gen_c002_docx.cjs` + 향후 공통 모듈 | `buildCorporateGoal()` 파라미터화 |
| `grid_2col` 빌더 신규 작성 | 신규 함수 | PDF + DOCX 각각 |
| `package.json` scripts 확장 | `package.json` | gen-c012 scripts 추가 |

**Phase C 착수 조건**: 이 보고서 GPT 독립검증 PASS + 위 최소 변경 목록 승인.

---

## 5. Phase B 산출물 목록

| 파일 | 유형 | 상태 |
|---|---|---|
| `design/REF-C012-FIELD-SPEC-058.md` | 설계 명세서 | **신규** |
| `scripts/c012_fields.json` | 필드 명세 JSON | **신규** |
| `qa/WO-058-PHASE-B-REPORT.md` | 이 보고서 | **신규** |

**변경 없음**: 기존 생성기 (gen_c002_pdf.py, gen_c002_docx.cjs), c002_fields.json, 설계 명세서 v0.2.

---

## 6. GPT 독립검증 요청 항목

| # | 검증 항목 |
|---|---|
| V01 | c012_fields.json 섹션 구조가 REF-C012 FORM 유형에 적합한가? |
| V02 | 결재란 레이블 "신청/검토/허가"가 OF-04(성명/서명)→신청, OF-11(허가자 성명)→허가 매핑에 적합한가? |
| V03 | 작업기본정보 8개 필드(F01~F08)의 2열 그리드 배치가 적절한가? |
| V04 | 작업내용(F09) 20mm / 안전조치 사항(F10) 30mm 최소 높이가 적절한가? |
| V05 | GAP-01(grid_2col), GAP-02(freeform_area), GAP-04(basic_info) — Phase C 착수 전 최소 수정 목록이 완전한가? |
| V06 | GAP-03이 "NONE" (JSON 변경만으로 해결)이라는 판단이 정확한가? |
| V07 | 3개 블로커(SOURCE_FIELDS_UNVERIFIED/LEGAL_REVIEW_PENDING/RIGHTS_UNVERIFIED) 해소 없이 Phase C (POC 생성기) 착수 가능한가? |
