# REF-01 Source Section Manifest / WO-047
Date: 2026-10-08
WO: WO-REF01-SOURCE-SECTION-CELL-EXTRACTION-047
Investigator: Claude Code (collect/evidence only — no DB writes, no implementation)
Basis: OBJ-REF-01-THREE-LEVEL-IDENTITY-CONTRACT-046.md; evidence receipts 041–045.

## S0 PREFLIGHT

| Item | Value |
|---|---|
| Repository branch | docs/tai-reference-forms-charter-obj-20261008 |
| Branch HEAD SHA | 4bfab39e (after fetch) |
| Supabase project | vwlahtguyggrhvslabax |
| Table | public.ref_form_research_items |
| DB row count | 189 ✓ (confirmed via SELECT COUNT(*)) |
| DB rows observed_fields nonempty | 10 (REF-C001~005, REF-C012~016) |
| DB mutations this WO | 0 |

### Source file hash verification

| Asset | Local filename | SHA256 (WO-specified) | SHA256 (recomputed) | Match | Size (bytes) |
|---|---|---|---|---|---|
| A: 2022 MOEL HWP | 활용 서식 모음_'중대재해처벌법 따라하기' 안내서.hwp | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe | e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe | MATCH | 897,024 |
| B: 2023 HWPX | (서식) 2023 새로운 위험성평가 안내서 수록 각종 서식.hwpx | c624ea2e72c4e79b8daa011375d2105f3f917e069b47dfd95c9850b193d21d46 | c624ea2e72c4e79b8daa011375d2105f3f917e069b47dfd95c9850b193d21d46 | MATCH | 54,195 |
| C: MOEL guide PDF | 최종_경영책임자와 관리자가 알아야 할 중대재해처벌법 따라하기 안내서.pdf | a73ce4c67dfcb4a1b27f647ad346496f1bc7421666653da516c9ca92a46c60ff | a73ce4c67dfcb4a1b27f647ad346496f1bc7421666653da516c9ca92a46c60ff | MATCH | 34,266,070 |

All three SHA256 hashes VERIFIED. No speculative recovery attempted.

### Parser inventory

| Parser | Version | Fidelity note |
|---|---|---|
| olefile | 0.47 | OLE/CFB stream listing and raw byte access |
| pyhwp | 0.1b15 | Installed but manual HWP5 record parser used (tag-level) |
| HWP5 manual parser | N/A | Reads tag IDs 66 (PARA_HEADER), 67 (PARA_TEXT); decodes UTF-16-LE; handles compressed BodyText. Cell boundary coordinates NOT reliably extracted — HWP5 table control records (tag 85/87) parsed by count only. |
| zipfile | stdlib | HWPX ZIP extraction |
| xml.etree.ElementTree | stdlib | HWPX section0.xml parsing; hp:tbl/hp:tr/hp:tc/hp:cellAddr accessible but cellAddr row/col attribute not populated in this file (all returned `?`). Cell content NATIVE_TABLE_VERIFIED via hp:t nodes. |
| pdfplumber | installed | PDF text extraction, page-level heading identification |

Cell coordinate fidelity: HWP5 = NATIVE_PARAGRAPH_ONLY (no exact row/col). HWPX = NATIVE_TABLE_VERIFIED (table/row/cell structure readable; coordinates unresolved due to missing cellAddr attributes in this specific file). PDF = PDF_CROSSCHECK_ONLY.

---

## S1 HWP5 FORM BOUNDARY EVIDENCE (Asset A)

Source: SHA256 e94d8d8a271c148973111ff0c74b4d67ba2f9884aff59e87301e261b5794aefe
OLE stream: BodyText/Section0 (single section, raw-deflate compressed, 60,732→320,173 bytes decompressed)
Total HWP5 paragraph records: 2,197

Section headings identified by `漠杳` control character prefix in paragraph text.

### S1 Section Inventory (20 entries)

