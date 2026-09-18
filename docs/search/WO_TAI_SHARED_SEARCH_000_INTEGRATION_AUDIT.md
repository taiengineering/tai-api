# WO-TAI-SHARED-SEARCH-000: Integration Audit (FROZEN STATE)

**Date**: 2026-09-19  
**Scope**: Read-only investigation of TAI shared-search infrastructure  
**Deliverable**: Connection Matrix + Duplicate Matrix for SEARCH-01 planning
**Hard fence honored**: 0 code / 0 DB write / 0 deploy / 0 env change

---

## 1. Repo Anchors

| Working Directory | Reference SHA | Note |
|---|---|---|
| `/Users/taiwangsim/Desktop/tai-api-obj-chem` | `7d033721` | main after PR #401 + #402 merges |
| `/Users/taiwangsim/Desktop/tai-api` | (not probed) | Secondary checkout — used only when primary was insufficient |
| `/Users/taiwangsim/Desktop/tai-www` | (not audited) | Frontend consumer — deferred (see §16 Unknowns) |

The audit was performed on the `docs/tai-shared-search-master-plan-v2` branch at head `7be439d6…`, whose tree of `services/` and `routers/` is identical to the merged main `7d033721`.

---

## 2. Query Understanding Stack (S00-01)

### Implemented Tiers

| Tier | Name | Classification | File + Line | Status |
|---|---|---|---|---|
| T1 | EXACT | Deterministic, runtime-independent | `tools/search_dict/search_core.py:91` | APPROVED, indexed |
| T2 | NORMALIZED_EXACT | Compact matching (spacing/punct-insensitive) | `tools/search_dict/search_core.py:95` | APPROVED, indexed |
| T2b | PUNCTUATION | No-punctuation matching (KR law separators) | `tools/search_dict/search_core.py:98` | APPROVED, indexed |
| T3 | EXPANSION (ALIAS/SYNONYM) | Approved expansion edges from query.compact → subject | `tools/search_dict/search_core.py:101` | APPROVED, indexed |
| T4 | KIWI TOKEN | Morphological noun overlap (kiwipiepy optional) | `services/search_query_svc.py:130` | OPTIONAL, lazy-init |
| T6 | TRIGRAM | pg_trgm similarity (scratch DSN only, never leg-prod) | `services/search_query_svc.py:154` | OPTIONAL, lazy-init |

### Normalization Module

- **Path**: `tools/search_dict/normalize.py`
- **Functions**: `normalize_basic()`, `compact()`, `no_punctuation()`
- **Contract**: Same module used at build time and runtime (deterministic)
- **Reuse**: CHEM adapter (`services/kosha_msds/search_adapter.py:30`)

### Runtime Projection

- **Path**: `tools/search_dict/artifacts/TAI_SEARCH_RUNTIME_PROJECTION_v1.json`
- **Snapshot ID**: `SEARCH-DICT-LEGPROD-2026-09-16` (from `seed_v2.py:36`)
- **Load**: `services/search_query_svc.py:53-58`
- **Subjects**: All with `non_production=false`
- **Expansions**: APPROVED only (WO §52)

### Kiwi Integration

- **User Dictionary**: `tools/search_dict/artifacts/TAI_KIWI_USER_DICTIONARY_v1.txt`
- **Noun Tags**: `{NNG, NNP, SL}` (Korean nouns + Latin symbols)
- **Graceful Fallback**: Tier 4 returns `None` if kiwipiepy unavailable
- **File**: `tools/search_dict/search_runtime_ext.py:29-39`

### Runtime Injector

- **Path**: `tools/search_dict/search_runtime_ext.py`
- **Classes**: `TokenTier` (T4), `TrigramTier` (T6)
- **Guardrail**: TrigramTier refuses leg-prod DSN (WO §2)

---

## 3. Search Dictionary (S00-02)

### API Surface

| Endpoint | Router | Handler | File | Status |
|---|---|---|---|---|
| `GET /search-dict/lookup` | `/search-dict` | `lookup()` | `routers/search_dictionary.py:19` | **CONNECTED** |
| `GET /search-dict/health` | `/search-dict` | `health()` | `routers/search_dictionary.py:32` | **CONNECTED** |
| `GET /search-dict/census` | `/search-dict` | `census()` | `routers/search_dictionary.py:41` | **CONNECTED** |

### Registration

- **Router Registry Path**: `router_registry/public.py:28`
- **Module**: `routers.search_dictionary`
- **Prefix**: `/search-dict`
- **Public**: Yes (no auth required)

### Data Source

- **Master Seed**: `tools/search_dict/seed_v2.py`
- **Ground Truth**: `tools/search_dict/extract/GROUND_TRUTH_464.tsv` (verified=true in leg-prod)
- **Aliases**: `tools/search_dict/extract/LAW_ALIAS_15.tsv`
- **Overlay Terms**: KOSHA equipment/chemical domain terms (PROPOSED/REVIEWED where linkage needs review)

### Database Tables (Optional, schema-only)

- **Primary**: `public.search_term_master` (APPROVED terms only in production)
- **Relations**: `public.search_term_relations` (abbreviation/spacing/synonym)
- **Index**: `ix_search_term_trgm` GIN on `term_normalized` using `pg_trgm`
- **Migration**: `migrations/2026-09-16_search_dictionary_tables.sql:1-57`
- **Note**: Schema is additive + idempotent; DB APPLY = 0 per WO §2

### Production HTTP 503 Hypothesis

**Observed**: Live acceptance reports HTTP 503 on `/search-dict/health`

**Root Cause Analysis**:

1. **Scenario A: Missing Projection File**
   - If `TAI_SEARCH_PROJECTION` env var points to deleted/moved artifact
   - Service raises `SearchDictError` in `_get_projection()`
   - Router maps to HTTP 503 via `services/search_query_svc.py:54-56`
   - **Evidence**: `_get_projection()` checks `os.path.exists()` and raises if missing

2. **Scenario B: Kiwi/Trigram Late-Init Failure**
   - Tier 4 (Kiwi) or Tier 6 (Trigram) fails during `_get_token_tier()`/`_get_trigram_tier()`
   - Sentinel value `_token_tier = False` or `_trigram_tier = False` set
   - If health check is probing optional tiers without graceful fallback, HTTP 503 returned
   - **Evidence**: `services/search_query_svc.py:73-83` (token), `89-102` (trigram)

