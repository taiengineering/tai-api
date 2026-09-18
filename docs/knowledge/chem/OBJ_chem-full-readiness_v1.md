---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-FULL-READINESS-001 receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-FULL-READINESS-001 — Shared Incremental Materialize Writer

## Summary

Convert the SEO preview production writer from a blind-INSERT loop
into a shared incremental writer that classifies each plan row
against the current DB state and writes only the delta:

```text
NEW        → INSERT with fresh id + CHEM:<uuid> content_id
UNCHANGED  → no write; existing id / content_id preserved
CHANGED    → UPDATE mutable columns; canonical identity preserved
CONFLICT   → IncrementalWriteBlocked (preflight-caught earlier)
```

Membership rows are written for every plan chemical regardless of
kind. The writer never mutates canonical identity fields (`id`,
`content_id`, `source_id`, `source_key`, `chem_id`) on an existing
chemical row, and never mutates the `(chemical_id, section_no)`
natural key on an existing section row. `PUBLISHED_SEO_PREVIEW`
snapshot `7bba6dfe-…f364c5` in production is untouched by this WO
(no live DB write is performed).

## Anchors

```text
main at run             = 655cee77f6befb6f8e15c096e1a0b54663fb65af
branch                  = feature/chem-full-readiness-incremental-writer
```

## Design

Reused verbatim (no forks):

```text
services/kosha_msds/materialize_writer.py
    classify_chemicals()          NEW / UNCHANGED / CHANGED / CONFLICT
    classify_sections()           same taxonomy, per section
    CHEMICAL_BATCH_SIZE           = 100  (unchanged from CHEM-08)
    SECTION_BATCH_SIZE            = 200
    SNAPSHOT_ITEM_BATCH_SIZE      = 500
    open_snapshot()               unchanged
services/kosha_msds/identity.py
    new_content_id()              default id_factory wraps it
```

New in `services/kosha_msds/materialize_writer.py`:

```text
CHEMICAL_IMMUTABLE_FIELDS  = {id, content_id, source_id, source_key, chem_id}
CHEMICAL_MUTABLE_FIELDS    = {identity_status, identity_reason,
                              chemical_name_ko/en, cas_no, ke_no, en_no, un_no,
                              last_date, source_content_hash, source_dataset_url,
                              is_current, last_seen_at, updated_at}
SECTION_IMMUTABLE_FIELDS   = {chemical_id, section_no}
SECTION_MUTABLE_FIELDS     = {payload_json, section_hash,
                              result_code, result_message, fetched_at}

MemoryMaterializeStore.update_chemical(source_id, source_key, mutable_fields)
MemoryMaterializeStore.update_section(chemical_id, section_no, mutable_fields)
    - raises ValueError on any immutable field
    - raises KeyError if the row does not exist

IncrementalWriteBlocked  (MaterializeWriterError subclass)
execute_incremental_write(inputs, *, store, snapshot_id, id_factory=None)
    -> IncrementalWriteReport
```

New in `services/kosha_msds/production_store.py`:

```text
SupabaseMaterializeStore.update_chemical(source_id, source_key, mutable_fields)
SupabaseMaterializeStore.update_section(chemical_id, section_no, mutable_fields)
    - mirrors the memory store's field-mutability check
    - uses .table().update({...}).eq("source_id").eq("source_key").execute()
    - never DELETE / never TRUNCATE / never touches identity columns
```

## `execute_production.py` refactor

The 90-line inline INSERT/verify loop (previous lines 295-368) is
replaced with a single call:

```python
try:
    write_report = w.execute_incremental_write(
        plan_inputs, store=mat_store, snapshot_id=snapshot_id,
    )
except w.IncrementalWriteBlocked as exc:
    raise ExecutorError(f"BLOCKED {BLOCK_MATERIALIZE_WRITE}: {exc}") from exc
mat_store.update_snapshot_status(snapshot_id, SNAPSHOT_COMPLETED)
```

