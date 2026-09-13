---
class: records
type: report
scope: knowledge
project: chem
title: OBJ-CHEM-03 corpus enumeration and production quota gate
version: 1
status: active
owner: taiwang
---

# OBJ-CHEM-03 — Official Corpus Enumeration + Production Quota Gate

```text
CHEM-03 = IN_PROGRESS (research/gate only; GPT review before merge)
CHEM-01 = CLOSED / PASS_WITH_INGEST_GATE
CHEM-02 = DONE / CLOSED
CHEM-04 = NOT OPENED
OBJ-RISK = NOT STARTED
FULL_OFFICIAL = STILL BLOCKED
```

This checkpoint does **not** ingest, apply production migration, insert FULL_OFFICIAL snapshots, enable Graph `chemical`, or submit a data.go.kr account action.

---

## 0. Revision guard

```text
CHEM-02 canonical SHA =
0b07cb27b728335fe36a06aa414d21f1597e0c1d
authorized CHEM-03 base / origin/main at branch create =
44f99b2c75a23ad7b1b59ac518964ba25c6c36a6
delta vs CHEM-02 =
1 commit, docs/canonical/test-universe Appendix3 fixture authority freeze only
CHEM impact of that delta =
NO
branch =
feat/obj-chem-03
```

Appendix3 content is out of scope and was not copied or re-verified.

---

## Report card

```text
ENUMERATION_GATE = CONDITIONAL
method           = OFFICIAL_WEB_LIST
reason           = AUTOMATION_RIGHT/CONTRACT_CONFIRMATION_REQUIRED
official complete chemId enumeration = NO
official bulk source                 = NO
N                                    = UNKNOWN
WEB_ADVISORY_COUNT(t2 header)        = 20568
observed_at(t2)                      = 2026-09-14 KST
PRODUCTION ACCOUNT PATH              = CONFIRMED
QUOTA_APPROVAL                       = PENDING_OWNER_ACTION
QPS                                  = UNKNOWN
INCREMENTAL SYNC                     = UNRESOLVED
external inquiry required            = YES
production mutation                  = 0
migration applied                    = NO
Graph mutation                       = 0
existing CHEM tests                  = 34 passed / 0 failed
live OpenAPI re-probe this checkpoint = NO (CHEM-01 evidence reused; quota conserved)
```

---

## A. Official Enumeration Candidates

| method | official source | complete? | reproducible? | chemId available? | automation allowed? | verdict |
|---|---|---|---|---|---|---|
| E1 OpenAPI full list | data.go.kr `15157612` swagger + catalog + DCAT | NO | search-only | YES after a search hit | YES for documented search/detail | **FAIL** |
| E2 Official bulk file | data.go.kr / KOSHA / DCAT | NO | n/a | n/a | n/a | **FAIL** |
| E3 KOSHA web list | `MSDSInfo/mgr/hub/chemList.do` | APPEARS finite in UI | pageIndex GET/POST | YES in `selectChem(chemId,…)` | NOT documented as OpenAPI; hub popup | **CONDITIONAL / NOT APPROVED as FULL_OFFICIAL** |
| E4 Provider export | not yet requested | UNKNOWN | UNKNOWN | intended | only if provider supplies | **PENDING INQUIRY** |

Forbidden methods (not used, not proposed): chemId brute-force, CAS/name combinatorics, `%` wildcard harvest, 2,057-page crawler, “모두보기” `pageSize=100000000` (commented in page source; not invoked).

---

## B. OpenAPI Findings

Official source remains CHEM-01/02 freeze:

```text
dataset_id = 15157612
source_id  = KOSHA_MSDS
host       = apis.data.go.kr/B552468/msdschem
produces   = application/xml
```

Documented paths (swagger, 17 operations, unchanged):

```text
GET /getChemList
GET /getChemDetail01 … /getChemDetail16
```

`getChemList` required query (swagger):

```text
serviceKey, searchCnd, searchWrd, pageNo, numOfRows
```

`searchCnd`: `0` 국문명 / `1` CAS / `2` UN / `3` KE / `4` EN. No extra “all” code.

Bulk / dump-all / index operation: **NOT_FOUND** in swagger, portal HTML, DCAT (`dcat:endpointURL` empty, `dcat:accessURL` empty), or catalog JSON.

Empty search (CHEM-01 live, not re-run):

```text
searchWrd="" → resultCode=00, totalCount=0
```

