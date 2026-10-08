# OBJ-REF-01 — 수집종료 선언 및 기존 조사물 품질 검증 / 23
Date: 2026-10-08
Owner request: **STOP ALL NEW SOURCE / FORM DISCOVERY; investigate and validate already-collected candidates only**.
State: REF-01 DISCOVERY_CLOSED, QUALITY_REVIEW_IN_PROGRESS (not REF-01 DONE).

## 1. Data fidelity
- Re-read Git sources: register 13 (81 research rows), practitioner report 18 (26), role expansion 19 (23), equipment/confined-space 14 (12), governance 15 (12), environmental 17 (15), maintenance/chemical 21 (10), role/event 22 (10). These are **counts of report-local research lines** and may overlap; cannot be summed into a unique-form product count.
- Register 13 is only the initial 81 lines from reports 03/08-12. It does **not** include reports 14-22 as a single synchronized master, and must not be called complete.
- No contents of original third-party HWP/ZIP/PDF attachments were verified; field and rights verification remain pending. Draft descriptions are separate from authoritatively verified source fields.
- Existing TAI DB comparison and copying TAI AUTO outputs remain OUT-OF-SCOPE.

## 2. Evaluation axes (method, not conclusions)
1. **Purpose separation**: author, who requests it, real trigger, record after completion, who reads/approves; where distinct, keep separate even with similar columns.
2. **Evidence**: ANNEX (official statute names form), PAGE_TITLE (official publicly enumerated), INSTITUTION_SAMPLE, PRIVATE_FORM_PAGE, PRIVATE_PUBLIC_CONTENTS, ROLE_AND_WMS, METHOD_ONLY, PROCESS, WORKFLOW_INFERENCE.
3. **Delivery decision**: OFFICIAL_ORIGINAL subject to current version/rights; INDEPENDENT_BLANK (original content by TAI), EXPLANATORY_REFERENCE, EXCLUDE_UNFIT.
4. **Field verification**: exact source-observed field vs independent work-derived candidate vs LEG required, kept in three separate columns in later REF-03.
5. **Copyright**: public accessibility of paid/private forms ≠ reproduction right. Commercial content never mirrored; no TAI AUTO copying.
6. **Privacy**: health, worker identity and surveillance data need minimization/access checks.
7. **Physical formats**: worklog/table→XLSX; approval/report→DOCX/HWPX; final print→PDF; technical drawings do not become bogus DOCX templates.

