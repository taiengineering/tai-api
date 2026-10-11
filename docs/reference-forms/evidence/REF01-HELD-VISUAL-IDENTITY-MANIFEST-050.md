# REF-01 Held Visual Identity Manifest — WO-050
Date: 2026-10-08
WO: WO-REF01-HELD-SOURCE-VISUAL-IDENTITY-050
Investigator: Claude Code (evidence/inspection only — no DB writes authorized)
Basis: WO-049 CLOSED FINAL. REF-C006/C010 on HOLD from WO-049. REF-C008 typo deferred.

---

## S0 PREFLIGHT

### Source file hashes (verified)

| File | Path | SHA256 | Status |
|---|---|---|---|
| 2022 MOEL HWP | Downloads/활용 서식 모음_'중대재해처벌법 따라하기' 안내서.hwp | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe | VERIFIED ✓ |
| 2023 HWPX | Downloads/(서식) 2023 새로운 위험성평가 안내서 수록 각종 서식.hwpx | c624ea2e72c4e79b8daa011375d2105f3f917e069b47dfd95c9850b193d21d46 | VERIFIED ✓ |
| MOEL guide PDF | Downloads/최종_경영책임자와 관리자가 알아야 할 중대재해처벌법 따라하기 안내서.pdf | a73ce4c67dfcb4a1b27f647ad346496f1bc7421666653da516c9ca92a46c60ff | VERIFIED ✓ |

### Git state

| Item | Value |
|---|---|
| Branch | docs/tai-reference-forms-charter-obj-20261008 |
| Branch HEAD | 69688f33 |
| WO file | docs/reference-forms/WO-REF01-HELD-SOURCE-VISUAL-IDENTITY-050.md |

### Parser/viewer versions

| Tool | Version | Use |
|---|---|---|
| olefile | 0.47 | HWP5 OLE compound document reader |
| zlib (Python stdlib) | — | BinData raw-deflate decompression |
| Pillow (PIL) | installed | TIF→PNG conversion for visual reading |
| pdfplumber | installed | PDF text extraction |
| Claude multimodal vision | — | Visual reading of flowchart diagram |

### HWP OLE BinData streams

| Stream | Compressed bytes | Decompressed bytes | Format | Image size |
|---|---|---|---|---|
| BinData/BIN0001.tif | 747,636 | 21,961,460 | TIF LE (49492a00) | 2520×2750px @400dpi |
| BinData/BIN0002.tif | 11,518 | 66,532 | TIF LE | 96×123px @400dpi |
| BinData/BIN0003.tif | 5,489 | 33,644 | TIF LE | 58×59px @400dpi |

BIN0002 = cursor/click icon (UI decoration). BIN0003 = circle bullet icon (UI decoration). Neither contains flowchart content.

BinData compression: FileHeader property bitmask 0x00000001 (bit0=compressed). All BinData streams use raw deflate (zlib wbits=-15). BIN0001 is the sole HWP-10a diagram source.

### SoT preflight (live SQL — WO-050 S0)

```sql
SELECT COUNT(*) AS total_rows,
  COUNT(*) FILTER (WHERE jsonb_array_length(COALESCE(observed_fields,'[]'::jsonb)) > 0) AS observed_nonempty,
  c006_fields, c006_checksum, c010_fields, c010_checksum
```

| Item | Value |
|---|---|
| total_rows | 189 ✓ |
| observed_nonempty | 14 ✓ |
| REF-C006 field_count | 0 (HOLD) |
| REF-C006 checksum | NULL (HOLD) |
| REF-C010 field_count | 0 (HOLD) |
| REF-C010 checksum | NULL (HOLD) |

DB mutations this WO: 0. Prohibition confirmed.

---

## S1 REF-C010 VISUAL EXTRACTION

### S1-A HWP-10a — 협착사고 발생 시 대응 시나리오(처리 흐름도)

Source: HWP BodyText/Section0 para 1462–1463
- Para 1462: heading `협착사고 발생 시 대응 시나리오(처리 흐름도)`
- Para 1463: embedded image control → BinData/BIN0001.tif

