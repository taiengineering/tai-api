---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-FULL-READINESS-002 receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-FULL-READINESS-002 — FULL Cutover / Rollback Rehearsal

## Summary

Fixture-only rehearsal that exercises the SEO_PREVIEW ↔ FULL cutover
machinery already present in the repo. No new routing, no new
schema, no new engine — this WO composes the existing seams (CHEM-06
scoped read, CHEM-07 dormant public router with
`KOSHA_MSDS_PUBLIC_MODE`, CHEM-10 `preflight_publish`) into a
canonical readiness check and a documented L1 rollback contract,
then verifies C1..C8.

```text
CHEM-04 hydration           = NOT REQUIRED (parallel Track H)
Production DB write         = 0
Production publish          = 0
Railway env change          = 0
Deploy                      = 0
KOSHA API call              = 0
Search / terminology change = 0
Schema / migration          = 0
```

## Anchors

```text
main at run                = 64d97d2832111f807c395210c689e0e0c6746045
branch                     = feature/chem-full-readiness-002-cutover-rehearsal
```

## What was added

```text
services/kosha_msds/cutover.py                          NEW (~130 lines)
  @dataclass(frozen=True) class FullReadyReport
  def is_full_ready(snapshot_id, *, store,
                    expected_materialize_binding=None) -> FullReadyReport
    → delegates to publish.preflight_publish(scope=FULL) — no new
      eligibility engine (WO §8).

  rollback_contract() -> dict
    L1 (this WO):   KOSHA_MSDS_PUBLIC_MODE=full → seo_preview
                     mutates_db = False
    L2 (out of scope):  publish_state demote — future owner-approved WO
    OFF failsafe:   unknown / missing env → HTTP 503 MSDS_PUBLIC_DORMANT

tests/test_chem_full_readiness_002_cutover.py           NEW (17 tests)
docs/knowledge/chem/OBJ_chem-full-readiness-002_v1.md   NEW (this receipt)
```

Nothing else changed. In particular:

```text
supabase/migrations/                                    untouched
router_registry/                                        untouched
routers/kosha_public_msds.py                            untouched
services/kosha_msds/publish.py                          untouched
services/kosha_msds/read.py                             untouched
services/kosha_msds/materialize_writer.py               untouched
services/kosha_msds/production_store.py                 untouched
services/kosha_msds/search_adapter.py                   untouched
services/kosha_msds/materialize.py                      untouched
tools/chem_seo_preview/                                 untouched
tools/chem04/, tools/chem05/, tools/chem08/, tools/chem10/   untouched
```

## Cutover contract

FULL readiness (WO §8) is the canonical publish preflight, wrapped
for tests / receipts:

```text
FULL_READY = (
    snapshot.status                       == COMPLETED
  AND snapshot.enumeration_mode            == FULL_OFFICIAL
  AND snapshot.publish_state               == NOT_PUBLISHED
  AND snapshot.expected_count              == 20,568
  AND snapshot.discovered_count            == 20,568
  AND snapshot_items count                 == 20,568
  AND incomplete memberships               == 0
  AND sections count                       == 329,088
  AND duplicate memberships                == 0
  AND duplicate section pairs              == 0
  AND materialize binding matches manifest
)
```

Every one of those invariants is a `preflight_publish` block reason;
`is_full_ready` never re-implements them.

## L1 rollback contract

```text
L1 action        =  KOSHA_MSDS_PUBLIC_MODE=full  →  seo_preview
mutates DB       =  False
from mode        =  full
to mode          =  seo_preview
authorized here  =  True

L2 action        =  publication_state demote away from PUBLISHED_FULL
mutates DB       =  True
authorized here  =  False  ← requires a separate owner-approved WO

OFF failsafe     =  unknown / missing env → HTTP 503 MSDS_PUBLIC_DORMANT
                    (routers/kosha_public_msds.py already wires this)
```

The point of L1 as the primary rollback: it changes the router's
read pointer, not any DB row. FULL snapshot stays intact as evidence;
SEO preview snapshot keeps serving traffic. That means an L1 rollback
can't race against pending traffic — a critical invariant when
incident-response happens under load.

## Rehearsal test matrix (C1..C8)

