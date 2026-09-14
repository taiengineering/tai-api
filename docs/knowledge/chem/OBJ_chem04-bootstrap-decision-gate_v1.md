---
class: records
type: report
scope: knowledge
project: chem
title: OBJ-CHEM-04 secondary content bootstrap Decision Gate
version: 1
status: active
owner: taiwang
---

# OBJ-CHEM-04 — Secondary Content Bootstrap Decision Gate

```text
WO-CHEM-04-BOOTSTRAP-DECISION-001 = EVIDENCE COMPLETE / POLICY NOT DECIDED
WO-CHEM-04-CONTENT-LOCAL-001      = PASS
PR #359                           = OPEN / UNMERGED
implementation HEAD               = d04487a0a2da60eaae46172bc9f4e37101e9dd97
docs freeze HEAD                  = d2259ab85eedbe1dd846acf1d7fb2ff883f8c826
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
```

Reasons:

1. OPTION C is the intended path, but live sample fidelity is **not measured** (no serviceKey in this worktree).
2. OPTION C pass bar (`section fidelity >= 99%`, `CONTENT_DIFFERENT` 0 or explained) is therefore unmet.
3. OPTION B must not be auto-selected.
4. Provenance of **method** is verified; provenance of **as-of date** is not.
5. Rights allow attributed internal bootstrap in principle, not customer authoritative display.

After a ≤320-call live sample on the 16 (or filled-to-20) chemIds, GPT can reopen C vs A. Do not infer currentness of 9,124 from that sample.

---

## STOP

```text
PR #359 merge              = NOT AUTHORIZED
WO-CHEM-04-HYDRATE-001     = NOT OPENED
production ingest          = NO
live API calls this WO     = 0
bulk hydration             = NO
```