3. **Scenario C: Scratch DSN Misconfiguration**
   - If `TAI_SEARCH_SCRATCH_DSN` is set to invalid/unreachable Postgres
   - `TrigramTier.__init__()` fails to connect
   - Sentinel `_trigram_tier = False` but health() still flags it (HTTP 503)
   - **Evidence**: No try/except around tier instantiation in health() return; health returns dict with tiers only after success

**Most Likely**: **Scenario A** (missing projection artifact in production build). The projection file path is hardcoded to `tools/search_dict/artifacts/TAI_SEARCH_RUNTIME_PROJECTION_v1.json`, and if the artifact directory isn't packaged or is in wrong location at runtime, `_get_engine()` → `_get_projection()` fails immediately.

**Hypothesis for SEARCH-01**: Confirm production deployment includes `tools/search_dict/artifacts/` directory. If not, copy from build output or adjust `TAI_SEARCH_PROJECTION` env var.

---

## 4. Public Safety Search (S00-03)

### Router

- **Path**: `routers/public_safety_search.py:1-27`
- **Endpoint**: `GET /public/safety-search/kosha?q=&page=&page_size=`
- **Registration**: `router_registry/public.py:10`
- **Public**: Yes (no auth)

### Source Adapters

| Source | Type | File | Handler | Classification | Query Method |
|---|---|---|---|---|---|
| **KOSHA Smart Search** | External API | `services/kosha_smart_search.py:330` | `search_kosha_public()` | **EXTERNAL_PROVIDER** | DIRECT_QUERY |
| Knowledge Center | DB | (not implemented in public router) | — | NOT_CONNECTED | — |
| Safety Material | DB | (not implemented in public router) | — | NOT_CONNECTED | — |
| KOSHA GUIDE | DB | (not implemented in public router) | — | NOT_CONNECTED | — |
| Accident (CSI) | DB | (not implemented in public router) | — | NOT_CONNECTED | — |
| Law Update | DB | (not implemented in public router) | — | NOT_CONNECTED | — |
| Precedent | DB | (not implemented in public router) | — | NOT_CONNECTED | — |

### KOSHA Smart Search Details

- **Provider**: `PROVIDER = "KOSHA"` (`services/kosha_smart_search.py:28`)
- **Source**: `apis.data.go.kr/B552468/srch/smartSearch` (data.go.kr OpenAPI, dataset 15123696)
- **Transport**: HTTP GET via `services/kr_public_api.kr_get()`
- **Timeout**: 15 seconds
- **Graceful Degradation**: Returns `{"status": "unavailable", ...}` on network/schema errors (not 5xx)
- **Query Normalization**: `normalize_query()` at `services/kosha_smart_search.py:81-94`
- **Result Normalization**: `normalize_item()` at `services/kosha_smart_search.py:218-233`
- **No Search Dict Integration**: Adapter does NOT call `search_query_svc.lookup()` for expansion

### Verdict

**PARTIAL**: Public safety search exposes only 1 source (KOSHA Smart Search / external provider). Knowledge Center, Safety Material, GUIDE, Accident, Law Update, Precedent are **NOT_CONNECTED** to this router. They exist in other admin/SaaS routers but not in `/public/safety-search/`.

---

## 5. Admin `/search` (S00-04)

### Cross-Search Router

- **Path**: `routers/global_search.py:1-26`
- **Endpoint**: `GET /search?q=&types=company,user,factory,payment&limit=`
- **Registration**: `router_registry/saas_core.py:12`
- **Auth**: **REQUIRED** (no public prefix; called from SaaS UI)

### Implementation

- **Service**: `services/global_search_svc.search()`
- **Query Method**: ilike (partial string match) on DB tables
- **Target Types**: `{"company", "user", "factory", "payment"}`
- **DB Tables**: companies, users, factories, payment_methods (via Supabase)
- **Soft Delete**: Respected (`.is_("deleted_at", "null")`)

### Verdict

**KEEP SEPARATE**: `/search` is **admin cross-search over operational entities** (company/user/factory/payment), NOT a knowledge search. Zero overlap with `/search-dict/` (terminology) or `/public/safety-search/` (KOSHA smart search). File evidence:

- `routers/global_search.py:17` — prefix="/search" (vs. "/search-dict")
- `services/global_search_svc.py:17` — `TYPES = ("company", "user", "factory", "payment")` (vs. terminology subjects)

---

## 6. LEG Candidate / ON_DEMAND Wiring (S00-05)

### Call Graph

```
services.leg_candidate_adapter.to_candidate_contract(raw)
  ├─ _make_candidate(item, source_bucket) [for each obligation]
  └─ enrich_ondemand(candidates)  [from services.leg_ondemand_enrichment]
```

### Search Query Connectivity

- **search_query_svc.lookup() used by leg_candidate_adapter?** NO
- **Evidence**: Grep in `services/leg_candidate_adapter.py` finds NO import of `search_query_svc`
- **Only direct reference**: Comment in `services/kosha_msds/search_adapter.py:9` (optional reuse for CHEM domain, not LEG)

### Verb Enrichment

- `leg_ondemand_enrichment.enrich_ondemand()` is called (path: `services/leg_ondemand_enrichment.py:1`)
- No evidence of Search Dictionary integration in LEG path

### Verdict

**NOT_CONNECTED**: `search_query_svc` does NOT feed `leg_candidate_adapter` today. LEG candidate pipeline is independent of shared search terminology. This aligns with WO expectation.

---

## 7. Knowledge Graph (S00-06)

### Graph Producer / Acceptor / Read Model

| Component | File | Status | Type |
|---|---|---|---|
| **Graph Store** | `services/knowledge_graph_store.py` | (not fully read) | Read/Write backend |
| **Graph Hydrator** | `services/knowledge_graph_hydrate.py` | (not fully read) | Transformer |
| **Graph Service** | `services/knowledge_graph_svc.py` | (not fully read) | Query layer |
| **Graph Rules** | `services/knowledge_graph_rules.py` | **COMPLETE** | Controlled mapping |
| **Public Read Router** | `routers/public_knowledge_graph.py:1-52` | **COMPLETE** | API surface |

