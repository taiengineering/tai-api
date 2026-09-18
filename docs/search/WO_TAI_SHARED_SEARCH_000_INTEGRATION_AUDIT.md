# WO-TAI-SHARED-SEARCH-000: Integration Audit (FROZEN STATE) — PATCH-2

**Date**: 2026-09-19 (PATCH-2 revision)
**Scope**: Read-only cross-repo audit of the current TAI shared-search
infrastructure. Deliverable = Connection Matrix + Duplicate Matrix +
SEARCH-01 handoff scope.
**Hard fence honored**: 0 code / 0 DB write / 0 deploy / 0 env change /
0 search-index create / 0 graph apply / 0 RISK ACTIVE change / 0 CHEM
hydration.
**Authority**: subordinate to `PLAN_safety-knowledge-hub-master_v0.1.md`
and `PLAN_safety-knowledge-object-implementation_v1.md`, and to
`docs/TAI_SHARED_SEARCH_MASTER_PLAN_v2.md`. This document DESCRIBES the
current state; it does not redecide the target.

---

## 1. Canonical repo anchors (MAIN only)

The primary evidence tree for this audit is each repo's `origin/main`.

| Repo | GitHub | `origin/main` HEAD |
|------|--------|--------------------|
| **tai-api** | `taiengineering/tai-api` | `7d033721256113825199eff288a6ffeb6f3ce848` |
| **tai-www** | `taiengineering/tai-www` | `04a6955e1973f957062135b16214f6a95735384c` |
| **tai-admin** | `taiengineering/tai-admin` | `5f2d2cb079e5a9b47ed621a14678ed7bb07f3c52` |

### Role labels (renamed per PATCH-2 §B)

```text
tai-www         = Public / marketing / discovery surface
/safety-search  = Public safety knowledge search surface
tai-admin       = SaaS application surface (Vue3 vue3/src/pages/**)
tai-api         = Backend API (routers/**, services/**)
```

### Non-canonical local cross-check worktrees

The following working checkouts were used only to cross-check that
feature branches carry the same shape as `main`. They are NOT the
audit's evidence source.

| Working dir | HEAD | Branch | Role |
|---|---|---|---|
| `/Users/taiwangsim/Desktop/tai-api-obj-chem` | `7d033721` | tracks origin/main | primary tai-api checkout (identical to main) |
| `/Users/taiwangsim/Desktop/tai-api` | `b36e032e` | `feat/free-result-additional-information` | non-canonical cross-check |
| `/Users/taiwangsim/Desktop/tai-www-seo-03c-meta` | `9723b955` | `feature/seo-03c-2-marketing` | non-canonical cross-check |
| `/Users/taiwangsim/Desktop/tai-www-seo-03b-kb` | `d02ac711` | `feature/seo-03b-kb-decouple` | non-canonical cross-check |
| `/Users/taiwangsim/Desktop/tai-www` | `fc44c299` | `wo-safety-library-001-wp1c-r4c` | landing site (separate repo `taiengineering/www`), not the SaaS surface |
| `/Users/taiwangsim/Desktop/tai-engineering/tai-admin` | `447b04c7` | `feat/sem003-diving-family-ui` | non-canonical cross-check |

All `git show origin/main:<path>` reads in the rest of this document
resolve against the SHAs in the canonical table above.

---

## 2. Query Understanding stack (S00-01)

### Tier map (deterministic → optional)

| Tier | Name | Kind | File | Runtime dep |
|------|------|------|------|-------------|
| T1 | EXACT | deterministic | `tools/search_dict/search_core.py` | none |
| T2 | NORMALIZED_EXACT | deterministic | `tools/search_dict/search_core.py` | none |
| T2b | PUNCTUATION | deterministic | `tools/search_dict/search_core.py` | none |
| T3 | ALIAS / SYNONYM (APPROVED expansions) | deterministic | `tools/search_dict/search_core.py` | none |
| T4 | KIWI TOKEN | optional | `services/search_query_svc.py:70-83` via `search_runtime_ext.TokenTier` | `kiwipiepy` package |
| T6 | TRIGRAM | optional | `services/search_query_svc.py:86-102` via `search_runtime_ext.TrigramTier` | `TAI_SEARCH_SCRATCH_DSN` (Postgres w/ pg_trgm) |

### Graceful degradation

Both optional tiers wrap their init in `try/except`; failure sets an
internal sentinel to `False` (services/search_query_svc.py:82, :101)
and `lookup()` continues with the deterministic tiers only. The
`/search-dict/health` response's `token_tier` / `trigram_tier` flags
report the observed state — **T4/T6 failure is NOT a 503 cause**.

### Normalization

