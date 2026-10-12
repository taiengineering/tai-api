---
class: plans
type: OBJECT_IMPLEMENTATION_PLAN
scope: csie
project: tai-api/tai-www
version: '1.0'
status: GPT_PLAN_DRAFT_DOCS_ONLY
architect: GPT
executor: Codex
owner: TAI Owner
---

# CSIE — 공통 안전정보 활용 엔진 오브젝트 기반 구현계획서 v1.0

- **문서 ID**: `CSIE-OBJECT-IMPLEMENTATION-PLAN-001`
- **날짜**: 2026-10-12 (KST)
- **상위 설계**: `CSIE_WP01_COMMON_ENGINE_DETAILED_DESIGN_v1_2026-10-12.md`
- **목표**: 기존 OpenSearch 검색엔진과 원천 어댑터를 최대한 재사용하면서, 근거 있는 문서 컨텍스트·안전한 관련자료·원천별 권리 및 버전 정보·서비스 재사용 API를 단계적으로 제공한다.
- **역할**: GPT=분석/설계/작업지시/필요시 독립검증, Codex=실행/테스트/증거, Owner=범위/병합/운영변경 승인.
- **문서의 효과**: Object/WP 계획 수립. 문서 등록은 코드 구현·DB migration·검색 index write·배포를 승인하지 않는다.

## 0. 불필요한 검증 제거 — 실행 거버넌스 개정

### 0.1 변경 영향 기준의 검증 선택

| 변경 범위 | 검증/종료 기준 | 하지 않는 일 |
|---|---|---|
| **문서 전용** `.md`, 그림, 계획서 | 실제 변경 파일명/내용·원문 누락 확인. 문서 PR/커밋 증거만. 의미상 Owner 승인 필요 시 1회 승인 | 소스 검사 반복, 전체 테스트, DB·OpenSearch/배포 조회, 별도 GPT 기술 독립검증 게이트 |
| **소스 변화 없음 + 이미 확인된 코드** | 기존 고정 증거 승계; 추가 수행 0 | 반복 소스 조사, 같은 QA 재실행 |
| **코드 변경** | 해당 Object/WP 영향 범위의 단위·계약 테스트, 변경 diff 및 보호 규칙 검증 | 전체 회귀/E2E/성능검사 자동 확대 |
| **DB schema / migration 변경** | 변경 migration만 리허설/rollback·RLS/GRANT 관련 확인, Owner DB 적용 별도 승인 | 무관 DB 전수검사 또는 임의 운영 쓰기 |
| **OpenSearch mapping/index/alias 변경** | 대상 candidate index의 계약·권리·parity·rollback 검증, Owner 별도 승인 | 설계/문서 단계에서 운영 인덱스 조회 강제, 과거 실사 반복 |
| **실제 서비스 배포/공개 활성화** | 변경된 라우트/화면 최소 smoke, 데이터 공개·권리·권한, 배포 SHA 및 롤백 확인 | 모든 기존 서비스의 E2E 반복 |

**실행 원칙**: `No material change → No revalidation`. 테스트는 변경으로 위험이 발생하는 경계에서만 실행한다. 작업자가 버전/증거를 확보하지 못하면 해당 **운영 액션**만 보류하며 설계와 다른 독립 WP를 차단하지 않는다. `PR_READY`/QA 판정은 **새 diff가 있을 때만** 의미가 있다. 원격 main에 이미 포함된 코드를 중복 PR 생성하지 않는다.

**Owner 승인 최소화**: 문서 PR은 파일 범위만 확인하고 일괄 승인 가능. 실제 소스 구현은 WP별 PR 승인. 운영 DB·index alias·feature flag·배포는 각각 명시 승인 필요. GPT의 분석/설계 책임은 유지하되 **변경이 없는 문서에 기능 독립검증을 형식적으로 발급하지 않는다**.

### 0.2 이미 완료된 내용을 재개발하지 않는다 (2026-10-12 원격 main 기준)

