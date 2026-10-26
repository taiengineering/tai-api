# MATRIX 관련 기존 코드·로직 As-Is와 재사용 경계

기준: tai-api Git main 10d9894d7dbee2044e76f8867c6f125c202e450e / LEG main dcbf981c430376916e991882fec8ec3c5463508d. 아래 경로와 동작은 고정 소스 검토 범위의 관찰로, DB의 현재 데이터 및 HTTP 응답 보증이 아니다.

## 1. 기존 검색은 변경 대상이 아님

- routers/public_safety_search.py: GET /public/safety-search 및 /sections. 검색어·객체유형·결과내 검색·페이지를 OpenSearch 검색 엔진에 전달한다. 실패한 OpenSearch를 정상 empty로 위장하지 않고 503로 반환하도록 소스 계약이 있다.
- object-type 범위: GUIDE, SAFETY_MATERIAL, CSI_ACCIDENT, CHEM, CHEM_REGULATION, KNOWLEDGE, PRECEDENT, LEGAL, REFERENCE_FORM, CHEM_SAFETY, HAZARDOUS_MATERIAL, CHEM_ACCIDENT. 이는 **검색 지원 범위**이며 모든 객체의 공개권리·상세 링크 적합성이나 MATRIX 지원을 뜻하지 않는다.
- services/shared_search/query.py: 기존 lexical dictionary 결과와 source key 후보를 검색계획에 사용. 동일 콘텐츠 canonical ID와 TAI 상세 URL ID 사이의 검증은 별도다.
- SearchResult 및 각 상세 router는 기존 계약의 authority이다. 관계 추천 기능 때문에 검색 랭킹, 타입별 섹션, URL, 공개 정책을 재설계하지 않는다.

## 2. Search Dictionary (이미 있는 핵심 어휘 자산)

- tools/search_dict/seed_v1.py: 용어 원천, 표기, approved/proposed 상태. LEG 용어·별칭과 공식/도메인 표기 seed 포함. seed는 전체 사전 census나 모든 제품 개념을 대표하지 않는다.
- tools/search_dict/normalize.py: 원문은 보존하고 Unicode NFC, 공백 축소, compact, latin_lower, 문장부호 제거를 서로 다른 파생 검색 필드로 만든다. term_id는 source_id+source_key+term_type+원문 해시이며 canonical content ID가 아니다.
- tools/search_dict/build_dictionary.py: 용어/동의어/표기 관계 검증 후 결정적 projection 생성. 용어 상태 PROPOSED/REVIEWED/APPROVED/REJECTED/HOLD, 관계 상태도 별도로 관리.
- tools/search_dict/search_core.py: EXACT→NORMALIZED_EXACT→PUNCTUATION→승인 별칭/동의어를 결정적 어휘 탐색에 사용한다. services/search_query_svc.py에는 추가 Kiwi 및 trigram 확장 경로가 존재하며 실가동 여부는 배포 구성에 의존한다.
- routers/search_dictionary.py: /search-dict/lookup, /health, /census. 사전 결과는 콘텐츠 관계 정답이나 사업장 법적 적용 여부가 아니다.

### K17/K18 미해결 결함 — 핵심 영향

K17: term_latin_lower는 compiler term master에 있으나 runtime projection 인덱싱/lookup에는 대문자와 소문자를 동등하게 조회하는 경로가 없다. K1 합성 MSDS 검색에서 대문자만 성공, 소문자는 누락했다. **기존 실제 서비스 모든 검색 경로의 장애로 일반화할 수는 없지만 Content MATRIX가 용어 사전에 의존할 경우 개선이 필요하다.**

K18: projection expansion은 확장 관계 상태 APPROVED만 검증하고 관계 양 끝 단어의 APPROVED 여부와 대상 subject의 생산 노출 가능 여부를 검증하지 않아 PROPOSED-only subject가 도달할 수 있다. lexical 사전 APPROVED를 Graph 관계 공개승인으로 승격하지 않는다. 우선 부정검증 대상으로 유지한다.

## 3. Graph relation store — 이미 존재하는 구조

- 마이그레이션: supabase/migrations/20261006153514_knowledge_graph_relations.sql.
- knowledge_relation_runs: 실행 ledger, rule_set_version, dry_run, 완료 상태·집계.
- knowledge_relation_edges: edge_key unique, CONTEXT/DIRECT, source_content_type/id, relation_type, relation_key 또는 target_content_type/id, CANDIDATE/ACCEPTED/REJECTED, is_active, stale.
- knowledge_relation_evidence: edge FK, method, source_field/value, rule_id/version, source_version, content_hash, evidence_json 등 provenance.
- Graph 룰: services/knowledge_graph_rules.py. 통제형 EXACT_MAPPING/TAXONOMY/CONTROLLED_KEYWORD/SOURCE_NATIVE/DETERMINISTIC_RULE 방식, 코드상 LLM/SEMANTIC 후보 승격 금지. 사고·안전자료 등 특정 콘텐츠 유형과 필드를 대상으로 한다.
- Producer: services/knowledge_graph_producers.py. 후보 생성 및 원천 hash 보존. CONTENT, alias, field match만으로 자동 법령 판단을 내리는 구조가 아니다.