`tools/search_dict/normalize.py` — same functions used at build time
and runtime: `normalize_basic()`, `compact()`, `no_punctuation()`.
Reused by `services/kosha_msds/search_adapter.py` (CHEM).

### Verdict: **CONNECTED** (code + wired routers). Prod runtime state is separately audited in §3.

---

## 3. Search Dictionary (S00-02)

### API surface

| Endpoint | Handler | File:line |
|---|---|---|
| `GET /search-dict/lookup` | `lookup()` | `routers/search_dictionary.py:19` |
| `GET /search-dict/health` | `health()` | `routers/search_dictionary.py:32` |
| `GET /search-dict/census` | `census()` | `routers/search_dictionary.py:41` |

Registered via `router_registry/public.py`.

### Runtime projection loading

`services/search_query_svc.py:25-32` resolves the projection path
from env `TAI_SEARCH_PROJECTION` (default = repo-relative
`tools/search_dict/artifacts/TAI_SEARCH_RUNTIME_PROJECTION_v1.json`).
`_get_projection()` (line 53-58) raises `SearchDictError` if the file
is missing. Router maps that exception → HTTP 503
(`routers/search_dictionary.py:36-37`, `:45-46`).

### Production HTTP 503 root-cause analysis

Verified in this audit against `origin/main` = `7d033721`:

```text
tools/search_dict/artifacts/
  BUILD_SHA256SUMS.txt                    TRACKED IN REPO ✓
  TAI_SEARCH_RUNTIME_PROJECTION_v1.json   NOT TRACKED IN REPO ✗
```

The projection is a **build output** — `BUILD_SHA256SUMS.txt` lists
its expected SHA (line 15) but the file itself is regenerated by
`SEARCH_DICT_SEED=seed_v2 python3 tools/search_dict/build_dictionary.py build <out>`.

Since the runtime projection is not shipped in the repo, `_get_projection()`
raises `SearchDictError` unless one of the following is true in
production:

1. The prod build/CI step generates the projection into
   `tools/search_dict/artifacts/` before service start, OR
2. The prod deployment sets `TAI_SEARCH_PROJECTION` to a pre-built
   artifact path.

Verdicts:

```text
REPO ARTIFACT ABSENCE                = CONFIRMED (this audit)
PROD PACKAGE ARTIFACT ABSENCE        = UNVERIFIED (SEARCH-01 target)
PROD env TAI_SEARCH_PROJECTION       = UNVERIFIED (SEARCH-01 target)
PROD /search-dict/health = 503       = REPORTED (Owner live acceptance)
```

**Removed from 503 candidate list** (previously misclassified):

- ~~Kiwi initialization failure~~ — graceful, sets `token_tier=False`, no 503.
- ~~Trigram initialization failure~~ — graceful, sets `trigram_tier=False`, no 503.
- ~~`TAI_SEARCH_SCRATCH_DSN` connect failure~~ — graceful, no 503.

SEARCH-01 verifies T4/T6 degradation as **separate** from the 503
root cause.

### Search Dictionary build census

`SEARCH_DICT_SEED=seed_v2` is the current production seed. The seed
comprises **more than** the ground-truth 464 + alias 15 files:

| Input | Location | Row count |
|---|---|---|
| `GROUND_TRUTH_464.tsv` | `tools/search_dict/extract/` | 464 rows |
| `LAW_ALIAS_15.tsv` | `tools/search_dict/extract/` | 15 rows |

Additional subject types layered on top by `seed_v2.py`:

- LAW_NAME (~423)
- AGENCY_NAME (~26)
- TECH_TERM (~15)
- EQUIPMENT_TERM
- ACCIDENT_TERM
- GENERAL_TERM
- CHEM_TERM (1 subject `물질안전보건자료` with 3 terms MSDS/SDS/물질안전보건자료 — WO-CHEM-FULL-READINESS-003 receipt)
- Curated relations / expansions (APPROVED only)

The exact runtime census (subjects, indexed_terms, subject_type
distribution) requires either (a) a local deterministic build or (b)
the live `/search-dict/census` response. Neither is materialized in
this audit:

```text
LOCAL BUILD CENSUS         = NOT EXECUTED (SEARCH-01 may run in /tmp)
PROD RUNTIME CENSUS        = UNVERIFIED (blocked by 503)
```

Do not quote "464 + 15 total" as the dictionary size — it is the
extract set, not the projection.

### Verdict: **CONNECTED (code + routers)**; runtime status = pending SEARCH-01.

---

## 4. Public safety-search — re-verified on tai-www main

Layered evidence, re-run against `tai-www origin/main` = `04a6955e`.

### 4.1 tai-www product surface — `/safety-search`

Evidence: `git show origin/main:src/lib/server/safetySearch.js`.

The `GROUP_DEFS` composition on main confirms **7 adapters** (6
internal + 1 external provider):