| 저장소 | 원격 main SHA | 이미 존재하는 계약 |
|---|---|---|
| `taiengineering/tai-api` | `cf0af61cb9c734de0db3fa3cba40f93264a04f0b` | WP-01 CAS enrichment, WP-03 chemical accident API, WP-04 3개 검색 adapter, `REFERENCE_FORM` 포함 기본 13개 adapter, marketing 선택 분기 |
| `taiengineering/tai-www` | `f47235a9d1ccfcfb5e8632af5fb023dfca00a5c6` | WP-02/03 MSDS 보강·화학사고 상세 및 새 검색 유형 표시 |

- 기존 공개 내부 검색 타입은 **12개**: `KNOWLEDGE, GUIDE, REFERENCE_FORM, LEGAL, CSI_ACCIDENT, SAFETY_MATERIAL, CHEM, CHEM_REGULATION, PRECEDENT, CHEM_SAFETY, HAZARDOUS_MATERIAL, CHEM_ACCIDENT` (외부 KOSHA smartSearch는 별도).
- 기존 기본 검색어댑터 **10개 + 신규 3개**는 이미 Git main에 반영됨. **CSIE는 새 3개 adapter를 다시 생성하거나 등록하지 않는다.** 화학 정보 재색인·공개 반영 여부는 미확인; 운영 활성화 범위에서만 검증한다.
- 기존 엔드포인트 유지: `GET /public/chemical-enrichment/by-cas/{cas_no}`, `GET /public/accidents/chemical`, `GET /public/accidents/chemical/{datano}`, `GET /public/safety-search?q=암모니아&type=chem_safety`.
- 기존 설계 v1.0의 EXT037 타입 이름 `CHEM_SAFETY_INFO`는 **최신 merged 코드와 상충하므로 폐기하고 `CHEM_SAFETY`를 기준**으로 삼는다. `HAZARDOUS_MATERIAL`, `CHEM_ACCIDENT`는 유지한다. 설계 원본을 무단 수정하지 않고 이번 계획의 **상위 설계 차이 정정(Design Delta D-01)** 으로 추적한다.
- v1 설계의 '9유형'은 **구 baseline 설명**으로만 해석. 신규 3개가 이미 12유형 코드에 포함되어 있으므로 사용 현황과 신규 구현 범위를 혼동하지 않는다. 이미 존재하는 v1 API·검색 어댑터의 동작은 보존한다.
- 코드 존재 ≠ OpenSearch 현재 색인 완료 ≠ 운영 공개 QA PASS. 재실사 루프 대신 운영 index gate에서 한 번 확인한다.

## 1. 전체 구성 및 의존성

```text
OBJECT PLAN (본 문서)
  ├─ OBJ-00  계약 고정 및 P0 type-scope 수정 [최초 소스 변경 시 별도 WO]
  ├─ OBJ-01  표준 컨텍스트 사전 / 검증 규칙
  ├─ OBJ-02  기존 13개 원천 adapter 보강 / eligibility / evidence
  ├─ OBJ-03  SearchDocument v2 / 공개 필드 sanitizer
  ├─ OBJ-04  OpenSearch v2 candidate / incremental / rollback
  ├─ OBJ-05  Search v2 / related / context / totals
  ├─ OBJ-06  통합검색 화면 개선
  ├─ OBJ-07  유형별 상세 및 관련자료/SEO/권리
  ├─ OBJ-08  SaaS·CHEM·Paid 참고자료 BFF (후속 승인)
  └─ OBJ-09  활성화·운영 전환 (Owner 운영 승인)

단계 A: OBJ-00 → OBJ-01 → OBJ-02/03
단계 B: OBJ-04 → OBJ-05
단계 C: OBJ-06/07
단계 D: OBJ-08(별도 스코프) → OBJ-09(운영)
```

OBJ는 논리 모듈 경계이며 **모든 OBJ에 별도 조사/WP/PR을 반드시 만들라는 뜻이 아니다**. 상호 영향이 작고 코드가 실제로 함께 변경되어야 하는 WP는 GPT가 한 작업지시서로 묶는다. 반대로 운영 파괴 위험이 있는 index/DB는 분리한다.

## 2. OBJ별 구현 상세