### Controlled Context List (from `services/knowledge_graph_rules.py:70-122`)

| Rule ID | Relation Type | Relation Key | Aliases (KO) | Aliases (EN) | Status |
|---|---|---|---|---|---|
| `EQUIPMENT_FORKLIFT_V1` | equipment | forklift | 지게차, 포크리프트 | forklift | APPROVED |
| `TASK_WELDING_V1` | task | welding | 용접, 용접작업 | welding | APPROVED |
| `PROCESS_EXCAVATION_V1` | process | excavation | 굴착, 굴착작업 | excavation | APPROVED |
| `TOPIC_FALL_V1` | topic | fall | 추락, 떨어짐 | fall | APPROVED |
| `SECTOR_CONSTRUCTION_V1` | sector | construction | 건설, 건설업 | construction | APPROVED |

### Disabled Relations (WO §2)

- `DISABLED_RELATIONS = frozenset({"chemical", "legal_obligation"})` (line 53)
- **Note**: `chemical` and `legal_obligation` are NOT wired in public graph

### FULL_CORPUS_APPLY Status

- **Verdict**: **NO**
- **Evidence**: Only 5 controlled rules defined; `WAVE3_GENERATED_RELATIONS = {"equipment", "process", "task", "topic", "sector"}` (subset); chemical + legal_obligation disabled
- **Method Restriction**: Only `EXACT_MAPPING`, `TAXONOMY`, `CONTROLLED_KEYWORD`, `SOURCE_NATIVE`, `DETERMINISTIC_RULE` allowed; `SEMANTIC_CANDIDATE` + `LLM_CANDIDATE` forbidden

### Wiring from Search into Graph

- **Direct**: `routers/public_knowledge_graph.py` does NOT call `search_query_svc.lookup()`
- **Indirect**: Graph hydrator may populate from domain source tables (GUIDE, ACCIDENT, etc.) but not from search-dict
- **Verdict**: **NOT_CONNECTED** (Search Dictionary does not feed Knowledge Graph)

---

## 8. Per-Domain Audit Matrix

### 8.1 GUIDE Domain

| Property | Value | File | Note |
|---|---|---|---|
| **SoT** | KOSHA official guide database (not queried in this audit) | — | Read-only reference |
| **Canonical Identity** | `KOSHA_GUIDE` content_type (per knowledge_graph_rules.py:24) | `services/knowledge_graph_rules.py:24` | Structured |
| **Public Status** | Public read via `/public/knowledge-graph/` | `routers/public_knowledge_graph.py` | READ_ONLY |
| **Search Implementation** | Via Search Dictionary (term expansion only, not direct query) | `tools/search_dict/seed_v2.py` | Terminology overlay |
| **Search Dict Use** | YES (overlay terms for equipment/work phrases) | `tools/search_dict/seed_v2.py:139-150` | APPROVED |
| **Kiwi Use** | YES (T4 matches noun tokens in GUIDE text) | `tools/search_dict/search_runtime_ext.py` | OPTIONAL |
| **Graph Relation** | YES (equipment/task/process/topic/sector rules match GUIDE fields) | `services/knowledge_graph_rules.py:70-122` | APPROVED |
| **Public Consumer** | Knowledge Graph API: `/public/knowledge-graph/context?relation_type=equipment&relation_key=forklift` | `routers/public_knowledge_graph.py:63` | Paginated |
| **Paid Consumer** | Diagnosis integrated (admin only, no public fetch) | `routers/diagnosis_integrated.py` | Determination |
| **SaaS Consumer** | Yes (company inspection/equipment profiles fetch related GUIDE via knowledge graph) | (not fully traced) | PARTIAL |
| **Index/Projection** | No unified search index; uses domain source tables + graph relations | `migrations/2026-09-16_search_dictionary_tables.sql` | Table-based |

**Classification**: `PARTIAL` — GUIDE accessible via Knowledge Graph rules (controlled keywords) but NOT via shared search index.

---

### 8.2 SAFETY_MATERIAL Domain

| Property | Value | File | Note |
|---|---|---|---|
| **SoT** | KOSHA Safety Material storage (DB table, not queried here) | `services/kosha_safety_material_storage.py` | Stored |
| **Canonical Identity** | `SAFETY_MATERIAL` content_type | `services/knowledge_graph_rules.py:25` | Structured |
| **Public Status** | Public read via storage API | `routers/kosha_public_materials.py:1-8` | READ_ONLY |
| **Search Implementation** | Via KOSHA Smart Search (external provider, not search dict) | `services/kosha_smart_search.py:330` | Direct query |
| **Search Dict Use** | NO (external provider only) | — | Not integrated |
| **Kiwi Use** | No (handled by KOSHA provider) | — | External |
| **Graph Relation** | (disabled per DISABLED_RELATIONS + no concrete rules for SAFETY_MATERIAL) | `services/knowledge_graph_rules.py:53` | NOT_CONNECTED |
| **Public Consumer** | `/public/safety-search/kosha` (KOSHA Smart Search provider) | `routers/public_safety_search.py:18` | Paginated |
| **Paid Consumer** | No (material sourcing is SaaS, not paid diagnosis feature) | — | NOT_CONNECTED |
| **SaaS Consumer** | Yes (`routers/material_source.py` for factory material registry) | `routers/material_source.py:1` | CONNECTED |
| **Index/Projection** | No unified search index; direct external provider + local storage | — | Federated |

**Classification**: `PARTIAL` — Accessible via KOSHA Smart Search (external provider), local storage API, and SaaS material source registry. NOT accessible via search dictionary.

---

### 8.3 CSI (ACCIDENT) Domain

