---
class: records
type: report
scope: knowledge
project: chem
title: OBJ-CHEM-01 KOSHA MSDS source contract identity and minimal probe
version: 1
status: active
owner: taiwang
---

# OBJ-CHEM-01 — Source Contract + Identity + Minimal Probe

> Operator-requested basename `OBJ_CHEM01_SOURCE_CONTRACT_AND_PROBE.md` was adjusted to `OBJ_chem01-source-contract-and-probe_v1.md` for DOC-RULE-020.
> CHEM-01 status = **CONDITIONAL** (official source/contract/probe/identity strategy measured; full-corpus API total and dump-all enumeration not measured).
> This checkpoint does not implement ingest, schema, public API, WWW, factory linking, or Graph chemical enable.

```text
WAVE4   = IN_PROGRESS
OBJ-CSI  = DONE / CLOSED  (untouched)
OBJ-CHEM = STARTED
  CHEM-01 = CONDITIONAL
OBJ-RISK = NOT STARTED
Graph chemical relation = DISABLED (unchanged)
Production mutation     = 0
```

---

## 0. Revision guard

```text
repo   = taiengineering/tai-api
branch = origin/main
HEAD   = 501a583eb238e8d0ccecdda01ee0d602ac701693
```

Measured 2026-09-13 from `origin/main` after `git fetch`. **Matches the authorized SHA.** No reset.

Delta since OBJ-CSI apply SHA `2444f8e10987d37dc2544ccf9b9e19129275d0f3`:

```text
501a583e docs(test-universe): record Obs-007 crane object analysis (#342)
```

Docs-only. Not a chemical/Graph/CSI mutation.

Worktree used for this report: `/Users/taiwangsim/Desktop/tai-api-obj-chem` at detached `501a583e`. Dirty `/Users/taiwangsim/Desktop/tai-api` (`feat/free-result-additional-information`) was not used.

---

## A. Source

```text
source_id     = KOSHA_MSDS
provider      = 한국산업안전보건공단
dataset       = 한국산업안전보건공단_물질안전보건자료 조회 서비스
dataset_id    = 15157612
official URL  = https://www.data.go.kr/data/15157612/openapi.do
kosha UI      = https://msds.kosha.or.kr/MSDSInfo/
format        = XML
API type      = REST
registered    = 2026-03-13
modified      = 2026-08-06
license       = 이용허락범위 제한 없음
dev quota     = 1,000 / day
ops quota     = 활용사례 등록 후 증설 신청
deliberation  = 개발=자동승인 / 운영=심의승인
contact       = 디지털계획부 052-703-0291
OpenAPI apply = 공공데이터포털 1566-0025
```

Official catalog JSON (`https://www.data.go.kr/catalog/15157612/openapi.json`) repeats the same name, dates, XML encoding, license, and KOSHA disclaimer.

### Role (frozen)

```text
PUBLIC / REFERENCE CHEMICAL KNOWLEDGE
```

Not:

```text
사업장 실제 보유 MSDS 원본
제조자/수입자 제공 MSDS
법적 제출 MSDS의 대체물
TAI Legal Engine applicability / obligation verdict
```

Official dataset description (portal swagger `info.description`, measured):

- Coverage is 산업안전보건법 제104조 유해인자 분류기준 대상 물질/혼합물 (시행령 제86조 제외).
- KOSHA chemical information is **MSDS 작성·검토 참고용만**.
- 산업안전보건법 제110조·제111조에 따른 MSDS 작성·제공 의무는 제조·수입자에게 있다.

TAI display principle:

```text
KOSHA 화학물질정보를 기반으로 한 참고정보.
사업장에서 사용하는 실제 제품의 MSDS는 제조·수입·공급자로부터
제공받은 최신 MSDS를 확인해야 한다.
```

### Existing DB boundary (production read, 2026-09-13)

```text
factory_materials      = 0
master_dangerous_goods = 49
Graph active edges     = 11,776
Graph evidence         = 11,776
CSI READY              = 37,157
CSI HOLD               = 39
```

`factory_materials` = 고객/사업장 inventory. `master_dangerous_goods` = 위험물 법정 분류 master. **Neither is KOSHA chemical catalog SoT.** New catalog is a separate object. CHEM-01 did not migrate.

