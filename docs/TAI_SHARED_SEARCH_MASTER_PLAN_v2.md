# TAI Shared Search & Knowledge Consumer Master Plan v2

> Status: **plan / not yet implemented**
> Supersedes: prior CHEM-centric roadmap
> Owner: taiwang
> Date frozen: 2026-09-18
> Live signal at freeze:
>   - PR #401 (CHEM-FULL-READINESS-005 harness) — OPEN
>   - PR #399 (CHEM-FULL-READINESS-004 ops observability) — merged into main
>   - production `/search-dict/*` — observed HTTP 503 during live acceptance

## 0. 계획 재수립 목적

기존 CHEM 중심 작업계획을 TAI 초기 전체 설계 기준으로 복원한다.

최종 목표는 페이지별 검색기능을 따로 만드는 것이 아니다.

```text
Domain SoT
  LEG
  GUIDE
  Safety Material
  CSI / Accident
  RISK
  CHEM
  Knowledge
  Precedent
       ↓
TAI Unified Search Projection
       ↓
TAI Shared Search Engine
       ↓
Public / Paid / SaaS / LEG Enrichment
```

원칙:

```text
검색엔진 = 하나
검색인덱스 = 하나의 공통 contract
Domain SoT = 각 원본 DB 유지
Consumer = 여러 개

SEARCH TERM != CANONICAL ID
SEARCH INDEX != SOURCE OF TRUTH
```

---

## 1. 현재까지 실제 완료된 것

### 1-1. 검색어 해석 엔진

완료.

기존:

```text
services/search_query_svc.py
tools/search_dict/*
```

검색 tier:

```text
T1  EXACT
T2  NORMALIZED_EXACT
T2b PUNCTUATION
T3  ALIAS / SYNONYM
T4  KIWI TOKEN
T6  TRIGRAM
```

즉:

```text
검색어
→ 정규화
→ 동의어/약어
→ Kiwi 형태소
→ 오타/Trigram
→ subject 후보
```

까지 이미 존재한다.

이것을 새로 만들지 않는다.

---

### 1-2. Search Dictionary

완료.

현재 canonical snapshot:

```text
SEARCH-DICT-LEGPROD-2026-09-16
```

초기 설계상 이 사전은 MSDS 전용이 아니다.

Consumer:

```text
LEGAL
CHEM
RISK
EQUIPMENT
ACCIDENT
Public Discovery
LEG Candidate Enrichment
ON_DEMAND
```

용 공용 lexical layer다.

---

### 1-3. Public 통합검색 1차

이미 구현되어 있다.

현재 `/safety-search`는:

```text
Knowledge Center
Safety Material
KOSHA GUIDE
Accident
Law Update
Precedent
+
KOSHA Smart Search
```

를 검색한다.

하지만 현재 구현은:

```text
6개 source adapter
→ 각각 직접 검색
→ presentation에서 합침
```

구조다.

즉:

```text
Unified Search UI = 있음
Unified Search Index = 없음
Unified Search Engine = 아직 아님
```

이다.

---

### 1-4. Knowledge Graph

core는 존재한다.

현재 controlled production context:

```text
equipment:forklift
task:welding
process:excavation
topic:fall
```

만 적용되어 있다.

```text
FULL CORPUS APPLY = NO
```

상태다.

따라서 Graph도 아직 전체 Consumer 기반은 아니다.

---

### 1-5. 위험성평가 RISK 데이터

데이터 기반 작업은 상당 부분 완료됐다.

Production mapping:

```text
CIC_W = 1,139
KOSHA =    46
KALIS =     9
----------------
TOTAL = 1,194
```

A/B/C reconciliation과 Owner Approval까지 종료됐다.

그러나:

```text
risk_canonical_nodes = 1,110

DRAFT  = 1,110
ACTIVE = 0

risk_canonical_node_sectors = 0
```

이다.

즉 RISK는:

```text
원천수집            완료
canonical 초안       완료
source mapping        완료
정합성 검증           완료
```

이지만 다음은 아직 안 했다.

```text
consumer-ready ACTIVE
sector linkage
Graph 연결
Search Index 연결
SaaS 연결
Paid Diagnosis 연결
```

---

### 1-6. CHEM

현재 별도 Track에서 진행 중.

