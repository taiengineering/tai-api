---
class: design
type: ENGINE_ARCHITECTURE_DESIGN
scope: csie
title: TAI Common Safety Information Engine — WP01 Detailed Design
version: 1.0
status: GPT_DESIGN_DRAFT_FOR_DOCS_PR
owner: TAI Owner
architect: GPT
executor: Codex
---

# CSIE — TAI 공통 안전정보 활용 엔진 상세설계 v1.0

| 항목 | 내용 |
|---|---|
| 문서 ID | `CSIE-WP01-ENGINE-DESIGN-001` |
| 작성일 | 2026-10-12 (KST) |
| 아키텍처 결정 | **OpenSearch 검색·집계 + 문서별 표준 컨텍스트 + 최소 검증된 직접 관계** |
| 문서 상태 | **GPT 작성 설계안. Codex 문서 전용 PR 제출 → GPT 독립검증 → Owner 설계 승인 전까지 미동결(DRAFT)** |
| WP00 | **CONDITIONAL CLOSED FOR DESIGN**; 운영 인덱스 미확인은 운영 적용 게이트로 이관 |
| 기준 실측 소스 | `tai-api@172a0c0a9e5ae27f80d49f1c9b10ec13e02d538c`, `tai-www@3b10ece193ee2ccc3f61e0cca0ea38799eb38520`; 이후 main 변화는 Anchor Diff 확인 |
| 기준 배포 | API Railway 배포 `bb24497d-9bef-4dc4-ba42-12d98b43eae5` / WWW CF 배포 `82bccbec-971a-4af8-9c83-bea1ca435056`; 배포 조회 영수증 기준 |
| 변경 승인 | 본 문서 제출은 **코드·DB·OpenSearch write, 스케줄러 실행, PR merge, deploy를 승인하지 않음** |
| 선행 참조 | `TAI_COMMON_SAFETY_INFORMATION_ENGINE_MASTER_PLAN_v1_2026-10-12.md`, `TAI_SAFETY_SEARCH_REBUILD_MASTER_PLAN_2026-10-12.md`, `CSIE_WP00_*` 및 `CSIE_WP00_R1_REV1_GPT_INDEPENDENT_REVIEW_2026-10-12.md` |

> **중요 정정/우선순위**: 상위 마스터 계획에 남은 `Claude Code` 실행자 표기는 **Codex**로 정정하며, 국가 법령의 SoT를 `45cm-prj-db`라고 한 표현은 폐기한다. `45cm-prj-db`의 governance 문서/RPC는 **개발 거버넌스 규칙** SoT이며, 현재 국가 법령 검색 어댑터가 읽는 데이터는 별도 **`leg-prod/public.law_*` 법령 도메인**이다. 법령 수집의 최종 공적 근거/판본 계보는 해당 법령 데이터 체계에서 추적한다. 이 설계 문서는 국가 법령 SoT의 모든 업스트림 계보가 독립검증됐다는 주장이 아니다.

---

## 0. 결정 및 경계

### 0.1 확정하는 설계 원칙

1. 원천 데이터/공식 API와 기존 도메인 DB가 SoT다. **OpenSearch는 재구축 가능한 파생 read index**이며 법령 적용 여부를 판단하지 않는다.
2. 키워드마다 `keyword × document` 테이블을 만들지 않는다. 검색은 **어휘 일치(Lexical Search)**와 **확인된 컨텍스트(Verified Context)**를 명확히 구분한다.
3. 기존 검색 계층의 `T0~T9` tier, `_msearch`, public DTO v1, 타입별 URL/소비자 계약, 기존 outbox/증분 색인 및 atomic alias 코드를 **우선 재사용**한다.
4. **Public 검색 인덱스에는 공개 허용된 비민감 정보만** 포함한다. 기업·공장·사용자·진단 응답·개인정보·비공개 MSDS 등은 공통 검색 인덱스에 넣지 않는다.
5. 직접 관계는 **근거가 있는 식별자/판본/원천 명시 링크**에 한한다. 단어 유사도·검색 랭킹·LLM 후보를 법령 의무, 유해성, 위반이나 특정 작업의 사실로 확정하지 않는다.
6. 새 v2 기능은 **추가 계약과 별도 shadow 검증**으로 제공하며, 기존 `/public/safety-search` 및 `/sections` 계약은 호환 상태를 유지한다.
7. 기존 Graph 11,776 edge는 테스트 회귀 대조 자료이며 공식 정답/서비스 운영 관계 데이터로 승격하지 않는다.
8. 코드는 Codex가 실행하되, **분석·설계·기술 결정·작업지시·독립검증은 GPT**, 최종 설계·병합·DB/index/배포 승인자는 Owner다.

### 0.2 비범위

- 새 자체 법령 의무 추출, 벌칙 계산, 중대재해 적용 판단, tenant 데이터 중앙 복제.
- 모든 3개 API의 원문을 곧바로 검색 공개하는 것, 원문/첨부/썸네일의 무조건 재호스팅.
- 11,776개 테스트 관계를 신규 운영 Graph로 전량 이관하는 것.
- 새 벡터 DB, 대규모 LLM 자동 태깅, 1차 알림·AI 채팅·검색 사용자 개인화.
- 기존 `tai-chemical`의 내부 MSDS reference matching을 공통 검색 API로 대체하는 것.

### 0.3 설계와 운영의 두 게이트

- `DESIGN_GATE`: 현행 소스와 읽기 증거로 데이터 계약·모듈 인터페이스·실행 검증 기준을 설계하고 승인한다. 운영 OpenSearch alias 접근 부재만으로 반복 조사하지 않는다.
- `RELEASE_GATE`: live alias/mapping, 색인 parity, PUBLIC/rights, 실제 결과·성능·롤백을 확인한 후에만 alias 교체 또는 공개 기능을 활성화한다. 근거 부족 시 **그 변경만 BLOCKED**; 설계와 무관한 WP를 무한 반복하지 않는다.

---

## 1. 확인된 기존 기준선과 설계 적용