### Existing Graph boundary

`services/knowledge_graph_rules.py` at this HEAD:

```text
CONTEXT_RELATION_TYPES includes chemical
DISABLED_RELATIONS     = {"chemical", "legal_obligation"}
```

CHEM-01 did **not** enable `chemical`, add rules, dry-run, or apply. Graph SoT unchanged.

### Existing code divergence (do not fix in CHEM-01)

`routers/kosha_apis.py` already exposes `/kosha/msds` against `B552468/msdschem`, but request params are **stale vs official 15157612 swagger**:

| live adapter | official swagger / probe |
|---|---|
| `chemNm`, `casNo` | `searchCnd` + `searchWrd` |
| `kmcNo` | `chemId` |
| tries JSON then XML | official `produces: application/xml` |

Treat the live adapter as a convenience search wrapper, **not** the CHEM catalog contract.

---

## B. API Contract

Measured from official portal page swagger embedded in `https://www.data.go.kr/data/15157612/openapi.do` (2026-09-13 HTML) plus live XML probes.

```text
host      = apis.data.go.kr/B552468/msdschem
base URL  = https://apis.data.go.kr/B552468/msdschem
auth      = query serviceKey (공공데이터포털 일반 인증키)
schemes   = https, http
produces  = application/xml
root      = response
success   = header.resultCode=00 / resultMsg=NORMAL SERVICE.
```

### Operations (17)

| operation | role | required query |
|---|---|---|
| `GET /getChemList` | 화학물질 목록 검색 | `serviceKey`, `searchCnd`, `searchWrd`, `pageNo`, `numOfRows` |
| `GET /getChemDetail01` … `16` | MSDS 16개 항목 상세 | `serviceKey`, `chemId` |

There is **no** dump-all / catalog-export operation.

`searchCnd` (official):

```text
0 = 국문명
1 = CAS No
2 = UN No
3 = KE No
4 = EN No
```

Pagination: `pageNo` + `numOfRows` on list only. Detail operations are `chemId`-scoped, no page.

`numOfRows` official max = **UNKNOWN** (not in swagger). Probe: `10`, `100`, `1000` all accepted. `numOfRows=1000` returned 777 items (full `벤젠` name-search set). Ceiling above 1000 = unmeasured.

### List response fields (swagger + probe)

| field | swagger | probe list item |
|---|---|---|
| `chemId` | PRESENT integer “화학물질ID” | PRESENT, zero-padded string e.g. `001008` |
| `chemNameKor` | PRESENT | PRESENT |
| `casNo` | PRESENT | PRESENT or XML-omitted |
| `keNo` | PRESENT | PRESENT or XML-omitted |
| `enNo` | PRESENT | PRESENT or XML-omitted |
| `unNo` | PRESENT | PRESENT or XML-omitted; format mixed (`1114` vs `UN3082`) |
| `lastDate` | PRESENT 최종 갱신일 | PRESENT `YYYY-MM-DD` |
| `openYn` | PRESENT | PRESENT as empty string in sample |
| `koshaConfirm` | PRESENT | PRESENT as empty string in sample |
| `totalCount` / `pageNo` / `numOfRows` | PRESENT on body | PRESENT |
| English name | ABSENT on list | ABSENT on list |

Empty optional identifiers are often **omitted as XML elements**, not sent as `""`. Parser must treat missing tag as NULL.

### Detail response fields (all 16 ops share this item schema)

Swagger item: `itemDetail`, `lev`, `msdsItemCode`, `upMsdsItemCode`, `msdsItemNameKor`, `msdsItemNo`, `ordrIdx`.

| field | swagger | benzene detail probe |
|---|---|---|
| `msdsItemNameKor` | PRESENT | PRESENT |
| `msdsItemCode` | PRESENT | PRESENT (e.g. `A02`, `B0402`, `O02`) |
| `upMsdsItemCode` | PRESENT | PRESENT |
| `lev` | PRESENT 1–3 | PRESENT |
| `ordrIdx` | PRESENT | PRESENT |
| `itemDetail` | PRESENT | PRESENT **or XML-omitted** (08/09/12 heading rows) |
| `msdsItemNo` | PRESENT 항목구분 | ABSENT in benzene XML |

