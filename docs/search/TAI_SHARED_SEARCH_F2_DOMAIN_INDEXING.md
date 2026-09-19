# TAI Shared Search — F2 Domain Indexing

**WO**: WO-TAI-SHARED-SEARCH-F2
**Status**: implementation-ready. Production Supabase migration for
F1 remains un-applied; F2 adds no new schema.
**Contract source**:
- `docs/search/TAI_SHARED_SEARCH_CONSTITUTION_v1.md`
- `docs/search/TAI_SHARED_SEARCH_DOCUMENT_CONTRACT_v1.md`
- `docs/search/TAI_SHARED_SEARCH_RESULT_CONTRACT_v1.md`
- `docs/search/TAI_SHARED_SEARCH_FOUNDATION_v1.md`

F2 wires each Domain SoT to the Foundation through a thin adapter.
The adapter layer is intentionally minimal — most of the code is
already shared.

## 1. Architecture

```
Domain SoT (kosha_guide / kosha_safety_materials / csi_accident_cases /
            kosha_msds_* / safe_help_content / industrial_accident_precedents /
            LEG stack / risk_canonical_nodes)
      │
      │   (each Domain's own read model; F2 never mutates it)
      ▼
   DomainAdapter (per Domain, ~80 LOC)
      │
      ▼
   Common Indexer (services/shared_search/indexer.py)
      │
      ▼
   Common Writer + RebuildFramework  (F1)
      │
      ▼
   SearchStore Protocol (MemoryStore in tests, SupabaseSearchStore in prod)
      │
      ▼
   Unified Search Projection
```

**Every write goes through the SearchStore.** No adapter touches
`search_documents` directly. Enforced by
`tests/test_shared_search_f2_adapters.py::test_no_duplicate_common_implementations`
which greps the adapters directory for forbidden call patterns.

## 2. Shared modules (Foundation-level)

| Module | Role | Reused by |
|--------|------|-----------|
| `services/shared_search/contract.py` | vocabulary + `FORBIDDEN_DOCUMENT_KEYS` | writer, all adapters transitively |
| `services/shared_search/document.py` | `normalize_document()` — sort/dedup/reject | writer |
| `services/shared_search/hash_utils.py` | deterministic `content_hash` | writer, reconcile, adapters via helper |
| `services/shared_search/writer.py` | `Writer` + `MemoryStore` | all adapters via Indexer |
| `services/shared_search/rebuild.py` | `RebuildFramework` | Indexer |
| `services/shared_search/reconcile.py` | `reconcile()` READ-only | Indexer |
| `services/shared_search/store.py` | `SearchStore` Protocol | MemoryStore + SupabaseSearchStore |
| `services/shared_search/source_reader.py` | `paginate_supabase()` — the ONE Supabase paginator | production adapters (F2+) |
| `services/shared_search/indexer.py` | Common index orchestrator (`full_rebuild`, `object_reindex`, `reconcile_domain`, `dry_run`) | callers of adapters |
| `services/shared_search/adapters/_common.py` | `coerce_iso` + `as_str_list` + `expected_hashes_from_documents` | all 8 adapters |
| `services/shared_search/production_store.py` | `SupabaseSearchStore` implementing `SearchStore` | production runtime |