PDF cross-check: physical p106 (0-indexed 105). PDF text extraction = only heading text + page number 105. Confirms image-only — no extractable text body.

Image read method: TIF decompressed from OLE raw deflate → PIL PNG conversion (2000px wide) → Claude multimodal visual reading. No OCR applied (diagram was visually readable).

#### Diagram nodes extracted (literal visual reading of BIN0001)

| # | Node text | Type | Actor(s) in parentheses | Arrow/trigger |
|---|---|---|---|---|
| N01 | 협착사고 발생 | EVENT_START | — | — (top of flow) |
| N02 | 비상 정지 | ACTION | 목격자 | ↓ from N01 |
| N03 | 119 신고 산업안전팀 | ACTION | 목격자/현장관리자 | 즉시 ← from N02 (left branch) |
| N04 | 보전팀 호출 | ACTION | 목격자/현장관리자 | 즉시 ← from N02 (left branch) |
| N05 | 의식, 상태 확인 | ACTION | 목격자/현장관리자 | ↓ from N02 |
| N06 | 대표이사 보고 | ACTION | 현장관리자 | 즉시 → from N05 (right branch) |
| N07 | 지원 및 응급처치 | ACTION | 목격자/현장관리자 | ↓ from N05 (N04 feeds in from left) |
| N08 | 주변 안전확보 | ACTION | 현장관리자 | ↓ from N07 |
| N09 | 병원 후송 | ACTION | 현장관리자 | ↓ from N08 |
| N10 | 사고자 상황 파악 | ACTION | 안전보건담당자 | → from N09 (right branch) |
| N11 | 관계기관 신고 | ACTION | 안전보건담당자 | → from N10 |
| N12 | 고용노동부 | EXTERNAL_REFERENCE | — | → from N11 (label above) |
| N13 | 안전보건공단 | EXTERNAL_REFERENCE | — | → from N11 (label below) |
| N14 | 현장사진 촬영 | ACTION | 현장관리자 | ↓ from N09 |
| N15 | 사고조사 | ACTION | 현장관리자/목격자/안전보건담당자 | → from N14 (right branch) |
| N16 | 원인분석 및 재발방지대책 수립 | ACTION | 사고조사 TFT | → from N15 |
| N17 | 대표이사 (stakeholder) | STAKEHOLDER | — | → from N16 (right label) |
| N18 | 근로자대표 | STAKEHOLDER | — | → from N16 (right label) |
| N19 | 현장관리자 (stakeholder) | STAKEHOLDER | — | → from N16 (right label) |
| N20 | 안전보건담당자 (stakeholder) | STAKEHOLDER | — | → from N16 (right label) |
| N21 | 현장 재가동 | ACTION | 현장관리자/보전팀 | ↓ from N14 |
| N22 | 위험성평가 반영 | ACTION | 현장관리자 | → from N21 (right/bottom branch) |
| N23 | 근로자 교육 | ACTION | 현장관리자 | ↓ from N22; annotation: 수시/정기교육 |
| N24 | 현장 안전보건활동 | ACTION | 현장관리자 | ↓ from N23 |

Arrow timing annotations observed: N02→N03 = 즉시, N02→N04 = 즉시, N05→N06 = 즉시.

Total nodes extracted: 24 (8 main flow + 16 branches/references).

#### Form classification

**WORKFLOW_DIAGRAM — NOT a blank data-entry form.**

Evidence: No blank boxes, no underlined input fields, no empty cells for user data entry are present in the image. All boxes contain pre-printed process step text and pre-assigned actor labels in parentheses. The actor parenthetical labels (목격자, 현장관리자, etc.) are responsibility assignments within a fixed process, not fillable fields. This document serves as a reference response procedure, not a form template.

Implication for observed_fields: No FORM_INPUT_FIELD type nodes exist in HWP-10a. Observed_fields cannot be populated with form input fields from this image source.

#### Relationship between SoT title and HWP-10a

SoT: `사고 발생 대응 시나리오(처리 흐름도)`
HWP-10a: `협착사고 발생 시 대응 시나리오(처리 흐름도)`