Detail is a **nested label tree**, not typed GHS/CAS columns. GHS pictograms arrived as gif filenames (`GHS02.gif|GHS07.gif|...`), not structured codes.

### Detail sections (official summaries; all 16 returned HTTP 200 / `00` for benzene `chemId=001008`)

| op | section | benzene item rows |
|---|---|---:|
| 01 | 화학제품과 회사에 관한 정보 | 8 |
| 02 | 유해성·위험성 | 11 |
| 03 | 구성성분의 명칭 및 함유량 | 4 |
| 04 | 응급조치요령 | 5 |
| 05 | 폭발·화재시 대처방법 | 3 |
| 06 | 누출사고시 대처방법 | 3 |
| 07 | 취급 및 저장방법 | 2 |
| 08 | 노출방지 및 개인보호구 | 11 |
| 09 | 물리화학적 특성 | 21 |
| 10 | 안정성 및 반응성 | 4 |
| 11 | 독성에 관한 정보 | 26 |
| 12 | 환경에 미치는 영향 | 12 |
| 13 | 폐기시 주의사항 | 2 |
| 14 | 운송에 필요한 정보 | 8 |
| 15 | 법적 규제현황 | 20 |
| 16 | 그 밖의 참고사항 | 6 |

### Candidate domain inventory vs API (list + benzene details)

Verdict is **PRESENT / ABSENT / UNKNOWN**. UNKNOWN = not a dedicated field; may exist only inside free-text `itemDetail`.

| candidate | verdict | evidence |
|---|---|---|
| 물질명(국문) | PRESENT | list `chemNameKor`; detail01 제품명 |
| 영문명 | ABSENT as dedicated field | not on list; benzene 이명 empty |
| CAS No. | PRESENT | list `casNo`; detail03 `CAS 번호` |
| KE No. | PRESENT | list `keNo` (may omit) |
| UN No. | PRESENT | list `unNo`; detail14 유엔번호 |
| EN No. | PRESENT | list `enNo` (may omit) |
| 공식 물질 식별자 | PRESENT | `chemId` |
| 개정일 | PRESENT | list `lastDate`; detail16 최종 개정일자 |
| GHS classification | PRESENT as text | detail02 유해성·위험성 분류 |
| hazard statement | PRESENT as text | detail02 유해·위험문구 |
| precautionary statement | PRESENT as text | detail02 예방조치문구 |
| pictogram | PRESENT as gif filename list | detail02 그림문자 |
| signal word | PRESENT as text | detail02 신호어 |
| physical/chemical properties | PRESENT as tree | detail09 |
| exposure limits | PRESENT as tree | detail08 (many rows omit `itemDetail`) |
| toxicity | PRESENT as tree | detail11 |
| first aid | PRESENT as tree | detail04 |
| handling/storage | PRESENT as tree | detail07 |
| PPE | PRESENT as tree | detail08 개인보호구 |
| fire fighting | PRESENT as tree | detail05 |
| spill response | PRESENT as tree | detail06 |
| transport | PRESENT as tree | detail14 |
| regulatory information | PRESENT as **source text** | detail15. Not TAI Legal Engine |

### Error contract (portal, not guessed)

Gateway / auth codes published on the dataset page:

| code | message |
|---|---|
| 10 | INVALID_REQUEST_PARAMETER_ERROR |
| 12 | NO_OPENAPI_SERVICE_ERROR |
| 20 | SERVICE_KEY_IS_NULL / PERMISSION_DENIED / SERVICE_ACCESS_DENIED_ERROR |
| 22 | LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR (일일) |
| 23 | LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR (초당) |
| 29 | BLACKLIST_IP_ACCESS_ERROR |
| 30 | SERVICE_KEY_IS_NOT_REGISTERED_ERROR |
| 31 | DEADLINE_HAS_EXPIRED_ERROR |

Success in probe: `00` / `NORMAL SERVICE.`

Per-second numeric cap = **UNKNOWN** (code 23 exists; QPS not published).
Daily cap = **1,000** on 개발계정 (portal “신청 가능 트래픽”).

Transport note (existing tai-api): Railway uses `services.kr_public_api.kr_get` (Korea proxy + curl_cffi). CHEM probes used that path. Direct laptop httpx without env failed.

