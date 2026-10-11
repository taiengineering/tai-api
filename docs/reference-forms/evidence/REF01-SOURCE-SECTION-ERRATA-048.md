# REF-01 Source Section Errata / WO-048
Date: 2026-10-08
WO: WO-REF01-SOURCE-IDENTITY-CORRECTION-048
Investigator: Claude Code (evidence correction only — no DB writes authorized by this WO)
Basis: WO-047 manifest `REF01-SOURCE-SECTION-MANIFEST-047.md` + GPT independent review + direct SoT SQL.

## ERRATUM RECORD

WO-047 manifest declared HWP-11 UNRESOLVED / no confirmed research_id. This was incorrect.

**Error**: `HWP-11 | 도급·용역·위탁 업체 안전보건 수준 평가 예시 | UNRESOLVED — No confirmed research_id in 189 rows`

**Correction**: REF-C011 exists in SoT with source_title `도급·용역·위탁 업체 안전보건 수준 평가`. HWP-11 heading `도급·용역·위탁 업체 안전보건 수준 평가 예시` (예시 = guide example suffix) matches. No new SoT record creation required. DO NOT CREATE DUPLICATE.

WO-047 manifest is retained unchanged (evidence history must not be rewritten). This erratum supersedes the HWP-11 UNRESOLVED classification only.

---

## S0 DIRECT SoT PROOF — REF-C006 through REF-C011

SQL: `SELECT research_id, source_title, source_document_access, observed_fields FROM public.ref_form_research_items WHERE research_id IN ('REF-C006','REF-C007','REF-C008','REF-C009','REF-C010','REF-C011')`

| research_id | source_title (current SoT) | observed_fields | source_document_access | source_url |
|---|---|---|---|---|
| REF-C006 | 위험성평가표(빈도강도법) | [] (empty) | ARTICLE_LOGIN_REQUIRED | KOSHA 453942 |
| REF-C007 | 안전보건예산 편성 서식 | [] (empty) | ARTICLE_LOGIN_REQUIRED | KOSHA 453942 |
| REF-C008 | 안전보건 전문이력 평가 기준 및 평가표 | [] (empty) | ARTICLE_LOGIN_REQUIRED | KOSHA 453942 |
| REF-C009 | 안전보건 전문인력 등 배치표 및 담당업무 | [] (empty) | ARTICLE_LOGIN_REQUIRED | KOSHA 453942 |
| REF-C010 | 사고 발생 대응 시나리오(처리 흐름도) | [] (empty) | ARTICLE_LOGIN_REQUIRED | KOSHA 453942 |
| REF-C011 | 도급·용역·위탁 업체 안전보건 수준 평가 | [] (empty) | NOT_CHECKED | NULL |

DB total rows: 189. observed_fields nonempty: 10 (REF-C001~C005, C012~C016 from batches 042/043). All 6 target IDs have observed_fields=[].

---

## S1 HWP SOURCE HEADING ↔ SoT TITLE MATCH ANALYSIS

| research_id | SoT source_title | HWP heading (exact, from HWP-047) | Match assessment |
|---|---|---|---|
| REF-C006 | 위험성평가표(빈도강도법) | KRAS 시스템 위험성평가표 작성 예시 | TITLE_DIVERGENCE — SoT title is generic form name; HWP heading specifies KRAS online system. Do not equate. |
| REF-C007 | 안전보건예산 편성 서식 | 안전보건 예산 편성항목 예시 | CLOSE_MATCH — "편성 서식" vs "편성항목 예시". Same subject, minor wording difference. |
| REF-C008 | 안전보건 전문이력 평가 기준 및 평가표 | 안전보건 전문인력 평가 기준 및 평가표 예시 | PROBABLE_MATCH with TYPO NOTE — SoT has "이력"(career history) vs HWP "인력"(personnel). HWP text is "인력" (correct). SoT may have a typo. Do not silently change source_title. |
| REF-C009 | 안전보건 전문인력 등 배치표 및 담당업무 | 안전보건 전문인력 등 배치표 및 담당업무 | EXACT_MATCH |
| REF-C010 | 사고 발생 대응 시나리오(처리 흐름도) | HWP-10a: 협착사고 발생 시 대응 시나리오(처리 흐름도) [image-only] | PARTIAL_MATCH — HWP-10a heading contains "처리 흐름도" and "시나리오". SoT title "사고 발생 대응 시나리오(처리 흐름도)" aligns with HWP-10a generically; but HWP-10a is image-only. HWP-10b/10c are different accident types. |
| REF-C011 | 도급·용역·위탁 업체 안전보건 수준 평가 | 도급·용역·위탁 업체 안전보건 수준 평가 예시 | MATCH (예시 suffix is guide context, not a different form) |

