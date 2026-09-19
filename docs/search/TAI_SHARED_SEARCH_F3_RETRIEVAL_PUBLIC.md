# TAI Shared Search — F3 Retrieval Engine & Public API

**WO-TAI-SHARED-SEARCH-F3 | Goal G-mu82mpyp-0c0ce2**

---

## 0. Status

```
F3 IMPLEMENTATION COMPLETE
G1 EXECUTABLE SEAL = PASS
READY FOR GPT F3-G1 OWNER GO VERIFY
```

| F-stage | Status |
|---------|--------|
| F1 Foundation | CLOSED / MERGED (main) — production apply NOT required for G1 |
| F2 Domain Indexing | CLOSED / MERGED (b4ee0ce3) |
| F3 Retrieval + Public | **PR #409 — OPEN / CI SUCCESS / behind main = 0** |
| F4 LEG + SaaS + Paid | WAITING |

**PR #409 HEAD:** `e5a5863d94a7dd1966f997b0cd25b3aeec9faa0c`

---

## 1. Architecture

```
              TAI Search Dictionary (deterministic)
            services/search_query_svc.lookup_deterministic()
                            │
                            ▼
                     SearchQueryPlan
              services/shared_search/query.py
              (10-tier active_tiers,
               subject_candidates,
               identifier_candidates)
                            │
                            ▼
              OpenSearchSearchReader
          services/shared_search/opensearch_reader.py
                    (_msearch — parallel tiers)
                            │
                            ▼
                OpenSearch 2.17 + analysis-nori
              alias: tai-shared-search-current
                            │
                            ▼
              SharedRetrievalEngine
          services/shared_search/retrieval.py
              (tier dedup, rank, paginate)
                            │
                            ▼
            SearchResult / SearchResponse
           services/shared_search/result.py
                            │
                    ┌───────┴────────┐
                    │                │
                 Public         F4 SaaS/Paid
             /public/          (same engine,
            safety-search       different
                              visibility_scopes)
```

**Runtime invariants:**
- Shared Search Kiwi runtime = 0
  (TAI Search Dictionary uses `lookup_deterministic()` — Kiwi/TOKEN/TRIGRAM excluded)
- No per-Domain retrieval engine
- No per-Domain ranking
- No PostgreSQL FTS in retrieval path
- No pg_trgm in retrieval path
- Legal applicability authority not invaded
- CHEM public mode follows `KOSHA_MSDS_PUBLIC_MODE` env var

---

## 2. Query Understanding

**Module:** `services/shared_search/query.py`

**Inputs:** `q`, `visibility_scopes`, `object_types`, `page`, `page_size`

**Outputs (SearchQueryPlan):**
- `normalized_query` — stripped, whitespace-normalized query
- `identifier_candidates` — candidate source_key / canonical_id values
- `subject_candidates` — Search Dictionary hits (SubjectCandidate)
- `active_tiers` — ordered list of tiers to execute (T0–T9)
- `dictionary_ok` / `dictionary_error` — graceful degradation when projection absent

**Identifier gate:** single-token queries (no whitespace) are tested as potential
`source_key` / `canonical_id` values before BM25/fuzzy runs.

**Dictionary integration:** calls `lookup_deterministic()` from
`services.search_query_svc`. This path excludes Kiwi TOKEN and TRIGRAM tiers.
Read-only; no dictionary writes.

**Search Dictionary role:**
```
TAI Search Dictionary = semantic expansion authority (T2/T3 tiers)
Nori               = Korean morphological tokenizer (T8 BM25_NORI tier)
OpenSearch         = retrieval execution + BM25 ranking
TAI Retrieval      = tier/filter/dedup authority
```

---

## 3. Retrieval Tier Precedence

Fixed 10-tier order. Higher tier always outranks lower tier for the same document
(dedup: highest tier wins).

| T# | Tier name | Description |
|----|-----------|-------------|
| T0 | `SOURCE_KEY_EXACT` | `source_key` keyword exact match |
| T1 | `CANONICAL_ID_EXACT` | `canonical_id` keyword exact match |
| T2 | `DICTIONARY_EXACT` | Search Dictionary exact subject match |
| T3 | `DICTIONARY_EXPANSION` | Search Dictionary synonym/expansion match |
| T4 | `TITLE_EXACT` | `title` keyword exact match |
| T5 | `ALIAS_EXACT` | `aliases` keyword exact match |
| T6 | `SUBJECT_EXACT` | `subjects.subject_key` exact match |
| T7 | `CONTEXT_EXACT` | `context.context_key` exact match |
| T8 | `BM25_NORI` | OpenSearch BM25 with Nori Korean analysis |
| T9 | `FUZZY_FALLBACK` | Fuzzy match (only when T0–T8 produce no results) |