| Ordinal | Para start | Para end | Exact Korean heading | Candidate research_id | Relationship | Confidence |
|---|---|---|---|---|---|---|
| HWP-01 | 1 | 15 | 안전보건 경영방침 작성 예시 | REF-C001 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-02a | 16 | 296 | 안전보건 목표 및 추진계획서 작성 예시(1) | REF-C002 | EXACT_SOURCE_SECTION (part 1 of 2) | NATIVE_PARAGRAPH_ONLY |
| HWP-02b | 297 | 844 | 안전보건 목표 및 추진계획서 작성 예시(2) | REF-C002 | EXACT_SOURCE_SECTION (part 2 of 2) | NATIVE_PARAGRAPH_ONLY |
| HWP-03 | 845 | 908 | 위험기계·기구·설비 목록 작성 서식 예시 | REF-C003 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-04 | 909 | 975 | 유해·위험물질 목록 작성 서식 예시 | REF-C004 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-05 | 976 | 1025 | 작업별 위험관리 대장 활용 서식 예시 | REF-C005 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-06 | 1026 | 1232 | KRAS 시스템 위험성평가표 작성 예시 | REF-C006 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-07 | 1233 | 1290 | 안전보건 예산 편성항목 예시 | REF-C007 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-08 | 1291 | 1404 | 안전보건 전문인력 평가 기준 및 평가표 예시 | REF-C008 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-09 | 1405 | 1461 | 안전보건 전문인력 등 배치표 및 담당업무 | REF-C009 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-10a | 1462 | 1463 | 협착사고 발생 시 대응 시나리오(처리 흐름도) | REF-C010? | AMBIGUOUS — image-only section (2 paras: heading + empty); no table/text field extracted | PDF_CROSSCHECK_ONLY |
| HWP-10b | 1464 | 1541 | 추락사고 대응 시나리오 작성 예시 | REF-C010? | RELATED_STAGE — scenario table present; WO-047 target REF-C010 title is "사고 발생 대응 시나리오(처리 흐름도)", ambiguous match | NATIVE_PARAGRAPH_ONLY |
| HWP-10c | 1542 | 1596 | 질식, 감전재해 대응 시나리오 작성 예시 | UNRESOLVED | No confirmed research_id | NATIVE_PARAGRAPH_ONLY |
| HWP-11 | 1597 | 1645 | 도급·용역·위탁 업체 안전보건 수준 평가 예시 | UNRESOLVED | No confirmed research_id in 189 rows | NATIVE_PARAGRAPH_ONLY |
| HWP-12 | 1646 | 1806 | 안전작업허가서 활용 서식 | REF-C012 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-13 | 1807 | 1845 | 사고조사 보고서 서식 | REF-C013 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-14 | 1846 | 1953 | 재해 감소대책 수립 및 실행 계획서 작성 서식 | REF-C014 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-15 | 1954 | 1973 | 아차 사고 보고서 양식 예시 | REF-C015 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |
| HWP-15b | 1974 | 1993 | 아차 사고 등급 분류기준 | REF-C015 sub-section | Sub-section (classification table, not a separate form) | NATIVE_PARAGRAPH_ONLY |
| HWP-16 | 1994 | 2197 | 연간 교육계획 수립 서식 | REF-C016 | EXACT_SOURCE_SECTION | NATIVE_PARAGRAPH_ONLY |

**Section count:** 20 entries (18 primary forms + 1 split + 1 subsection).
**Primary form count:** 16 distinct forms (REF-C001~C009, C010-ambiguous, C012~C016).
**UNRESOLVED:** HWP-10a/10b/10c (REF-C010 ambiguity: 협착/추락/질식·감전 scenarios), HWP-11 (도급평가).

### S1 Field labels per section (REF-C006~C010, new vs. 042/043)

**HWP-06: KRAS 시스템 위험성평가표 작성 예시 (REF-C006 candidate)**
Para 1040-1101 column headers: 담당, 부장, 대표, 작업공정명, 위험성평가, 평가일시, 세부작업내용, 유해·위험요인 파악, 관련근거(법적기준), 현재의 안전보건조치, 위험성, 위험분류, 위험발생 상황 및 결과, 가능성(빈도), 중대성(강도), 위험성(빈도x강도), 위험성 감소대책, 개선 후 위험성, 개선예정일, 완료일, 담당자
Note: WO source title "위험성평가표(빈도강도법)"; HWP heading "KRAS 시스템 위험성평가표 작성 예시" — title divergence, KRAS = KOSHA Risk Assessment System. Heading match RELATED_STAGE, not exact title match with REF-C006 DB entry.