## 3. Existing-record sample audit (25 illustrative cases, not full set)
| QA ID | Research title | Work trigger | Recorded evidence | Evidence class | Initial disposition hypothesis | Blocking unknown |
|---|---|---|---|---|---|---|
| QA-01 | 위험성평가 기록표(빈도·강도법) | 평가 시행 | KOSHA 03 + 09 | PAGE_TITLE | 독립 XLSX | 평가 항목·산식 원본 미열람; 법령 검증 필요 |
| QA-02 | 위험성평가 기록표(3단계 판단법) | 평가 시행 | MOEL 09 | METHOD_ONLY | 독립 XLSX | 방법 존재 확인, 실제 서식 항목 미확인 |
| QA-03 | 작업 전 TBM 실시기록 | 시작 전 공유 | MOEL 12 + 18 | PROCESS | 독립 DOCX/XLSX | 특정 종이서식 의무 단정 금지 |
| QA-04 | 안전작업 허가서 | 작업 승인 | KOSHA 03 | PAGE_TITLE | 독립 DOCX | 위험별 승인 항목·권한 구분 검증 |
| QA-05 | 교육 연간계획서 | 교육 계획 | KOSHA 03 | PAGE_TITLE | 독립 XLSX | 교육 대상/시간/주기 LEG 확인 |
| QA-06 | 교육 실시일지 | 교육 실시 | KOSHA 03 | PAGE_TITLE | 독립 XLSX/DOCX | 원본 ZIP 미열람; 출석/증빙 항목은 가설 |
| QA-07 | 수급업체 안전보건 수준 평가표 | 협력업체 선정 | KOSHA 03 | PAGE_TITLE | 독립 XLSX | 평가기준과 채점 근거 확인 |
| QA-08 | 사고조사 보고서 | 사고 발생 | KOSHA 03 | PAGE_TITLE | 독립 DOCX | 대외 산업재해 조사표와 역할 분리 |
| QA-09 | 아차사고 보고서 | 아차사고 | KOSHA 03 | PAGE_TITLE | 독립 DOCX | 사고조사와 다른 간이보고 |
| QA-10 | 지게차 작업계획서 | 장비 작업 전 | KOSHA 03 + MOEL 14 | PAGE_TITLE | 독립 DOCX | 샘플 비법정 형식, 내용 원문 미열람 |
| QA-11 | 일일 안전관리일지 | 현장 순찰·일 마감 | Practitioner 18 | PRIVATE_PUBLIC_CONTENTS | 독립 XLSX | 판매자료 목차만 확인; 원본 내용 미검증 |
| QA-12 | 작업중지·재개 기록 | 위험 발생·재개 | Practitioner 18 | PRIVATE_PUBLIC_CONTENTS | 독립 DOCX | 승인자·재개 판단 책임 검증 |
| QA-13 | 설비 예방보전 일정·완료대장 | 예방보전 | Practitioner 19/21 | PRIVATE_FORM_PAGE | 독립 XLSX | 공개 서식 설명 수준; 실제 파일 미열람 |
| QA-14 | 설비 고장·수리 요청 및 완료서 | 설비 이상 | Practitioner 19/21 | PRIVATE_FORM_PAGE | 독립 DOCX/XLSX | 수리완료 vs 재가동 승인 구분 |
| QA-15 | 시설관리 일일 운영일지 | 시설 일상관리 | Practitioner 20 | PRIVATE_FORM_PAGE | 독립 XLSX | 민간 공개 양식 설명, 원본 미열람 |
| QA-16 | 외주업체 작업완료 확인서 | 외주작업 종료 | Practitioner 19/20 | WORKFLOW_INFERENCE | 독립 DOCX | 실물 서식 근거 부족 |
| QA-17 | 화학물질 입고·검수 기록부 | 입고 | Practitioner 19/21/22 | ROLE_AND_WMS | 독립 XLSX | 로트/검수 항목은 자체 제안 |
| QA-18 | 화학물질 출고·불출 관리대장 | 출고 | Practitioner 19/21/22 | PRIVATE_FORM_AND_WMS | 독립 XLSX | 요청·출고·수령 단계의 책임 구분 |
| QA-19 | 화학물질 재고실사·차이처리표 | 재고실사 | Practitioner 19/21/22 | PRIVATE_FORM_AND_WMS | 독립 XLSX | 실사와 승인·조정 단계 구분 |
| QA-20 | MSDS 수령·개정 이력대장 | 자료 수령/갱신 | KOSHA 10 + Practitioner 21 | PROCESS | 독립 XLSX | 공단 MSDS 원문 재배포 금지 |
| QA-21 | 연구실 일상 안전점검표 | 일상점검 | University 19 | INSTITUTION_SAMPLE | 독립 XLSX | 기관별 차이·저작권 및 원본 항목 확인 |
| QA-22 | 산업안전보건위원회 회의록 | 회의·의결 | Law 15 | ARTICLE | 독립 DOCX | 대상 사업장·보존과 항목 검증 |
| QA-23 | 소방시설등 자체점검 실시결과 보고서 | 법정 보고 | Law 10 | ANNEX | 공식 원본 | 별지 최신버전·배포조건 확인 |
| QA-24 | 작업환경측정 결과보고서 | 측정 결과 제출 | Law 12 | ANNEX | 공식 원본 | 전문기관 작성·제출주체 검증 |
| QA-25 | 기술도면 P&ID | 공정 기술설계 | KOSHA 08 | HTML_DOCUMENT | 일반 빈 서식 제작 제외 | 도면 원본·기술자료 안내로 별도 취급 |

## 4. Observed duplicates of research intent (NOT legacy DB comparison)
- 위험성평가 four methods: one workflow family, multiple method-specific template versions; preserve methods until field analysis.
- 교육 계획 versus 교육 실시 versus 이수 확인: different event and evidence; retain.
- 작업허가 general versus 밀폐공간 PTW: possible family/variant structure, require task-specific fields before decision.
- 화학물질 재고: inbound/issue/cycle count/quarantine/adjustment are distinct events; no forced merge into one XLSX sheet.
- 설비 고장복구 vs 재가동 승인: operational completion vs safe restart need separate authorization test.
- Public legal annexes should not be reinvented or treated as TAI-created legal originals.

## 5. Findings and blockers from **collected evidence only**
- READY_TO_INDEPENDENT_FIELD_DESIGN ≠ READY_TO_PUBLISH. A named official example supports demand for a topic, not the verified content of its fields.
- REPORT 21 confirms private vendors list actual maintenance and stock forms, but without original interior inspection we cannot claim any precise column names are verified from file.
- Reports 18/19/22 reflect job role and workflow description; a TAI draft document candidate cannot be labeled **actually used at that company**.
- 25 selected rows are a QA *sample*, not a full individualized audit of the collected universe.
- Mandatory legal status needs LEG comparison during REF-03. Until then, label legal claims REVIEW_REQUIRED.

## 6. Work execution order after collection freeze
**REF-01-QA1**: Assemble a complete single report-row ledger from reports 03–22, preserving row id and report provenance (no new sources).
**REF-01-QA2**: Independently assign objective, event, requester, signer, output, evidence strength, and original-available status for every record. Mark unsupported unknown, do not fill.
**REF-01-QA3**: Examine already-cited original files when access permits; only these already-found sources, no external discovery. Record observed field details and copyright facts; until available mark unread.
**REF-01-QA4**: Final corpus gate: each row either deliverable candidate, official original, engineering reference, ineligible, or source-unverified. Report counts without conflating overlap.
**REF-01-QA5**: Independent verify source coverage and close REF-01, then begin REF-02 canonical/classification strictly as plan.

## 7. Gate and mutations
- **New source and candidate collection FROZEN by Owner.**
- **REF-01 quality review OPEN**; NO REF-01 final closure claim.
- REF-02/03+ blocked pending object exit.
- Git documentation only, production DB writes=0, code changes=0, deploy=0, no files published.