T0–T7 execute as a single `_msearch` request. T8 runs in the same `_msearch` call.
T9 (fuzzy) runs only as a fallback when page is empty after T0–T8.

**Within-tier ranking:**
```
tier_precedence ASC
→ OpenSearch _score DESC
→ source_updated_at DESC
→ object_type ASC
→ canonical_id ASC
```

**Field boosts (BM25):**
```
title ^5  aliases ^4  search_text ^2  summary ^1
```

---

## 4. Result Deduplication

Identity: `(object_type, canonical_id)`

One document appearing in multiple tiers → highest-priority tier wins.
Lower-tier evidence is discarded (not merged).

---

## 5. Pagination

OpenSearch overfetch + slice. Stable because ordering is fully deterministic.

```
page: 1..N (1-indexed)
page_size: 1..50
overfetch = (page × page_size) + page_size  ← to cover dedup loss
```

`SearchResponse.total` is the count of deduplicated results across ALL tiers
(before pagination slice), consistent across pages.

---

## 6. Visibility Filtering

Every OpenSearch query applies mandatory filters:
```
publication_status = PUBLISHED
AND visibility_scopes contains <scope>
```

| Consumer | Scope |
|----------|-------|
| Public (F3) | `PUBLIC` |
| SaaS (F4) | `SAAS` |
| Paid (F4) | `PAID` |

HOLD / REMOVED documents are excluded from the serving index at rebuild time.
The engine does NOT re-judge Domain publication status; the rebuild is authoritative.

**CHEM special:** indexed with `visibility_scopes=['PUBLIC']` only when
`KOSHA_MSDS_PUBLIC_MODE` ∈ `{seo_preview, full}` at rebuild time.

---

## 7. Result Contract

**`SearchResult`** (one hit):

| Field | Type | Notes |
|-------|------|-------|
| `object_type` | str | e.g. `GUIDE`, `CSI_ACCIDENT`, `LEGAL` |
| `canonical_id` | str | Domain UUID |
| `title` | str | Display title |
| `source_id` | str | e.g. `KOSHA_GUIDE`, `CSI`, `LAW` |
| `source_key` | str? | Domain-native key |
| `source_updated_at` | str? | ISO-8601 |
| `summary` | str? | Short description |
| `public_url` | str? | tai-www public URL |
| `saas_url` | str? | SaaS URL (F4) |
| `match_type` | str | Winning tier name (e.g. `BM25_NORI`, `SOURCE_KEY_EXACT`) |
| `matched_on` | str? | Actual term matched |
| `rank_tier` | int | Tier precedence index (0=highest) |
| `subject_type` | str? | From dictionary candidate |
| `subject_key` | str? | From dictionary candidate |
| `subject_match_type` | str? | e.g. `SYNONYM_OF` |
| `matched_term` | str? | Dictionary matched term |

**`SearchResponse`** (paginated):

| Field | Type | Notes |
|-------|------|-------|
| `query` | str | Original query |
| `page` | int | |
| `page_size` | int | |
| `total` | int | Total deduplicated hits (all pages) |
| `items` | list[SearchResult] | Current page |
| `active_tiers` | list[str] | Tiers that produced ≥1 hit |
| `dictionary_snapshot` | str? | Dictionary version |
| `status` | str | `ok` / `empty` / `error` |

No internal scoring, OpenSearch raw fields, or debug data exposed in public responses.

---

## 8. OpenSearch Index Architecture

**Cluster:** OpenSearch 2.17.0 + `analysis-nori` plugin

**Alias (serving):**
```
tai-shared-search-current → tai-shared-search-v1-{run_id}
```

**Physical index naming:**
```
tai-shared-search-v1-{first_16_chars_of_run_id_lowercase}
```

**Analyzers (custom):**
```
tai_nori_index   — index-time: nori_tokenizer (mixed decompound) + POS filter + lowercase + asciifolding
tai_nori_search  — search-time: same tokenizer without decompound filter
```