Relationship: **VARIANT** — same document type ("대응 시나리오(처리 흐름도)"), accident-type specific (협착사고 = crush). SoT title is the generic category name. Cannot confirm IDENTICAL without separate generic template. Identity determination: GPT.

---

### S1-B HWP-10b — 추락사고 대응 시나리오 작성 예시

Source: HWP BodyText/Section0 para 1464–1541
PDF cross-check: physical p107 (0-indexed 106)

#### Column headers (table structure)

| Label | Label type | Para ref |
|---|---|---|
| 시간 및 상황 | COLUMN_HEADER | 1466 |
| 조치사항 | COLUMN_HEADER | 1467 |
| 담 당 | COLUMN_HEADER | 1468 |
| 비 고 | COLUMN_HEADER | 1469 |

#### Row labels (time-sequence rows)

| Label | Label type | Para ref | PDF text confirmed |
|---|---|---|---|
| 00:00~00:01 추락사고 발생/환자 발생 | ROW_LABEL | 1470–1472 | ✓ p107 |
| 00:01~00:06 환자 구조 | ROW_LABEL | 1483–1496 | ✓ p107 |
| 00:01~00:06 119 구조대 신고 | ROW_LABEL | 1497–1510 | ✓ p107 |
| 00:01~00:06 환자 응급조치 | ROW_LABEL | 1511–1523 | ✓ p107 |
| 00:06~00:10 상황 보고 | ROW_LABEL | 1524–1530 | ✓ p107 |
| 00:06~00:10 현장 보존 | ROW_LABEL | 1531–1535 | ✓ p107 |
| 00:10~ 환자 병원 후송 | ROW_LABEL | 1536–1539 | ✓ p107 |

Form classification: TABLE_TEMPLATE — scenario writing guide with column structure. Contains blank "담 당" and "비 고" columns for user-fill. PDF extracted content shows only the leftmost example text columns; 담 당 and 비 고 columns appear empty (no pre-filled values visible in PDF extraction).

Relationship to SoT: **RELATED** — same accident response domain; "작성 예시" explicitly marks it as a writing guide/template. Not the same document as the SoT generic title "사고 발생 대응 시나리오(처리 흐름도)".

---

### S1-C HWP-10c — 질식, 감전재해 대응 시나리오 작성 예시

Source: HWP BodyText/Section0 para 1542–1596
PDF cross-check: physical p108 (0-indexed 107)

#### Column headers (same structure as HWP-10b)

| Label | Label type | Para ref |
|---|---|---|
| 시간 및 상황 | COLUMN_HEADER | 1544 |
| 조치사항 | COLUMN_HEADER | 1545 |
| 담 당 | COLUMN_HEADER | 1546 |
| 비 고 | COLUMN_HEADER | 1547 |

#### Row labels (time-sequence rows)

| Label | Label type | Para ref | PDF text confirmed |
|---|---|---|---|
| 00:00~00:01 질식/감전 사고 발생/환자 발생 | ROW_LABEL | 1548–1555 | ✓ p108 |
| 00:01~00:06 환자 구조 | ROW_LABEL | 1556–1561 | ✓ p108 |
| 00:01~00:06 119 구조대 신고 | ROW_LABEL | 1562–1565 | ✓ p108 |
| 00:01~00:06 환자 응급조치 | ROW_LABEL | 1566–1568 | ✓ p108 |
| 00:01~00:06 2차 재해방지 조치 | ROW_LABEL | 1569–1572 | ✓ p108 |
| 00:06~00:10 상황보고 | ROW_LABEL | 1573–1578 | ✓ p108 |
| 00:06~00:10 현장 보존 | ROW_LABEL | 1579–1582 | ✓ p108 |
| 00:10~ 환자 병원 후송 | ROW_LABEL | 1583–1585 | ✓ p108 |

Note: HWP-10c covers two accident types in one table (질식 = asphyxiation, 감전 = electrical shock). SoT research_id for HWP-10c: UNRESOLVED (no confirmed match in 189 rows). HWP-10c is NOT merged into REF-C010 per WO-049/050 prohibition.

Form classification: TABLE_TEMPLATE — same as HWP-10b (writing guide with blank columns).

