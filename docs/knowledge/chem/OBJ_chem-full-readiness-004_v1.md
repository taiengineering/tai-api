---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-FULL-READINESS-004 receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-FULL-READINESS-004 — MSDS Operations Observability

## Summary

Read-only operator status collector + CLI that composes existing
CHEM stack surfaces into a single JSON report. No new engine, no
new schema, no production mutation. Absorbs P3's deferred live
dictionary binding check as the first observability gate.

```text
IMPLEMENT     = YES (composer + CLI)
FIXTURE TEST  = YES (O1..O8 + CLI smoke)
DB MUTATION   = 0
LIVE PUBLISH  = 0
DEPLOY        = 0
NEW ENGINE    = 0
```

## Anchors

```text
main at run                = 977718bc1d10f63f9586079ba47c9d1b69280cd1
branch                     = feature/chem-full-readiness-004-ops-observability
```

## Files (4)

```text
services/kosha_msds/ops.py                             NEW  (~430 lines)
  ExistingState-style dataclasses:
    HydrationStatus, ProductionStatus, PublicationStatus,
    PublicRuntimeStatus, DictionaryRuntimeStatus, FullReadinessStatus
  collect_hydration_status()   reads CHEM-04 artifact
                                (checkpoint.json / run_report.json / responses.jsonl)
  collect_production_status()  reads via publish_store / read_store
                                (Supabase-backed in production, Memory* in tests)
  collect_publication_status() reads latest published snapshots per scope
  collect_public_runtime()     reads KOSHA_MSDS_PUBLIC_MODE env var only
  collect_dictionary_runtime() live GET /search-dict/{health,census,lookup}
                                (injectable http_get; UNVERIFIED_NETWORK on any error)
  collect_full_readiness()     delegates to
                                services.kosha_msds.cutover.is_full_ready
  derive_alerts()              simple rules over collected values
  collect_status()             top-level orchestrator returning a single dict

tools/chem_ops/__init__.py                             NEW
tools/chem_ops/status.py                               NEW  (CLI wrapper)
  --artifact-dir  --live-base-url  --no-db  --no-deep-scan  --format
  Always exits 0 (status tool, not health check). Alerts surfaced in payload.

tests/test_chem_full_readiness_004_ops.py              NEW  (12 tests)
docs/knowledge/chem/OBJ_chem-full-readiness-004_v1.md  NEW  (this receipt)
```

## Output shape

```text
{
  "repository":      { git_main, runner_version, contract_version },
  "hydration":       { status, queue_total=329088, completed, remaining,
                        unique_chemicals, complete_chemicals,
                        incomplete_chemicals, next_pending_chem_id,
                        next_pending_section, last_terminal_reason,
                        last_run_at, responses_sha256 },
  "production_db":   { chemicals, sections, snapshots, snapshot_items,
                        preview_current, full_current,
                        latest_completed_snapshot, latest_preview_snapshot,
                        latest_full_snapshot, running_snapshots,
                        failed_snapshots },
  "publication":     { latest_preview_snapshot, latest_full_snapshot,
                        preview_count, full_count },
  "public_runtime":  { raw_env_value, resolved_mode, effective_scope,
                        is_failsafe_off },
  "search_dictionary": { runtime_snapshot, subjects, indexed_terms,
                          chem_term_msds_matched, chem_term_sds_matched,
                          binding, error },
  "full_readiness":  { ready, reason, snapshot_id, details },
  "alerts":          [ { code, severity, evidence }, ... ]
}
```

## Reused existing surfaces (no forks)

```text
services.kosha_msds.contract         PUBLIC_MODE_* constants,
                                     PUBLISH_* constants,
                                     SNAPSHOT_* constants,
                                     ENUMERATION_FULL_OFFICIAL
services.kosha_msds.cutover.is_full_ready
                                     canonical FULL readiness gate (P2)
services.kosha_msds.publish.MemoryPublishStore
                                     read side (latest_published_snapshot,
                                     _snapshots / _items / _sections peek)
services.kosha_msds.read.MemoryMsdsReadStore
                                     read side (_current / _preview peek)
services.kosha_msds.production_store.SupabasePublishStore /
services.kosha_msds.read.SupabaseMsdsReadStore
                                     production adapters (CLI --no-db skips them)
CHEM-04 artifact (checkpoint.json / run_report.json / responses.jsonl)
                                     hydration progress read-only source
tools/search_dict/lookup / health / census (via urllib GET on --live-base-url)
                                     P3-deferred live dictionary binding gate
```

## Alerts vocabulary

