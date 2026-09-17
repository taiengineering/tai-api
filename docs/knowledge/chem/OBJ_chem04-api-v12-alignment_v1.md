---
class: records
type: report
scope: knowledge
project: chem
title: WO-CHEM-04-API-V12-ALIGN-001 KOSHA MSDS OpenAPI v1.2 endpoint alignment
version: 1
status: active
owner: taiwang
---

# WO-CHEM-04-API-V12-ALIGN-001 — KOSHA MSDS Official API v1.2 Alignment

## Official specification

```text
title       = 한국산업안전보건공단
              OPENAPI 서비스 명세서 (물질안전보건자료 MSDS)
version     = 1.2
date        = 2026-09-16
change note = 호출URL 현행화, 활용방법 추가
```

## Contract change (endpoints only)

```text
OLD BASE      = https://apis.data.go.kr/B552468/msdschem
NEW BASE      = https://apis.data.go.kr/B552468/msdschem1

OLD LIST      = getChemList
NEW LIST      = getChemList001

OLD DETAIL 01 = getChemDetail01
NEW DETAIL 01 = getChemDetail011

OLD DETAIL 09 = getChemDetail09
NEW DETAIL 09 = getChemDetail091

OLD DETAIL 10 = getChemDetail10
NEW DETAIL 10 = getChemDetail101

OLD DETAIL 16 = getChemDetail16
NEW DETAIL 16 = getChemDetail161
```

Under v1.2 every operation name ends with a literal trailing `1`.
The new contract lives in `services/kosha_msds/contract.py`:

```text
DETAIL_OPERATION_TEMPLATE = "getChemDetail{section:02d}1"
detail_operation(n)       = single source of truth for section→op name
SOURCE_CONTRACT_VERSION   = "KOSHA_MSDS_OPENAPI_V1_2"
```

## Parser — NO change

The v1.2 spec's Detail response schema (`lev / msdsItemCode /
upMsdsItemCode / msdsItemNameKor / msdsItemNo / ordrIdx /
itemDetail`) is identical to what
`services.kosha_msds.parse.canonical_section_items()` already
canonicalizes. Parser was not touched by this WO.

The v1.2 List response fields (`casNo / chemId / chemNameKor /
enNo / keNo / unNo / koshaConfirm / lastDate / openYn /
numOfRows / pageNo / totalCount`) match the existing
`LIST_IDENTITY_FIELDS`. Parser was not touched.

```text
PARSER CHANGE  = NO
LIST FIELDS    = compatible
DETAIL FIELDS  = compatible
```

## Rate-limit token retention

The v1.2 spec's documented error table lists:

```text
01 = Gateway 인증실패
11 = 필수요청 파라메터 없음
```

but existing runtime evidence (2026-09-14 measurement) has
observed data.go.kr gateway returning `22 / 23` on quota
exhaustion. Per WO §12 those tokens are retained in
`RATE_LIMIT_DAILY_CODES = frozenset({"22"})` and
`RATE_LIMIT_SECOND_CODES = frozenset({"23"})`. They are
runtime-observed gateway errors, not v1.2-documented error
codes.

## Live 17-call smoke (2026-09-18)

Real production KOSHA MSDS OpenAPI on the v1.2 endpoints, using the
developer service key from env only, hard cap = 25 total:

```text
LIVE LIST                = 1 call
  URL ends in            = /getChemList001
  HTTP                   = 200
  resultCode             = 00
  parse                  = PASS
  items                  = >0

LIVE DETAIL              = 16 / 16 attempted
  01 getChemDetail011    → HTTP 200 / rc 00 / PASS
  02 getChemDetail021    → HTTP 200 / rc 00 / PASS
  03 getChemDetail031    → HTTP 200 / rc 00 / PASS
  04 getChemDetail041    → HTTP 200 / rc 00 / PASS
  05 getChemDetail051    → HTTP 200 / rc 00 / PASS
  06 getChemDetail061    → HTTP 200 / rc 00 / PASS
  07 getChemDetail071    → HTTP 200 / rc 00 / PASS
  08 getChemDetail081    → HTTP 200 / rc 00 / PASS
  09 getChemDetail091    → HTTP 200 / rc 00 / PASS
  10 getChemDetail101    → HTTP 200 / rc 00 / PASS
  11 getChemDetail111    → HTTP 200 / rc 00 / PASS
  12 getChemDetail121    → HTTP 200 / rc 00 / PASS
  13 getChemDetail131    → HTTP 200 / rc 00 / PASS
  14 getChemDetail141    → HTTP 200 / rc 00 / PASS
  15 getChemDetail151    → HTTP 200 / rc 00 / PASS
  16 getChemDetail161    → HTTP 200 / rc 00 / PASS