**Field types:**
- `object_type`, `canonical_id`, `source_id`, `source_key`: `keyword` (exact, not analyzed)
- `title`, `search_text`, `summary`: `text` with `tai_nori_index` / `tai_nori_search`
- `aliases`: `text` multi-field + `keyword`
- `subjects`, `context`: `nested` (keyword sub-fields)
- `publication_status`, `visibility_scopes`: `keyword`
- `source_updated_at`, `indexed_at`: `date`

**Nori evidence:**
```
OpenSearch version  = 2.17.0
analysis-nori       = PASS
tai_nori_index      = PASS
tai_nori_search     = PASS
mapping SHA256      = f65e1870ff0f4911a2e9c20a4b04ee5ef69b33d6e8a9d1a0abff1c5a08cf12ab
evidence artifact   = docs/search/evidence/f3_opensearch_nori_analyze_20260919.json
```

**Nori user dictionary:**
```
DEFERRED — SEARCH QUALITY TUNING
```
TAI deterministic dictionary remains semantic authority (T2/T3).
Nori user_dictionary will be revisited after G1 production query evidence.

---

## 9. Rebuild Safety (F3-G1)

### 9.1 Canonical preparation authority

`prepare_search_document()` in `services/shared_search/writer.py` is the
single authority for canonical document preparation:
```
raw adapter payload
  → normalize_document()
  → content_hash()
  → canonical wire dict
```
Both the Memory/Supabase Writer and the OpenSearch bulk rebuild use this helper.
No duplicate normalization logic exists.

### 9.2 Hard-fail rules

| Condition | Result |
|-----------|--------|
| `failed_bulk_items > 0` | `RUN_STATUS_FAILED` — alias unchanged |
| `actual_count != expected_count` | `RUN_STATUS_FAILED` — alias unchanged |
| `expected_count == 0` | `RUN_STATUS_FAILED` — alias unchanged |
| Per-domain count mismatch | `RUN_STATUS_FAILED` — alias unchanged |
| Duplicate `(object_type, canonical_id)` | `RUN_STATUS_FAILED` — alias unchanged |
| `promote()` with status != `VALIDATED` | `RebuildRejected` — alias unchanged |
| `promote()` with pre-flight count mismatch | `RebuildRejected` — alias unchanged |

### 9.3 Duplicate detection authority

OpenSearch `_id` is **not aggregatable** — `_id` cardinality aggregation is NOT used.

Duplicate detection is TAI-side only:
```python
global_seen: set[tuple[str, str]]  # (object_type, canonical_id)
```
Checked in `opensearch_rebuild.py` for every PUBLISHED document,
BEFORE any OpenSearch write. First occurrence wins; duplicate raises `RebuildRejected`.

### 9.4 Rebuild flow

```
1.  Supabase client      build_production_adapters(supabase_client)
2.  begin_run            OpenSearchSearchStore.begin_run(domains)
3.  candidate index      create_candidate_index(run_id)
4.  per adapter:
      adapter.iter_documents()
        → prepare_search_document()     ← normalize + hash
        → PUBLISHED only
        → global_seen duplicate guard   ← before write
        → stage_documents() bulk
5.  validate_run         expected == actual, per-domain parity, failed_bulk == 0
6.  promote()            VALIDATED guard + pre-flight count check
7.  atomic alias swap    tai-shared-search-current → new physical index
```

### 9.5 Rollback

Alias reverted to previous physical index. Rollback metadata:
```
rollback_at       = ISO timestamp
rollback_target   = previous physical index name
```

---

## 10. Database Migration

### PostgreSQL retrieval migration — REMOVED

```
20260919_shared_search_retrieval.sql
= REMOVED from PR #409
= SUPERSEDED by OpenSearch
```

This migration (PostgreSQL FTS indexes, pg_trgm indexes, GIN retrieval indexes)
was authored for the original PostgreSQL retrieval design. It was removed when the
backend was switched to OpenSearch. It is not an active artifact.

### F1 Foundation migration — retained, NOT required for G1

```
20260919_shared_search_foundation.sql
= repo artifact retained
= production apply = NO (not required for OpenSearch path)
= G1 requirement = NO
```

The F1 Foundation migration (search_documents, search_rebuild_runs tables) was
designed for a Supabase-backed store. The OpenSearch rebuild path does not depend
on these tables. Do not apply without explicit Owner instruction.

---

## 11. Public API

**Router:** `routers/public_safety_search.py`

### GET /public/safety-search