---

## S2 PER-ID PROPOSED WRITE MATRIX

This matrix documents what could be written to observed_fields for each ID, pending GPT authorization. **No DB writes performed in this WO.**

Source asset for all entries: Asset A — 2022 MOEL HWP, SHA256 `e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe`.
All field labels: extracted from HWP5 BodyText/Section0 paragraph text (NATIVE_PARAGRAPH_ONLY — no exact cell coordinates).
All requiredness: UNVERIFIED (no LEG check performed).
source_document_access proposed value: OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL (same as batches 042/043).

---

### REF-C006 — 위험성평가표(빈도강도법)

HWP section: HWP-06, Para 1026–1232
HWP exact heading: `KRAS 시스템 위험성평가표 작성 예시`
SoT source_title: `위험성평가표(빈도강도법)`
Title relationship: RELATED_CANDIDATE_SOURCE_SECTION (HWP heading specifies KRAS online system; SoT title specifies frequency×severity method; same evaluation domain, different naming. Do NOT overwrite SoT source_title.)

| Proposed label | Label type | Para ref | Notes |
|---|---|---|---|
| 담당 | APPROVAL_COLUMN | 1040 | Approval box header |
| 부장 | APPROVAL_COLUMN | 1041 | Approval box header |
| 대표 | APPROVAL_COLUMN | 1042 | Approval box header |
| 작업공정명 | INPUT_LABEL | 1071 | Process name field |
| 평가일시 | INPUT_LABEL | 1073 | Assessment date |
| 세부작업내용 | COLUMN_HEADER | 1074–1076 | Sub-task description (split across 3 paras) |
| 유해·위험요인 파악 | COLUMN_HEADER | 1077 | Hazard identification column group |
| 관련근거(법적기준) | COLUMN_HEADER | 1078–1079 | Legal basis |
| 현재의 안전보건조치 | COLUMN_HEADER | 1080–1082 | Existing safety measures |
| 위험분류 | COLUMN_HEADER | 1092–1093 | Risk category |
| 위험발생 상황 및 결과 | COLUMN_HEADER | 1094–1095 | Risk scenario |
| 가능성(빈도) | COLUMN_HEADER | 1096–1097 | Probability/frequency |
| 중대성(강도) | COLUMN_HEADER | 1098–1099 | Severity |
| 위험성(빈도x강도) | COLUMN_HEADER | 1100–1101 | Risk score |
| 위험성 감소대책 | COLUMN_HEADER | 1084–1085 | Risk reduction measures |
| 개선 후 위험성 | COLUMN_HEADER | 1086–1087 | Post-improvement risk |
| 개선예정일 | COLUMN_HEADER | 1088–1089 | Target improvement date |
| 완료일 | COLUMN_HEADER | 1090 | Completion date |
| 담당자 | COLUMN_HEADER | 1091 | Responsible person |

Confidence: NATIVE_PARAGRAPH_ONLY. Column groups split across multiple paragraphs due to table cell rendering. Cell merge/boundary not verified.
Extraction note: Column headers separated by cell boundaries are represented as multi-paragraph sequences. The actual table has merged header cells that this parser cannot resolve.

---

### REF-C007 — 안전보건예산 편성 서식

HWP section: HWP-07, Para 1233–1290
HWP exact heading: `안전보건 예산 편성항목 예시`
SoT source_title: `안전보건예산 편성 서식`
Title relationship: CLOSE_MATCH

This section is a budget line-item template, not an interactive row-entry form. Labels are budget category names (CATEGORY/ROW_LABEL type), not standalone input fields.

