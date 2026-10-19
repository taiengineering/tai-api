# OBJ-REF-01 조사 증거 04 — 공단 24개 서식 대비 기존 DB 검색
Date: 2026-10-08
State: PARTIAL; REF-01 not closed. REF-02 semantic dedup still blocked.

## Read-only SQL test
Source: KOSHA official posted 24 names: https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view
DB source: TAI Supabase project vwlahtguyggrhvslabax; document_forms(260) + document_form_master(64) + form_templates(11).

Exploratory query: 22 keyword probes generated from 24 page names (some prefixes grouped). For each probe, UNION ALL 3 tables with source+code+name; SQL comparison name ILIKE '%'||keyword||'%', per-probe hit count. This is strict **substring screening**, not fuzzy matching, structural match, or semantic equivalence.

## Actual results
| Probe | Source name grouping | Matching DB |
|---|---|---|
| 1 | 안전보건경영방침 | 0 |
| 2 | 안전보건활동 목표 | 0 |
| 3 | 위험기계 | 0 |
| 4 | 유해·위험물질 목록 | 0 |
| 5 | 작업별 위험 | 0 |
| 6 | 위험성평가표 | 0 |
| 7 | 안전보건예산 | 0 |
| 8 | 안전보건 전문인력 | 0 |
| 9 | 사고 발생 대응 | 0 |
| 10 | 도급·용역 | 0 |
| 11 | 안전작업 허가서 | 0 |
| 12 | 사고조사 보고서 | 0 |
| 13 | 재해 감소대책 | 0 |
| 14 | 아차사고 | 0 |
| 15 | 연간 안전보건교육 | 0 |
| 16 | 안전보건관리담당자 선임계 | 0 |
| 17 | 관리감독자 임명장 | 0 |
| 18 | 지게차 안전작업 | 0 |
| 19 | 지게차 정기점검 | 0 |
| 20 | 중량물 취급 | 0 |
| 21 | 안전보호구 지급대장 | 0 |
| 22 | 안전보건교육일지 | 1: document_forms:DOC-OSH-006 안전보건교육일지 |

Observed: 21 probes zero literal substring match; 1 probe with one exact matching document name. This does NOT imply 21 absent business documents or 23 new templates. For example '위험성평가표' may be in existing DB as '위험성평가 실시기록' or equivalent differently named content. 24 source line items were grouped to 22 probes. Neither the 218 unverified candidate inventory nor attached government file internals were directly searched by this SQL.

## Additional reliable source
MOEL structural metal-products manufacturing safety system guide posting (2022-10-03):
https://www.moel.go.kr/policy/policydata/view.do?bbs_cd=7&bbs_seq=20221000002
Official page explicitly states it includes accident cases, hazards/countermeasures and needed forms; full annex actual contents are not yet inspected. General manufacturing conditions cannot be asserted as universal statutory obligations.

## Proposed semantic contrast columns (must be populated only from actual files)
- Original wording and owner/publication date
- Workflow family and lifecycle (plan/execute/record/review/report)
- Equipment / role / sector coverage
- Field list with table columns, signatures and frequency
- Explicit legal obligation and LEG evidence vs voluntary best practice
- Official source file type, copyright license, format conversion eligibility
- TAI record IDs and matching disposition: EXACT / VARIANT / RELATED / DISTINCT / NO_CANDIDATE / REVIEW_REQUIRED
- Canonical name, aliases, canonical SEO purpose and uniqueness
- Verification state: URL_PAGE / FILE_CONTENT / LEG / RIGHTS / OWNER_PUBLISH

## Gate
REF-01 stays OPEN. REF-02 no semantic merge. Next: inspect official attachment bytes and record field-level evidence, compare the 218 candidate workbook and all 335 DB names by intent; confirm each KOSHA item before treating it as a new document. No production DB or Git runtime modifications.
