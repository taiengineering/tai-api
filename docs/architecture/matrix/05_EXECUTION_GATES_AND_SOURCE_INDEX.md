# MATRIX 다음 작업·승인 게이트·출처 인덱스

문서 기준: 2026-10-13. 단순 ZIP 무결성/관계 건수 합격보다 **실제 콘텐츠 간 의미가 정확하고 이용자가 클릭할 수 있는가**를 최상위 Gate로 둔다.

## 1. 현행 고정 상태

| 영역 | 상태 |
|---|---|
| PR #605 공통 MATRIX v2.1 문서 | OPEN / DRAFT / UNMERGED — 수정·병합하지 않음 |
| G0 공개 Graph containment | PR #606 MERGED / API main code DEPLOYED, live HTTP 확인 안 됨 |
| G1 공개 positive 관계 | BLOCKED / NOT_AUTHORIZED |
| WO-003 SaaS caller 설비 추적 | HOLD — 현 Content MATRIX 비범위 |
| Search Dictionary | 기존 lexical 재사용 검토 가능, K17/K18 결함 OPEN |
| WO-009 | 32개 참조·58행 인간 관계 POC 부분 수용 |
| 사용자 카드 | 4개 구성/감사, 실제 서비스 카드 E2E 아님 |
| 공식 cross-source 관계 | VERIFIED 0 |
| Content MATRIX 자동 생성기 | NOT_IMPLEMENTED / NOT_TESTED |
| 실제 상세↔타섹션 클릭 성공 증거 | NOT_OBSERVED |
| 제품 코드·DB·배포 | 이번 문서 PR에서는 0 변경 |

## 2. 권고 다음 Work Packages (새 승인 없이 구현하지 않음)

### P0 — 콘텐츠 관계 MVP 범위 Freeze (Owner)
- 제품 목적 '검색 기존 유지/상세 타섹션 관계' 확정 여부를 문서로 승인.
- 공정·설비/사업장 caller, LEG 의무판정, 제품 MSDS 및 대량 bulk 생성은 비범위 확인.
- 첫 관계 우선순위: 사고→가이드/안전자료; 사고→사고; 안전자료→공개 지식.
- G0 유지·G1 공개권한 별도 결정.
- 문서 대상 저장소/PR 병합 별도 Owner Gate.

### P1 — 실제 콘텐츠 exact-ID POC (Claude 수집, GPT 의미검증)
- 기존 API/공개 자료와 캐시를 구분하여, 두 섹션에 실제 존재하는 문서를 조회.
- 1~3쌍의 정확한 source_content_id, target_content_id, 원천 ID, 제목, 버전, 저작권/공개상태, 실제 상세 URL을 교차검증.
- 문맥 '언급/관련'과 콘텐츠 직접 관계를 분리. 로더/폐지 더미, 지게차 위험행동 등 기확정 반례를 포함.
- Cloudflare/DNS/Railway는 본선 사전조건이 아니다. 가능하면 HTTP 소비자 테스트는 별도 Gate에서 수행하고, 불가능하면 NOT_RUN으로 남김.
- 고정 source SHA, 증거 원문·법적 이용조건·실제 결과를 제출. 출처 열람이 안 되면 범위만 HOLD, 나머지는 진행.

### P2 — 최소 읽기 계약·보안/권리 Gate (GPT 설계, Owner 승인)
- 기존 knowledge_relation_edges/evidence 및 공개 상세·검색 reader 재사용 가능성을 검증.
- 임의 source->target ID를 만들지 않고 정확한 대상 객체 타입/namespace를 고정.
- 원천과 대상 모두에 대해 current/public/rights/authority를 읽기에서 확인.
- 실패 유형 ABSENT(정상 빈 결과), WITHHOLD(정상 비공개), UNAVAILABLE(원천 오류)을 구분.
- 관계 공개를 위해 G1 차단 해제 또는 새로운 우회경로를 임의로 열지 않는다.
- 신규 테이블/API/권한/Feature flag 추가는 최소 필요성이 입증된 뒤 별도 구현 WO.