The return dict keeps the `materialized_chemicals`,
`materialized_sections`, and `materialized_snapshot_items` metric
names that the existing test suite asserts on
(`test_happy_path_promotes_to_published_seo_preview`); these now
resolve to `new + unchanged + changed` sums from the write report so
the empty-DB path stays byte-identical while a non-empty replay
reports the same "in-snapshot" totals rather than counting `INSERT`s.

The `materialize_write_report` key is added to the return dict for
downstream logging / receipt purposes.

`services.kosha_msds.identity.new_content_id` is no longer imported
directly by the executor; the shared writer's default id_factory
owns that binding.

## Tests

```text
tests/test_chem_full_readiness.py     11 / 11  PASS  (0.06s)

  F1  empty DB → all NEW  (F1 asserts INSERT semantics identical
                            to the pre-refactor SEO preview run)
  F2  exact replay → all UNCHANGED, zero chemical/section writes,
                     membership rows only, existing id / content_id preserved
  F3  Preview → expanded corpus (3 UNCHANGED + 2 NEW, membership=5)
  F4  CHANGED chemical → id / content_id / source_key / chem_id all
                          preserved; source_content_hash + cas_no updated
  F5  CHANGED section → (chemical_id, section_no) preserved;
                         section_hash updated; other 15 sections stay UNCHANGED
  F6  Identity conflict → IncrementalWriteBlocked, zero INSERTs / zero UPDATEs
  F7  Partial-failure replay → 2 UNCHANGED + 3 NEW, no duplicate-key error,
                                original UUIDs preserved on replayed rows
  F8  Snapshot state unchanged by the writer (RUNNING / NOT_PUBLISHED);
      writer never emits PUBLISHED_FULL

  Extra:
    - update_chemical refuses any of {id, content_id, source_id,
      source_key, chem_id}; mutable field succeeds; identity byte-stable
    - update_section refuses any of {chemical_id, section_no}
    - deterministic replay produces identical write report

Focused CHEM regression                185 / 185  PASS
  (chem05 + chem06 + chem07 + chem08 + chem09 + chem10
   + chem_seo_preview + chem_seo_preview_execute + chem_full_readiness)

Pre-existing SEO preview executor tests (16) all still pass — the
happy_path_promotes_to_published_seo_preview assertion on
materialized_chemicals=3 / sections=48 / snapshot_items=3 is
byte-identical.
```

## Governance

```text
PRODUCTION DB WRITE                  = 0
PUBLISHED_SEO_PREVIEW MUTATION       = 0  (F8 verifies)
PUBLISHED_FULL MUTATION              = 0
KOSHA API CALL                       = 0
HYDRATION RESUME                     = 0
HYDRATION ARTIFACT MUTATION          = 0

SCHEMA CHANGE                        = 0
NEW MIGRATION                        = 0
NEW ENGINE                           = 0
NEW SCHEMA IDENTITY MODEL            = 0

CANONICAL IDENTITY OVERWRITE         = 0
  (F4 / F5 / test_immutable_* verify)

DB CONNECTION OPENED BY THIS WO      = 0
```

## Files (4)

```text
services/kosha_msds/materialize_writer.py                MOD  (+ mutable/immutable
                                                                field contract,
                                                                update_chemical /
                                                                update_section on
                                                                MemoryMaterializeStore,
                                                                execute_incremental_write)
services/kosha_msds/production_store.py                  MOD  (+ update_chemical /
                                                                update_section on
                                                                SupabaseMaterializeStore)
tools/chem_seo_preview/execute_production.py             MOD  (write loop replaced
                                                                by shared writer call;
                                                                new_content_id import
                                                                dropped)
tests/test_chem_full_readiness.py                        NEW  (11 tests)
docs/knowledge/chem/OBJ_chem-full-readiness_v1.md        NEW  (this receipt)
```

Not modified: `supabase/migrations/*`, `routers/*`, `router_registry/*`,
`services/kosha_msds/read.py`, `services/kosha_msds/search_adapter.py`,
`services/kosha_msds/publish.py`, `services/kosha_msds/materialize.py`,
`tools/chem04/*`, `tools/chem05/*`, `tools/chem08/*`, `tools/chem10/*`,
`services/kosha_safety_materials/*`, `tai-www`, Railway config.