### OBJ-00 — 기존 계약 보존·P0 CHEM filter 교정

- **책임**: 기존 공개 검색 typed filter의 fail-closed 보장, 최신 baseline 계약 기록. 기존 12유형/13 adapters/URL 보존.
- **재사용**: `routers/public_safety_search.py`, `services/shared_search/opensearch_reader.py`, existing tests.
- **WP-00A (문서만)**: 기존 v1→현행 12유형 변화와 `CHEM_SAFETY` 네임스페이스 정정표. **본 계획의 §0.2로 충족; 추가 PR/검증 불필요.**
- **WP-00B (최소 코드 패치)**: `type=chem` + MSDS public mode `off`에서 빈 타입리스트가 모든 PUBLIC object type으로 확장되지 않도록 fail-closed. 분명한 다른 typed 미지원도 fail-closed. **별도 Owner 코드변경 승인 후** 진행; 신규 기능 추가 금지.
- **수용**: `type=chem` off에서 다른 유형 0; 기존 정상 타입 응답 호환; 신규 `chem_safety` 등에 영향 0. **해당 라우트 테스트만** 수행.
- **금지**: 전체 검색 엔진 교체·검색수순/랭킹 변경·운영 mode toggle.
- **완료 조건**: WP-00B 변경 PR에 국소 테스트 PASS, GPT 변경 diff 검토, Owner 병합 승인. P0 hotfix를 다른 OBJ 전체 완료의 전제 조건으로 묶지 않는다(공개 활성화 전엔 필수).

### OBJ-01 — 표준 컨텍스트 사전 및 근거 검증

- **책임**: `equipment/task/process/risk_factor/sector/chemical`와 v2 확장 `topic`/`legal_reference`의 명칭공간 및 증거 상태; lexical과 confirmed 관계 분리.
- **재사용**: 기존 Nori/dictionary, `subjects`/`context` nested, Graph 4개 테스트 keyword는 비교군으로만 사용.
- **WP-01A**: Git 기반 versioned dictionary + alias/official identifier schema + 정확 CAS/source ID namespace.
- **WP-01B**: `ContextResolver`가 source structured field/approved controlled phrase에서 `CONFIRMED/CANDIDATE/STALE`과 provenance를 산출; LLM candidate 자동확정 금지.
- **수용**: `equipment:forklift`, `task:welding`, `process:excavation`, `risk_factor:fall`, CAS 등을 deterministic fixture로 검증; 부정/인용문은 verified 승격 금지; 원천 버전 변경은 stale 처리; **전체 실제 문서 백필 금지**.
- **산출물**: 사전/fixture/해당 모듈 테스트. 신규 DB table 필요 없음.

### OBJ-02 — 원천 적격성·공개권리·최소 직접관계

- **책임**: **기존 13개 어댑터를 다시 작성하지 않고**, `source_id`, canonical identity, current/version, public eligibility, rights metadata를 별도 공통 확장 단계로 정규화.
- **WP-02A**: 기존 12 public type + 외부 KOSHA 권리 경계를 분류. EXT037/132/165의 기존 adapter와 CAS/사고 endpoints 그대로 사용.
- **WP-02B**: `SourceEligibility` / `ExplicitReferenceResolver` public-safe projection. 법령 current pointer와 시행 중 시점을 구분. EXT165 addr, place 등 민감 가능 필드 기본 제외.
- **수용**: 공개 보류/권리 UNKNOWN fail-closed, KOSHA GUIDE LINK_ONLY 유지, 회사/공장/tenant 데이터 금지, CAS 유사성만으로 원천 합병·법 적용 판단 금지. **샘플 source fixture로만** 확인.
- **선행/주의**: 신규 공개 권리 판단이 미완이면 해당 신규 화면 활성화만 보류. 기존 잘 동작하는 원천 reader 전체 중단 금지.

### OBJ-03 — SearchDocument v2 및 sanitizer