Relationship to SoT: **RELATED** — same domain; explicitly a 작성 예시. Distinct accident types from HWP-10a and HWP-10b.

---

### S1-D Summary — REF-C010 three-source relationship

| Source | HWP section | PDF page | Document type | Relationship to SoT | Form input fields |
|---|---|---|---|---|---|
| HWP-10a | Para 1462–1463 | p106 | WORKFLOW_DIAGRAM (image) | VARIANT (crush-specific flowchart) | NONE |
| HWP-10b | Para 1464–1541 | p107 | TABLE_TEMPLATE | RELATED (fall scenario template) | 담 당, 비 고 (blank columns) |
| HWP-10c | Para 1542–1596 | p108 | TABLE_TEMPLATE | RELATED (asphyxiation/electrical template) | 담 당, 비 고 (blank columns) |

These three are NOT merged. Canonical identity determination reserved for GPT.

Current SoT observed_fields for REF-C010: [] (empty, HOLD maintained). No writes performed.

---

## S2 REF-C006 SOURCE IDENTITY COMPARISON

### Source evidence

HWP-06 heading: `KRAS 시스템 위험성평가표 작성 예시`
HWP-06 paragraphs: 1026–1232
PDF cross-check: physical p93 (0-indexed 92). PDF p93 extracted text confirms heading `KRAS 시스템 위험성평가표 작성 예시 (http://kras.kosha.or.kr)`.

SoT research_id: REF-C006
SoT source_title: `위험성평가표(빈도강도법)`

### Field structure comparison

HWP-06 columns extracted from para range (per WO-048 erratum and PDF p93 cross-check):

| Field | Type | Method relevance |
|---|---|---|
| 담당 / 부장 / 대표 | APPROVAL_COLUMN | — (approval box) |
| 작업공정명 | INPUT_LABEL | — (process identifier) |
| 평가일시 | INPUT_LABEL | — (date) |
| 세부작업내용 | COLUMN_HEADER | — (work description) |
| 유해·위험요인 파악 | COLUMN_HEADER | — (hazard identification) |
| 관련근거(법적기준) | COLUMN_HEADER | — (legal basis) |
| 현재의 안전보건조치 | COLUMN_HEADER | — (existing controls) |
| 위험분류 | COLUMN_HEADER | — (risk classification) |
| 위험발생 상황 및 결과 | COLUMN_HEADER | — (risk scenario) |
| **가능성(빈도)** | COLUMN_HEADER | **빈도강도법: frequency axis** |
| **중대성(강도)** | COLUMN_HEADER | **빈도강도법: severity axis** |
| **위험성(빈도x강도)** | COLUMN_HEADER | **빈도강도법: computed risk** |
| 위험성 감소대책 | COLUMN_HEADER | — (risk reduction) |
| 개선 후 위험성 | COLUMN_HEADER | — (post-improvement risk) |
| 개선예정일 | COLUMN_HEADER | — (target date) |
| 완료일 | COLUMN_HEADER | — (completion date) |
| 담당자 | COLUMN_HEADER | — (responsible person) |

PDF p93 text extraction confirmed example data rows present: actual risk scores (1, 2, 6) and assessment notes visible. Form is pre-filled example, not blank template.

### Identity analysis

빈도강도법 method confirmation:
- `가능성(빈도)` = frequency/probability axis ✓
- `중대성(강도)` = severity/consequence axis ✓
- `위험성(빈도x강도)` = risk = frequency × severity ✓

These three columns ARE the defining computational structure of 빈도강도법 (frequency-severity method). The KRAS 위험성평가표 uses this method.

