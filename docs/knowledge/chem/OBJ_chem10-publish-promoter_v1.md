---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-10-PUBLISH-PROMOTER-001 receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-10-PUBLISH-PROMOTER-001 — Guarded KOSHA MSDS Publish Promoter

## Summary

Pure-logic + CLI publish promoter that validates whether a
`kosha_msds_snapshots` row is eligible for promotion from
`NOT_PUBLISHED` → `PUBLISHED_FULL`, and (fixture-only under this WO)
performs that promotion. **Zero production publication under this WO.**
A load-bearing three-gate fence blocks every path that could open a
live DB connection.

```text
IMPLEMENT               = YES
FIXTURE TEST            = YES
PRODUCTION PUBLISH      = NO
DB WRITE                = 0
ROUTER ACTIVATION       = 0
CUSTOMER PUBLICATION    = 0
```

## Anchors

```text
main at run             = d30fee633d6350ae3fdc76425dfbeac4da607f0a
branch                  = feature/chem10-publish-promoter
```

## Files

```text
services/kosha_msds/publish.py                      pure logic —
                                                     preflight, eligibility,
                                                     safety fence,
                                                     fixture-only promotion
tools/chem10/__init__.py                            package marker
tools/chem10/publish_snapshot.py                    --dry-run +
                                                     fail-closed --execute CLI
tests/test_chem10_publish_promoter.py               25 tests (§32 items
                                                     1..20 + §32 21..24
                                                     recommended + 1 extra
                                                     cross-domain)
docs/knowledge/chem/
  OBJ_chem10-publish-promoter_v1.md                this receipt
```

## Reused existing constants / helpers (no fork)

```text
services/kosha_msds/contract.py
  ENUMERATION_FULL_OFFICIAL
  SNAPSHOT_COMPLETED
  PUBLISH_NOT_PUBLISHED, PUBLISH_PUBLISHED_FULL
  DETAIL_COMPLETE, DETAIL_EMPTY_BUT_VALID, DETAIL_INCOMPLETE

services/kosha_msds/materialize.py
  FULL_OFFICIAL_CHEMICAL_COUNT = 20,568 (constant re-imported symbolically)
  FULL_OFFICIAL_SECTION_COUNT = 329,088
```

## The three-gate fence

`assert_can_execute_publish()` is the single choke point that any
promotion caller must pass before opening a DB connection or calling
the fixture promote helper against a live store:

```text
Gate A  report.eligible is True
  → data-shape gates (§6..§13):
    - snapshot exists
    - status == COMPLETED
    - enumeration_mode == FULL_OFFICIAL
    - publish_state != PUBLISHED_FULL (i.e., not already published)
    - expected_count == 20,568
    - discovered_count == 20,568
    - snapshot_item_count == 20,568
    - 0 INCOMPLETE memberships
    - section_count == 329,088
    - 0 duplicate memberships
    - 0 duplicate (chemical_id, section_no) pairs
    - optional expected_materialize_binding match on
      snapshots.metrics_json (adapter_version /
      materialize_plan_sha256 / responses_sha256)

Gate B  owner_approved is True
  → BLOCK_OWNER_AUTHORIZATION_MISSING otherwise (§12)

Gate C  wo_scope_allows_publish is True
  → hard-wired False by module-level
    services.kosha_msds.publish.PRODUCTION_PUBLISH_ALLOWED
  → BLOCK_WO_SCOPE_FORBIDS_PUBLICATION otherwise
  → Only a future execution WO can flip Gate C. There is no CLI flag
    under WO-CHEM-10 that opens it.
```

Any gate failure raises `PublicationForbidden` **before** any store
promote method is called.

## Block reason vocabulary (WO §27)

```text
SNAPSHOT_NOT_FOUND
SNAPSHOT_NOT_COMPLETED
NOT_FULL_OFFICIAL
ALREADY_PUBLISHED
EXPECTED_COUNT_MISMATCH
DISCOVERED_COUNT_MISMATCH
SNAPSHOT_ITEM_COUNT_MISMATCH
INCOMPLETE_MEMBERSHIP
SECTION_COUNT_MISMATCH
DUPLICATE_MEMBERSHIP
DUPLICATE_SECTION
MATERIALIZE_BINDING_MISMATCH
OWNER_AUTHORIZATION_MISSING
WO_SCOPE_FORBIDS_PUBLICATION
```

## Atomic promotion model

Promotion is a single-field update on the target snapshot:
`publish_state = 'PUBLISHED_FULL'`. The view
`kosha_msds_current`'s SQL definition
(`supabase/migrations/20260914_kosha_msds_catalog.sql:169-202`) orders
by `completed_at DESC` and picks the newest PUBLISHED_FULL row, so
the view's answer flips atomically the moment the update commits.

Historical snapshots are never touched (WO §19). Old PUBLISHED_FULL
snapshots stay in place; the view naturally shifts to the newer one.

## Failure semantics

