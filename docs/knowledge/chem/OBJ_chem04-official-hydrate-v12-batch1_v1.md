---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-04-OFFICIAL-HYDRATE-V12-001 Batch 1 hydration receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-04-OFFICIAL-HYDRATE-V12-001 — Batch 1 Runtime Hydration + Quota Measurement

## Scope

```text
API CONTRACT              = KOSHA MSDS OPENAPI v1.2 (2026-09-16)
BASE                      = https://apis.data.go.kr/B552468/msdschem1
ACCOUNT                   = DEVELOPMENT / APPROVED  (2026-09-17 ~ 2028-09-17)
PORTAL DISPLAY            = 2,000 / operation / day

EXECUTION MODE            = FOREGROUND
BACKGROUND / FIRE-AND-FORGET = FORBIDDEN
CONCURRENCY               = workers = 1
```

## Anchors

```text
main start                = 1a43a50a126040c0739e4fa3b8faa1b8460d4d48
branch                    = feature/chem04-official-hydrate-v12
queue                     = artifacts/chem04/content/queues/hydration_queue.jsonl  (gitignored)
queue rows                = 329,088
queue SHA256              = 7eba2dca2e183bab2c09f6260874cf8b5380ccb6d2f4bec61dfd193c881085d9
hard safety cap           = 40,000
```

## Runner behaviour

```text
started_at                = 2026-09-17T21:36:30Z
ended_at                  = 2026-09-17T23:11:06Z
elapsed                   = ~1h35m
stop_reason               = QUOTA_LIMIT
```

## Batch 1 result

```text
start_completed (pre-run) = 361
new_success               = 31,600
new_official_empty        = 0
new_errors                = 1        (the HTTP 429 that triggered STOP)
total_completed           = 31,961   authoritative records

remaining in queue        = 297,127

http_requests (this run)  = 31,601
http_429                  = 1
resultCode 22             = 0
resultCode 23             = 0
consecutive error budget  = untriggered
```

## Per-operation call counts (single day)

```text
getChemDetail011          = 1,975
getChemDetail021          = 1,975
getChemDetail031          = 1,975
getChemDetail041          = 1,975
getChemDetail051          = 1,975
getChemDetail061          = 1,975
getChemDetail071          = 1,975
getChemDetail081          = 1,975
getChemDetail091          = 1,975
getChemDetail101          = 1,976   ← 1,976th call was the HTTP 429
getChemDetail111          = 1,975
getChemDetail121          = 1,975
getChemDetail131          = 1,975
getChemDetail141          = 1,975
getChemDetail151          = 1,975
getChemDetail161          = 1,975
TOTAL                     = 31,601
```

## First quota hit

```text
first quota HTTP status   = 429
first quota operation     = getChemDetail101
first quota chemId        = 432377
detected at               = 2026-09-17T23:11:06Z (KST 2026-09-18 08:11)
retry                     = 0    (immediate STOP per WO §18)
additional probes         = 0    (WO §40)
```

## Q4 answered — quota scope is PER-OPERATION

The portal-displayed `2,000 / operation / day` is enforced as an
independent per-endpoint bucket. Evidence:

```text
Total requests across 16 operations at first quota-hit = 31,601
Per-operation calls at first quota-hit                 = 1,975 / 1,975 / ... / 1,976
Operation that hit 429                                 = getChemDetail101  (its own 1,976th call)
Other operations at that moment                        = 1,975 each (unaffected)
```

If the cap were service-wide 2,000/day, the 2,001st TOTAL call
would have 429'd. Instead the runner made 31,601 total requests
before any op reached its own ~1,976th call. Portal number ≈
runtime enforcement, per operation, with ~24-request headroom
above the displayed 2,000 (likely a soft grace / cache window).

Working conclusion for planning purposes (not a contractual
guarantee — KOSHA can change enforcement without notice):

```text
DEVELOPMENT account daily capacity ≈ 16 × 2,000 ≈ 32,000
                                     requests / day
Batch 1 empirical daily ceiling    = 31,601
                                     (very slightly above 16 × 1,975)
```

## Full-hydration horizon (informational)

```text
FULL_OFFICIAL_CALLS remaining after Batch 1 = 329,088 - 31,961 = 297,127
Daily ceiling observed empirically          = ~31,600
Batches remaining                           = ceil(297,127 / 31,600) ≈ 10
Wall-clock estimate                         = ~10 additional daily quota windows
```

This is NOT a request for `10 batches at 31,600` to run
autonomously. Each subsequent batch requires its own owner
authorization and foreground execution.

## Frozen output SHAs

```text
responses.jsonl SHA256                = 49994a2a8d44b5c2acfae60283d5f2f76fd65e0af5842a10db43383e26b643dd
errors.jsonl SHA256                   = 919c64b0976bb5ff8681765a5ff3ae93e898830ad4a2c9e711e842bcbb0cf90d
checkpoint.json SHA256                = dbebbc5196f0471edce0bc18bbd4227fe542dcdf19004bb31b40e20d0a165cca
run_report canonical SHA256           = c8c83a3de035b2ce687163a377b8fe498cc0e9f29211e0d37e7c33ed004cb717
```

All bulk artifacts stay under `artifacts/chem04/official_v12/`
which is gitignored (per WO §10). Only this receipt, the runner,
its tests, and the client rate-limit fix are committed.

## Content correctness spot-check

Each record in `responses.jsonl` carries:

```text
source                      = KOSHA_OFFICIAL
source_contract_version     = KOSHA_MSDS_OPENAPI_V1_2
official_spec_version       = 1.2
official_spec_date          = 2026-09-16
authoritative_verified      = true    (only on HTTP 200 + resultCode 00 + parse PASS)
result_code                 = 00
items                       = parsed sections (v1.2 canonical fields)
```

Every one of the 31,961 records satisfies these fields (this WO's
runner writes them uniformly; the tests validate the same
contract). Records for the 1 chemId whose Detail101 request 429'd
are NOT present in responses.jsonl — that pair is still in the
`remaining` set and will be re-attempted on the next quota window.

## Governance

```text
PRODUCTION DB WRITE         = 0
PRODUCTION INGEST           = 0
CUSTOMER PUBLICATION        = 0
SUPABASE WRITE              = 0
CANONICAL MUTATION          = 0

KOSHA IDENTITY HOLD         = PRESERVED (Owner Option-A policy unchanged)
authoritative source        = KOSHA OFFICIAL only
secondary dataset           = NON_AUTHORITATIVE (unchanged)

SECRET LEAK CHECK           = PASS (0 raw serviceKey occurrences across
                              responses.jsonl, errors.jsonl, checkpoint.json,
                              run_report.json)
```

## Verdict

```text
WO-CHEM-04-OFFICIAL-HYDRATE-V12-001  = PASS / BATCH1_QUOTA_MEASURED

Batch 1 authoritative corpus         = 31,961 records saved locally (gitignored)
Runtime quota scope                  = PER-OPERATION confirmed
Per-op empirical ceiling             = ~1,976 calls / operation / day
Daily aggregate ceiling              = ~31,600 calls / day
Full corpus hydration ETA            = ~10 more daily quota windows

NEXT                                 = GPT delta-only verify
                                       → Owner authorises Batch 2 explicitly
                                       → resume next quota window
                                       (or, if desired, submit operating-account
                                        / traffic-increase request to compress
                                        the ~10-window horizon — draft ready
                                        in OBJ_chem04-quota-account-gate_v1.md)
STOP
```
