---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-04-OFFICIAL-HYDRATE-V12-BATCH2 Batch 2 hydration receipt
version: 1
status: active
owner: taiwang
---

# WO-CHEM-04-OFFICIAL-HYDRATE-V12-BATCH2 — Batch 2 Foreground Resume

## Verdict summary

```text
STOP REASON (runner)     = QUOTA_LIMIT
STOP REASON (WO §9)      = QUOTA_WINDOW_NOT_AVAILABLE
NEW SUCCESS              = 0
NEW HTTP REQUESTS        = 1
NEW HTTP 429             = 1
CORPUS DELTA             = 0 records
```

The Batch-1 quota window had not reset by the time Batch 2 was
attempted. The runner made exactly one resume request (the first
pending pair), received an immediate HTTP 429, and STOPPED per
WO §9. No retry, no additional probes, no artifact corruption.

## Scope

```text
API CONTRACT             = KOSHA MSDS OPENAPI v1.2 (2026-09-16)
BASE                     = https://apis.data.go.kr/B552468/msdschem1
ACCOUNT                  = DEVELOPMENT / APPROVED  (2026-09-17 ~ 2028-09-17)
PORTAL DISPLAY           = 2,000 / operation / day

EXECUTION MODE           = FOREGROUND
KEY INJECTION            = railway run --service tai-api-prod
CONCURRENCY              = workers = 1
```

## Anchors

```text
main at run              = 60bbef11810190e2073941d4471d4afd559e1249
branch                   = docs/chem04-official-hydrate-v12-batch2
queue                    = artifacts/chem04/content/queues/hydration_queue.jsonl (gitignored)
queue rows               = 329,088
queue SHA256             = 7eba2dca2e183bab2c09f6260874cf8b5380ccb6d2f4bec61dfd193c881085d9
hard safety cap          = 40,000
```

## Batch 1 baseline (verified before run)

```text
responses.jsonl (raw)             = 49994a2a8d44b5c2acfae60283d5f2f76fd65e0af5842a10db43383e26b643dd  OK
errors.jsonl    (raw)             = 919c64b0976bb5ff8681765a5ff3ae93e898830ad4a2c9e711e842bcbb0cf90d  OK
checkpoint.json (canonical)       = dbebbc5196f0471edce0bc18bbd4227fe542dcdf19004bb31b40e20d0a165cca  OK
run_report      (canonical aug)   = c8c83a3de035b2ce687163a377b8fe498cc0e9f29211e0d37e7c33ed004cb717  OK
queue           (SHA + rows)      = 7eba2dca…085d9 / 329,088                                            OK
start_completed (unique pairs)    = 31,961                                                              OK
```

## Runner behaviour

Same `tools/chem04/official_hydrate_v12.py` runner invoked via
`railway run --service tai-api-prod` (no new code, no shell env
lookup of the key, no `~/.env` read). Key never printed.

```text
started_at (UTC)         = 2026-09-18T00:08:14Z
ended_at   (UTC)         = 2026-09-18T00:08:15Z
started_at (KST)         = 2026-09-18 09:08:14+09:00
ended_at   (KST)         = 2026-09-18 09:08:15+09:00
elapsed                  = ~1 second
stop_reason              = QUOTA_LIMIT
```

Interval since Batch 1 terminal 429:

```text
Batch 1 terminal 429     = 2026-09-17T23:11:06Z (KST 08:11:06)
Batch 2 terminal 429     = 2026-09-18T00:08:15Z (KST 09:08:15)
elapsed between 429s     = ~57 minutes 09 seconds
```

## Batch 2 result

```text
start_completed          = 31,961
new_success              = 0
new_official_empty       = 0
new_errors               = 1        (the HTTP 429 on the first resume call)
total_completed          = 31,961   authoritative records (unchanged)

remaining in queue       = 297,127  (unchanged)

http_requests (this run) = 1
http_429                 = 1
resultCode 22            = 0
resultCode 23            = 0
consecutive error budget = untriggered
```

## Per-operation call counts IN THIS RUN

```text
getChemDetail011         = 0
getChemDetail021         = 0
getChemDetail031         = 0
getChemDetail041         = 0
getChemDetail051         = 0
getChemDetail061         = 0
getChemDetail071         = 0
getChemDetail081         = 0
getChemDetail091         = 0
getChemDetail101         = 1     ← the sole resume call; 429 terminal
getChemDetail111         = 0
getChemDetail121         = 0
getChemDetail131         = 0
getChemDetail141         = 0
getChemDetail151         = 0
getChemDetail161         = 0
TOTAL                    = 1
```

