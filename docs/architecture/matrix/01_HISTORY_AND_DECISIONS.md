# MATRIX 기획부터 로직 작업까지 — 결정·검증 이력

기준: 2026-10-13. 완료, 계획, 가설, 코드 존재, 배포, E2E는 다른 상태값이다. 이 문서에서 사용하는 PASS는 명시된 좁은 검증 범위만 뜻한다.

## 1. 발단과 사업 목적 (2026-10-12)

TAI에는 사고사례·안전 가이드·안전자료·공개 지식·법령·판례·화학 등 여러 원천과 통합검색이 이미 있었다. 초기 기획은 별도 검색 또는 신규 제품을 만드는 것이 아니라, 흩어진 콘텐츠 간 정보 관계를 재사용함으로써 사용자의 자료 탐색·정리 비용을 줄이는 것이었다.

초기 설계에서는 표준 개념 ↔ 콘텐츠 ↔ 직접 근거 관계를 공동 자산으로 관리하고 기존 통합검색·상세화면·향후 SaaS에서 소비하는 폭넓은 범용 MATRIX를 검토했다. 검색어×섹션 건수표는 제품 MATRIX 자체가 아니라 검색 하위 기능이라고 구분했다.

2026-10-12 외부 연구 및 v2.1 초안은 PR #605에 Draft로 등록됐다. 이 PR은 현재 합병 승인/제품 구현의 근거가 아니다.
- 원본 설계 PR: https://github.com/taiengineering/tai-api/pull/605
- 원본 파일: docs/architecture/csie/TAI_COMMON_SAFETY_RELATION_MATRIX_EXTERNAL_RESEARCH_AND_DESIGN_V2_1_2026-10-12.md (PR #605 branch)
- SKOS 개념명/동의어/연관어, PROV 출처계보, SHACL 검증 원칙 등을 참조했지만 RDF/Neo4j/신규 엔진 도입은 승인하지 않았다.

## 2. MX00 및 MX01 v2 범용 설계

MX00 조사에서 Graph의 CONTEXT 관계 4개 집합은 합계 11,776건으로 보고·검증됐다. 이는 기존 DB 컨텍스트 **테스트/현황 기준선**이지 올바른 문서 간 관계 수나 공개 가능 건수가 아니다.

다음 단계 MX01은 기존 DB/검색/레지스트리/Graph 재사용, KSIC·KCSC·MSDS·LEG의 공식 식별자·판본 근거, 관계별 권리·원천 lineage, 다중 소비자를 검토했다. 그러나 실제 crosswalk 및 법령 권위 경계 미입증으로 최종 설계 Freeze와 제품 구현은 BLOCKED로 남겼다.

G0는 공개 Graph 3개 엔드포인트에서 미승인 관계 노출을 막기 위한 정적 반환 보호 장치다. PR #606 병합과 Railway 배포가 확인됐으며 소스상 context/items/related가 빈 결과를 반환한다. 실제 운영 HTTP 응답, 캐시·프록시·UI E2E는 미확인이다. G1은 정확한 승인 witness, 원천 권리, currentness 및 SQL 선행 필터가 필요한 공개 positive 흐름으로 **미승인**이다.

## 3. MATRIX CORE 및 호출자 분리 결정 (10월 13일)

초기 논의에서 KSIC·건설코드·MSDS 및 사용자 입력을 기준값으로 넣는 제안을 검토했으나, Owner가 구조를 정정했다.

- MATRIX 기본값은 사용자 사업장/공정/설비/자재 데이터가 아니다.
- MATRIX는 공식 기준정보, 텍스트, 버전, 관계 근거로 형성되는 공통 참조 계층이다.
- 사용자 SaaS 입력·유료진단·검색은 MATRIX를 나중에 호출하는 consumer다.
- WO-003의 사업장별 work.equipment_ref↔equipment_assets.id 연결은 후속 SaaS caller adapter 성격이며 MATRIX CORE 구축으로 승인되지 않았다.
- LEG만이 법령 의미/적용 판단 SoT이다.

이는 이후 콘텐츠 중심 범위 전환에도 유지되는 중요한 데이터 권위 원칙이다.

## 4. 조사·검증 WO 이력

| 작업 | 수행된 것 | 검증/미검증 | 상태 |
|---|---|---|---|
| MX01 WO-001 | 기존 TAI API→LEG→점검·검색 코드 호출부, ID 손실·재사용·미연결 조사 | 고정 소스 검토만. 실제 운영 E2E E01~E12 NOT_RUN | ACCEPTED_WITH_CONTRACT_GAPS |
| WO-002 | 격리된 기존 실제 함수 4 PASS/3 GAP, LEG 정적 E07, 합성 관계모델 5 PASS | 실제 DB·원격 LEG·소비자 E2E 없음 | CLOSED ISOLATED PROOF, 제품 GAP OPEN |
| WO-003 | 사업장 설비-작업 ID 연결 최소 구현 제안 | 사용자 입력은 caller이므로 CORE 구현 범위에서 유예 | OWNER_PENDING / HOLD |
| WO-004 K0 | 기존 Search Dictionary와 KSIC/KCSC/CHEM/LEG/Graph 자산·27 Git Blob 조사, 골든 K01~K18 설계 | 18 cases PLANNED/NOT_RUN | ACCEPTED_WITH_GAPS |
| WO-005 K1 | 18개 격리 계약 검증 | lexical PASS 2, GAP 6, HOLD 8, FAIL 2(K17/K18). 공식 crosswalk 미검증 | ISOLATED EVIDENCE, 제품 미승인 |
| WO-006 | 실제 공개 색인/캐시 콘텐츠 7개 + 거부 표본 1개, 관계 제안 22행 | 후보16·HOLD3·거부3, 검색→상세 NOT_RUN | ACCEPTED_PARTIAL |
| WO-007 | 공개 검색 GET 접근 시도 | Mac DNS 해석 오류 curl exit 6; 상세 조회·확장 NOT_RUN | ACCESS_HOLD |
| WO-008 | Railway 공개 도메인·Cloudflare zone 조회 시도 | Railway 도메인 확인, CF DNS 메타데이터 403, HTTP NOT_RUN | ACCESS_HOLD |
| WO-009 | 인프라 의존 제거, 기존 7 + 신규 참조 25, 32개 참조·58행·4개 사용자 카드 작성 | POC 의미/샘플 부분 수용, 공식 crosswalk 0, 자동생성 E2E 0 | POC_PARTIAL_EVIDENCE |

## 5. WO-009 결과를 읽은 뒤의 의미적 전환

GPT는 58행을 직접 판독해 단순 건수보다 **관계 의미가 맞는지** 우선 검토했다. 지게차 포크 탑승은 '위험행동 언급'이지 표준 작업코드 신설이 아니며, 주조기와 로봇은 서로 다른 개체이고, 로더가 밀던 폐지 더미와의 접촉을 로더 직접 충돌로 단순화할 수 없다는 점이 확인됐다.

23건의 SOURCE_EXACT_SUPPORTED는 17개 코드↔표시명과 6개 물질 식별자/CAS 병기의 근거이지, 다른 도메인을 잇는 23개 검증된 의미관계가 아니다. 당시 POC에서 검증된 공식 교차관계는 0건이다.

## 6. 가장 최근 제품 방향 제안 (2026-10-13)

Owner는 '검색은 그대로 두고, 콘텐츠 상세에서 다른 섹션의 관련 콘텐츠를 보여주며, 공정·설비 SaaS는 이 MATRIX를 이용하지 않는 경우'를 제시했다. GPT는 이 **콘텐츠↔콘텐츠 MATRIX**가 범용/법령적용 엔진보다 운영 목적이 분명하고 빠르게 검증 가능하다고 권고했다.

이 전환은 **현재 우선 설계안**이지 Owner의 별도 구현/공개/DB/배포 승인으로 읽지 않는다.

- 검색 = 검색 결과 발견. 기존 계약을 그대로 유지.
- 상세페이지 = 내용, 출처와 함께 타 섹션 연관 콘텐츠 카드 조회.
- MATRIX = 콘텐츠 간 후보 탐색·증거·승인 상태·권리·공개 가능성.
- 공정/설비 판단, 고객 실제 자산, LEG 적용 여부는 이 MATRIX의 영역 밖이다.
- 새 테이블/새 검색/자동 법적 해석/Graph G1 공개는 필요성이 확인될 때 별도 결정한다.

## 7. 변경 및 비변경

문서화 자체는 제품 로직 변경이 아니다. 이력 전체에서 분리해 관리해야 한다:
- 실제 소스에 존재한 것: Search Dictionary, Graph relation/evidence, 공유검색, 공개 라우터, G0 안전차단.
- 작성했으나 미병합인 것: PR #605 v2.1 기획.
- 조사자가 만든 것: 22/58개 POC 관계, 4개 사용자 카드.
- 미실행/미증명인 것: 공식 crosswalk, 자동 Content MATRIX, 검색→상세 라이브 연계, 운영에서 positive 관계 노출, LEG 업무 적용.
- 현재 권장 다음 단계: 작지만 정확한 콘텐츠 상세↔다른 섹션 콘텐츠 관계 POC를 원천·권리·문서 ID가 검증된 샘플로 수행.

상세한 로직 계약·증거·실행 게이트는 같은 디렉터리의 02~05 문서를 참조한다.