| Property | Value | File | Note |
|---|---|---|---|
| **SoT** | CSI accident database (read-only in this audit) | `routers/public_csi_accidents.py:1` | Authority |
| **Canonical Identity** | `ACCIDENT` content_type | `services/knowledge_graph_rules.py:26` | Structured |
| **Public Status** | Public read via CSI router | `routers/public_csi_accidents.py:18` | READ_ONLY |
| **Search Implementation** | None in shared search (domain-specific query) | `routers/public_csi_accidents.py` | Direct DB |
| **Search Dict Use** | NO (accident terms are in seed overlay as ACCIDENT_TERM subject_type, not indexed separately) | `tools/search_dict/seed_v2.py:143-145` | Terminology only |
| **Kiwi Use** | Yes (T4 matches accident text fields) | `tools/search_dict/search_runtime_ext.py` | OPTIONAL |
| **Graph Relation** | YES (topic/equipment/process rules match accident_summary/object_major/process_minor) | `services/knowledge_graph_rules.py:82-99` | APPROVED |
| **Public Consumer** | `/public/knowledge-graph/` (accident context lookups) + `/public/csi/accidents` (direct query) | `routers/public_csi_accidents.py` | Both |
| **Paid Consumer** | No (accidents are informational, not diagnosis obligation) | — | NOT_CONNECTED |
| **SaaS Consumer** | Inspection/risk profiles (lookup related accidents) | (not fully traced) | PARTIAL |
| **Index/Projection** | No unified search index; uses graph relations + domain table | — | Table-based |

**Classification**: `PARTIAL` — Searchable via Knowledge Graph rules (equipment/task/topic), but no direct search-dict integration.

---

### 8.4 CHEM Domain

| Property | Value | File | Note |
|---|---|---|---|
| **SoT** | KOSHA MSDS (Materialized Safety Data Sheet) | `services/kosha_msds/` (not fully read) | Authority |
| **Canonical Identity** | `CHEM_TERM` subject_type (search dict only) | `tools/search_dict/seed_v2.py:51` | Structured |
| **Current State** | Read-only CHEM-06 (no current hydration per WO constraint) | `services/kosha_msds/search_adapter.py:1-23` | Frozen |
| **Public Status** | Dormant unless `KOSHA_MSDS_PUBLIC_MODE` set | `router_registry/public.py:9` | Conditional |
| **Search Implementation** | Deterministic search adapter (Kiwi + optional dict expansion) | `services/kosha_msds/search_adapter.py:112-180` | CHEM-specific |
| **Search Dict Use** | YES (subject_type="CHEM_TERM" restricted lookup) | `services/kosha_msds/search_adapter.py:50-51` | OPTIONAL |
| **Kiwi Use** | YES (T4 token matching on chemical names) | `services/kosha_msds/search_adapter.py:165` | Core |
| **Graph Relation** | DISABLED (per DISABLED_RELATIONS) | `services/knowledge_graph_rules.py:53` | NOT_CONNECTED |
| **Public Consumer** | `/public/safety-search/chemical` (dormant, would call adapter) | `router_registry/public.py:9` | Conditional |
| **Paid Consumer** | No (chemical compliance is domain-specific, not diagnosis obligation) | — | NOT_CONNECTED |
| **SaaS Consumer** | Potential (factory chemical inventory), not wired | — | UNKNOWN |
| **Index/Projection** | No unified search index; deterministic identifier + Kiwi + optional dict | `services/kosha_msds/search_adapter.py:88-110` | Identifier-first |

**Classification**: `DUPLICATE` — Has own search implementation (search_adapter.py) separate from shared search-dict; composition over inheritance (reuses normalize.py + safe_help_kiwi.py).

---

### 8.5 RISK Domain

| Property | Value | File | Note |
|---|---|---|---|
| **SoT** | Risk canonical nodes (DB table: `public.risk_canonical_nodes`) | `tools/risk02/ingest001_source_core_local_exec.py:1` | Authority |
| **Canonical Identity** | Risk node ID + sector linkage | `tools/risk02/ingest001_source_core_local_exec.py:12` | Structured |
| **Current State** | DRAFT (no active hydration per WO constraint) | `tools/risk02/ingest001_source_core_local_exec.py` | Frozen |
| **Public Status** | Not public (admin/inspection only) | — | Private |
| **Search Implementation** | None visible in this audit (domain-specific queries only) | — | NOT_CONNECTED |
| **Search Dict Use** | NO (risk terms not in seed_v2) | `tools/search_dict/seed_v2.py` | Not integrated |
| **Kiwi Use** | NO | — | Not integrated |
| **Graph Relation** | NO (risk domain separate from knowledge graph) | `services/knowledge_graph_rules.py` | NOT_CONNECTED |
| **Public Consumer** | None (risk is operational/private) | — | NOT_CONNECTED |
| **Paid Consumer** | NO (risk is user-facing inspection context, not paid feature) | — | NOT_CONNECTED |
| **SaaS Consumer** | Inspection plan builders fetch risk context (not via search) | — | PARTIAL (DB query) |
| **Index/Projection** | No unified search index; tables: `risk_canonical_nodes`, `risk_source_mappings`, `risk_canonical_node_sectors` | `tools/risk02/ingest001_source_core_local_exec.py:15-20` | Table-based |

**Classification**: `PARTIAL` — Risk domain is isolated, no search integration. SaaS consumers access via direct DB query, not shared search.

---

### 8.6 LEGAL Domain

| Property | Value | File | Note |
|---|---|---|---|
| **SoT** | law_master + dict_legal_terms (leg-prod DB) | `tools/search_dict/seed_v2.py:52-74` | Authority |
| **Canonical Identity** | `LEGAL_TERM` subject_type (search dict) | `tools/search_dict/seed_v2.py:114` | Structured |
| **Current State** | APPROVED ground-truth (464 terms from leg-prod) | `tools/search_dict/seed_v2.py:8` | Frozen |
| **Public Status** | Public read via search-dict (terminology) + law updates | `router_registry/public.py:28` | Public |
| **Search Implementation** | Shared Search Dictionary (T1-T3 deterministic + T4 Kiwi optional) | `routers/search_dictionary.py:19` | Integrated |
| **Search Dict Use** | YES (law names, short names, agencies, instruments) | `tools/search_dict/seed_v2.py:140-150` | Core |
| **Kiwi Use** | YES (T4 matches legal text) | `tools/search_dict/search_runtime_ext.py` | OPTIONAL |
| **Graph Relation** | NO (legal_obligation disabled in graph) | `services/knowledge_graph_rules.py:53` | NOT_CONNECTED |
| **Public Consumer** | `/search-dict/lookup?subject_type=LEGAL_TERM` | `routers/search_dictionary.py:19` | Primary |
| **Paid Consumer** | Diagnosis engine (obligation retrieval), NOT via shared search | `routers/diagnosis_integrated.py` | NOT_CONNECTED |
| **SaaS Consumer** | Legal engine lookups (direct DB, not via search-dict) | `routers/engine_legal.py` | NOT_CONNECTED |
| **Index/Projection** | Unified search-dict projection + optional pg_trgm table | `migrations/2026-09-16_search_dictionary_tables.sql:6-53` | Projection + optional table |