Backed by `OpenSearchSearchReader`. Requires `TAI_OPENSEARCH_URL` to be
configured; raises `503 SHARED_SEARCH_UNAVAILABLE` if missing (fail-closed).

**Query parameters:**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `q` | str | required | min 1 char; 422 on blank |
| `type` | str? | all | `guide`, `material`, `accident`, `chem`, `knowledge`, `precedent`, `law`/`legal` |
| `page` | int | 1 | ≥1 |
| `page_size` | int | 10 | 1..50 |

**Visibility:** `PUBLIC` only. `CHEM` excluded unless `KOSHA_MSDS_PUBLIC_MODE` active.
**Missing OpenSearch config:** `503 SHARED_SEARCH_UNAVAILABLE` (no silent fallback).

### GET /public/safety-search/kosha (unchanged)

External KOSHA Smart Search — retained as-is. Not merged into Shared Search index.

---

## 12. Public Parity Audit

### 12.1 tai-www current state

As of F3 verification, tai-www (`main`) already has the following files:

```
src/lib/server/safetySearch.js
src/pages/safety-search.astro
tests/wave2-safety-search.test.mjs
```

A `/safety-search` page already exists. The current implementation uses
legacy/federated providers.

**F3-G2 objective:** replace eligible internal provider paths with
`GET /public/safety-search` while retaining non-parity legacy providers
(LAW, KOSHA external).

### 12.2 Shared Search adapter coverage (F2)

| object_type | F2 adapter | Source view / table |
|---|---|---|
| `GUIDE` | `GuideAdapter` | `kosha_guide_current_snapshot` |
| `SAFETY_MATERIAL` | `SafetyMaterialAdapter` | `kosha_safety_materials` |
| `CSI_ACCIDENT` | `CsiAccidentAdapter` | `csi_accident_catalog` |
| `CHEM` | `ChemAdapter` | `kosha_msds_catalog` |
| `KNOWLEDGE` | `KnowledgeAdapter` | `safe_help_content` |
| `PRECEDENT` | `PrecedentAdapter` | precedent source |
| `LEGAL` | `LegalAdapter` | `law_article` |
| `RISK` | `RiskAdapter` | risk source |

### 12.3 Parity matrix

| WO group | Shared Search type | Semantic parity | Cutover ready |
|---|---|---|---|
| `guide` | `GUIDE` | HIGH — same KOSHA source | YES |
| `material` | `SAFETY_MATERIAL` | HIGH — same KOSHA catalog | YES |
| `accident` | `CSI_ACCIDENT` | HIGH — same CSI catalog | YES (after G1 rebuild) |
| `precedent` | `PRECEDENT` | HIGH — same source | YES |
| `knowledge` | `KNOWLEDGE` | MEDIUM — needs verify (article vs. chunk identity) | NEEDS VERIFY |
| `law` | `LEGAL` (`law_article`) | LOW — revision ≠ article grain | RETAIN LEGACY |
| `kosha` | external (unchanged) | N/A — external | RETAIN |
| `chem` | `CHEM` | N/A — new domain | DEFER to UX decision |

### 12.4 Cutover decisions

```
SHARED SEARCH cutover-ready:
  GUIDE
  SAFETY_MATERIAL
  CSI_ACCIDENT (after G1 rebuild validates counts)
  PRECEDENT

NEEDS VERIFY before cutover:
  KNOWLEDGE (article/chunk identity mapping)

LEGACY RETAINED:
  LAW (revision grain ≠ law_article)
  KOSHA (external provider, unchanged)

DEFERRED to UX decision (F4+):
  CHEM (API-ready; no public display URL confirmed)
```

### 12.5 tai-www G2 migration design

When `work/search-f3-public` PR lands:

```
src/lib/server/safetySearch.js   — updated: orchestrates SharedSearch + legacy providers
```

**Provider architecture:**
```
SafetySearchOrchestrator
  ├── SharedSearchProvider   → GET /public/safety-search (GUIDE, MATERIAL, CSI, PRECEDENT)
  ├── LegacyLawProvider      → law_revision_board (direct, retained)
  └── KoshaProvider          → GET /public/safety-search/kosha (unchanged)
```

**Rollback (G2):** switch to `LegacyProvider` only via env var. No DB rebuild.

---

## 13. Production Gate Plan

### GATE-1 (F3-G1): Search Infrastructure Activation

