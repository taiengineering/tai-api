---
class: records
type: report
scope: knowledge
project: chem
title: OBJ-CHEM-04 local secondary content audit and hydration queue
version: 2
status: active
owner: taiwang
---

# OBJ-CHEM-04 — Local content audit (WO-CHEM-04-CONTENT-LOCAL-001)

```text
WO-CHEM-04-MERGE-001          = CLOSED / PASS
IDENTITY PHASE                = PASS / 20568
FULL DETAIL HYDRATION         = NOT STARTED
PRODUCTION INGEST             = NO
CHEM-04                       = IN_PROGRESS
CURSOR FULL DATA RUN          = NO
LOCAL FULL DATA RUN           = YES
```

Identity is frozen. This WO measures secondary **content coverage** against the official current 20,568 chemId set and produces a **section-level** hydration queue. It does not call Detail01~16 in bulk and does not ingest production.

---

## Observed secondary content contract

Source: `Yuyongkim/inconvenience-msds` `train.jsonl` at pinned revision
`5db49df655360dc69cc250ecb41058bf464553fa`.

README was not the authority. First raw record keys actually present:

```text
chem_id
name_ko
cas_no
name_en
sections
total_text_chars
total_braille_chars
```

Each `sections[]` object observed:

```text
section_no
title
text_ko
braille
```

Content-audit scope (policy B):

```text
presence + canonical hash = text_ko / textKo only
braille                   = observed on source, excluded from audit
BRAILLE_IN_CONTENT_AUDIT  = False
```

Braille-only sections are `EMPTY`, not `PRESENT`. Braille changes do not change `content_hash`.

Fields **not** present on the sampled raw record (do not invent):

```text
lastDate
last_date
openYn
revision
snapshot
source_url
retrieved_at
content_hash
```

Freshness is `DATE_UNKNOWN` unless a comparable date exists on **both** official current index (`official_revision_date`) and the secondary record. Hugging Face upload date and file mtime are not revision.

---

## Local CLIs (operator machine for full run)

```bash
python -m tools.chem04.audit_secondary_content --local-jsonl PATH
python -m tools.chem04.build_content_coverage
python -m tools.chem04.build_hydration_queue
python -m tools.chem04.content_report
```

Cursor probe only:

```bash
python -m tools.chem04.audit_secondary_content --local-jsonl tests/fixtures/kosha_msds/secondary_content_sample.jsonl --max-rows 5
```

`--download` streams the pinned HF `train.jsonl`. Do not combine with `--max-rows`.

Artifacts (gitignored):

```text
artifacts/chem04/content/indexes/secondary_content_index.jsonl
artifacts/chem04/content/coverage/current_content_coverage.jsonl
artifacts/chem04/content/queues/hydration_queue.jsonl
artifacts/chem04/content/queues/structural_delta_queue.jsonl
artifacts/chem04/content/reports/content_audit_report.json
artifacts/chem04/content/manifests/content_manifest.json
```

---

## Queue contract

```text
STRICT_API_CALLS            = official_current × 16
STRUCTURAL_DELTA_CALLS      = missing / invalid / official-only / empty-valid
AUTHORITATIVE_VERIFY_CALLS  = STRUCTURAL_DELTA
                            + REVISION_UNKNOWN
                            + REVISION_CHANGED
DELTA_API_CALLS             = AUTHORITATIVE_VERIFY_CALLS
```

Do not materialize a blind `20,568 × 16` queue. `hydration_queue.jsonl` is the authoritative-verify set. `structural_delta_queue.jsonl` is the bootstrap-hole set.

`REVISION_UNKNOWN` complete records **are** queued on the verify path. Secondary has no `lastDate`/`revision` on the observed schema, so COMPLETE ≠ current authoritative confirmed.

`CURRENT_MATCH` complete is not queued.

Operator sequence:

```text
구현/테스트
→ LOCAL FULL RUN
→ GPT 결과 검증
→ merge authorization
```

Local full run is **before** merge, not after.

```text
PRODUCTION AUTHORITATIVE CONTENT = NO
secondary content production ingest = NO
```

---

## Full-run metrics

Filled by the operator local full run. Until then:

```text
official ∩ secondary     = LOCAL_RUN_PENDING
SECONDARY_COMPLETE       = LOCAL_RUN_PENDING
SECONDARY_PARTIAL        = LOCAL_RUN_PENDING
SECONDARY_EMPTY_VALID    = LOCAL_RUN_PENDING
SECONDARY_INVALID        = LOCAL_RUN_PENDING
SECONDARY_MISSING        = LOCAL_RUN_PENDING
STRICT_API_CALLS              = LOCAL_RUN_PENDING
STRUCTURAL_DELTA_CALLS        = LOCAL_RUN_PENDING
AUTHORITATIVE_VERIFY_CALLS    = LOCAL_RUN_PENDING
DELTA_API_CALLS               = LOCAL_RUN_PENDING
API CALL REDUCTION            = LOCAL_RUN_PENDING
STRUCTURAL_API_CALL_REDUCTION = LOCAL_RUN_PENDING
```

Next hydration strategy is `WO-CHEM-04-HYDRATE-001` and is not opened by this WO.
