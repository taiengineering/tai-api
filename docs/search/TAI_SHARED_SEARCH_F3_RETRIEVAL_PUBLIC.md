# TAI Shared Search — F3 Retrieval Engine & Public API

**WO-TAI-SHARED-SEARCH-F3 | Goal G-mu82mpyp-0c0ce2**

---

## 0. Status

```
F3 IMPLEMENTATION COMPLETE
READY FOR GPT INDEPENDENT VERIFY
WAITING FOR F3-G1 OWNER APPROVAL
```

| F-stage | Status |
|---------|--------|
| F1 Foundation | CLOSED / MERGED (main) — production apply deferred to G1 |
| F2 Domain Indexing | CLOSED / MERGED (b4ee0ce3) |
| F3 Retrieval + Public | **CURRENT — this document** |
| F4 LEG + SaaS + Paid | WAITING |

---

## 1. Architecture

```
                     Shared Query Understanding
                   services/shared_search/query.py
                            │
             ┌──────────────┴──────────────┐
             │                             │
       Search Dictionary              Kiwi TOKEN
   services/search_query_svc.py   (runtime extension)
             │
             ▼
      SearchQueryPlan
     (8-tier active_tiers,
      subject_candidates,
      identifier_candidates)
             │
             ▼
    Domain Projection → Shared Retrieval Engine
                   services/shared_search/retrieval.py
                         │ SearchDocumentReader
                    ┌────┴────┐
                    │         │
           MemorySearchReader  SupabaseSearchReader
              (tests)          (production)
                         │
                         ▼
                 Common Result Contract
              services/shared_search/result.py
                 SearchResult / SearchResponse
                         │
                    ┌────┴────┐
                    │         │
                 Public     F4 SaaS/Paid
              /public/       (same engine,
             safety-search    different
                              visibility_scopes)
```

**Rules enforced:**
- No per-Domain retrieval engine
- No per-Domain ranking
- No new Kiwi instantiation
- No new Search Dictionary
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
- `active_tiers` — ordered list of tiers to execute
- `dictionary_ok` / `dictionary_error` — graceful degradation when projection absent

**Identifier gate (§19):** single-token queries (no whitespace) are tested as
potential `source_key` / `canonical_id` values before any FTS/trigram runs.

**Dictionary integration:** wraps `services.search_query_svc.lookup()` which
manages the Search Dictionary + Kiwi singleton. Query vocabulary (`EXACT`,
`SYNONYM_OF`, `TOKEN`, `TRIGRAM`, …) is read-only — not re-implemented here.

---

## 3. Retrieval Tier Precedence

Fixed tier order (WO §22). Higher tier always outranks lower tier for the same
document (dedup: highest tier wins).

| # | Tier name | Description |
|---|-----------|-------------|
| 1 | `IDENTIFIER_EXACT` | `source_key` exact match |
| 2 | `CANONICAL_EXACT` | `canonical_id` exact match |
| 3 | `SUBJECT` | `subjects @> [{subject_key}]` via Search Dictionary |
| 4 | `TITLE_EXACT` | `title ILIKE $q` |
| 5 | `ALIAS_EXACT` | `aliases @> ARRAY[$q]` |
| 6 | `CONTEXT` | `context @> [{context_key}]` |
| 7 | `FTS` | `to_tsvector('simple', search_text) @@ plainto_tsquery('simple', $q)` |
| 8 | `TRIGRAM` | `title % $q` (pg_trgm, similarity ≥ 0.3) — last resort |

**Within-tier sort (§24):**
```
tier_precedence ASC
→ source_updated_at DESC
→ object_type ASC
→ canonical_id ASC
```

---

## 4. Result Deduplication

Identity: `(object_type, canonical_id)`

One document appearing in multiple tiers → highest-priority tier wins.
Lower-tier evidence is discarded (not merged into a single result).

---

## 5. Pagination

Physical offset pagination. Stable because the ordering is fully deterministic.

```
page: 1..N (1-indexed)
page_size: 1..50
offset = (page - 1) × page_size
```

`SearchResponse.total` is the count of deduplicated results across ALL tiers
(before pagination), consistent across pages.

---

## 6. Visibility

Every retrieval query applies:
```sql
publication_status = 'PUBLISHED'
AND visibility_scopes @> ARRAY['<scope>']
```

| Consumer | Scope |
|----------|-------|
| Public (F3) | `PUBLIC` |
| SaaS (F4) | `SAAS` |
| Paid (F4) | `PAID` |

The engine does NOT re-judge Domain publication status. What the adapter set
during the rebuild is authoritative.