| 현행 사실 / 확인 범위 | 설계 반영 |
|---|---|
| `tai-api/services/shared_search/production_bindings.py::build_production_adapters`는 기존 어댑터를 바인딩하며 EXT-037/132/165는 active SHA의 목록에서 미발견 | EXT3를 신규 SearchAdapter 계약으로 별도 추가 설계. 현재 INDEXED=0이라는 주장은 금지 |
| `SearchDocument`의 v1 `subjects`, `context`는 이미 nested 필드 | 구조 재사용 여지 있음. 다만 CHEM은 `chem_id`, KECO는 CAS 등 `chemical` 키 의미가 달라 v2 이름공간/증거 계약이 필요 |
| `opensearch_reader.py`는 tier별 200 후보, `_msearch` 사용, 섹션 API는 9개 engine.search를 순차 호출 | 우선 순위 보존 검증 없이 `terms+top_hits` 단일 쿼리 전환 금지 |
| v1 `SearchResponse.total`은 dedup된 fetch 후보 수. `/sections`는 total 없음 | v2의 별도 정확도·관계(`eq/gte/unknown`)를 포함하는 `total` 계약 필요 |
| `type=chem`+공개 mode off → `object_types=[]` → type filter 없음 | 독립 **P0 type-scope 결함**으로 등록. v2 이전에 별도 수정 WO를 승인받아 교정; 운영 유출 확정 주장은 금지 |
| `tai-www` 검색과 상세는 현행 public API 계약 호출; Paid, SaaS, CHEM는 서로 다른 계약 | 소비자별 BFF/adapter. Paid/SaaS를 public DTO v1 직접 사용자로 가정하지 않음 |
| `tai-api` 인덱스 재구축/검증/atomic alias/rollback와 outbox 증분 경로 존재 | 기존 writer/guard 재사용. v2 물리 인덱스 이름을 현재 v1 함수에 그대로 넣지 말고 version-aware 전략 정의 |
| `leg-prod/public.law_master/current_version_id` → `law_version` → `law_article` 검색 계약 | 최신 pointer와 **오늘 시행 중(effective)**을 분리하여 라벨/필터 처리 |
| `GUIDE`는 현재 저장 정책이 LINK_ONLY; `SAFETY_MATERIAL` 권리 정책 혼재 | 공개 search snippet, 원문, 미리보기, binary 각각 권리 체크; unknown fail-closed |
| 기존 4키워드 Graph 11,776개 `CONTROLLED_KEYWORD` | 추후 relevance QA의 비교군만 사용, 정확도 정답으로 보지 않음 |
| EXT037 7,189 / EXT132 7,277 / EXT165 1,143 수집 완료, 하루 단위 스케줄 성공 기록 | 합계 15,609 **COLLECTED**. `MAPPED`, `INDEXED`, `PUBLIC`은 별도 단계 |
| OpenSearch Railway service/deployment 존재하지만 live alias·mapping·stats 미확인 | shadow 및 배포 전 필수 read checks로 이월 |

**고정 참고 경로**: `tai-api/routers/public_safety_search.py`; `services/shared_search/{contract.py,result.py,opensearch_reader.py,opensearch_mapping.py,opensearch_store.py,retrieval.py,production_bindings.py,incremental.py}`; `tai-www/src/lib/server/safetySearch.js`; `tai-www/src/pages/safety-search.astro`; `tai-chemical/app/adapters/msds_reference.py`.

---

## 2. 논리 아키텍처 및 책임

```text
[공식 3 API / KOSHA / LEG / KECO / CSI / 콘텐츠 / MSDS / 서식]
          │ 수집(기존 collect/sync)   <= SoT 유지, 수정·재수집은 본 설계 범위 아님
          ▼
[원천별 CURRENT & PUBLIC ELIGIBILITY Reader]
          │ source_id, source_key, canonical_id, version, origin rights
          ▼
[기존 DomainAdapter / SearchDocument normalizer]
          ├── [CSIE Context Resolver v1]  구조형 식별자→통제사전→검증 상태
          ├── [Explicit Reference Resolver]  원천이 명시한 정확 참조만
          └── [Public Sanitizer + Source Rights/Version Gate]
          │ v1 호환 projection + 별도 v2 extension
          ▼
[기존 SearchWriter / incremental outbox / full rebuild safeguards]
          │  candidate index 검증 => shadow alias (별도 승인 하에)
          ▼
[OpenSearch CSIE v2 Index (derived, public-safe)]
          │ exact / Nori / nested context / facet / verified direct link
          ├── [Public Search v2 Presenter] -> tai-www search UI
          ├── [Related Read API]         -> 자료형별 상세
          └── [Reference Context API]   -> SaaS / CHEM / Paid BFF에서 조회
                                    (private tenant context는 소유 서비스 내 유지)
```

| 논리 모듈 | 입력 | 출력 | 책임/비책임 |
|---|---|---|---|
| `SourceEligibility` | source row + rights + version | eligible / reject reason | 각 원천별 current/public 판단. 법 적용 판단 금지 |
| `CanonicalProjection` | approved source | `SearchDocument` v1 필수 + v2 후보 | 원본 PK, 공개 URL, text, provenance 정규화 |
| `ContextResolver` | 공개 구조 필드/증거 텍스트 + 사전 스냅샷 | 증거가 있는 context assertions | 규칙 기반 정규화. 자동 법적 관계 판정 금지 |
| `DirectReferenceResolver` | 정확한 source identifiers | source-grounded edges | 불확실한 CAS/문서명은 직접관계로 승격 금지 |
| `IndexPublisher` | validated projection | versioned candidate index | 기존 rebuild/증분/rollback 재사용 및 안전성 검증 |
| `RetrievalOrchestrator` | 검색 문자열/타입/검증된 context | ranked hits/facets | v1 tier parity, v2 total 정확성/한계 표시 |
| `PublicPresenter` | public-safe hits | 9유형별 카드 DTO + 추가원천 확장 | UI 표시. signed URL/tenant 필드 차단 |
| `ContextRead` | 확인된 context key | 검증된 자료만 | 적용 의무가 아닌 *참고자료* 조회 |

**구현 의존성**: 독립 모듈은 추후 OBJ 계획에서 경계로 사용하되, 이 상세설계 자체는 구현 object/work package 발주를 승인하지 않는다.

---

## 3. 콘텐츠 유형 및 원천 어댑터 계약

### 3.1 현재 Public v1 9유형 유지

`KNOWLEDGE`, `GUIDE`, `REFERENCE_FORM`, `LEGAL`, `CSI_ACCIDENT`, `SAFETY_MATERIAL`, `CHEM`, `CHEM_REGULATION`, `PRECEDENT`. `KOSHA smartSearch`는 외부 provider이며 내부 인덱스 count와 합치지 않는다.

- 기존 route/URL/canonical_id/search DTO는 변경 없이 유지한다. 상세 링크에서 기존 `public_url` 재사용, 보존 불가능하면 명시적 redirect 계획을 Owner가 별도 승인한다.
- `RISK` 내부 어댑터가 생산 목록에 존재하지만 Public v1 9유형 allowlist와 별개이므로 기존 공개 타입이라고 선언하지 않는다.
- `KNOWLEDGE`는 Help와 Marketing Knowledge가 동일 public object_type 아래에서 **서로 다른 source_id/source_key**를 가진다. ID 단순 합치기 금지.
- `CHEM`(KOSHA MSDS), `CHEM_REGULATION`(KECO)는 같은 제품/같은 법적 규제 사실로 자동 동치 처리하지 않는다.

### 3.2 신규 3 API — 내부 v2 확장 타입 결정