```text
GROUP_DEFS = Object.freeze([
  { type: 'knowledge',  contentType: 'KNOWLEDGE_CENTER',  label: '지식센터' },
  { type: 'material',   contentType: 'SAFETY_MATERIAL',   label: '안전자료' },
  { type: 'guide',      contentType: 'KOSHA_GUIDE',       label: '안전가이드' },
  { type: 'accident',   contentType: 'ACCIDENT',          label: '재해사례' },
  { type: 'law',        contentType: 'LAW_UPDATE',        label: '개정법령' },
  { type: 'precedent',  contentType: 'PRECEDENT',         label: '판례' },
  { type: 'kosha',      contentType: 'KOSHA_SEARCH',      label: 'KOSHA 공식검색' },
]);
```

Data sources per group (same file, main):
- knowledge / material / precedent → static modules under `src/lib/modules/safety.js`
- guide → `tai-www` server helper `koshaGuides.js` (`listGuides`)
- accident → `csiAccidents.js` (`listCsiAccidents`)
- law → Supabase `law_revision_board` via `sbQuery`
- kosha → external provider (via tai-api endpoint below)

### 4.2 tai-api provider endpoint — `/public/safety-search/kosha`

Only the KOSHA smart-search adapter lives in tai-api. Search
dictionary is **not** invoked by this endpoint today.

### 4.3 Layered verdict

```text
PUBLIC PRODUCT SURFACE (tai-www /safety-search) = CONNECTED / FEDERATED DIRECT ADAPTERS
SHARED SEARCH DICTIONARY INTEGRATION             = NOT_CONNECTED
UNIFIED SEARCH INDEX                              = NOT_EXISTS
KOSHA PROVIDER API (tai-api)                      = CONNECTED
```

Federation lives at the tai-www layer; each domain still runs its own
read against its own source. This matches `GAP-02 Unified Search
Index 없음` in Master Plan v2 §2 (open).

---

## 5. Admin `/search` (S00-04)

Admin cross-search operates over company / user / factory / payment
entities — orthogonal to knowledge-domain search. `KEEP SEPARATE`
verdict stands.

---

## 6. LEG Candidate / ON_DEMAND (S00-05)

Grep across `services/` confirms:

- `services/leg_candidate_adapter.py` — exists, invoked by legal
  applicability flow.
- `services/leg_ondemand_enrichment.py` — exists, wired to
  `leg_candidate_adapter`.
- `services/search_query_svc.py` → `leg_candidate_adapter` — **no
  reference**. Search-dict lookup output is not fed into the
  candidate enrichment path today.

Verdict: **NOT_CONNECTED** (matches `GAP-03 LEG wiring 없음` in
Master Plan v2 §2).

---

## 7. Knowledge Graph (S00-06) — CODE vs PROD split

### 7.1 Code-level controlled rules (5)

From `services/knowledge_graph_rules.py:70-122`:

| rule_id | relation_type | relation_key | match_mode |
|---|---|---|---|
| EQUIPMENT_FORKLIFT_V1 | equipment | forklift | CONTROLLED_PHRASE |
| TASK_WELDING_V1 | task | welding | CONTROLLED_PHRASE |
| PROCESS_EXCAVATION_V1 | process | excavation | CONTROLLED_PHRASE |
| TOPIC_FALL_V1 | topic | fall | CONTROLLED_PHRASE |
| SECTOR_CONSTRUCTION_V1 | sector | construction | **SOURCE_NATIVE** |

The `sector:construction` rule depends on source rows already
carrying a `sector` / `work_type` / `category` value; it does not
scan text.

### 7.2 Production applied contexts (independent DB census — Owner-provided)

```text
equipment / forklift    =    858 edges
process   / excavation  =  1,230 edges
task      / welding     =  1,149 edges
topic     / fall        =  8,539 edges
sector    / construction =     0 edges applied
──────────────────────────────────────────
TOTAL                   = 11,776 edges
```

### 7.3 Verdict split

```text
CODE RULE COUNT              = 5
PROD ACTIVE CONTEXT COUNT    = 4 (sector rule matched 0 source rows)
PROD ACTIVE EDGE COUNT       = 11,776
FULL_CORPUS_APPLY            = NO
```

Code-vs-prod discrepancy is a fact to track, not a design choice —
sector:construction may become active once source columns are
populated. This is exactly `GAP-07 Graph coverage 확장 미완료` in
Master Plan v2.

### 7.4 Search ↔ Graph wiring

No wiring from `search_query_svc` into graph rules today. Graph is
consumed via `routers/public_knowledge_graph.py`, independent from
`/search-dict/*`. This is another instance of `GAP-02` and `GAP-05`.

---