Pagination: list only. `numOfRows` official max = **UNKNOWN**. CHEM-01: `10` / `100` / `1000` accepted; `1000` returned the full 777-hit `벤젠` name set. Ceiling above 1000 = unmeasured. That is **not** a corpus dump-all.

Undocumented behavior (already frozen; not expanded here): empty `searchWrd` is not an enumerator; `%` is not an official complete enumerator (CHEM-01: 22 hits, not N).

Older dataset `15001197` (KOSHA-hosted `msds.kosha.or.kr/openapi/service/msdschem/chemlist`) is a predecessor listing, not the CHEM catalog SoT. CHEM-03 does not switch sources. English portal copy for that older id still describes search-required `chemlist`, not dump-all. Current `data.go.kr/data/15001197/openapi.do` returned **404**.

Attached official document on `15157612`:

```text
한국산업안전보건공단_물질안전보건자료_오픈API활용가이드.hwp
download = portal fn_fileDownload('FILE_000000003696754','1')
```

Login-gated. Not retrieved in this checkpoint (no portal login). Filename is a **usage guide**, not a chemical master file.

---

## C. KOSHA Web Findings

Inspected only three pages (no crawl):

```text
page 1     GET  /MSDSInfo/mgr/hub/chemList.do
middle     GET+POST pageIndex=1029
last       GET+POST pageIndex=2057
```

```text
observed_at            = 2026-09-14 KST
WEB_ADVISORY_COUNT     = 20568   (header 총 N건)
observed_pages         = 2057
page_size              = 10
last_page_rows         = 7
last_page arithmetic   = 2056×10 + 7 = 20567
header vs arithmetic   = 20568 ≠ 20567
prior operator observe = 20567 / 2057 pages
```

Name this value **WEB_ADVISORY_COUNT**. Do **not** store it as `expected_count`, official snapshot count, or FULL_OFFICIAL N.

Count drift:

```text
t1 operator WEB_ADVISORY_COUNT ≈ 20567
t2 CHEM-03 header              = 20568
t2 last-page arithmetic        = 20567
```

Difference is **not an error**. It is evidence the web total is a live advisory and that even header vs last-page arithmetic is not a frozen contract. Snapshot window design must assume source drift.

Row identity:

```text
javascript:selectChem('{chemId}','{casNo}','{chemName}')
```

Examples:

```text
page 1 first  chemId=009098  CAS=37-87-6
page 1        chemId=000001  염산 구아니딘  (not list position 1)
page 1029     chemId=038597
page 2057 last chemId=047134  CAS empty
```

`047134` CAS-null matches the CHEM-01 OpenAPI observation. `chemId` is present. List order is **not** dense `000001…N`. Sequential chemId guessing is invalid.

Network / contract:

```text
HTML server-rendered
form POST action = /MSDSInfo/mgr/hub/chemList.do
GET ?pageIndex=N also returns the same page
hidden listType=msds
jquery-1.3 only; no list JSON/XHR on this page
page is a hub popup (opener.document / self.close)
OpenAPI/swagger mention = ABSENT
automation-rights document = NOT_FOUND
```

Commented source contains `option value="100000000">모두보기</option>` but that control is **commented out** and was **not** invoked.

Verdict for E3: useful **contract discovery / count cross-check** only. Not an approved FULL_OFFICIAL enumerator until KOSHA/portal confirm machine-to-machine use.

---

## D. Bulk/File Findings

```text
available              = NOT FOUND for KOSHA MSDS catalog
15157612 distributions = OpenAPI XML only (DCAT has no file accessURL)
KOSHA 자료실 master    = NOT FOUND as chemId bulk
format / count / freq  = n/a
```

Related files that are **not** this corpus:

- `15091887` KOSHA 민간위탁 취급물질 CSV (1회성, not chemId catalog)
- 화학물질안전원 file/OpenAPI (different provider)
- 한국가스공사 MSDS file (workplace product MSDS, not KOSHA catalog)

---

## E. Enumeration Verdict

```text
ENUMERATION_GATE = CONDITIONAL
method           = OFFICIAL_WEB_LIST
reason           = AUTOMATION_RIGHT/CONTRACT_CONFIRMATION_REQUIRED
```

FULL_OFFICIAL remains **blocked**. Acceptance A–H are not jointly satisfied:

| clause | status |
|---|---|
| A official provider-backed | web UI yes; OpenAPI dump-all no |
| B finite | UI shows a finite page count |
| C complete | NOT VERIFIED (header≠last-page arithmetic; no omission test) |
| D reproducible | pageIndex reproducible as HTML, not as a published API contract |
| E every chemId obtainable | technically present per row; harvesting 2,057 pages is forbidden here |
| F no guessed identifiers | web rows carry chemId; brute-force IDs would guess |
| G omission checkable | NOT without a provider census or approved enumerator |
| H snapshot source count | web header is WEB_ADVISORY_COUNT only |

Preferred future split (not implemented):

```text
OFFICIAL BULK/INDEX  → chemId enumeration
OpenAPI detail 01-16 → hydration
```

---

## F. Quota Model

`N` is **UNKNOWN**. Do not freeze 20568.

Formula:

```text
DETAIL_CALLS        = 16 × N
ENUMERATION_CALLS   = official enumerator cost (currently UNKNOWN / NOT_FOUND)
VALIDATION_CALLS    = sample round-trip after seed (suggest ≥ 16)
TOTAL_INITIAL_CALLS = ENUMERATION_CALLS + (16 × N) + VALIDATION_CALLS
```

Simulation only (`N` not frozen), using t2 header 20,568:

```text
SIMULATION ONLY
16 × 20,568 = 329,088 detail calls
if a 1,000-row official list dump existed: ceil(20568/1000) = 21 list calls
VALIDATION_CALLS example = 16
TOTAL ≈ 329,125
```

Development quota:

```text
dev quota = 1,000 / day
329,125 / 1,000 ≈ 330 days
development account = NOT FEASIBLE for full initial detail load
```

Do **not** treat multi-day brute ingest on the 개발계정 as the solution (source drift, acquisition window, retry, mismatch with operational traffic model).

Acquisition window if a production quota `Q` exists:

```text
minimum_days = ceil(TOTAL_INITIAL_CALLS / Q)
```

FULL_OFFICIAL must not be oversold as a point-in-time exact snapshot of every detail field. A future definition may be:

```text
complete identity set captured at enumeration time
details acquired during a bounded acquisition window
```

Not implemented in CHEM-03.

---

## G. Production Account

Dataset `15157612` portal page (cached official HTML, CHEM-01 capture still matching CHEM-03 re-read):

```text
current stage inspected     = NO (no data.go.kr login)
documented path             = YES
개발단계                    = 자동승인
운영단계                    = 심의승인
개발계정 트래픽             = 1,000 / day
운영계정 트래픽             = 활용사례 등록 시 신청하면 트래픽 증가 가능
numeric default ops quota   = NOT STATED on this dataset page
QPS numeric cap             = UNKNOWN (resultCode 23 exists; value unpublished)
traffic increase fields     = 운영계정 신청 시 활용자가 필요 트래픽 작성 (portal-wide procedure)
활용사례 등록               = 운영 전환에 필요
account mutation this step  = NOT SUBMITTED
```

```text
PRODUCTION ACCOUNT PATH = CONFIRMED
QUOTA_APPROVAL          = PENDING_OWNER_ACTION
```

---

## H. Application Draft (do not submit in CHEM-03)

제출 직전 완성본. 계정 credential / 사업자등록번호 / 담당자 개인정보는 비워 둔다. 사용자가 포털 마이페이지에서 운영계정·활용사례 화면에 붙여 넣을 문안이다.

### 서비스명

```text
TAI Safe
```

### 활용목적

```text
산업현장의 화학물질 안전정보를 KOSHA 공식 참고정보와 연계하여 제공하는
산업안전관리 SaaS입니다.

본 서비스는 한국산업안전보건공단 화학물질정보(공공데이터포털
「한국산업안전보건공단_물질안전보건자료 조회 서비스」, dataset 15157612)를
사업장 참고정보로 표시합니다.

명확히 하지 않는 것:
- KOSHA MSDS를 법적 MSDS 원본으로 대체하지 않습니다.
- 제조·수입·공급자가 제공한 최신 MSDS 확인을 안내합니다.
- 화면과 응답에 KOSHA 출처를 표시합니다.
```

### 필요 트래픽 (evidence/formula)

일일 신청값은 운영자가 `N`과 허용 acquisition days `D`를 고른 뒤 계산한다.

```text
Q_day >= ceil( (ENUMERATION_CALLS + 16N + VALIDATION_CALLS) * 1.10 / D )
```

`1.10` = retry margin (rate-limit 22/23, transport). 공식 enumerator가 아직 없으므로 ENUMERATION_CALLS는 문의 회신 후 채운다.

시뮬레이션 (`N=20568` **not frozen**, `VALIDATION_CALLS=16`):