- **책임**: v1 타입/DTO를 지우지 않고 v2 계약을 추가한다. `context_assertions`, `context_flat_keys`, `source_version`, `rights_mode`, `current_status`, `display_meta`, `index_generation`, `normalized_identifiers` 등 확장.
- **WP-03A**: v2 canonical document schema, v1 compatibility projection, source-level public allowlist.
- **WP-03B**: provenance/hash/noop/deletion/rights-policy change fixture. 민감 문자열 포함 `search_text`/`summary`가 공개되지 않도록 규칙 명시.
- **수용**: typed unknown/secret/tenant 데이터 fail-closed, source 버전·법령 시행일·사고발생일·indexed_at 구분, v1 직렬화 호환, 문서별 idempotence.
- **범위**: 로컬 pure-unit tests; index create/write/alias 불허.

### OBJ-04 — OpenSearch v2 candidate, 증분 갱신 및 rollback

- **책임**: 기존 full rebuild/validate/atomic alias/rollback·incremental outbox 재사용. v2 version-aware candidate mapping/index `tai-shared-search-v2-*` 설계 적용.
- **WP-04A**: 코드로만 v2 mapping/analyzer 및 index generation planner 구현; 기존 alias `tai-shared-search-current` 변화 0.
- **WP-04B**: writer/index lineage/incremental fencer/tombstone/last-good + 테스트. v1 writer 영향 차단.
- **WP-04C (운영 동작 별도 승인)**: 사설 OpenSearch에 candidate/shadow index 생성·적재·검증. 접근 불가 시 해당 WP만 BLOCKED. 설계로 되돌아가 조사 루프 금지.
- **수용**: versioned mapping hash, 공개 eligible 건수 대비 candidate parity, fail/rollback 안전성, 기존 index 유지, 권리 취소 반영. 운영 alias 전환 **본 OBJ에서 금지**.
- **검증**: 로컬 mapping/writer 함수만 테스트; OpenSearch 실제 확인은 WP-04C 승인 때 **단 한 번** 수행.

### OBJ-05 — 공통 검색 v2·관련자료·집계 API

- **책임**: 기존 T0~T9 `_msearch` 우선순위 재사용, v1 응답 보존; v2 lexical/verified context/direct reference read API.
- **WP-05A**: v2 retrieval/filter/related/context JSON DTO 및 pagination/권리/현재판 감시.
- **WP-05B**: 후보 수와 전체 hit count 별도 표현 `total {value,relation}`; OpenSearch exact total은 확인된 경우만 `eq`, 그 외 unknown. `KOSHA` 외부 provider 실패 격리.
- **수용**: `GET /public/safety-search/v2/{search,sections,related,context}`는 **후보 계약**이고 최종 route namespace는 기존 라우트와 충돌 0이어야 함. 동일 문서 dedup, direct/confirmed/lexical 의미 분리, 공개 scope 강제. 실제 ranking parity는 승인된 candidate 이후에만.
- **범위**: 코드·fixture만 가능; 활성 인덱스 전환/실제 사용자 응답 활성화는 OBJ-09.

### OBJ-06 — Public 통합검색 UI

- **책임**: 기존 `/safety-search` 화면에서 정확한 개수·미확인 개수, 날짜 의미, 12유형 표시 및 자료 검색 → 상세 이동, CTA 개선.
- **WP-06A**: existing `safetySearch.js`, `safety-search.astro`에 feature-gated v2 consumer 추가. v1 fallback은 **에러와 0건을 구분**해 제공; 맹목적 fallback 금지.
- **WP-06B**: 섹션별 카드/필터/문서출처/rights/날짜/비슷한 정보 안내. 외부 KOSHA는 별도 표시.
- **수용**: v1 URL/robots noindex/canonical 보존, 다른 원천 미노출, `total=unknown`은 0으로 렌더링 금지, 모바일/데스크톱 국소 UI 테스트.
- **주요 성과 관측**: 카드→상세 클릭률, 상세 후 이탈, 진단 CTA 진입(목표 수치 사전 확정하지 않음).

### OBJ-07 — 유형별 상세·관련자료·원천권리·SEO

