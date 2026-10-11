# OBJ-REF-01 — Construction / Industrial hygiene / Occupational health evidence 12
Date: 2026-10-08
Status: REF-01 IN_PROGRESS / not closed
Governance: PRJ development governance; LEG legal SoT. Public statutes are source evidence needing LEG consistency check. No existing TAI DB comparison or TAI AUTO output copying. No common design before inventory + field analysis.

## Official evidence
S1 MOEL Construction TBM practical guidance (2023-03-24), attached guide PDF listed; source URL https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20230301670 . Content of attachment not inspected.
S2 MOEL (2024-04-29), documents different evidence forms acceptable for TBM education management beyond per-worker log: work log/mobile/video, source https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=16488 . Does NOT establish one mandatory TBM paper form.
S3 MOEL construction site TBM description: preparation includes risk assessment and recent incidents; execution includes work content/procedure, workers' condition and risk awareness, emergency route; source https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=14837
S4 MOEL 2024-02-22 construction-themed official publication lists safety-management guide/TBM guide/risk-assessment guide attachments https://moel.go.kr/local/daejeon/info/dataroom/view.do?bbs_seq=20240201341 . Attachment field contents NOT reviewed.
S5 Current Ministry of Government Legislation Industrial Safety and Health Act Enforcement Rule, effective 2026-08-01, art 188 explicitly references annex 82 작업환경측정 결과보고서 and annex 83 작업환경측정 결과표, report within applicable period, and art 189 mentions pre-survey/personal sampling principles https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1028065097 https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lspttninfSeq=154537
S6 Same current regulation art 209 explicitly identifies annex 84 일반건강진단 결과표, annex 85 특수·배치전·수시·임시건강진단 결과표; these are forms sent by examination institutions under prescribed circumstances https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1028064801
S7 Same current regulation art 210(4) identifies annex 86 사후관리 조치결과 보고서 in conditions described in article 210(3); report is NOT generically required from every health examination https://www.law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lspttninfSeq=154565
S8 Historic MOEL 2018 construction goal-management scheme site includes HWP '안전관리계획서' and '안전관리계획 이행 체크리스트'; applicable to particular historical campaign, not proof of universally mandatory form https://moel.go.kr/local/seoulseobu/info/dataroom/view.do?bbs_seq=20180900159

## Source-confirmed OFFICIAL annex inventory (not TAI re-created legal forms)
| Code | Exact form name | Source | Important caveat |
|---|---|---|---|
| OSH-ANNEX-082 | 작업환경측정 결과보고서 | S5 / 시행규칙 188 | official original only, current attached official annex to be obtained |
| OSH-ANNEX-083 | 작업환경측정 결과표 | S5 / 시행규칙 188,189 | measurement technical output, not generic DIY measurement spreadsheet |
| OSH-ANNEX-084 | 일반건강진단 결과표 | S6 / 시행규칙 209 | issued by health examination institution |
| OSH-ANNEX-085 | 특수·배치전·수시·임시건강진단 결과표 | S6 / 시행규칙 209 | issued by health examination institution |
| OSH-ANNEX-086 | 사후관리 조치결과 보고서 | S7 / 시행규칙 210 | conditional obligation only; sensitive personal health data |

## Proposed independent DOCUMENT WORKFLOW candidates (not legal required fields)
| Candidate ID | Draft searchable title | Usage | TAI-proposed fields (hypothesis only) | Format |
|---|---|---|---|---|
| CON-01 | 건설현장 작업 전 안전회의(TBM) 기록지 | task pre-brief and recording | 현장/공종, 일시, 위험요인, 개선조치, 참여 확인, 작업 변경사항 | XLSX/DOCX/PDF |
| CON-02 | 공종별 위험성평가 및 변경 이력표 | track changing work phases | 공종, 작업단계, 유해위험요인, 대책, 담당/재확인 | XLSX/PDF |
| CON-03 | 건설현장 유해위험 발견·시정조치 관리대장 | cross-contractor closure | 발견 일시/위치, 지적, 시정책임, 기한, 증빙, 종결확인 | XLSX/PDF |
| CON-04 | 현장 일일 안전점검 기록표 | scheduled site checks | 현장, 구역, 날짜, 기계/가설시설, 결과, 후속조치 | XLSX/PDF |
| CON-05 | 작업구역 인수인계 및 안전조치 확인서 | interface coordination | 공종/작업팀, 인계구역, 잔류위험, 방호조치, 양측 확인 | DOCX/PDF |
| IH-01 | 작업환경측정 대상 유해인자 사전 조사표 | support measurement preparation | 작업장/공정, 유해인자, 취급량, 작업시간, 대상자, 측정기관 협의 | XLSX/DOCX |
| IH-02 | 작업환경측정 결과 개선관리대장 | track reduction/controls | 측정일, 공정, 물질/인자, 결과참조, 조치, 기한, 재평가 | XLSX/PDF |
| OH-01 | 건강진단 일정·실시 관리대장 | schedule without medical diagnoses | 교육아닌 검진유형, 대상 인원, 예약/실시/미수검, 일정, 담당 | XLSX |
| OH-02 | 건강진단 사후관리 조치 추적표 | need-to-know restricted health followup | 비식별 내부키, 의사소견 조치유형, 담당, 기한, 이행상태 (minimal) | ACCESS-RESTRICTED XLSX |
| OH-03 | 근골격계 부담작업 유해요인 개선관리표 | exposure and job improvement | 작업/자세, 부담요인, 개선안, 책임자, 이행/재평가 | XLSX/PDF |

## Privacy and rights gates
- Health and exposure records can contain sensitive personal information. No sample with real worker identifiers or health diagnostics; privacy and permissions need dedicated design.
- The official report form and company-internal action register are different products. Never pretend a TAI blank workbook is an authentic medical examination output or official submission certificate.
- Field clusters above are independent hypotheses; no original PDF form content was examined. Follow full attachment acquisition, LEG check and rights check before publishing.

## Object outcome
REF-01 IN_PROGRESS; ten independently proposed candidate workstreams + five official annex references. No DB/source comparison, production DB write, API/FE change, deployment, or published file.