## 8. Per-domain matrix (revised)

Multi-axis view. Each row separates CODE existence from PROD wiring
from consumer layer.

| Domain | Code exists | Prod runtime | Uses shared dict | Uses unified index | Graph relation | Public consumer | SaaS consumer | Paid consumer | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| GUIDE | yes (`koshaGuides.js`, `routers/kosha_guide.py`) | live | no | none exists | forklift/welding/fall rules match | tai-www /safety-search | NOT TRACED | NOT TRACED | PARTIAL |
| SAFETY_MATERIAL | yes (`safety.js` static, admin materials table) | live | no | none exists | none | tai-www /safety-search | NOT TRACED | NOT TRACED | PARTIAL |
| CSI / ACCIDENT | yes (`csiAccidents.js`, tai-api routers) | live | no | none exists | fall rule matches | tai-www /safety-search | NOT TRACED | NOT TRACED | PARTIAL |
| CHEM (MSDS) | yes (`services/kosha_msds/search_adapter.py`) | live (P3 shipped) | **yes** (CHEM_TERM subject type expansion) | none exists | disabled per graph WO §2 | via CHEM-07 public router (dormant) | NOT TRACED | NOT TRACED | PARTIAL — has own retrieval; also consumes shared dict |
| RISK | canonical schema only | 1,110 DRAFT / 0 ACTIVE / 0 sector links | no | none exists | none | none | none | none | **NOT_CONNECTED as consumer** (matches GAP-04) |
| LEGAL | yes (extensive) | live | terminology present in shared dict | none exists | disabled per graph WO §2 | applicability engine independent | applicability engine independent | applicability engine independent | Terminology CONNECTED, wiring GAP-03 |
| KNOWLEDGE_CENTER (Help) | yes (`services/safe_help_kiwi.py`, `routers/safe_help.py` GET /help/search) | live | no (own Kiwi invocation) | none exists | none | tai-www /safety-search knowledge tab | NOT TRACED | NOT TRACED | PARTIAL |
| PRECEDENT | yes (`safety.js` static) | live | no | none exists | none | tai-www /safety-search | NOT TRACED | NOT TRACED | PARTIAL |

Where "NOT TRACED" appears, the audit did not follow an actual
frontend → API call chain in this pass. Those cells must be resolved
via a follow-up SaaS-consumer trace (see §11 unknowns) before any
consumer-migration WO is opened.

---

## 9. Admin & operational search surfaces (verified on main)

Separate from knowledge search. Distinct backend catalog vs SaaS
caller — do not collapse.

| Endpoint | Router file | Kind | Actual caller (tai-admin main) |
|---|---|---|---|
| `GET /help/search` | `routers/safe_help.py` | Help-center Kiwi search (own index) | `vue3/src/pages/help/useHelp.ts` |
| `GET /factory-process/search` | `routers/factory_process_v3.py:66` | Operational process lookup | `vue3/src/pages/process-select/useProcessSelectList.ts` |
| `GET /factory-process/kcsc/search` | `routers/factory_process_v3.py:212` | KCSC master ILIKE search | `vue3/src/pages/process-select/useKcscSearch.ts` |
| `GET /engine-equipment/models` | `routers/engine_equipment.py:161` | Engine/master equipment catalog list | not observed in SaaS pages (reference/admin surface) |
| `GET /equipment-assets/model/search` | `routers/equipment_assets.py` | SaaS equipment-model lookup (called from add-modal via raw fetch) | `vue3/public/assets/js/tai-rebuild/pages/my-equipment/MyEqAddModal.js` |
| `GET /ksic-engine/search` | `routers/ksic_engine.py:151` | KSIC industry code lookup | (reference surface — not traced to a specific vue3 caller in this pass) |
| `GET /search` (admin) | tai-api admin router | Company / user / factory / payment cross-search | admin panels only |

Classifier:

| Endpoint | Classification |
|---|---|
| `/help/search` | KNOWLEDGE DISCOVERY CANDIDATE — help articles could be indexed by shared engine downstream (SEARCH-04+); do NOT migrate under SEARCH-01 |
| `/factory-process/search` | OPERATIONAL SEARCH — factory-scoped lookup, KEEP SEPARATE |
| `/factory-process/kcsc/search` | REFERENCE DATA SEARCH — code lookup, KEEP SEPARATE |
| `/engine-equipment/models` | ENGINE / MASTER CATALOG API — KEEP SEPARATE |
| `/equipment-assets/model/search` | SAAS EQUIPMENT MODEL LOOKUP — KEEP SEPARATE (distinct caller from engine catalog) |
| `/ksic-engine/search` | REFERENCE DATA SEARCH — industry code lookup, KEEP SEPARATE |
| `/search` (admin) | ADMIN OPERATIONAL — KEEP SEPARATE |

