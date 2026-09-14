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
CHEM-04 = IN_PROGRESS (PATCH-2 on PR #350, not merged)
CHEM-01 = CLOSED / PASS_WITH_INGEST_GATE
CHEM-02 = DONE / CLOSED
CHEM-03 = CLOSED / CONDITIONAL
CHEM-ENUM-GATE-01 = CLOSED / CONDITIONAL (historical)
R1 OPENAPI DATA RIGHTS = CLEAR
OPENAPI SEARCH CONTRACT = PASS
OPENAPI DETAIL CONTRACT = PASS
INCREMENTAL RUNNER = IMPLEMENTED
DOCUMENTED FULL ENUMERATION API = NOT AVAILABLE
INITIAL FULL SEED = BLOCKED
PRODUCTION FULL INGEST = BLOCKED
```

This PATCH freezes the **official OpenAPI 활용가이드 contract**. It does not invent a dump-all. It does not crawl `chemList.do`.

---

## 0. Revision guard

```text
PR #350 reviewed head (PATCH-2 parent) =
d5ada607e1532c79c651b852e5fa0b83e53b99e0
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

### B. Full identity source (not yet established)

```text
ENUMERATION / CENSUS of every chemId
```

```text
A = AVAILABLE
B = NOT YET ESTABLISHED
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
IN_PROCESS RESUME = PASS
PROCESS-RESTART RESUME = NOT_IMPLEMENTED
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

Not:

```text
OpenAPI 자체가 전체 chemId를 찾아주는 runner
```

When an official chemId seed exists, the same runner can hydrate and incrementally update.

`list_page` still allows omitted search params so a **future official list transport** can reuse pagination. OpenAPI omitted-search results cannot be promoted to FULL corpus (`SEARCH_IS_NOT_CORPUS`). `pageNo < 1` fail-closed.

---

## 7. Initial Seed Gate

```text
INITIAL FULL INGEST requires official chemId census source
INITIAL_FULL_SEED = BLOCKED
```

Required identity field: `chemId`.

Acceptable later (none established now):

```text
1. KOSHA 공식 전체목록
2. data.go.kr 공식 file dataset
3. KOSHA official bulk/index
4. future official enumeration API
```

Forbidden:

```text
웹 scraping
검색어 사전 조합
가나다/알파벳 brute-force
CAS brute-force
chemId 숫자 추측
undocumented endpoint
```

Seed acceptance (all required):

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

OpenAPI search still cannot detect “a new chemId was added to the global corpus”. Global NEW discovery also needs official seed refresh.

---

## 9. Publish

FULL_OFFICIAL constructor requires `seed_source ∈ OFFICIAL_SEED_SOURCES`.

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
production full ingest   = NO
web crawl                = NO
Graph mutation           = 0
Legal Engine mutation    = 0
KOSHA inquiry sent       = NO
```

---

## 11. Tests

```text
python3 -m pytest tests/test_kosha_msds_catalog.py tests/test_kosha_msds_full_sync.py -q --tb=line
```

CI: mock transport only. No live KOSHA calls. No additional full-list probe.

---

## STOP

```text
OPENAPI LIST CONTRACT = SEARCH-ONLY
DOCUMENTED FULL ENUMERATION API = NOT AVAILABLE
API_FULL_ENUMERATION = BLOCKED_BY_SOURCE_CONTRACT
INITIAL FULL SEED = BLOCKED
SYNC RUNNER = PRESERVED
CHEM-04 = IN_PROGRESS
MERGE = NOT AUTHORIZED
```
