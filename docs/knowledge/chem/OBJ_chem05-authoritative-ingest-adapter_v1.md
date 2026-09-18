---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-05-AUTHORITATIVE-INGEST-ADAPTER-001 adapter receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-05-AUTHORITATIVE-INGEST-ADAPTER-001 — KOSHA Official MSDS → Canonical DB Materialize Adapter

## Summary

Adapter code + tests + local-terminal dry-run PASS. No production DB
mutation, no KOSHA API call, no publication, no hydration state change.
`execute_eligible = false` — intentionally — because the authoritative
KOSHA corpus is still being hydrated under CHEM-04.

```text
CHEM-05 adapter implementation is valid.
Current execution is intentionally blocked because
the authoritative corpus is incomplete.
This is an expected governance gate, not an implementation failure.
```

## Scope

```text
API CONTRACT             = KOSHA MSDS OPENAPI v1.2 (2026-09-16)
SCHEMA REUSE             = existing public.kosha_msds_* AS-IS
NEW MIGRATION            = 0
NEW ENGINE               = 0
IMPLEMENTATION           = adapter (materialize planner + dry-run CLI)
MATERIALIZE MODE         = CHUNKED (design fixed; not executed under this WO)
PROVENANCE FOLDING       = snapshot.metrics_json  (no new DB columns)
KEY INJECTION            = adapter is DB-idle; no service key used
```

## Anchors

```text
main at run              = 088e99dd362aebcc292832c9f7e3004dfeb7ac5c
branch                   = feature/chem05-authoritative-ingest-adapter
adapter version          = CHEM05_V1
```

## Phase A — implementation

New files (untracked prior to this receipt commit):

```text
services/kosha_msds/materialize.py                  pure logic; contract admission,
                                                     chemical aggregation, section
                                                     projection, hash binding,
                                                     completeness, execute
                                                     eligibility, PUBLISHED_FULL
                                                     guard
tools/chem05/__init__.py                            package marker
tools/chem05/build_materialize_plan.py              Phase-B planner CLI
tools/chem05/materialize_official_v12.py            --dry-run + fail-closed
                                                     --execute (never opens DB
                                                     under this WO)
tests/test_chem05_materialize.py                    15 required tests + 2 e2e
.gitignore                                          + artifacts/chem05/
```

Reused from existing services (no fork, no new hash algorithm):

```text
services/kosha_msds/identity.py     identity_status_for_chem_id,
                                    new_content_id (unused at plan time),
                                    CHEM_ID_WIDTH
services/kosha_msds/hash.py         section_hash, source_content_hash
services/kosha_msds/parse.py        canonical_section_items, normalize_optional
services/kosha_msds/contract.py     SOURCE_ID, SOURCE_CONTRACT_VERSION,
                                    OFFICIAL_SPEC_VERSION, OFFICIAL_SPEC_DATE,
                                    ALLOWED_SECTIONS, DATASET_URL, DETAIL_*,
                                    ENUMERATION_FULL_OFFICIAL,
                                    PUBLISH_NOT_PUBLISHED, SNAPSHOT_RUNNING
```

Provenance folding (WO §4, no new DB columns):

```text
official_spec_version   → snapshot.metrics_json.official_spec_version
official_spec_date      → snapshot.metrics_json.official_spec_date
authoritative_verified  → admission gate; failing records rejected
                          before entering the plan
ingest_batch_id         → kosha_msds_snapshots.id (per-run natural key)
adapter_version         → snapshot.metrics_json.adapter_version = "CHEM05_V1"
artifact_responses_sha  → snapshot.metrics_json.artifact_responses_sha256
```

Unit test results:

```text
tests/test_chem05_materialize.py    17/17 PASS  (0.10s)
  §33 items 1..15                    covered individually
  e2e_dry_run_writes_plan_manifest_report   PASS
  e2e_census_supplements_identity           PASS

Full CHEM/KOSHA surface (regression check)
  chem04 + chem05 + kosha_msds_*     186/186 PASS   (0 skips, 0 fails)
```

## Phase B — Owner local-terminal dry-run

Command executed by the Owner on their local terminal (Claude did not
re-run this):

```bash
python3 -m tools.chem05.materialize_official_v12 --dry-run \
  --responses artifacts/chem04/official_v12/responses.jsonl \
  --out-dir artifacts/chem05
```

Result (Owner-supplied; not re-verified by Claude):

```text
artifact_records         = 31,961
unique_pairs             = 31,961
unique_chemids           = 1,998
complete_chemicals       = 1,997
incomplete_chemicals     = 1
missing_sections         = 297,127
duplicate_pairs          = 0
source_contract_failures = 0
execute_eligible         = false
execute_block_reasons    = [INCOMPLETE_CHEMICALS,
                            FULL_OFFICIAL_CORPUS_INCOMPLETE]
```

