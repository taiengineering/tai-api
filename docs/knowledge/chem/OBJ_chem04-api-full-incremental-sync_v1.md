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

# OBJ-CHEM-04 — Official OpenAPI search contract + incremental runner

```text
CHEM-04 = IN_PROGRESS (PATCH-3 on PR #350, not merged)
CHEM-01 = CLOSED / PASS_WITH_INGEST_GATE
CHEM-02 = DONE / CLOSED
CHEM-03 = CLOSED / CONDITIONAL
CHEM-ENUM-GATE-01 = CLOSED / CONDITIONAL (historical)
R1 OPENAPI DATA RIGHTS = CLEAR
OPENAPI SEARCH CONTRACT = PASS
OPENAPI DETAIL CONTRACT = PASS
INCREMENTAL RUNNER = IMPLEMENTED
DOCUMENTED FULL ENUMERATION API = NOT AVAILABLE
OPENAPI LIST CONTRACT = SEARCH-ONLY
DETAIL01_ID_DISCOVERY = IN_PROGRESS
EMPIRICAL_API_CENSUS = IN_PROGRESS
INITIAL FULL SEED = BLOCKED until INITIAL_SEED_CANDIDATE = PASS
PRODUCTION FULL INGEST = BLOCKED
```

This PATCH freezes the **official OpenAPI 활용가이드 contract** and adds empirical `getChemDetail01` identity discovery. It does not invent a dump-all. It does not crawl `chemList.do`. Empirical census is **not** `FULL_OFFICIAL`.

---

## 0. Revision guard

```text
PR #350 PATCH-3 parent (PATCH-2 reviewed head) =
998d54b6c22728220d45a5fbafbe02178818e796
branch =
feature/chem04-api-full-sync
```

`origin/main` may have moved with unrelated E2E docs after CHEM-ENUM-GATE-01 merge. CHEM impact of that delta = NO. This PATCH does not rebase.

---

## A vs B — do not mix

### A. OpenAPI (available)

```text
SEARCH  = getChemList (searchCnd + searchWrd required)
DETAIL  = getChemDetail01~16 (chemId required)
```

### B. Full identity source

```text
DOCUMENTED ENUMERATION API = NOT AVAILABLE
EMPIRICAL_API_CENSUS       = PATCH-3 Detail01 ID discovery (not FULL_OFFICIAL)
```

```text
A = AVAILABLE
B.official = NOT YET ESTABLISHED
B.empirical = DETAIL01_ID_DISCOVERY
```

The PR #350 runner is **B-consumer + A-detail hydrator**, not an OpenAPI dump-all finder.

---

## 1. Official getChemList contract (HWP freeze)

Owner document: 한국산업안전보건공단 물질안전보건자료 오픈API 활용가이드.

```text
operation = getChemList
purpose   = 화학물질 검색 목록 조회
OPENAPI LIST CONTRACT = SEARCH-ONLY
searchWrd = REQUIRED
searchCnd = REQUIRED
  0 = 국문명
  1 = CAS No
  2 = UN No
  3 = KE No
  4 = EN No
pageNo    = OPTIONAL
numOfRows = OPTIONAL
```

Response fields (no guessed extras):

```text
chemId, chemNameKor, casNo, unNo, keNo, enNo,
koshaConfirm, lastDate, openYn,
pageNo, numOfRows, totalCount
```

```text
identity = KOSHA_MSDS + chemId (text, keep leading zeros)
cas_no   = nullable, not identity
```

---

## 2. totalCount semantics

```text
totalCount = SEARCH RESULT COUNT
           = count for this searchWrd + searchCnd
```

It is **not** the global KOSHA chemical corpus size.

예: `searchCnd=0 searchWrd=벤젠` → 그 검색 결과 건수 (CHEM-01: 777). 그것이 N이 아니다.

`kosha_msds_snapshots.expected_count` for FULL_OFFICIAL may only come from an **official chemId census**, never from a search `totalCount`.

---

## 3. Documented functions that do not exist

```text
searchWrd omitted → ALL
searchWrd blank → ALL
searchWrd = *
searchWrd = %
searchCnd = ALL
getAllChemList
bulk-list API
updatedSince
global chemId enumeration API
```

```text
DOCUMENTED_OPENAPI_FULL_ENUMERATION = NO
DOCUMENTED_FULL_ENUMERATION_API     = NOT AVAILABLE
API_FULL_ENUMERATION                = BLOCKED_BY_SOURCE_CONTRACT
```

의미: API 장애 아님, 구현 실패 아님, 서비스키 문제 아님. 공식 API가 search-oriented contract이다.

---

## 4. Live probe (historical; do not repeat)

CHEM-04 Stage A (6 calls, no further probing):