---

## C. Probe

Official OpenAPI only. No HTML scrape. `serviceKey` not recorded.

```text
probe date     = 2026-09-13
base           = https://apis.data.go.kr/B552468/msdschem
call count     = 27  (24 primary + 2 extra list + 1 CAS-null rescan of 벤젠 1000)
HTTP           = 200 on all recorded calls
resultCode     = 00 on all recorded calls
```

### C1. benzene / CAS `71-43-2` / `searchCnd=1`

```text
operation = getChemList
params    = searchCnd=1 searchWrd=71-43-2 pageNo=1 numOfRows=10
totalCount= 1
itemCount = 1
chemId    = 001008
chemNameKor = 벤젠
casNo     = 71-43-2
keNo      = KE-02150
enNo      = 200-753-7
unNo      = 1114
lastDate  = 2025-09-17
```

All 16 `getChemDetailNN` with `chemId=001008` succeeded. Sample values (truncated):

- 01 제품명 = `벤젠`
- 02 분류 = `인화성 액체 : 구분2|피부 부식성/피부 자극성 : 구분2|...|발암성 : 구분1B|...`
- 02 신호어 = `위험`
- 02 그림문자 = `GHS02.gif|GHS07.gif|GHS08.gif|GHS09.gif`
- 03 함유량 = `100%`
- 15 산안법 = `작업환경측정대상물질 ...|특별관리물질|...` (**source text, not TAI verdict**)

### C2. toluene / CAS `108-88-3` / `searchCnd=1`

```text
totalCount = 1
chemId     = 001032
chemNameKor= 톨루엔
casNo      = 108-88-3
keNo       = KE-33936
enNo       = 203-625-9
unNo       = 1294
lastDate   = 2025-08-08
```

`numOfRows=100` and `1000` still returned 1 item (parameter accepted).

### C3. special / name `신나` / `searchCnd=0`

Purpose: weak matching / non-substance product name.

```text
totalCount = 2
```

Hits were **not** paint thinner:

| chemId | chemNameKor | casNo |
|---|---|---|
| 046091 | 사리노마이신나트리움 | 55721-31-8 |
| 004051 | 다이하이드록시에틸글리신 나트륨 | 139-41-3 |

Name search is **substring**. `신나` matched `나트륨`. This is factory-material linkage risk, not a catalog identity failure.

### Additional list measurements

| probe | totalCount | notes |
|---|---:|---|
| `searchCnd=0 searchWrd=벤젠 numOfRows=20` | 777 | 에틸벤젠/아조벤젠 등 부분문자열 |
| `searchCnd=0 searchWrd=벤젠 numOfRows=1000` | 777 | 777 items returned; 1 CAS-null |
| `searchCnd=0 searchWrd=` (empty) | 0 | **no dump-all** |
| `searchCnd=0 searchWrd=%` | 22 | not a corpus dump |
| `searchCnd=0 searchWrd=가 numOfRows=10` | 218 | prefix/substring; 가솔린, 아가로오스, … |

CAS-null row inside `벤젠` name search (mixture/reaction product):

```text
chemId      = 047134
chemNameKor = 아닐린과 1,4-비스(클로로메틸)벤젠의 공중합체와 2,5-퓨란디온의 반응생성물
casNo       = XML omitted
lastDate    = 2018-04-02
```

In that 777-row page: `unique chemId = 777`, CAS duplicates = 0, CAS null = 1, KE omitted = 198, EN omitted = 255, UN omitted = 461.
`chemId` range in that page: `000140` … `455683` (not a dense 1..N catalog).

---

## D. Corpus

```text
KOSHA web UI reference baseline ≈ 20,568종   (operator-supplied; not this probe’s SoT)
API dump-all totalCount          = NOT AVAILABLE
empty searchWrd totalCount       = 0
API reported totals              = per-search only (e.g. 벤젠=777, 가=218, exact CAS=1)
difference                       = UNKNOWN (no API census)
```

Do not treat 20,568 as ingest N until an official dump or a measured unique-`chemId` census exists.

---

## E. Identity

### Official stable source id?

```text
YES. chemId
```

Swagger: integer 화학물질ID. Probe: stable zero-padded identifier used as the only required detail key. Unique in the 777-row name-search page.