```text
P1 Incremental Materializer     DONE
P2 FULL Cutover/Rollback        DONE
P3 Search backend QA            DONE
P4 Ops Observability            MERGE READY
P5 FULL Acceptance Harness      NEXT

CHEM-04 Hydration               병렬 진행
```

현재 Preview:

```text
chemicals = 1,997
sections  = 31,952
```

FULL:

```text
20,568 chemicals
329,088 sections
```

수집 완료를 기다리지 않고 나머지를 진행한다.

---

## 2. 초기 설계 중 실제 미완료 항목

다음이 핵심 backlog다.

### GAP-01 — 검색 Runtime Production Binding

현재:

```text
/search-dict/*
→ production에서 503 관측
```

따라서 코드상 Kiwi/T4/T6가 존재하는 것과:

```text
실제 production runtime
```

에서 동작하는 것은 아직 별개다.

반드시 확인:

```text
runtime projection = v2
Kiwi token_tier = true
Trigram runtime = 정상
CHEM_TERM = 정상
```

---

### GAP-02 — 공통 Search Index 없음

현재 가장 큰 구조적 공백이다.

지금 Public 검색은 각 source를 직접 조회한다.

```text
GUIDE DB 직접 조회
Safety Material 직접 조회
Accident 직접 조회
Knowledge 직접 조회
Law 직접 조회
Precedent 직접 조회
```

이 구조를 계속 확장하면:

```text
CHEM 추가
RISK 추가
Equipment 추가
Graph 추가
SaaS Context 추가
```

할 때마다 검색 로직이 늘어난다.

따라서 공용 index가 필요하다.

---

### GAP-03 — Search Dictionary → LEG 실제 배선 미완료

원래 계획:

```text
search_query_svc
       ↓
LEG Candidate Enrichment
       ↓
leg_candidate_adapter
leg_ondemand_enrichment
```

현재 실제 코드를 확인하면:

```text
leg_candidate_adapter
→ leg_ondemand_enrichment
```

은 연결돼 있다.

하지만:

```text
search_query_svc
→ LEG candidate
```

연결은 없다.

즉 인수인계 문서에서 남긴 TODO가 실제로 남아 있다.

---

### GAP-04 — RISK Consumer화 미완료

RISK 데이터는 있으나 실제 서비스에서 사용하는 연결이 없다.

남은 것:

```text
RISK canonical activation 정책
sector linkage
RISK read model
Search Index projection
Graph edge
SaaS context
Paid context
```

---

### GAP-05 — SaaS Context Search 미완료

초기 계획에서는 다음 화면이 검색엔진을 자동으로 사용해야 한다.

```text
공정
작업
설비
화학물질
법령의무
점검
```

사용자가 다시 검색하지 않아도:

```text
관련 GUIDE
관련 안전자료
관련 사고
관련 위험성평가
관련 CHEM
관련 법령/Knowledge
```

을 보여주는 구조였다.

아직 공통 결선이 없다.

---

### GAP-06 — Paid Diagnosis Knowledge 연결

초기 WAVE 5 계획:

```text
진단 결과
+
관련 GUIDE
+
안전자료
+
사고
+
RISK
+
CHEM
```

이다.

아직 공통 Search/Graph consumer로 연결되지 않았다.

---

### GAP-07 — Graph 전체 활용

Graph core는 있지만 controlled context만 적용했다.

```text
FULL CORPUS APPLY = NO
```

검색엔진과 Consumer가 안정된 후 Graph coverage 확장 전략이 필요하다.

---

## 3. 목표 검색 아키텍처

검색을 네 계층으로 명확히 나눈다.

```text
┌─────────────────────────────────┐
│ A. QUERY UNDERSTANDING          │
│                                 │
│ Search Dictionary               │
│ Exact / Normalize / Alias       │
│ Kiwi / Trigram                  │
└───────────────┬─────────────────┘
                ↓
┌─────────────────────────────────┐
│ B. UNIFIED SEARCH INDEX         │
│                                 │
│ GUIDE                           │
│ MATERIAL                        │
│ CSI / ACCIDENT                  │
│ CHEM                            │
│ RISK                            │
│ LEGAL                           │
│ KNOWLEDGE                       │
│ PRECEDENT                       │
└───────────────┬─────────────────┘
                ↓
┌─────────────────────────────────┐
│ C. RETRIEVAL / RANKING          │
│                                 │
│ identifier exact                │
│ subject exact                   │
│ title exact                     │
│ alias                           │
│ FTS                             │
│ context                         │
│ trigram fallback                │
└───────────────┬─────────────────┘
                ↓
┌─────────────────────────────────┐
│ D. CONSUMERS                    │
│                                 │
│ Public Search                   │
│ Paid Diagnosis                  │
│ SaaS Context                    │
│ LEG Candidate                   │
│ Help / Support                  │
└─────────────────────────────────┘
```

