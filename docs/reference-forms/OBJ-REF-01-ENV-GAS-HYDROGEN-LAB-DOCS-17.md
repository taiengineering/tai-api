# OBJ-REF-01 — 환경·위험물/가스·수소·연구실·문서관리 연구 17
Date: 2026-10-08
Status: REF-01 IN_PROGRESS, NOT CLOSED
Policy: Independent reference-form library, no original TAI AUTO copying, no legacy TAI DB comparison. LEG legal SoT and PRJ change governance. All source URLs official law.go.kr unless otherwise noted.

## A. Verified legal names / operational requirements from HTML legal text
| Domain | Authority | Officially named form/record | Link | Status |
|---|---|---|---|---|
| 환경-폐수 | 물환경보전법 시행규칙 제49조, 시행 2026-06-22 | 폐수배출시설 및 수질오염방지시설 운영일지: 별지 제18호 / 폐수무방류시설 제19호 / 특정처리사업자 제20호 / 폐수처리업 제21호; article says daily record and generally 1-year retention, 3 years for no-discharge exceptions | https://law.go.kr/LSW/lumLsLinkPop.do?chrClsCd=010202&lspttninfSeq=60717 | ARTICLE_VERIFIED; annex content unread |
| 환경-폐기물 | 폐기물관리법 시행규칙 제58조, 시행 2026-06-22 | 음식물류 폐기물 관리대장 별지 제35호의2; 사업장폐기물 관리대장 별지 제36호; 자체 재활용 관리대장 별지 제36호의2 | https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1020179883 | ARTICLE_VERIFIED; annex content unread |
| 위험물 | 위험물안전관리법 시행규칙 제53조, 시행 2026-07-01 | 위험물안전관리자 선임신고서 별지 제32호 | https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lspttninfSeq=79639 | ARTICLE_VERIFIED; annex content unread |
| LPG | 액화석유가스의 안전관리 및 사업법 시행규칙 제49조, 시행 2026-01-02 | 안전관리자 선임·해임·퇴직 신고서 별지 제35호 | https://www.law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1030034441 | ARTICLE_VERIFIED; annex content unread |
| 도시가스 | 도시가스사업법 시행규칙 제37조, 시행 2026-09-18 | 안전관리규정 심사신청서 별지 제31호; actual 안전관리규정 separately attached | https://law.go.kr/LSW/lsLinkCommonInfo.do?chrClsCd=010202&lspttninfSeq=58201 | ARTICLE_VERIFIED; annex content unread |
| 수소 | 수소경제 육성 및 수소 안전관리에 관한 법률 시행규칙, 시행 2026-09-18 and 수소 안전관리기준 통합고시 시행 2026-04-14 | 수소제조/저장설비 definition and safety-management-rule criteria: specific standalone blank annex list NOT yet confirmed | https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1021606427 and https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulId=83253&efYd=0 | PROCESS_VERIFIED; individual forms unverified |
| 연구실 | 연구실 안전환경 조성에 관한 법률 제11조·제16조, 시행 2026-05-20 | 연구실안전관리위원회 운영, 점검/진단결과 공표와 일정 조건의 중대결함 보고; exact prescribed blank document names not verified | https://www.law.go.kr/lsLinkCommonInfo.do?ancYnChk=&chrClsCd=&lsJoLnkSeq=1023165707 and https://www.law.go.kr/LSW/lsLinkCommonInfo.do?lsJoLnkSeq=1033223857 | PROCESS_VERIFIED; individual forms unverified |

NOTE: These URLs identify current provisions, **not inspected official HWP/HWPX annex contents**. Applicability of regulation and which exact annex/period applies must be independently checked against LEG. Annex text, rights/redistribution status = PENDING.

