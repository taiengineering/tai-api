---
class: records
type: report
scope: knowledge
project: chem
title: OBJ-CHEM-04 local secondary content audit and hydration queue
version: 3
status: active
owner: taiwang
---

# OBJ-CHEM-04 — Local content audit (WO-CHEM-04-CONTENT-LOCAL-001)

```text
WO-CHEM-04-CONTENT-LOCAL-001  = PASS
WO-CHEM-04-MERGE-001          = CLOSED / PASS
IDENTITY PHASE                = PASS / 20568
CONTENT LOCAL AUDIT           = PASS
FULL DETAIL HYDRATION         = NOT STARTED
WO-CHEM-04-HYDRATE-001        = NOT OPENED
PRODUCTION INGEST             = NO
CHEM-04                       = IN_PROGRESS
CURSOR FULL DATA RUN          = NO
LOCAL FULL DATA RUN           = COMPLETE
MERGE                         = NOT AUTHORIZED
```

Identity is frozen. This WO measured secondary **content coverage** against the official current 20,568 chemId set and produced section-level hydration queues. It did not call Detail01~16 in bulk and did not ingest production.

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
python3 -m tools.chem04.audit_secondary_content --local-jsonl PATH
python3 -m tools.chem04.build_content_coverage
python3 -m tools.chem04.build_hydration_queue
python3 -m tools.chem04.content_report
```

This Mac has `python3`, not `python`.

Cursor probe only:

```bash
python3 -m tools.chem04.audit_secondary_content --local-jsonl tests/fixtures/kosha_msds/secondary_content_sample.jsonl --max-rows 5
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

## Full-run metrics (PASS)

Operator local full run on HEAD `d04487a0a2da60eaae46172bc9f4e37101e9dd97`.
SHA256 values below are **local execution evidence**. GPT did not independently rehash the gitignored artifacts.

```text
secondary raw rows               = 48966
secondary identity rows          = 48963
official current rows            = 20568
official ∩ secondary             = 18478
SECONDARY_COMPLETE               = 9124
SECONDARY_PARTIAL                = 9354
SECONDARY_EMPTY_VALID            = 0
SECONDARY_INVALID                = 0
SECONDARY_MISSING                = 2090
revision match                   = 0
revision changed                 = 0
revision unknown                 = 20568
STRICT_API_CALLS                 = 329088
STRUCTURAL_DELTA_CALLS           = 51940
AUTHORITATIVE_VERIFY_CALLS       = 329088
DELTA_API_CALLS                  = 329088
API CALL REDUCTION               = 0 / 0.00%
STRUCTURAL_API_CALL_REDUCTION    = 277148 / 84.22%
```

Integrity:

```text
9124 + 9354 + 2090 = 20568
9124 + 9354        = 18478
16 structural endpoint sum = 51940
329088 - 51940     = 277148 = 84.22%
```

Local artifact hashes (not in Git; not GPT-rehashed):

```text
secondary_content_index SHA256 =
2ff2a3d7271d62fba0699c8076cd9a4ee54160e651efa0448bc9099ea1a13947
current_content_coverage SHA256 =
5f57582642c1c639c277a5a1ff36663e47468aec5ab112b574d000c9fdcb4e0c
hydration_queue SHA256 =
7eba2dca2e183bab2c09f6260874cf8b5380ccb6d2f4bec61dfd193c881085d9
structural_delta_queue SHA256 =
6c7d9d4d31481e15104883782ffcfc58f13319d673053e1eb10000d5f1b7f1f6
report canonical SHA256 =
5166cf532baf384c5762816f5fd84b9d5ecdd21af966dc392b6a8935dfa3da51
```

Decision:

```text
structural bootstrap accepted → 51940 calls / 84.22% reduction
currentness officially verified → 329088 calls / same as strict
```

Secondary weakness is missing revision/date, not missing body. 9,124 COMPLETE records are structurally full and still `DATE_UNKNOWN`.

---

## Next — Decision Gate, not hydration

Do **not** open `WO-CHEM-04-HYDRATE-001` yet.

Next required decision:

```text
GATE: how far TAI accepts structurally complete secondary content as bootstrap
      before official current verification
```

Until that gate is decided:

```text
PR #359                      = OPEN / UNMERGED
MERGE                        = NOT AUTHORIZED
PRODUCTION INGEST            = NO
FULL DETAIL HYDRATION        = NOT STARTED
WO-CHEM-04-HYDRATE-001       = NOT OPENED
CHEM-04                      = IN_PROGRESS
```

## STOP