`/engine-equipment/models` and `/equipment-assets/model/search` are
NOT the same consumer even though both are equipment-scoped — one is
an engine/master catalog list, the other is a SaaS `MyEqAddModal`
raw-fetch lookup used during asset registration. Any future
consolidation must be a deliberate WO, not an accidental merge.

None of these seven are migration targets for the Shared Search
Engine initiative; they operate on entity/reference data, not
knowledge/discovery.

---

## 10. Paid Diagnosis consumer (traced on tai-www main)

Evidence: `git show origin/main:src/pages/paid-diagnosis-result.astro`
+ `paid-diagnosis-detail.astro` (tai-www).

Grep for related-knowledge sections
(`guide|material|csi|risk|chem|accident|related|knowledge`) on both
Astro pages returns only:

- a `rules_table / risk gauge / duty.what fallback = 0` comment on
  `paid-diagnosis-result.astro`
- a `risk_grade / grade` display key on `paid-diagnosis-detail.astro`

No related-knowledge panels (no GUIDE / MATERIAL / CSI / RISK / CHEM
sections) are wired.

Verdict: **NOT_CONNECTED**. Matches Master Plan v2 `GAP-06 Paid
Knowledge 연결 없음` (open).

---

## 11. SaaS consumer matrix — traced on tai-admin main

Evidence: `git show origin/main:<file>` in `taiengineering/tai-admin`
at `5f2d2cb0`. All 6 required page kinds (Process / Task / Equipment /
Chemical / Obligation / Inspection) traced through the composable →
API path → tai-api router chain.

### Direct-usage census in tai-admin `vue3/**`

```text
/search-dict     direct use = 0 files  (grep returns nothing)
/knowledge-graph direct use = 0 files
/help/search     direct use = 1 file   (vue3/src/pages/help/useHelp.ts)
```

**No SaaS page consumes the Shared Search Dictionary or the
Knowledge Graph today.** Only the help center consumes its own
Kiwi-backed `/help/search`.

### Page-kind trace

| Page kind | tai-admin page(s) | API endpoints called | Data source | Verdict |
|---|---|---|---|---|
| **PROCESS** | `vue3/src/pages/process-select/index.vue` + `useProcessSelectList.ts` + `useKcscSearch.ts` | `/factories`, `/factories/:id`, `/factory-process/search`, `/factory-process/:id/processes` (GET/POST/PATCH/DELETE), `/factory-process/kcsc/search` | tai-api factory_process_v3 router (Supabase-direct + KCSC master ILIKE) | **DIRECT_DOMAIN_QUERY** |
| **TASK (work-schedule)** | `vue3/src/pages/work-schedule-list/**`, `vue3/src/pages/my-inspection/**` (schedules tab) | `/work-schedules`, `/inspection/schedules/:factory_id` | tai-api work_schedules / inspection routers | **DIRECT_DOMAIN_QUERY** |
| **EQUIPMENT** | `vue3/src/pages/my-equipment/**` + `vue3/public/assets/js/tai-rebuild/pages/my-equipment/MyEqAddModal.js` | `/equipment-assets`, `/equipment-assets/model/search`, `/factories` | tai-api equipment_assets router (own catalog + Supabase table) | **DIRECT_DOMAIN_QUERY** |
| **CHEMICAL** | *(no vue3 page)* | *(no page)* | — | **NOT_CONNECTED** — tai-admin `main` has no chemical/MSDS SaaS page (`git ls-tree ... vue3/src/pages | grep -iE "chem|msds"` returns nothing). CHEM-07 public router in tai-api is dormant. |
| **OBLIGATION** | closest analog: `vue3/src/pages/compliance-report/index.vue` + inspection-anchor pages | `/factories`, `/inspection-sets?source=LEGAL_ENGINE`, `/construction-inspection-anchor`, `/inspection-anchor` (routes) | tai-api legal engine + inspection engine (deterministic rules) | **DIRECT_DOMAIN_QUERY** (via Legal Engine, not Shared Search) |
| **INSPECTION** | `vue3/src/pages/my-inspection/**`, `vue3/src/pages/inspection-detail/[inspectionId].vue`, `vue3/src/pages/inspection-workbench/[inspectionId].vue` | `/inspection/status/:factory_id`, `/inspection-sets`, `/inspection-set-items`, `/inspection/schedules/:factory_id`, `/inspection/start/:id`, `/inspection/complete/:id`, `/inspection/result/:id/items` | tai-api inspection engine | **DIRECT_DOMAIN_QUERY** |

### RISK UI trace (per PATCH-2 §I)

RISK has a full SaaS UI in tai-admin main:

- `vue3/src/pages/risk-assessment-list/**` (useRiskAssessmentList.ts)
- `vue3/src/pages/risk-assessment-detail/**` (useRiskAssessmentDetail.ts)
- `vue3/src/pages/risk-assessment-report/**`
- `vue3/src/pages/risk-assessment-scale/**`

API endpoints consumed:

```text
/risk-assessments                                (GET, POST)
/risk-assessments/:id                            (GET)
/risk-assessments/continuous-status              (GET)
/risk-assessments/:id/complete                   (POST)
/ra/scales?include_presets=true                  (GET)
/ra/assessments/:id/items                        (GET, POST)
/ra/assessments/:id/readiness                    (GET)
/ra/items/:id/controls                           (POST)
/ra/controls/:id                                 (PATCH)
/ra/items/:id/reevaluate                         (POST)
/ra/items/:id/revisions                          (GET)
```

Verdict: **DIRECT_DOMAIN_QUERY** against a dedicated
`/risk-assessments` + `/ra/*` API — this is **NOT** the `risk_canonical_nodes`
store (1,110 DRAFT / 0 ACTIVE / 0 sector links).

Key distinction (per PATCH-2 §I):

```text
RISK UI (risk-assessment-list/detail/report/scale)
    consumes /risk-assessments + /ra/*    → live SaaS domain

RISK canonical (risk_canonical_nodes)
    1,110 DRAFT / 0 ACTIVE / 0 sector    → not consumer-ready
```

"RISK UI exists" ≠ "RISK canonical is consumer-ready". The two must
be tracked separately in the Consumer track; the canonical store's
consumerization (RISK-C0*) is still open.

### Aggregate SaaS verdict

- **0 SaaS pages** consume `/search-dict` or `/knowledge-graph`.
- **1 SaaS page** (help center) consumes its own `/help/search`.
- **5 traced page kinds** are `DIRECT_DOMAIN_QUERY` against dedicated
  domain APIs. Chemical is `NOT_CONNECTED` (no page).
- Matches `GAP-05 SaaS Context Search 없음` in Master Plan v2 —
  every SaaS page today runs domain-specific direct queries; none go
  through a shared discovery layer.

---

## 12. Unified Search Index census

Grep across `services/` + `routers/` + `supabase/migrations/` in
`tai-api`:

```text
search_document            not found
search_index               not found
search_projection          not found
tsvector                   not found
GIN index                  not found
pg_trgm                    referenced ONLY as optional T6 tier
                           (services/search_query_svc.py:41)
materialized view          only knowledge_graph_relations
                           (supabase/migrations/20260913_knowledge_graph_relations.sql)
```

Verdict: **NO UNIFIED INDEX EXISTS.** This is exactly `GAP-02
Unified Search Index 없음` in Master Plan v2 §2, still open.

---

## 13. Revised Connection Matrix (PATCH-2 traced)

```text
Component                     Code    Prod    ShrDct   UnfIdx   Graph   Pub    SaaS    Paid   Evidence
─────────────────────────────────────────────────────────────────────────────────────────────────────
Search Dictionary (T1..T3)    yes     UNVER   —        —        —      —      —       —      §3
T4 Kiwi                       yes     UNVER   —        —        —      —      —       —      §2
T6 Trigram                    yes     UNVER   —        —        —      —      —       —      §2
Runtime projection artifact   build   UNVER   —        —        —      —      —       —      §3
tai-www /safety-search        yes     live    NO       NO       partial fed'd  n/a     n/a    §4
tai-api /public/…/kosha       yes     live    NO       NO       —      via UI —       —      §4
LEG candidate adapter         yes     live    NO       NO       —      n/a    n/a     n/a    §6
Knowledge Graph               yes     4/5     NO       NO       CODE=5 —      NO      —      §7
CHEM search adapter           yes     live    YES     NO       NO     via UI NO      NO     §11 (no SaaS page)
RISK canonical                yes     1110D   NO       NO       NO     NO     NO      NO     §8, §11
RISK UI (/risk-assessments)   yes     live    NO       NO       NO     n/a    DIRECT  NO     §11
LEGAL applicability           yes     live    partial  NO       NO     n/a    via /inspection-sets NO §11
Help /help/search             yes     live    NO       NO       NO     via UI DIRECT  n/a    §9, §11
Process (factory-process)     yes     live    NO       NO       NO     —      DIRECT  —      §11
Task (work-schedules)         yes     live    NO       NO       NO     —      DIRECT  —      §11
Equipment (equipment-assets)  yes     live    NO       NO       NO     —      DIRECT  —      §11
Chemical                      n/a     n/a     n/a      n/a      n/a    n/a    NONE    n/a    §11 (no page)
Obligation (compliance)       yes     live    NO       NO       NO     —      DIRECT  n/a    §11
Inspection                    yes     live    NO       NO       NO     —      DIRECT  —      §11
Paid Diagnosis pages          yes     live    NO       NO       NO     —      —       DIRECT §10 (no related-knowledge panels)
Admin /search                 yes     live    NO       NO       NO     —      —       —      §5
```

