---
class: records
type: report
scope: knowledge
project: chem
title: OBJ-CHEM-04 API-only full list and incremental sync
version: 1
status: active
owner: taiwang
---

# OBJ-CHEM-04 — KOSHA OpenAPI full list + incremental sync

```text
CHEM-04 = IN_PROGRESS (PATCH-1 on PR #350, not merged)
CHEM-01 = CLOSED / PASS_WITH_INGEST_GATE
CHEM-02 = DONE / CLOSED
CHEM-03 = CLOSED / CONDITIONAL
CHEM-ENUM-GATE-01 = CLOSED / CONDITIONAL (historical)
R1 OPENAPI DATA RIGHTS = CLEAR
R2/R3 = NOT APPLICABLE on this API-only path
CHEM-ENUM-GATE-01 web harvest = not used
```

This work order does **not** crawl `chemList.do`, send a KOSHA inquiry, brute-force chemId/CAS/search words, apply production migration, or run production Detail ingest.

---

## 0. Revision guard

```text
authorized origin/main =
3e65de0b59fe765398d14986f361279390232ac5
branch =
feature/chem04-api-full-sync
```

---

## 1. Existing CHEM-02 implementation (reused, not replaced)

| piece | location |
|---|---|
| getChemList / getChemDetail01–16 client | `services/kosha_msds/client.py` (`search`, `get_detail_section`, `get_full_detail`) |
| XML parse / resultCode | `services/kosha_msds/parse.py` |
| retry/timeout | `KoshaMsdsClient._get` (`DEFAULT_MAX_ATTEMPTS=3`, `DEFAULT_TIMEOUT_SECONDS=30`) |
| canonical hash | `services/kosha_msds/hash.py` |
| identity = chemId text | `services/kosha_msds/identity.py` |
| fixtures | `tests/fixtures/kosha_msds/` |
| DB contract | `supabase/migrations/20260914_kosha_msds_catalog.sql` (not applied) |

No second KOSHA client. Existing `/kosha/msds` router stays stale and untouched.

New:

```text
services/public_data_sync/census.py
  LIST identity census + previous/current diff
services/kosha_msds/sync.py
  pagination, fail-closed census, incremental plan, resume hydration
KoshaMsdsClient.list_page
  getChemList page with optional omitted searchCnd/searchWrd
```

---

## 2. Official API Guide frozen facts (unchanged)

```text
getChemList searchWrd required (HWP) = YES
getChemList searchCnd required (HWP) = YES
documented ALL mode                 = NO
documented bulk/index               = NO
```

---

## 3. Stage A — live getChemList full-list probe

Transport: existing `kr_get` via Railway `tai-api-prod` production env (serviceKey never printed). Budget: **6 calls** (max 10). CHEM-01 `searchCnd=0 searchWrd=""` was **not** repeated.

| # | request (serviceKey omitted from log) | HTTP | resultCode | totalCount | items |
|---|---|---|---|---|---|
| 1 | pageNo=1 numOfRows=10 (searchWrd/searchCnd **OMITTED**) | 200 | 00 | **0** | 0 |
| 2 | serviceKey only (swagger/default) | 200 | 00 | **0** | 0 |
| 3 | searchWrd=BLANK, searchCnd **OMITTED**, pageNo=1 numOfRows=10 | 200 | 00 | **0** | 0 |
| 4 | pageNo=1 numOfRows=100 (search omitted) | 200 | 00 | **0** | 0 |
| 5 | searchCnd=0, searchWrd **OMITTED**, pageNo=1 numOfRows=10 | 200 | 00 | **0** | 0 |
| 6 | pageNo=0 numOfRows=10 (search omitted) | 200 | 00 | **0** | 0 |

```text
FULL_LIST_API = BLOCKED
actual full-list request =
GET /getChemList?pageNo=1&numOfRows=10
(searchWrd OMITTED, searchCnd OMITTED)
searchWrd = OMITTED / BLANK
searchCnd = OMITTED / VALUE 0
totalCount = 0
N = UNKNOWN
sample page 1 count = 0
sample page 2 count = NOT REACHED
chemId present = NO (zero rows)
```

No guessed search words. No `%` / alphabet combinatorics. No chemList.do. No Detail01–16 in this probe.

`numOfRows` 10 and 100 were accepted on the empty dump-all shape. **1000 was not re-probed on dump-all** (empty contract already fail-closed; CHEM-01 already showed 1000 works on **search**).

```text
WORKING_PAGE_SIZE = 1000
meaning =
CHEM-01 search-measured practical page size (10/100/1000 accepted)
NOT an official maximum
dump-all page size = UNMEASURED (0 items)
```

---

## 4. FULL_LIST_API PASS criteria vs this probe

| clause | live |
|---|---|
| 1 totalCount at corpus scale | **NO** (0) |
| 2 pageNo increase returns different rows | NOT REACHED |
| 3 last page reachable | NOT REACHED |
| 4 each row has chemId | NOT REACHED |
| 5 repeatable pagination | NOT REACHED |
| 6 no guessed chemId | YES (none guessed) |

