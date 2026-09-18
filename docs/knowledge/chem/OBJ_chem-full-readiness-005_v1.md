---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-FULL-READINESS-005 receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-FULL-READINESS-005 — FULL Acceptance Harness

## Summary

Single canonical read-only harness that composes hydration → plan →
materialize dry-run → materialized-full → publish → search-runtime →
public-cutover into one verdict. No new decision engine — every stage
delegates to an existing collector:

    Stage A  SOURCE_READY              ops.collect_hydration_status  (P4)
                                       + frozen-queue SHA256 identity gate
    Stage B  FULL_PLAN_READY           MaterializePlanInputs / CHEM-05
                                       execute_block_reasons translation
    Stage C  MATERIALIZE_READY         materialize_writer.preload_existing_state
                                       + classify_chemicals + classify_sections
                                       (CHEM-08, dry-run only)
    Stage D  MATERIALIZED_FULL_READY   publish_store.find_full_candidate
                                       (P4 store contract)
    Stage E  PUBLISH_READY             cutover.is_full_ready (P2 / CHEM-10)
    Stage F  SEARCH_RUNTIME_READY      ops.collect_dictionary_runtime  (P4)
    Stage G  PUBLIC_CUTOVER_READY      A + B + C + D + E + F +
                                       public_mode == seo_preview

Verdict vocabulary (WO §14) — exactly four outcomes:

    WAIT_HYDRATION              source not yet complete, no integrity failure
    BLOCKED                     any integrity failure (queue mismatch,
                                CONFLICT rows, identity regeneration,
                                baseline drift, running-snapshot hold, etc.)
    READY_FOR_FULL_MATERIALIZE  A + B + C ready, D not yet materialized
    READY_FOR_FULL_CUTOVER      A..F all ready + public_mode = seo_preview

```text
IMPLEMENT     = YES (composer + CLI)
FIXTURE TEST  = YES (H1..H14 + running-snapshot hold)
DB MUTATION   = 0
LIVE PUBLISH  = 0
DEPLOY        = 0
NEW ENGINE    = 0
```

## Anchors

```text
main at run                = f32e4a71a692865ff03ca5276b3d331a126547bf
branch                     = feature/chem-full-readiness-005-acceptance-harness
frozen queue sha256        = 7eba2dca2e183bab2c09f6260874cf8b5380ccb6d2f4bec61dfd193c881085d9
frozen queue rows          = 329,088
expected chemical count    = 20,568
expected section count     = 329,088
```

## Files (3)

```text
services/kosha_msds/full_acceptance.py                 NEW  (~470 lines)
  Verdict constants:
    VERDICT_WAIT_HYDRATION / VERDICT_BLOCKED /
    VERDICT_READY_FOR_FULL_MATERIALIZE / VERDICT_READY_FOR_FULL_CUTOVER
  Block reasons (WO §14):
    QUEUE_IDENTITY_MISMATCH / DUPLICATE_SOURCE_PAIR /
    SOURCE_CONTRACT_FAILURE / NOT_FULL_PLAN / CHEMICAL_CONFLICT /
    SECTION_CONFLICT / IDENTITY_REGENERATION /
    EXPECTED_BASELINE_DRIFT / RUNNING_SNAPSHOT_HOLD
  Dataclasses:
    StageReport(name, ready, block_reasons, evidence)
    AcceptanceReport(verdict, stages, overall_block_reasons)
    MaterializeExpectedBaseline
    DEFAULT_PREVIEW_TO_FULL_BASELINE = (1997/18571/0 chemicals,
                                         31952/297136/0 sections)
  Stage evaluators (A..F) + evaluate_full_acceptance orchestrator.

tools/chem_full_acceptance/__init__.py                 NEW
tools/chem_full_acceptance/check.py                    NEW  (CLI wrapper)
  --artifact-dir  --queue  --plan-dir  --live-base-url
  --no-db  --no-deep-scan  --format
  Always exits 0 (evidence tool, not health check).

tests/test_chem_full_readiness_005_acceptance.py       NEW  (H1..H14 + H14b)
```