Columns: `Code` (present in repo) / `Prod` (verified live or
UNVERIFIED) / `ShrDct` (uses shared dictionary) / `UnfIdx` (uses a
unified index — NO everywhere) / `Graph` (uses knowledge graph
relations) / `Pub` (public consumer wiring) / `SaaS` (SaaS
consumer wiring — `DIRECT` = domain-specific direct query) / `Paid`
(paid diagnosis wiring).

**Aggregate finding**: not a single SaaS consumer today reads
through `/search-dict` or `/knowledge-graph`. Every SaaS page kind
resolves through a dedicated domain API. This is exactly the state
Master Plan v2 §2 describes as `GAP-02 / GAP-04 / GAP-05 / GAP-06`,
all still open.

---

## 14. Duplicate Matrix — segmented

Segment A — **must remain separate** (different concerns):

| Implementation | Reason |
|---|---|
| Admin `/search` (company/user/factory/payment) | Operational entity search, not knowledge discovery |
| `/factory-process/search`, `/factory-process/kcsc/search` | Factory-scoped operational lookup |
| `/engine-equipment/models` | Equipment reference catalog |
| `/ksic-engine/search` | Industry code lookup |
| Address / geocoding search (if present) | Reference data |
| KOSHA external provider | Third-party discovery contract |

Segment B — **Shared Search Engine consumer candidates** (target
state per Master Plan v2):

| Implementation | Target consumer |
|---|---|
| tai-www /safety-search federated composition | Should consume Shared Search Engine (SEARCH-06) |
| CHEM search adapter | Should consume Shared Search Engine (SEARCH-04 CHEM indexer) while retaining CHEM-specific identifier logic |
| RISK future consumer views | Should consume Shared Search Engine (SEARCH-04 RISK indexer) once RISK-C0* opens ACTIVE gates |
| SaaS context panels (process / task / equipment / obligation / inspection / chemical) | Should consume Shared Search Engine via context queries (SEARCH-05 / consumer track) |
| Paid diagnosis related-knowledge sections | Should consume Shared Search Engine (consumer track) |

Segment C — **domain-specific logic that must be retained**:

| Piece | Reason |
|---|---|
| CHEM identifier-exact logic (chemId / CAS / KE / EN / UN) | Identifiers must not go through Kiwi / fuzzy |
| LEGAL applicability engine (deterministic rules) | Rule engine ≠ discovery layer |
| RISK canonical logic (DRAFT→ACTIVE promotion, sector linkage) | Semantic curation, not search |
| Search dictionary curation (seed_v2 build) | Determinism guardrail |

**Migration to shared consumption ≠ removal of domain logic.** These
are orthogonal.

---

## 15. Master Plan v2 alignment (S00 does NOT redecide the roadmap)

The following statements from the prior audit are **removed**:

- ~~"No unified index is intentional architecture"~~
- ~~"Do not unify searches"~~
- ~~"Risk isolation should be preserved"~~
- ~~"LEG disconnected is correct by design"~~
- ~~"Shared-Search Infrastructure is INTENTIONALLY MODULAR"~~

Corrected framing:

```text
CURRENT STATE
  · No unified index exists.
  · Search dictionary + Kiwi + trigram tiers exist as
    query-understanding infrastructure but are not consumed
    across all knowledge domains.
  · Public /safety-search federates 6 direct source adapters
    + 1 external KOSHA provider (tai-www composition layer).
  · LEG candidate adapter is not fed by search dictionary.
  · RISK canonical is fully DRAFT with 0 sector linkage.
  · Graph covers 4/5 controlled contexts in production.

TARGET (Master Plan v2)
  · Domain SoT + specialized deterministic logic → remain
    separate and canonical.
  · Consumer discovery layer → SHARED across Public / Paid /
    SaaS / LEG enrichment via a unified projection + engine.
  · Federation at tai-www today should migrate to consumption
    of the Shared Search Engine under SEARCH-06.
```

---

## 16. GAP status (restored — do NOT close in SEARCH-00)

All seven Master Plan v2 GAPs remain **OPEN**. SEARCH-00 narrows
scope; it does not close gaps.