KRAS-specific elements:
- Heading explicitly names "KRAS 시스템" (KOSHA Risk Assessment System, URL: http://kras.kosha.or.kr)
- "작성 예시" (writing example) suffix — this is a completed example, not a blank form
- No online-system-specific fields (login IDs, process codes, etc.) visible in the text extraction

Difference between method compatibility and form identity:
- **Method compatibility** (CONFIRMED): The KRAS 위험성평가표 uses the 빈도강도법 calculation. The column structure matches.
- **Form identity** (NOT CONFIRMED): The HWP form is explicitly a KRAS system example. A generic "위험성평가표(빈도강도법)" template (if it exists independently) may or may not have identical column structure. No separate generic template is available in the Owner-provided files for direct comparison.

### Proposed relationship

**METHOD_COMPATIBLE** — The KRAS 위험성평가표 uses 빈도강도법 (frequency×severity) as its risk scoring method, confirmed by 가능성(빈도)/중대성(강도)/위험성(빈도x강도) column structure. The source document is labeled as a KRAS system example. Whether this constitutes an IDENTICAL ORIGINAL SOURCE to the SoT research entry `위험성평가표(빈도강도법)` cannot be confirmed without a separate generic 빈도강도법 template for direct comparison. Identity determination: GPT.

Current SoT observed_fields for REF-C006: [] (empty, HOLD maintained). No writes performed.

---

## S3 REF-C008 TYPO RECOMMENDATION

### Evidence

| Source | Title |
|---|---|
| SoT source_title | 안전보건 **전문이력** 평가 기준 및 평가표 |
| HWP-08 heading (para 1292) | 안전보건 **전문인력** 평가 기준 및 평가표 예시 |
| PDF cross-check | Not retrieved in WO-050 (deferred) |

Korean character difference:
- `이력` (以歷) = career history, work record
- `인력` (人力) = personnel, human resources, workforce

Context: This document evaluates safety management personnel roles (안전보건관리책임자, 관리감독자, 안전보건총괄책임자). The correct domain term is `전문인력` (specialized personnel). `전문이력` (professional career history) is semantically incorrect in this context.

Assessment: The SoT `source_title` appears to contain a data-entry transcription error. One Korean character (`이` vs `인`) was substituted. The HWP original is authoritative.

### Proposed non-destructive correction path

**Do NOT update `source_title` directly** — preserves original recorded value and audit trail.

Recommended approach (for Owner authorization, not executed here):
1. Add to `source_observation_note`: `"SoT source_title '전문이력' is a probable transcription error; HWP-08 original heading reads '전문인력'. Correction pending Owner authorization."`
2. If Owner authorizes: update `source_title` = `'안전보건 전문인력 평가 기준 및 평가표'` in a separate authorized DB write.
3. Do NOT add "예시" suffix — the SoT does not carry the 예시 annotation.

DB writes: NONE (prohibited in WO-050).

---

## S4 RESIDUALS AND PARSER LIMITATIONS

| Item | Status | Note |
|---|---|---|
| HWP-10a visual read | COMPLETE | 24 nodes extracted. WORKFLOW_DIAGRAM confirmed. |
| HWP-10b/10c text | COMPLETE | PDF cross-check confirms column headers and row labels. |
| REF-C006 KRAS vs generic 빈도강도법 | UNDETERMINED | No independent generic template available in Owner files for direct form-to-form comparison. METHOD_COMPATIBLE confirmed. |
| REF-C010 SoT title identity | GPT_DETERMINATION_REQUIRED | Three source sections (10a/10b/10c) serve different document functions. |
| REF-C010c SoT research_id | UNRESOLVED | HWP-10c (질식,감전) has no confirmed research_id in 189 rows. |
| REF-C008 typo correction | PENDING_OWNER_AUTH | Correction path proposed; not written. |
| BIN0001 image quality | READABLE | 2520×2750px @400dpi — clear enough for visual node extraction without OCR. |
| HWP-10b/10c blank columns | NOTED | 담 당/비 고 are user-fillable columns but have no pre-printed content. Decision on whether to include as FORM_INPUT_FIELD: GPT. |
| HWP-10a FORM_INPUT_FIELD | NONE | No input fields in diagram. Workflow reference only. |

---

## S5 STOP — GPT INDEPENDENT VERIFY

DB mutations this WO: 0.
SoT state: 189 rows, 14 observed_nonempty, REF-C006/C010 HOLD maintained (confirmed via live SQL).
No new research IDs. No source_title changes. No schema changes. No deployment.

FINAL: READY_FOR_GPT_INDEPENDENT_REVIEW
DO_NOT_EXPAND = TRUE
