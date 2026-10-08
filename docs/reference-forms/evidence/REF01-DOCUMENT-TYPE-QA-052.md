# REF01-DOCUMENT-TYPE-QA-052
Date: 2026-10-08
WO: WO-REF01-DOCUMENT-TYPE-QA-CORRECTION-052
Investigator: Claude Code (evidence/collect only)
Status: EVIDENCE_READY_FOR_GPT_REVIEW
DB mutations: 0
Supersedes: REF01-DOCUMENT-TYPE-CLASSIFICATION-PROPOSAL-051.md (WO-051 proposal preserved as immutable evidence history)

---

## S0 PREFLIGHT

| Item | Value |
|---|---|
| Branch | docs/tai-reference-forms-charter-obj-20261008 |
| Branch HEAD SHA | 954c37fa |
| Supabase project | vwlahtguyggrhvslabax |
| Table | public.ref_form_research_items |
| Row count | 189 ✓ |
| observed_fields nonempty | 14 ✓ |
| canonical assigned | 0 ✓ |
| Owner/publication changes | 0 ✓ |
| WO-051 proposal | PRESERVED IMMUTABLE at REF01-DOCUMENT-TYPE-CLASSIFICATION-PROPOSAL-051.md |

---

## S1 CHANGE MATRIX — TYPE CORRECTIONS

13 type corrections applied. WO-051 proposal is preserved unmodified as evidence history.

| # | research_id | source_title | WO-051 type | WO-052 type | correction reason |
|---|---|---|---|---|---|
| 1 | EQUIP-01 | 지게차 작업계획서 | CHECKLIST | PLAN | 작업계획서 = work-execution plan; keyword "점검" matched workflow_family "고위험 장비 작업·점검", not title |
| 2 | EQUIP-02 | 트럭 적재·운반 작업계획서 | CHECKLIST | PLAN | same: 작업계획서 title dominates |
| 3 | EQUIP-03 | 고소작업대 작업계획서 | CHECKLIST | PLAN | same |
| 4 | EQUIP-04 | 이동식크레인 작업계획서 | CHECKLIST | PLAN | same |
| 5 | EQUIP-05 | 굴착기 작업계획서 | CHECKLIST | PLAN | same |
| 6 | REF-C045 | 소방시설 자체점검 실시결과 보고서 | CHECKLIST | REPORT | "실시결과 보고서" = statutory result report; 자체점검 = inspection method, not document type |
| 7 | GOV-11 | 안전보건 내부점검 결과보고서 | CHECKLIST | REPORT | "결과보고서" = result report; 내부점검 = audit method; principal output is report |
| 8 | RP-16 | 연구실 교차점검 결과·분석보고서 | CHECKLIST | REPORT | "결과·분석보고서" in title; same pattern as GOV-11/REF-C045 |
| 9 | REF-C063 | 사후관리 조치결과 보고서 별지86 | EVALUATION | REPORT | "조치결과 보고서" = statutory treatment result reporting form; not scoring/qualification assessment |
| 10 | REF-C007 | 안전보건예산 편성 서식 | FORM | PLAN | HWP heading = "안전보건 예산 편성항목 예시" (budget category example); structure is CATEGORY_LABEL + ROW_LABEL budget items, not interactive permit/application |
| 11 | REF-C009 | 안전보건 전문인력 등 배치표 및 담당업무 | FORM | REGISTER | principal output = durable registry of assigned safety staff by statutory position (안전관리자/보건관리자/안전보건관리담당자/산업보건의); REGISTER = durable inventory |
| 12 | RP-07 | 작업환경·안전 개선과제 월간관리표 | EVALUATION | REGISTER | "월간관리표" = monthly management tracking ledger; REGISTER = durable inventory; not scoring/qualification assessment |
| 13 | PRA-22-04 | 화학물질 파손·누출품 격리 및 재고조정 승인서 | REGISTER | FORM | "승인서" = single-transaction approval form; not a durable multi-entry ledger; keyword "재고" was misleading |

---

## S2 EVIDENCE PROVENANCE CORRECTIONS

### ERR-01: REF-C010 N24 node description (WO-051 misquote)

