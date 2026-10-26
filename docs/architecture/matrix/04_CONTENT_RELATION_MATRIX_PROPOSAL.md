# TAI Content Relationship MATRIX — 상세 콘텐츠 간 연결 설계 제안

- 날짜: 2026-10-13
- 상태: GPT 제품 제안 / Owner 구현·공개·DB 설계 승인 별도 필요
- 목표: 기존 안전정보 검색은 그대로 두고 **기존 콘텐츠 상세 화면에서 다른 섹션의 연관 콘텐츠**를 보여준다.
- 비목표: 공정·설비의 사용자 사업장 입력 판정, 고객 자산 검증, LEG 법령의무 적용, 검색 랭킹 교체, 새 SaaS/Graph DB 구축.

## 1. 왜 콘텐츠 MATRIX인가

기존 MATRIX 범용안은 KSIC/KCSC/MSDS/LEG 공식 교차관계를 요구한다. 실제 WO-009 증거에서 원천 ID·판본·crosswalk가 검증된 관계는 0이었다. 반면 사고사례 안의 설비·위험행동·사고유형 문맥 구분은 수작업 의미감사로 일부 가능성이 확인됐다.

콘텐츠 MATRIX는 범위를 좁혀 '이 자료를 읽는 안전관리자에게 관련된 **실재하는 다른 자료**를 제공'하는 업무에 집중한다. 기존 검색은 검색 기능으로 남기고, 상세화면 하단 또는 측면에 타 섹션 자료를 제한 수량 노출한다. 이탈률/체류시간 개선은 현재 가설이며, 실제 효과는 나중에 계측해야 한다.

## 2. 사용자 경험 (신규 전용 페이지 없음)

대표 흐름:
1. 방문자가 기존 통합검색에서 지게차 사고사례를 연다.
2. 기존 상세페이지의 원문·출처·작성기관 표시는 그대로 둔다.
3. 별도 영역 '함께 보면 좋은 안전정보'에서 안전 가이드, 다른 사고사례, 안전 지식 순으로 타 섹션 문서 카드를 보여준다.
4. 카드에는 유형, 정확한 제목, 왜 관련있는지(주제/위험/문서인용 등), 원출처, 링크를 제공한다.
5. 클릭 시 기존 해당 자료의 상세 URL로 이동한다.
6. 검증·권리가 부족한 경우 개별 관계를 숨긴다. 존재하지 않는 콘텐츠를 꾸며 보여주지 않는다. 관련 카드가 0이면 기존 상세페이지는 그대로 정상 표시한다.

초기 카드 유형 권고:
- 사고사례 ↔ 안전 가이드/안전자료
- 사고사례 ↔ 같은 위험 또는 작업 문맥의 다른 사고사례
- 안전 가이드/자료 ↔ 같은 주제의 공개 지식
- 법령 원문 또는 판례·화학은 정확한 원천 ID/권리 확인 후 후속 확장

'동일 업종'이나 '키워드 공통'만으로 추천을 확정하지 않는다. 사고 언급이 고객 현장 해당 위험 존재를 뜻하는 것도 아니다.

## 3. 설계상 객체 (논리 DTO이며 실제 DB/schema/API 아님)

### 3.1 ContentRef
- source_namespace: 원천 기관/TAI 내부 provider 또는 객체 유형별 name space
- object_type: 실제 검색·상세 API가 허용하는 콘텐츠 유형
- canonical_content_id: 기존 원천/TAI 객체 identity (확인된 경우에만)
- source_record_id: 원천 기관 ID — 확인된 원천의 독립 필드
- source_version / current_snapshot / source_hash: 입증된 값만
- public_url: 기존 상세 resolver가 해당 콘텐츠와 동일함을 확인한 URL
- visibility_scope, rights_policy, currentness: 현재 상태 조회의 근거
- original_title, displayed_title, language: 원문 표제와 표시 문자열 구분

### 3.2 ContentConceptAnnotation
- content_ref, concept_namespace/id 또는 타입별 후보 key
- concept_type: equipment, action/task, hazard, incident_outcome, chemical_topic, legal_reference, process_topic 등 문맥 태깅을 위한 분류. 사업장 설비 ID 아님.
- role: PRIMARY_TOPIC, MENTIONED_EQUIPMENT, MENTIONED_ACTION, INCIDENT_MECHANISM, DIRECT_QUOTE 등
- evidence_field, excerpt_pointer, rule_id/version, curation_state
- 검색어 '지게차' ↔ CONTENT에서 지게차 사용 사실을 확정하기 전에 어떤 문맥인지 확인