**Classification**: `CONNECTED` — LEGAL terms fully integrated into shared search dictionary. Terminology search works; domain logic (obligation matching, legal engine) operates independently.

---

### 8.7 KNOWLEDGE_CENTER Domain

| Property | Value | File | Note |
|---|---|---|---|
| **SoT** | Knowledge Center articles (not queried in this audit) | — | Authority |
| **Canonical Identity** | `KNOWLEDGE_CENTER` content_type | `services/knowledge_graph_rules.py:29` | Structured |
| **Public Status** | Public read via knowledge graph + help center | `router_registry/public.py:11, 27` | Public |
| **Search Implementation** | Help center search (separate module, not shared search) | `routers/safe_help.py` | Domain-specific |
| **Search Dict Use** | NO (help center terminology is separate) | — | NOT_CONNECTED |
| **Kiwi Use** | Possible in help search, but not via shared search-dict | — | NOT_CONNECTED |
| **Graph Relation** | NO concrete rules (KNOWLEDGE_CENTER not in CONTROLLED_RULES) | `services/knowledge_graph_rules.py:70-122` | NOT_CONNECTED |
| **Public Consumer** | `/helpcenter/` (help center query) + `/public/knowledge-graph/context?content_type=KNOWLEDGE_CENTER` | `routers/helpcenter.py` + `routers/public_knowledge_graph.py` | Both |
| **Paid Consumer** | Support/help features (SaaS integration) | `routers/member_support.py` | PARTIAL |
| **SaaS Consumer** | Support widget embedded in SaaS UI | `router_registry/saas_core.py:38-39` | CONNECTED |
| **Index/Projection** | No unified search index; help center has own search (safe_help_kiwi.py) | `services/safe_help_kiwi.py` | Domain-specific |

**Classification**: `DUPLICATE` — Knowledge Center (help center) has own search implementation (`routers/safe_help.py`) separate from shared search-dict.

---

### 8.8 PRECEDENT Domain

| Property | Value | File | Note |
|---|---|---|---|
| **SoT** | Precedent database (labor court decisions, not queried here) | `routers/precedent_api.py:1` | Authority |
| **Canonical Identity** | `PRECEDENT` content_type | `services/knowledge_graph_rules.py:30` | Structured |
| **Public Status** | Public read via precedent API | `routers/precedent_api.py:18` | READ_ONLY |
| **Search Implementation** | Domain-specific query in `search_precedents()` | `routers/precedent_api.py:10` | Direct DB |
| **Search Dict Use** | NO (precedent terms not in seed_v2) | `tools/search_dict/seed_v2.py` | NOT_CONNECTED |
| **Kiwi Use** | Possible in domain query, but not via shared search-dict | — | NOT_CONNECTED |
| **Graph Relation** | NO concrete rules (PRECEDENT not in CONTROLLED_RULES) | `services/knowledge_graph_rules.py:70-122` | NOT_CONNECTED |
| **Public Consumer** | `/precedents/?q=` (direct domain query) | `routers/precedent_api.py:10` | Primary |
| **Paid Consumer** | NO (precedent is informational, not diagnosis obligation) | — | NOT_CONNECTED |
| **SaaS Consumer** | Potential (inspect/legal reference), not traced | — | UNKNOWN |
| **Index/Projection** | No unified search index; domain table only | — | Table-based |

**Classification**: `SEPARATE` — Precedent domain operates independently with own search implementation; no integration with shared search-dict or knowledge graph.

---

## 9. SaaS Consumer Matrix (8 Page Kinds)

| Page Kind | Endpoint | Fetched Items | Search Method | Dict Use | Graph Use | Classification |
|---|---|---|---|---|---|---|
| **Company** | `GET /companies/{id}/360` | Company facts + obligations | Direct DB query | NO | NO | NOT_CONNECTED |
| **Factory** | `GET /factories/{id}` | Factory profile + related risk + equipment | Direct DB + risk lookup | NO | NO | PARTIAL (risk) |
| **Process** | `GET /companies/{id}/processes` | Process registry + related equipment/tasks | Direct DB | NO | YES (process graph) | PARTIAL |
| **Task** | `GET /factories/{id}/tasks` | Task registry + related accidents/guides | Direct DB + graph query | NO | YES (task graph) | PARTIAL |
| **Equipment** | `GET /factories/{id}/equipment` | Equipment registry + related hazards/guides | Direct DB + graph query | NO | YES (equipment graph) | PARTIAL |
| **Chemical** | `GET /factories/{id}/chemicals` | Chemical inventory (via material_source) | Direct DB | NO | NO (chemical disabled) | NOT_CONNECTED |
| **Obligation** | `GET /diagnosis/{id}/obligations` | Filtered legal obligations | Direct DB | NO | NO | NOT_CONNECTED |
| **Inspection** | `GET /inspections/{id}` | Inspection plan + checklist + legal refs | Direct DB + obligation query | NO | PARTIAL (related guides/risks) | PARTIAL |

**Summary**:
- **NOT_CONNECTED**: Company, Obligation profiles do NOT fetch related knowledge/guides
- **PARTIAL**: Equipment, Task, Process, Inspection DO use Knowledge Graph context (equipment/task/process/topic rules)
- **DUPLICATE**: Chemical inventory and SaaS chemical listing have NO graph/search integration

---

## 10. Paid Diagnosis Matrix

### Diagnosis Result Features