| 공식 수집 원천 | 현재 snapshot | **설계상 v2 object_type** | canonical key 제안 | 우선 공개 정책 |
|---|---:|---|---|---|
| EXT037 `EXT037_CHEMICAL_SAFETY` / data.go.kr `15072442` | 7,189 | `CHEM_SAFETY_INFO` | `EXT037:{datano}` | 사전 심의 승인·필드 허용 검증 전에는 PUBLIC OFF |
| EXT132 `EXT132_HAZARDOUS_MATERIAL` / `15061055` | 7,277 | `HAZARDOUS_MATERIAL` | `EXT132:{chemicalno}` (raw `chemaicalno` 정규화) | 공개 정책 확인 전 PUBLIC OFF |
| EXT165 `EXT165_CHEMICAL_ACCIDENT` / `15072446` | 1,143 | `CHEM_ACCIDENT` | `EXT165:{datano}` | addr/place/원문 비식별·권리 검증 전 PUBLIC OFF |

**설계 결정**: 3종을 `CHEM`, `CSI_ACCIDENT`, `CHEM_REGULATION`과 무조건 합치지 않는다. 서로 다른 원천/사건/규제 사실이고 동일성은 확인되지 않았다. v2 신규 타입 식별자를 우선 사용하되 **기존 9개 공개 섹션에는 자동 추가하지 않는다**. 상세 렌더러/권리 QA/별도 Owner 타입 공개 승인을 거친 후 단계적으로 공개한다. 신규 타입이 실제 3개 UI 섹션이 될지, 상위 화학정보 탭의 하위 source 필터가 될지는 **표시 레벨의 후속 제품 결정**이며 영구 타입 식별자 변경을 수반하지 않는다.

### 3.3 Source adapter 최소 인터페이스 (의사계약)

```python
class CSIESourceAdapter(Protocol):
    source_id: str
    object_type: str
    def iter_current_public_candidates(self, *, cursor: str | None, limit: int) -> Page: ...
    def get_by_source_key(self, key: str) -> SourceRecord | None: ...
    def prepare_public_document(self, record: SourceRecord) -> PublicProjection | Rejected: ...
    def identify_version(self, record: SourceRecord) -> SourceVersion: ...
    def admit_for_public(self, record: SourceRecord) -> EligibilityDecision: ...
```

- `iter_current_public_candidates`는 bounded page, snapshot completeness/freshness 정책을 적용하고 source row를 복제하지 않는다.
- 동일 source_id+canonical_id는 한 가지 운영 writer path만 갖도록 한다. 수집 서비스와 검색 재색인 서비스의 책임을 분리한다.
- `source_ref`는 `{source_id, source_key, source_version, source_hash}` 형태로 표시하고 **공식 data.go.kr ID는 provenance 메타**로 별도 보존한다.
- API 3종의 자동 갱신 스케줄은 현재 증거대로 하루 단위이나, **수집 성공이 색인 성공을 뜻하지 않는다**. 완료 이벤트/outbox → search document update의 단계별 receipt가 필요하다.
- source-specific fields는 각 adapter의 **public allowlist**를 벗어나 전달할 수 없다. EXT165 주소/개인명/사업장명 텍스트는 기본 exclude하며 비식별 정책 승인 전 원문 미노출.

---

## 4. 표준 컨텍스트 사전 및 정규화

### 4.1 타입 네임스페이스 (v2)

| `context_type` | 표준 `context_key` 예시 | 강한 원천 증거 | 금지 오해 |
|---|---|---|---|
| `equipment` | `equipment:forklift` | 원천 사고객체/설비 코드·공식 지침의 대상 | 본문에 지게차 한 번 등장 → 모든 경우 확정 아님 |
| `task` | `task:welding` | 공식 작업명/작업 코드 | 작업 수행 유무·법정 의무 자동 판단 아님 |
| `process` | `process:excavation` | 원천 공정분류 | 공사명·위치만으로 공정 확정 금지 |
| `risk_factor` | `risk_factor:fall` | 공식 사고유형/위험 분류 | 사고 결과와 예상 위험 혼동 금지 |
| `sector` | `sector:construction` | 공인 산업/원천 분류 | 사업장 업종 의무 판정 금지 |
| `chemical` | `chemical:cas:108-88-3` | CAS 검증/공식 물질 식별자 | CAS만으로 제품·혼합물의 동일성 확정 금지 |
| `chemical` | `chemical:source:KOSHA:<chem_id>` | KOSHA source record의 고유 ID | `chem_id`와 CAS 문자열을 같은 key로 취급 금지 |
| `topic` (v2 extension) | `topic:risk-assessment` | 공식 주제 또는 승인된 통제규칙 | 원천 결과를 법령 적용 대상으로 추론 금지 |
| `legal_reference` (v2 explicit only) | `{law_id,version_id,article_id}` | 정확한 법령/조문 참조 | free-text 법령명만으로 direct link 확정 금지 |

기존 v1 `ALLOWED_CONTEXT_TYPES={process,task,equipment,chemical,legal_obligation,risk_factor,sector}`와 완전 동일하지 않다. **v2 확장 `topic`/`legal_reference`를 v1 코드에 무단 주입하지 않는다.** 내부 정규화 타입을 정의한 뒤, v2 mapping/validation을 version-aware하게 추가한다. `legal_obligation`을 검색 태깅 또는 개인 사업장 의무 산정에 활용하지 않는다.

### 4.2 Context assertion 계약 (논리 스키마)

```json
{
  "context_type": "equipment",
  "context_key": "equipment:forklift",
  "verification": "CONFIRMED",
  "evidence_kind": "STRUCTURED_SOURCE_FIELD",
  "evidence_ref": {"source_id":"CSI", "source_key":"<source-id>", "field":"accident_object"},
  "rule_id": "CSIE_EQ_FORKLIFT_001",
  "rule_version": "1.0.0",
  "dictionary_version": "csie-dict-v1",
  "source_version": "<source-version-or-hash>"
}
```

- `verification`: `CONFIRMED | CANDIDATE | REJECTED | STALE`.
- `evidence_kind`: `STRUCTURED_SOURCE_FIELD | EXACT_OFFICIAL_IDENTIFIER | CONTROLLED_PHRASE | HUMAN_VERIFIED | LLM_CANDIDATE`.
- **Public `verified_contexts`의 검색 필터 입력**은 `CONFIRMED`만. `CONTROLLED_PHRASE`는 원천 필드 의미와 부정문/인용문·문맥 규칙을 통과하고 QA 승인된 룰에 한해서 confirmed 가능. 그렇지 않으면 candidate.
- LLM 도출물은 기본 `CANDIDATE`이며 자동 승격하지 않는다. `REJECTED`/`STALE`은 추천·관련자료에서 제외.
- 원천 변경으로 `source_hash` 또는 버전이 바뀌면 assertion을 재검증하고, 재검증 전 이전 확정 관계를 보여주지 않는다.

### 4.3 사전 운영·저장 설계

- 최초 SoT는 **Git 버전 관리 사전 + 규칙/테스트 fixture**. 별도 전역 keyword×document 테이블을 만들지 않는다.
- 사전 레코드: `{type,key,preferred_ko,aliases_ko,aliases_en,official_code?,status,rule_version,review_ref}`. 동의어는 단순 표기 대응이며 상·하위 포함관계는 별도 verified rule 없이는 만들지 않는다.
- 변경 절차: GPT 문맥/규칙 설계 → Codex PR 구현/fixtures → GPT 독립검증 → Owner merge. 릴리즈된 사전의 immutable version/hash를 index generation에 기록한다.
- 향후 수천 개 이상의 컨텍스트에 승인 UI가 필요하면 관리 DB/RPC를 별도 OBJ로 검토하되 **WP01에서 신규 테이블 강제 생성 금지**.

