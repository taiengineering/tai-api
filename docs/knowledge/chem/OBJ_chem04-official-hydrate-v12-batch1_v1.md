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

Both segments below are the same `tools/chem04/official_hydrate_v12.py`
runner (only code path that writes to `artifacts/chem04/official_v12/`).
The main segment resumed from the exact next queue row after the
pre-run's last completed pair (idempotent on `(chemId, sectionNo)`).

```text
pre-run segment (interrupted)
  started_at (UTC)        = 2026-09-17T21:28:17Z
  ended_at   (UTC)        = 2026-09-17T21:29:05Z
  started_at (KST)        = 2026-09-18 06:28:17+09:00
  ended_at   (KST)        = 2026-09-18 06:29:05+09:00
  records                 = 361
  last completed          = chemId=097377 / sectionNo=9

main segment (WO run)
  started_at (UTC)        = 2026-09-17T21:36:30Z
  ended_at   (UTC)        = 2026-09-17T23:11:06Z
  started_at (KST)        = 2026-09-18 06:36:30+09:00
  ended_at   (KST)        = 2026-09-18 08:11:06+09:00
  elapsed                 = ~1h34m35s
  first fetched pair      = chemId=097377 / sectionNo=10  (resume)
  stop_reason             = QUOTA_LIMIT
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

## Start-361 provenance

The 361 records the main run resumed from are NOT from Option-C
sampling and NOT from the v1.2 contract smoke. They come from a
prior, interrupted execution of the same
`official_hydrate_v12.py` runner in the same quota window:

```text
pre-run runner                 = tools/chem04/official_hydrate_v12.py
pre-run window (UTC)           = 2026-09-17T21:28:17Z → 21:29:05Z (48 seconds)
pre-run window (KST)           = 2026-09-18 06:28:17 → 06:29:05 +09:00
pre-run records                = 361
pre-run source (all 361)       = KOSHA_OFFICIAL
pre-run contract (all 361)     = KOSHA_MSDS_OPENAPI_V1_2
pre-run operations (all 361)   = v1.2 format (getChemDetail{01..16}1)
pre-run authoritative_verified = true (all 361)
pre-run last completed pair    = chemId=097377 / sectionNo=9
main-run first fetched pair    = chemId=097377 / sectionNo=10   (resume)
Option-C import into responses = 0  (no code path exists)
v1.2 smoke import into responses = 0  (no code path exists)
```

Only `tools/chem04/official_hydrate_v12.py` writes to
`artifacts/chem04/official_v12/responses.jsonl` (grep-verified);
`live_sample_compare.py` and `v12_contract_smoke.py` output to
different paths entirely. So the 361-corpus is authoritative
KOSHA-fetched hydration data, identical in provenance to the
31,600 new records of the main run.

Note: the runner emits a checkpoint every 200 completed rows. In
the pre-run this fired at row 200 (chemId=097364 / sectionNo=8);
that checkpoint is what earlier reports observed and quoted as
"HTTP requests = 200 / last completed = 097364 / 8". The pre-run
continued past the checkpoint and stopped at 361, not at 200.

## Per-operation call counts IN THIS RUN

These are PER-OPERATION CALLS IN THE MAIN RUN only — not a daily
ceiling. Batch 1 also included the 361-record pre-run segment
above, and v1.2 smoke calls also consumed some of the same quota
window. Treat the numbers below strictly as this main run's own
send counts.

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
getChemDetail101          = 1,976   ← 1,976th call in this run was the terminal HTTP 429
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
detected at (UTC)         = 2026-09-17T23:11:06Z
detected at (KST)         = 2026-09-18 08:11:06+09:00
retry                     = 0    (immediate STOP per WO §18)
additional probes         = 0    (WO §40)
```

## Q4 partial answer — what this run does and does not prove

This run does not prove the strict-independent-buckets model. It
rules out the service-wide model and is strongly consistent with
the portal's per-operation model, but the runner STOPPED
immediately on the first 429 (per WO §18) and did not probe other
operations after the quota-hit. So cross-endpoint availability
post-quota was not tested here.

```text
SERVICE-WIDE 2,000/day                     = REJECTED BY OBSERVATION
OBSERVED AGGREGATE BEFORE FIRST 429        = 31,601 requests in this run
PORTAL PER-OPERATION 2,000 MODEL           = STRONGLY CONSISTENT WITH OBSERVATION
INDEPENDENT PER-ENDPOINT BUCKETS           = NOT YET STRICTLY PROVEN
```

Direct evidence:

```text
Total requests across 16 operations at first quota-hit = 31,601
Per-operation calls IN THIS RUN at first quota-hit     = 1,975 / 1,975 / ... / 1,976
Operation that hit 429                                 = getChemDetail101
                                                         (its own 1,976th call IN THIS RUN)
Other operations at that moment                        = 1,975 calls IN THIS RUN each
                                                         (not re-probed post-429)
```

Why this is not proof of strict independence: a pooled ~32,000
service-wide bucket that happens to be sized ≈ 16 × 2,000 is
still logically consistent with observation, because we did not
attempt another operation after Detail101 429'd. Distinguishing
those two models requires an explicit probe of a different
operation immediately after a per-op 429, which WO §40 forbids
during Batch 1.

Also: 1,975 / 1,976 are PER-OPERATION CALLS IN THIS MAIN RUN —
not a daily ceiling. Batch 1 also includes the 361-record pre-run
segment (~22-23 calls per operation, same day, same runner), and
v1.2 smoke calls also count against that window. So these counts
cannot be subtracted from 2,000 to infer headroom.

Working ceiling for planning purposes (not a contractual guarantee
— KOSHA can change enforcement without notice):

```text
EXACT DAILY PER-OP CEILING                 = NOT ISOLATED BY THIS RUN
PORTAL DISPLAY                             = 2,000 / operation / day
OBSERVED BEHAVIOR                          = consistent with approximately
                                             2,000 / operation / day
BATCH-1 USABLE AGGREGATE THROUGHPUT        = 31,600 successful new records
                                             (31,601 requests, 1 terminal 429)
```

## Full-hydration horizon (informational)

```text
FULL_OFFICIAL_CALLS remaining after Batch 1 = 329,088 - 31,961 = 297,127
Batch-1 usable aggregate throughput         = ~31,600 successful records
Batches remaining                           = ceil(297,127 / 31,600) ≈ 10
Wall-clock estimate                         = ~10 additional daily quota windows
                                              (assuming similar future quota windows
                                               — not a contractual guarantee)
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
Q4-A service-wide 2,000/day?         = NO / disproven by this run
Q4-B strictly independent per-op?    = STRONGLY INDICATED
                                       / NOT STRICTLY PROVEN (no post-429 probe)
Batch-1 usable aggregate throughput  = ~31,600 successful records / run
Full corpus hydration ETA            = ~10 more daily quota windows
                                       (assuming similar future windows)

NEXT                                 = GPT delta-only verify
                                       → Owner authorises Batch 2 explicitly
                                       → resume next quota window
                                       (or, if desired, submit operating-account
                                        / traffic-increase request to compress
                                        the ~10-window horizon — draft ready
                                        in OBJ_chem04-quota-account-gate_v1.md)
STOP
```