TOTAL LIVE CALLS          = 17
HARD CAP                  = 25   (under cap ✓)
HTTP 429                  = 0
resultCode 22             = 0
resultCode 23             = 0
schema break              = NO
serviceKey leakage        = NO
```

Test chemId for the Detail smoke: `000001` (official example).
List search: `searchCnd=0` / `searchWrd=벤젠`.

## Targeted unit tests

```text
tests/test_kosha_msds_catalog.py           = updated
  - BASE_URL / LIST_OPERATION expectations refreshed to v1.2
  - handler URL parsing now strips trailing '1' to recover section digits
  - added 4 explicit v1.2 contract tests (SOURCE_CONTRACT_VERSION,
    BASE_URL, LIST_OPERATION, detail_operation() full range +
    range guard)
tests/test_kosha_msds_full_sync.py         = updated
  - URL-suffix parsing now uses [:-1] to strip trailing '1'
  - assertion sets now compare against {NN1} not {NN}
tests/test_chem04_live_sample.py           = updated
  - detail_url() generator asserts /getChemDetail{NN}1 pattern
  - asserts new /msdschem1/ base
```

Full CHEM-04 + KOSHA MSDS suite result:

```text
186 / 186 PASS   (skip = 0)
```

## Quota evidence (Owner-confirmed, portal display)

Per Owner-provided screen capture from data.go.kr:

```text
ACCOUNT TYPE                      = DEVELOPMENT
STATUS                            = APPROVED
VALID                             = 2026-09-17 ~ 2028-09-17

Portal display (per operation):
  getChemList001                  = 2,000 / day
  getChemDetail011 .. 161         = 2,000 / day each
```

Runtime enforcement scope (service-wide vs per-endpoint) remains
`TO BE MEASURED`. The next hydration WO will measure this by
running fail-closed against real 429 / resultCode 22 rather than
pre-stopping at the portal number (per Owner instruction in the
WO §24 forward plan).

## Anchors

```text
main start                        = eaf199602770bf6fbcc524a356673723422dcd07
branch                            = feature/chem04-api-v12-align
changed files                     = 8
  services/kosha_msds/contract.py
  services/kosha_msds/client.py
  services/kosha_msds/live_sample.py
  services/kosha_msds/discovery.py
  tools/chem04/live_sample_compare.py
  tools/chem04/v12_contract_smoke.py           (new; one-shot tool)
  tests/test_chem04_live_sample.py
  tests/test_kosha_msds_catalog.py
  tests/test_kosha_msds_full_sync.py
  docs/knowledge/chem/OBJ_chem04-api-v12-alignment_v1.md  (new)
```

## Scope closure

```text
FULL HYDRATION                    = NOT STARTED
PRODUCTION INGEST                 = 0
DB WRITE                          = 0
MIGRATION                         = 0
SCHEMA CHANGE                     = 0
20,568 IDENTITY RECENSUS          = 0
48,963 SECONDARY RE-AUDIT         = 0
329,088 / 51,940 CALLS            = 0
```

Frozen prior CHEM-02 / CHEM-03 / CHEM-04 evidence (including
Option-A decision on PR #359) reused verbatim, not reverified.

## Verdict

```text
WO-CHEM-04-API-V12-ALIGN-001      = PASS / HYDRATION-V12-READY

OFFICIAL API SPEC                 = V1.2 CONFIRMED
CLIENT BASE                       = msdschem1
LIST OP                           = getChemList001
DETAIL OPS                        = 011 .. 161
PARSER                            = COMPATIBLE
LIVE LIST                         = PASS
LIVE DETAIL                       = 16 / 16 PASS

NEXT                              = GPT delta-only verify
                                    → v1.2 PR merge
                                    → WO-CHEM-04-OFFICIAL-HYDRATE-V12-001
                                      (fail-closed at real 429 / rc22;
                                       do NOT pre-stop at portal number)
STOP
```