### 3.3 ContentRelationProposal
- source_content_ref, target_content_ref (두 대상 모두 실제 콘텐츠)
- kind: SAME_SUBJECT, SIMILAR_INCIDENT, RISK_TOPIC_RELATED, REFERENCES_DOCUMENT, EXPLAINS_TOPIC 등 설계상 어휘. 기존 Graph DB enum에 없는 신규 값은 그대로 insert 금지.
- evidence: source_field, target_field, quote_or_exact_reference, source_hash/version, rule_id/version
- state: DISCOVERED, REVIEW_REQUIRED, EVIDENCE_VERIFIED, OWNER_APPROVED 등 논리적 검토 단계
- rights/visibility/currentness: 별도 공개 판정. '상태 APPROVED'만으로 공개 금지
- identity_key: 실제 source + target + 명시 relation_type 및 판본/namespace를 기준으로 안정적으로 구별할 것. 대상 ID 비어 있으면 DIRECT edge를 만들지 않는다.

중요: 특정 사고에 지게차가 등장한다는 Annotation과 '이 사고와 저 가이드가 관련된다'는 두 콘텐츠 간 Relation은 서로 다른 객체다. 전자를 무조건 후자로 변환할 수 없다.

## 4. 최소 처리 로직 — 현재 구현 사실이 아닌 제안

### Step A — 원천 콘텐츠 신뢰 게이트
기존 공개 검색/상세 SoT에서 후보 원천 콘텐츠의 실제 object_type, canonical ID, 표제, 본문/메타데이터, source version, 공개 가능 여부를 가져온다. URL slug 단독으로 객체 동등성을 주장하지 않는다. Source/reader가 실패하면 해당 관계를 보류하고 GET 성공으로 위장하지 않는다.

### Step B — 개념 후보 추출
기존 Search Dictionary·통제 규칙에서 어휘와 정형 필드를 활용한다. 사고 문장에서 설비, 실제 수행 행동, 직접 접촉 대상, 사고 결과, 원인 추정, 예방조치 서술을 분리한다. lexical 일치·유사 문구·LLM은 후보 탐색 보조일 뿐 확정 근거가 아니다.

### Step C — 타 섹션 문서 후보 찾기
원문 ID가 확인된 콘텐츠 목록이나 기존 OpenSearch를 이용해 특정 개념·위험 주제에 맞는 다른 섹션 문서를 찾는다. 검색 후보 순위는 관계 승인 상태가 아니다. 기존 결과 집합·인덱스 변경을 최소화한다. 검색 개선 POC와 관계 품질 평가는 분리한다.

### Step D — 관계 근거와 실패 분류
- 직접 문서 인용: 원문에 식별 가능한 서식/가이드/문서 ID가 있고 대상 문서가 일치할 때만 DIRECT 근거 후보로 승격.
- 관련 주제: 주제+현장 문맥이 유효하면 CANDIDATE/REVIEW_REQUIRED, 담당 검수 기준 충족 후 연결 가능.
- 부정/혼동: 같은 단어라도 다른 행위, 장비/구성품, 부정형 또는 위험행동, 인과대상 불일치이면 REJECT.
- 판본·ID·권리 누락: HOLD. 자동 대체·임의 GUID·원천번호→URL slug 변환 금지.
- 법령 정보: 법령명 언급은 주제 태그 가능. LEG law/article/clause UUID+시행판본 없는 '적용 의무' 출력 금지.

### Step E — 공개 가능한 카드만 조회
원천과 대상 양쪽이 현재 유효하고 공개권리 확인이 있으며, 승인된 관계·근거·정확한 링크가 있을 때만 카드 표시. 하나라도 미확인 시 그 관계는 숨기고 기존 상세 콘텐츠를 정상 제공한다.

랭킹(제안): verified direct citation > 검수된 같은 핵심 개념·사고유형 > 검수된 같은 위험 주제. 단순 문구/LLM score 단독 공개 우선순위 금지. 동일 대상은 한 번만 보여주고, 같은 섹션 일색이 되지 않게 타 섹션을 우선하되 관련성 없는 섹션을 강제로 채우지 않는다.

## 5. 콘텐츠 안전성 및 권리 게이트