### 4.4 문서 하나가 여러 컨텍스트를 갖는 경우

- 독립 confirmed context는 다수 허용, 자동 조합된 교집합으로 실제 작업수행/법령 적용을 주장하지 않는다.
- 동일 원천 문서가 여러 context에 나타나더라도 `object_type + canonical_id`로 dedup한다. 서로 다른 원천 문서는 CAS나 유사 제목만으로 하나의 canonical_id로 합치지 않는다.
- `search_match`는 Nori/BM25로도 생성될 수 있지만 `verified_context`로 승격하지 않는다.

---

## 5. 명시적 직접 관계 — 최소 계약

| relation_type | source → target | 허용 조건 | 시간/중복 정책 |
|---|---|---|---|
| `SOURCE_CITES_ARTICLE` | 가이드/지식 → LEG 조문 | 조문 공식 ID 또는 검증된 법명+번호+판본 | 양측 판본 저장, 구판/시행예정 구분 |
| `MATERIAL_IDENTIFIES_CAS` | 물질정보 → CAS | 원천 CAS 형식 검증, 동등성 주장 없음 | 원천 버전과 함께 invalidation |
| `GUIDE_SUPERSEDES` | 지침 신판 → 구판 | 발행기관 번호/개정 판본 명시 | 관계 방향 고정 |
| `DOCUMENT_VARIANT_OF` | PDF/DOCX/언어판 → 대표 문서 | 원천 제공 식별자 동일성 | title 유사도만으로 병합 금지 |
| `ORIGIN_EXPLICIT_REF` | 자료 → 원천 링크 | 공식 URL 또는 source-issued reference | 권리/URL 유효성 검증 |

- 단순 `RELATED_SIMILARITY`는 **명시적 관계가 아니라 검색 후보**. Related API에서 `match_basis=LEXICAL`로 표기, verified direct와 분리한다.
- `relation_key`는 stable IDs이며 evidence/source_version/verification/status/expiry 필수. test `knowledge_relation_edges`를 그대로 운영 SoT로 사용하지 않는다.
- 첫 구현은 **원천이 갖고 있는 직접 참조의 read-time projection** 우선. 별도 승인 관계 레지스트리 DB는 실제 필요성을 입증하고 별도 Object 승인 후 추가한다.

---

## 6. Canonical SearchDocument v2 — 증분 확장 설계

### 6.1 기존 필드 유지

현행 `object_type`, `canonical_id`, `source_id`, `source_key`, `title`, `summary`, `search_text`, `aliases`, `keywords`, `subjects`, `context`, `public_url`, `saas_url`, `publication_status`, `visibility_scopes`, `source_updated_at`, `content_hash`, `indexed_at`는 기존 v1 호환 보존. 새 인덱스의 v2 추가 필드를 기존 v1 타입 정의로 암묵적 변환하지 않는다.

### 6.2 v2 신규 필드 후보 및 타입

| field | 타입 | 규칙 |
|---|---|---|
| `contract_version` | keyword | `csie-search-doc/2`; 구 인덱스에 무단 추가 금지 |
| `source_record_id` | keyword | 원천 공식 ID, `canonical_id`와 별도 |
| `source_version` | keyword | source 판본/hash, 없으면 null과 version_quality 라벨 |
| `source_hash` | keyword | 공개 projection 대상의 원천 hash; raw 재게시 금지 |
| `current_status` | keyword | `CURRENT | SUPERSEDED | FUTURE_EFFECTIVE | UNKNOWN`; 법령 effective 판정 아님 |
| `rights_mode` | keyword | 원천별 정책 `METADATA_ONLY | LINK_ONLY | LIMITED_PREVIEW | RENDER_ALLOWED | BLOCKED` |
| `rights_policy_version` | keyword | 공개 정책/승인 revision |
| `context_assertions` | nested | v2의 확정 상태/근거/룰 버전 포함; public-safe evidence_ref만 |
| `context_flat_keys` | keyword[] | confirmed context의 typed key만; 정확 필터·집계용 |
| `facet_keys` | keyword[] 또는 명시 typed field | 검증된 source category/sector/format 등. 무제한 동적 필드 금지 |
| `direct_references` | nested | public-safe 정확 source ref, `VERIFIED`만 검색 노출 |
| `display_meta` | 제한 타입별 object, index=false 우선 | 카드 표시용 일자·발행처·사고유형 등 공개 필드만; 독립 sanitizer |
| `dictionary_version` | keyword | 원자적 사전 snapshot ID |
| `normalized_identifiers` | keyword[] | `CAS:108-88-3`, `GUIDE:<no>` 등 typed namespace |
| `effective_at` / `published_at` / `occurred_at` | date, optional | 의미 다른 원천 일자 분리. `source_updated_at`/indexed_at로 대체 금지 |
| `index_generation` | keyword | 검증/집계 스냅샷 식별자 |

**주의**: 이 표는 v2 candidate mapping의 기술 계약이다. 활성 v1 mapping에는 이 필드가 없으며, `opensearch_mapping.py`는 현재 v1 인덱스 이름을 생성한다. 별도 `v2` mapping hash/name/candidate index 절차가 필요하다. 현재 index가 동적 매핑을 허용하더라도 그 우연한 동작을 v2 완료라고 취급하지 않는다.

### 6.3 public-safe 예시 (모두 합성 값)

```json
{
  "contract_version":"csie-search-doc/2",
  "object_type":"CSI_ACCIDENT",
  "canonical_id":"fixture-csi-001",
  "source_id":"CSI",
  "source_key":"fixture-source-001",
  "title":"지게차 관련 사고(합성 테스트)",
  "publication_status":"PUBLISHED",
  "visibility_scopes":["PUBLIC"],
  "rights_mode":"METADATA_ONLY",
  "context_flat_keys":["equipment:forklift"],
  "context_assertions":[{"context_type":"equipment","context_key":"equipment:forklift","verification":"CONFIRMED","evidence_kind":"STRUCTURED_SOURCE_FIELD","rule_version":"1.0.0"}],
  "source_version":"fixture-v1",
  "dictionary_version":"csie-dict-v1",
  "index_generation":"fixture-shadow-1"
}
```

### 6.4 금지 사항

- `company_id`, `factory_id`, `user_id`, 진단 응답·법 적용 판정, 원문 주소·개인명, secret, access_token, private signed URL 등은 **key 이름과 값 내용 모두 검사**. v1 `FORBIDDEN_DOCUMENT_KEYS`만으로 `search_text` 문자열의 민감정보 검출까지 보장하지 못하므로 source별 public allowlist + sanitizer + fixture 테스트가 필요하다.
- 기밀/tenant 문서가 아닌 경우에도 원문 저작권이 불확실하면 full text 색인·저장·공개를 확대하지 않는다.
- 빈 타입 목록은 **match-all이 아니다**. 호출 계층과 reader 양쪽에서 fail-closed empty-result 또는 explicit unavailable를 보장한다.

