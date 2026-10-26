# OBJ-REF-01 — 역방향 실무자 중심 서식 조사 18
Date: 2026-10-08
Status: REF-01 / REVERSE_RESEARCH_IN_PROGRESS
Purpose: official/law-first source discovery complemented by **practitioner activity → work event → evidence document** starting point. Not a replacement for LEG law SoT.

## Method and evidence hierarchy
1. **PRACTITIONER_CONTENTS**: public headings of commercially sold construction-site safety-manager practical handoff guide, NOT private book contents.
2. **JOB_POST**: publicly shown job ad that enumerates two tiers ('법적 필수 서류', '현장 운영 서류'). Employer's label '필수' is **not independently verified as statutory requirement**.
3. **MOEL/OFFICIAL_REVIEW**: cross-check for some workflows; historically dated official rules are NOT automatically current.
4. **WORKFLOW_INFERENCE**: derived missing documents to validate with actual practitioners; do not claim field usage observed.

### Source directory
| Code | What was actually observed | URL | Caveat |
|---|---|---|---|
| PRACTITIONER_CONTENTS | 민간 안전관리자 실무 인수인계 전자책의 공개 목차 및 부록 | https://kmong.com/gig/808817 | Commercial description only. No paid book opened, downloaded, or copied. |
| JOB_POST | 안전관리자 모집공고의 공개 업무·현장서류 분류 | https://www.saramin.co.kr/api/jobs/job/content?rec_idx=54361387 | Employer listing, not representative survey nor proof of legal requiredness. |
| MOEL | 고용노동부 2024 TBM 실적 관리 방식 안내 | https://www.moel.go.kr/news/enews/report/enewsView.do?news_seq=16488 | Cross-check, not primary source of document popularity. |
| OFFICIAL_REVIEW | 건설업 산업안전보건관리비 계상 및 사용기준(법령정보센터 과거 고시) | https://law.go.kr/admRulLsInfoP.do?admRulSeq=2100000247238 | Historical version; current application and expenses require LEG confirmation. |
| WORKFLOW_INFERENCE | AI analysis of gaps between work events and evidence handoffs | N/A | Proposed, not observed field document. |

## 26 practitioner-first research candidates
Rows are proposed **TAI original blank reference docs**, not verified frequency, official original names, or final unique deliverables. Fields are TAI-designed hypotheses, not copied from a private source.