### 현재 Graph에서 특히 주의할 계약

- DIRECT edge는 source_content_type/id + target_content_type/id가 실제로 유효한 객체를 가리켜야 한다. TAI 상세 URL slug, 원천 기관 문서번호, 검색 인덱스 canonical_id를 혼용하지 않는다.
- CONTEXT edge (예: equipment/forklift)는 콘텐츠 간 DIRECT edge가 아니다. 기존 4개 context 집계 11,776개는 테스트/레거시 관측치이며 실서비스 추천의 정답셋이 아니다.
- 기존 edge.status=ACCEPTED는 기존 규칙 기준 상태이지 Owner 승인, 출처 이용권한, 원문 검증, G1 공개 승인 여부를 대체하지 못한다.
- 같은 source에서 두 개의 서로 다른 개체를 언급한 경우 서로 다른 context relation 또는 별도 검증된 대상 콘텐츠를 가져야 한다. 키 없이 주조기와 취출로봇을 동일 edge로 합치면 안 된다.

## 4. G0 공개 containment과 G1의 분리

- routers/public_knowledge_graph.py의 context/items/{type}/{id}/contexts, items/{type}/{id}/related 는 G0 기준 소스에서 빈 결과 DTO 반환.
- G0 코드: PR #606 병합, Railway 배포 SUCCESS 확인. 운영 HTTP로 G0가 반환되는지/프록시·캐시에서 노출되는지 별도 NOT_RUN.
- G1 공개 positive는 미구현/미승인. 원천 권리·승인 witness·현재성·링크 무결성·실패 시 503을 명확히 해야 한다. 공개 G0 차단을 제거하거나 우회하여 테스트하지 않는다.
- 본 콘텐츠 MATRIX 설계는 G0의 승인 없는 공개를 전제하지 않는다. 나중에 다른 전용 읽기 경로를 제안하더라도 중복 우회 공개가 되지 않도록 같은 권한/승인 게이트가 필요하다.

## 5. 초기 범용 CORE에서 조사한 다른 소스 — 현 콘텐츠용으로 자동 연결하지 말 것

| 기존 자산 | 확인된 역할 | 현 콘텐츠 MATRIX에서 허용/제외 |
|---|---|---|
| routers/ksic_engine.py: industry_master, v_process_unified | KSIC 업종·공정 목록과 기존 필터 | 콘텐츠의 맥락 태그 가능성만; 업종→사업장 설비 보유 사실 추정 금지 |
| routers/factory_process_v3.py | process_id, kcs_code, 수동 공정명과 각 source 구분 | KCS 코드 ≠ 현장 실제 작업 객체. SaaS caller 제외 |
| services/equipment_source/registry.py | 확정 코드 010/014/023/024/038의 boolean facts | 코드·표시명을 사고 문맥 내 설비 실물 ID로 사용하지 않음 |
| services/work_source/registry.py | FORKLIFT=실제 사용 작업, 기타 ELECTRICAL/HIGH_PLACE/PAINTING/MAINTENANCE/EXCAVATION 등 | 콘텐츠 언급 개념으로 참고 가능, 고객 실제 수행 fact로 오인 금지 |
| tai-chemical material resolver | 회사 범위 MSDS 제품/버전 조회 | 고객 회사별 자료는 콘텐츠 공통 마스터에 넣지 않음 |
| LEG creation legal_identity.py | law_id/article_id/clause_id UUID 권위 | 법령 이름·표제·runtime atom_id를 동일 법적 객체로 자동 치환 금지 |

## 6. 콘텐츠 MATRIX 설계 시 재사용 판정

REUSE: 기존 공개 콘텐츠/검색, Search Dictionary 어휘/정규화, Graph 기존 저장·근거 개념, 원천별 상세 reader, 권한/가시성 정책.

REVIEW_BEFORE_REUSE: 기존 Graph edges의 의미/정답/rights/currentness 및 상세 URL ID와 source ID의 차이.

DO_NOT_REUSE_AS_AUTHORITY: 고객 입력, 사업장별 작업/설비 자산, 업체 MSDS 제품 버전, 검사 의무 판단, 텍스트 유사성 점수.

NOT_BUILT: Content MATRIX 자동 후보→검수→공개 E2E, 검증된 타섹션 상세 카드 조회, 실측 클릭/체류시간 증가.

참조: 2026-10-13 MX00/MX01 v2, WO-001/002, WO-004/K0/K1, WO-009 GPT 의미검증 보고서.
