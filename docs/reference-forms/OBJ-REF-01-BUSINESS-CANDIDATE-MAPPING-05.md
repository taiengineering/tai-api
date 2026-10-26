# OBJ-REF-01 source-to-catalog business candidate matching 05
Date 2026-10-08 / Status PRELIMINARY / No confirmed semantic merge

## Executive correction
Previous 22 literal substring checks found only '안전보건교육일지' exact name (DOC-OSH-006). **That was not a no-coverage verdict.** Wider SELECT-only thematic search of current public.document_forms finds multiple business-related existing entries with different titles. Do NOT interpret 21 zero literal matches as 21 new document families.

## Evidence scope
- DB Supabase project vwlahtguyggrhvslabax; SELECT-only existing document_forms.
- Query: SELECT doc_id,doc_name FROM public.document_forms WHERE doc_name ~ '위험|지게차|도급|사고|교육|관리자|보호구|허가|예산|점검|중량' ORDER BY doc_name LIMIT 100.
- This yielded a limited sample (LIMIT 100): **not an exhaustive comparison**, not matching by fields. No claim that every corresponding catalog entry was retrieved.
- Primary source HTML lists 24 form names: https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view ; verified web search indexed page.
- Attempt to retrieve official webpage directly from execution environment was blocked by DNS resolution. HWP/HWPX/ZIP attachment bytes not inspected; no field-level or reproduction-rights approval.
- A second official KOSHA region posted matching 2024 list: https://oshri.kosha.or.kr/kosha/intro/easternGyeongnamBranch_A.do?article.offset=20&articleLimit=10&articleNo=449234&mode=view ; not additional distinct 24 forms.

## Source form -> existing DB *candidate* mapping
| KOSHA listed form | Existing TAI IDs/names (read-only evidence) | Initial relationship hypothesis | Actual field verification |
|---|---|---|---|
| 위험성평가표(빈도강도법) | DOC-OSH-002 위험성평가서; DOC-OSH-041 위험성평가 실시결과서 | METHOD_VARIANT vs RESULT | PENDING |
| 재해 감소대책 수립 및 실행 계획서 | DOC-OSH-042 위험성평가 개선조치계획서 | RELATED_WORKFLOW / possible overlap | PENDING |
| 도급·용역·위탁 업체 안전보건 수준 평가 | DOC-SERA-007 도급용역위탁 안전보건 확보기록; DOC-OSH-040 도급사업 안전보건조치 이행기록; DOC-CON-010 도급사업 안전보건조치계획 | RELATED_WORKFLOW / evaluation distinct until evidence | PENDING |
| 안전작업 허가서 | DOC-OSH-013 작업허가서(일반); DOC-OSH-049 작업허가서(위험작업); DOC-OSH-047 밀폐공간 작업허가서 | FAMILY / scope variants | PENDING |
| 사고조사 보고서 서식 | DOC-OSH-018 사고보고서; DOC-OSH-003 산업재해 조사표 | RELATED / external submission distinguished | PENDING |
| 안전보건예산 편성 서식 | DOC-SERA-004 재해예방 인력예산 편성기록 | RELATED / potentially distinct purpose | PENDING |
| 안전보건교육일지 서식 | DOC-OSH-006 안전보건교육일지; DOC-OSH-037 안전보건교육 실시기록부; DOC-SERA-006 안전보건교육 실시 결과기록 | EXACT_NAME_CANDIDATE DOC-OSH-006; others RELATED | PENDING |
| 안전보호구 지급대장 | DOC-OSH-045 보호구 지급대장; DOC-OSH-046 보호구 착용 점검기록 | LIKELY_ALIAS candidate first; second DISTINCT inspection activity | PENDING |
| 위험기계·기구·설비 목록 | DOC-OSH-059 기계설비 점검기록부; DOC-CON-013 장비점검기록부 | EQUIPMENT INVENTORY vs INSPECTION (likely DISTINCT) | PENDING |
| 유해·위험물질 목록 작성 서식 | DOC-OSH-044 물질안전보건자료 교육기록; DOC-CHEM-003 유해화학물질 취급시설 자체점검 기록 | RELATED_DOMAIN but DIFFERENT_TASK | PENDING |
| 아차사고 보고서 | DOC-OSH-018 사고보고서 | RELATED, incident type may differ | PENDING |
| 연간 안전보건교육 수립 서식 | DOC-OSH-006 안전보건교육일지; DOC-OSH-037 안전보건교육 실시기록부 | PLAN vs EXECUTION distinct | PENDING |

## Explicitly no mapping established
- 지게차 안전작업 계획서, 지게차 정기점검표, 중량물 취급 작업계획서: not found in inspected name-filter sample; must search full 335, 218 candidates by synonyms and actual contents before claiming absent.
- 안전보건경영방침, 안전보건활동 목표, 관리감독자 임명장, 선임계: investigation pending.
- Other KOSHA names not listed above require complete coverage spreadsheet in later WO.

## Field-level classification contract to apply on original files
For each original form: exact name, attachment+page/section, objective, lifecycle (plan/evaluate/approve/execute/log/close/report), actor, scope, repeating columns, signature/approval, statutory vs recommended under LEG, source rights, file format/version, canonical SEO name and user aliases, semantic match verdict and rationale.

## Objective statuses
REF-01 OPEN (official source enumeration and preliminary links). REF-02 BLOCKED for final dedup (only hypotheses). REF-03 legal/rights verification BLOCKED. Production mutations: DB=0, API/FE=0, publish=0.