| Proposed label | Label type | Para ref | Notes |
|---|---|---|---|
| 구분 | COLUMN_HEADER | 1236 | Category column |
| 연도(예: 2021, 2022) | COLUMN_HEADER | 1237–1238 | Year columns (example years only) |
| 인력 및 시설분야 | CATEGORY_LABEL | 1239 | Budget domain 1 |
| 위험시설 정비 및 개보수 | ROW_LABEL | 1240 | Line item |
| 안전검사 실시 | ROW_LABEL | 1243 | Line item |
| 안전시설 신규 설치 및 투자 | ROW_LABEL | 1246 | Line item |
| 안전보건조직 노무관리 | ROW_LABEL | 1249 | Line item |
| 안전분야 | CATEGORY_LABEL | 1252 | Budget domain 2 |
| 안전인력 육성 및 교육 | ROW_LABEL | 1253 | Line item |
| 안전보건 진단 및 컨설팅 | ROW_LABEL | 1256 | Line item |
| 위험성평가 실시 | ROW_LABEL | 1259 | Line item |
| 안전보호구 구입 | ROW_LABEL | 1262 | Line item |
| 보건분야 | CATEGORY_LABEL | 1265 | Budget domain 3 |
| 작업환경측정 실시 | ROW_LABEL | 1266 | Line item |
| 특수건강검진 실시 | ROW_LABEL | 1269 | Line item |
| 근골격계질환 예방 | ROW_LABEL | 1272 | Line item |
| 휴게·위생시설 관리 | ROW_LABEL | 1275 | Line item |
| 기타 | CATEGORY_LABEL | 1278 | Budget domain 4 |
| 협력사 안전관리 역량 지원 | ROW_LABEL | 1279 | Line item |
| 안전보건 캠페인 추진 | ROW_LABEL | 1284 | Line item |
| 예비(예비비) | ROW_LABEL | 1287–1288 | Reserve budget |

Confidence: NATIVE_PARAGRAPH_ONLY. These are budget category/sub-category labels, not interactive user input fields.

---

### REF-C008 — 안전보건 전문이력 평가 기준 및 평가표

HWP section: HWP-08, Para 1291–1404
HWP exact heading: `안전보건 전문인력 평가 기준 및 평가표 예시`
SoT source_title: `안전보건 전문이력 평가 기준 및 평가표`
Title relationship: PROBABLE_MATCH with TYPO — SoT "이력" should be "인력". Do not silently overwrite source_title.

This section has two distinct sub-components, documented separately:

**Sub-section A: 평가기준 (Para 1292–1299)**

| Proposed label | Label type | Para ref | Notes |
|---|---|---|---|
| 양호 | EVALUATION_CRITERION | 1294 | Rating: Good |
| 보통 | EVALUATION_CRITERION | 1296 | Rating: Acceptable |
| 미흡 | EVALUATION_CRITERION | 1298 | Rating: Insufficient |

Content: Criterion definitions by legal duty fulfilment level. Not interactive input fields.

**Sub-section B: 평가표(안) (Para 1301–1404)**

| Proposed label | Label type | Para ref | Notes |
|---|---|---|---|
| 직책 | COLUMN_HEADER | 1303 | Role/position |
| 성명 | COLUMN_HEADER | 1304 | Name |
| 담당업무 | COLUMN_HEADER | 1305 | Assigned duties (list) |
| 평가 (미흡/보통/양호) | COLUMN_HEADER | 1306–1309 | 3-point rating scale |
| 안전보건관리 책임자 | ROW_LABEL | 1310–1312 | Role type 1 |
| 관리감독자 | ROW_LABEL | 1354–1355 | Role type 2 |
| 안전보건총괄책임자 | ROW_LABEL | 1382–1383 | Role type 3 |

Note: Duty item lists (항목 1~10 per role) are statutory quotations from산업안전보건법, not independent form fields. They are reference text embedded in the evaluation table.

Confidence: NATIVE_PARAGRAPH_ONLY. Table has merged cells spanning role groups; paragraph boundaries do not directly map to cell coordinates.

---

### REF-C009 — 안전보건 전문인력 등 배치표 및 담당업무

HWP section: HWP-09, Para 1405–1461
HWP exact heading: `안전보건 전문인력 등 배치표 및 담당업무`
SoT source_title: `안전보건 전문인력 등 배치표 및 담당업무`
Title relationship: EXACT_MATCH

| Proposed label | Label type | Para ref | Notes |
|---|---|---|---|
| 직책 | COLUMN_HEADER | 1407 | Position |
| 성명 | COLUMN_HEADER | 1408 | Name |
| 담당업무 | COLUMN_HEADER | 1409 | Assigned duties |
| 비고 | COLUMN_HEADER | 1410 | Remarks |
| 안전관리자 (산안법 제17조) | ROW_LABEL | 1411–1412 | Personnel type 1 |
| 보건관리자 (산안법 제18조) | ROW_LABEL | 1425–1426 | Personnel type 2 |
| 안전보건관리담당자 (산안법 제19조) | ROW_LABEL | 1443–1445 | Personnel type 3 |
| 산업보건의 (산안법 제22조) | ROW_LABEL | 1454–1456 | Personnel type 4 |

