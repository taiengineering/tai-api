---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-07-MSDS-PUBLIC-ROUTER-001 dormant router receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-07-MSDS-PUBLIC-ROUTER-001 — Dormant KOSHA MSDS Public Router

## Summary

Public HTTP router for the KOSHA MSDS catalog. Code is complete and
test-validated, but the router is **NOT registered** in
`router_registry/public.py` — verified by
`test_18_router_not_registered_in_public_registry`. Nothing serves
from this route in production until a future owner-approved
activation WO.

```text
IMPLEMENT     = YES
REGISTER      = NO
DEPLOY EXPOSE = NO
PUBLISH       = NO
```

## Anchors

```text
main at run          = 063b05b6254a40a828cef5c6140d79b16d55a1e2
branch               = feature/chem07-msds-public-router
```

## Endpoints (dormant)

```text
GET /public/kosha/msds
    query params:
      chem_id, cas_no, ke_no, en_no, un_no, name_ko, name_en,
      limit  (1..MAX_LIMIT=100)
      offset (>=0)
    zero filters → CHEM-06 list_current  (ORDER BY chem_id ASC)
    any filter   → CHEM-06 search

GET /public/kosha/msds/{chem_id}
    → CHEM-06 get_by_chem_id(..., include_sections=True)
    → 404 MSDS_CHEMICAL_NOT_FOUND if not in current view

GET /public/kosha/msds/{chem_id}/sections/{section_no}
    section_no validated by FastAPI Path(ge=1, le=16) → 422 on out-of-range
    → CHEM-06 get_section
    → 404 MSDS_SECTION_NOT_FOUND if current chemical exists but section absent
    → 404 MSDS_SECTION_NOT_FOUND if chemical is not current
```

## Delegation

The router only calls CHEM-06 service functions. It never issues raw
Supabase table access, never runs SQL, never mutates. Verified by
`test_17_router_delegates_to_chem06_service_no_direct_bypass`, which
scans the router source for forbidden tokens:

```text
.table(   .insert(   .update(   .delete(   .upsert(   .rpc(
execute_sql   SELECT   INSERT   UPDATE   DELETE
```

None present.

## Store injection

Follows the repo's existing lazy-singleton pattern
(`routers/kosha_public_materials.py`):

```text
_store = None
def get_store():
    global _store
    if _store is None:
        _store = SupabaseMsdsReadStore()
    return _store
```

Tests monkey-patch `get_store()` to return a `MemoryMsdsReadStore`
so the test suite makes zero network I/O.

## Response contract

Reuses CHEM-06 shape verbatim — router does not re-shape, re-hash,
or re-classify:

```text
list / search envelope:
  { items: [...], total: int, limit: int, offset: int }

detail envelope:
  chem_id, content_id, identity_status,
  chemical_name_ko, chemical_name_en,
  cas_no, ke_no, en_no, un_no,
  last_date,
  provenance = { source_id, source_key, source_content_hash,
                 source_dataset_url, snapshot_id },
  sections   = [ { section_no, payload_json, section_hash,
                   result_code, fetched_at }, ... ]
```

Raw DB PKs (`chemicals.id`, `sections.id`, `sections.chemical_id`)
never leak — verified by `test_15_internal_pk_not_exposed`.

## Cross-domain isolation

```text
services/kosha_safety_materials      NOT imported (test_16)
router_registry/public.py            NOT modified (test_18)
supabase/migrations/                 NOT modified
tools/chem04/, tools/chem05/         NOT modified
services/kosha_msds/materialize.py   NOT modified
services/kosha_msds/read.py          NOT modified (delegation only)
```

## Tests

```text
tests/test_chem07_public_router.py    20 / 20  PASS  (0.54s)

  §24 items 1..18 individually covered:
    01 GET list → 200
    02 empty list → 200 + items=[]
    03 list pagination passthrough
    04 chem_id exact filter
    05 CAS filter
    06 Korean name filter
    07 English name filter
    08 detail found → 200
    09 detail non-current → 404
    10 detail includes 16 sections
    11 section found → 200
    12 section for non-current chem → 404
    13 section 0 → 422 (FastAPI Path validation)
    14 section 17 → 422
    15 internal DB PK not exposed
    16 no kosha_safety_materials import
    17 router uses CHEM-06 service, no direct table access
    18 router NOT registered in public registry

  Extra:
    19 OpenAPI shows the 3 dormant paths under /public/kosha/msds;
       /public/kosha/materials domain is NOT present in this isolated app
    20 module-import parity: importing routers.kosha_public_msds does not
       run any startup, and router.prefix == /public/kosha/msds

Focused CHEM-05/06/07 regression      54 / 54  PASS
```

## Activation prerequisites

Every one of these must be true before an activation WO adds
`{"module": "routers.kosha_public_msds"}` to `router_registry/public.py`:

```text
CHEM-04 hydration                    329,088 authoritative sections on disk
production materialize               COMPLETED via a future WO with owner approval
kosha_msds_snapshot.status           COMPLETED
kosha_msds_snapshot.enumeration_mode FULL_OFFICIAL
kosha_msds_snapshot.publish_state    PUBLISHED_FULL
owner activation approval            explicit
```

Nothing below that bar is reachable from customers today.

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
DIRECT DB QUERY IN ROUTER   = 0
```

## Verdict

```text
WO-CHEM-07-MSDS-PUBLIC-ROUTER-001  = PASS / DORMANT_ROUTER_READY

Router is code-complete, test-validated, and dormant. Registration
and activation require a separate future WO. Nothing customer-facing
changes as a result of this PR.

NEXT  =  GPT delta-only verify
         → CHEM-04 hydration remains armed / hold (Owner trigger after
           2026-09-19 09:30 KST)
         → CHEM-07 activation WO gated on the prerequisites above
STOP
```
