---
class: records
type: report
scope: knowledge
project: chem
title: OBJ-CHEM-04 secondary content bootstrap Decision Gate
version: 5
status: active
owner: taiwang
---

# OBJ-CHEM-04 — Secondary Content Bootstrap Decision Gate

```text
WO-CHEM-04-BOOTSTRAP-DECISION-001 = EVIDENCE COMPLETE / POLICY BLOCKED
WO-CHEM-04-OPTIONC-LIVE-SAMPLE-001 = BLOCKED
WO-CHEM-04-OPTIONC-FETCH-DIAG-001 = FAIL / QUOTA STOP
WO-CHEM-04-CONTENT-LOCAL-001      = PASS
PR #359                           = OPEN / UNMERGED
current HEAD                      = 65f0efdc56db5f299b92c6fe82866ea19045f057
implementation HEAD               = d04487a0a2da60eaae46172bc9f4e37101e9dd97
docs freeze HEAD                  = d2259ab85eedbe1dd846acf1d7fb2ff883f8c826
decision evidence HEAD            = 65f0efdc56db5f299b92c6fe82866ea19045f057
PROVENANCE                        = CONDITIONAL
RIGHTS                            = CONDITIONAL
MERGE                             = NOT AUTHORIZED
FULL DETAIL HYDRATION             = NOT STARTED
WO-CHEM-04-HYDRATE-001            = NOT OPENED
PRODUCTION INGEST                 = NO
CHEM-04                           = IN_PROGRESS
BOOTSTRAP POLICY                  = NOT DECIDED
```

This Gate does **not** treat `SECONDARY_COMPLETE 9,124` as current KOSHA official content. It asks only how far that set may be used as **initial bootstrap**.

```text
STRUCTURAL_COMPLETE ≠ CURRENT_AUTHORITATIVE
```

Cursor recommendation only. GPT/Owner decides policy.

---

## Baseline (from CONTENT-LOCAL-001 PASS)

```text
official current             = 20568
official ∩ secondary         = 18478
SECONDARY_COMPLETE           = 9124
SECONDARY_PARTIAL            = 9354
SECONDARY_MISSING            = 2090
STRICT_API_CALLS             = 329088
STRUCTURAL_DELTA_CALLS       = 51940
AUTHORITATIVE_VERIFY_CALLS   = 329088
revision_unknown             = 20568
```

---

## Provenance (measured)

Sources read (not README-only):

```text
https://huggingface.co/datasets/Yuyongkim/inconvenience-msds
https://huggingface.co/datasets/Yuyongkim/inconvenience-msds/raw/main/README.md
https://github.com/yuyongkim/inconvenience-msds
https://raw.githubusercontent.com/yuyongkim/inconvenience-msds/main/LICENSE
https://raw.githubusercontent.com/yuyongkim/inconvenience-msds/main/scripts/export_hf_dataset.py
https://raw.githubusercontent.com/yuyongkim/inconvenience-msds/main/scripts/fetch_remaining_kosha.py
https://raw.githubusercontent.com/yuyongkim/inconvenience-msds/main/scripts/scan_missing_kosha.py
pinned HF revision = 5db49df655360dc69cc250ecb41058bf464553fa
```

### 1. Generated from KOSHA OpenAPI?

**Yes, by source scripts.** `fetch_remaining_kosha.py` and `scan_missing_kosha.py` call `https://apis.data.go.kr/B552468/msdschem/getChemDetailNN` with `chemId`. Raw XML is stored in local SQLite `msds_details(chem_id, section_no, xml_data)`. Dataset card: “retrieved via the Korea Public Data Portal API (data.go.kr) under an authorized operational account.”

`getChemList` in `fetch_remaining_kosha.py` is invoked **without** `searchWrd`/`searchCnd`. CHEM-04 measured that OpenAPI list is SEARCH-ONLY. That list path is not a valid full-enum API. Numeric `getChemDetail01` scan `0–50000` is present (`scan_missing_kosha.py`). Corpus size 48,966 > current official 20,568 is consistent with historical/non-current IDs, not with a live current web index.

### 2. How Detail01~16 were collected?

Per-section OpenAPI GET, XML saved. Empty success responses not always stored. Export then skips sections whose flattened text is empty (`if text:` in `export_hf_dataset.py`). Empty official XML therefore becomes **omitted section objects** in `train.jsonl` → TAI audit `MISSING`, not `EMPTY`.