Note: Duty item lists per role type (items 1~14 from HWP source) are statutory duty descriptions, not standalone input fields. They provide duty reference context for the 담당업무 column.

Confidence: NATIVE_PARAGRAPH_ONLY.

---

### REF-C010 — 사고 발생 대응 시나리오(처리 흐름도)

HWP sections: HWP-10a, HWP-10b, HWP-10c (Para 1462–1596)
SoT source_title: `사고 발생 대응 시나리오(처리 흐름도)`

Three source sections preserved independently per WO-048 GPT determination. No canonical merge.

**HWP-10a: 협착사고 발생 시 대응 시나리오(처리 흐름도)** (Para 1462–1463)
- Content: Image/diagram only. Para 1462 = heading; Para 1463 = embedded image control (BinData/BIN0001.tif via OLE).
- Observed fields: NONE extractable via text parser.
- Extraction confidence: PDF_CROSSCHECK_ONLY (PDF p.106 confirms heading).
- Field labels: EMPTY — requires visual/OCR extraction of the flowchart image.

**HWP-10b: 추락사고 대응 시나리오 작성 예시** (Para 1464–1541)

| Proposed label | Label type | Para ref | Notes |
|---|---|---|---|
| 시간 및 상황 | COLUMN_HEADER | 1466 | Time/situation column |
| 조치사항 | COLUMN_HEADER | 1467 | Action items column |
| 담 당 | COLUMN_HEADER | 1468 | Responsible party column |
| 비 고 | COLUMN_HEADER | 1469 | Notes column |
| 00:00~00:01 추락사고 발생/환자 발생 | ROW_LABEL | 1470–1472 | Time sequence row 1 |
| 00:01~00:06 환자 구조 / 119 구조대 신고 / 환자 응급조치 | ROW_LABEL | 1483–1496 | Time sequence rows 2–4 |
| 00:06~00:10 상황 보고 / 현장 보존 | ROW_LABEL | 1517–1530 | Time sequence rows 5–6 |
| 00:10~ 환자 병원 후송 | ROW_LABEL | 1537–1539 | Time sequence row 7 |

**HWP-10c: 질식, 감전재해 대응 시나리오 작성 예시** (Para 1542–1596)
Same column structure as HWP-10b: 시간 및 상황 / 조치사항 / 담 당 / 비 고
Accident scenario: 밀폐공간 질식 / 감전 (Para 1553–1555)
Confidence: NATIVE_PARAGRAPH_ONLY.
SoT mapping: UNRESOLVED — no confirmed research_id for this specific scenario type.

Matching note for REF-C010: HWP-10a heading `협착사고 발생 시 대응 시나리오(처리 흐름도)` is the closest textual match to SoT `사고 발생 대응 시나리오(처리 흐름도)`, but is image-only. HWP-10b and HWP-10c are related scenario types (fall, asphyxiation/electrical) not named in the SoT title. Relationship to REF-C010: AMBIGUOUS pending GPT resolution.

---

### REF-C011 — 도급·용역·위탁 업체 안전보건 수준 평가

**ERRATUM CORRECTION: Previously classified UNRESOLVED in WO-047. Correct classification: MATCH.**

HWP section: HWP-11, Para 1597–1645
HWP exact heading: `도급·용역·위탁 업체 안전보건 수준 평가 예시`
SoT source_title: `도급·용역·위탁 업체 안전보건 수준 평가`
Title relationship: MATCH (예시 = guide example annotation, not a different form)
PDF page: 111 (confirmed via pdfplumber extraction)
source_url (current SoT): NULL
source_document_access (current SoT): NOT_CHECKED