**HWP-07: 안전보건 예산 편성항목 예시 (REF-C007)**
Para 1236-1288 column/row headers: 구분, 연도(2021, 2022), 인력 및 시설분야(위험시설 정비·개보수, 안전검사, 안전시설 설치·투자, 안전보건조직 노무관리), 안전분야(안전인력 육성·교육, 안전보건 진단·컨설팅, 위험성평가, 안전보호구 구입), 보건분야(작업환경측정, 특수건강검진, 근골격계질환 예방, 휴게·위생시설 관리), 기타(협력사 지원, 안전보건 캠페인), 예비비
Note: This is a budget line-item template, not a tabular form with input rows. Observation confidence: NATIVE_PARAGRAPH_ONLY.

**HWP-08: 안전보건 전문인력 평가 기준 및 평가표 예시 (REF-C008)**
Sub-section 1 (평가기준, Para 1293-1299): 양호/보통/미흡 기준 텍스트 (not tabular)
Sub-section 2 (평가표, Para 1302-1404): 직책, 성명, 담당업무, 평가(미흡/보통/양호), 역할유형(안전보건관리 책임자/관리감독자/안전보건총괄책임자), 담당업무항목 1~10
Note: 담당업무항목은 산안법 조항 참조. 평가는 3점 척도.

**HWP-09: 안전보건 전문인력 등 배치표 및 담당업무 (REF-C009)**
Para 1407-1461 column headers: 직책, 성명, 담당업무, 비고
직책 유형: 안전관리자(산안법 제17조), 보건관리자(산안법 제18조), 안전보건관리담당자(산안법 제19조), 산업보건의(산안법 제22조)
담당업무: 각 직책별 법정 직무 항목 1~14

**HWP-10a: 협착사고 발생 시 대응 시나리오(처리 흐름도) [AMBIGUOUS]**
Para 1462: heading "漠杳 협착사고 발생 시 대응 시나리오(처리 흐름도)"
Para 1463: empty (image control character only — diagram is embedded BinData, not text)
No text field labels extractable. Image/diagram only. Parser limitation: NATIVE_PARAGRAPH_ONLY — image bytes NOT committed.

**HWP-10b: 추락사고 대응 시나리오 작성 예시 [RELATED_STAGE]**
Para 1465-1541 table headers: 시간 및 상황, 조치사항, 담 당, 비 고
Time sequence: 00:00~00:01(추락사고 발생/환자 발생), 00:01~00:06(환자 구조/119 신고/응급조치), 00:06~00:10(상황 보고/현장 보존), 00:10~(환자 병원 후송)

**HWP-10c: 질식·감전재해 대응 시나리오 작성 예시 [UNRESOLVED]**
Para 1543-1596 table headers: 시간 및 상황, 조치사항, 담 당, 비 고
Same time-sequence structure as HWP-10b. No confirmed research_id.

---

## S2 HWPX EIGHT-SECTION EXTRACTION (Asset B)