### 3–4. Transform / is `text_ko` raw OpenAPI?

`text_ko` is **not** raw XML and **not** LLM summary of Korean body. Measured flatten:

```text
for each item:
  skip if itemDetail empty or '자료없음'
  GHSNN.gif → Korean pictogram label
  '|' → ', '
  emit "{msdsItemNameKor}: {cleaned}"
join with newline
then braille-encode that string
```

So `text_ko` is a **deterministic flatten** of OpenAPI items. Meaning is derived from `itemDetail`, but structure/labels/GHS filenames are transformed. Braille is a further encoding; TAI audit already excludes braille.

### 5–7. Dates

```text
record-level lastDate/revision in train.jsonl = NOT AVAILABLE (content audit)
corpus-level retrieval timestamp in records  = NOT AVAILABLE
encoder audit notes                          = 2026-08-13 / 2026-08-14
  (braille standard audit, not MSDS retrieval date)
HF/GitHub upload dates                       = NOT used as revision
```

**source snapshot date evidence = NOT AVAILABLE**  
**record-level revision = NOT AVAILABLE**

```text
PROVENANCE = CONDITIONAL
source generation method = OpenAPI Detail01~16 XML → flatten → braille
```

---

## Rights

Measured labels:

```text
dataset card / LICENSE = CC BY 4.0 (dataset)
encoder LICENSE        = MIT
source MSDS (author)   = 공공누리 제1유형 (Attribution)
CHEM-01 OpenAPI catalog 15157612 = 이용허락범위 제한 없음
KOSHA role (CHEM-01)   = 참고용 / not manufacturer SDS
```

Author’s KOGL Type 1 label and the official OpenAPI catalog string are **not the same**. This Gate does not collapse them.

```text
RIGHTS = CONDITIONAL
internal bootstrap = ALLOWED (with attribution; not authoritative)
customer display   = UNKNOWN
  (must not present secondary as current official KOSHA;
   참고용 disclaimer remains even for official OpenAPI)
REDISTRIBUTION_ALLOWED of the HF dataset under CC BY 4.0 = yes, with attribution
REDISTRIBUTION as TAI authoritative current MSDS = NO
```

Rights are not blank. They are not a blank check for customer-facing official content.

---

## Sample methodology

Deterministic strata from local official current × coverage. Exact `chemId` only. No CAS/name fallback.

```text
S1 GENERAL COMPLETE              5  filled
S2 CAS NULL among COMPLETE       0  COMPLETE ∩ official_cas null = 0
S3 SPECIAL NAME                  3  filled
S4 RECENT official_revision_date 3  filled
S5 OLD official_revision_date    3  filled
S6 known/validated               2  001008, 000001
                                 047134 = SECONDARY_PARTIAL, excluded
sample chemicals                 = 16  (20 requested; S2 empty, S6 short)
sample sections planned          = 256
sample_manifest_sha256           =
b404725ade87b289e124abcca0652e91ec4bace1f5094d79f251860035af2351
```

This SHA256 is local execution evidence of the sample ID list.

Live OpenAPI comparison:

```text
DATA_GO_KR_SERVICE_KEY / KOSHA_SERVICE_KEY / BUILDING_API_KEY = unset in this worktree
live official comparison = NOT_RUN_SERVICE_KEY_MISSING
live API calls           = 0
```

Historical CHEM test fixtures for benzene are **truncated** (many sections empty in fixture XML). Offline flatten vs `train.jsonl` 001008 is **not** current OpenAPI fidelity. Sections 03 and 04 of those short fixtures matched secondary flatten exactly; other fixture sections are incomplete. **Do not** treat that as 9,124 currentness or as section fidelity %.

---

## Sample comparison (live)

```text
sample chemicals     = 16 selected / 0 live-compared
sample sections      = 256 planned / 0 live-compared
EXACT                = NOT_MEASURED
NORMALIZED_EQUAL     = NOT_MEASURED
CONTENT_DIFFERENT    = NOT_MEASURED
SECONDARY_MISSING    = NOT_MEASURED
OFFICIAL_EMPTY       = NOT_MEASURED
SECONDARY_EMPTY      = NOT_MEASURED
API_ERROR            = NOT_RUN
section fidelity %   = NOT_MEASURED
chemical all-match % = NOT_MEASURED
mismatch causes      = NOT_MEASURED
```