- **WO-051 text**: "N01 사고발생 → N24 관할관청 보고"
- **WO-050 source (authoritative)**: N24 = `현장 안전보건활동`
- **Corrected**: REF-C010 flow ends N24 = `현장 안전보건활동`. The "관할관청 보고" description in WO-051 S4 was an error; WO-050 table row is the verified evidence.
- **Impact on type**: none. REF-C010 remains WORKFLOW_DIAGRAM SOURCE_STRUCTURE_VERIFIED PROVISIONAL.

### ERR-02: REF-C008 observed_fields rationale (WO-051 incorrect basis)

- **WO-051 text cited**: "배점/점수 항목 confirming scoring/evaluation structure"
- **Actual WO-049 observed_fields (authoritative)**:
  - Component A_평가기준: 양호 (EVALUATION_CRITERION para 1294), 보통 (EVALUATION_CRITERION para 1296), 미흡 (EVALUATION_CRITERION para 1298)
  - Component B_평가표: 직책 (COLUMN_HEADER 1303), 성명 (COLUMN_HEADER 1304), 담당업무 (COLUMN_HEADER 1305), 평가 미흡/보통/양호 (COLUMN_HEADER 1306-1309), 안전보건관리 책임자 (ROW_LABEL 1310-1312), 관리감독자 (ROW_LABEL 1354-1355), 안전보건총괄책임자 (ROW_LABEL 1382-1383)
- **Corrected basis**: EVALUATION_CRITERION labels (양호/보통/미흡) + COLUMN_HEADER rating scale confirm evaluation structure. No "배점" or numeric "점수" fields were stored — basis corrected to EVALUATION_CRITERION + structured rating columns.
- **Impact on type**: none. REF-C008 remains EVALUATION SOURCE_STRUCTURE_VERIFIED non-provisional.

### ERR-03: Confidence tier — SOURCE_STRUCTURE_VERIFIED fidelity clarification

WO-051 applied SOURCE_STRUCTURE_VERIFIED to 15 rows (REF-C001~C016 minus REF-C006). However, HWP-derived fields were verified via `NATIVE_PARAGRAPH_ONLY` extraction (paragraph text stream), not confirmed cell geometry or table boundary analysis. REF-C010 is verified via visual image inspection (separate method).

**Fidelity sub-tags for SOURCE_STRUCTURE_VERIFIED rows:**
- REF-C001~C016 (HWP text extracted): fidelity = NATIVE_PARAGRAPH_ONLY (paragraph label text confirmed; cell boundary geometry not independently verified)
- REF-C010 (WO-050 visual extraction): fidelity = VISUAL_IMAGE_INSPECTION (24 nodes from image scan; layout confirmed but pixel-level fidelity not guaranteed)

**Implication**: NATIVE_PARAGRAPH_ONLY evidence confirms field labels exist in the document but cannot confirm exact cell geometry, row/column boundaries, or input field type (free-text vs checkbox vs dropdown). Classification types remain valid; confidence is correctly SOURCE_STRUCTURE_VERIFIED as generic source inspection.

### ERR-04: WO-051 arithmetic error (non-provisional count)

- **WO-051 text**: "The 2 non-provisional rows in SOURCE_STRUCTURE_VERIFIED are REF-C001~C005/C007~C009/C011~C016"
- **Correct count in WO-051**: 14 rows non-provisional (REF-C001~C005=5, C007=1, C008=1, C009=1, C011~C016=6)
- **WO-052 corrected count**: 12 rows non-provisional (REF-C007 and REF-C009 now PROVISIONAL after type correction)
- **Corrected statement**: 12 rows are non-provisional SOURCE_STRUCTURE_VERIFIED: REF-C001~C005, REF-C008, REF-C011~C016.

---

## S3 CORRECTED CLASSIFICATION TOTALS

| primary_type | WO-051 | WO-052 | delta |
|---|---|---|---|
| CHECKLIST | 47 | 39 | -8 |
| REGISTER | 34 | 35 | +1 |
| RECORD | 33 | 33 | 0 |
| FORM | 27 | 26 | -1 |
| PLAN | 13 | 19 | +6 |
| REPORT | 10 | 14 | +4 |
| EVALUATION | 14 | 12 | -2 |
| REFERENCE | 10 | 10 | 0 |
| WORKFLOW_DIAGRAM | 1 | 1 | 0 |
| UNDETERMINED | 0 | 0 | 0 |
| **TOTAL** | **189** | **189** | **0** |