- **책임**: 기존 12유형 상세 URL/renderer 재사용하고 원천 근거에 따른 관련자료 블록 제공. 9유형 상세 리빌드 계획과 중복 개발 금지.
- **WP-07A**: `related` 후보를 source/type/version/rights 기준으로 제한하고 matched-basis를 출처 표기. KOSHA LINK_ONLY면 원문은 기관 링크 유지.
- **WP-07B**: 기존 상세별 날짜·출처·관련 사고/지침·SEO canonical/noindex/sitemap 정합. 신규 EXT3는 기존 관련 URL/상세 구현을 우선 재사용하고 권리 미승인 시 공개 확대 금지.
- **수용**: 공개 승인 자료만 렌더, 기존 public URL 404·중복·canonical 혼란 0(변경된 경로 기준), 법령 시행예정 표기 분리, 새 관계는 확정 의무라고 보이지 않음.
- **범위**: 변경한 상세 타입만 국소 확인, 전체 사이트 크롤링 금지.

### OBJ-08 — SaaS·CHEM·Paid 참고자료 BFF (후속 선택)

- **책임**: 공개 안전정보 조회 계약 재사용. SaaS의 사업장 설비·작업/화학 재고·진단응답은 **기존 서비스의 테넌트 경계 내부**에 유지.
- **WP-08A**: SaaS의 registered equipment/task → canonical public context key 변환·관련 참고문서 조회. 테넌트 자료 외부 전송 금지.
- **WP-08B**: CHEM의 CAS/MSDS/EXT037/132/KECO 참고자료 링크·출처 버전, 법령진단은 결과 근거열람 링크만; LEG applicability 변경 없음.
- **수용**: tenant leakage 0, 실제 적용의무/규제 판정 로직 0, 기존 BFF/권한 유지. 소비자별 작업은 Owner 별도 범위 승인 후 진행.
- **초기 출시 필수 아님**: 1차 Public 검색/상세 개선이 끝난 뒤 선택.

### OBJ-09 — 운영 canary·색인 활성화 및 관측

- **책임**: OBJ-04/05/06/07의 승인된 결과를 안전하게 활성화. 기본 Read alias/운영서비스 유지, 비가역 전환 금지.
- **WP-09A**: 배포 SHA/실제 active alias/physical index와 generation 확인. (과거 조사 자료 재수집 아님, **해당 배포 직전 필요사항만**.)
- **WP-09B**: candidate index parity, source→writer→read→public lineage, 권리/private 노출, 소수 대표 키워드 Top 결과·성능; rollback.
- **WP-09C**: Owner 승인 후에만 feature flag/canary 및 필요시 원자적 alias promote; 기존 물리 index 보존.
- **수용**: 0 index bulk fail, rights/private zero leaks, 관측 가능한 503과 empty 구분, last-good 및 rollback 가능, 새 EXT3 각각 색인/공개 단계 증거 분리.
- **미확인 시**: 운영 활성화만 BLOCKED, 이미 완성된 코드·설계는 재개발하지 않음.

## 3. 실행 순서 및 단계별 승인 기준

| Wave | 실행 순서 | 발주/검증 방법 | 완료 기준 |
|---|---|---|---|
| Wave A — 계약 및 안전성 | OBJ-00B → OBJ-01 → OBJ-02/03 | 실제 바뀐 파일에 한정, fixture 테스트 | typed fail-closed, v2 canonical/rights/context 코드 계약 |
| Wave B — 검색 엔진 | OBJ-04A/B → OBJ-05A/B | 로컬 계약 테스트 + 필요 시 승인된 candidate만 | v1 호환, v2 별도 search/related/context read |
| Wave C — 고객 화면 | OBJ-06 → OBJ-07 | 변경 UI/API smoke만, 기존 URL 유지 | 검색→상세→관련자료 탐색 가능 (feature flag off로 준비 가능) |
| Wave D — 운영 적용 | OBJ-04C → OBJ-09 | Owner 인덱스/배포 승인·운영 범위만 확인 | 권리·색인 parity·canary·rollback 증거 |
| 후속 확장 | OBJ-08 | 별도 Owner 범위 승인 | SaaS/CHEM/Paid 공개 참고자료 재사용 |