---

## 7. Retrieval 및 OpenSearch v2 설계

### 7.1 검색 3개 모드

| 모드 | 조건 | 일치 근거 | 결과 라벨 |
|---|---|---|---|
| `LEXICAL` | 검색어 `q` | 기존 ID/title/alias/dictionary/Nori/fuzzy T0~T9 | `검색어 일치` |
| `VERIFIED_CONTEXT` | canonical `context_type:key` | `CONFIRMED` + 현재 버전 + 공개 허용 | `확인된 주제 관련자료` |
| `DIRECT_REFERENCE` | source article/guide/CAS/official ref | exact ID + 검증 근거 + 유효 판본 | `원천에서 직접 연결된 자료` |

동일 문서가 여러 모드에 걸리면 문서를 중복 표시하지 않고 **중복 일치 근거는 유지**한다. 최우선 라벨은 DIRECT_REFERENCE > VERIFIED_CONTEXT > LEXICAL이지만, 일반 검색 순위를 바꾸지 않도록 **v2 related-mode 내부에서만** 라벨 우선순위를 적용한다.

### 7.2 검색 실행과 집계

- **1차 구현 접근은 기존 `SharedRetrievalEngine`과 `_msearch`의 tier 우선순위 및 public filters를 보존**한다. /sections 9회 순차 호출을 성급히 통합하지 않는다.
- v2 API는 **hits 부분(랭킹)**과 **aggs 부분(정확한 타입별 총수/필터)**를 분리한 논리 응답을 갖는다. 동일 alias generation/동일 필터·query plan을 기준으로 집계한다. OpenSearch의 `track_total_hits` budget과 aggregation 비용은 shadow에서 결정.
- v1 total (`len(dedup(candidates))`)은 `candidate_total`로만 유지하여 v2 `total`에 재사용 금지. `total: {value, relation: "eq" | "gte" | "unknown"}`를 사용한다. `eq`는 정확한 hit counting이 확보될 때만, `gte`는 하한 근거가 있을 때만, 그 외 null/unknown.
- `display_group_count`(판본/언어/중복 묶기 후 개수)는 `total`과 분리한다. 중복 묶음과 facet 기준을 바꾸지 않은 채 total로 표시 금지.
- 통합 section 응답에서 KOSHA provider 실패는 `external.status=unavailable`로 격리; OpenSearch 전체 실패는 503으로 관측 가능하게 유지. 섹션 일부 독립 실패는 부분 성공/오류 리스트 분리.
- `_msearch`는 **HTTP 왕복 횟수 절감이지 OpenSearch shard workload 소거가 아님**. 미측정 임계값·p95 개선율은 설계 PASS 기준으로 고정하지 않는다.
- `filters/terms+top_hits` 단일 aggregation으로 변경하는 것은 **유형별 tier 순서/권리 범위/top10 parity가 통과된 후의 최적화 후보**일 뿐, 1차 필수 구현이 아니다.

### 7.3 Alias, index, rollback

1. 실제 운영 alias/physical index는 미확인 — **운영 변경 시점의 READ ONLY prerequisite**.
2. v2 candidate index naming `tai-shared-search-v2-<runid16>` (설계안), shadow alias 별도 예: `tai-shared-search-csie-shadow`, 기존 `tai-shared-search-current` 불변.
3. v2 rebuild는 기존 `SearchWriter`·manifest·validate_run·atomic promote/rollback 개념 재사용. 운영 alias action 생성 함수의 입력/인덱스 이름 가정이 v1 고정되어 있어 version-aware refactor 및 regression 테스트 필요.
4. shadow 검증: mapping hash, Nori analyzer, per-source count parity, public-only sanitation, representative queries, index write failures=0, current/rights/stale, incremental-delta/rollback.
5. Owner 별도 승인 이후에만 운영 alias를 **한 번** 변경하며 기존 물리 index 보존 및 rollback 확인. 운영 shadow index 생성/쓰기조차 본 WP01에서 승인하지 않는다.
6. 지표·검증 전 새 public v2 API가 없더라도 기존 API는 정상 유지하는 방식으로 단계별 배포한다.

---

## 8. API v2 외부/내부 계약 (설계형, 구현 전)

### 8.1 공개 검색 v1 보존

- `GET /public/safety-search?q=&type=&within=&page=&page_size=` unchanged.
- `GET /public/safety-search/sections?q=&section_size=` unchanged.
- `GET /public/safety-search/kosha`는 외부 검색으로 유지.
- 기존 `SearchResult.to_dict()` 필드 삭제/재명명/의미 재사용 금지. 특히 `rank_tier`, `matched_on`, `subject_*`를 검증된 물리 context의 증거로 바꿔 부르지 않음.

### 8.2 Public v2 endpoints 후보

```http
GET /public/safety-search/v2/sections?q=지게차&section_size=6
GET /public/safety-search/v2/search?q=지게차&type=guide&page=1&page_size=10
GET /public/safety-search/v2/related?object_type=CSI_ACCIDENT&canonical_id=<id>&limit=8
GET /public/safety-search/v2/context?context_type=equipment&context_key=equipment:forklift&limit=10
```

- `related`는 소스별 대상 문서를 server-side fetch하고 **원천 권리·current를 재검증**. 누구나 넣는 object_id로 tenant lookup이 되지 않도록 Public allowlist와 원천 가시성 재검증.
- `context` endpoint는 **public-approved stable key만** 입력받으며 raw 자유 텍스트·사업장 설비 ID·private tenant context 전달 금지. unknown type/key는 `422` 또는 empty 결과를 계약에 따라 고정.
- SaaS/유료/화학 소비자는 각각 **기존 BFF/서비스 내부 권한 검증** 후 공개 참고자료를 조회. 검색 서비스가 tenant 목록/진단 답변/화학 재고를 보관하거나 판단하지 않음. 실제 서비스별 API endpoint 추가는 나중에 별도 OBJ에서 확정.

### 8.3 Public v2 응답 예시 — 합성

```json
{
  "contract_version":"csie-public-search/2",
  "query":"지게차",
  "index_generation":"fixture-shadow-1",
  "status":"ok",
  "sections":[{
    "type":"guide",
    "total":{"value":null,"relation":"unknown"},
    "display_group_count":null,
    "facets":[],
    "items":[{
      "object_type":"GUIDE",
      "canonical_id":"fixture-guide-001",
      "title":"지게차 안전 작업지침 (합성)",
      "public_url":"/safety-guide/fixture-guide-001",
      "source_id":"KOSHA_OFFICIAL_GUIDE",
      "match_basis":"LEXICAL",
      "rights_mode":"LINK_ONLY",
      "display_meta":{"date_label":"발행일","date_value":null}
    }],
    "has_more":false,
    "status":"ok"
  }],
  "external_kosha":{"status":"separate","items":[]}
}
```