### Confidence distribution (unchanged from WO-051)

| confidence | count |
|---|---|
| RESEARCH_REPORT_ONLY | 173 |
| SOURCE_STRUCTURE_VERIFIED | 15 |
| SOURCE_TEXT_PARTIAL | 1 |

### Provisional and review flags

| flag | WO-051 | WO-052 |
|---|---|---|
| provisional=True | 175 | 177 |
| provisional=False | 14 | 12 |
| needs_gpt_review=True | 7 | 8 |

Non-provisional rows (12): REF-C001 (FORM), REF-C002 (PLAN), REF-C003 (REGISTER), REF-C004 (REGISTER), REF-C005 (REGISTER), REF-C008 (EVALUATION), REF-C011 (EVALUATION), REF-C012 (FORM), REF-C013 (REPORT), REF-C014 (PLAN), REF-C015 (REPORT), REF-C016 (PLAN).

GPT review flags (8): P-07, P-18, REF-C006, REF-C007 (new), REF-C009 (new), REF-C010, RP-05, RP-12.

---

## S3 QUALITY GATES

| Gate | Status | Detail |
|---|---|---|
| primary_type exactly one enum value per row | PASS | 189/189 |
| No UNDETERMINED | PASS | 0 |
| Sum = 189 | PASS | 39+35+33+26+19+14+12+10+1=189 |
| WO-051 proposal preserved immutable | PASS | REF01-DOCUMENT-TYPE-CLASSIFICATION-PROPOSAL-051.md unchanged |
| EQUIP-01~05 작업계획서 → PLAN | PASS | 5 corrected |
| REF-C045 결과보고서 → REPORT | PASS | corrected |
| GOV-11 결과보고서 → REPORT | PASS | corrected |
| RP-16 결과분석보고서 → REPORT | PASS | corrected |
| REF-C063 조치결과보고서 → REPORT | PASS | corrected |
| REF-C007 FORM → PLAN | PASS | HWP heading = 예산편성항목 예시 |
| REF-C009 FORM → REGISTER | PASS | placement registry of statutory positions |
| RP-07 EVALUATION → REGISTER | PASS | 관리표 = management ledger |
| PRA-22-04 REGISTER → FORM | PASS | 승인서 = approval form |
| REF-C010 N24 corrected | PASS | 현장 안전보건활동 (not 관할관청 보고) |
| REF-C008 rationale corrected | PASS | EVALUATION_CRITERION labels, not 배점/점수 |
| Confidence fidelity NATIVE_PARAGRAPH_ONLY noted | PASS | documented in ERR-03 |
| WO-051 arithmetic 14→12 corrected | PASS | documented in ERR-04 |
| DB mutations | PASS | 0 |

---

## S4 CORRECTED 189-ROW PROPOSAL

Columns: research_id | source_title | workflow_family | disposition | obs | primary_type | confidence | prov | gpt | notes