## First (only) quota hit

```text
first quota HTTP status  = 429
first quota operation    = getChemDetail101
first quota chemId       = 432377
detected at (UTC)        = 2026-09-18T00:08:15Z
detected at (KST)        = 2026-09-18 09:08:15+09:00
retry                    = 0    (immediate STOP per WO §18 / Batch2 WO §9)
additional probes        = 0
```

The Batch-2 first-pending pair matches the Batch-1 terminal 429
target exactly (`chemId=432377 / getChemDetail101`), which is
what the resume-safe runner is expected to re-attempt.

## WO §9 classification

Because the first resume call itself 429'd:

```text
NEW SUCCESS              = 0
HTTP 429 count           = 1
=> WO §9 outcome         = QUOTA_WINDOW_NOT_AVAILABLE
```

The Batch 1 daily quota window had not reset in the ~57 minutes
between the two 429s. This is a defined outcome per WO §9 and
does not consume the run authorization — the same authorization
covers the next foreground resume in a genuinely reset window.

## Cumulative artifact state after Batch 2

```text
responses.jsonl (raw)         = 49994a2a8d44b5c2acfae60283d5f2f76fd65e0af5842a10db43383e26b643dd
                                (unchanged since Batch 1 — no new success records)
errors.jsonl    (raw)         = 06569e91dca726d5c8244ee8ed9da190b9f1086823c9eb38672ecf56147770fc
                                (grew from 1 line to 2 lines — Batch 1 429 + Batch 2 429)
checkpoint.json (canonical)   = 740a7d67d9f6e716d2aedb12d134df6d52e05cae62c59340b2910bc7d8bf0b18
run_report      (canonical aug) = c8855a757161eac22b167faf474960278e01ad52194c9c052b8231c8b63d48a6
```

Batch 1 SHAs remain preserved as historical baseline. Bulk
artifacts stay under `artifacts/chem04/official_v12/` which is
gitignored (per WO §10). Only this receipt is committed.

## Content correctness (spot-check)

No new response records were written (new_success = 0), so
`responses.jsonl` is byte-identical to Batch 1's final state. The
31,961 already-completed records continue to satisfy:

```text
source                     = KOSHA_OFFICIAL
source_contract_version    = KOSHA_MSDS_OPENAPI_V1_2
official_spec_version      = 1.2
official_spec_date         = 2026-09-16
authoritative_verified     = true    (only on HTTP 200 + rc 00 + parse PASS)
result_code                = 00
```

## Progress equation

```text
total_completed  + remaining  = queue_rows
      31,961     +   297,127  =   329,088       PASS
```

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

SECRET LEAK CHECK           = PASS (0 raw serviceKey= occurrences across
                              responses.jsonl, errors.jsonl,
                              checkpoint.json, run_report.json;
                              key delivered via `railway run` env
                              injection, never printed to log)

CODE CHANGE                 = 0  (services/, tools/, tests/ untouched)
TEST CHANGE                 = 0
BULK ARTIFACT MUTATION      = 0 (responses.jsonl SHA unchanged;
                                 errors.jsonl grew by 1 authorized
                                 error line via runner)
LIVE API CALLS              = 1  (the single resume request)
QUOTA PROBE                 = 0
POST-429 EXPERIMENT         = 0
```

## Verdict

```text
WO-CHEM-04-OFFICIAL-HYDRATE-V12-BATCH2 = STOPPED / QUOTA_WINDOW_NOT_AVAILABLE

Batch 2 corpus delta                   = 0 records
Cumulative authoritative corpus        = 31,961 records (unchanged)
Cumulative remaining                   = 297,127
Q4-A service-wide 2,000/day?           = still disproven (from Batch 1)
Q4-B strictly independent per-op?      = still not strictly proven
                                         (this run did not probe other ops)

NEXT                                   = GPT delta-only verify
                                         → owner attempts Batch 2 (re-resume)
                                           only in a genuinely reset quota
                                           window; the Batch-2 authorization
                                           covers that follow-up run at
                                           owner's timing.
STOP
```