- `total=unknown`은 **실측이 없을 때의 정상 표현**이며 0을 의미하지 않는다.
- `has_more`는 정확한 cursor/next detection 계약으로만 true/false를 설정. v1 후보 200 제한으로 인해 아직 뒤 페이지에 문서가 있는지 판단할 수 없다면 `has_more=null`/unknown을 허용한다.
- v2 필드 `rights_mode`/`display_meta`/`match_basis`는 public-safe serializer 화이트리스트를 통해 생성. 내부 score/쿼리DSL/evidence raw/tenant/secret 미노출.
- 상태: 정상 `ok`, 매치 없음 `empty`, 섹션부분오류 `partial`, 서비스장애 `unavailable`, 공급원 분리 `external_unavailable`. HTTP 422/503 및 내부 코드 구분. UI는 empty와 unavailable을 동일하게 렌더링하지 않음.

### 8.4 상세 페이지와 URL 정책

- 기존 URL과 canonical 유지: `/safety-search/legal/{id}`, `/accident/csi/{uuid}`, `/knowledge/{slug}`, `/safety-guide/{id}`, `/safety-news/{id}`, `/reference-form/{slug}`, `/msds/{chem_id}`, `/precedent/{id}`.
- 9유형별 화면은 기존 `TAI_SAFETY_SEARCH_REBUILD_MASTER_PLAN`의 텍스트행/이미지격자/전용 detail renderer를 구현 대상으로 재사용. 본 설계는 **읽기 계약만 정하고 상세 레이아웃을 중복 정의하지 않는다**.
- `CHEM_REGULATION`은 기존 CAS 검증·MSDS 연결 규칙 존중. 신규 3종은 공개 권리·detail URL/robots/중복검증 후 신규 상세 URL/섹션 제공.
- 검색 결과 SSR은 `noindex,follow`; 상세페이지 indexability, sitemap, canonical은 원천별 정책 유지. `via=tai_search` 같은 추적 param은 canonical에서 제거.

---

## 9. 원천 변경·갱신·삭제의 일관성

**수집완료 → 문서 정규화 → eligibility → 색인 → public**의 증거를 별도 관리한다.

```text
SOURCE_SNAPSHOT_COMPLETED
 -> NORMALIZED / MAP_ACCEPTED or MAP_REJECTED
 -> RIGHTS_AND_CURRENT_ADMITTED
 -> OUTBOX_IDEMPOTENT_ENQUEUE
 -> WRITER_PREPARE / HASH_NOOP or UPSERT / DELETE
 -> INDEX_RECEIPT(index_generation, source/version/hash)
 -> READ_ALIAS_VERIFIED
 -> PUBLIC_RESPONSE_VERIFIED
```

- FULL SNAPSHOT 3종: 새 current snapshot과 previous의 `source_key`를 비교하여 **신규/변경/삭제**를 결정. 누락/부분 snapshot이 완료로 오인되지 않게 source completeness gate 요구.
- 기존 `search_index_outbox`, incremental claim/reconcile 및 rebuild fence 코드를 재사용하고, 큐 조회 timeout/미확인 항목은 운영 preflight에서 확인한다.
- 해시 NOOP 및 idempotent duplicate 처리. `REMOVED`/`HOLD`/권리 취소된 문서는 public alias에서 제거·차단하는 방안이 기존 경로와 일치하는지 테스트.
- outbox backlog·index lag를 `source_completed_at`, `normalized_at`, `indexed_at`, `public_verified_at`로 분리. 날짜/시행일을 색인 시각으로 덮어쓰지 않는다.
- alias가 전환되어도 오래된 incremental writer가 구 index를 갱신하지 않도록 generation/fence/active-alias check 필요. 실패 시 retry 한도와 DLQ/blocked 표시.
- 한 원천의 인증/수집 오류가 기존 인덱스 전체 삭제를 야기하지 않도록 **fail-closed, last-good 유지**. 권리취소/삭제는 별도 안전 우선 처리.

---

## 10. 법령·화학·공개권리 책임 경계

### 10.1 법령

- **개발거버넌스 SoT**: `45cm-prj-db/governance`의 Constitution/Contract/Policy/Rule/Guide. **국가 법령 검색 read source**: `leg-prod/public.law_master` → `law_version` → `law_article`.
- `law_master.current_version_id`는 **source에서 선택된 current pointer**일 뿐 반드시 오늘 시행 중은 아니다. 2027년 시행 예정 표본이 current 상태로 관측됐다.
- 법령 index/카드는 `법령명`, `조문번호`, `version_mst_no`, `시행일`, `시행상태(as_of date 기준 판정 가능할 때만)`를 구분하고, **원천 원문 대비 검증되지 않은 오늘 적용 여부 라벨은 UNKNOWN**.
- v2 검색은 조문/법령 reference retrieval이다. `applies_to_company`나 의무/위반 여부는 기존 LEG diagnosis route의 책임. 시행예정도 검색할 수 있지만 시행중처럼 표현하지 않음.

### 10.2 화학·규제

- KOSHA MSDS product/source identity, CAS, KECO chemicals/regulatory facts, EXT037/132/165는 **서로 다른 원천**이다. CAS는 cross-reference 후보이지 제품·혼합물 동일성 증거가 아니다.
- `CHEM` public mode(`off/seo_preview/full`) 및 별도 MSDS router gate를 존중한다. `type=chem` off 시 결과는 반드시 CHEM 비노출·cross-type 누출 0.
- KECO/EXT132 규제 정보는 공식 데이터 사실을 출처·기준일과 함께 제공하되 사용자 회사에 적용되는 화학 규제·저장허용량·기준초과/처벌을 검색에서 계산하지 않는다.
- EXT165 원문 `addr` 등의 직접 식별·민감 가능 필드는 비식별/최소수집/공개 범위 승인 전 `search_text`, `summary`, `display_meta`, 관련 검색 결과에서 모두 제외.

### 10.3 권리·보안

- 권리 최소 모드: `BLOCKED` → 미색인/미공개; `LINK_ONLY`/`METADATA_ONLY` → 허용 메타만+공식 링크; `LIMITED_PREVIEW` → 허용한 작은 발췌/이미지만; `RENDER_ALLOWED` → 승인된 조건 내 본문/이미지.
- 공개 원문 URL, 요약/썸네일, PDF 파일 bytes, 생성한 파생 이미지는 **각각** 별도 권리 검증. `KOSHA_GUIDE LINK_ONLY` 원문 직접 재호스팅 금지.
- 원천별 계정 운영 심의/라이선스/상업적 이용/삭제 요구를 catalog 기본 문구만으로 승인했다고 간주하지 않는다.
- public response/raw debug에 secret, signed URL, service role, 원천 API 계정, 민감 주소, tenant IDs 노출 0. 접근 로그/분석 로그에도 토큰/개인정보 금지.
- Supabase public 노출 여부가 필요한 후속 관계 테이블에는 RLS + 최소 GRANT, view `security_invoker`, ownership policy, read API scope; **WP01에서는 테이블/migration 생성 없음**.

---

