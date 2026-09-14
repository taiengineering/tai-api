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
CHEM-04 = IN_PROGRESS (PATCH-5 on PR #350, not merged)
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
DETAIL01_ID_DISCOVERY = PASS / FALLBACK_VALIDATION
PRIMARY ENUMERATION = KOSHA WEB CURRENT INDEX + SECONDARY BOOTSTRAP
50-DAY NUMERIC SCAN = NO
CURSOR FULL DATA EXECUTION = NO
LOCAL FULL DATA EXECUTION  = YES
PRODUCTION FULL INGEST = BLOCKED until GPT approval
```

This PATCH does not invent a dump-all OpenAPI. Sequential Detail01 scan is preserved as a fallback tool and is **not** primary enumeration.

---

## 0. Revision guard

```text
PR #350 PATCH-5 parent (PATCH-4 reviewed head) =
d50ecf8a9d4d643b7ea5f99c21d54394588856fa
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
python3 -m pytest \
  tests/test_kosha_msds_catalog.py \
  tests/test_kosha_msds_full_sync.py \
  tests/test_kosha_msds_discovery.py \
  tests/test_kosha_msds_bootstrap.py \
  tests/test_chem04_cli.py \
  -q --tb=line
```

CI: mock transport + fixture probe only. No live KOSHA calls. No Hugging Face 883MB download. No additional getChemList dump-all probe.

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

PATCH-3 sequential Detail01 scan is **FALLBACK / VALIDATION only**. It is not the primary way to build the current chemId census. A 50-day 1,000/day numeric scan is **not** required.

---

## 13. PATCH-4 role split — Cursor agent ≠ local bulk runner

Cursor the IDE and the Cursor conversation agent are not the same execution subject.

```text
GPT
= 설계 / 작업지시 / 결과 검증 / 승인

Cursor agent
= 수집기·정합화 코드 작성
= 테스트 작성
= dry-run / fixture / 10~100건 샘플 검증
= PR 관리

Local PC terminal
= 대량 데이터 다운로드
= KOSHA current index 전체 수집
= 48,966건 seed 처리
= JOIN / diff / checksum
= 대용량 artifact 생성
= checkpoint / resume

Supabase Production
= 검증·승인 완료 후에만 적재
```

```text
1. Cursor implements collectors + join + tests
2. fixture / 10~100 dry-run
3. commit + PR
4. LOCAL terminal FULL RUN of the same code
5. local artifact 생성
6. 결과 요약만 Cursor/GPT에 전달
7. GPT 독립검증
8. 승인 후 production ingest
```

```text
Cursor FULL DATA EXECUTION = NO
LOCAL FULL DATA EXECUTION  = YES
Cursor responsibility      = IMPLEMENT + TEST + SMALL PROBE
Local responsibility       = DOWNLOAD + FULL COLLECT + FULL JOIN + ARTIFACT
Production responsibility  = NONE until GPT approval
```

Bulk originals are **not** committed to Git.

```text
artifacts/chem04/
  secondary_seed/
  official_current/
  joins/
  manifests/
  checkpoints/
```

`.gitignore` covers `artifacts/chem04/`. Git keeps collection code, schema/constants, manifest **format**, and tests.

---

## 14. Local CLIs

Same code Cursor tests; the operator machine runs the full job.

```bash
# Cursor / CI probe — fixture only
python -m tools.chem04.bootstrap_seed \
  --local-jsonl tests/fixtures/kosha_msds/secondary_seed_sample.jsonl \
  --max-rows 10 \
  --out /tmp/chem04-seed.jsonl \
  --manifest /tmp/chem04-manifest.json

python -m tools.chem04.collect_current_index --max-pages 3

# Local FULL RUN — operator terminal, not the Cursor agent
python -m tools.chem04.bootstrap_seed --download
# or reuse an already downloaded official train.jsonl:
python -m tools.chem04.bootstrap_seed --local-jsonl /path/to/train.jsonl --verify-sha256

python -m tools.chem04.collect_current_index --full --resume --delay 1.0
python -m tools.chem04.diagnose_header_gap --pages 1,4,102,1493,2057
# local full diagnosis after parser fix:
# python -m tools.chem04.diagnose_header_gap --full --delay 1.0
python -m tools.chem04.join_current_identity \
  --official artifacts/chem04/official_current/kosha_current_index.jsonl \
  --seed artifacts/chem04/secondary_identity_seed.jsonl
python -m tools.chem04.report \
  --seed artifacts/chem04/secondary_identity_seed.jsonl \
  --official artifacts/chem04/official_current/kosha_current_index.jsonl
```

Safety:

```text
python -m tools.chem04.bootstrap_seed            → refused (need --local-jsonl or --download)
python -m tools.chem04.collect_current_index     → refused (need --max-pages or --full)
python -m services.kosha_msds.discovery          → refused (need --enable-primary-scan)
```

---

## 15. PATCH-4 source contract (code-ready; full N = LOCAL_RUN_PENDING)

Secondary bootstrap (Hugging Face `Yuyongkim/inconvenience-msds`):

```text
role                    = BOOTSTRAP IDENTITY SEED (not TAI SoT, not FULL_OFFICIAL)
revision                = 5db49df655360dc69cc250ecb41058bf464553fa
train.jsonl bytes       = 882524767
train.jsonl sha256      = 2c342e638e403540076f0e0d13d0018f7671b11747b5a40cb67a5245d13a4227
github HEAD (code repo) = f98915d4d1a89a90083e7b70914cdb1b49e14ccf
advertised rows         = 48966
observed identity fields= chem_id, name_ko, cas_no, name_en
absent                  = lastDate, openYn, KE, UN, EN, snapshot date
sections/braille/body   = DROPPED; production ingest = NO
full unique chemId N    = LOCAL_RUN_PENDING
```

Do not invent `lastDate` comparison from the secondary dataset. Do not force-fit 48,966.

KOSHA official current web index:

```text
https://msds.kosha.or.kr/MSDSInfo/mgr/hub/chemList.do
robots.txt              = 404 (no robots file; not an explicit ban)
identity                = javascript:selectChem('chemId','casNo','chemName')
columns                 = No. / 물질명 / CAS No. / 개정일
listType                = msds
workers                 = 1
pageSize guessing       = FORBIDDEN
header N                = live; do not hardcode
row count per page      = live; last page and some middle pages may be short
full page crawl         = LOCAL_RUN_PENDING
STOP                    = robots deny / CAPTCHA / HTTP 403 / HTTP 429
```

JOIN (deterministic; no fuzzy / LLM):

```text
DIRECT_OFFICIAL_ID > CAS_EXACT unique > NAME_EXACT (NFC/trim/whitespace)
> COMPOUND_EXACT (name_en) > UNMATCHED | AMBIGUOUS
resolved_chem_id        = official chemId when present
present_in_secondary    = official chemId ∈ secondary seed
secondary_chem_id       = null when official-only
full join counts        = LOCAL_RERUN_PENDING after parser fix
```

---

## 16. PATCH-5 — header 20,568 vs parsed 19,870

GPT review `CHG_REQUIRED`. Classification from live HTML probe (pages 1, 4, 102, 1493, 2057), not a second 2,057-page crawl:

```text
data_tr without selectChem     = 0
unpublished/hidden row         = NOT OBSERVED
other onclick                  = NOT OBSERVED
legacy parse [^']* chemName    = DROPS apostrophe names (2,2'-PCB, 4,4'-…)
fixed parse (.*?) chemName     = href count == parsed count on probed pages
page 1493                      = legacy 3 / href 10 / fixed 10
page 4                         = legacy 9 / href 10 / fixed 10
page 102                       = legacy 5 / href 10 / fixed 10
page 2057                      = legacy 7 / href 8 / fixed 8
header 20568                   = consistent with 2056×10 + last page 8
UNEXPLAINED HEADER DELTA       = PARSER_APOSTROPHE_NAME (not force-fit 19870)
CURRENT FULL CENSUS            = CONDITIONAL until local re-collect with fixed parser
```

Report path: `artifacts/chem04/secondary_identity_seed.jsonl` is accepted as a fallback. `--seed` / `--official` / `--join` / `--manifest` override defaults.

```text
python -m tools.chem04.diagnose_header_gap --pages 1,4,102,1493,2057
python -m tools.chem04.collect_current_index --full --delay 1.0
```

Do not resume the 19,870 JSONL after this parser change — start a new `--full` collect (or delete the old artifact first). `--resume` would keep the under-parsed rows.

OpenAPI this PATCH:

```text
API calls this PATCH    = 0
same-day Detail01 retry = FORBIDDEN (quota already observed)
validation runner max   = 100 (later quota window only)
```

---

## STOP

```text
OPENAPI LIST CONTRACT = SEARCH-ONLY
DOCUMENTED FULL ENUMERATION API = NOT AVAILABLE
API_FULL_ENUMERATION = BLOCKED_BY_SOURCE_CONTRACT
DETAIL01_ID_DISCOVERY = PASS / FALLBACK_VALIDATION
EMPIRICAL_API_CENSUS = NOT FULL_OFFICIAL
50-DAY NUMERIC SCAN = NO
CURSOR FULL DATA EXECUTION = NO
LOCAL FULL DATA EXECUTION = YES
FULL INDEX / SEED / JOIN COUNTS = LOCAL_RERUN_PENDING (apostrophe parser fix)
HEADER 20568 vs ROWS 19870 = PARSER_APOSTROPHE_NAME
CURRENT FULL CENSUS = CONDITIONAL
REPORT PATH = FALLBACK + CLI ARGS
INITIAL_SEED_CANDIDATE = BLOCKED
PORTAL 1000/day HARD LIMIT OBSERVED = YES
INITIAL FULL SEED = BLOCKED
SYNC RUNNER = PRESERVED
PRODUCTION INGEST = NO
CHEM-04 = IN_PROGRESS
MERGE = NOT AUTHORIZED
```
