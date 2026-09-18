---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-08-PRODUCTION-MATERIALIZER-001 materializer receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-08-PRODUCTION-MATERIALIZER-001 — Guarded KOSHA MSDS Production Materializer

## Summary

Pure-logic + CLI materializer that consumes CHEM-05's plan artifacts
and produces preflight, row classification (NEW / UNCHANGED / CHANGED /
CONFLICT), and a deterministic chunk plan. **Zero production DB writes
under this WO.** A load-bearing three-gate fence blocks every code path
that could open a live DB connection.

```text
IMPLEMENT               = YES
TEST (fixture only)     = YES
PRODUCTION EXECUTE      = NO
DB WRITE                = 0
PUBLISH                 = 0
```

## Anchors

```text
main at run             = 3b5e0cb5699df6663021d44997af41b4c628abf1
branch                  = feature/chem08-production-materializer
```

## Files

```text
services/kosha_msds/materialize_writer.py      pure logic — preflight,
                                                classification, chunk planning,
                                                snapshot lifecycle helpers,
                                                the load-bearing safety fence
tools/chem08/__init__.py                       package marker
tools/chem08/materialize_production.py         --dry-run + fail-closed --execute CLI
tests/test_chem08_materializer.py              23 tests (§26 items 1..20 + 3 CLI/cross-domain)
docs/knowledge/chem/
  OBJ_chem08-production-materializer_v1.md    this receipt
```

## Reused existing helpers (no fork)

```text
services/kosha_msds/contract.py   ALLOWED_SECTIONS,
                                   DETAIL_COMPLETE / _INCOMPLETE / _EMPTY_BUT_VALID,
                                   SNAPSHOT_RUNNING / _COMPLETED / _FAILED,
                                   PUBLISH_NOT_PUBLISHED / _PUBLISHED_FULL,
                                   ENUMERATION_FULL_OFFICIAL,
                                   SOURCE_CONTRACT_VERSION
services/kosha_msds/materialize.py CHEM-05 plan schema (untouched;
                                   materializer consumes ChemicalBundle.to_dict())
```

Existing DB writer patterns referenced only for chunk sizes (no
imports, no coupling):

```text
tools/risk02/ingest001_source_core_local_exec.py
  RECORD_BATCH=100 MEMBERSHIP_BATCH=500
tools/risk_map/map_materialize001.py
  execute_values page_size=200
```

## Chunk sizes

```text
CHEMICAL_BATCH_SIZE          = 100    (based on RISK-02 RECORD_BATCH)
SECTION_BATCH_SIZE           = 200    (based on RISK-MAP page_size)
SNAPSHOT_ITEM_BATCH_SIZE     = 500    (based on RISK-02 MEMBERSHIP_BATCH)
```

Chunk planning is deterministic: input order does not affect batch
contents (verified by test 12).

## The three-gate fence

`assert_can_execute_production_write()` is the single choke point that
future code must pass before opening a DB connection. It enforces:

```text
Gate A  preflight_report.can_execute is True
  → data-shape gates (§4)
    - execute_eligible from CHEM-05 plan is True
    - manifest bindings (responses_sha256, plan_file_sha256,
                         plan_semantic_sha256) match on-disk SHAs
    - no PUBLISHED_FULL attempt in manifest
    - no existing RUNNING snapshot (unless --resume-snapshot matches)
    - no INCOMPLETE detail_status chemicals
    - no CHEMICAL_CONFLICT
    - no SECTION_CONFLICT

Gate B  owner_approved is True
  → BLOCK_OWNER_AUTHORIZATION_MISSING otherwise (§6)

Gate C  wo_scope_allows_write is True
  → hard-wired False by module-level
    services.kosha_msds.materialize_writer.PRODUCTION_WRITE_ALLOWED
  → BLOCK_WO_SCOPE_FORBIDS_WRITE otherwise
  → A future execution WO with explicit owner approval is the only
    mechanism that flips this. There is no CLI flag under WO-CHEM-08
    that opens Gate C.
```

Any gate failure raises `ProductionWriteForbidden` **before** any
store write method is called.

## Row classification (WO §13-§14)

```text
NEW        row not present in DB (natural key not found)
UNCHANGED  row present; source_content_hash (chemical) or
           section_hash (section) matches the plan exactly
CHANGED    row present; hash differs but identity is consistent
CONFLICT   identity mismatch — e.g. DB row exists on natural key but
           chem_id disagrees. Fail-closed at preflight; CONFLICT rows
           are excluded from every chunk batch.
```