| GAP | Status after SEARCH-00 |
|---|---|
| GAP-01 Runtime Production Binding | OPEN — SEARCH-01 target (projection artifact + env + T4/T6 degradation) |
| GAP-02 Unified Search Index 없음 | OPEN — SEARCH-02..05 target |
| GAP-03 LEG actual wiring 없음 | OPEN — SEARCH-07 target |
| GAP-04 RISK Consumerization 없음 | OPEN — RISK-C0* track |
| GAP-05 SaaS Context Search 없음 | OPEN — Consumer rollout track |
| GAP-06 Paid Knowledge 연결 없음 | OPEN — Consumer rollout track |
| GAP-07 Graph coverage 확장 미완료 | OPEN — separate WO after SEARCH-05 |

---

## 17. SEARCH-01 confirmed scope (narrow)

SEARCH-01 focuses on `GAP-01 Runtime Production Binding` only.

1. Diagnose the production `/search-dict/*` HTTP 503 root cause.
2. Verify or fix the deployment package's inclusion of
   `TAI_SEARCH_RUNTIME_PROJECTION_v1.json` (either check-in or a
   deterministic pre-start build step).
3. Verify or set `TAI_SEARCH_PROJECTION` env binding in prod.
4. Confirm projection SHA / snapshot id / subject count / expansion
   count against `SEARCH-DICT-LEGPROD-2026-09-16`.
5. Verify T4 (Kiwi) graceful degradation reporting via `/health`.
6. Verify T6 (Trigram) graceful degradation reporting via `/health`.
7. Produce an artifact-dependency manifest for DevOps handoff (which
   files must ship + which env vars must exist).

### Out-of-scope for SEARCH-01

- Unified index design / build (SEARCH-02 / SEARCH-03)
- Domain indexers (SEARCH-04)
- Retrieval engine (SEARCH-05)
- Public migration (SEARCH-06)
- LEG candidate wiring (SEARCH-07)
- Any RISK ACTIVE change / graph apply / CHEM hydration resume
- Merging CHEM adapter into shared search (SEARCH-04 concern)
- Rewriting help center (potential SEARCH-04 concern, not now)

---

## 18. Unknowns (require follow-up)

| Item | Resolves by |
|---|---|
| Prod deployment artifact layout (`TAI_SEARCH_PROJECTION` path) | SEARCH-01 DevOps handoff |
| T6 Trigram runtime state in prod | SEARCH-01 `/health` inspection once 503 clears |
| tai-www SaaS consumer call graph for each page kind | Follow-up consumer trace WO |
| Paid diagnosis related-knowledge fetch paths | Follow-up consumer trace WO |
| Whether `sector:construction` graph rule will match anything post-migration | Data audit under Consumer rollout track |

---

## 19. Hard fence honored

```text
CODE CHANGE           = 0
DB WRITE              = 0
MIGRATION             = 0
DEPLOY                = 0
ENV CHANGE            = 0
SEARCH INDEX CREATE   = 0
GRAPH APPLY           = 0
RISK ACTIVE CHANGE    = 0
CHEM HYDRATION        = 0
```

---

## Appendix A. File inventory (verified paths)

Search dictionary + query understanding:

- `services/search_query_svc.py`
- `services/search_dictionary_svc.py`
- `routers/search_dictionary.py`
- `tools/search_dict/search_core.py`
- `tools/search_dict/search_runtime_ext.py`
- `tools/search_dict/normalize.py`
- `tools/search_dict/build_dictionary.py`
- `tools/search_dict/seed_v2.py`
- `tools/search_dict/extract/GROUND_TRUTH_464.tsv`
- `tools/search_dict/extract/LAW_ALIAS_15.tsv`
- `tools/search_dict/artifacts/BUILD_SHA256SUMS.txt` (in repo)
- `tools/search_dict/artifacts/TAI_SEARCH_RUNTIME_PROJECTION_v1.json` (**not in repo**)

Public safety search (tai-www product surface):

- `tai-www/src/lib/server/safetySearch.js`
- `tai-www/src/lib/server/koshaGuides.js`
- `tai-www/src/lib/server/csiAccidents.js`
- `tai-www/src/lib/modules/safety.js`

Public safety search (tai-api provider):

- `routers/public_safety_search.py` (KOSHA provider adapter)

LEG candidate / on-demand:

- `services/leg_candidate_adapter.py`
- `services/leg_ondemand_enrichment.py`

Knowledge graph:

- `services/knowledge_graph_rules.py`
- `services/knowledge_graph_svc.py`
- `services/knowledge_graph_producers.py`
- `services/knowledge_graph_store.py`
- `services/knowledge_graph_hydrate.py`
- `routers/public_knowledge_graph.py`

CHEM adapter:

- `services/kosha_msds/search_adapter.py`

Help center:

- `services/safe_help_kiwi.py`
- `routers/safe_help.py`

Admin / operational search:

- `routers/factory_process_v3.py`
- `routers/engine_equipment.py`
- `routers/ksic_engine.py`
- tai-api admin `/search` router (path TBD in cross-check)