20 live chemicals matching current OpenAPI would still **not** prove 9,124 are current. This Gate forbids that inference.

---

## Structural holes (current 20,568)

Official-only (no secondary row) = 2,090, which is also Detail01 structural count. Overlap chemicals still miss some sections:

```text
Detail01 structural = 2090   overlap extra = 0
Detail02 structural = 7428   overlap extra = 5338
Detail03 structural = 2095   overlap extra = 5
Detail11 structural = 4797   overlap extra = 2707
Detail12 structural = 5448   overlap extra = 3358
Detail13 structural = 6038   overlap extra = 3948
Detail15 structural = 2159   overlap extra = 69
```

HF dataset card “section 15 coverage 72.3%” is **corpus-wide 48,966**, not official-current overlap. Among current overlap, section 15 is nearly present. The large current holes are 02/11/12/13, plus export omitting empty flattened XML.

Possible causes (not proven without live XML): omitted empty sections; never fetched; later official added content. **UNKNOWN** until sample API.

---

## Call-cost comparison

```text
OPTION A  REJECT                 329088 calls
OPTION B  BOOTSTRAP_ONLY         51940 calls
OPTION C  BOOTSTRAP + sample     51940 + ≤320 sample
```

Secondary weakness remains **missing revision/date**, not only missing body. 9,124 COMPLETE are still `DATE_UNKNOWN`.

---

## Decision matrix

```text
Criterion                    A       B       C
------------------------------------------------
Current authoritative        YES*    NO      NO
API calls                    329088  51940   51940 + sample
Secondary dependency         NO      YES     YES
Initial speed                LOW     HIGH    HIGH
Currentness proof            HIGH    LOW     LOW
Content fidelity evidence    N/A     LOW     HIGH (after live sample)
Operational practicality     LOW     HIGH    HIGH
Rights / provenance fit      SAFE    RISK    RISK pending sample
```

`YES*` = after full official hydration.

If B/C were later approved, storage must stay split:

```text
content_origin         = SECONDARY_BOOTSTRAP | KOSHA_OFFICIAL
current_verified       = false until official verify
authoritative_verified = false until official verify
bootstrap_source       = Yuyongkim/inconvenience-msds
official_current_membership = true  (20,568 already frozen; do not rejudge)
```

Incremental future model (web index NEW/REMOVED/CHANGED → Detail hydrate) is **not implemented** in this WO.

---

## Risk

```text
STALE_SECONDARY     possible; no retrieval date
PARSER_DIFFERENCE   confirmed: flatten + drop empty + GHS rewrite
NORMALIZATION_ONLY  not measured live
SOURCE_CHANGED      possible on official_revision_date
UNKNOWN             remaining
customer confusion  if bootstrap is shown as official current
```

OPTION B auto-approve is forbidden by this WO.

---

## Recommended option (Cursor, not policy)

```text
RECOMMENDATION     = BLOCKED
BOOTSTRAP POLICY   = NOT DECIDED
WO status          = EVIDENCE COMPLETE / POLICY BLOCKED
```

Reasons:

1. OPTION C is the intended path, but live sample fidelity is **not measured** (no serviceKey in this worktree).
2. OPTION C pass bar (`section fidelity >= 99%`, `CONTENT_DIFFERENT` 0 or explained) is therefore unmet.
3. OPTION B must not be auto-selected.
4. Provenance of **method** is verified; provenance of **as-of date** is not.
5. Rights allow attributed internal bootstrap in principle, not customer authoritative display.

After a ≤320-call live sample on the 16 (or filled-to-20) chemIds, GPT can reopen C vs A. Do not infer currentness of 9,124 from that sample.

Independent confirmation 2026-09-14: freeze this Gate as **evidence complete / policy blocked**. `SECONDARY_COMPLETE 9,124` is not current-authoritative.

---

## OPTION C resume (only next opening)

Do not auto-approve OPTION B. Do not merge PR #359. Do not open HYDRATE-001.

```text
OPTION C 재개 조건
= ≤320 live sample 비교 완료
+ section fidelity ≥ 99%
+ CONTENT_DIFFERENT = 0 또는 설명 가능
```

Until that sample exists:

```text
POLICY = BLOCKED
BOOTSTRAP POLICY = NOT DECIDED
```

---

## STOP

```text
WO-CHEM-04-BOOTSTRAP-DECISION-001 = EVIDENCE COMPLETE / POLICY BLOCKED
PR #359 merge              = NOT AUTHORIZED
WO-CHEM-04-HYDRATE-001     = NOT OPENED
OPTION B auto-approve      = NO
production ingest          = NO
live API calls this WO     = 0
bulk hydration             = NO
FULL DETAIL HYDRATION      = NOT STARTED
CHEM-04                    = IN_PROGRESS
```

---

## LIVE SAMPLE ADDENDUM

Does not replace Decision Gate evidence or the STOP block above.

```text
WO-CHEM-04-OPTIONC-LIVE-SAMPLE-001
start HEAD                 = 37b057ebe1265fa37c90332450e36ab45f2ed1cf
sample manifest SHA256     = b404725ade87b289e124abcca0652e91ec4bace1f5094d79f251860035af2351
sample chemicals selected  = 16
planned sections           = 256
hard cap                   = 320
Cursor live probe          = max 1 chemId × 16
LOCAL 16×16                = operator machine only
serviceKey                 = env only (KOSHA_SERVICE_KEY then DATA_GO_KR_SERVICE_KEY)
production writer          = NONE
live metrics               = LOCAL_RUN_PENDING
TECHNICAL OPTION C GATE    = LOCAL_RUN_PENDING
BOOTSTRAP POLICY           = NOT DECIDED
OPTION B auto-approve      = NO
WO-CHEM-04-HYDRATE-001     = NOT OPENED
PR #359 merge              = NOT AUTHORIZED
```

CLI (LOCAL PC only for the frozen 16×16):

```bash
export KOSHA_SERVICE_KEY='...'   # or DATA_GO_KR_SERVICE_KEY; never commit
python3 -m tools.chem04.live_sample_compare --local-run
```

Cursor may run `--probe` (1 chemId) only. Full sample execution is not done in this worktree.

Until the operator local run returns SHA256 for `comparison.jsonl` and `live_sample_report.json`:

```text
section fidelity %         = LOCAL_RUN_PENDING
CONTENT_DIFFERENT          = LOCAL_RUN_PENDING
API_ERROR                  = LOCAL_RUN_PENDING
PROVENANCE                 = CONDITIONAL
RIGHTS                     = CONDITIONAL
customer display           = separate rights check; not solved by this WO
content_origin             = SECONDARY_BOOTSTRAP (if later approved)
current_verified           = false
authoritative_verified     = false
```

16 sample match ≠ 9,124 current verified.

---

## LIVE SAMPLE MEASURED RUN (256)

Does not replace the addendum above.

```text
WO-CHEM-04-OPTIONC-LIVE-SAMPLE-001 = BLOCKED
HEAD                      = d62c1a6b9d621c2fbb532fe7d5258a1bd4a3c282
attempted sections        = 256
successful official fetch = 0
API_ERROR                 = 256
comparable sections       = 0
fidelity                  = NOT MEASURED
quota issue               = NO
429                       = 0
resultCode22              = 0
secret leak               = 0
comparison SHA256         = 6016e9a949b45d4026669e7437a152de6e00cd914e8d175592e8409aa24d1d9e
live_sample_report SHA256 = 969b5b6153df21e76c92b1045a42b7f6302ff115ea3dc5912a820fe085ea925b
failure checkpoint SHA256 = 7e83e02fd1afc930d2a4e574eedd402854f2c1867e958e780722a192672e4bab
checkpoint                = KEEP (do not delete until preflight OK)
TECHNICAL OPTION C GATE   = BLOCKED
```

Cause was not classifiable: `run_live_sample()` dropped the redacted fetch_error token from `fetch_official_xml()`.

---

## FETCH DIAG ADDENDUM

```text
WO-CHEM-04-OPTIONC-FETCH-DIAG-001
scope = redacted fetch_error on API_ERROR rows
      + error_token_counts
      + preflight 001008 × getChemDetail01 (1 call)
256 re-run              = NOT AUTHORIZED
failure checkpoint      = KEEP
transport/key guessing  = NO
kr_get path             = UNCHANGED
OPTION C                = BLOCKED
OPTION B                = NO
MERGE                   = NOT AUTHORIZED
HYDRATE-001             = NOT OPENED
PRODUCTION              = NO
```