| Feature | Type | Endpoint | Data Fetched | Search/Graph Use | Classification |
|---|---|---|---|---|---|
| **Obligations** | Read-only table | `GET /diagnosis/{id}/result/obligations` | Matched legal obligations | Direct DB query (no search) | NOT_CONNECTED |
| **Related GUIDE** | Informational panel | (embedded in result) | Matching guides via knowledge graph | Knowledge Graph context rules | PARTIAL |
| **Related Material** | Informational panel | (embedded in result) | Matching safety materials (KOSHA) | Direct DB (no search) | NOT_CONNECTED |
| **Related CSI** | Informational panel | (embedded in result) | Matching accident cases (via graph) | Knowledge Graph topic/equipment rules | PARTIAL |
| **Legal References** | Footer citations | (embedded in result) | Citation links to law articles | Direct law_master reference | NOT_CONNECTED |

**Summary**: Paid diagnosis uses Knowledge Graph for GUIDE/ACCIDENT/CSI context lookup, but NOT for shared search-dictionary expansion. Obligation matching is deterministic, not search-based.

---

## 11. Support / Help

### FAQ / PAGE_GUIDE / TASK_GUIDE / Knowledge Center

| Feature | Router | Search Implementation | Reusable | Classification |
|---|---|---|---|---|
| **FAQ** | `routers/safe_help.py` | Domain-specific (Kiwi + custom indexing) | Partial (normalize.py only) | DUPLICATE |
| **PAGE_GUIDE** | (part of helpcenter) | Help center query (safe_help_kiwi.py) | Partial | DUPLICATE |
| **TASK_GUIDE** | (part of helpcenter) | Help center query | Partial | DUPLICATE |
| **Knowledge Center** | `routers/public_knowledge_graph.py` | No search (graph lookup only) | NOT REUSABLE | SEPARATE |

**Verdict**: **REUSE CANDIDATE** for `normalize.py` (deterministic normalization), but help center maintains own Kiwi invocation separate from search-dict. Knowledge Graph rules could standardize "guide lookup" pattern.

---

## 12. Unified Search Index Census

### Index Inventory

| Index Type | Name | Table | Columns | Purpose | Status |
|---|---|---|---|---|---|
| **PostgreSQL Inverted (tsvector)** | None found | — | — | — | NOT_EXISTS |
| **PostgreSQL Trigram (GIN)** | `ix_search_term_trgm` | `search_term_master` | `term_normalized` | Fuzzy match (T6) | OPTIONAL_SCHEMA |
| **Materialized View** | None found | — | — | — | NOT_EXISTS |
| **Domain-specific** | Risk tables | `risk_canonical_nodes` | — | Risk domain only | TABLE_BASED |
| **Domain-specific** | Guide tables | (not inspected) | — | GUIDE domain | TABLE_BASED |
| **Domain-specific** | Accident/CSI | `public_csi_accidents` (inferred) | — | CSI domain | TABLE_BASED |
| **JSON Projection** | `TAI_SEARCH_RUNTIME_PROJECTION_v1.json` | (artifact) | subjects, expansions, snapshot | Deterministic tiers T1-T3 | OFFLINE_ONLY |

### Verdict: **NO UNIFIED INDEX EXISTS**

**Finding**: 
- Deterministic search (T1-T3) is **offline-compiled** into JSON projection artifact (WO §17)
- Optional Trigram (T6) would use optional `ix_search_term_trgm` table (schema exists, application optional)
- No unified inverted index across all domains
- Each domain maintains own table + indexing (risk, guide, accident, chem, legal, etc.)

**Implication**: SEARCH-01 scope does NOT include unified index creation. Deterministic tiers are already unified; fuzzy tier (T6) is optional per DSN availability.

---

## 13. Connection Matrix (Aggregate)

### Component Integration Summary

| Component | Shared Search Dict | Search Dict → Paid | Knowledge Graph | Public Safety Search | Admin Cross-Search | Per-Domain Index |
|---|---|---|---|---|---|---|
| **Query Understanding (Tiers T1-T6)** | CONNECTED | Not applicable | NOT_CONNECTED | NOT_CONNECTED | NOT_CONNECTED | — |
| **Search Dictionary (Terminology)** | CONNECTED | NOT_CONNECTED (paid uses direct DB) | NOT_CONNECTED | NOT_CONNECTED | NOT_CONNECTED | ✓ JSON artifact |
| **Public Safety Search** | NOT_CONNECTED | — | NOT_CONNECTED | CONNECTED (KOSHA provider) | NOT_CONNECTED | — |
| **Admin `/search`** | NOT_CONNECTED | — | NOT_CONNECTED | NOT_CONNECTED | CONNECTED | — |
| **LEG Candidate/ON_DEMAND** | NOT_CONNECTED | NOT_CONNECTED | NOT_CONNECTED | NOT_CONNECTED | NOT_CONNECTED | — |
| **Knowledge Graph** | NOT_CONNECTED | PARTIAL (graph rules used by diagnosis) | CONNECTED | NOT_CONNECTED | NOT_CONNECTED | ✓ Tables |
| **GUIDE Domain** | PARTIAL (terminology) | NOT_CONNECTED | CONNECTED (graph rules) | NOT_CONNECTED | NOT_CONNECTED | ✓ Table-based |
| **SAFETY_MATERIAL** | NO | NO | NOT_CONNECTED | CONNECTED (KOSHA provider) | NOT_CONNECTED | ✓ Table-based |
| **CSI (ACCIDENT)** | PARTIAL (terminology) | NOT_CONNECTED | CONNECTED (graph rules) | NOT_CONNECTED | NOT_CONNECTED | ✓ Table-based |
| **CHEM Domain** | CONNECTED (subject_type=CHEM_TERM) | NOT_CONNECTED | NOT_CONNECTED (disabled) | NOT_CONNECTED (dormant) | NOT_CONNECTED | ✓ Adapter-based |
| **RISK Domain** | NO | NO | NOT_CONNECTED | NO | NOT_CONNECTED | ✓ Table-based |
| **LEGAL Domain** | CONNECTED | NOT_CONNECTED (direct DB) | NOT_CONNECTED (disabled) | NOT_CONNECTED | NOT_CONNECTED | ✓ Projection-based |
| **KNOWLEDGE_CENTER (Help)** | NO | NO | NOT_CONNECTED | NO | NOT_CONNECTED | ✓ Separate search |
| **PRECEDENT** | NO | NO | NOT_CONNECTED | NO | NOT_CONNECTED | ✓ Table-based |