```text
FULL ENUMERATION = BLOCKED
```

Do **not** substitute KOSHA web advisory 20,568 as `N` or `expected_count`.

---

## 5. Identity / list fields (CHEM-02, reused)

When a list row exists, store only observed fields:

```text
chemId, chemNameKor, casNo, unNo, keNo, enNo, koshaConfirm, lastDate, openYn
```

```text
source_id  = KOSHA_MSDS
source_key = chemId   # text, keep leading zeros ("000001")
cas_no     = nullable, not identity
```

---

## 6. Runner design (implemented; live dump-all fail-closed)

`collect_list_census` paginates `list_page` then fail-closes if:

```text
missing chemId
duplicate chemId
collected != totalCount
totalCount <= 0   # live dump-all
```

Checkpoint / resume:

```text
IN_PROCESS RESUME = PASS
PROCESS-RESTART RESUME = NOT_IMPLEMENTED
checkpoint = in-memory SyncCheckpoint only
durable DB/file checkpoint = not in this PR
```

Rate limit: optional `sleep_s` between pages/details. Retry/backoff remains CHEM-02 client `_get`.

Idempotency: completed chemId is not re-fetched on resume. Hash compare on CHANGED can skip a new logical version when payload is identical.

Initial plan: previous map empty → all current chemId = **NEW** → Detail01–16 each.

Incremental:

```text
NEW      = current - previous          → Detail01–16
CHANGED  = intersection, lastDate !=   → Detail01–16, then canonical hash
UNCHANGED= intersection, lastDate ==   → 0 detail calls
REMOVED  = previous - current          → REMOVED_CANDIDATE
           no DELETE; historical rows stay
```

Additional change indicators: **none used**. lastDate only.

---

## 7. Snapshot / publish

CHEM-02 schema reused. No new chemical master. No schema expansion this WO.

```text
FULL_OFFICIAL snapshot = candidate constructor exists
PUBLISHED_FULL         = NOT performed
production ingest      = NO
```

Publish gate (evaluated, not applied):

```text
enumerated rows == totalCount
missing/duplicate chemId = 0
covered_detail_count == census.total_count
missing_detail_count == 0
every census chemId COMPLETE or EMPTY_BUT_VALID
INCOMPLETE = 0
incremental PUBLISHED_FULL = FORBIDDEN
  (no DB-backed prior full coverage in this PR)
```

Partial NEW/CHANGED records cannot publish even if those few rows are COMPLETE.

PATCH-1: `list_page` rejects `pageNo < 1` (pageNo=0 fail-closed).

---

## 8. REMOVED_CANDIDATE — schema proposal only

Existing columns already cover a non-delete stale mark:

```text
kosha_msds_chemicals.last_seen_at
kosha_msds_snapshot_items.in_snapshot
kosha_msds_chemicals.is_current  (stays false until PUBLISHED_FULL)
```

Proposal (not migrated here): a chemId absent from the new census is omitted from the new snapshot membership (`in_snapshot` only for current census) while the chemical row remains. Optional later: `last_seen_at` not updated. **No DELETE. No new inactive column in this PR.**

---

## 9. DETAIL_CALLS / quota

```text
N = UNKNOWN (API totalCount on dump-all = 0)
DETAIL_CALLS = 16 × N = UNKNOWN
development quota = 1,000/day
production traffic increase = Owner approval (not this PR)
```

This PR did **not** call Detail01–16 live and did **not** paginate a full corpus.

---

## 10. Production boundary

```text
production DB write          = 0
production migration         = NO
production full ingest       = NO
FULL_OFFICIAL publication    = NO
Graph mutation               = 0
factory_material link        = NO
Legal Engine link            = NO
frontend                     = NO
web chemList.do crawl        = NO
KOSHA inquiry sent           = NO
```

---

## 11. Tests

```text
python3 -m pytest tests/test_kosha_msds_catalog.py -q --tb=line
34 passed / 0 failed
python3 -m pytest tests/test_kosha_msds_full_sync.py -q --tb=line
24 passed / 0 failed
```

CI: mock transport only. No live KOSHA calls.

---

## 12. Unused paths (explicitly discarded)

```text
KOSHA web chemList.do crawl
file-based enumeration
chemId brute force
search-word combinatorics
KOSHA inquiry
lazy/on-demand-only catalog as the CHEM-04 SoT
```

---

## STOP

```text
FULL_LIST_API = BLOCKED
FULL ENUMERATION = BLOCKED
IN_PROCESS RESUME = PASS
PROCESS-RESTART RESUME = NOT_IMPLEMENTED
incremental PUBLISHED_FULL = FORBIDDEN
next = do not bypass with web/file
      wait GPT; if pagination later PASS, then quota → migration → ingest
CHEM-04 = IN_PROGRESS
```