## Verdict on current production state (2026-09-18)

Running the harness against the frozen artifact directory with a
memory publish/materialize placeholder:

    railway run --service tai-api-prod python3 -m tools.chem_full_acceptance.check \
        --artifact-dir artifacts/chem04/official_v12 \
        --queue     artifacts/chem04/content/queues/hydration_queue.jsonl

    verdict = WAIT_HYDRATION
    overall_block_reasons = []
    source.evidence.completed = 31,961
    source.evidence.remaining = 297,127
    source.evidence.queue_sha256 = 7eba2dca…5d9 (matches frozen)
    source.evidence.queue_rows = 329,088   (matches frozen)

Matches the expected H1 outcome. No integrity gate fires; the harness
correctly reports "not yet complete" rather than any BLOCK reason.

## H-case matrix

| Case | Fixture shape                              | Expected verdict / stage |
|------|--------------------------------------------|--------------------------|
| H1   | partial hydration (~10% completed)         | WAIT_HYDRATION           |
| H2   | source short by exactly 1                  | WAIT_HYDRATION           |
| H3   | plan with `execute_block_reasons=[DUPLICATE_PAIRS]` | BLOCKED / DUPLICATE_SOURCE_PAIR |
| H4   | full source, no plan                       | source stage ready       |
| H5   | preview-shaped plan (PREVIEW_CHEMS rows)   | BLOCKED / NOT_FULL_PLAN  |
| H6   | full plan exact                            | plan stage ready         |
| H7   | preview→FULL dry-run                       | UNCHANGED=preview,       |
|      |                                            | NEW=(full-preview),      |
|      |                                            | CONFLICT=0 both levels   |
| H8   | UNCHANGED row with no db_chemical_id       | BLOCKED / IDENTITY_REGENERATION |
| H9   | DB chem_id disagrees with plan chem_id     | BLOCKED / CHEMICAL_CONFLICT |
| H10  | full plan ready, no FULL candidate         | READY_FOR_FULL_MATERIALIZE |
| H11  | FULL_OFFICIAL / NOT_PUBLISHED candidate    | publish stage ready      |
| H12  | search-dict UNVERIFIED_NETWORK (503)       | search_runtime not-ready |
| H13  | search-dict V2_MATCH + msds True           | search_runtime ready     |
| H14  | everything green + mode=seo_preview        | READY_FOR_FULL_CUTOVER   |
| H14b | H14 + running_snapshots=1                  | BLOCKED / RUNNING_SNAPSHOT_HOLD |

Tests use monkeypatched size baselines (20 chemicals / 320 sections in
lieu of 20,568 / 329,088) to keep fixture assembly cheap. The harness
logic itself is size-independent.

## Read-only invariant

The harness never writes to the store. Every call site is one of:

- `preload_existing_state` (read-only bulk fetch)
- `classify_chemicals` / `classify_sections` (pure functions)
- `find_full_candidate` (read-only census)
- `preflight_publish` (read-only preflight, no promote)

Three-gate write protections downstream stay in place:
`assert_can_execute_production_write` in `materialize_writer.py` still
requires all three of (write path enabled, owner approval, WO scope
allows write) before any actual mutation runs — the harness never
opens that path.

## Follow-up (not in this WO)

- CHEM-04 Batch 3 hydration: still 297,127 records remaining. Live
  quota-limited. This harness will flip to READY_FOR_FULL_MATERIALIZE
  as soon as those two facts change (`completed == 329,088` AND
  `incomplete_chemicals == 0`).
- P6 execute WO — the actual FULL materialize + publish. Distinct
  Owner-approved WO; three-gate write path opens only under that WO.

## PR

    feature/chem-full-readiness-005-acceptance-harness → main
