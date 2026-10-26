# TAI 참고서식 REF-01 공식 출처 기반 업무·서식 조사 02
Date: 2026-10-08
Status: SOURCE DISCOVERY ONLY / NOT CLOSED
Parent: TAI-REF-FORM-PLAN-001, TAI-REF-FORM-OBJECT-PLAN-001
Authority: PRJ for dev governance, LEG for legal applicability. Neither this document nor a public example determines legal obligation.

## 1. 이번 조사에서 확인한 1차 출처 (페이지 내용 확인)
S1. KOSHA 부산광역본부, 2025-02-07 '안전보건관리체계 구축(위험성평가) 관련 활용 서식 및 안내서 등 자료 안내'
https://www.kosha.or.kr/kosha/intro/busanHeadquarters_A.do?articleNo=453942&boardNo=141&mode=view
Official posting shows downloadable: [붙임1] 중대재해처벌법 따라하기 안내서 PDF, [붙임2] 활용 서식 모음 HWP, [붙임3] 안전보건관리체계 구축 컨설팅 매뉴얼 HWP, [붙임4] 안전보건관리담당자 선임계 등 서식 HWP, [붙임5] 안전보건교육일지 ZIP (엑셀/한글).
Classification: documented official *bundles*, individual files/fields inside bundles NOT INSPECTED. Commercial redistribution/license PENDING.

S2. MOEL, 2023-02-22 '위험성평가 중심 안전보건관리체계 구축 컨설팅 안내'
https://www.moel.go.kr/local/incheonbukbu/info/policydata/view.do?bbs_seq=20230201264
Official page explicitly identifies seven workflow topics: 위험요인 파악; 위험요인 제거·대체·통제/위험성평가; 경영자 리더십; 근로자 참여; 비상조치; 도급관리; 전사적 안전보건 평가 및 개선.
Caution: linked 컨설팅 신청서 relates to historic 2023 application, not a general safety-document template to indiscriminately add. These topics are workflow categories, not prescribed paper titles.

S3. MOEL, 2025-03-31 '2024년도 위험성평가 및 안전보건관리체계 구축 우수사례집'
https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20250302091
Page explicitly lists 12 risk assessment cases (manufacturing/other 8, construction 4) and 4 safety-system cases (manufacturing 3, construction 1).
Caution: casebook != standard official form. Attachment content NOT INSPECTED.

S4. KOSHA, Risk assessment methods FAQ (public indexed PDF listing, actual PDF NOT INSPECTED in this round)
https://edu.kosha.or.kr/headquater/support/pds/filedownload/20240618161529_4648504880514822912_pdf
Indexed snippet identifies evaluation methods: frequency/severity, checklist, three-level judgment and key-factor method; method depends on workplace circumstances. A single universal '위험성평가표' format should not be prescribed until checked against LEG and methods.

S5. MOEL, 2021-08-29 안전보건관리체계 구축을 위한 가이드북 (official PDF attachment listing)
https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20210802108
Older context only; legal currency cannot be assumed.

## 2. Verified source-derived records (not automatically unique documents)
| Candidate record / group | Basis | Intended relation to TAI | Next investigation | Status |
|---|---|---|---|---|
| 안전보건관리담당자 선임계 등 공공서식 묶음 | S1 official attachment name | OFFICIAL_BUNDLE; do not pretend individual item list is known | fetch HWP, enumerate actual forms & fields, rights | VERIFIED_BUNDLE_ONLY |
| 안전보건교육일지 공공 배포 묶음 (Excel/한글) | S1 official attachment name | OFFICIAL_BUNDLE | enumerate XLSX/HWP contents, current legal fields | VERIFIED_BUNDLE_ONLY |
| 안전보건관리체계 활용서식 모음 | S1 official HWP attachment | OFFICIAL_BUNDLE | enumerate internal document names and required/recommended fields | VERIFIED_BUNDLE_ONLY |
| 위험요인 파악 기록 업무 | S2 workflow | WORKFLOW_CANDIDATE | find official sample/field evidence | WORKFLOW_ONLY |
| 위험성 감소대책 실행/확인 기록 업무 | S2 workflow | WORKFLOW_CANDIDATE | distinguish from core evaluation record | WORKFLOW_ONLY |
| 근로자 의견수렴 기록 업무 | S2 workflow | WORKFLOW_CANDIDATE | identify sample form(s), frequency and legal context | WORKFLOW_ONLY |
| 비상조치 계획·교육·훈련 기록 업무 | S2 workflow | WORKFLOW_CANDIDATE | document inventory, validate against applicable laws | WORKFLOW_ONLY |
| 도급업체 안전관리 기록 업무 | S2 workflow | WORKFLOW_CANDIDATE | subcontractor evaluation vs joint site inspection | WORKFLOW_ONLY |
| 안전보건활동 점검 및 개선 기록 업무 | S2 workflow | WORKFLOW_CANDIDATE | meeting, review, closure evidence separations | WORKFLOW_ONLY |
| 위험성평가 분야별 사례 | S3 | CASE_REFERENCE | extract only with attachment review; no reuse assumptions | VERIFIED_CASEBOOK_LISTING |
| 위험성평가 방식별 참고 서식 | S4 snippet | METHOD_VARIANT_HYPOTHESIS | actual form/method details and currency required | INDEXED_SNIPPET_ONLY |

## 3. Data semantics and SEO preclassification
- Public bundles may contain multiple subdocuments: never count bundle as one deliverable or duplicate its unknown child count.
- Canonical titles MUST follow actual work purpose (e.g. '안전보건교육일지' vs '안전보건교육 실시기록부' = alias candidate, not automatic alias).
- Preserve source attachment original name distinct from TAI public search title; formats represent original content, not promised exported files.
- Required/optional columns cannot be marked LEGAL_REQUIRED from this research. Default REQUIRED_STATUS=UNVERIFIED.
- SEO: page title/meta & download format should not advertise unverified file contents.

## 4. Method, gate and next inquiry
Method in this round: Official page text and public search snippet; attachment binaries not downloaded or inspected. No PDF interpreted. All field-level claims are PROVISIONAL.
Next: obtain attached HWP/ZIP/PDF by approved means and inspect originals, enumerate document titles and item fields, inspect licensing and current LEG, map existing 335 records and 218 candidates by ID & purpose. Need false-positive control for historical government 신청서.
REF-01: OPEN. REF-02: BLOCKED apart from 11 name-collision candidates. OBJ-REF-03+: BLOCKED.
Production DB/Storage write=0, API/FE changes=0, deploy=0.
