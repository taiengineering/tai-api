# OBJ-REF-01 — 실무 시점별 분류와 FM 원본 근거 보완 20
Date: 2026-10-08
Status: REF-01 OPEN / practitioner-first research

## Boundaries
No comparison with legacy TAI DB. TAI AUTO workflows may inspire *scope only*; no copying text, content, layout. Sources support only directly visible facts; research-created fields/titles remain hypotheses. LEG law SoT; PRJ governance. No downloads or template production.

## Newly verified FM practitioner-facing source evidence
1. Private publicly listed actual template: '기계설비 유지관리 일지' https://www.pabburi.co.kr/양식.서식/facilities/기계설비-유지-관리-일지-문서서식/ — page explicitly describes 관리시설명, 점검일, 점검자, 상태내용, 조치·특이사항, 점검결과, 차기 일정. Page text only inspected; attached licensed form NOT downloaded; **no copying**.
2. 서울시 public building mechanical maintenance/inspection plan (2024) PDF search-indexed text https://opengov.seoul.go.kr/og/com/download.php?dname=24년기계설비유지관리및성능점검계획.pdf&dtype=basic&nid=30138403&rid=F0000102561855&uri=/files/dcdata/100217/20240112/F0000102561855.pdf — lists 기계설비별 주기/결과 and identifies equipment management No. continuity across inventory, maintenance and performance checks. PDF result snippet inspected **but full PDF was not rendered/visually inspected**; do not assert more than indexed excerpt.
3. Facility maintenance practical training course advertises '시설물 현황표, 유지관리계획서, 유지관리 점검표' as documents for training https://www.youtube.com/watch?v=X0YQ5gyrJ2o — training video description only, no video/full material analysis.
4. Current administrative standard '시설물의 안전 및 유지관리 실시 등에 관한 지침' [시행 2025-04-22], shows official 별지1 유지관리 결과보고서 https://law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000257848&chrClsCd=010201 ; official regulation, not direct evidence of FM worker routine daily log.
5. Maintainer practitioner blog describes routine responsibilities https://celtisblog.co.kr/기계설비-유지관리자-업무-범위-총정리/ ; writer self-describes practical experience, not independently audited. Secondary qualitative source only.

## Timing / work-event taxonomy for library discovery
| Event | User searches for | Suggested independent form titles (RESEARCH DRAFTS) | Practitioner workflow | Strength |
|---|---|---|---|---|
| D-1 / planning | 내일 작업, 작업 전 준비 | 익일 작업 위험·협력업체 조율표 | next-day site coordination | HYPOTHESIS |
| Shift handoff | 인수인계, 교대 | 설비 교대 인수인계서 | live state/overdue risk | HYPOTHESIS |
| Day-start | 작업 전 TBM, 투입확인 | 작업 전 위험공유 기록지 | brief, safety verification | PREVIOUS SOURCE |
| Daily rounds | 시설관리 일일일지 | 기계설비 유지관리 일지 | status, exceptions, resolution | PRIVATE PAGE OBSERVED |
| Inspection schedule | 정기/법정검사 | 설비별 유지관리 점검표 | link asset master to schedule and results | SEOUL PLAN EXCERPT |
| Fault/alert | 고장·경보 | 고장접수·시정조치 대장 | alert, fix, recheck | HYPOTHESIS |
| Contractor arrival | 외주방문/작업허가 | 외주작업 방문·작업완료 확인서 | permit/area/handover | HYPOTHESIS |
| Safety work stop | 작업중지/재개 | 작업중지·안전조치·재개 기록 | hold, authority, restart | PRIOR RESEARCH |
| Project or MOC | 설비변경 | 변경 전 안전성 검토서 | risk and authorization | PRIOR RESEARCH |
| Equipment inspection | 시설물 현황/유지관리계획 | 시설물 현황표, 유지관리계획서 | asset inventory, planning and check | TRAINING DESCRIPTION |
| Period close | 주간/월간 점검보고 | 안전/시설 이슈 집계보고서 | escalation and KPI | HYPOTHESIS |
| Regulated reporting | 유지관리 결과보고 | 법정 유지관리 결과보고서 | official annex, applies per current regulation | OFFICIAL ANNEX NAMED |
| Yearly handover | 연차/담당자 변경 | 시설관리 업무 인수인계서 | transfer evidence and open issues | HYPOTHESIS |

## Proposed independent field contract illustration — NOT source transcription
'시설관리 일일 운영일지' concept: facility reference, date/shift, equipment/area, current state, alarms, unusual observations, response owner, request/closure link, next visit date. Maintainer sample exact columns ARE NOT reproduced; this is a distinct requirements decomposition.
- Maintain asset identifier continuity across equipment registry, maintenance sheets and check results; approved field definitions after legal and privacy check.
- Never claim all suggested forms are legally mandatory or this taxonomy reflects statistically validated form popularity.
- Official annexes must be published only as current original with rights check.

## Research exit and next
Facility management source gap partially addressed (private example, Seoul plan and training course). Remaining validation: actual contractor work-completion paper sample, shift log for multi-site operations, equipment PM schedule specimens, attachments full contents and reuse license. Other 4 practitioner sectors also need primary document evidence.
REF-01 stays OPEN; REF-02+ BLOCKED. Git documentation only, production DB/storage/API/FE/deploy 0.