```text
HYDRATION_ARTIFACT_MISSING            INFO
RUNNING_SNAPSHOT_STALE                WARN
FAILED_SNAPSHOT_PRESENT               WARN
PUBLIC_MODE_FAILSAFE_OFF              WARN
FULL_MODE_WITHOUT_FULL_PUBLICATION    CRIT
DICTIONARY_RUNTIME_NOT_V2             WARN
```

## Tests

```text
tests/test_chem_full_readiness_004_ops.py    12 / 12  PASS  (0.17s)

  O1  preview production counts (1997 / 31952) reported
  O2  hydration status from artifact
       31961 / 297127; last_terminal_reason=QUOTA_LIMIT;
       next_pending = 432377 / 10; deep-scan complete=3 incomplete=1;
       responses SHA byte-verified
  O2b artifact_dir missing → status=ARTIFACT_NOT_AVAILABLE +
       HYDRATION_ARTIFACT_MISSING alert
  O3  FULL_READY=false / reason=NO_FULL_CANDIDATE
       (preview snapshot exists but no COMPLETED/FULL_OFFICIAL/
        NOT_PUBLISHED candidate)
  O4  live dictionary v2 match → V2_MATCH; MSDS + SDS matched
  O5  live dictionary v1 or other → V1_OR_OTHER;
       DICTIONARY_RUNTIME_NOT_V2 alert
  O6  live HTTP unavailable → UNVERIFIED_NETWORK; CLI still exits 0
       (both ConnectionError and missing --live-base-url paths)
  O7  unknown public mode → resolved_mode=off + PUBLIC_MODE_FAILSAFE_OFF alert
  O7b public mode=full without PUBLISHED_FULL snapshot →
       CRIT alert FULL_MODE_WITHOUT_FULL_PUBLICATION
  O8  read-only invariant: no write / promote / insert / update call
       reaches the store during status collection
       (verified via _NoMutationPublishStore that pytest.fails on any
        mutation method invocation)

  Extra:
    test_cli_smoke_no_db_no_live_url — CLI runs cleanly with --no-db
      and no --live-base-url; JSON output parses; binding =
      UNVERIFIED_NETWORK
    test_no_new_engine_no_kosha_safety_materials_coupling — ops.py
      imports no engine, no safety-materials, no hydration runner
      (grep-verified on import statements, not docstring mentions)

Focused CHEM regression                     258 / 258  PASS
  chem05 + chem06 + chem07 + chem08 + chem09 + chem10
  + chem_seo_preview + chem_seo_preview_execute
  + chem_full_readiness + chem_full_readiness_002_cutover
  + chem_full_readiness_003_search_qa + chem_full_readiness_004_ops
```

## Governance

```text
PRODUCTION DB WRITE               = 0    (O8 verifies)
PUBLISH                           = 0
RAILWAY ENV CHANGE                = 0
DEPLOY                            = 0
KOSHA API CALL                    = 0

SCHEMA CHANGE                     = 0
NEW MIGRATION                     = 0
NEW ENGINE                        = 0
NEW ROUTER                        = 0
NEW LLM DEPENDENCY                = 0
NEW ALERT FRAMEWORK               = 0    (rules are simple derivations
                                          over canonical values)

CROSS-DOMAIN COUPLING             = 0    (grep-verified imports)
CHEM-04 hydration                 = 0    (artifact read-only)
DICTIONARY REMAPPING              = 0
```

## What this WO does NOT do

- No admin UI. The CLI is the operator surface; a future WO can wrap
  it into an admin route by consuming the same JSON.
- No new DB table, no migration, no dictionary remapping.
- No live acceptance of the search adapter's cross-domain behavior
  against the actual production dictionary — the P3 deferred item
  is now readable via `search_dictionary.binding` when Owner runs
  the CLI with `--live-base-url` against production; the reading is
  not automated in CI.

## Verdict

```text
WO-CHEM-FULL-READINESS-004 = PASS / READY FOR GPT DELTA VERIFY

Operators can now run:

  railway run --service tai-api-prod \\
    python3 -m tools.chem_ops.status \\
    --artifact-dir artifacts/chem04/official_v12 \\
    --live-base-url https://api.taieng.co.kr

and get a single JSON that answers:
  - is hydration progressing?
  - what's live in production DB?
  - which snapshots are published?
  - what public mode is the router in?
  - is /search-dict actually bound to v2?
  - is a FULL cutover eligible?
  - what needs owner attention?

NEXT  =  GPT delta-only verify
         → P5 full acceptance harness
         → CHEM-04 hydration continues in Track H
STOP
```