omit / blank / default / `searchCnd=0` without `searchWrd` → `resultCode=00`, `totalCount=0`.

This **matches** the official search-only contract. It is not an outage and not a reason to hunt hidden parameters.

```text
ADDITIONAL FULL-LIST PROBE = 0
```

금지: `*`, `%`, blank variation, undocumented ALL mode, web scrape, file download, KOSHA 문의.

---

## 5. Existing CHEM-02 pieces (reused)

| piece | location |
|---|---|
| search / detail client | `services/kosha_msds/client.py` |
| XML / resultCode | `services/kosha_msds/parse.py` |
| retry/timeout | `KoshaMsdsClient._get` |
| hash | `services/kosha_msds/hash.py` |
| identity | `services/kosha_msds/identity.py` |
| schema | `supabase/migrations/20260914_kosha_msds_catalog.sql` (not applied) |

---

## 6. Runner — preserved, role restated

Kept:

```text
pagination
identity census validation
NEW / CHANGED / UNCHANGED / REMOVED_CANDIDATE
Detail01~16 hydration
IN_PROCESS RESUME = PASS (hydration, in-memory)
PROCESS-RESTART RESUME = NOT_IMPLEMENTED (hydration)
DISCOVERY PROCESS-RESTART RESUME = PASS (local checkpoint + jsonl)
PUBLISHED_FULL coverage guard
incremental PUBLISHED_FULL = FORBIDDEN (no DB-backed prior coverage)
```

Role:

```text
Known chemical identity census
+
KOSHA OpenAPI Detail01~16
+
incremental change synchronization
```

PATCH-3 adds a separate **identity discovery** path (`getChemDetail01` only). It does not replace the hydration runner.

`list_page` still allows omitted search params so a **future official list transport** can reuse pagination. OpenAPI omitted-search results cannot be promoted to FULL corpus (`SEARCH_IS_NOT_CORPUS`). `pageNo < 1` fail-closed.

---

## 7. Initial Seed Gate

```text
INITIAL FULL INGEST requires official chemId census source
INITIAL_FULL_SEED = BLOCKED
EMPIRICAL_API_CENSUS ≠ FULL_OFFICIAL
```

Required identity field: `chemId`.

Acceptable later as **official** seed (none established now):

```text
1. KOSHA 공식 전체목록
2. data.go.kr 공식 file dataset
3. KOSHA official bulk/index
4. future official enumeration API
```

PATCH-3 adds an **empirical** candidate, not an official source:

```text
DETAIL01_ID_DISCOVERY / EMPIRICAL_API_CENSUS
000001 ~ 050000 Detail01 existence scan
+ 10,000 trailing zero-discovery tail
→ INITIAL_SEED_CANDIDATE (not FULL_OFFICIAL)
```

Forbidden:

```text
웹 scraping
검색어 사전 조합
가나다/알파벳 brute-force
CAS brute-force
getChemList hidden ALL / undocumented list dump
undocumented endpoint
N × Detail02~16 hydration in this PATCH
```

`chemId` 6-digit Detail01 existence scan is authorized here as empirical discovery only. It is not a documented enumeration API.

Seed acceptance for FULL_OFFICIAL (all required):

```text
official source = YES
chemId available = YES
complete/final finite enumeration = YES
reproducible acquisition = YES
source version/date recordable = YES
```

---

## 8. Incremental (kept)

After an official seed exists:

```text
NEW / CHANGED(lastDate) → Detail01~16
UNCHANGED → 0 detail calls
REMOVED_CANDIDATE → no DELETE
```

OpenAPI search still cannot detect “a new chemId was added to the global corpus”. Global NEW discovery also needs official seed refresh. Empirical Detail01 census refresh is a later decision.

---

## 9. Publish

FULL_OFFICIAL constructor requires `seed_source ∈ OFFICIAL_SEED_SOURCES`.

`EMPIRICAL_API_CENSUS` is **not** in `OFFICIAL_SEED_SOURCES`.

PUBLISHED_FULL still requires PATCH-1 coverage:

```text
covered_detail_count == census.total_count
missing_detail_count == 0
COMPLETE or EMPTY_BUT_VALID for every census chemId
BOUNDED_SEARCH → PUBLISHED_FULL = NO
```

This PR does **not** publish.

---

## 10. Production boundary

```text
production mutation      = 0
production migration     = NO
production catalog ingest = NO
full Detail02~16 hydration = NO
web crawl                = NO
file seed                = NO
Graph mutation           = 0
Legal Engine mutation    = 0
KOSHA inquiry sent       = NO
merge                    = NO
```

---

## 11. Tests

```text
python3 -m pytest tests/test_kosha_msds_catalog.py tests/test_kosha_msds_full_sync.py tests/test_kosha_msds_discovery.py -q --tb=line
```