## What this WO does NOT do

- No production DB write. `PUBLISHED_SEO_PREVIEW` snapshot in production
  stays intact.
- No `PUBLISHED_FULL` transition.
- No hydration resume; CHEM-04 is a parallel Track-H stream.
- No FULL plan / materialize / publish. Those remain owner-approved
  execution WOs (CHEM-08-EXECUTE / CHEM-10-EXECUTE / CHEM-12).
- No merge under Claude Code — awaits GPT delta-only verify.

## PATCH-1 — Bulk read + RUNNING closure

Two independent fixes, no re-design.

### PATCH-A — Bulk existing-state read

The pre-PATCH classify+write flow issued a per-row point read per
chemical AND per section, then re-read every section a second time
during the write phase. At FULL scale that was 678,744 REST round-
trips (20,568 + 329,088 + 329,088).

PATCH-A collapses the entire classify+write into two bulk fetches
via new store methods and a `_preload_existing_state` helper:

```text
services/kosha_msds/materialize_writer.py
  MemoryMaterializeStore.get_chemicals_by_natural_keys(pairs)
  MemoryMaterializeStore.get_sections_by_chemical_ids(chemical_ids)
  _preload_existing_state(inputs, store) -> (chem_map, sec_map)

  classify_chemicals(chemicals, *, store, preloaded_chemicals=None)
  classify_sections(chemicals, chem_class, *, store,
                    preloaded_sections=None)
  execute_incremental_write() now:
    1. preloads existing chemicals+sections in one bulk pass
    2. classifies against the preloaded maps
    3. reuses the preloaded section map for the write-phase check
       (no second `get_section` call)

services/kosha_msds/production_store.py (SupabaseMaterializeStore)
  get_chemicals_by_natural_keys(pairs)
    - groups by source_id, chunks source_keys @ _CHEMICAL_KEY_CHUNK = 200
    - one REST round-trip per chunk via .in_("source_key", chunk)
  get_sections_by_chemical_ids(chemical_ids)
    - chunks chemical_ids @ _SECTION_CHEM_CHUNK = 200
    - paginates within each chunk @ _SECTION_PAGE = 1000
```

Round-trip budget under FULL:

```text
before  20,568 chemical point reads
       + 329,088 section point reads (classify)
       + 329,088 section point reads (write)
       ─────────
       = 678,744

after   ~103 chemical bulk fetches (20,568 / 200)
       + ~412 section bulk fetches ((20,568 / 200) × ⌈3,200 / 1,000⌉)
       ─────────
       = ~515 REST round-trips
```

Backwards compat: stores lacking the bulk methods fall through to
the per-row path via `getattr(store, "get_chemicals_by_natural_keys",
None)` — pre-existing fixture doubles still work.

### PATCH-B — RUNNING → FAILED closure

`tools/chem_seo_preview/execute_production.py` now wraps the write
phase in a try/except that best-effort transitions the RUNNING
snapshot to FAILED before re-raising:

```python
try:
    try:
        write_report = w.execute_incremental_write(...)
    except w.IncrementalWriteBlocked as exc:
        raise ExecutorError(f"BLOCKED {BLOCK_MATERIALIZE_WRITE}: {exc}") from exc
    mat_store.update_snapshot_status(snapshot_id, SNAPSHOT_COMPLETED)
except Exception:
    try:
        mat_store.update_snapshot_status(snapshot_id, SNAPSHOT_FAILED)
    except Exception:
        pass  # secondary failures don't shadow the original exception
    raise
```

The snapshot row itself is preserved as evidence of the failed run
(no DELETE / no TRUNCATE). Future retries are unblocked because
`BLOCK_EXISTING_RUNNING_SNAPSHOT` only fires on RUNNING snapshots.

## PATCH-1 tests