## 11. 수용·회귀 테스트 설계 (구현 전 고정 기준)

### 11.1 필수 정적/fixture 테스트

| ID | 시나리오 | 기대값/차단 |
|---|---|---|
| T-01 | `type=chem`, mode off | empty/unavailable, **다른 object_type 결과 0** |
| T-02 | 다른 typed+mode combinations | 정확히 요청 타입만. 9유형 allowlist 회귀 0 |
| T-03 | 민감/tenant 필드가 key에 존재 | writer rejects; public 문서에 금지 필드 0 |
| T-04 | 민감 문자열이 허용 필드 안에 포함 | public sanitizer fail-closed/review; 재색인 금지 |
| T-05 | `chemical:source:<chem_id>` vs `chemical:cas:<CAS>` | 서로 다른 ID, explicit match 없이는 동일성 금지 |
| T-06 | 지게차 문서 본문 단순 부정/인용만 존재 | lexical 가능, verified-context 자동 확정 불허 |
| T-07 | source 버전 변경/권리철회/삭제 | 이전 confirmed link·색인 무효화, last-good/삭제 정책 검증 |
| T-08 | `current=true`, 시행일 미래 | `현재 시행중` 문구 금지, 시행 예정/unknown 정확 라벨 |
| T-09 | v1 public search DTO regression | 공개 필드/URL/총수의 기존 *의미* 유지, v2와 total 혼동 금지 |
| T-10 | KOSHA external timeout/404 | 내부 결과 영향 0, unavailable과 empty 구분 |
| T-11 | stale/index generation mismatch | 확정 관련자료/집계 제공 차단 또는 명시 stale 처리 |
| T-12 | 중복 원천 ID/타입·잘못된 canonical link | 결정론적 dedup 또는 reject, 교차 원천 오합병 0 |
| T-13 | query noresult/특수기호/CAS/empty | 0/unknown 명확 표시, 무관 related 강제 삽입 금지 |
| T-14 | `DIRECT_REFERENCE` 없는 문서 | BM25 hit만으로 법령 정확 인용·의무 적용 라벨 금지 |

### 11.2 골든 검색어·원천 검증

- 4 기준: `지게차, 용접, 굴착, 추락`. 추가: `비계, 밀폐공간, 위험성평가, 톨루엔, 108-88-3, <의도적 미일치 키워드>`, 필요 시 복합 작업·동의어.
- 기본 Public 9유형 + KOSHA external; 새 EXT3 v2 타입은 공개 gate 통과 뒤 별도 행. 현행 Graph 11,776은 **relation 수만 비교**하고 정답이라고 간주하지 않는다.
- 각 대표 결과 Top10: `{query, type, canonical_id, title, rank_tier, match_basis, rights, date_label, source, public_url, is_current, human_relevance}`. manual adjudication의 sample ID·판정자가 필요하다.
- 지표: precision@10, 누락/오탐, high-risk legal/chemical false claim 수, exact total vs candidate_total 차이, orphan public_url, median/p95 latency, index lag, shard/heap, 권리·보안 침해 0. 운영 baseline 없이 개선율 숫자를 PASS 조건으로 확정하지 않음.
- 성능 POC: 기존 tier baseline A vs query+agg 후보 B vs split/cache 후보 C를 동일 인덱스 generation/필터/키워드로 비교. **A parity를 기준**으로 B/C의 순위 저하·쿼리 비용/부하를 Owner에게 결과로 제시하여 최종 선택.

### 11.3 실제 운영 적용 전 Hard Gates

- `G-DEPLOY`: 대상 service/repo/env 및 active deploy SHA 확인.
- `G-INDEX`: current alias → exact physical index, mapping hash, Nori plugin, shard/replica, docs/storage stats 확인.
- `G-LINEAGE`: source snapshot → normalized doc → candidate index → alias → 실제 public URL 및 권리/버전 연결. EXT3 각각 별도.
- `G-QA`: 위 대표 검색 실제 response/Top10/total의 정의·권리/민감정보·CHEM off mode 판정.
- `G-OPS`: query budget/latency, outbox lag, rollback previous index/alias, canary/flag 상태.
- 어느 하나 BLOCKED여도 **관련 운영 변경만 금지**하고 설계 작업을 되돌리지 않는다.

---

## 12. 계측, 성능, SEO, 제품 연동

- 기술 지표: `source_snapshot_age`, `normalization_reject`, `public_rights_reject`, `index_noop/upsert/delete`, `outbox_backlog`, `indexed_lag`, `index_generation`, `search_query_latency`, `search_error_by_section`, `total_relation`, `context_confirmed/candidate/stale`.
- 기존 Railway CPU/메모리와 HTTP duration 표본은 **단위/표본 수 일부 미확인**. 승인되지 않은 수치 단위를 붙이거나 전체 p95 목표로 확대하지 않는다.
- 사용자 행동: `search_submit`, `section_open`, `result_open`, `related_open`, `source_exit`, `diagnosis_cta`. admin/test/bot traffic과 실제 유입 구분. 탐색 실적과 유료 매출 효과는 별도 실측.
- SEO: 검색 SSR `noindex,follow` 유지, 기존 detail canonical/sitemap 보존, 검색 조합별 자동 인덱싱 금지. 주제 허브는 별도 컨텐츠 품질 승인 후 추가.
- 단계 확장: Public Search/Detail → SaaS 참고자료/설비·작업 Context BFF → CHEM MSDS/재고 참고자료 → 진단 결과 원문근거 → 알림/AI 별도 오브젝트. 각 모듈의 사용자·도메인 권한과 버전은 계속 별도 유지.

---

## 13. 위험·의존성·결정 기록

| ID | 위험 또는 미해결 사실 | 지금의 GPT 설계 판단 | 검증 시점 |
|---|---|---|---|
| DR-01 | OpenSearch alias/index 실환경 미확인 | v2 shadow + 기존 alias 유지. **설계 진행**, 운영 전 필수 확인 | search PoC/운영 Gate |
| DR-02 | EXT3 수집 완료, actual INDEXED/PUBLIC 불명 | 신규 소스 어댑터+권리 게이트 설계; 수집 건수를 색인 건수라 부르지 않음 | adapter implementation/운영 Gate |
| DR-03 | v1 total 후보 개수만 제공 | public v2 별도 `total{value,relation}`. 기존 total 보존 | retrieval/API OBJ |
| DR-04 | CHEM typed OFF 필터 결함 | **별도 P0 수정 WO**. WP01 문서 PR에 코드 혼입 금지 | Owner 승인한 별도 핫픽스 |
| DR-05 | EXT165 dirty working tree / 3파일 hash drift | 기존 스트림 보호, checkout/브랜치 격리, reset/clean/수정 금지 | Codex PR 준비 즉시 |
| DR-06 | 법령 current vs 시행중 | provenance/current/effective label 별도; LEG 법 적용 판단 분리 | legal adapter/UX QA |
| DR-07 | GUIDE/MATERIAL/KOSHA/MSDS 권리 혼재 | source-specific license fail-closed, public allowlist | source adapter QA/운영 Gate |
| DR-08 | SaaS/Paid/Chem 소비 계약 다름 | API v2 직결 강제 금지, service BFF 중간 계약 | 소비자별 OBJ |
| DR-09 | dynamic contexts의 운영 저장/관리 규모 미확정 | Git 사전 + SearchDocument context 우선; 관계DB 남발 금지 | context object test |
| DR-10 | v2 index 도입 비용/성능 미측정 | tier parity 우선; 비용 측정 후 최적화 | search PoC/운영 Gate |

