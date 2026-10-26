# TAI MATRIX — 기획·로직·검증 통합 인덱스

- 기준 시각: 2026-10-13 (Asia/Seoul)
- 문서 목적: MATRIX 최초 문제 정의부터 MX00/MX01, WO-001~009, 콘텐츠 중심 범위 전환 제안까지 이어지는 의사결정과 증거를 한곳에 보존한다.
- 이 문서군은 이력과 현재 제안의 정리본이다. 구현 승인서, 운영 적용 승인서 또는 완성 선언이 아니다.
- 저장 위치: tai-api / docs/architecture/matrix/
- 기준 저장소: tai-api main 10d9894d7dbee2044e76f8867c6f125c202e450e; LEG main dcbf981c430376916e991882fec8ec3c5463508d. CHEM은 병렬 변경이 있으므로 시점별 SHA로 확인.
- 문서 변경만 허용한다. 코드·DB·인덱스·권한·배포 변경 없음.

## 먼저 읽을 문서

| 파일 | 읽는 목적 |
|---|---|
| [01_HISTORY_AND_DECISIONS.md](01_HISTORY_AND_DECISIONS.md) | 최초 목표 → 공통 지식 관계 → 사용자 입력/마스터 분리 → 콘텐츠 관계 전환의 전체 연혁과 WO별 결과 |
| [02_EXISTING_LOGIC_AND_SYSTEM_BOUNDARIES.md](02_EXISTING_LOGIC_AND_SYSTEM_BOUNDARIES.md) | 실제 GitHub 소스에서 확인한 검색사전, 공정/설비, Graph, 공개 검색/상세, 법령 식별자 및 기존 G0/G1 구현 경계 |
| [03_POC_RESULTS_AND_MEANING_AUDIT.md](03_POC_RESULTS_AND_MEANING_AUDIT.md) | WO-002/K0/K1/006~009 결과의 의미, 32개 원천 참조·58행 의미검증, 반례와 미입증 사항 |
| [04_CONTENT_RELATION_MATRIX_PROPOSAL.md](04_CONTENT_RELATION_MATRIX_PROPOSAL.md) | 현행 권고안: 기존 검색 유지 + 다른 섹션 콘텐츠를 상세페이지에서 연결하는 Content MATRIX 논리설계 |
| [05_EXECUTION_GATES_AND_SOURCE_INDEX.md](05_EXECUTION_GATES_AND_SOURCE_INDEX.md) | 다음 POC, 인수인계, 승인 게이트, 파일/PR/SHA 근거 인덱스 |

## 지금의 의사결정 경계

1. 검색은 현행 OpenSearch / Search Dictionary / 통합검색 기능을 그대로 사용한다.
2. MATRIX의 최근 제안 방향은 **콘텐츠와 콘텐츠의 연관정보**를 콘텐츠 상세페이지에 보여주는 것이다. 공정·설비 SaaS의 사업장 판단/설비 인스턴스와 결합하지 않는다.
3. KSIC, KCSC, MSDS, LEG를 가로지르는 공식 교차관계는 아직 증명되지 않았다. 과거 범용 CORE 설계는 보존하되 현재 콘텐츠 POC의 승인된 제품 범위로 간주하지 않는다.
4. 사고에서 어떤 설비·행동·위험이 **언급되는 관계**와 그 사업장에 **법령 의무가 적용되는 관계**는 완전히 다르다. 의무 적용은 LEG SoT 전용이다.
5. 검색사전의 APPROVED, Graph의 ACCEPTED, 원천 필드 일치는 서로 다른 승인 의미다. 어느 것도 자동으로 공개 가능·법적 정확성·관계 정답을 뜻하지 않는다.
6. 기존 Graph G0 정적 비공개 차단 코드는 병합·배포됐으나 HTTP 실응답은 검증되지 않았다. G1 공개 positive 흐름은 보류된다.
7. 실데이터 POC 32개는 **공개 콘텐츠 32건이 아니다**. 원래 공개 콘텐츠 7건 + 내부 정의/분류 참조 13건 + 외부 자료 12건이며, 신규 공개 본문은 0건이다.
8. 58개 관계 행은 조사자가 제안한 샘플이다. 공식 crosswalk 검증 0, 자동 MATRIX 성능 검증 0, 라이브 서비스 E2E 0.
9. CF/DNS 접근 실패는 별도의 인프라 확인 이슈로 분리하며, MATRIX 내용 검증의 필수 선행조건으로 만들지 않는다.

## 역할과 승인

- GPT: 기획·분석·설계·작업지시·의미 판정·독립검증.
- Claude Code: 승인된 범위의 소스 조사·실행·증거 수집.
- Owner: 제품 범위, PR/병합, 운영 DB, 배포, 공개 활성화 별도 승인.
- PRJ 개발 거버넌스와 LEG 법령 SoT의 권위를 우회하지 않는다.
- 본 문서 PR은 **문서 저장을 위한 제출**이며 제품 구현, PR #605 병합, G1 활성화 또는 공개 약속이 아니다.

## 판정

CURRENT_DOCUMENT_STATUS = CONSOLIDATED / OWNER_PRODUCT_FREEZE_PENDING

PREFERRED_NEXT_EXPERIMENT = CONTENT_DETAIL_TO_CROSS_SECTION_RELATION_POC

PRODUCT_CODE_CHANGE = NONE; DB_WRITE = NONE; DEPLOY = NONE
