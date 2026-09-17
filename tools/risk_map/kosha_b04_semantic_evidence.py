"""WO-RISK-KOSHA-B04-EVIDENCE-001 KOSHA B04 semantic review evidence pack.

Thin wrapper over the deterministic retrieval engine in
`tools.risk_map.kosha_b01_semantic_evidence`. Same mechanical semantics as
B01/B02/B03. No LLM, no fuzzy, no embedding, no synonym expansion. No
semantic decision.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from tools.risk04.review_decisions import write_tsv
from tools.risk04.seed_review import universe_sha
from tools.risk_map.kosha_b01_semantic_evidence import (
    B01_EVIDENCE_FIELDS as _SHARED_EVIDENCE_FIELDS,
    CANDIDATE_CAP,
    FROZEN_CANONICAL_RECEIPT_SHA,
    FROZEN_GPT_REVIEW_PACK_SHA,
    FROZEN_MAP_MATERIALIZATION_RECEIPT_SHA,
    build_batch_evidence,
)
from tools.risk_map.map_approve001_owner_binding import FROZEN_PROPOSAL_SHA

WO_ID = "WO-RISK-KOSHA-B04-EVIDENCE-001"
BATCH_ID = "B04"

EXPECTED_B04_ROWS = 100
EXPECTED_B04_EXACT_NAME = 0
EXPECTED_B04_SEMANTIC_SEARCH = 100

B04_EVIDENCE_FIELDS: tuple[str, ...] = _SHARED_EVIDENCE_FIELDS

B04_EVIDENCE_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B04_SEMANTIC_EVIDENCE_v1.tsv"
)
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk-kosha-b04-semantic-evidence_v1.md")


def build_b04_evidence() -> tuple[list[dict], list[dict]]:
    return build_batch_evidence(
        BATCH_ID,
        EXPECTED_B04_ROWS,
        EXPECTED_B04_EXACT_NAME,
        EXPECTED_B04_SEMANTIC_SEARCH,
    )


def b04_evidence_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *B04_EVIDENCE_FIELDS)


def render_report(rows: list[dict], sha_value: str) -> str:
    with_candidates = sum(
        1 for r in rows if r["evidence_state"] == "CANDIDATES_FOUND"
    )
    no_candidates = sum(
        1 for r in rows if r["evidence_state"] == "NO_MECHANICAL_CANDIDATE"
    )
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-B04-EVIDENCE-001 KOSHA B04 semantic review evidence
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KOSHA B04 Semantic Review Evidence

## THIS IS MECHANICAL EVIDENCE ONLY

```text
THIS IS MECHANICAL EVIDENCE ONLY
THIS IS NOT GPT SEMANTIC REVIEW
THIS IS NOT OWNER MAPPING APPROVAL
THIS IS NOT PRODUCTION MATERIALIZATION
THIS DOES NOT LIFT KOSHA IDENTITY HOLD
ZERO MECHANICAL CANDIDATES != NO_MATCH
```

## Inputs (frozen repository evidence)

```text
GPT REVIEW PACK SHA               = {FROZEN_GPT_REVIEW_PACK_SHA}
CANONICAL RECEIPT SHA             = {FROZEN_CANONICAL_RECEIPT_SHA}
CIC_W PROPOSAL SHA                = {FROZEN_PROPOSAL_SHA}
MAP MATERIALIZATION RECEIPT SHA   = {FROZEN_MAP_MATERIALIZATION_RECEIPT_SHA}
```

Same deterministic retrieval engine as B01/B02/B03 — no schema change, no
scoring change, no new lexical resource. Only the batch selector differs.

## B04 composition

```text
B04 rows                          = {len(rows)}
EXACT_NAME_CANDIDATE              = 0   (all 12 exact-name candidates in B01)
SEMANTIC_SEARCH_REQUIRED          = {len(rows)}
rows with mechanical candidates   = {with_candidates}
rows with zero mechanical candidates = {no_candidates}
candidate cap                     = {CANDIDATE_CAP} per row
```

## Cumulative KOSHA review evidence

```text
B01 evidence + review             = complete
B02 evidence + review             = complete
B03 evidence + review             = complete
B04 evidence                      = complete (this WO)
B04 review                        = pending (GPT semantic review)
GPT decisions committed so far    = 300 / 620
B04 rows GPT-review-ready         = 100
```

## Frozen SHA

```text
RISK KOSHA B04 SEMANTIC EVIDENCE SHA = {sha_value}
```

## Verdict

```text
{WO_ID} = EVIDENCE_FROZEN / GPT_REVIEW_READY
B04 SEMANTIC DECISIONS = 0
KOSHA PRODUCTION MAPPINGS = 0
MERGE = NOT AUTHORIZED
NEXT = GPT KOSHA SEMANTIC REVIEW BATCH 04
STOP
```
"""


def write_all() -> dict:
    rows_a, _ = build_b04_evidence()
    rows_b, _ = build_b04_evidence()
    if rows_a != rows_b:
        raise SystemExit("B04_EVIDENCE_ROW_ORDER_DRIFT")
    sha_a = b04_evidence_sha(rows_a)
    sha_b = b04_evidence_sha(rows_b)
    if sha_a != sha_b:
        raise SystemExit(f"B04_EVIDENCE_SHA_DRIFT {sha_a} vs {sha_b}")

    write_tsv(rows_a, B04_EVIDENCE_PATH, B04_EVIDENCE_FIELDS)
    REPORT_PATH.write_text(render_report(rows_a, sha_a), encoding="utf-8")

    with_candidates = sum(1 for r in rows_a if r["evidence_state"] == "CANDIDATES_FOUND")
    no_candidates = sum(1 for r in rows_a if r["evidence_state"] == "NO_MECHANICAL_CANDIDATE")

    return {
        "b04_rows": len(rows_a),
        "rows_with_mechanical_candidates": with_candidates,
        "rows_with_zero_mechanical_candidates": no_candidates,
        "b04_evidence_sha_run1": sha_a,
        "b04_evidence_sha_run2": sha_b,
        "b04_evidence_path": str(B04_EVIDENCE_PATH),
        "report_path": str(REPORT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} evidence generator")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