| No | Workstream | Draft document | Trigger | Draft field families | Evidence | Priority hypothesis |
|---|---|---|---|---|---|---|
| P-01 | 일일운영 | D-1 내일 작업계획·위험조율표 | 작업 전날 | 공종, 협력업체, 예정작업, 인터페이스 위험, 승인/전달 | PRACTITIONER_CONTENTS | HIGH |
| P-02 | 일일운영 | 일일 안전관리 업무일지 | 매일 | 순찰, 교육, 지적사항, 회의, 조치, 보고 | PRACTITIONER_CONTENTS + JOB_POST | HIGH |
| P-03 | 일일운영 | 현장 안전순찰·지도 일지 | 매일/수시 | 순찰구역, 작업상태, 지적, 지도, 조치 | JOB_POST | HIGH |
| P-04 | 일일운영 | TBM 실시 및 작업자 확인 기록 | 작업 전 | 작업, 위험, 조치, 참여확인 | JOB_POST + MOEL | HIGH |
| P-05 | 일일운영 | 작업종료 안전조치·인계서 | 작업 종료 | 잔류위험, 현장정리, 인계자, 후속작업 | PRACTITIONER_CONTENTS | MED |
| P-06 | 허가/고위험작업 | 통합 위험작업 허가관리대장 | 작업 전/종료 | 작업구분, 허가번호, 장소, 승인, 회수/종료 | PRACTITIONER_CONTENTS + JOB_POST | HIGH |
| P-07 | 허가/고위험작업 | 위험작업 동시작업 간섭조정표 | 작업 전 | 작업구역, 팀, 동시위험, 협의결정, 통제 | WORKFLOW_INFERENCE | MED |
| P-08 | 장비/자재 | 중장비 반입 사전검토·승인서 | 반입 시 | 장비, 업체, 자격증빙, 검사, 현장승인 | PRACTITIONER_CONTENTS | HIGH |
| P-09 | 장비/자재 | 장비·운전원 자격·검사 만료관리표 | 월간/투입 | 장비, 운전자, 자격/검사, 만료예정, 조치 | WORKFLOW_INFERENCE | MED |
| P-10 | 장비/자재 | 안전시설물 설치확인서 | 설치·변경 | 설치위치, 규격, 검사, 담당, 사진증거 | JOB_POST | HIGH |
| P-11 | 장비/자재 | 가설시설·비계·거푸집 점검표 | 투입/정기 | 가설물, 위치, 안전상태, 부적합, 조치 | JOB_POST | HIGH |
| P-12 | 장비/자재 | 가설전기·임시배선 안전점검표 | 투입/정기 | 배전/누전, 접지, 노출위험, 점검, 조치 | JOB_POST | HIGH |
| P-13 | 시정조치 | 위험요인 지적·조치·재점검 대장 | 발견~종결 | 지적, 증거, 담당, 기한, 재확인, 종결 | PRACTITIONER_CONTENTS | HIGH |
| P-14 | 시정조치 | 작업중지·재개 승인기록 | 위험 발생 | 중지사유, 조치, 판단, 재개승인 | PRACTITIONER_CONTENTS | HIGH |
| P-15 | 사고 | 사고 최초 상황보고서 | 사고 직후 | 사고개요, 현장조치, 연락, 현재상태 | PRACTITIONER_CONTENTS | HIGH |
| P-16 | 인력/교육 | 신규작업자 투입 전 서류확인표 | 신규투입 | 소속, 교육, 자격, 보호구, 투입가능 확인 | PRACTITIONER_CONTENTS | HIGH |
| P-17 | 인력/교육 | 외국인·신규작업자 이해확인 기록 | 교육후/투입 | 언어, 핵심위험, 이해확인, 보완지도 | PRACTITIONER_CONTENTS | MED |
| P-18 | 협력업체 | 협력업체 일일 작업·위험정보 공유표 | 매일 | 회사, 작업, 동시작업, 위험, 조정 | PRACTITIONER_CONTENTS | HIGH |
| P-19 | 협력업체 | 협력업체 투입 전 적격성·서류확인표 | 계약/투입 | 업체, 작업범위, 서류, 평가, 후속조치 | PRACTITIONER_CONTENTS | HIGH |
| P-20 | 안전관리비 | 산업안전보건관리비 사용계획·집행내역 | 계획/월간 | 예산구분, 집행일, 항목, 금액, 증빙, 잔액 | PRACTITIONER_CONTENTS + OFFICIAL_REVIEW | HIGH |
| P-21 | 안전관리비 | 산업안전보건관리비 지출증빙 체크리스트 | 지출전/후 | 지출목적, 근거, 품목, 세금계산서, 지급증빙 | PRACTITIONER_CONTENTS | HIGH |
| P-22 | 일정관리 | 월간 안전관리 업무캘린더 | 월간 | 교육, 점검, 검사, 회의, 만료기한, 완료 | PRACTITIONER_CONTENTS | HIGH |
| P-23 | 인수인계 | 현장 안전관리자 업무 인수인계서 | 담당자 변경 | 진행중 위험, 검사, 미조치, 연락체계, 문서 | PRACTITIONER_CONTENTS | HIGH |
| P-24 | 인수인계 | 현장 핵심문서·증빙 보유현황표 | 신규/감사 | 문서명, 보관위치, 최신일, 누락/개선 | PRACTITIONER_CONTENTS | MED |
| P-25 | 보고 | 주간 안전관리 실적·이슈 보고서 | 주간 | 실시현황, 사고/지적, 지연과제, 다음주 계획 | WORKFLOW_INFERENCE | MED |
| P-26 | 보고 | 월간 안전보건 지표·경영보고서 | 월간 | 교육/점검/조치 지표, 미완료 위험, 의사결정 | WORKFLOW_INFERENCE | MED |

## What reverse research changes (gaps from compliance-first inventory)
- The field practitioner navigates **D-1 → Prestart/TBM → Active patrol → STOP/REPAIR → End-of-shift handoff**, not a statute list.
- Distinct **routine artifacts**: daily diary, safety patrol diary, inbound equipment approval, worker-onboarding completeness, safety-installation confirmation, evidence for safety-budget spending, rolling deadlines calendar, handover folder.
- Each needs a specific event trigger and closure state, not a generic undifferentiated daily safety checklist.
- Certain drafts intersect source names from 03–17; this is an **independent future deliverable-planning problem**, not legacy TAI DB matching. This report does NOT append 26 new unique forms to the total.
- Priority HIGH/MED are reasoned heuristics from practitioner-described workflow prominence; **no download counts, analytics or survey of actual practitioners** supports numerical popularity/rankings.
- Regulator's allowance of TBM work log/mobile/video means 'TBM paper form mandatory' claims are prohibited.

## Additional practitioner segments to research next
- Manufacturing EHS/safety leads: maintenance shutdown/PTW/LOTO, chemical receipt & storage, shift turnover, incident closure, facilities preventive maintenance.
- Building/FM operation: contract service visit log, facility statutory inspection schedule, corrective/repair requests, vendor evidence chain.
- Research lab safety staff: pre-experiment risk approval, instrument status, chemical inventory receiving, lab entry training.
- Chemical material warehouse staff: purchasing approval, inbound lot/product checks, SDS version, issuance/returns, stock discrepancy and disposal evidence.
These are **research hypotheses**, not described by the construction-focused practitioner source.

## Governance
No comparison with old TAI DB; TAI AUTO document **workflows included** but text/layout not copied. No paid content copied. No legal-required claim based on job ad. LEG review before compliance labeling. No production DB changes, code changes, design work, downloadable templates, or deployment.
REF-01 remains OPEN; REF-02 blocked until source/fields/coverage adequate.