**CHEM special:** CHEM documents are indexed with `visibility_scopes=['PUBLIC']`
only when `KOSHA_MSDS_PUBLIC_MODE` ∈ `{seo_preview, full}` at rebuild time.
The API also checks this env var to include/exclude `CHEM` from the allowed
object_types list.

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
| `match_type` | str | Winning tier name |
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

No internal SQL, scoring coefficients, or debug data exposed in public responses.

---

## 8. Database Migration

**File:** `supabase/migrations/20260919_shared_search_retrieval.sql`

**Status:** authored, NOT applied to production (awaiting G1).

Extends F1 Foundation tables with:

| Index | Tier |
|-------|------|
| `search_documents_fts_search_text_idx` | FTS (simple) |
| `search_documents_fts_weighted_idx` | Weighted FTS (title=A, body=B) |
| `search_documents_title_trgm_idx` | TRIGRAM (title only) |
| `search_documents_subjects_gin_idx` | SUBJECT |
| `search_documents_context_gin_idx` | CONTEXT |
| `search_documents_aliases_gin_idx` | ALIAS_EXACT |
| `search_documents_visibility_scopes_gin_idx` | all tiers |
| `search_documents_source_key_idx` | IDENTIFIER_EXACT |
| `search_documents_canonical_id_idx` | CANONICAL_EXACT |
| `search_documents_object_type_idx` | type filter |
| `search_documents_source_updated_at_idx` | within-tier sort |
| `search_documents_title_lower_idx` | TITLE_EXACT |

**What is NOT indexed (§15):**
- `search_text gin_trgm_ops` — no evidence of size/necessity; excluded per WO
- Large legal body trigram index — excluded per WO

---

## 9. Public API

**Router:** `routers/public_safety_search.py`

### GET /public/safety-search

New F3 endpoint. Backed by `SharedRetrievalEngine`.

**Query parameters:**

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `q` | str | required | min 1 char; 422 on blank |
| `type` | str? | all | `guide`, `material`, `accident`, `chem`, `knowledge`, `precedent`, `law`/`legal` |
| `page` | int | 1 | ≥1 |
| `page_size` | int | 10 | 1..50 |

**Visibility:** `PUBLIC` only. `CHEM` excluded unless `KOSHA_MSDS_PUBLIC_MODE` active.
**Blank q:** returns 422. DB full-scan never executed.
**Legal authority:** never produced here.

### GET /public/safety-search/kosha (unchanged)

External KOSHA Smart Search — retained as-is. Not merged into Shared Search index.

---

## 10. Public Parity Audit

### 10.1 tai-www current state

As of the F3 investigation, tai-www (`/Users/taiwangsim/Desktop/tai-www`) does **not**
have a `/safety-search` page or `src/lib/server/safetySearch.js` file.
Domain-specific search pages exist separately:

| tai-www page | Source table | search scope |
|---|---|---|
| `/accident-cases` | `csi_accident_catalog` (client-side) | CSI accidents |
| `/precedent-search` | supabase precedents | Precedents |
| `/law/*` | supabase law_revisions | Law revisions |
| `/safety-news` | supabase safety posts | Safety news |

### 10.2 Shared Search adapter coverage (F2)

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

### 10.3 Parity matrix (per WO §37-§40)

| WO group | Current tai-www source | Shared Search type | Semantic parity | Cutover ready |
|---|---|---|---|---|
| `guide` | not unified (KOSHA PDF/guides) | `GUIDE` | HIGH — same KOSHA source | YES |
| `material` | `/safety-post-detail` (KOSHA materials) | `SAFETY_MATERIAL` | HIGH — same KOSHA catalog | YES |
| `accident` | `/accident-cases` (CSI catalog, client-side) | `CSI_ACCIDENT` | HIGH — same CSI catalog | YES (after G1 rebuild) |
| `precedent` | `/precedent-search` | `PRECEDENT` | HIGH — same source | YES |
| `knowledge` | `safe_help_content` | `KNOWLEDGE` | MEDIUM — needs verify (article vs. chunk identity) | NEEDS VERIFY |
| `law` | `law_revision_board` (revision events) | `LEGAL` (`law_article`) | LOW — different grain: revision ≠ article | RETAIN LEGACY |
| `kosha` | external KOSHA provider | external (unchanged) | N/A — external | RETAIN |
| `chem` | none (no current public tab) | `CHEM` | N/A — new domain | DEFER to UX decision |

### 10.4 Cutover decisions

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
  CHEM (no public UI tab; API-ready but no display URL confirmed)