**병렬 가능**: OBJ-01 사전은 OBJ-00B hotfix와 병렬; OBJ-02/03 일부 독립 fixture 병렬; Public UI 정적 화면 준비는 검색 DTO contract 확정 후 가능. **병렬 금지**: 동일 파일에 여러 Codex 작업이 동시 수정되는 것, 소유자 승인 없이 index writer와 public UI 동시 활성화하는 것.

### 3.1 최소 Codex 산출 형식

```text
WO_ID=
OBJECT_ID=
WP_ID=
REPO=
BASE_SHA=
HEAD_SHA=
CHANGED_FILES=
CODE_CHANGED=YES/NO
DB_CHANGED=YES/NO
INDEX_CHANGED=YES/NO
APPLICABLE_TESTS=<수행한 범위와 결과 또는 NOT_REQUIRED>
UNVERIFIED=<관련 기능에 실질 영향을 주는 항목만>
PR=<draft URL 또는 NONE>
NEXT_GATE=<GPT_CHANGE_REVIEW / OWNER_MERGE_APPROVAL / OWNER_RUNTIME_APPROVAL>
```

**필요한 검증만**: `CODE_CHANGED=NO`, `DB_CHANGED=NO`, `INDEX_CHANGED=NO`이면 `APPLICABLE_TESTS=NOT_REQUIRED`. 문서 내용에 반영된 최신 main 변화는 GPT가 계획 작성 중 판단했으므로 Codex가 같은 분석을 다시 하지 않는다.

## 4. 위험, 완료 정의, 변경 관리

- **주요 위험**: `CHEM mode off` typed filter; 원천 공개권리(특히 EXT165 주소·사고), 미래 시행법령 current label, CAS와 KOSHA chem_id 혼동, 현재 v1 total 부정확성, 운영 Alias 미확인 및 outbox lag. 위험 해소를 위해 수십 회 사전 조사를 반복하지 않고 **영향받는 OBJ의 구현/활성화 순간에 국소 검증**.
- **코드 완료(DONE-CODE)**: 승인된 범위 코드가 main에 병합되고 국소 테스트 통과. **배포 완료(DONE-DEPLOY)**와 구분.
- **공개 완료(DONE-PUBLIC)**: 실제 public-safe 응답/권리/URL와 운영 인덱스·서비스 활성화 근거가 있을 때만 선언.
- **일부 객체 실패**는 독립된 객체 전체를 자동 BLOCKED시키지 않는다. 권리 미승인 원천은 해당 원천만 비공개.
- **Scope creep 금지**: 기존 13 어댑터 재개발·Graph 11,776개 전수 복제·신규 벡터DB·법령 적용 판단·재고 데이터 공개·새 무단 DB 테이블 생성.
- **최신 상태 충돌 시**: 실제 main/배포 기준과 오래된 설계 표가 다르면 원본 소스 계약을 우선하며, GPT가 짧은 **Design Delta**를 기록한다. Codex는 임의 설계 변경 금지.

## 5. 문서 등록과 다음 게이트

1. 이 Object Plan과 상위 상세설계를 **문서 전용** Git 경로에 Codex가 등록한다. 같은 내용이 이미 있으면 중복 변경·PR 생성하지 않는다.
2. 문서 작업 종료 증거는 **변경 파일 목록, Git diff --check, 문서 hash, 브랜치/commit/PR URL**이면 충분하다. **별도 기능 QA/독립검증 단계를 추가하지 않는다**.
3. Owner는 문서와 전체 개발 방향을 한 번 승인한다. 승인 후 GPT는 **OBJ-00B(기존 CHEM filter P0 hotfix)** 또는 **OBJ-01(컨텍스트 사전)** 중 하나의 구현 WO를 발행한다.
4. Codex는 승인된 범위 구현. 실제 소스·DB·index 변경이 생기는 WP에서만 필요한 국소 검증을 수행한다. Owner 없는 운영 적용 없음.

**현재**: `PLAN_DRAFT_FOR_DOCS_GIT`. 구현 승인/배포 승인 아님.