1. 내용 링크는 출처·저작권·재게시 허용 정책을 분리한다. 링크 가능과 본문 복제 가능은 다르다.
2. 공지/스팸/현재성 미달 자료는 추천 제외. 사라진 원문과 stale 링크는 취소 또는 별도 상태로 표시.
3. private/tenant 문서와 회사별 MSDS·재고는 이 공개 콘텐츠 MATRIX에서 제외한다.
4. 사용자 접근 가능 상태보다 더 높은 데이터가 관계 요약을 통해 새어나오지 않게 양 끝 객체의 정책을 검사한다.
5. 관계 설명은 검증 가능한 '동일 위험 주제', '문서에서 특정 설비 언급' 정도만. '반드시 준수할 법령', '원인 확정', '동일 MSDS'는 별도 권위 근거 전까지 금지.
6. 운영 Graph의 G0 차단을 우회하지 않는다. G1 승인은 별도 Owner gate다.

## 6. 기존 자산에 대한 최소 변경 방침

- 신규 DB 테이블/Graph 엔진/벡터DB를 기본값으로 가정하지 않는다.
- 기존 knowledge_relation_edges/evidence, Search Dictionary, 검색 reader, 상세 resolver, rights policy가 요구 계약을 충족하는지 먼저 확인한다.
- 새 물리 스키마가 필요하더라도 정답 샘플과 조회 계약에서 누락이 확인된 경우만 최소한으로 제안한다.
- K17/K18 lexical 결함은 별도 좁은 패치 후보. 패치 전에는 그 취약한 경로에서 확정 관계를 만들지 않는다.
- 공개 positive 관계 제공에는 G1 authority 승인 및 서버 측 적용 범위를 먼저 명시해야 한다.

## 7. 첫 POC: 이용자 관점의 성공/실패

초기 수작업 검수 대상 콘텐츠 상세 20건(가능한 범위), 각 실제 source ID와 target ID를 확인하고 1~3개 정확한 타섹션 연결로 수직 슬라이스를 먼저 검증한다. 20개 확보가 불가하면 실제 확보분만 정직하게 기록하고 신규 데이터 수집 성공이라고 주장하지 않는다.

비교 조건:
- A: 기존 상세 화면만
- B: 동일 원문+검증된 타섹션 관계 카드
- 평가자: 원천을 직접 읽는 GPT 독립 의미검증 + Owner 제품판정; 가능하면 안전관리자 실제 피드백 별도
- 평가 질문: 관련성이 설명되는가, 동일 ID 문서를 여는가, 중복/오류/광고성 추천이 없는가, 추가 카드가 사용자의 탐색 작업을 줄이는가?
- 사후 사용자 성과(클릭/체류/이탈)는 배포 후의 별도 계측이며 지금부터 수치 목표를 사후 꾸미지 않는다.

초기 골든 반례:
- 지게차 포크 탑승은 정상 작업코드 아님.
- 주조기와 로봇 둘을 하나의 target ID로 축약 금지.
- 폐지 더미 충돌을 로더 본체 충돌로 오인 금지.
- 트럭 적재함 추락 → KCSC 비계 규정 직결 금지.
- CAS 같음 → 제조사별 MSDS 제품 동일화 금지.
- 소스 사전 APPROVED/Graph ACCEPTED → 공개권리 통과로 치환 금지.
- 다른 원천번호를 URL slug로 넣어 상세 콘텐츠 링크 오염 금지.

## 8. 인터페이스 계약 스케치 (실재 API 아님)

읽기 입력 후보: object_type, canonical_content_id, caller_visibility.

읽기 출력 후보: 원천 콘텐츠 메타, 검증된 관련 카드 목록 [{target_type, target_canonical_id, title, canonical_detail_url, relation_label, evidence_summary, source_attribution}], 상태 및 빈 결과 의미.

현재 endpoints나 새 URL을 이미 제공한다고 쓰지 않는다. 추후 제품 구현 승인 시 DB/RPC/route 존재 여부부터 확인하고 DTO를 기존 상세 API에 확장할지, 별도 읽기 엔드포인트를 둘지 결정한다.

## 9. 제품 승인 전 최종 미해결 항목

- 실제 공개 콘텐츠 2개 사이의 신뢰 가능한 exact ID 및 상세 링크 수직 연결 증거 없음.
- 후보 생성기의 자동 precision/recall 근거 없음.
- 유형별 이용권한과 현재성/출처 라이선스 확정 계약 부족.
- 외부 표준 판본 및 LEG 공식 ID crosswalk 미검증 (현 콘텐츠 MVP에서는 법률 적용 연결 범위 제외).
- 실서비스 검색→상세 및 추천 카드 소비자 E2E 미검증.
- G1 공개 관계 승인·게시·회수 프로세스 미완성.
- Owner의 현 콘텐츠 범위 제품 Freeze·구현·배포 승인 대기.

VERDICT = PREFERRED_PRODUCT_DIRECTION / NOT_IMPLEMENTED / NOT_APPROVED_FOR_PUBLICATION