`promote_to_published_full` wraps the fixture-store promote call in a
try/except that rolls back to the prior publish_state on any error.
Under the current MemoryPublishStore the primitive is a single-field
update so a partial-write is impossible; the try/except is kept for
symmetry with a future Supabase adapter that may involve richer
sequences. Test 18 verifies rollback semantics on a simulated failure.

## Store architecture

```text
MemoryPublishStore        in-memory fixture store — read + fixture write
  get_snapshot(id)
  snapshot_items(id)
  section_count_for_snapshot(id)
  duplicate_section_pairs_for_snapshot(id)
  latest_published_snapshot()
  promote_to_published_full(id)   fixture-only
  demote_snapshot(id)             fixture-only rollback helper

SupabasePublishStore      DEFERRED — a future execution WO wires it.
```

No production DB connection is opened by this module.

## What this WO does NOT touch

```text
supabase/migrations/                             untouched
router_registry/*                                untouched (test 23)
services/kosha_msds/read.py                      untouched
services/kosha_msds/search_adapter.py            untouched (test 24)
services/kosha_msds/materialize.py               untouched
services/kosha_msds/materialize_writer.py        untouched
routers/kosha_public_msds.py                     untouched
tools/chem04/, tools/chem05/, tools/chem08/      untouched
services/kosha_safety_materials/*                not imported (test 25)
```

## Tests

```text
tests/test_chem10_publish_promoter.py    25 / 25  PASS  (6.50s)

  §32 items 1..20 individually covered:
    01 snapshot missing → BLOCK
    02 RUNNING → BLOCK
    03 FAILED → BLOCK
    04 enumeration != FULL_OFFICIAL → BLOCK
    05 already PUBLISHED_FULL → BLOCK (no mutation)
    06 expected_count != 20,568 → BLOCK
    07 discovered_count != 20,568 → BLOCK
    08 snapshot_items != 20,568 → BLOCK
    09 INCOMPLETE membership > 0 → BLOCK
    10 sections != 329,088 → BLOCK
    11 duplicate membership → BLOCK
    12 duplicate section pair → BLOCK
    13 materialize binding mismatch → BLOCK
    14 valid full snapshot → ELIGIBLE (0 block reasons)
    15 owner approval missing → BLOCK
    16 WO scope false → BLOCK (even with owner approval)
    17 fixture promotion (wo_scope_allows_publish=True)
       → NOT_PUBLISHED → PUBLISHED_FULL
    18 promotion failure via simulated store exception
       → new snapshot state stays NOT_PUBLISHED
       → old PUBLISHED_FULL snapshot preserved
    19 historical snapshots not deleted after promotion
    20 dry_run causes zero mutation (store byte-identical before/after)

  §32 items 21..24 (recommended):
    21 exactly one view-current snapshot after promotion
    22 CLI --execute --owner-approved → rc=2, never opens DB
    23 router_registry/public.py unchanged
    24 search_adapter untouched; publish.py does not import from routers

  Extra:
    25 no services/kosha_safety_materials import in publish.py or CLI

Focused CHEM-08 + CHEM-10 regression      48 / 48  PASS
```

## Governance

```text
PRODUCTION DB WRITE          = 0
PRODUCTION INGEST            = 0
SUPABASE WRITE               = 0
CUSTOMER PUBLICATION         = 0
KOSHA API CALL               = 0
HYDRATION RESUME             = 0
HYDRATION ARTIFACT MUTATION  = 0

SCHEMA CHANGE                = 0
NEW MIGRATION                = 0
NEW ENGINE                   = 0
NEW RPC / SQL FUNCTION       = 0
ROUTER REGISTRATION          = 0
LIVE ROUTE                   = 0
SEARCH LAYER CHANGE          = 0
CROSS-DOMAIN COUPLING        = 0
DB CONNECTION OPENED         = 0
```

## Verdict

```text
WO-CHEM-10-PUBLISH-PROMOTER-001  = PASS / PUBLISH_PROMOTER_READY

Promoter is code-complete and fixture-validated. Zero DB code path
is reachable under this WO. A separate future execution WO must:
  1. flip services.kosha_msds.publish.PRODUCTION_PUBLISH_ALLOWED = True
  2. wire a SupabasePublishStore behind the store interface
  3. carry explicit owner approval and pass --owner-approved
  4. Only execute AFTER CHEM-04 full hydration AND CHEM-08 owner-
     approved production materialize have completed

Sequencing (unchanged from WO §41):
  CHEM-04 full hydration
    → CHEM-05 final plan
    → CHEM-08 production materialize (future execution WO)
    → CHEM-10 publish (future execution WO)
    → CHEM-06 canonical read reflects publish
    → CHEM-12 router activation (future execution WO)

NEXT  =  GPT delta-only verify
         → CHEM-04 hydration remains armed / hold pending quota reset
         → future WO-CHEM-10-EXECUTE-001 for production publish
STOP
```