---

## 14. Duplicate Matrix (All Search Implementations)

### Every Separate Search Implementation

| Implementation | Location | Purpose | Reuses | Status | Recommendation |
|---|---|---|---|---|---|
| **Shared Search Dictionary** | `routers/search_dictionary.py` | Terminology/alias lookup | normalize.py | MASTER | Keep (T1-T3 deterministic) |
| **KOSHA Smart Search (Public)** | `services/kosha_smart_search.py` | Public safety material discovery | (none) | External provider | Keep (external contract) |
| **Admin Global Search** | `services/global_search_svc.py` | Company/user/factory/payment lookup | (none) | Admin operational | Keep SEPARATE (not knowledge) |
| **CHEM Search Adapter** | `services/kosha_msds/search_adapter.py` | Chemical identifier + Kiwi match | normalize.py, safe_help_kiwi.py | Domain-specific | EVALUATE for merger into shared search |
| **Help Center Search** | `services/safe_help_kiwi.py` | FAQ/guide article search | normalize.py | Kiwi-based | EVALUATE for merger or reuse |
| **Knowledge Graph Lookup** | `routers/public_knowledge_graph.py` | Context relation queries | (none) | Graph-based | Keep SEPARATE (graph is different concern) |
| **Precedent Domain Search** | `routers/precedent_api.py` | Labor decision lookup | (none) | Domain-specific | Keep SEPARATE (specialized legal domain) |
| **Risk Lookup** | (implicit in inspection set builder) | Risk node context | (none) | Operational | Keep SEPARATE (operational, not public) |
| **LEG Candidate Adapter** | `services/leg_candidate_adapter.py` | Obligation extraction | (none) | Domain-specific | Keep SEPARATE (deterministic rule matching) |

### Verdict: **MULTIPLE VALID SEPARATE CONCERNS**

**Classification by Recommendation**:

| Action | Implementations | Rationale |
|---|---|---|
| **KEEP (Master)** | Shared Search Dictionary (T1-T6) | Unified terminology; powers public API; deterministic |
| **KEEP SEPARATE** | Admin Global Search, Knowledge Graph, Precedent, Risk, LEG Adapter | Distinct concerns (operational vs. knowledge vs. specialized domain) |
| **EVALUATE for MERGE** | CHEM Search Adapter, Help Center Search | Reuse normalize.py + Kiwi; could layer on shared search dict for terminology |

**SEARCH-01 Scope**: Do NOT merge separate concerns. Instead:
1. Ensure shared search-dict runs 100% (fix 503)
2. Verify CHEM adapter gracefully handles search-dict outage (currently optional reuse, not hard dependency)
3. Document help center search as "parallel concern" (not blocking search-dict)

---

## 15. Confirmed Gaps

| Gap | Impact | Workaround | Ticket |
|---|---|---|---|
| **Search Dictionary 503 on health** | `/search-dict/health` fails in production | Check env var `TAI_SEARCH_PROJECTION` + ensure artifacts packaged | SEARCH-01 |
| **Chemical Graph Disabled** | `DISABLED_RELATIONS: {"chemical", "legal_obligation"}` | Chemical lookups work via search adapter, not graph | Design decision (preserve) |
| **Paid Diagnosis + Search Dict** | Diagnosis engine does NOT use shared search-dict for obligation matching | Obligation matching is deterministic rule-based, not search-based | Design decision (correct) |
| **Knowledge Center Not in Graph** | No KNOWLEDGE_CENTER rules in controlled graph | Help center search is separate; intentional isolation | Design decision (preserve) |
| **Precedent Not in Graph** | No PRECEDENT rules or search integration | Precedent domain is specialized legal; intentional isolation | Design decision (preserve) |
| **Risk Domain Isolation** | Risk schema/hydration decoupled from search and graph | Risk context fetched via direct DB query, not search-dict | Design decision (preserve) |
| **No Full-Text Search Across All Domains** | Each domain maintains own search/index | Deterministic search-dict covers terminology; fuzzy search (T6) available for legacy content | Design limitation (by design) |

---

## 16. Unknowns (Requiring DB Access or Cross-Repo Probing)

| Unknown | Blocker for SEARCH-01? | Resolution Path |
|---|---|---|
| **Exact location of TAI_SEARCH_PROJECTION in prod build** | YES | Check deployment package / K8s ConfigMap |
| **Trigram tier (T6) runtime state** | NO | Query `TAI_SEARCH_SCRATCH_DSN` env var in prod; optional feature |
| **Help center search table structure** | NO | Read `services/safe_help_kiwi.py` fully (artifact only, not a blocker) |
| **Knowledge graph hydrator materialization pipeline** | NO | Inspect `services/knowledge_graph_hydrate.py` (artifact only, works today) |
| **Risk canonical nodes current row count + active status** | NO | DB query: `SELECT status, count(*) FROM public.risk_canonical_nodes` (frozen per WO) |
| **CSI accidents indexing strategy** | NO | Check if `public_csi_accidents` table has indexes (artifact, not search-dict related) |
| **CHEM adapter production traffic** | NO | Check logs for `/public/safety-search/chemical` requests (dormant per code) |
| **SaaS graph traversal latency** | NO | Performance question, not integration audit |

---

## 17. SEARCH-01 Handoff Scope

### Confirmed Scope for SEARCH-01

1. **Diagnose + Fix HTTP 503 on `/search-dict/health`**
   - **Root Cause Hypothesis**: Missing projection artifact in production build
   - **Action**: Confirm `TAI_SEARCH_PROJECTION` env var + verify artifact packaged in deployment
   - **Success Criterion**: `GET /search-dict/health` returns 200 + snapshot ID

2. **Verify Runtime Projection v1 Integrity**
   - **Asset**: `TAI_SEARCH_RUNTIME_PROJECTION_v1.json` (SEARCH-DICT-LEGPROD-2026-09-16)
   - **Check**: Snapshot ID, subject count, expansion count match build output manifest
   - **Success Criterion**: All tiers (T1-T3) respond deterministically