```text
tests/test_chem_full_readiness.py                       13 / 13  PASS
  F1..F8 unchanged
  + A1  bulk-read replaces per-row reads in execute
  + A2  round-trip count invariant across 5 vs 400 existing chemicals

tests/test_chem_seo_preview_execute.py                  19 / 19  PASS
  16 pre-existing tests unchanged
  + F9   insert_sections failure → snapshot FAILED, publish never called
  + F10  insert_chemicals failure → snapshot FAILED, PUBLISHED_* untouched
  + F11  replay after failed run → 0 duplicate-key errors,
         3 UNCHANGED chemicals + partial UNCHANGED/NEW sections

Focused CHEM regression                                190 / 190  PASS
```

## PATCH-2 — Preflight preload sharing + NEW bulk verify

Two follow-up fixes to close the remaining N+1 in the executor's
end-to-end path.

### PATCH-2 §1 — single preload shared by preflight + writer

Before PATCH-2, `preflight()` called `classify_chemicals` and
`classify_sections` without preloaded maps, so those still issued
per-row point reads:

```text
Executor _run:
  preflight()             ← FULL: 20,568 chem + 329,088 sec point reads
  execute_incremental_write()  ← preload here, then bulk classify + write
```

After PATCH-2, the executor calls `preload_existing_state` once and
passes the returned `ExistingState` to both:

```text
services/kosha_msds/materialize_writer.py
  @dataclass(frozen=True) class ExistingState
  def preload_existing_state(inputs, store) -> ExistingState
  def preflight(..., preloaded: Optional[ExistingState] = None)
  def execute_incremental_write(..., preloaded: Optional[ExistingState] = None)

tools/chem_seo_preview/execute_production.py
  preloaded = w.preload_existing_state(plan_inputs, mat_store)
  preflight  = w.preflight(..., preloaded=preloaded)
  write_report = w.execute_incremental_write(..., preloaded=preloaded)
```

Round-trip budget for the whole executor pipeline (FULL):

```text
before PATCH-2   ~349,000 point reads before writer + ~515 bulk in writer
after PATCH-2    ~515 bulk round-trips total across preflight + writer
```

Backwards compat: both `preflight()` and `execute_incremental_write()`
still call `preload_existing_state` internally when `preloaded=None`,
so pre-existing tests that don't preload still work — they just do
the fetch inside instead of the executor.

### PATCH-2 §2 — bulk NEW post-insert verification

Before PATCH-2, the "did the INSERT actually land with the expected
id?" sanity check ran one `get_chemical_by_natural_key` per NEW row.
For FULL that's an extra 18k+ point reads.

After PATCH-2, the writer issues a single
`store.get_chemicals_by_natural_keys(new_keys)` after all NEW rows
are inserted and validates the batch in memory. Backwards compat:
stores lacking the bulk method fall through to the per-row path.

## PATCH-2 tests

```text
tests/test_chem_full_readiness.py                       16 / 16  PASS

  F1..F8 unchanged
  A1 revised   preload + NEW verify = 2 chem bulk reads, 1 sec bulk read,
                zero chem_point_reads (was 3, now 0), zero sec_point_reads
  A2 unchanged round-trip count invariant across 5 vs 400 existing
  + B1  full preflight + writer end-to-end zero point reads
        (50 existing chemicals: 1 chem_bulk + 1 sec_bulk = 2 round-trips total)
  + B2  400 NEW post-insert verification = 1 bulk fetch, 0 point reads
        (was 400 point reads, now 0)
  + B3  PATCH-2 preload path preserves F2/F4/F6 semantics
        (all UNCHANGED replay + CONFLICT fail-closed)

tests/test_chem_seo_preview_execute.py                  19 / 19  PASS  (unchanged)

Focused CHEM regression                                193 / 193  PASS
```

## Verdict

```text
WO-CHEM-FULL-READINESS-001 PATCH-2 = PASS / READY FOR MERGE

- Incremental writer preserves canonical identity
- Preflight and writer share one preload (2 bulk fetches total)
- NEW post-insert verification is bulk, not per-row
- RUNNING snapshots are always closed to FAILED on write error
- Executor pipeline (preflight → write) hits 0 point reads under FULL
- No production DB write under this WO
- Pre-existing SEO preview tests all still pass unchanged

NEXT  =  merge → P2 FULL cutover rehearsal
STOP
```
