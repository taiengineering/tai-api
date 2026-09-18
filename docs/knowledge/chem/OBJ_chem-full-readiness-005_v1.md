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

---

## PATCH-1 — Final safety gates

Independent verify identified three blind spots + one unrealistic
fixture. PATCH-1 closes each without adding a new decision engine.

### A. Materialize baseline is now an actual gate (was defined but not used)

- `evaluate_full_acceptance` now auto-selects between `DEFAULT_PREVIEW_TO_FULL_BASELINE`
  (PRE) and the new `FULL_REPLAY_BASELINE` (POST) based on Stage D.
- Stage D runs *before* Stage C so its readiness picks the baseline:
  - no FULL candidate → PRE (1997 UNCHANGED / 18,571 NEW / 0 CHANGED; 31,952 UNCHANGED / 297,136 NEW / 0 CHANGED)
  - FULL candidate present → POST replay (20,568 UNCHANGED / 0 NEW / 0 CHANGED; 329,088 UNCHANGED / 0 NEW / 0 CHANGED)
- Stage C evidence now carries `baseline_source` so operators see which one applied.
- Any drift → BLOCKED / EXPECTED_BASELINE_DRIFT. Previously an ill-shaped classification could quietly reach READY_FOR_FULL_MATERIALIZE.

### B. CHEM-04 ↔ CHEM-05 binding is now actually verified

- Stage B calls `services.kosha_msds.materialize_writer.verify_manifest_binding()` — the canonical binding verifier. No new SHA logic.
- The CLI recomputes the plan file's SHA256 from disk and threads it through as `on_disk_plan_file_sha256`; hydration's `responses_sha256` flows through as `hydration_responses_sha256`.
- Any of {manifest.responses_sha256 ≠ hydration responses SHA, manifest.plan_semantic_sha256 ≠ report.plan_sha256, manifest.plan_file_sha256 ≠ recomputed} → BLOCKED / MANIFEST_BINDING_MISMATCH.

### C. Frozen queue is required once hydration completes

- Previously "queue file absent" silently skipped identity verification.
- Now: hydration in progress → still `WAIT_HYDRATION` (queue may still be materializing).
- Hydration complete + queue file absent or SHA/rows drift → BLOCKED / QUEUE_IDENTITY_MISMATCH.

### D. H14 fixture now models real production lifecycle

- Previously H14 mixed a preview-shaped materialize store with an already-materialized publish store — an impossible transient state (production has ONE Supabase DB).
- PATCH-1 §D: H14 now uses `_full_materialize_store()` (20,568 chemicals × 16 sections all UNCHANGED against the plan) together with `_valid_full_publish_store()`. The auto-selected baseline is POST replay, and the verdict resolves cleanly to READY_FOR_FULL_CUTOVER.

### E. Additional tests (H15..H20)

| Case | What it exercises | Expected |
|------|-------------------|----------|
| H15  | PRE baseline drift (one fewer UNCHANGED chemical) | BLOCKED / EXPECTED_BASELINE_DRIFT |
| H16  | POST-materialization replay (full mat store + full plan) | Stage C ready with all UNCHANGED |
| H17  | hydration responses SHA ≠ manifest.responses_sha256 | BLOCKED / MANIFEST_BINDING_MISMATCH |
| H18  | on-disk plan-file SHA ≠ manifest.plan_file_sha256 | BLOCKED / MANIFEST_BINDING_MISMATCH |
| H19  | FULL source complete but queue file missing | BLOCKED / QUEUE_IDENTITY_MISMATCH |
| H20  | current production (partial hydration) still yields | WAIT_HYDRATION with no block reasons |

### F. BLOCKED reason integrity

- A BLOCKED verdict can no longer be produced with an empty `overall_block_reasons`.
- New derived reasons:
  - `BLOCK_SEARCH_RUNTIME_NOT_READY` (fires when everything else is green but Stage F is not-ready → search-dictionary is offline / V1)
  - When hydration is complete and no plan is supplied, `BLOCK_NOT_FULL_PLAN` is surfaced at the fallback branch.
- Verdict vocabulary stays exactly four values: `WAIT_HYDRATION / BLOCKED / READY_FOR_FULL_MATERIALIZE / READY_FOR_FULL_CUTOVER`.

### Read-only invariant (unchanged)

    DB INSERT/UPDATE/DELETE = 0
    PUBLISH                  = 0
    ENV CHANGE               = 0
    DEPLOY                   = 0
    KOSHA API CALL           = 0
    CHEM-04 RESUME           = 0

### Anchors (PATCH-1)

```text
main at run   = f32e4a71a692865ff03ca5276b3d331a126547bf
branch        = feature/chem-full-readiness-005-acceptance-harness
old head      = f925b62347942223da46a8cf13b5e3ba3b0ece8f
tests         = 21/21 pass (was 15) — H15..H20 added, H14 rewritten
regression    = 287/287 CHEM tests pass
local CLI     = WAIT_HYDRATION (queue rows 329,088, SHA matches frozen)
```