**설계 결과**: DR-01/02/05/07/10은 *상세설계 문서 승인*의 반복 조사 사유가 아니다. 운영 적용 또는 해당 기능의 PUBLIC 활성화만 제한한다. P0 CHEM 결함은 운영과 독립된 작은 수정 대상으로 관리한다.

---

## 14. 설계 승인 및 OBJ 기반 구현계획 이행 순서

이 문서는 **설계 결과물**이며 아직 Object/WP 구현작업계획서가 아니다. 다음 순서 고정.

```text
GPT WP01 상세설계 작성 [본 문서]
  ↓
Codex: 문서만 독립 브랜치에 추가 → DRAFT PR 제출 (no code)
  ↓
GPT: 고정 HEAD/파일 목록·설계 정합성 독립검증
  ↓
Owner: 설계서 승인 및 문서 PR merge 승인
  ↓
GPT: 별도 CSIE Object Implementation Plan 작성 (OBJ 단위, 의존성/게이트/WO)
  ↓
Codex: 계획서 문서 PR 제출 → GPT 독립검증 → Owner 승인
  ↓
GPT: **한 번에 하나의 승인된 OBJ/WP 구현 WO** 발행
  ↓
Codex: 구현/테스트/증거 → GPT 독립검증 → Owner PR merge/DB/index/deploy 별도 승인
```

### 14.1 OBJ 구현계획서 작성 시 분해 기준 (목록은 후보, 아직 발주·승인 아님)

| 후보 OBJ | 책임 경계 | 주요 선행 |
|---|---|---|
| `OBJ-00` | 설계/테스트 계약 및 P0 CHEM 회귀 분리 | WP01 문서 승인 |
| `OBJ-01` | 표준 컨텍스트 사전·검증 규칙 | OBJ-00 |
| `OBJ-02` | Source Eligibility/원천 어댑터(기존 9 + EXT3) | OBJ-01 |
| `OBJ-03` | CSIE v2 SearchDocument·rights/version sanitizer | OBJ-01/02 |
| `OBJ-04` | OpenSearch shadow index/writer/refresh+rollback | OBJ-03 |
| `OBJ-05` | Search v2 retrieval/totals/facets 및 related/context read | OBJ-04 |
| `OBJ-06` | Public Search UI (9유형, extra source gated) | OBJ-05 |
| `OBJ-07` | 유형별 상세/관련자료/원문권리/SEO | OBJ-05/06 |
| `OBJ-08` | SaaS·CHEM BFF 참고자료 연계 | OBJ-05, 별도 승인 |
| `OBJ-09` | 검증·성능·운영 alias canary/rollback | 각 관련 OBJ 뒤, 운영 승인 별도 |

이 표는 시스템 경계를 식별하는 **후속 Object Plan의 입력**일 뿐, 구현 순서를 지금 자동으로 승인하는 표가 아니다. 실제 Object Plan에서 범위/정량 수용 기준/테스트/branch/DB·index 권한/원천 권리/선행 PR을 분리한다. **Codex는 OBJ 계획이나 구현 코드를 이번 설계 PR에 추가하지 않는다.**

### 14.2 WP01 설계문서 승인 기준

1. 이 파일만 대상으로 하는 docs-only PR: 변경 파일 범위가 사전 허용 문서 경로, code/SQL/config/migration/lock/환경 파일 0.
2. 기존 9유형·v1 DTO/API·현재 원천 SoT와 충돌 없음, EXT3 3개 원천 식별/권리/공개 gate 명확.
3. lexical/context/direct 및 candidate/confirmed/rights/current/effective의 **다른 의미를 혼합하지 않음**.
4. 운영 미확인 사항은 release gate로 표시하며, 사실로 대체하지 않음.
5. 코드/DB/index/배포 변경 0, 독립 HEAD SHA 및 file list receipts 제출.
6. GPT 독립검증 `PASS` 뒤 Owner가 설계 승인 및 merge 승인. 그 전 구현 계획서 발행/구현 진입 금지.

---

## 15. 소스와 증거 교차표

| 설계 입력 | 재현 기준/문서 |
|---|---|
| v1 타입·필터·CHEM off 위험 | `tai-api@172a0c0a:routers/public_safety_search.py:39-163`; `services/shared_search/opensearch_reader.py:41-66`; R1 REV1 `GPT_CHEM_OFF_FIXTURE_EVIDENCE.json` |
| 기존 v1 contract | `tai-api@172a0c0a:services/shared_search/{contract.py,result.py,retrieval.py}` |
| v1 Nori/index/stored fields | `tai-api@172a0c0a:services/shared_search/{opensearch_mapping.py,opensearch_store.py}` |
| source adapter registry | `tai-api@172a0c0a:services/shared_search/production_bindings.py:939-970` |
| source snapshot / Graph | `CSIE_WP00_SOURCE_INVENTORY_2026-10-12.md`, `CSIE_WP00_KEYWORD_BASELINE_2026-10-12.md` |
| Public WWW/UX | `tai-www@3b10ece1:src/lib/server/safetySearch.js`, `src/pages/safety-search.astro`, `TAI_SAFETY_SEARCH_REBUILD_MASTER_PLAN_2026-10-12.md` |
| current/rights/tenant | `CSIE_WP00_SEARCH_CONTRACT_AND_INDEX_2026-10-12.md`, `CSIE_WP00_RISKS_AND_UNVERIFIED_2026-10-12.md` |
| 2026-10-12 배포/fixture | `CSIE_WP00_R1_REV1_GPT_INDEPENDENT_REVIEW_2026-10-12.md` 및 REV1 Codex 원본 ZIP receipts |
| 기존 Graph의 성격 | `tai-www/docs/ops/tai-www/PLAN_safety-knowledge-graph_v1.md` (테스트 회귀 보존, 운영 정답으로 승격 금지) |

### 15.1 Owner 설계 결정값 (문서 승인 시 고정 요청)

- `D-01`: CSIE v2 내부 확장 3타입의 명칭/분리 정책 승인 여부.
- `D-02`: Public v1 contract 보존 및 v2 additive-only 채택 승인 여부.
- `D-03`: 컨텍스트 사전 Git-version-first, 정확 관계 최소화 승인 여부.
- `D-04`: Public-first shadow index 및 추후 SaaS BFF 방식 승인 여부.
- `D-05`: CHEM P0 별도 핫픽스 승인 여부(실행은 별도 WO).

**END — CSIE WP01 설계안, 문서 PR 전용, 운영 쓰기/구현 미승인.**
