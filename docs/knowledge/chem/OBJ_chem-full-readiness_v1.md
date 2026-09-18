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

## Verdict

```text
WO-CHEM-FULL-READINESS-001 = PASS / READY FOR GPT DELTA VERIFY

The SEO preview production writer is now safely re-runnable, and
future FULL rollouts will use the same code path with the same
canonical-identity guarantees. Nothing under this WO touches
production data.

NEXT  =  GPT delta-only verify
         → P2 FULL Cutover Readiness (fixture-only)
         → P3 Search acceptance
         → P4 Ops observability
         → P5 Full acceptance harness
         → CHEM-04 hydration continues in Track H, unblocked
STOP
```