```text
tests/test_chem_full_readiness_002_cutover.py     17 / 17 PASS  (3.86s)

  C1  preview active before FULL publish
       - mode=seo_preview → 3 preview rows served
       - 0 FULL-only chemicals leak into preview
  C2  FULL publish eligibility (canonical readiness check)
       - is_full_ready → ready=true, 0 block_reasons
       - 20,568 memberships / 329,088 section pairs verified
  C3  FULL publish preserves preview snapshot
       - promote_to_published_full (owner_approved=True,
         wo_scope_allows_publish=True fixture override)
       - old PUBLISHED_SEO_PREVIEW snapshot byte-identical after promotion
       - new snapshot flipped to PUBLISHED_FULL
  C4  mode=full → FULL scope served (5 rows including F00001-F00003)
  C5  rollback: mode=full → mode=seo_preview
       - preview scope served again
       - store._current and store._preview byte-identical before/after
       - L1 rollback DB mutation = 0
  C6  invalid full corpus blocks publish (6 parametrized cases)
       - membership_short   → SNAPSHOT_ITEM_COUNT_MISMATCH
       - section_short      → SECTION_COUNT_MISMATCH
       - incomplete_member  → INCOMPLETE_MEMBERSHIP
       - duplicate_member   → DUPLICATE_MEMBERSHIP
       - duplicate_section  → DUPLICATE_SECTION
       - binding_mismatch   → MATERIALIZE_BINDING_MISMATCH
       - each: assert_can_execute_publish raises PublicationForbidden
                snapshot publish_state stays NOT_PUBLISHED
  C7  mode=full without a PUBLISHED_FULL snapshot
       - FULL slice empty → empty envelope (not 500)
       - preview data does NOT leak into the FULL response
  C8  unknown mode → OFF → 503
    C8   garbage mode value → 503 MSDS_PUBLIC_DORMANT
    C8b  explicit "off" → 503
    C8c  missing env var → default OFF → 503

Extra safety:
  test_no_new_engine_or_terminology_change
    cutover.py imports zero search / terminology / hydration / production_store /
    safety_materials symbols. Composer, not engine.
  test_l1_rollback_contract_documented
    rollback_contract() returns machine-readable {l1, l2, off_failsafe} dict.

Focused CHEM regression                          114 / 114  PASS
  test_chem06_read_service + test_chem07_public_router +
  test_chem10_publish_promoter + test_chem_seo_preview_execute +
  test_chem_full_readiness + test_chem_full_readiness_002_cutover
```

## Governance

```text
PRODUCTION DB WRITE                  = 0
PUBLISHED_SEO_PREVIEW MUTATION       = 0  (C5 verifies)
PUBLISHED_FULL PRODUCTION MUTATION   = 0
PRODUCTION PUBLISH                   = 0
RAILWAY ENV CHANGE                   = 0
DEPLOY                               = 0
KOSHA API CALL                       = 0
HYDRATION RESUME                     = 0
CHEM-04 hydration                    = 0

SCHEMA CHANGE                        = 0
NEW MIGRATION                        = 0
NEW ENGINE                           = 0
NEW ROUTER                           = 0
NEW SCHEMA IDENTITY MODEL            = 0

TERMINOLOGY DICTIONARY CHANGE        = 0
KIWI CHANGE                          = 0
SEARCH REDESIGN                      = 0

CROSS-DOMAIN COUPLING                = 0
  (test_no_new_engine_or_terminology_change grep-verifies cutover.py
   imports no search / terminology / hydration / production_store /
   kosha_safety_materials symbols)
```

## Verdict

```text
WO-CHEM-FULL-READINESS-002 = PASS / READY FOR GPT DELTA VERIFY

Cutover contract, rollback contract, and C1..C8 rehearsal are
fixture-verified. Execution machinery for the actual FULL cutover
is already present in the repo (routers/kosha_public_msds.py env
handling, publish.preflight_publish, is_full_ready composer, MemoryPublishStore
and SupabasePublishStore). Owner-approved execution WOs plug into
these seams without further re-design.

NEXT  =  GPT delta-only verify
         → P3 search / terminology acceptance
         → P4 ops observability
         → P5 full acceptance harness
         → CHEM-04 hydration continues in Track H (unblocking nothing here)
STOP
```