Interpretation:

- 1,998 chemIds have at least one section on disk; 1,997 have all 16
  authoritative sections and are marked COMPLETE.
- The single INCOMPLETE chemId is expected: it is chemId=432377, whose
  section 10 request produced the Batch-1 terminal 429 and is still in
  the pending queue.
- 297,127 sections remain missing because CHEM-04 hydration has not
  finished (the daily quota window has not reset since Batch 1).
- 0 source-contract failures / 0 duplicates → the artifact is clean; the
  block is a corpus-completeness gate, not a data-integrity gate.

## Frozen SHAs (Phase B)

```text
responses.jsonl (raw)              = 49994a2a8d44b5c2acfae60283d5f2f76fd65e0af5842a10db43383e26b643dd
                                     (unchanged since Batch 1)
materialize_plan.jsonl (raw)       = 8c07b29001317e87722eed8b778d2f0b8fe032886eebc68d09bb79d7da706afe
plan (semantic)                    = 71035ce89a9b57804bb8f97bdd4e98089ad05c528d7cc9aa6d4e9aabb7e75492
manifest                           = a9c3cc572f8a5cdbb2b7cdddd64152713c58a17567aa09b29d9df67964e4c34d
```

The plan_file and plan_semantic SHAs are deterministic under identical
input (same input → same hash — proven by unit tests 07/08/09/12); the
manifest SHA embeds run timestamps and is intentionally non-deterministic
across runs. The plan_semantic SHA is the load-bearing determinism
guarantee for future re-runs.

## Progress equation

```text
total_completed  + remaining  = queue_rows
    31,961       +  297,127   =   329,088     PASS
```

Unchanged from CHEM-04 Batch-2 receipt; adapter did not touch the
hydration corpus.

## Execute gate architecture

Two independent, order-preserving gates block `--execute` from reaching
any DB code path:

```text
Gate 1  (data-shape)
  plan.execute_eligible must be true
    unique_chemids           == 20,568
    unique_pairs             == 329,088
    incomplete_chemicals     == 0
    duplicate_pairs          == 0
    source_contract_failures == 0

Gate 2  (WO-scope)
  This WO forbids production DB writes (§17, §27, §45)
  The CLI refuses to open any DB connection under this WO even when
  the operator sets --i-understand-full-corpus. Actual production
  materialize requires a separate future WO with explicit owner
  approval (WO §43-§44).
```

Unit test 11 (`test_11_execute_gate_blocks_before_db_mutation`) verifies
that `--execute` exits with rc=2 and never opens a DB connection, even
with the operator flag set.

## PUBLISHED_FULL guard

The adapter's `SnapshotCandidate.publish_state` is always
`NOT_PUBLISHED`. `assert_no_publish_full(snapshot)` raises `ValueError`
if any code path attempts to mutate it to `PUBLISHED_FULL`. Publication
is a separate future WO (WO §31).

## Governance

```text
PRODUCTION DB WRITE         = 0
PRODUCTION INGEST           = 0
SUPABASE WRITE              = 0
CANONICAL MUTATION          = 0
CUSTOMER PUBLICATION        = 0
KOSHA API CALL              = 0
HYDRATION RESUME            = 0
HYDRATION ARTIFACT MUTATION = 0
  (responses.jsonl SHA still 49994a2a…b643dd)

SCHEMA CHANGE               = 0  (no migration, no ALTER, no CREATE TABLE)
NEW ENGINE                  = 0  (adapter reuses existing kosha_msds/ helpers)
NEW HASH ALGORITHM          = 0

CROSS-DOMAIN COUPLING       = 0
  test_15 verifies services/kosha_safety_materials is NOT imported
  from any adapter module (that is a different KOSHA domain).

SECRET LEAK CHECK           = PASS
  the adapter has no KOSHA service key usage; the runner artifact
  it reads is already redacted (secret leak = 0 at CHEM-04 close).
```

## Verdict

```text
WO-CHEM-05-AUTHORITATIVE-INGEST-ADAPTER-001  = PASS / ADAPTER_READY

Phase A (Claude implementation)              = PASS
Phase B (Owner local-terminal dry-run)       = PASS
                                               (execute_eligible=false, expected)
Phase C (Claude receipt / commit / push / PR) = this receipt

Adapter is code-complete and dry-run-validated.
Execute path is fail-closed until:
  1. CHEM-04 hydration reaches 20,568 × 16 = 329,088 authoritative
     records, AND
  2. A separate future WO explicitly authorizes production materialize.

NEXT  =  GPT delta-only verify → owner-triggered future WO for
         production materialize once the KOSHA corpus is complete
         (owner may compress the quota horizon via the operating-account
         path preserved in OBJ_chem04-quota-account-gate_v1.md)

STOP
```