**Duplicate common implementation = 0**. Every capability shared by
2+ adapters lives in a single module. The audit test enumerates the
prohibited patterns (search_documents.upsert / search_rebuild_runs.insert
/ promote_search_rebuild / supabase.table( / …) and verifies zero
matches under `services/shared_search/adapters/**`.

## 3. Domain Identity Matrix (F2-actual)

| Domain | object_type | canonical_id source | source_id | source_key | publication gate | Notes |
|---|---|---|---|---|---|---|
| GUIDE | `GUIDE` | `kosha_guide.id` | `KOSHA_OFFICIAL_GUIDE` | `guide_no` (fallback: `kosha_guide.id` when `guide_no` absent) | catalog + latest COMPLETED snapshot | PDF originals not chunked (LINK_ONLY) |
| SAFETY_MATERIAL | `SAFETY_MATERIAL` | `kosha_safety_materials.id` | `KOSHA_OFFICIAL_MATERIAL` | `source_med_seq` (NULLABLE) | catalog + snapshot + no unresolved storage hold (real column: `status` ∈ {`OPEN`, `RESOLVED`}, F2 FINAL §1 — no `resolved` boolean) | `status != RESOLVED` (fail-closed on null) collapses to HOLD |
| CSI_ACCIDENT | `CSI_ACCIDENT` | `csi_accident_cases.content_id` (`CSI:<uuid>`) | `CSI` | `NULL` (CSI file has none) | latest COMPLETED `snapshot_items.identity_status=READY` | detail = `/public/accidents/csi/{uuid_part}` |
| CHEM | `CHEM` | `kosha_msds_chemicals.id` (uuid) | `KOSHA_MSDS` | `kosha_msds_chemicals.source_key` (chem_id) | present in `kosha_msds_seo_preview_current` OR `kosha_msds_full_current` | Search NEVER calls `cutover.is_full_ready`. PUBLIC visibility gated by `KOSHA_MSDS_PUBLIC_MODE` env at query time. CHEM_TERM per-row subject NOT auto-assigned (F2 §19). |
| KNOWLEDGE | `KNOWLEDGE` | `safe_help_content.doc_id` | `TAI_HELP_CENTER` | `safe_help_content.doc_id` | `status = PUBLISHED` | `/help/search` operational endpoint unchanged; adapter mirrors content |
| PRECEDENT | `PRECEDENT` | `industrial_accident_precedents.id` | `law_go_kr` | `prec_seq` (may be NULL for legacy) | `is_active = true` | Detail resolver DEFERRED_TO_DOMAIN_ADAPTER; adapter sets `public_url = null` |
| LEGAL | `LEGAL` | `law_article.id` (Domain PK) — F2 FINAL §7 forbids `article_internal_key` (7,642 distinct / 35,412 rows) | `LEG_OFFICIAL` | `NULL` (F2 FINAL §8: no synthetic composite) | active `law_master` + `law_article.is_deleted_in_version=false` (F2 FINAL §3-§10: assembled from `law_master`+`law_version`+`law_article`; `law_article_current` view does NOT exist) | `obligation_atom` / `norm_cluster` raise `AdapterBlockedSubtype` (blocked; `legal_obligations` has 0 rows) |
| RISK | `RISK` | `risk_canonical_nodes.id` (when ACTIVE) | future | future | `status = ACTIVE` **AND** sector-linked | Currently 0 rows yielded — RISK-C02 opens the ACTIVE gate |

## 4. Adapter Protocol

```python
class DomainAdapter(Protocol):
    domain_name: str
    object_type: str

    def iter_documents(self) -> Iterator[dict]: ...
    def iter_expected_hashes(self) -> Iterator[dict]: ...
    def object_reindex_payload(self, canonical_id: str) -> Optional[dict]: ...
```

Every adapter is ~80 LOC and contains:

1. A constructor accepting Domain-shaped `fetch_current` / `fetch_by_id`
   callables. Tests inject in-memory lists; production wires them to
   `paginate_supabase(...)` over the Domain SoT.
2. A private `_normalize_<domain>(row) -> dict | None` function that
   translates a Domain row into a SearchDocument payload dict.
3. Three Protocol methods, each delegating to shared helpers.

RISK adapter is an empty generator today; it satisfies the Protocol
so a future RISK-C02 WO can flip it on with a fetcher change alone.

## 5. Common Indexer

```
Indexer(store).full_rebuild(adapters)
     ↓
   RebuildFramework.begin(expected_domains=[a.domain_name for a in adapters])
     ↓
   for each adapter:
     for payload in adapter.iter_documents():
        writer.stage(run_id, payload)     # normalize + hash + insert
     mark_domain_done(run, adapter.domain_name)
   (AdapterBlockedSubtype caught + recorded; run continues)
     ↓
   validate(run)
     ↓
   promote(run)  → store.replace_current_from_staging(run_id)  → PUBLISHED-only swap
     ↓
   RebuildResult{run_id, status, promoted_count, per_domain, blocked_subtypes}
```

`object_reindex(adapter, canonical_id)` and `reconcile_domain(adapter)`
follow the same delegation shape.

`dry_run(adapter)` normalizes every adapter payload without touching
the store — this is what production census (WO §26/§27) uses. Returns
a `DryRunCensus` with the counts + collision totals.

## 6. Production store

`SupabaseSearchStore` implements the `SearchStore` Protocol against
Supabase-py:

- current CRUD → `search_documents` (upsert on `object_type,canonical_id`)
- run/staging CRUD → `search_rebuild_runs` / `search_rebuild_documents`
- atomic promotion → `client.rpc("promote_search_rebuild", ...)`

The store never touches raw SQL beyond the RPC call. Its I/O
surface is a duck-typed `client.table(...).select/.insert/.upsert/.update/.delete/.eq/.range/.execute()` — same subset the CHEM
`production_store.py` and other TAI modules use.

## 7. Read-only production census

F2 CO §36-§40 delivers the tooling; the production run itself is an
Owner-approved separate step.

### 7.1 Tooling
- `services/shared_search/census.py::run_census(adapter)` — READ-only
  aggregator. Never writes to the SearchStore. Returns a
  `DomainCensus` with `yielded_count / unique_canonical_ids /
  duplicate_canonical_ids / identity_failures / title_failures /
  timestamp_failures / normalization_failures /
  visibility_{public,saas,paid,internal} / hash_collisions /
  blocked_subtypes / warnings`.
- `services/shared_search/production_bindings.py::build_production_adapters(supabase)`
  — returns all 8 Domain adapters wired to the production views
  through the shared paginator. Consumer never constructs fetchers.
- `tools/shared_search/f2_census.py` — thin CLI wrapper.

### 7.2 Run command (post Owner GO)

```bash
railway run --service tai-api-prod \
    python3 -m tools.shared_search.f2_census --json \
    > f2_census_$(date +%Y%m%d).json
```

Zero SearchStore write. Zero RPC. Zero DML. Zero env change.

### 7.3 Baseline anchors (F2 WO §7 / §40) + measured census (2026-09-19)

The Owner-provided sanity anchors and the actual READ-only census
result (evidence: `docs/search/evidence/f2_census_20260919.json`):

| Domain | Anchor | Measured | Δ | Verdict |
|---|---|---|---|---|
| GUIDE | ≈ 1,039 | **1,039** | 0 | anchor exact |
| SAFETY_MATERIAL (member) | ≈ 9,218 | **9,218** | 0 | anchor exact |
| SAFETY_MATERIAL (HOLD) | ≈ 501 | 135 | -366 | signal (join = hold ∩ membership, not raw hold count) |
| CSI READY | ≈ 37,157 | 34,368 | -2,789 | signal (Domain state drift) |
| CHEM SEO PREVIEW | 1,997 | 0 | -1,997 | signal (view returned 0 rows; investigate outside F2 scope) |
| CHEM FULL | 0 | 0 | 0 | anchor exact |
| KNOWLEDGE PUBLISHED | 322 | **322** | 0 | anchor exact |
| PRECEDENT active | 849 | **849** | 0 | anchor exact |
| LEGAL current-eligible articles | 35,412 | **35,412** | 0 | anchor exact — canonical_id = `law_article.id`, 35,412 unique, 0 duplicate |
| LEGAL obligations | 0 (BLOCKED) | 0 (BLOCKED) | 0 | anchor exact |
| RISK indexed | 0 | 0 | 0 | anchor exact — gate closed until RISK-C02 |

Hard-fail criteria (F2 WO §14):
- duplicate canonical_ids: **0** across all 8 Domains
- identity failures: **0**
- title failures: **0**
- timestamp failures: **0**
- normalization failures: **0**
- LEGAL yielded == 35,412: **PASS**

Drift signals (Domain state / join semantics — not blockers): CSI,
CHEM SEO preview, MATERIAL HOLD. Recorded here for the Owner and
handed off to F3.

## 8. Boundary — what F2 does NOT do

- No production migration apply (F1 migration is still un-applied)
- No production Search write
- No production Supabase Search RPC call
- No retrieval HTTP endpoint (F3)
- No consumer wiring (F4)
- No RISK ACTIVE change
- No CHEM hydration / materialize / publish
- No env change
- No graph apply

The F1 safety guards (RISK-DRAFT rejection, legal-applicability
key rejection, tenant-key rejection, no-LLM audit) all continue to
apply — F2 tests re-run the audit test against the full
`services/shared_search/**` tree including the new adapter files.

## 9. Tests

`tests/test_shared_search_f2_adapters.py` — 31 tests:

- Per-adapter unit tests (GUIDE / MATERIAL / CSI / CHEM / KNOWLEDGE /
  PRECEDENT / LEGAL / RISK)
- Cross-domain integration (7-Domain rebuild + RISK negative)
- Publication safety (HOLD / DRAFT / is_active=false all skipped)
- Object reindex
- Reconcile
- Dry-run census counts
- Cross-domain identity collision (same canonical_id + different
  object_type allowed; same pair collapses to one row)
- Shared-use audit (adapters directory grep for forbidden patterns)
- No LLM SDK imports in `services/shared_search/**`
- End-to-end rebuild → reindex → reconcile

Regression across the full search stack: 133 pass / 1 skip
(shared_search F1+F2 + search-dict + CHEM P5).

## 10. F3 handoff

F2 produces:

- 8 adapters ready to be wired to production Supabase fetchers
  (`GuideAdapter(fetch_current=…)` etc.)
- One `SupabaseSearchStore` awaiting the F1 migration's production
  apply
- One `Indexer` that will orchestrate every future rebuild / reindex /
  reconcile without per-Domain branching

F3 (SEARCH-05) picks up from here to build the retrieval engine on
top of `search_documents` + the query-understanding stack.