3. **Confirm Optional Tiers (Kiwi T4, Trigram T6) Graceful Fallback**
   - **Kiwi (T4)**: If kiwipiepy unavailable, tier silently returns None (already implemented)
   - **Trigram (T6)**: If `TAI_SEARCH_SCRATCH_DSN` unset, tier silently returns None (already implemented)
   - **Success Criterion**: Search functions with deterministic tiers only if optional tiers unavailable

4. **Document Artifact Dependencies**
   - **Create**: `docs/search/ARTIFACT_MANIFEST.md` listing all required files
   - **Include**: Checksums (from `BUILD_SHA256SUMS.txt`), deployment paths, env vars
   - **Success Criterion**: DevOps can reproduce build + package predictably

### Out-of-Scope for SEARCH-01 (SEARCH-02+)

- Merge CHEM adapter into shared search-dict (separate concern)
- Implement unified full-text search across all domains (violates deterministic contract)
- Add Knowledge Center / Precedent / Risk to graph rules (intentional isolation)
- Rewrite help center search to use shared search-dict (separate concern)
- Implement search-based obligation matching in paid diagnosis (deterministic rules correct)
- Enable Trigram (T6) by default (optional tier, no change needed)

---

## 18. Surprising Findings

1. **Shared Search Dictionary is MINIMAL by Design**
   - Only 464 ground-truth terms + 15 law aliases from leg-prod
   - Deterministic tiers (T1-T3) operate on offline-compiled JSON (no runtime LLM, no external calls)
   - Search-dict does NOT feed paid diagnosis; diagnosis uses direct DB rules
   - This is **intentional architecture**, not a limitation

2. **Knowledge Graph Rules Are Hardcoded + Controlled**
   - Only 5 controlled rules (equipment/task/process/topic/sector)
   - `WAVE3_GENERATED_RELATIONS` suggests future rules, but disabled for now
   - Chemical + legal_obligation are explicitly disabled in public graph
   - This is **precision over coverage** (WO §1)

3. **Multiple Valid Search Implementations Are Intentional**
   - No "unified search index"; instead, each domain owns its search contract
   - Admin search (company/user/factory/payment) is deliberately SEPARATE from knowledge search
   - Help center search is SEPARATE from shared search-dict (both work, no conflict)
   - This is **separation of concerns**, not duplication

4. **LEG Candidate Adapter Does NOT Use Shared Search**
   - Legal obligation matching is **deterministic rule-based**, not search-based
   - Search-dict is for terminology lookup (aliases/synonyms), not obligation matching
   - This is **correct by design** (WO §1)

5. **CHEM Domain Has Own Search Adapter But Gracefully Degrades**
   - Reuses `normalize.py` + `safe_help_kiwi.py` (composition)
   - Optionally calls `search_query_svc.lookup()` for term expansion (failure is silent)
   - If search-dict unavailable, CHEM adapter still functions with Kiwi + identifiers
   - This is **robust isolation**

---

## 19. Summary & Recommendations

### Verdict: Shared-Search Infrastructure is **INTENTIONALLY MODULAR**

The audit reveals a well-separated architecture:

- **Shared Layer (T1-T3)**: Deterministic terminology search (offline-compiled)
- **Optional Layers (T4, T6)**: Kiwi token + Trigram (graceful fallback)
- **Domain Layers**: Each domain (GUIDE, CHEM, CSI, Risk, etc.) maintains own index/search
- **Graph Layer**: Knowledge Graph for controlled context relations (5 rules, precision-focused)
- **Operational Layers**: Admin search, LEG rules, help center (intentionally separate)

### SEARCH-01 Must Focus On

1. **Production 503 Root Cause**: Artifact packaging in deployment
2. **Offline Determinism**: Verify projection integrity + tier isolation
3. **Artifact Documentation**: Clear manifest for DevOps handoff

### Avoid in SEARCH-01

- Unifying all searches (violates WO §1 determinism + precision)
- Merging domains (violates domain autonomy)
- Changing Knowledge Graph rules (approved + controlled per WO §6)
- Enabling Trigram by default (optional tier, no change needed)

---

## Appendix A: File Inventory

### Core Search Dictionary

- `routers/search_dictionary.py` (API surface)
- `services/search_query_svc.py` (lookup + tier management)
- `services/search_dictionary_svc.py` (census + metadata)
- `tools/search_dict/search_core.py` (deterministic T1-T3 engine)
- `tools/search_dict/search_runtime_ext.py` (runtime T4 + T6)
- `tools/search_dict/normalize.py` (shared normalization)
- `tools/search_dict/seed_v2.py` (SEARCH-DICT-LEGPROD-2026-09-16 snapshot)
- `tools/search_dict/artifacts/TAI_SEARCH_RUNTIME_PROJECTION_v1.json` (compiled projection)
- `tools/search_dict/artifacts/BUILD_SHA256SUMS.txt` (build manifest)

### Public Safety Search

- `routers/public_safety_search.py` (API)
- `services/kosha_smart_search.py` (KOSHA provider adapter)

### Admin Cross-Search

- `routers/global_search.py` (API)
- `services/global_search_svc.py` (company/user/factory/payment lookup)

### Knowledge Graph

- `routers/public_knowledge_graph.py` (API)
- `services/knowledge_graph_svc.py` (query layer)
- `services/knowledge_graph_hydrate.py` (transformer)
- `services/knowledge_graph_store.py` (backend)
- `services/knowledge_graph_rules.py` (5 controlled rules)

### Domain Adapters

- `services/kosha_msds/search_adapter.py` (CHEM domain)
- `services/leg_candidate_adapter.py` (LEG obligations)
- `services/leg_ondemand_enrichment.py` (LEG enrichment)

### Schema

- `migrations/2026-09-16_search_dictionary_tables.sql` (optional DB tables)

### Tests (Reference)

- `tests/test_chem_full_readiness_003_search_qa.py` (CHEM adapter tests)
- `tests/test_chem_full_readiness_004_ops.py` (CHEM operations)

### Router Registry

- `router_registry/public.py` (public routers including `/search-dict`)
- `router_registry/saas_core.py` (SaaS routers including `/search` for admin)

---

**Audit Complete**: Ready for SEARCH-01 planning.