Preflight only (after this patch, operator local terminal):

```bash
export KOSHA_SERVICE_KEY='...'
python3 -m tools.chem04.live_sample_compare --preflight
```

Do not pass `--local-run` until GPT authorizes a new 256 after preflight OK. If `--local-run` is used later, preflight runs first and a FAIL does not write the sample checkpoint.

---

## FETCH DIAG MEASURED RUN (preflight)

Does not replace the 256 measured run. Does **not** reclassify those 256 `API_ERROR` rows as quota.

```text
WO-CHEM-04-OPTIONC-FETCH-DIAG-001 = FAIL / QUOTA STOP
preflight              = FAIL
chemId                 = 001008
section                = Detail01
HTTP 429               = 1
resultCode 22          = 1
quota_stop             = YES
http_requests          = 1
retry                  = 0
preflight report SHA256 =
e82c7e1415129fd7e52cf63fa7cbfa21c72df6db5316346becacc42398cbc821
preflight file SHA256  =
5954d8003e1fad1b8f970ae9ea7457749f2a6301d0ea59a65046653ba42615fb
failure checkpoint SHA =
7e83e02fd1afc930d2a4e574eedd402854f2c1867e958e780722a192672e4bab
256 re-run             = NOT AUTHORIZED
TODAY ADDITIONAL CALL  = NO
```

Official error map ([data.go.kr 15157612](https://www.data.go.kr/data/15157612/openapi.do)):

```text
22 LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR
   = API 서비스의 일일 호출 허용량 초과
20 SERVICE_ACCESS_DENIED_ERROR
   = 접근 권한 문제 (not observed here)
30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR
   = 미등록/잘못된 인증키 (not observed here)
```

This preflight returned HTTP 429 and resultCode 22. That is daily service traffic limit, not key format and not chemId/parameter error. Gateway accepted the key far enough to enforce quota.

---

## QUOTA POLICY ADDENDUM

Official portal text for this service ([data.go.kr 15157612](https://www.data.go.kr/data/15157612/openapi.do)):

```text
개발계정 신청 가능 트래픽 = 1,000
운영계정                 = 활용사례 등록 시 트래픽 증가 신청 가능
```

Swagger 가이드는 `serviceKey`에 **일반 인증키(Decoding)** 입력을 안내한다 ([gateway swagger guide](https://www.data.go.kr/images/biz/swagger-guide/gw/gateway_swagger_guide.pdf)). 이번 22 응답은 키 교체 사유가 아니다.

```text
AUTH KEY CHANGE          = NO
AUTH KEY FORMAT ISSUE    = NO EVIDENCE
PARAMETER ISSUE          = NO EVIDENCE
CURRENT ROOT CAUSE       = DAILY SERVICE TRAFFIC LIMIT
OFFICIAL DEV TRAFFIC     = 1,000/day
PER-ENDPOINT 1,000       = NOT DOCUMENTED
SERVICE-WIDE 1,000       = WORKING ASSUMPTION
if_1000_per_day_per_endpoint 21-day strict
                         = undocumented assumption; not official
if_1000_per_day_global
                         = conservative calendar (329088 → 330일,
                           51940 → 52일) under service-wide 1,000
OPTION C                 = BLOCKED BY QUOTA
BOOTSTRAP POLICY         = NOT DECIDED
HYDRATE-001              = NOT OPENED
51,940 structural hydration
                         = not solvable on a 1,000/day 개발계정
```

2026-09-14 Detail01 census (`PORTAL 1000/day HARD LIMIT OBSERVED`) remains a **Detail01-that-day observation**. It does not prove 16 independent 1,000 buckets.

Do not treat 개발계정 1,000 as the path to 51,940 structural calls. Official increase path: 운영계정 심의 + 활용사례 등록 후 트래픽 증설 신청.

Next investigation (no extra OpenAPI today):

```text
1. 현재 KOSHA MSDS 활용신청 = 개발계정 or 운영계정
2. 현재 승인 일일 트래픽이 실제 1,000인지
3. 운영계정 전환 / 트래픽 증설 가능 수량
4. 1,000 quota가 getChemDetail01~16 전체 공유인지
```

Code and generic `serviceKey` env handling are unchanged in this freeze.