```

### 10.5 tai-www migration design (§42-§43)

When `/safety-search` is created in `work/search-f3-public` (separate PR):

```
src/lib/server/sharedSearch.js   — new: API client for GET /public/safety-search
src/lib/server/safetySearch.js   — new: orchestrates SharedSearch + legacy providers
src/pages/safety-search.astro    — new: Public search page (SSR)
```

**Provider architecture:**
```
SafetySearchOrchestrator
  ├── SharedSearchProvider   → GET /public/safety-search (GUIDE, MATERIAL, CSI, PRECEDENT)
  ├── LegacyLawProvider      → law_revision_board (direct, retained)
  └── KoshaProvider          → GET /public/safety-search/kosha (unchanged)
```

**Rollback (§63):** switch `safetySearch.js` to `LegacyProvider` only. No DB
rebuild required. Feature flag via environment variable; no new flag system.

---

## 11. Production Gate Plan

### GATE-1 (F3-G1): Search Infrastructure Activation

**Requires: Owner Approval after GPT independent verify + CI success**

```
1. Apply F1 Foundation migration (20260919_shared_search_foundation.sql)
2. Apply F3 Retrieval migration (20260919_shared_search_retrieval.sql)
3. Verify schema: search_documents / search_rebuild_runs / search_rebuild_documents
4. Run FULL rebuild (all 8 adapters)
5. Per-domain count reconcile vs. Domain SoT:
   - GUIDE / SAFETY_MATERIAL / CSI / CHEM / KNOWLEDGE / PRECEDENT / LEGAL
   - duplicate identity = 0
   - unexplained_drop = 0
   - HOLD exposure = 0
6. Retrieval smoke tests against production search_documents
7. tai-api deploy + /public/safety-search health check
```

### GATE-2 (F3-G2): Public Cutover

**Requires: G1 complete + Owner Approval**

```
tai-www work/search-f3-public PR merge
→ production deploy
→ /safety-search consumer switch
→ KOSHA provider unchanged
```

**Rollback:** revert `safetySearch.js` provider selection. DB untouched.

---

## 12. F4 Handoff

F4 reuses `SharedRetrievalEngine` WITHOUT modification:

```python
# F4 SaaS call
engine.search(q, visibility_scopes=["SAAS"], page=1, page_size=10)

# F4 Paid call
engine.search(q, visibility_scopes=["PAID"], page=1, page_size=10)
```

No new engine. No copy. Pass different `visibility_scopes`.
Legal applicability authority remains in Legal Engine — Search is discovery only.

---

## 13. Retrieval Readiness Evidence

Production census READ-ONLY evidence (from F2 FINAL2 run):

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

## 14. Files Changed (F3 PR)

| File | Change |
|------|--------|
| `supabase/migrations/20260919_shared_search_retrieval.sql` | NEW — retrieval indexes |
| `services/shared_search/query.py` | NEW — query understanding |
| `services/shared_search/result.py` | NEW — result contract |
| `services/shared_search/retrieval.py` | NEW — shared retrieval engine |
| `services/shared_search/__init__.py` | MODIFIED — F3 exports added |
| `routers/public_safety_search.py` | MODIFIED — added GET /public/safety-search |
| `tests/test_shared_search_f3_retrieval.py` | NEW — 51 tests |
| `docs/search/TAI_SHARED_SEARCH_F3_RETRIEVAL_PUBLIC.md` | NEW — this document |

**Part A files (included in F2 FINAL2, present in b4ee0ce3 merge):**
- `services/shared_search/adapters/csi_accident.py` — title OR summary fallback
- `services/shared_search/adapters/chem.py` — A02 product_name binding
- `services/shared_search/census.py` — CountingFetcher + source_yield_audit
- `services/kosha_msds/section_fields.py` — extract_product_name helper
- `services/shared_search/production_bindings.py` — A02 enrichment

---

## 15. Safety Invariants

```
PRODUCTION DB WRITE    = 0  (F3 implementation phase)
MIGRATION APPLY        = 0  (awaiting G1)
DEPLOY                 = 0  (awaiting G1)
PUBLIC CUTOVER         = 0  (awaiting G2)
CHEM API CALL          = 0
RISK CHANGE            = 0
GRAPH APPLY            = 0
LLM CALL               = 0
LEGAL APPLICABILITY    = 0  (search is discovery only)
EMBEDDING / VECTOR     = 0  (Postgres FTS + pg_trgm only)
NEW GENERIC INDEX      = 0  (search_documents only, as Foundation)
```