**Requires: Owner Approval after GPT independent verify + CI success**

```
1.  Provision OpenSearch infrastructure (cluster, auth, TLS)
2.  Verify OpenSearch version = 2.17.x
3.  Verify analysis-nori plugin installed
4.  Configure tai-api:
      TAI_OPENSEARCH_URL = <cluster URL>
      TAI_OPENSEARCH_USERNAME / PASSWORD (if auth required)
5.  Run opensearch_bootstrap.py
      — cluster health check
      — plugin verification
      — tai_nori_index / tai_nori_search _analyze tests on golden terms
6.  Run production READ-only dry-run census:
      python3 tools/shared_search/opensearch_rebuild.py --dry-run
      Confirm:
        CSI published = 37,157
        CHEM published = 1,997
        RISK = 0
        duplicate = 0
        unexplained drop = 0
7.  Create candidate physical index
      (create_candidate_index in opensearch_bootstrap.py or rebuild tool)
8.  Run FULL OpenSearch rebuild:
      python3 tools/shared_search/opensearch_rebuild.py --full
9.  Verify rebuild result:
      bulk_failure = 0
      expected total == physical total
      per-domain parity (all domains)
      HOLD exposure in serving index = 0
      RISK document count = 0
10. Atomic alias promotion:
      tai-shared-search-current → candidate index
11. Retrieval smoke tests via /public/safety-search
12. Deploy tai-api
13. Production API smoke:
      GET /public/safety-search?q=안전보건관리책임자
      → 200 with results from OpenSearch
```

**F1 Foundation migration:** NOT part of G1 procedure. Do not apply without
separate Owner instruction. The OpenSearch rebuild path does not depend on it.

**No PostgreSQL retrieval migration:** `20260919_shared_search_retrieval.sql`
was removed from this PR. It is not applied and not needed.

#### Nori User Dictionary — Intentionally Deferred

TAI Search Dictionary remains the semantic authority for deterministic
term expansion and subject matching (T2/T3 retrieval tiers).

Nori `user_dictionary` integration is **intentionally deferred until
production query-quality evidence demonstrates a need**. The current
`tai_nori_index` / `tai_nori_search` analyzers produce correct Korean
morphological analysis for all F3 golden terms
(evidence: `docs/search/evidence/f3_opensearch_nori_analyze_20260919.json`).

This is NOT a gap — it is a deliberate quality-gating decision.

### GATE-2 (F3-G2): Public Cutover

**Requires: G1 complete + Owner Approval**

```
tai-www work/search-f3-public PR merge
→ production deploy
→ /safety-search consumer switch to SharedSearchProvider
→ KOSHA external provider unchanged
→ LAW legacy provider unchanged
```

**Rollback:** switch `safetySearch.js` to legacy providers only. No DB rebuild.

---

## 14. F4 Handoff

F4 reuses `SharedRetrievalEngine` without modification:

```python
# F4 SaaS call
engine.search(q, visibility_scopes=["SAAS"], page=1, page_size=10)

# F4 Paid call
engine.search(q, visibility_scopes=["PAID"], page=1, page_size=10)
```

No new engine. No copy. Pass different `visibility_scopes`.
Legal applicability authority remains in Legal Engine — Search is discovery only.

---

## 15. Retrieval Readiness Evidence

Production census READ-ONLY evidence (F2 FINAL2 run):

```json
{
  "CSI": {
    "eligible_source_count": 37157,
    "yielded_count": 37157,
    "title_fallback_to_summary": 2789,
    "unexplained_drop": 0
  },
  "CHEM": {
    "eligible_source_count": 1997,
    "a02_product_name_count": 1997,
    "yielded_count": 1997,
    "unexplained_drop": 0
  }
}
```

See: `docs/search/evidence/f2_census_20260919.json`

---

## 16. Files Changed (F3 PR #409)

