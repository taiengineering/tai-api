---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-06-MSDS-CANONICAL-READ-SERVICE-001 read service receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-06-MSDS-CANONICAL-READ-SERVICE-001 — KOSHA MSDS Canonical Read Service

## Summary

Internal, read-only MSDS canonical service. Reads from the existing
`public.kosha_msds_current` view (publish-gated) and, only for the
`last_date` column not projected by the view, from
`public.kosha_msds_chemicals` — always by the current view's own `id`,
so the publish gate is preserved.

No public router. No customer publication. No new schema, no new
engine, no new RPC, no new SQL function. No DB mutation.

## Scope

```text
READ SOURCE                = public.kosha_msds_current   (publish-gated view)
SECTION SOURCE             = public.kosha_msds_sections
SUPPLEMENTARY COLUMN SOURCE = public.kosha_msds_chemicals  (last_date only,
                                                            joined via id from
                                                            current view)
MODE                       = read-only service layer
CONSUMER                   = future router (CHEM-07); NOT this WO
```

## Anchors

```text
main at run             = e8184eaf548648e81dd990bbf2440110fa02a73e
branch                  = feature/chem06-msds-canonical-read-service
```

## Implementation

```text
services/kosha_msds/read.py         pure read service (MemoryMsdsReadStore
                                    + SupabaseMsdsReadStore, 4 operations)
tests/test_chem06_read_service.py   17 tests (§17 items 1..15 + 2 contract)
docs/knowledge/chem/
  OBJ_chem06-msds-canonical-read-service_v1.md   this receipt
```

Operations exposed (all keyword-only after positional inputs):

```text
get_by_chem_id(chem_id, *, store, include_sections=True)
    - returns full contract + 16 sections; None if chem_id not in
      the current view
get_section(chem_id, section_no, *, store)
    - validates section_no in 1..16 (SectionNoOutOfRange otherwise)
    - membership in current view is required BEFORE section is read
list_current(*, store, limit=20, offset=0)
    - deterministic ORDER BY chem_id ASC; caps limit at 100
search(*, store, chem_id, cas_no, ke_no, en_no, un_no, name_ko, name_en,
       limit=20, offset=0)
    - exact-match filters AND-ed with ilike name partial match; no ranking
```

Return contract (identity + provenance envelope):

```text
chem_id
content_id
identity_status
chemical_name_ko / chemical_name_en
cas_no / ke_no / en_no / un_no
last_date                          (fetched from kosha_msds_chemicals for
                                    a current-gated id; None on list/search
                                    to avoid N+1 queries)
provenance = {
    source_id, source_key, source_content_hash,
    source_dataset_url, snapshot_id
}
sections = [                        (only on get_by_chem_id when include_sections=True)
    { section_no, payload_json, section_hash, result_code, fetched_at }
]
```

Raw DB PKs (`chemicals.id`, `sections.id`) are NOT exposed in the
contract. `content_id` is the only globally-unique identifier surfaced.

## Reused existing helpers (no fork)

```text
services/kosha_msds/contract.py   ALLOWED_SECTIONS, SECTION_MIN, SECTION_MAX
services/kosha_msds/               (identity, parse, hash — read service
                                    does not touch these; contract-only)
```

Two stores match the repo's existing pattern
(services/kosha_safety_materials/display.py — same shape, different
domain):

```text
MemoryMsdsReadStore                in-memory replica for tests
SupabaseMsdsReadStore              production SELECT-only client
                                   (chains .table().select().eq()/ilike().
                                    order().range().execute() — no
                                    .insert/.update/.delete/.upsert/.rpc)
```

## Cross-domain isolation

```text
services/kosha_safety_materials    NOT imported (verified by test_14)
routers/                           NOT modified in this PR
supabase/migrations/               NOT modified in this PR
tools/chem04/, tools/chem05/       NOT modified in this PR
```

`test_15_no_db_mutation_methods_on_stores` verifies neither store
exposes `insert / update / delete / upsert / rpc / execute_sql`.

## Tests

```text
tests/test_chem06_read_service.py    17 / 17  PASS   (0.07s)

  01  get_by_chem_id current record         PASS
  02  non-current chemical NOT_FOUND        PASS
  03  list_current empty envelope           PASS
  04  deterministic chem_id ordering        PASS
  05  pagination limit/offset (+ clamping)  PASS
  06  exact chem_id search                  PASS
  07  exact CAS search                      PASS
  08  Korean name partial search            PASS
  09  English name partial search (ci)      PASS
  10  section 1..16 allowed                 PASS
  11  section 0/17/negative rejected        PASS
  12  non-current chemical section hidden   PASS
  13  section payload returned correctly    PASS
  14  no kosha_safety_materials import      PASS
  15  no DB mutation methods on stores      PASS

  16  list omits sections; get_by_id has    PASS
  17  provenance envelope shape stable       PASS
```

Regression check (CHEM/KOSHA surface, no wider run):

```text
tests/test_chem06_read_service.py             17
tests/test_chem05_materialize.py              17
tests/test_chem04_official_hydrate_v12.py     …
tests/test_kosha_msds_bootstrap.py            …
tests/test_kosha_msds_catalog.py              …
tests/test_kosha_msds_discovery.py            …
tests/test_chem04_bootstrap_decision.py       …
tests/test_chem04_content_audit.py            …
tests/test_chem04_cli.py                      …
tests/test_chem04_live_sample.py              …
----------------------------------------
Total                                        203 / 203  PASS
```

## Publish-gate behavior

The service ONLY reads via `kosha_msds_current`, whose SQL definition
(supabase/migrations/20260914_kosha_msds_catalog.sql:169-202) requires

```text
snapshot.status            == COMPLETED
snapshot.enumeration_mode  == FULL_OFFICIAL
snapshot.publish_state     == PUBLISHED_FULL
```

Until a `PUBLISHED_FULL` snapshot exists in production, the view
returns zero rows and every operation returns an empty envelope /
None. This is verified in `test_03_list_current_empty_returns_empty_envelope`.

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

PUBLIC ROUTER               = 0   (CHEM-07 will add this)
CROSS-DOMAIN COUPLING       = 0
```

## Verdict

```text
WO-CHEM-06-MSDS-CANONICAL-READ-SERVICE-001  = PASS / READ_SERVICE_READY

Service is code-complete and test-validated. Zero live consumers
until CHEM-07 wires the router. Zero rows returned in production
until a PUBLISHED_FULL snapshot exists (CHEM-04 hydration + a
future materialize + publish WO).

NEXT  =  GPT delta-only verify
         → CHEM-07 (public router / API contract) — separate future WO
         → CHEM-04 hydration remains armed / hold pending quota reset
STOP
```