---

## 4. 기술 선택

현재 규모에서는 Elasticsearch/OpenSearch를 도입하지 않는다.

우선:

```text
PostgreSQL / Supabase
+ PostgreSQL FTS
+ pg_trgm
+ 현재 Search Dictionary
+ Kiwi
```

를 사용한다.

이유:

```text
데이터 변경 빈도 낮음
전체 데이터 규모 관리 가능
기존 Supabase 사용
운영 복잡도 최소
1인 기업 유지보수 적합
```

Elastic 계열은 실제 검색량/데이터량으로 Postgres 한계가 확인된 후 검토한다.

---

## 5. 공통 Search Projection

새 검색엔진의 핵심이다.

개념:

```text
tai_search_documents
```

한 개의 공통 projection.

실제 schema는 repo audit 후 확정하지만 contract는 다음 정도로 고정한다.

```text
search_document_id

object_type
canonical_id

source_id
source_key

title
summary
search_text

aliases
keywords

subject_types
subject_keys

context:
  process
  task
  equipment
  chemical
  legal
  risk
  sector

public_url
saas_url

publication_status
source_updated_at
content_hash
indexed_at
```

중요:

```text
원본 payload 전체를 검색 DB가 소유하지 않는다.
```

Search index는:

```text
찾기 위한 projection
```

일 뿐이다.

상세조회:

```text
Search result
→ canonical_id
→ Domain SoT
```

로 간다.

---

## 6. Search Index 갱신 방식

TAI 데이터 특성상 복잡한 CDC부터 만들 필요가 없다.

초기:

```text
FULL REBUILD
+
OBJECT REINDEX
+
NIGHTLY RECONCILIATION
```

세 가지면 충분하다.

예:

```text
GUIDE publish
→ GUIDE reindex

CHEM FULL publish
→ CHEM reindex

RISK activation
→ RISK reindex

law snapshot change
→ LEG reindex
```

그리고 하루 1회:

```text
SoT
↔
Search Index

count
hash
missing
extra
```

검증한다.

---

## 7. Query Logic

### Q1. Identifier gate

가장 먼저:

```text
chemId
CAS
KE
EN
UN
canonical_id
law identifier
```

판별.

Identifier는:

```text
Kiwi 금지
fuzzy 금지
```

exact 우선.

---

### Q2. Query Resolution

identifier가 아니면 기존 공용 엔진 사용.

```text
normalize
↓
dictionary exact
↓
alias / synonym
↓
Kiwi
↓
trigram
```

여기서:

```text
subject_type
subject_key
expanded terms
tokens
```

을 만든다.

---

### Q3. Search Index Retrieval

그 신호로 Search Projection을 조회한다.

우선순위:

```text
1. Canonical / Identifier Exact
2. Subject Exact
3. Title Exact
4. Alias / Synonym
5. Context Match
6. FTS
7. Kiwi Token Match
8. Trigram Fallback
```

---

### Q4. Dedup

동일 canonical object가 여러 검색경로로 발견돼도:

```text
result = 1개
```

최고 우선 match만 보존한다.

---

### Q5. Explanation

검색결과마다:

```text
match_type
matched_term
subject
object_type
```

을 보존한다.

왜 검색됐는지 설명 가능해야 한다.

---

## 8. RISK 검색 원칙

RISK만을 위한 별도 검색엔진을 만들지 않는다.

```text
risk canonical / mapping
       ↓
Unified Search Index
       ↓
Shared Search Engine
```

으로 사용한다.

예:

```text
사용자 작업 = 용접작업
```

Search Engine:

```text
task:welding
       ↓
RISK
GUIDE
CSI
CHEM
LEGAL
```

을 동시에 찾는다.

---

## 9. KOSHA Smart Search 처리

현재 원칙 유지.

KOSHA Smart Search는:

```text
CONTENT SOURCE가 아님
DISCOVERY PROVIDER
```

이다.

따라서:

```text
TAI Search Index 결과
+
KOSHA Smart Search 결과
```

를 presentation에서 합친다.

KOSHA 외부 결과가:

```text
TAI canonical
법령 적용판정
RISK canonical
```

을 변경하지 않는다.

---

## 10. 작업 순서

### TRACK C — 현재 CHEM

#### C0

PR #399 merge. (완료 — main SHA `f32e4a71`)

#### C1

CHEM P5 Full Acceptance Harness. (PR #401 open)

CHEM hydration은 계속 별도 병렬.

이 Track 때문에 Search 작업을 기다리지 않는다.

---

### TRACK S — Shared Search Engine

#### SEARCH-00 — Integration Audit

가장 먼저 실행.

전수 조사:

```text
search_query_svc
/search-dict
/safety-search
global_search
Knowledge Graph
GUIDE
Safety Material
CSI
CHEM
RISK
LEGAL
Knowledge Center
Precedent
Paid
SaaS
```

각각:

```text
CONNECTED
PARTIAL
NOT_CONNECTED
DUPLICATED
```

판정.

##### 특별 주의

현재:

```text
GET /search
```

는 회사/회원/사업장/결제용 Admin 교차검색이다.

TAI Knowledge Search와 전혀 다른 기능이다.

재사용/혼합 금지.

---

#### SEARCH-01 — Runtime Production Fix

현재 503 문제 해결.

반드시 production에서:

```text
/search-dict/health = 200

snapshot =
SEARCH-DICT-LEGPROD-2026-09-16

token_tier = true
```

확인.

Kiwi 실제 runtime 확인.

Trigram도 runtime 상태 확인.

---

#### SEARCH-02 — Unified Search Contract

45cm 방식:

```text
SEARCH CONSTITUTION
        ↓
SEARCH INDEX CONTRACT
        ↓
SEARCH ENGINE
```

정의.

확정 대상:

```text
object_type
canonical_id
identity
publication
scope
context
ranking
dedup
reindex
failure
```

---

#### SEARCH-03 — Search Projection

Postgres 기반 공통 Search Index 구현.

새 generic source DB를 만들지 않는다.

Search projection만 생성.

---

#### SEARCH-04 — Domain Indexers

공통 writer 하나를 사용한다.

각 domain adapter만 둔다.

우선순위:

```text
1. GUIDE
2. Safety Material
3. CSI / Accident
4. Knowledge Center
5. CHEM
6. RISK
7. LEGAL
8. Precedent
```

각 source별 별도 검색엔진 생성 금지.

---

#### SEARCH-05 — Unified Retrieval Engine

구현:

```text
Query Resolver
+
Search Index Retrieval
+
Ranking
+
Dedup
+
Pagination
+
Explanation
```

하나의 공용 서비스.

---

#### SEARCH-06 — Public Unified Search Migration

현재 `/safety-search`의 6개 직접 adapter를 공통 엔진으로 교체한다.

Before:

```text
Page
→ source A
→ source B
→ source C
...
```

After:

```text
Page
→ TAI Shared Search
→ Unified Index
```

KOSHA Smart Search만 외부 provider로 유지.

---

#### SEARCH-07 — LEG Candidate Integration

기존:

```text
search_query_svc
```

결과를:

```text
leg_candidate_adapter
leg_ondemand_enrichment
```

앞단의 high-precision candidate signal로 연결한다.

절대 금지:

```text
검색결과
→ 법령 적용판정 변경
```

허용:

```text
검색 subject
→ candidate enrichment
```

---

### TRACK R — RISK Consumerization

#### RISK-C01 — Consumer Readiness Audit

현재 1,110 DRAFT canonical을 다시 설계하는 작업이 아니다.

확인:

```text
어떤 canonical이 Consumer에 노출 가능한가
어떤 evidence가 필요한가
어떤 DRAFT를 ACTIVE로 승격할 것인가
```

Owner gate 정의.

---

#### RISK-C02 — ACTIVE Gate

모든 1,110개를 일괄 ACTIVE 하지 않는다.

근거가 충분한 canonical만:

```text
DRAFT → ACTIVE
```

승격.

검색 similarity는 ACTIVE 근거가 아니다.

---

#### RISK-C03 — Sector Linkage

현재:

```text
risk_canonical_node_sectors = 0
```

을 실제 SaaS sector:

```text
BUILDING
MANUFACTURING
CONSTRUCTION
```

context와 연결.

---

#### RISK-C04 — RISK Read Model

Consumer가 사용할:

```text
process
task
risk factor
control/reduction context
source evidence
```

read model 제공.

---

#### RISK-C05 — Search Index

ACTIVE/허용된 RISK만 공통 Search Projection으로 index.

---

#### RISK-C06 — Graph

RISK:

```text
process
task
risk
```

관계를 existing Knowledge Graph로 연결.

새 Graph engine 생성 금지.

---

### TRACK X — Consumer Rollout

#### SEARCH-C01 — Public

```text
/safety-search
```

공통 Search Engine 사용.

---

#### SEARCH-C02 — SaaS Process

공정 화면:

```text
process context
→ Shared Search
→ GUIDE / CSI / RISK / CHEM / LEGAL
```

---

#### SEARCH-C03 — SaaS Task

작업 화면:

```text
task context
→ Shared Search
```

---

#### SEARCH-C04 — SaaS Equipment

설비 화면:

```text
equipment context
→ Shared Search
```

---

#### SEARCH-C05 — Obligation

법령의무 화면:

```text
obligation/legal context
→ GUIDE / Knowledge / related official data
```

법령판정은 여전히 Legal Engine.

---

#### SEARCH-C06 — Inspection

점검 화면:

```text
equipment + task + obligation
→ Shared Search
```

---

#### SEARCH-C07 — Chemical

MSDS 화면:

```text
CHEM search
+
related GUIDE / RISK / accident
```

공용 engine 사용.

---

#### SEARCH-C08 — Paid Diagnosis

진단결과:

```text
적용의무
+
관련 GUIDE
+
사고
+
RISK
+
CHEM
```

자동 제공.

---

## 11. Front 작업

백엔드 consumer 연결 후 진행.

### FRONT-01

Public Unified Search.

### FRONT-02

SaaS 공정 관련자료 panel.

### FRONT-03

SaaS 작업 관련자료 panel.

### FRONT-04

SaaS 설비 관련자료 panel.

### FRONT-05

법령의무 관련자료 panel.

### FRONT-06

점검 관련자료 panel.

### FRONT-07

MSDS 관련자료 panel.

### FRONT-08

Paid Diagnosis 관련자료.

공통 UI component를 사용한다.

페이지마다 별도 관련자료 UI 구현 금지.

예:

```text
KnowledgeRelatedPanel
```

하나를 공통 사용.

---

## 12. Search API

Admin 기존:

```text
/search
```

와 충돌시키지 않는다.

Knowledge 검색은 별도 contract 사용.

권장 예:

```text
/public/safety-search
```

Explicit:

```text
GET /public/safety-search?q=용접
```

Context:

```text
POST /knowledge/discovery
```

또는 repo convention에 맞는 동일 목적 endpoint.

중요한 것은 endpoint 이름보다:

```text
Explicit Search
Context Search
```

가 같은 Search Engine을 사용한다는 점이다.

---

## 13. Context Search

Public:

```text
사용자가 검색어 입력
```

SaaS:

```text
시스템이 이미 context를 알고 있음
```

따라서 SaaS에서는:

```text
q 없이도 검색 가능
```

해야 한다.

예:

```text
context = {
  sector,
  process_ids,
  task_ids,
  equipment_ids,
  chemical_ids,
  obligation_ids
}
```

Search Engine:

```text
context
→ subject resolution
→ Search Index
→ related knowledge
```

---

## 14. Relevance 원칙

LLM ranking은 1차 검색에서 사용하지 않는다.

초기:

```text
deterministic ranking
```

만.

순서:

```text
identifier exact
subject exact
title exact
alias
context
FTS
Kiwi
Trigram
```

충분하지 않을 때만 미래 별도 WO에서 reranker 검토.

---

## 15. 운영

### Reindex

```text
search-index rebuild
search-index reindex --type CHEM
search-index reindex --type RISK
```

등 운영 도구 제공.

### Reconciliation

하루 1회:

```text
SoT count
Index count
missing
extra
hash drift
```

검사.

### Observability

```text
last rebuild
last incremental update
document counts by type
failed indexing
stale objects
search runtime
Kiwi state
```

노출.

---

## 16. 전체 실행 순서

최종 순서는 다음으로 고정한다.

```text
NOW

1. PR #399 merge                  ← 완료 (main = f32e4a71)
2. CHEM P5                        ← PR #401 open

동시에

3. SEARCH-00 Integration Audit
4. SEARCH-01 Runtime 503 / v2 / Kiwi 정상화

        ↓

5. SEARCH-02 Unified Contract
6. SEARCH-03 Unified Search Index
7. SEARCH-04 Domain Indexers
8. SEARCH-05 Retrieval Engine

        ↓

9. SEARCH-06 Public Search migration
10. SEARCH-07 LEG Candidate wiring

        ↓

11. RISK-C01 Consumer audit
12. RISK-C02 ACTIVE gate
13. RISK-C03 Sector linkage
14. RISK-C04 Read model
15. RISK-C05 Search index
16. RISK-C06 Graph

        ↓

17. SaaS Context Search
    Process
    Task
    Equipment
    Obligation
    Inspection
    Chemical

        ↓

18. Paid Diagnosis integration

        ↓

19. Common Front components
20. Integrated E2E

        ↓

21. Search/Reindex operations closeout
```

---

## 17. CHEM Hydration과의 관계

CHEM 전체수집은 이 계획을 막지 않는다.

현재:

```text
CHEM search index
= Preview 1,997로 개발
```

한다.

FULL 완료 시:

```text
CHEM FULL publish
→ CHEM index rebuild
→ 20,568
```

만 하면 된다.

따라서:

```text
CHEM-04 hydration
```

은 계속 병렬 Track이다.

---

## 18. 완료 정의

이번 전체 검색/소비자 계획의 종료 조건:

```text
SEARCH RUNTIME
v2 + Kiwi 정상

UNIFIED INDEX
모든 승인 Domain index

PUBLIC
공통 검색엔진 사용

LEG
candidate enrichment 연결

RISK
consumer-ready

GRAPH
RISK/CHEM 등 consumer relation 제공

SAAS
공정/작업/설비/의무/점검에서 Context Search 사용

PAID
진단결과 관련자료 제공

FRONT
공통 component 사용

OPS
rebuild/reconcile/monitor 가능
```

그때 검색구조는:

```text
                      ┌─ Public
                      │
Domain SoT → Search Engine ─ Paid
                      │
                      ├─ SaaS
                      │
                      └─ LEG Enrichment
```

하나로 통합된다.

---

## 19. 첫 번째 실제 작업

새 계획의 첫 Search WO는:

```text
WO-TAI-SHARED-SEARCH-000
INTEGRATION AUDIT & GAP FREEZE
```

로 시작한다.

이 WO에서는 구현하지 않는다.

다음을 실제 repo 기준으로 확정한다.

```text
Search Dictionary
Public safety-search
LEG candidate
Knowledge Graph
GUIDE
Material
CSI
CHEM
RISK
LEGAL
Knowledge
Precedent
Paid
SaaS
```

각 연결을:

```text
CONNECTED
PARTIAL
NOT_CONNECTED
DUPLICATE
```

로 동결한다.

그 결과를 기준으로 SEARCH-01부터 **이미 있는 것은 재구현하지 않고 미연결부만 작업**한다.

---

## 20. 핵심 시사점 요약

- **CHEM 검색을 마친 뒤 프론트 QA**가 아니라, CHEM을 공용 검색엔진의 한 데이터 소스로 넣고 RISK·GUIDE·CSI·법령까지 같은 엔진으로 통합한 뒤 여러 SaaS 페이지가 그것을 소비하도록 만드는 것이 초기 설계의 핵심이다.
- 현재 `/safety-search`는 이미 좋은 1차 구현이 있으므로 **버리는 게 아니라, 그 화면을 유지하면서 뒤의 6개 직접 조회를 공통 Search Index/Engine으로 교체**하는 방식이 가장 유지보수가 적다.
- 검색엔진 = 하나 / 검색인덱스 = 하나 / Domain SoT = 각자 / Consumer = 여럿. 이 원칙만 유지되면 이후 CHEM FULL 수집, RISK ACTIVE 승격, Paid/SaaS/Front 통합은 각 track이 서로를 막지 않고 병렬 진행할 수 있다.