| D (days) | detail-dominated Q_day before retry | +10% retry |
|---:|---:|---:|
| 1 | 329,104 | ≈ 362,000 |
| 4 | 82,276 | ≈ 90,500 |
| 7 | 47,015 | ≈ 51,800 |

권고: 초기 적재 창을 짧게 유지하려면 **일 400,000건 전후를 신청 검토**하고, 안정화 후 정상 동기화량으로 낮춘다. 포털이 운영 기본치를 강제하면 그 기본치와 `ceil(TOTAL/Q)` 일수를 다시 계산한다. **CHEM-03는 이 숫자를 제출하지 않는다.**

### 초기 vs 정상

```text
initial seed  = 공식 identity set 1회 + chemId당 detail 16
steady-state  = INCREMENTAL_SYNC 미해결. lastDate만으로는 부족.
peak/day      = initial seed 창의 Q_day
average/day   = seed 이후에는 미확정 (재열거 계약 필요)
```

### 심의 설명에 넣을 범위

```text
호출 대상: getChemList (검색/열거가 공식 제공되는 범위) 및 getChemDetail01-16
저장: 참고용 catalog. 법적 MSDS 원본 대체 아님
공개: TAI Safe 가입 사업장 안전관리 화면 (출처 표시)
```

---

## I. Incremental Sync

```text
INCREMENTAL_SYNC = UNRESOLVED
```

`lastDate` exists on list items. That is **not** enough.

Missing required piece:

```text
전체 identity/header 집합을 낮은 cost로 다시 열거하는 공식 방법
```

No `updated-since` parameter in swagger. No dated bulk snapshot. Therefore:

```text
lastDate alone != incremental enumeration
```

---

## J. Risks / Blocks

```text
1. No documented OpenAPI dump-all → FULL_OFFICIAL cannot be opened from E1.
2. No official chemId bulk file → E2 closed.
3. KOSHA hub chemList.do is undocumented for automation → harvesting it is NOT APPROVED.
4. WEB_ADVISORY_COUNT drifts (20567/20568) and header≠last-page arithmetic.
5. 개발계정 1,000/day cannot seed ~16N details.
6. 운영계정은 심의승인 + 활용사례 + 트래픽 신청. 승인 전 production ingest 금지.
7. QPS unpublished; resultCode 23 exists → throttle design required even after daily quota.
8. chemId values are not a dense 1..N range → guessing IDs is both forbidden and incomplete.
9. kosha_msds_chemicals.is_current is unused by kosha_msds_current; revisit at production-migration preflight, not now.
```

---

## Source contact / inquiry draft (do not send)

수신: 한국산업안전보건공단 디지털계획부 (052-703-0291) 및 공공데이터포털 1566-0025  
데이터: 한국산업안전보건공단_물질안전보건자료 조회 서비스 (15157612)

```text
1. 전체 화학물질을 누락 없이 열거할 수 있는 공식 API operation이 있습니까?
   (현재 getChemList는 searchCnd/searchWrd 필수, searchWrd="" → totalCount=0)
2. 없다면 전체 chemId 목록 또는 정기 bulk export를 제공할 수 있습니까?
3. 웹 MSDS 전체목록(MSDSInfo/mgr/hub/chemList.do)을
   시스템 간 자동연계 목적으로 사용하는 것이 허용됩니까?
4. 약 2만 건 규모 전체 초기 동기화를 위한 권장 OpenAPI 방식은 무엇입니까?
5. 초기 적재 및 정기 갱신을 위해 운영계정 일일 traffic을
   어느 수준으로 신청해야 합니까?
6. 별도 QPS 제한/증설 절차가 있습니까?
```

---

## Production baseline (SELECT-only, 2026-09-14)

project_ref `vwlahtguyggrhvslabax`:

```text
factory_materials       = 0
master_dangerous_goods  = 49
Graph active edges      = 11,776
Graph evidence          = 11,776
chemical Graph edges    = 0
kosha_msds_* objects    = NULL (not applied)
```

---

## Tests

```text
python3 -m pytest tests/test_kosha_msds_catalog.py -q --tb=line
34 passed / 0 failed
```

CHEM-02 code was not modified.

---

## STOP

```text
production migration apply = NO
production ingest          = NO
FULL_OFFICIAL snapshot     = NO
public chemical API        = NO
factory-material linking   = NO
Graph chemical enable      = NO
account application submit = NO
inquiry send               = NO
CHEM-04                    = NOT OPENED
```