Recommended (strategy A):

```text
source_id   = KOSHA_MSDS
source_key  = chemId            # official, do not pad/unpad in identity
content_id  = CHEM:<internal immutable UUID>
cas_no / ke_no / en_no / un_no / chem_name_kor = attributes / indexes
identity_status = READY when chemId present
identity_status = HOLD  when chemId missing (not observed in this probe)
```

Forbidden:

```text
CAS:<value>:1 suffix
name hash identity
row number identity
search-order identity
```

### CAS

```text
CAS as primary key     = NO
CAS unique in sample   = YES for exact CAS search (benzene 1, toluene 1)
CAS unique in 벤젠*777 = YES among non-null CAS (0 duplicates)
CAS NULL               = YES, observed (chemId 047134 copolymer/reaction product)
CAS format variants    = UNKNOWN at corpus scale
```

CAS is an index, not identity. Missing CAS with present `chemId` → READY on `chemId`, CAS attribute NULL. Do not HOLD solely for missing CAS if `chemId` exists.

### HOLD policy

HOLD when source identity is ambiguous **after** `chemId` is applied — e.g. chemId missing/unparseable, or two current snapshot rows claiming the same chemId with conflicting payload (not observed). Do not HOLD mixtures just because CAS is null.

---

## F. Proposed Schema (DDL not executed)

Naming follows existing `kosha_*` / CSI snapshot pattern rather than `chemical_source_*`.

### `kosha_msds_cases`

Identity only. No current payload.

| column | notes |
|---|---|
| `content_id` PK | `CHEM:{uuid}` |
| `source_id` | `'KOSHA_MSDS'` |
| `source_key` | `chemId` text, unique |
| `identity_status` | `READY` / `HOLD` |
| `identity_reason` | HOLD reason |
| `first_seen_at` / `updated_at` | |

### `kosha_msds_snapshots`

One fetch/sync attempt.

| column | notes |
|---|---|
| `id` | snapshot uuid |
| `status` | `RUNNING` / `COMPLETED` / `FAILED` |
| `source_id` | `KOSHA_MSDS` |
| `source_contract_version` | e.g. `KOSHA_MSDS_OPENAPI_V1` (15157612 swagger 1.0.0) |
| `fetched_at` / `started_at` / `completed_at` | |
| `source_count` | unique chemId in snapshot |
| `api_call_count` | |
| `failure_reason` | |
| `r2_written` | default false; CHEM-01/02 must not require R2 |

### `kosha_msds_snapshot_items`

| column | notes |
|---|---|
| `(snapshot_id, source_key)` PK | |
| `content_id` | FK cases |
| `identity_status` / `identity_reason` | snapshot-scoped truth |
| `cas_no` / `ke_no` / `en_no` / `un_no` | nullable attributes |
| `chem_name_kor` | |
| `last_date` | source `lastDate` |
| `open_yn` / `kosha_confirm` | as received |
| `list_raw_json` | getChemList item |
| `detail_raw_json` | map of section `01`–`16` item arrays |
| `source_content_hash` | see § hash |
| `in_current_snapshot` | optional; CSI used current **view** instead |

### `kosha_msds_current`

View = latest `COMPLETED` snapshot membership. Same pattern as `csi_accident_current`.

### Not in this catalog

- `factory_materials` (customer inventory)
- `master_dangerous_goods` (법정 위험물 분류)
- Legal Engine tables

Future join (not implemented):

```text
factory_materials → chemical_match → kosha_msds_current
match status: MATCHED | AMBIGUOUS | UNMATCHED | MANUAL_CONFIRMED
```

`신나` probe shows automatic exact name match is unsafe.

---

## G. Ingest feasibility

### Call model (measured operations only)

Per chemical already identified by `chemId`:

```text
detail calls = 16
list calls   = 0 or 1 (discovery only)
```

Full catalog:

```text
dump-all list            = NOT POSSIBLE (empty searchWrd totalCount=0)
unique chemId census     = NOT MEASURED
if N were known:
  detail_calls = 16N
  list_calls   = UNKNOWN (no official enumerator)
```

Using operator web baseline **only as a planning ceiling**, not SoT:

```text
N_ref                 ≈ 20,568
detail_calls_if_N_ref = 329,088
dev quota 1,000/day   → ≥ 329 days of detail-only traffic
plus discovery        → more
```

```text
개발계정 소요일     = NOT sufficient for full ingest
운영계정            = REQUIRED before full production ingest
incremental by date = NOT in official parameters
lastDate            = PRESENT on list items; usable only after re-fetch/compare
per-second limit    = EXISTS (code 23); QPS number UNKNOWN → throttle required
numOfRows=1000      = accepted; reduces list pages but does not create dump-all
```

Name-search enumeration (`가`, `벤젠`, …) overlaps and is substring-based. Summing `totalCount` across queries **overcounts**. Do not build corpus N that way.

CHEM-02 must not start full ingest on 개발계정.

---

## H. Risks

| risk | measured fact | implication |
|---|---|---|
| license | 이용허락범위 제한 없음 | reuse allowed; still attribute KOSHA / data.go.kr |
| legal disclaimer | portal + 산안법 110/111 | TAI must label **참고정보**; never substitute workplace MSDS |
| Legal Engine mix | detail15 is source regulatory prose | do not copy into applicability/obligation |
| identity | `chemId` exists; CAS nullable | CAS is index |
| mixture | CAS-null copolymer row + 100% benzene composition rows | keep chemId; HOLD only if chemId missing |
| name ambiguity | `벤젠`→777; `신나`→나트륨 | factory match cannot be exact-name |
| API quota | 1,000/day dev; ops 심의 | full ingest blocked on 개발계정 |
| update detection | `lastDate` only; no since-param | hash + snapshot compare |
| UN/CAS format | `1114` vs `UN3082`; XML omits empties | normalize as derived; persist raw |
| pictogram | gif filenames | store as source string; do not fetch KOSHA HTML assets in CHEM-01/02 unless separately contracted |
| stale adapter | `/kosha/msds` params ≠ swagger | do not treat live router as catalog SoT |
| Graph | `chemical` DISABLED | keep disabled until a later OBJ |
| CSI | closed | no reopen |

### Normalization proposal (rules only, not implemented)

- Persist **raw** `casNo`/`keNo`/`unNo`/`chemNameKor`/`itemDetail`.
- Derived columns: CAS hyphen-normalized, UN digits-only, KE uppercased, name whitespace collapsed.
- CAS checksum: compute `cas_checksum_ok` boolean. **Invalid checksum ≠ auto-discard.**
- Korean/English: list has no English; aliases live in detail03 이명 when present.
- NULL vs blank: missing XML tag → SQL NULL. Empty `itemDetail` on a present row → empty string.

### Content hash proposal

```text
source_content_hash = SHA256(canonical JSON of:
  chemId, casNo, keNo, enNo, unNo, chemNameKor, lastDate,
  openYn, koshaConfirm,
  detail sections 01-16 ordered by (section, ordrIdx, msdsItemCode, itemDetail)
)
```

Exclude: `fetched_at`, `snapshot_id`, TAI `content_id`, local timestamps, `serviceKey`.

---

## Mutation boundary (this checkpoint)

```text
production DB write        = 0
Graph write                = 0
R2 write                   = 0
Legal Engine write         = 0
factory_materials          = 0 (unchanged)
master_dangerous_goods     = 49 (unchanged)
CSI READY/HOLD             = 37157 / 39 (unchanged)
code implementation        = 0
DDL                        = 0
```

Local probe scripts lived in `/tmp/obj-chem01/` and were **not committed**.

---

## CHEM-01 exit

| criterion | result |
|---|---|
| Official source confirmed | PASS |
| License confirmed | PASS |
| API contract confirmed | PASS (swagger + probe) |
| Minimal probe success | PASS |
| Actual fields known | PASS |
| Identity strategy evidence-based | PASS (`chemId`) |
| Full-ingest call model known | **CONDITIONAL** (16N if N known; N not API-measured; dump-all absent) |
| Schema proposal complete | PASS (not applied) |
| Production mutation = 0 | PASS |

```text
CHEM-01 = CONDITIONAL
CHEM-02 = NOT OPEN
```

Stop. GPT independent review required before CHEM-02 (schema migration / ingest / public / WWW / Graph enable).
