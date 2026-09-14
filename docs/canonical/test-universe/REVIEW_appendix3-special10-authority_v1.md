---
wo: WO-E2E-OBS007-SPECIAL10-APPENDIX3-REVISE-STAGE-A-001
class: records
type: review
scope: canonical
project: test-universe
title: SPECIAL10 Appendix3 fixture authority Stage A review pack
version: 1
status: pending-gpt-review
owner: taiwang
---

# REVIEW — SPECIAL10 Appendix3 Fixture Authority (Stage A)

```text
STAGE_A_ONLY = YES
AUTHORITY = false
AUTHORITY = NOT_APPROVED
LEGAL_CLASSIFICATION = NOT_STARTED
```

> This pack is NOT authority.
> No values approved.
> No production derivation.
> No inference.

---

## A. Why

```text
Frozen SPECIAL_FACILITY 10
→ Official request BUILDING
→ server Appendix3 gate applies
```

Frozen source sector remains `SPECIAL_FACILITY`. Existing consumer projection sets `request.sector = BUILDING`. Live `run_diagnosis` therefore requires explicit Appendix3 source. Current Runner Appendix3 gating is Frozen source-sector based and leaves these 10 ungated.

This Stage A file does not change that code and does not assign item numbers.

---

## B. Scope

Exact profile IDs:

```text
PF-0037
PF-0038
PF-0039
PF-0106
PF-0107
PF-0108
PF-0109
PF-0110
PF-0111
PF-0112
```

```text
TARGET_ROWS = 10
UNIQUE_PROFILE_IDS = 10
```

Approved MFG+BUILDING 75 Appendix3 authority rows are out of scope and must not be modified.

---

## C. Current failure

```text
Run-A2 attempted = 112
success = 102
422 = 10
402 = 0

10/10:
source sector SPECIAL_FACILITY
request sector BUILDING
appendix3_item_no absent
APPENDIX3_EXPLICIT_CLASSIFICATION_REQUIRED
```

Evidence remains in `~/45cm-test/obs007_crane_chg_v1/measurement_run_a2/`. Do not delete or overwrite it.

PF-0108 is included as one of these 10 rows. It is not a separate investigation in this Stage A.

---

## D. Governance

```text
This pack is NOT authority.
No values approved.
No production derivation.
No inference.
```

```text
ksic_mapping = false
Catalog = docs/canonical/legal-input/appendix3_items_v1.json
item_count = 49
read_only = true
```

Catalog labels are a read-only reference list. They are not a mapping rule.

Cursor extracted Frozen raw facts only. GPT will classify later. Owner synthetic fixture fact is used only if GPT cannot judge.

```text
PR347_RESULT = REVISE
PR347_ROLLBACK = NO
PR347_KEEP_FINAL = NO
```

PR #347 target improvement (MFG+BUILDING 75) remains. SPECIAL10 is incomplete coverage, not a rollback of previously working paths.

---

## E. Next

```text
GPT Semantic Classification
→ Owner Decision if needed
→ Authority Freeze
→ Runner Bridge REVISE
→ Full 112 Regression
→ KEEP / REVISE / ROLLBACK
→ only then Merge
```

```text
MERGE = BLOCKED
RUNNER_DELTA = 0
HTTP = 0
FULL_112_REGRESSION_PASS 전 merge 금지
```