Idempotency (§21) is proven by test 18: replaying the same plan
against a DB seeded with its result yields all-UNCHANGED, and the
chunk plan drops UNCHANGED rows to zero chemical/section batches.

## Snapshot lifecycle

```text
open_snapshot(...)             RUNNING, publish_state=NOT_PUBLISHED
                                enumeration_mode=FULL_OFFICIAL
                                source_contract_version=KOSHA_MSDS_OPENAPI_V1_2
                                expected_count=20,568
mark_snapshot_completed(...)   RUNNING → COMPLETED
mark_snapshot_failed(...)      RUNNING → FAILED
```

These helpers are fixture-only under WO-CHEM-08 (MemoryMaterializeStore
only). The future execution WO wires them against a Supabase/Postgres
store.

## PUBLISHED_FULL is unreachable

```text
Direct guard:  assert_no_publish_full()
Preflight:     manifest snapshot with publish_state=PUBLISHED_FULL
               emits BLOCK_PUBLISHED_FULL_ATTEMPTED
```

Test 16 covers both paths.

## Resume strategy (§17)

`--resume-snapshot <id>` matches a specific RUNNING snapshot in the DB
and silences BLOCK_EXISTING_RUNNING_SNAPSHOT. Idempotent classification
means already-written rows re-classify as UNCHANGED and are excluded
from the next batch. Complex recovery engines were rejected (WO §18).

## Tests

```text
tests/test_chem08_materializer.py     23 / 23  PASS  (0.09s)

  §26 items 1..20 individually covered:
    01 incomplete plan → BLOCK before DB
    02 bad manifest binding → BLOCK
    03 plan SHA mismatch → BLOCK
    04 existing RUNNING snapshot → BLOCK (resume-match silences)
    05 NEW chemical classification
    06 UNCHANGED chemical classification
    07 CHANGED chemical classification
    08 CONFLICT chemical → BLOCK
    09 NEW section classification
    10 UNCHANGED section classification
    11 section CONFLICT from parent → BLOCK
    12 chunk boundaries deterministic (order-independent)
    13 snapshot starts RUNNING
    14 success → COMPLETED
    15 write failure → FAILED
    16 PUBLISHED_FULL never emitted (direct + preflight guards)
    17 INCOMPLETE membership → BLOCK
    18 repeat run → zero duplicate logical rows
    19 dry_run never mutates store
    20 owner_auth missing + WO scope forbid together = fail-closed

  Extra:
    21 CLI --execute --owner-approved → rc=2, never opens DB
    22 no services/kosha_safety_materials import in writer or CLI
    23 CLI --dry-run prints compact JSON, PRODUCTION_WRITE_ALLOWED=False

Focused CHEM-05 + CHEM-08 regression   40 / 40  PASS
```

## Governance

```text
PRODUCTION DB WRITE         = 0
PRODUCTION INGEST           = 0
SUPABASE WRITE              = 0
CUSTOMER PUBLICATION        = 0
KOSHA API CALL              = 0
HYDRATION RESUME            = 0
HYDRATION ARTIFACT MUTATION = 0

SCHEMA CHANGE               = 0
NEW MIGRATION               = 0
NEW ENGINE                  = 0
NEW RPC / SQL FUNCTION      = 0
ROUTER REGISTRATION         = 0
LIVE ROUTE                  = 0
CROSS-DOMAIN COUPLING       = 0
```

## Verdict

```text
WO-CHEM-08-PRODUCTION-MATERIALIZER-001 = PASS / MATERIALIZER_READY

Writer is code-complete and fixture-validated. Zero DB code path
is reachable under this WO. A separate future execution WO must:
  1. flip services.kosha_msds.materialize_writer.PRODUCTION_WRITE_ALLOWED = True
  2. wire a SupabaseMaterializeStore behind the store interface
  3. carry explicit owner approval and pass --owner-approved
  4. run in a local terminal (Claude does not execute bulk
     production materialize in-session)

NEXT  =  GPT delta-only verify
         → CHEM-04 hydration remains armed / hold pending quota reset
         → future WO-CHEM-08-EXECUTE-001 for production materialize
STOP
```