CI: mock transport only. No live KOSHA calls. No additional getChemList dump-all probe.

---

## 12. PATCH-3 — DETAIL01_ID_DISCOVERY

```text
method                 = DETAIL01_ID_DISCOVERY
census status          = EMPIRICAL_API_CENSUS
DOCUMENTED ENUM API    = NOT AVAILABLE (unchanged)
OPENAPI LIST CONTRACT  = SEARCH-ONLY (unchanged)
PORTAL 1,000/day       = advisory display
RUNTIME API RESPONSE   = execution truth
quota unlimited assume = FORBIDDEN
```

Discovery:

```text
6-digit chemId f"{n:06d}"
→ GET getChemDetail01
→ DISCOVERED | ABSENT | UNKNOWN
```

```text
EXISTS  = HTTP OK + resultCode OK + non-empty item payload
ABSENT  = HTTP OK + resultCode OK + empty_but_valid
ERROR   = timeout / 5xx / 429 / resultCode 22 / parse / transport
ERROR  ≠ ABSENT
census complete ⇔ scanned = DISCOVERED + ABSENT and UNKNOWN = 0
```

Quota/rate STOP:

```text
HTTP 429
resultCode 22
service request limit exceeded
daily request limit
gateway throttling
명시적 quota error
→ checkpoint 저장, 추가 호출 STOP
```

Range:

```text
Stage 1  000001 ~ 000100
Stage 2  000101 ~ 001000
Stage 3  001001 ~ 005000
Stage 4  005001 ~ 050000
workers  4 start, max 8
tail     050001 ~ 060000 Detail01 only
         extend by 10,000 until a 10k block has DISCOVERED = 0
```

Local only:

```text
artifacts/chem04/chem_id_census_<timestamp>.jsonl
artifacts/chem04/checkpoint.json
git commit of artifacts = NO
production writer       = NEVER
```

External `48,966` and KOSHA web ~20,000 are advisory. Do not force-fit.

PASS for `INITIAL_SEED_CANDIDATE`:

```text
scan range complete
UNKNOWN = 0
10,000 trailing IDs with zero discoveries
checkpoint complete
artifact hash recorded
```

Live measurement is recorded after the scan. Until then:

```text
INITIAL_SEED_CANDIDATE = PENDING
```

### Live measurement 2026-09-14 (Railway tai-api-prod env, serviceKey not logged)

```text
scan starts                    = YES
Stage 1 000001-000100          = 100 DISCOVERED, quota=0, ~20 calls/sec
Stage 2 000101-001000          = 898 DISCOVERED, 2 UNKNOWN timeout, quota=0
Stage 3 001001-               = HTTP 429 after ~1008 total calls
000001~050000                  = quota STOP
tail probe                     = NOT STARTED
calls attempted                = 1008
DISCOVERED                     = 998
ABSENT                         = 1 (001005 empty_but_valid)
UNKNOWN                        = 9
  timeout                      = 000764, 000838
  HTTP 429                     = 001001-001004, 001006-001008
MAX_DISCOVERED_CHEMID          = 001000
MIN_DISCOVERED_CHEMID          = 000001
prefix watermark last_scanned  = 000763  (000764 UNKNOWN, ERROR ≠ ABSENT)
HTTP 429                       = 7
resultCode 22                  = 0
PORTAL 1000/day HARD LIMIT OBSERVED = YES
durable checkpoint             = PASS
artifact                       = artifacts/chem04/chem_id_census_20260914T010438Z.jsonl
artifact SHA256                = 8798424777acf6f8142e8e364d3094d779d0a2c0d61cdf959e7b6c1f93187daa
artifact rows                  = 1008
artifact git                   = NO
INITIAL_SEED_CANDIDATE         = BLOCKED
```

Runtime truth this run: after about 1,000 Detail01 calls the API returned HTTP 429. Portal displayed 1,000/day was not assumed; it was observed. Resume from checkpoint is possible on a later day. No Detail02~16 hydration. No production ingest.

---

## STOP

```text
OPENAPI LIST CONTRACT = SEARCH-ONLY
DOCUMENTED FULL ENUMERATION API = NOT AVAILABLE
API_FULL_ENUMERATION = BLOCKED_BY_SOURCE_CONTRACT
DETAIL01_ID_DISCOVERY = PASS (implemented; live census quota STOP)
EMPIRICAL_API_CENSUS = NOT FULL_OFFICIAL
INITIAL_SEED_CANDIDATE = BLOCKED
PORTAL 1000/day HARD LIMIT OBSERVED = YES
INITIAL FULL SEED = BLOCKED
SYNC RUNNER = PRESERVED
CHEM-04 = IN_PROGRESS
MERGE = NOT AUTHORIZED
```
