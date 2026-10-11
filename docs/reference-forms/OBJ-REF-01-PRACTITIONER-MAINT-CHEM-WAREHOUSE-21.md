# OBJ-REF-01 — 제조업 설비보전·화학물질 창고 실무원본 공개목차 조사 21
Date 2026-10-08 / REF-01 IN_PROGRESS / reverse practitioner research

## Method
Search of publicly accessible **template landing pages** and industry solution/role descriptions. This does NOT mean actual paid/commercial HWP/XLSX bytes inspected or usage frequency independently audited. Commercial source wording/layout **must not be copied into any TAI forms**. TAI independent field clusters are later design hypotheses, not source transcriptions. No current TAI DB comparison or AUTO duplication.

## Actual document titles and visible field/functional examples
| Source | Exact publicly posted document or feature | What source explicitly states | Evidence status | URL |
|---|---|---|---|---|
| PABBURI/시설 | 설비 유지 보전 업무 일지 양식문서 | maintenance work log, work date/actor/department, facility/location, work type | PRIVATE_FORM_LANDING_VISIBLE; HWP UNREAD | https://www.pabburi.co.kr/양식.서식/facilities/설비-유지-보전-업무-일지-양식문서/ |
| PABBURI/시설 | 유지보수 점검 일지 | inspection date/person/equipment/site, equipment status and corrective entries | PRIVATE_FORM_LANDING_VISIBLE; HWP UNREAD | https://www.pabburi.co.kr/양식.서식/facilities/유지보수-점검-일지/ |
| Finite Field | 설비 점검 일지 템플릿 | webpage says 9-sheet Excel with equipment master, inspection, maintenance plans, repair history, parts replacement | PRIVATE_WORKBOOK_LANDING_VISIBLE; XLSX UNREAD | https://finitefield.org/ko/excel-templates/asset-operations/equipment-inspection-log/ |
| PABBURI/물류 | 유해화학물질 재고관리 및 현황 기록장부 | webpage names chemical identifier, location, safety responsibility and related stock/flow forms | PRIVATE_FORM_LANDING_VISIBLE; HWP UNREAD | https://www.pabburi.co.kr/양식.서식/distribution/유해화학물질-재고관리-및-현황-기록장부/ |
| PABBURI/물류 | 창고 입출고 관리대장 | webpage names warehouse, manager, log type, item/specification and quantity reconciliation practice | PRIVATE_FORM_LANDING_VISIBLE; HWP UNREAD | https://www.pabburi.co.kr/양식.서식/distribution/창고-입출고-관리대장/ |
| PABBURI/물류 | 창고보관 수불대장 | listing describes item ledger, balance, stock changes, location and receipts/issues in related form titles | PRIVATE_FORM_LANDING_VISIBLE; HWP UNREAD | https://www.pabburi.co.kr/양식.서식/distribution/창고보관-수불대장/ |
| Yesform blog | 재고관리 엑셀 대장 | announces inventory Excel management/downloads, not a chemical-specific physical form; shows spreadsheet demand | SECONDARY_PROVIDER_CASE | https://blog.yesform.com/entry/엑셀-재고관리-대장-업데이트-서식-프로그램-구글-스프레드시트로-스마트하게-재고관리-업무-진해하세요/ |
| Solbitech | 설비·시설관리 시스템 | solution vendor describes checks/maintenance/repair/fault/equipment history digitization | SOLUTION_PROVIDER_DESCRIBED_WORKFLOW; NO BLANK FILE | https://solbitech.com/ |
| 철도산업정보센터 | 설비보전기사 수행직무 | day-to-day + periodic diagnostic, breakdown repairs, maintenance and operation | ROLE_DEFINITION; NOT FORM EVIDENCE | https://www.kric.go.kr/jsp/board/portal/sub04/lic/certifiDetail.jsp?board_seq=92 |

## Practical document contract hypotheses, not copied from commercial examples
| Candidate ID | Document (draft canonical) | Event trigger | Workflow output | Field themes independently devised | Status |
|---|---|---|---|---|---|
| MNT-01 | 설비예방보전 일정·완료대장 | scheduled PM | scheduled versus closed work | 설비식별자, 예정일, 실적일, 이상·재점검, 다음계획 | RESEARCH_DRAFT |
| MNT-02 | 설비 고장·수리 요청 및 완료서 | breakdown | request→assignment→fix→verification | 설비ID, 신고, 영향, 긴급도, 조치, 정상화 확인 | RESEARCH_DRAFT |
| MNT-03 | 설비보전 작업일지 | work completed | shift record | 설비ID, 시간, 담당, 작업범위, 결과, 잔여위험 | RESEARCH_DRAFT |
| MNT-04 | 교대인수인계 설비위험 현황표 | shift change | open issues transferred | 가동·중지상태, 경보, 미조치, 담당, 인수확인 | RESEARCH_DRAFT |
| MNT-05 | 정비 중 에너지격리·복귀 확인표 | maintenance/PTW | isolation and reactivation | 위험에너지원, 잠금, 확인, 해제, 승인 | RESEARCH_DRAFT |
| CHW-01 | 화학물질 입고·검수 기록표 | goods receipt | acceptance and exceptions | 제품/로트/수량, 용기, 문서버전 확인, 합격/격리 | RESEARCH_DRAFT |
| CHW-02 | 화학물질 출고·사용 불출대장 | dispense | stock outflow and recipient | 제품/로트, 장소, 수량, 요청부서, 처리자 | RESEARCH_DRAFT |
| CHW-03 | 화학물질 재고실사·차이처리표 | cycle count | counted versus ledger | 위치·품목·로트, 장부/실사량, 차이원인, 승인 | RESEARCH_DRAFT |
| CHW-04 | 화학물질 이상품 격리·처리 기록 | damaged/leaking item | quarantine and disposition | 용기/로트, 격리사유, 위험통제, 담당, 최종처분 | RESEARCH_DRAFT |
| CHW-05 | 화학물질 SDS 수령·버전 확인대장 | document revision | supplier doc traceability | 제조사/제품, 수령일, 개정버전, 현장배포, 확인 | RESEARCH_DRAFT |

## Findings and qualification
- Manufacturing maintenance: publicly visible **named forms** (maintenance work journal, inspection log) and linked inventory-repair planning workbook support more than job-duty inference from research 19.
- Chemical warehousing: public HWP listings directly name chemicals stock records; other storage and issues/receipts ledger listings are generic warehouse forms. Chemical-specific *lot-level fields* are a TAI inference and **not certified by those original document landing pages**.
- No source download, spreadsheet formulas, HWP field-by-field parsing, license examination, SEO demand measurement, or direct practitioner interview performed.
- The ten drafted lines overlap topic families in research 19, and **are not ten new unique forms added to total**.
- Avoid high-confidence claims about legal mandatory layouts; TAI forms independently authored only after field and legal review.
- To finish REF-01, need additional truly primary practitioner in-use samples, real-world role tests, content-level field analysis, and legal/rights checks.
- Git docs only, prod database/storage/code/deploy 0; REF-02+ blocked.