### P3 — 작은 실제 서비스 E2E 및 UX 비교
- 승인된 검증 환경에서 기존 상세페이지는 변경 전 그대로 정상 표시됨을 확인.
- 동일 콘텐츠의 A(원본) / B(타섹션 카드) 화면을 비교하며 정확성과 클릭 경로를 확인.
- 관계 0개, 중복 target, 같은 주제지만 다른 객체, stale, private, 권리 불명, API 장애를 반례로 검증.
- 실제 클릭/체류/이탈 지표는 서비스 활성화 후 검증. 성공을 미리 단정하지 않음.

## 3. 기능적 합격 조건

- 1~3개 타섹션 관계에서 각 source/target이 **실제 다른 콘텐츠**이고 객체 ID와 URL이 정확하게 해석된다.
- 관계 설명 문구가 원천 본문/정형 필드에 근거하며 오연결이 반례에서 걸러진다.
- 공개권리·현재성·원천 판본 확인이 끝나지 않은 링크는 공개에 사용하지 않는다.
- 일반 검색의 쿼리/섹션/랭킹/표시 계약이 변하지 않는다.
- 사고/작업/설비/위험태그의 의미가 섞이지 않는다.
- 법령 적용·사업장 점검/물질 제품 추천이 Content MATRIX 응답에 포함되지 않는다.
- 일부 데이터 부족이라도 통과/실패/미실행을 분리하고 정답셋 없는 자동 추천을 PASS로 표시하지 않는다.

## 4. 변경통제 및 안전

- GPT: 분석/설계/WO/독립검증/semantic.
- Claude Code: 조사/실행/실제 자료 수집, 정확한 원문과 SHA 제출.
- Owner: 구현 브랜치, 기능 플래그, 운영 DB, Git 병합, Railway 배포, public 관계 공개를 각각 승인.
- PRJ 개발거버넌스 우선. LEG는 법령 SoT로 유지.
- 병렬 CHEM 변경을 자동으로 최신 head에 편입하거나 새 승인 ref로 재설정하지 않는다.
- 이번 문서 업로드는 PR #605, PR #606, G1 또는 타 프로젝트 배포·DB를 변경하지 않는다.
- 토큰/비용을 고려하여 동일 ZIP/소스 반복 조사보다 정확한 관계 1~3쌍의 실제 원천 증거를 우선한다.

## 5. 문서·증거 원천 목록 (대화 제공 자료, 새 저장소에 원본 ZIP은 업로드하지 않음)

### 2026-10-12 계획 / MX00 / MX01
- TAI_MATRIX_MX00_GPT_INDEPENDENT_REVIEW_2026-10-12.md
- TAI_MATRIX_MX01_REUSE_FIRST_CONDITIONAL_DESIGN_2026-10-12.md
- TAI_MATRIX_MX01_INTEGRATED_ASSET_STANDARD_DESIGN_V2_2026-10-12.md
- TAI_MATRIX_MX01_V2_EVIDENCE_2026-10-12.zip
- TAI_MATRIX_MX01_V2_P0_DELTA_GPT_INDEPENDENT_REVIEW_2026-10-13.md
- MX01_V2_G0_G1_SCOPE_DECISION_DESIGN_2026-10-13.md
- TAI_MATRIX_MX01_V2_G0_WO010_GPT_INDEPENDENT_RELEASE_REVIEW_2026-10-13.md
- TAI_MATRIX_MX01_V2_G0_WO011_GPT_INDEPENDENT_REVIEW_2026-10-13.md
- PR #605: https://github.com/taiengineering/tai-api/pull/605
- PR #606: https://github.com/taiengineering/tai-api/pull/606