| research_id | source_title | workflow_family | disposition | obs | primary_type | confidence | prov | gpt | notes |
|---|---|---|---|---|---|---|---|---|---|
| CHW-01 | 화학물질 입고·검수 기록표 | 화학물질 재고·창고 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| CHW-02 | 화학물질 출고·사용 불출대장 | 화학물질 재고·창고 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| CHW-03 | 화학물질 재고실사·차이처리표 | 화학물질 재고·창고 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| CHW-04 | 화학물질 이상품 격리·처리 기록 | 화학물질 재고·창고 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| CHW-05 | 화학물질 SDS 수령·버전 확인대장 | 화학물질 재고·창고 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| CITYGAS-01 | 도시가스 공급·사용시설 안전점검 기록표 | 도시가스 시설관리 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| CONF-01 | 밀폐공간 출입·작업허가서 | 밀폐공간 작업관리 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| CONF-02 | 밀폐공간 산소·유해가스 측정 기록부 | 밀폐공간 작업관리 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| CONF-03 | 밀폐공간 출입·감시 기록부 | 밀폐공간 작업관리 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| CONF-04 | 밀폐공간 비상구조 장비 점검표 | 밀폐공간 작업관리 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| DOC-01 | 안전관리 문서 개정·승인 이력대장 | 문서·기록 관리 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| DOC-02 | 안전관리 서식 배포·회수 관리대장 | 문서·기록 관리 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| DOC-03 | 안전관리 기록물 보존·폐기 일정표 | 문서·기록 관리 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| ENV-01 | 대기배출시설·방지시설 자체관리 점검표 | 환경설비 운영관리 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| ENV-02 | 폐수처리시설 점검 및 개선관리대장 | 환경설비 운영관리 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| ENV-03 | 폐기물 보관장소 일상점검표 | 환경설비 운영관리 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| ENV-04 | 환경설비 정기보전·수리 기록부 | 환경설비 운영관리 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| EQUIP-01 | 지게차 작업계획서 | 고위험 장비 작업·점검 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| EQUIP-02 | 트럭 적재·운반 작업계획서 | 고위험 장비 작업·점검 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| EQUIP-03 | 고소작업대 작업계획서 | 고위험 장비 작업·점검 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| EQUIP-04 | 이동식크레인 작업계획서 | 고위험 장비 작업·점검 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| EQUIP-05 | 굴착기 작업계획서 | 고위험 장비 작업·점검 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| EQUIP-06 | 지게차 안전점검표 | 고위험 장비 작업·점검 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| EQUIP-07 | 크레인 안전점검표 | 고위험 장비 작업·점검 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| EQUIP-08 | 컨베이어 자율점검표 | 고위험 장비 작업·점검 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-01 | 산업안전보건위원회 회의록 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-02 | 산업안전보건위원회 의결사항 이행관리대장 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-03 | 근로자 안전보건 의견수렴·회신대장 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-04 | 관리감독자 현장 안전활동 기록지 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-05 | 관리감독자 업무수행 평가표 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | EVALUATION | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-06 | 안전보건협의체 회의록(도급사업) | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-07 | 합동안전보건점검 및 시정조치 기록 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-08 | 설비·공정 변경 전 안전성 검토서 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-09 | 안전보건 시정조치(CAPA) 관리대장 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-10 | 안전보건 연간 활동계획·실적 대비표 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-11 | 안전보건 내부점검 결과보고서 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N |  |
| GOV-12 | 유해위험요인 개선조치 종결확인서 | 안전보건 운영체계 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| H2-01 | 수소설비 운전·점검 기록부 | 수소 설비관리 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| H2-02 | 수소누출 대응 훈련기록표 | 수소 설비관리 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| HAZ-01 | 위험물 저장·취급시설 관리점검표 | 위험물 시설관리 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| LAB-01 | 연구실 일상 안전점검 기록표 | 연구실 안전관리 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| LAB-02 | 연구실 정밀안전진단 개선조치 대장 | 연구실 안전관리 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| LAB-03 | 연구실안전관리위원회 회의록 | 연구실 안전관리 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| LPG-01 | LPG 사용시설 안전점검 기록표 | LPG 시설관리 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| MNT-01 | 설비예방보전 일정·완료대장 | 설비보전 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| MNT-02 | 설비 고장·수리 요청 및 완료서 | 설비보전 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| MNT-03 | 설비보전 작업일지 | 설비보전 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| MNT-04 | 교대인수인계 설비위험 현황표 | 설비보전 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| MNT-05 | 정비 중 에너지격리·복귀 확인표 | 설비보전 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| P-01 | D-1 내일 작업계획·위험조율표 | 일일운영 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| P-02 | 일일 안전관리 업무일지 | 일일운영 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| P-03 | 현장 안전순찰·지도 일지 | 일일운영 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| P-04 | TBM 실시 및 작업자 확인 기록 | 일일운영 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| P-05 | 작업종료 안전조치·인계서 | 일일운영 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| P-06 | 통합 위험작업 허가관리대장 | 허가/고위험작업 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| P-07 | 위험작업 동시작업 간섭조정표 | 허가/고위험작업 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | Y | PROVISIONAL: coordination/coordination form |
| P-08 | 중장비 반입 사전검토·승인서 | 장비/자재 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| P-09 | 장비·운전원 자격·검사 만료관리표 | 장비/자재 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| P-10 | 안전시설물 설치확인서 | 장비/자재 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| P-11 | 가설시설·비계·거푸집 점검표 | 장비/자재 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| P-12 | 가설전기·임시배선 안전점검표 | 장비/자재 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| P-13 | 위험요인 지적·조치·재점검 대장 | 시정조치 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| P-14 | 작업중지·재개 승인기록 | 시정조치 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| P-15 | 사고 최초 상황보고서 | 사고 | INDEPENDENT_CANDIDATE | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N |  |
| P-16 | 신규작업자 투입 전 서류확인표 | 인력/교육 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| P-17 | 외국인·신규작업자 이해확인 기록 | 인력/교육 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| P-18 | 협력업체 일일 작업·위험정보 공유표 | 협력업체 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | Y | PROVISIONAL |
| P-19 | 협력업체 투입 전 적격성·서류확인표 | 협력업체 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| P-20 | 산업안전보건관리비 사용계획·집행내역 | 안전관리비 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| P-21 | 산업안전보건관리비 지출증빙 체크리스트 | 안전관리비 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| P-22 | 월간 안전관리 업무캘린더 | 일정관리 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| P-23 | 현장 안전관리자 업무 인수인계서 | 인수인계 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| P-24 | 현장 핵심문서·증빙 보유현황표 | 인수인계 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| P-25 | 주간 안전관리 실적·이슈 보고서 | 보고 | INDEPENDENT_CANDIDATE | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N |  |
| P-26 | 월간 안전보건 지표·경영보고서 | 보고 | INDEPENDENT_CANDIDATE | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N |  |
| PRA-22-01 | 화학물질 입고예정·검수 대조표 | 실무업무 보완후보 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| PRA-22-02 | 화학물질 로케이션 적치·이동기록 | 실무업무 보완후보 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| PRA-22-03 | 화학물질 출고검수·인계서 | 실무업무 보완후보 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| PRA-22-04 | 화학물질 파손·누출품 격리 및 재고조정 승인서 | 실무업무 보완후보 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| PRA-22-05 | 화학물질 재고실사 차이조사 및 조정대장 | 실무업무 보완후보 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| PRA-22-06 | 설비 보전작업 완료·재가동 인계서 | 실무업무 보완후보 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| PRA-22-07 | 시설 외주업체 점검·정비 완료확인서 | 실무업무 보완후보 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| PRA-22-08 | 연구실 사고·이상 발생 초동조치·종결 기록 | 실무업무 보완후보 | INDEPENDENT_CANDIDATE | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N |  |
| PRA-22-09 | 현장 안전점검 사진·증빙 인계목록 | 실무업무 보완후보 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| PRA-22-10 | 안전관리 미종결과제 주간 인수인계표 | 실무업무 보완후보 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C001 | 안전보건경영방침 | 경영방침 | INDEPENDENT_CANDIDATE | 3 | FORM | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C002 | 안전보건활동 목표/세부 추진계획 | 경영목표/계획 | INDEPENDENT_CANDIDATE | 10 | PLAN | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C003 | 위험기계·기구·설비 목록 작성 서식 | 설비목록 | INDEPENDENT_CANDIDATE | 9 | REGISTER | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C004 | 유해·위험물질 목록 작성 서식 | 물질목록 | INDEPENDENT_CANDIDATE | 14 | REGISTER | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C005 | 작업별 위험과관리 대장 | 작업위험관리 | INDEPENDENT_CANDIDATE | 9 | REGISTER | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C006 | 위험성평가표(빈도강도법) | 위험성평가 | INDEPENDENT_CANDIDATE | 0 | EVALUATION | SOURCE_TEXT_PARTIAL | Y | Y | PROVISIONAL: KRAS example; IDENTICAL_VERIFIED not confirmed |
| REF-C007 | 안전보건예산 편성 서식 | 안전보건예산 | INDEPENDENT_CANDIDATE | 21 | PLAN | SOURCE_STRUCTURE_VERIFIED | Y | Y | fidelity:NATIVE_PARAGRAPH_ONLY; HWP heading=편성항목 예시; PLAN vs |
| REF-C008 | 안전보건 전문이력 평가 기준 및 평가표 | 전문인력 평가 | INDEPENDENT_CANDIDATE | 10 | EVALUATION | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C009 | 안전보건 전문인력 등 배치표 및 담당업무 | 인력배치 | INDEPENDENT_CANDIDATE | 8 | REGISTER | SOURCE_STRUCTURE_VERIFIED | Y | Y | fidelity:NATIVE_PARAGRAPH_ONLY; 4 ROW_LABELs = statutory pos |
| REF-C010 | 사고 발생 대응 시나리오(처리 흐름도) | 비상대응 | INDEPENDENT_CANDIDATE | 0 | WORKFLOW_DIAGRAM | SOURCE_STRUCTURE_VERIFIED | Y | Y | PROVISIONAL: 10a WORKFLOW_DIAGRAM / 10b,10c TABLE_TEMPLATE;  |
| REF-C011 | 도급·용역·위탁 업체 안전보건 수준 평가 | 도급업체 평가 | INDEPENDENT_CANDIDATE | 17 | EVALUATION | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C012 | 안전작업 허가서 | 작업허가 | INDEPENDENT_CANDIDATE | 11 | FORM | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C013 | 사고조사 보고서 서식 | 사고조사 | INDEPENDENT_CANDIDATE | 15 | REPORT | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C014 | 재해 감소대책 수립 및 실행 계획서 작성 서식 | 재해저감 계획 | INDEPENDENT_CANDIDATE | 10 | PLAN | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C015 | 아차사고 보고서 서식 | 아차사고 | INDEPENDENT_CANDIDATE | 7 | REPORT | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C016 | 연간 안전보건교육 수립 서식 | 교육계획 | INDEPENDENT_CANDIDATE | 10 | PLAN | SOURCE_STRUCTURE_VERIFIED | N | N |  |
| REF-C017 | 안전보건관리담당자 선임계 | 선임계 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C018 | 안전보건관리담담당자의 업무 | 직무정의 | INDEPENDENT_CANDIDATE | 0 | REFERENCE | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C019 | 관리감독자 임명장 | 관리감독 임명 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C020 | 지게차 안전작업 계획서 | 지게차 작업계획 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C021 | 지게차 정기점검표 | 지게차 정기점검 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C022 | 중량물 취급 작업계획서 | 중량물 작업계획 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C023 | 안전보호구 지급대장 | 보호구 지급 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C024 | 안전보건교육일지 서식(엑셀, 한글) | 교육실시 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C025 | 위험작업 허가서 | 작업허가 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C026 | 위험성평가 기록표(3단계 판단법) | 위험성평가(3단계) | INDEPENDENT_CANDIDATE | 0 | EVALUATION | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C027 | 체크리스트형 위험성평가표 | 위험성평가(체크리스트) | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C028 | 핵심요인 분석법(OPS) 위험성평가표 | 위험성평가(OPS) | INDEPENDENT_CANDIDATE | 0 | EVALUATION | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C029 | 빈도·강도법 위험성평가표 | 위험성평가(빈도강도) | INDEPENDENT_CANDIDATE | 0 | EVALUATION | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C030 | 연간 안전보건교육 계획서 | 교육계획 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C031 | 안전보건교육 실시일지 | 교육실시 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C032 | 수급업체 안전보건 수준 평가표 | 도급업체 평가 | INDEPENDENT_CANDIDATE | 0 | EVALUATION | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C033 | 도급업체 안전관리 이행점검표 | 도급업체 이행점검 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C034 | 사고 비상대응 절차서 | 비상대응 | INDEPENDENT_CANDIDATE | 0 | REFERENCE | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C035 | 사고조사 보고서 | 사고조사 | INDEPENDENT_CANDIDATE | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C036 | 아차사고 보고서 | 아차사고 | INDEPENDENT_CANDIDATE | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C037 | 종사자 위험개선 건의·조치대장 | 의견수렴/개선 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C038 | 안전보건 관계법령 의무이행 점검표 | 의무이행점검 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C039 | 사업장 화학물질 취급목록 관리대장 | 물질목록 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C040 | 제품별 MSDS 수령·개정 이력대장 | MSDS 문서이력 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C041 | 화학물질 경고표지 확인 점검표 | 화학경고표지 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C042 | 화학물질 저장구역 점검표 | 화학물질 저장 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C043 | 화학물질 누출 비상대응 훈련기록 | 화학 비상훈련 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C044 | MSDS 교육·주지 확인 기록 | MSDS 교육 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C045 | 소방시설 자체점검 실시결과 보고서 | 소방 법정 결과보고 | OFFICIAL_ORIGINAL | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N | Statutory official form (OFFICIAL_ORIGINAL); legal gate UNVE |
| REF-C046 | 소방시설 점검 후 보완조치 관리대장 | 소방 시정조치 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C047 | 비상대피훈련 실시 및 개선기록 | 대피훈련 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C048 | 전기안전관리자 선임(해임) 신고서 별지15 | 전기안전관리자 선임(별지15) | OFFICIAL_ORIGINAL | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C049 | 전기안전관리자 선임(해임) 신고서 별지16 | 전기안전관리자 선임(별지16) | OFFICIAL_ORIGINAL | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C050 | 승강기 안전관리자의 선임 또는 변경 통보서 별지24 | 승강기 안전관리자 | OFFICIAL_ORIGINAL | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C051 | 고압가스 안전관리자 선임·해임·퇴직 신고서 별지19 | 고압가스 안전관리자 | OFFICIAL_ORIGINAL | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C052 | 전기설비 일상 점검기록표 | 전기설비 일상점검 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C053 | 전기설비 정전·복전 작업기록부 | 전기 정전·복전 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C054 | 승강기 운행·관리 규정 | 승강기 운영규정 | INDEPENDENT_CANDIDATE | 0 | REFERENCE | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C055 | 승강기 비상연락망 관리표 | 승강기 비상연락망 | INDEPENDENT_CANDIDATE | 0 | REFERENCE | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C056 | 승강기 고장·조치 이력대장 | 승강기 고장 이력 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C057 | 고압가스 설비 점검관리대장 | 고압가스 설비점검 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C058 | 고압가스 누출 비상대응 점검표 | 고압가스 비상대응 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C059 | 작업환경측정 결과보고서 별지82 | 작업환경측정 법정 보고 | OFFICIAL_ORIGINAL | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C060 | 작업환경측정 결과표 별지83 | 작업환경측정 법정 결과표 | OFFICIAL_ORIGINAL | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C061 | 일반건강진단 결과표 별지84 | 일반건강진단 법정 결과표 | OFFICIAL_ORIGINAL | 0 | EVALUATION | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C062 | 특수·배치전·수시·임시건강진단 결과표 별지85 | 특수 등 건강진단 법정 결과표 | OFFICIAL_ORIGINAL | 0 | EVALUATION | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C063 | 사후관리 조치결과 보고서 별지86 | 건강진단 사후관리 법정 보고 | OFFICIAL_ORIGINAL | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N | Statutory official form (OFFICIAL_ORIGINAL); legal gate UNVE |
| REF-C064 | 건설현장 작업 전 안전회의(TBM) 기록지 | 건설 작업전회의 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C065 | 공종별 위험성평가 및 변경 이력표 | 건설 공종 위험성평가 | INDEPENDENT_CANDIDATE | 0 | EVALUATION | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C066 | 건설현장 유해위험 발견·시정조치 관리대장 | 현장 유해위험 개선관리 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C067 | 현장 일일 안전점검 기록표 | 현장 일상점검 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C068 | 작업구역 인수인계 및 안전조치 확인서 | 작업구역 인수인계 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C069 | 작업환경측정 대상 유해인자 사전 조사표 | 작업환경 측정 사전조사 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C070 | 작업환경측정 결과 개선관리대장 | 작업환경 개선관리 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C071 | 건강진단 일정·실시 관리대장 | 건강진단 일정관리 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C072 | 건강진단 사후관리 조치 추적표 | 건강진단 사후관리 추적 | NEEDS_REVIEW | 0 | EVALUATION | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C073 | 근골격계 부담작업 유해요인 개선관리표 | 근골격계 유해요인 개선 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C074 | 사업의 개요 | 제조 사업개요 | TECHNICAL_REFERENCE | 0 | REFERENCE | RESEARCH_REPORT_ONLY | Y | N | PROVISIONAL |
| REF-C075 | 설치 장소 개요 | 제조 설치장소 개요 | TECHNICAL_REFERENCE | 0 | REFERENCE | RESEARCH_REPORT_ONLY | Y | N | PROVISIONAL |
| REF-C076 | 주요 부속설비 구조·배치도 | 기술 구조·배치도 | TECHNICAL_REFERENCE | 0 | REFERENCE | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C077 | 경보·방호장치 자료 | 경보·방호장치 증빙 | TECHNICAL_REFERENCE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C078 | 공정 설명서 및 PFD | 공정 설명·PFD | TECHNICAL_REFERENCE | 0 | REFERENCE | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C079 | P&ID | P&ID 도면 | TECHNICAL_REFERENCE | 0 | REFERENCE | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C080 | 폭발위험장소 구분도 | 폭발위험장소 구분도 | TECHNICAL_REFERENCE | 0 | REFERENCE | RESEARCH_REPORT_ONLY | Y | N |  |
| REF-C081 | 비상 시 조치계획 | 비상대응 계획 | TECHNICAL_REFERENCE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-01 | 설비 예방보전 일정·실적표 | 제조설비보전 | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-02 | 설비 고장·정비 작업요청서 | 제조설비보전 | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-03 | 정비작업 위험확인·에너지격리 확인표 | 제조설비보전 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-04 | 생산·보전 교대 인수인계 기록부 | 제조설비보전 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-05 | 설비 정지·재가동 승인기록 | 제조설비보전 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | Y | PROVISIONAL |
| RP-06 | 공정 변경 전 EHS 영향검토서 | 제조EHS | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-07 | 작업환경·안전 개선과제 월간관리표 | 제조EHS | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-08 | 시설·설비별 법정검사 일정관리표 | 건물FM | INDEPENDENT_CANDIDATE | 0 | PLAN | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-09 | 시설관리 일일 운영일지 | 건물FM | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-10 | 외주 정비업체 작업방문·완료확인서 | 건물FM | INDEPENDENT_CANDIDATE | 0 | FORM | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-11 | 설비 하자·수리요청 및 처리대장 | 건물FM | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-12 | 시설 비상경보 발생·대응이력부 | 건물FM | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | Y | PROVISIONAL |
| RP-13 | 연구실 일상 안전점검표 | 연구실 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-14 | 연구실 옥외저장소 점검일지 | 연구실 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-15 | 연구실 등록·변경·폐쇄 신청 확인표 | 연구실 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-16 | 연구실 교차점검 결과·분석보고서 | 연구실 | INDEPENDENT_CANDIDATE | 0 | REPORT | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-17 | 연구실 안전교육 이수·보완 확인표 | 연구실 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-18 | 화학물질 입고 검수기록부 | 화학물류 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-19 | 화학물질 출고·불출 관리대장 | 화학물류 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-20 | 화학물질 재고 실사·차이 조정표 | 화학물류 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-21 | 화학물질 보관구역 이상·격리 관리대장 | 화학물류 | INDEPENDENT_CANDIDATE | 0 | REGISTER | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-22 | 유효기간·용기상태 점검표 | 화학물류 | INDEPENDENT_CANDIDATE | 0 | CHECKLIST | RESEARCH_REPORT_ONLY | Y | N |  |
| RP-23 | 화학폐기물 불출·인계 확인기록 | 화학물류 | INDEPENDENT_CANDIDATE | 0 | RECORD | RESEARCH_REPORT_ONLY | Y | N |  |
---

## S5 RECEIPT SUMMARY

| Item | Value |
|---|---|
| Branch | docs/tai-reference-forms-charter-obj-20261008 |
| Evidence file | docs/reference-forms/evidence/REF01-DOCUMENT-TYPE-QA-052.md |
| Changed IDs (type) | 13 |
| Changed IDs (rationale/notes only) | 4 (REF-C007, REF-C008, REF-C009, REF-C010) |
| Total classified | 189 / 189 |
| UNDETERMINED | 0 |
| provisional (corrected) | 177 |
| needs_gpt_review (corrected) | 8 |
| DB mutations | 0 |
| WO-051 proposal | PRESERVED IMMUTABLE |
| FINAL | EVIDENCE_READY_FOR_GPT_REVIEW |

STOP — awaiting GPT independent review before any Supabase write or canonical ID assignment.