| Proposed label | Label type | Para ref | Notes |
|---|---|---|---|
| 평가항목 | COLUMN_HEADER | 1599 | Evaluation item column |
| 평가기준 | COLUMN_HEADER | 1600 | Criterion column |
| 배점 | COLUMN_HEADER | 1601 | Score weight column |
| 점수 | COLUMN_HEADER | 1602 | Score column |
| I. 안전보건관리체계 | CATEGORY_LABEL | 1603 | Domain 1 |
| 도급·용역·위탁받는 자의 안전보건관리 체계 구축 수준 | ROW_LABEL | 1604 | Domain 1 description |
| 리더십 | SUB_CATEGORY | 1607 | Sub-item 1-1 |
| 경영방침, 인력·시설·장비 등 자원 배정의 적정성 등 | ROW_LABEL | 1608 | Sub-item 1-1 criteria |
| 근로자 참여 | SUB_CATEGORY | 1611 | Sub-item 1-2 |
| 종사자 의견수렴 절차 및 이행 적정성 | ROW_LABEL | 1612 | Sub-item 1-2 criteria |
| 위험요인 파악 및 제거·대체·통제 | SUB_CATEGORY | 1615 | Sub-item 1-3 |
| 비상조치계획 | SUB_CATEGORY | 1619 | Sub-item 1-4 |
| II. 도급·용역·위탁 안전보건 관리계획 | CATEGORY_LABEL | 1623 | Domain 2 |
| 위험요인 파악 및 제거·대체·통제 (도급) | SUB_CATEGORY | 1627–1628 | Sub-item 2-1 |
| 자원 배정(시설·장비) | SUB_CATEGORY | 1631–1633 | Sub-item 2-2 |
| 자원 배정(인력) | SUB_CATEGORY | 1636–1638 | Sub-item 2-3 |
| 비상조치계획 (도급) | SUB_CATEGORY | 1641–1643 | Sub-item 2-4 |

배점 distribution: I.리더십 10 / 근로자참여 10 / 위험요인 10 / 비상조치 10 = subtotal 40; II.위험요인 15 / 시설장비 15 / 인력 15 / 비상조치 15 = subtotal 60; TOTAL 100점.

Confidence: NATIVE_PARAGRAPH_ONLY.

---

## S3 SUMMARY TABLE — PROPOSED UPDATES

This table represents what would be written to `observed_fields` if GPT authorizes the DB update batch.

| research_id | HWP section | Title match | Field labels proposed | Label types | Confidence | source_document_checksum |
|---|---|---|---|---|---|---|
| REF-C006 | HWP-06 (Para 1026–1232) | TITLE_DIVERGENCE | 19 | COLUMN_HEADER, INPUT_LABEL, APPROVAL_COLUMN | NATIVE_PARAGRAPH_ONLY | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe |
| REF-C007 | HWP-07 (Para 1233–1290) | CLOSE_MATCH | 21 | CATEGORY_LABEL, ROW_LABEL, COLUMN_HEADER | NATIVE_PARAGRAPH_ONLY | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe |
| REF-C008 | HWP-08 (Para 1291–1404) | PROBABLE_MATCH + TYPO | 10 | EVALUATION_CRITERION, COLUMN_HEADER, ROW_LABEL | NATIVE_PARAGRAPH_ONLY | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe |
| REF-C009 | HWP-09 (Para 1405–1461) | EXACT_MATCH | 8 | COLUMN_HEADER, ROW_LABEL | NATIVE_PARAGRAPH_ONLY | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe |
| REF-C010 (10a) | HWP-10a (Para 1462–1463) | PARTIAL_MATCH | 0 (image-only) | — | PDF_CROSSCHECK_ONLY | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe |
| REF-C010 (10b) | HWP-10b (Para 1464–1541) | RELATED_STAGE | 8 | COLUMN_HEADER, ROW_LABEL | NATIVE_PARAGRAPH_ONLY | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe |
| REF-C011 | HWP-11 (Para 1597–1645) | MATCH | 16 | CATEGORY_LABEL, SUB_CATEGORY, ROW_LABEL, COLUMN_HEADER | NATIVE_PARAGRAPH_ONLY | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe |

HWP-10c (질식·감전) remains UNRESOLVED — no SoT research_id confirmed.

---

## S4 STOP — GPT REVIEW GATE

DB mutations this WO: 0.
DB state: 189 rows, observed_fields nonempty: 10 (unchanged).
No new research records created. No schema changes. No canonical_candidate_id assignments.

Pending GPT authorization for next batch:
1. Confirm REF-C006 observed_fields write despite TITLE_DIVERGENCE (KRAS vs 빈도강도법).
2. Confirm REF-C007 observed_fields write with CATEGORY/ROW_LABEL type distinction.
3. Confirm REF-C008 observed_fields write; confirm whether SoT source_title typo "이력"→"인력" should also be corrected.
4. Confirm REF-C009 observed_fields write (EXACT_MATCH — no title issue).
5. Confirm REF-C010 strategy: write HWP-10b labels to REF-C010? Or hold pending HWP-10a visual extraction?
6. Confirm REF-C011 observed_fields write + source_document_access update (NOT_CHECKED → OWNER_UPLOADED_HWP_TEXT_PARSED_PARTIAL) + source_document_checksum set.

FINAL: EVIDENCE_READY_FOR_GPT_REVIEW. WO-047 erratum recorded. No DB writes performed.