### 2026-10-13 CORE / Keyword
- MX01_MATRIX_CORE_E2E_ASIS_AND_CONTRACT_2026-10-13.md
- MX01_MATRIX_CORE_E2E_001_GPT_INDEPENDENT_REVIEW_2026-10-13.md
- MX01_CORE_ISOLATED_SEAM_PROOF_002_2026-10-13.zip
- MX01_CORE_WO002_GPT_INDEPENDENT_REVIEW_2026-10-13.md
- TAI_MATRIX_MX01_KEYWORD_FOUNDATION_DESIGN_2026-10-13.md
- MX01_KEYWORD_FOUNDATION_K0_EVIDENCE_2026-10-13.zip
- MX01_K0_WO004_GPT_INDEPENDENT_REVIEW_2026-10-13.md
- MX01_KEYWORD_K1_ISOLATED_CONTRACT_PROOF_2026-10-13.zip
- MX01_K1_WO005_GPT_SOURCE_ONLY_INDEPENDENT_REVIEW_2026-10-13.md

### 2026-10-13 실데이터 POC·의미검증
- MX01_REAL_SERVICE_SAMPLE_POC_20261013.zip (WO-006)
- MX01_WO006_GPT_INDEPENDENT_REVIEW_2026-10-13.md
- MX01_REAL_SERVICE_ACCESS_COVERAGE_007_20261013.zip
- MX01_WO007_GPT_INDEPENDENT_REVIEW_2026-10-13.md
- MX01_REAL_PUBLIC_INGRESS_SERVICE_POC_008_20261013.zip
- MX01_WO008_GPT_INDEPENDENT_REVIEW_2026-10-13.md
- MX01_MATRIX_REAL_DATA_POC_009_20261013.zip
- MX01_WO009_GPT_INDEPENDENT_REVIEW_2026-10-13.md
- MX01_WO009_GPT_MEANING_VALIDATION_2026-10-13.md
- MX01_WO009_GPT_SEMANTIC_AUDIT_58_ROWS_2026-10-13.csv

원본 evidence ZIP은 해당 대화 첨부 자료다. Git 저장소에는 요약, 수용 판정, 추적 가능한 파일명만 보관하며 개인/고객/비밀 정보, 토큰, 자격증명, 운영 DB 덤프를 업로드하지 않는다.

## 6. 고정 소스 근거 (GitHub, main baseline)

- tai-api 10d9894d7dbee2044e76f8867c6f125c202e450e
  - docs/architecture/csie/TAI_COMMON_SAFETY_RELATION_MATRIX_EXTERNAL_RESEARCH_AND_DESIGN_V2_1_2026-10-12.md는 PR #605 Draft branch에 존재하며 main에 없다.
  - tools/search_dict/build_dictionary.py, normalize.py, search_core.py, seed_v1.py
  - services/knowledge_graph_rules.py, knowledge_graph_producers.py
  - supabase/migrations/20261006153514_knowledge_graph_relations.sql
  - routers/public_knowledge_graph.py, routers/public_safety_search.py
  - services/shared_search/query.py, services/shared_search/result.py
  - services/work_source/registry.py, services/equipment_source/registry.py
  - routers/ksic_engine.py, routers/factory_process_v3.py
- LEG dcbf981c430376916e991882fec8ec3c5463508d
  - development/engine/creation/contracts/legal_identity.py (law_id/article_id/clause_id의 권위 체계)
- CHEM: 병렬 변경 존재. 원본 증거의 고정 SHA와 현재 Git 원격을 매 작업별 비교. 파일 경로 app/repositories/material_resolver.py는 회사별 version identity를 다룬다.

## 7. 이후 ChatGPT 창 시작 프롬프트 (복사 용도)

TAI MATRIX 문서는 tai-api/docs/architecture/matrix/README.md부터 05번까지 읽는다.
- 현재 제안: 기존 통합검색 유지, 상세페이지 다른 섹션 콘텐츠 관계. 공정·설비 SaaS caller/LEG 의무 적용 제외.
- GPT 분석·설계·독립검증, Claude Code 실행·증거수집, Owner 승인.
- WO-009은 32개 참조/58행 HUMAN POC; 공식 crosswalk 0, 자동 및 실제 서비스 E2E 0.
- PR #605 Draft 건드리지 않음, G0 보존, G1 HOLD.
- 다음에는 실제 콘텐츠 source/target ID가 있는 연관관계 1~3쌍부터 검증한다.
- 기존 검색/DB/서비스 동작 변경 없이 Owner에 후속 상세 WO를 제출하라.
