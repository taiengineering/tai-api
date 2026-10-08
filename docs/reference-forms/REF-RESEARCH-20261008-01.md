# TAI REF read-only research 2026-10-08 / Evidence 01

Status: RESEARCH IN_PROGRESS, not approved for production.

## DB findings
Supabase project vwlahtguyggrhvslabax SELECT-only. document_forms 260, document_form_master 64, form_templates 11 (335 rows). Names normalized by removing spaces, separators and parentheses: 324 name groups, 11 pairs with matching normalized names; semantic duplicate determination PENDING.

| Matching name | Table 1 code | Table 2 code |
|---|---|---|
| 가스안전관리자 선임 신고서 | document_form_master:APPOINT-GAS-001 | document_forms:DOC-FAC-001 |
| 산업재해 발생 보고서 | document_form_master:LEGAL-OSHH-001 | document_forms:DOC-OSH-019 |
| 산업재해 조사표 | document_forms:DOC-OSH-003 | form_templates:OSHACT-FORM-030 |
| 소방안전관리자 선임 신고서 | document_form_master:APPOINT-FIRE-001 | document_forms:DOC-BLD-004 |
| 안전관리계획서 | document_form_master:LEGAL-CONST-001 | document_forms:DOC-CON-001 |
| 안전보건관리책임자 선임 보고서 | document_form_master:LEGAL-OSHH-005 | document_forms:DOC-OSH-062 |
| 안전보건교육 실시기록부 | document_form_master:STD-EDU-001 | document_forms:DOC-OSH-037 |
| 위험물 안전관리자 선임신고서 | document_form_master:APPOINT-HAZ-001 | document_forms:DOC-FAC-006 |
| 작업환경측정 결과보고서 | document_form_master:INSPECT-WORKEN-001 | document_forms:DOC-OSH-021 |
| 전기안전관리자 선임 신고서 | document_form_master:APPOINT-ELEC-001 | document_forms:DOC-BLD-008 |
| 통합 산업재해 현황 조사표 | document_forms:DOC-OSH-061 | form_templates:OSHACT-FORM-001 |

SQL duplicate normalization: regexp_replace(lower(trim(coalesce(name,''))),'[[:space:]·ㆍ()（）_-]+','','g'), group by normalized name, count(n)>1. Rows are not unique business documents; do not delete/merge from name alone.

## Official-source starting points
- Current law annex listing for Occupational Safety and Health Act Enforcement Rule: https://www.law.go.kr/LSW/lsInfoP.do?lsId=007364 (as crawled, annex includes HWP/HWPX/PDF; latest date/LEG alignment requires verification)
- MOEL facilities maintenance industry guidance: https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20220901127
- MOEL general machinery manufacturing: https://moel.go.kr/policy/policydata/view.do?bbs_seq=20221201570
- MOEL electrical equipment manufacturing: https://moel.go.kr/policy/policydata/view.do?bbs_seq=20221201571
- MOEL printing manufacturing: https://moel.go.kr/policy/policydata/view.do?bbs_seq=20221001013
- MOEL structural metal manufacturing (includes description of necessary forms): https://www.moel.go.kr/policy/policydata/view.do?bbs_cd=7&bbs_seq=20221000002

The pages have been reviewed as source listings; attached PDFs NOT YET READ. No licensing permission assumed. Industry-specific source expansion needs actual attachment inspection and LEG check before asserting any required form.

## Remaining gates
REF-00 baseline partially captured. REF-01 official discovery started, coverage incomplete. REF-02 only name collision signal, not semantic dedup. No production DB mutation, no runtime change, no deploy.