| File | Change |
|------|--------|
| `services/shared_search/query.py` | NEW — query understanding, 10-tier plan |
| `services/shared_search/result.py` | NEW — result contract (BM25_NORI, FUZZY_FALLBACK) |
| `services/shared_search/retrieval.py` | NEW — shared retrieval engine |
| `services/shared_search/opensearch_client.py` | NEW — OpenSearch client singleton |
| `services/shared_search/opensearch_mapping.py` | NEW — single authority for index settings + mapping |
| `services/shared_search/opensearch_reader.py` | NEW — OpenSearch-backed SearchReader (_msearch) |
| `services/shared_search/opensearch_store.py` | NEW — rebuild lifecycle manager |
| `services/shared_search/writer.py` | MODIFIED — prepare_search_document() public helper extracted |
| `services/shared_search/__init__.py` | MODIFIED — F3 exports added |
| `routers/public_safety_search.py` | MODIFIED — OpenSearch reader, 503 fail-closed |
| `tools/shared_search/opensearch_bootstrap.py` | NEW — cluster health + Nori verification tool |
| `tools/shared_search/opensearch_rebuild.py` | NEW — full rebuild orchestration |
| `tools/shared_search/opensearch_verify.py` | NEW — read-only cluster state verification |
| `tests/test_shared_search_f3_retrieval.py` | NEW — 103 tests (92+ passed, 3 skipped, 0 failed) |
| `docs/search/evidence/f3_opensearch_nori_analyze_20260919.json` | NEW — Nori _analyze evidence |
| `docs/search/TAI_SHARED_SEARCH_F3_RETRIEVAL_PUBLIC.md` | NEW — this document |
| `requirements.txt` | MODIFIED — `opensearch-py>=2.4.0,<3` added |

**Removed (not in final PR):**
- `supabase/migrations/20260919_shared_search_retrieval.sql` — REMOVED (PostgreSQL FTS path superseded by OpenSearch)

**F2 files included in main (b4ee0ce3), not in this PR:**
- `services/shared_search/adapters/csi_accident.py` — title OR summary fallback
- `services/shared_search/adapters/chem.py` — A02 product_name binding
- `services/shared_search/census.py` — CountingFetcher + source_yield_audit
- `services/kosha_msds/section_fields.py` — extract_product_name helper
- `services/shared_search/production_bindings.py` — A02 enrichment

---

## 17. Test Evidence

```
F1 regression    = PASS (62 passed)
F2 regression    = PASS (62 passed)
F3 suite         = PASS (103 passed, 3 skipped, 0 failed)
Search Dictionary = PASS
Time Guard       = PASS
F3-related failures = 0
new failures by PR  = 0
```

F3 test classes include:
- `TestQueryBuilding` — SearchQueryPlan construction
- `TestResultContract` — SearchResult / SearchResponse fields
- `TestTierPrecedence` — 10-tier ordering
- `TestVisibilityFilter` — PUBLISHED + scope filtering
- `TestDeduplication` — identity dedup
- `TestFuzzyFallback` — T9 conditional fallback
- `TestOpenSearchMapping` — mapping SHA256, alias structure
- `TestOpenSearchStore` — bulk staging, alias promotion, rollback
- `TestOpenSearchClient` — 503 fail-closed when URL missing
- `TestPublicAPILayer` — /public/safety-search behavior
- `TestCSICompleteness` — 37,157 / 37,157
- `TestCHEMCompleteness` — 1,997 / 1,997
- `TestImportRegressions` — no SupabaseSearchReader, no PostgreSQL FTS
- `TestPagination` — overfetch + slice
- `TestDeterministicDictionary` — lookup_deterministic excludes Kiwi
- `TestParityFixtures` — CSI + GUIDE via MemorySearchReader
- `TestPrepareSDocumentHelper` — canonical prepare helper parity
- `TestOpenSearchStoreSafetyGuards` — negative safety (bulk fail, count mismatch, etc.)
- `TestOpenSearchStoreRebuildConstants` — status constants, check_duplicates absent
- `TestGlobalDuplicateGuard` — D1 same-domain, D2 cross-adapter, D3 alias unchanged

---

## 18. Safety Invariants

```
PRODUCTION OPENSEARCH CREATE     = 0  (awaiting G1)
PRODUCTION INDEX CREATE          = 0  (awaiting G1)
PRODUCTION SUPABASE MIGRATION    = 0
PostgreSQL FTS Shared Search     = 0
pg_trgm Shared Search            = 0
Shared Search Kiwi runtime       = 0
DEPLOY                           = 0  (awaiting G1)
PUBLIC CUTOVER                   = 0  (awaiting G2)
CHEM API CALL                    = 0
RISK CHANGE                      = 0
GRAPH APPLY                      = 0
LLM CALL                         = 0
LEGAL APPLICABILITY              = 0  (search is discovery only)
EMBEDDING / VECTOR               = 0
OpenSearch _id aggregation       = 0  (_id is not aggregatable)
```