## B. Independent TAI reference-document research candidates, not statutory originals
| Code | Proposed title | Purpose | TAI-proposed fields / non-mandatory draft | Format hypothesis |
|---|---|---|---|---|
| ENV-01 | 대기배출시설·방지시설 자체관리 점검표 | Routine management alongside official environmental operating records | 설비, 일시, 가동/이상 여부, 조치책임, 증빙 | XLSX/PDF |
| ENV-02 | 폐수처리시설 점검 및 개선관리대장 | Corrective work tracking separate from official operating diary | 공정, 점검일, 이상, 개선, 완료확인 | XLSX/PDF |
| ENV-03 | 폐기물 보관장소 일상점검표 | Waste storage housekeeping | 보관위치, 폐기물종류, 표시, 누출/혼합, 조치 | XLSX/PDF |
| ENV-04 | 환경설비 정기보전·수리 기록부 | Repair history | 설비, 정비원인, 작업, 중지시간, 검증 | XLSX/PDF |
| HAZ-01 | 위험물 저장·취급시설 관리점검표 | In-house storage and operating checks | 장소, 물질군, 저장조건, 표시·방호, 문제·조치 | XLSX/PDF |
| LPG-01 | LPG 사용시설 안전점검 기록표 | Routine fuel-system checks | 설비, 날짜, 누출점검, 밸브·환기, 이상조치 | XLSX/PDF |
| CITYGAS-01 | 도시가스 공급·사용시설 안전점검 기록표 | Record equipment condition | 공급구역, 설비, 차단·경보, 점검결과·조치 | XLSX/PDF |
| H2-01 | 수소설비 운전·점검 기록부 | Internal H2 operational evidence | 설비ID, 운전상태, 압력/온도 참조, 경보, 후속조치 | XLSX/PDF |
| H2-02 | 수소누출 대응 훈련기록표 | Preparedness exercise | 대상설비, 시나리오, 참여자, 반응, 개선 | DOCX/PDF |
| LAB-01 | 연구실 일상 안전점검 기록표 | Laboratory equipment/use conditions | 연구실, 일자, 유해인자, 설비, 보호구, 개선/확인 | XLSX/PDF |
| LAB-02 | 연구실 정밀안전진단 개선조치 대장 | Manage followup against professional diagnostic reports | 진단일, 지적, 우선도, 담당자, 완료증빙 | XLSX/PDF |
| LAB-03 | 연구실안전관리위원회 회의록 | Committee deliberation record | 회의 일시, 참석, 안건, 협의, 실행담당 | DOCX/PDF |
| DOC-01 | 안전관리 문서 개정·승인 이력대장 | Version change control | 문서번호, 버전, 변경사유, 검토, 시행일 | XLSX/PDF |
| DOC-02 | 안전관리 서식 배포·회수 관리대장 | Version circulation and obsolete document suppression | 문서ID, 배포처, 버전, 회수/확인, 상태 | XLSX/PDF |
| DOC-03 | 안전관리 기록물 보존·폐기 일정표 | Manage legal/policy retention | 문서유형, 보존근거(검증필요), 보존기산일, 예정일, 승인 | XLSX/PDF |

## Source-sensitive distinctions / further checks
- Original legal prescribed forms vs independently authored internal checks = separate items and SEO pages. No copying public official annex layout into a 'TAI legal original'.
- The ENV-01 proposal is not official 대기환경 운영기록부; original 대기 별지 and actual articles still must be obtained/current checked.
- 수소: no distinct legally prescribed blank form title established this round; H2 candidates business hypotheses. 연구실: only committee and inspection processes checked, exact statutory form labels not established.
- No source-form field extraction, license verification, right to distribute, or legal required-field assignment performed.
- Per E0 rubric, five previously unresearched areas now have at least statutory/workflow leads; **NOT** E2 completed and REF-01 exit remains blocked.
- Next: obtain source fields for environmental annexes, laboratory inspection sample, H2 technical codes; finish article-by-article legal mapping in REF-03.
- Git docs only; production DB/storage/frontend/backend/deploy changes = 0.