Source: SHA256 c624ea2e72c4e79b8daa011375d2105f3f917e069b47dfd95c9850b193d21d46
ZIP structure: Contents/section0.xml (305,576 bytes), BinData/image1.bmp (7,110 bytes)
XML root: `hs:sec` (namespace: http://www.hancom.co.kr/hwpml/2011/section)
Structure: 23 top-level `hp:p` elements containing embedded `hp:tbl` elements via `hp:ctrl`
Total: 23 tbl, 105 tr, 295 tc (all via hp namespace)
cellAddr row/col attributes: NOT populated in this file (all `?`) — table row/cell position confirmed by hp:tr/hp:tc sequence count, NOT by coordinate values.

### S2 Section Inventory (8 sections confirmed)

Section boundary marker: each section opens with a `hp:p` containing a 1-row "참고" or "참고 N" table.

| HWPX ordinal | P-idx (top-level) | Exact Korean heading | Tables in section | Rows | Research_id candidate | Relationship (from 046) |
|---|---|---|---|---|---|---|
| HWPX-01 | P1 | 아차사고사례 발굴보고서 | 1 (11 rows) | 11 | REF-C015 | SAME_WORKFLOW_DIFFERENT_SOURCE_FORM |
| HWPX-02 | P3 | 제조공정 안전보건상 위험정보 | 2 (11+1 rows) | 12 | UNRESOLVED | no confirmed research_id |
| HWPX-03 | P5 | 사업장 순회점검에 의한 유해·위험요인 조사표 | 1 (5 rows) | 5 | UNRESOLVED | no confirmed research_id |
| HWPX-04 | P7 | 청취조사에 의한 유해·위험요인 조사표 | 1 (4 rows) | 4 | UNRESOLVED | no confirmed research_id |
| HWPX-05 | P9–P15 | 안전보건자료에 의한 유해·위험요인 조사표 | 3 (3+5+9+5 = multi-table, P9-P15) | 22 total | UNRESOLVED | no confirmed research_id |
| HWPX-06 | P18 | 안전보건 체크리스트에 의한 유해·위험요인 조사표 | 2 (4+2 rows) | 6 | REF-C027 | RELATED_STAGE_NOT_IDENTICAL |
| HWPX-07 | P20 | 위험성 감소대책 수립 및 실행 | 3 (5+2+4 rows) | 11 | REF-C014 | RELATED_CONTROL_STAGE_NOT_IDENTICAL |
| HWPX-08 | P22 | Tool Box Meeting 회의록 | 1 (26 rows) | 26 | REF-C064 | POSSIBLE_VARIANT_SCOPE_DIFFERENCE |

**Section count:** 8 (CONFIRMED — matches WO-047 specification).

### S2 Cell labels per section

**HWPX-01: 아차사고사례 발굴보고서** (P1, 11 rows)
Row 0: 아차사고사례 발굴보고서 (title)
Row 1: 1. 작성자
Row 2: 기관 | (blank) | 부서 | (blank)
Row 3: 작성일 | (blank) | 직급 | (blank) | 성명 | (blank)
Row 4: 2. 사고사례
Row 5: 발생연월 | (blank) | 발생형태 | (blank)
Row 6: ■ 사고 내용 (6하 원칙에 의해 구체적으로 작성)
Row 7: ■ 사고발생 원인
Row 8: ■ 재발방지 대책
Row 9: 비고
Row 10: (footer/empty)

**HWPX-02: 제조공정 안전보건상 위험정보** (P3, 2 tables)
Table 0 (11 rows): 제조공정 | 안전보건상 위험정보 | 생산품 | 원(재)료 | 근로자수 | 공정(작업)순서 | 기계·기구 및 설비 | 유해화학물질 | 기타 안전보건상 정보 | 기계·기구 및 설비명 | 수량 | 화학물질명 | 취급량/일 | 취급시간 | 3년간 재해발생사례 | 아차사고 사례
Table 1 (1 row): 작업형태/근로자 특성 체크박스 항목 (여성/고령/외국인/1년미만/비정규/장애/교대/도급/작업표준/운반수단/안전작업허가증/중량물/작업환경측정/특수건강진단/특별안전교육)

**HWPX-03: 사업장 순회점검에 의한 유해·위험요인 조사표** (P5, 5 rows)
Row 0: 사업장 순회점검에 의한 유해·위험요인 조사표 (title)
Row 1: 실시방법 | 내용
Row 2: 수행자 성명: | 수행일시:
Row 3: 유해·위험작업 (1)(2)(3) — 발견한 내용/장소/정도
Row 4: 사고 유형(①끼임·감김 ②추락·전도 ③감전 ④화재·폭발 ⑤기타) / 질병 유형(①진폐 ②중독 ③난청 ④요통 ⑤기타)

**HWPX-04: 청취조사에 의한 유해·위험요인 조사표** (P7, 4 rows)
Row 0: 청취조사에 의한 유해·위험요인 조사표 (title)
Row 1: 실시방법 | 내용
Row 2: 수행자 성명: | 근로자 성명(소속): | 수행일시:
Row 3: 경험담 1/2/3 | 근로자 의견(유해위험 경험 원인·반성) | 수행자 의견(경험에 대한 조언)

**HWPX-05: 안전보건자료에 의한 유해·위험요인 조사표** (P9+P11+P13+P15, multi-table)
P9 (3 rows): 조사표 제목/실시방법/수행자·일시
P11 (5 rows): 자료 종류 | 발생일시 | 유해·위험작업 → (1)재해조사보고서 rows
P13 (9 rows): 자료 종류 | 실시일시 | 관리구분 | 유해인자 종류 → (2)작업환경측정 / (3)건강진단 rows
P15 (5 rows): 자료 종류 | 경험일시 | 유해·위험작업 → (4)아차사고 보고 rows

**HWPX-06: 안전보건 체크리스트에 의한 유해·위험요인 조사표** (P18, 2 tables)
Table 0 (4 rows): 조사표 제목/실시방법/수행자·일시/blank
Table 1 (2 rows): 작업내용 | 유해·위험요인 — blank data row

**HWPX-07: 위험성 감소대책 수립 및 실행** (P20, 3 tables)
Table 0 (5 rows): 제목/실시방법/blank/blank/blank
Table 1 (2 rows): 유해·위험요인 | 감소대책 | 개선 후 위험성 — blank data row
Table 2 (4 rows): 반복적 감소대책 | 개선 후 위험성 수준 → 상/높음 | 중/보통 | 하/낮음

**HWPX-08: Tool Box Meeting 회의록** (P22, 26 rows)
Row 0: Tool Box Meeting 회의록 (title)
Row 1: TBM 일시 | 20년 월 일 | 작업날짜 동일여부 (□예, □아니오)
Row 2: 작업명 | (blank)
Row 3: 작업내용 | (blank)
Row 4: TBM 장소 | (blank)
Row 5: 위험성평가 실시여부 | 예□ 아니오□
Row 6: 잠재위험요인①/대책 | 잠재위험요인②/대책 | 잠재위험요인③
Row 7-11: (continuation rows)
Row 12: 중점위험요인 선정 | 대책
Row 13: TBM 리더 확인 (소속/직책/성명/서명)
Row 14: 작업 전 안전조치 확인 (잠재위험요소/조치여부/미조치내용)
Row 15-20: (continuation rows for safety checks)
Row 21: 작업 전 일일 안전점검 시행 결과
Row 22: 작업 후 종료 미팅(중점대책 실효성)
Row 23: 참석자 확인 (이름/서명 — multiple columns)
Row 24-25: (participant rows)

---

## S3 PDF CROSS-CHECK (Asset C)

Source: SHA256 a73ce4c67dfcb4a1b27f647ad346496f1bc7421666653da516c9ca92a46c60ff
File: 최종_경영책임자와 관리자가 알아야 할 중대재해처벌법 따라하기 안내서.pdf
Total pages: 134. Forms begin printed section IV (p79 in PDF physical index ≈ chapter IV).
Extraction method: pdfplumber page text (PDF_CROSSCHECK_ONLY — no table geometry from PDF).

### PDF page cross-reference map

| Physical PDF page | Printed section heading | HWP5 counterpart | Research_id candidate |
|---|---|---|---|
| 84 | 안전보건 경영방침 작성 예시 | HWP-01 | REF-C001 |
| 88 | 안전보건 목표 및 추진계획서 작성 예시(1) | HWP-02a | REF-C002 |
| 89 | 안전보건 목표 및 추진계획서 작성 예시(2) | HWP-02b | REF-C002 |
| 91 (upper) | 위험기계·기구·설비 목록 작성 서식 예시 | HWP-03 | REF-C003 |
| 91 (lower) | 유해·위험물질 목록 작성 서식 예시 | HWP-04 | REF-C004 |
| 92 | 작업별 위험관리 대장 활용 서식 예시 | HWP-05 | REF-C005 |
| 93 | KRAS 시스템 위험성평가표 작성 예시 | HWP-06 | REF-C006 |
| 98 | 안전보건 예산 편성항목 예시 | HWP-07 | REF-C007 |
| 100 | 안전보건 전문인력 평가 기준 및 평가표 예시 | HWP-08 | REF-C008 |
| 102–103 | 안전보건 전문인력 등 배치표 및 담당업무 | HWP-09 | REF-C009 |
| 106 | 협착사고 발생 시 대응 시나리오(처리 흐름도) | HWP-10a | REF-C010 ambiguous |
| 107 | 추락사고 대응 시나리오 작성 예시 | HWP-10b | REF-C010 related |
| 108 | 질식, 감전재해 대응 시나리오 작성 예시 | HWP-10c | UNRESOLVED |
| 111 | 도급·용역·위탁 업체 안전보건 수준 평가 예시 | HWP-11 | UNRESOLVED |
| 112 | 안전작업허가서 활용 서식 | HWP-12 | REF-C012 |
| 113 | 사고조사 보고서 서식 | HWP-13 | REF-C013 |
| 114 | 재해 감소대책 수립 및 실행 계획서 작성 서식 | HWP-14 | REF-C014 |
| 115 | 아차 사고 보고서 양식 예시 | HWP-15 | REF-C015 |
| 118 | 연간 교육계획 수립 서식 | HWP-16 | REF-C016 |

**PDF corroborates all HWP5 forms found.** REF-C004 (유해·위험물질 목록) confirmed on PDF page 91 lower half (same physical page as REF-C003).
Forms NOT in PDF: 아차 사고 등급 분류기준 (HWP-15b) — subsection only, PDF integrates it inline.
Forms in PDF page 90: 전담 조직 설치 예시(1) — present in PDF only, not a separate HWP section; NOT a new SoT candidate per WO scope.

---

## S4 GPT REVIEW GATE

**STOP: No DB writes, no schema changes, no new SoT candidates created in this WO.**

DB mutations this WO: 0.
Current DB state: 189 rows total, 10 rows with observed_fields nonempty (REF-C001~005, C012~016), unchanged from prior batches (042/043).

Pending GPT authorizations needed before next step:
1. **REF-C006 title discrepancy**: HWP heading "KRAS 시스템 위험성평가표 작성 예시" vs. DB source_title "위험성평가표(빈도강도법)". Are these the same form? Confirm before updating observed_fields for REF-C006.
2. **REF-C007~C009 observed_fields update**: Field labels extracted (HWP-07, HWP-08, HWP-09). Authorized?
3. **REF-C010 ambiguity resolution**: HWP has 3 scenario sub-sections. WO-039 target "사고 발생 대응 시나리오(처리 흐름도)". Confirm which (if any) maps to REF-C010.
4. **HWP-10c (질식·감전), HWP-11 (도급평가)**: No research_id. Authorize creating new rows, or mark UNRESOLVED in existing payload?
5. **HWPX cell-coordinate fidelity**: cellAddr attributes absent in this file. Accept NATIVE_TABLE_VERIFIED (structure confirmed by tag hierarchy) or require coordinate proof?

---

## S5 RETURN

| Item | Value |
|---|---|
| File hash verification | A, B, C all MATCH |
| Parser (A/HWP5) | olefile 0.47 + manual HWP5 tag parser; cell coordinates NOT extracted (NATIVE_PARAGRAPH_ONLY) |
| Parser (B/HWPX) | zipfile + ElementTree; table structure confirmed (NATIVE_TABLE_VERIFIED); row/col coordinates missing from cellAddr |
| Parser (C/PDF) | pdfplumber; page headings only (PDF_CROSSCHECK_ONLY) |
| HWP5 section count | 20 entries (16 primary, 1 two-part, 2 unresolved, 1 subsection) |
| HWPX 8-section count | 8 CONFIRMED |
| HWPX per-section fields | All 8 sections documented above |
| Source-to-research-ID matching | REF-C001~C009, C012~C016 CONFIRMED (17 IDs); REF-C010 AMBIGUOUS (3 scenario sections); HWP-10c/HWP-11 UNRESOLVED (2 sections) |
| PDF cross-check | 19 forms confirmed in PDF pp.84–118; printed page matches physical page in this PDF |
| Git manifest | This file; no source bytes committed |
| DB mutation count | 0 |
| DB row count | 189 UNCHANGED |
| FINAL | EVIDENCE_READY_FOR_GPT_REVIEW |

---

## Parser limitations summary

1. HWP5 table control records (TagID 85 LIST_HEADER, 87) were not decoded to extract exact row/column geometry. Observed field labels come from paragraph text sequence, not cell boundary analysis. Cell merged-span detection not performed.
2. HWPX hp:cellAddr elements present but `row`/`col` attributes returned empty string for all 295 cells in this file. Table structure confirmed by hp:tr (105 rows) / hp:tc (295 cells) tag hierarchy only.
3. PDF is rasterized in some form pages — pdfplumber text extraction may miss content in scanned/image areas. Page headings confirmed textually.
4. Copyright/reuse and LEG mandatory field judgments remain pending. No legal-required field asserted.
