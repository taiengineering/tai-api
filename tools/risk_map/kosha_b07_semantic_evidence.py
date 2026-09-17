"""WO-RISK-KOSHA-B07-EVIDENCE-001 KOSHA B07 semantic review evidence pack.

Thin wrapper over the deterministic retrieval engine in
`tools.risk_map.kosha_b01_semantic_evidence`. Same mechanical semantics as
B01-B06. No LLM, no fuzzy, no embedding, no synonym expansion. No semantic
decision.

Terminology (as reinforced by WO-B07):
  * `review_key`  = GPT review row identity — the literal key of the GPT
    decision manifest. B06 WO §5-§9 spelled its per-row keys as
    "source_key" but the values are actually review_key entries.
  * `source_key`  = KOSHA source-node identity. Preserved on every
    evidence row alongside review_key.

Evidence output preserves both. Frozen B06 artifacts are NOT edited.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha
from tools.risk_map.kosha_b01_semantic_evidence import (
    B01_EVIDENCE_FIELDS as _SHARED_EVIDENCE_FIELDS,
    CANDIDATE_CAP,
    FROZEN_CANONICAL_RECEIPT_SHA,
    FROZEN_GPT_REVIEW_PACK_SHA,
    FROZEN_MAP_MATERIALIZATION_RECEIPT_SHA,
    GPT_REVIEW_PACK_PATH,
    build_batch_evidence,
)
from tools.risk_map.map_approve001_owner_binding import FROZEN_PROPOSAL_SHA

WO_ID = "WO-RISK-KOSHA-B07-EVIDENCE-001"
BATCH_ID = "B07"

EXPECTED_B07_ROWS = 20
EXPECTED_B07_EXACT_NAME = 0
EXPECTED_B07_SEMANTIC_SEARCH = 20

B07_EVIDENCE_FIELDS: tuple[str, ...] = _SHARED_EVIDENCE_FIELDS

B07_EVIDENCE_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B07_SEMANTIC_EVIDENCE_v1.tsv"
)
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk-kosha-b07-semantic-evidence_v1.md")


def build_b07_evidence() -> tuple[list[dict], list[dict]]:
    return build_batch_evidence(
        BATCH_ID,
        EXPECTED_B07_ROWS,
        EXPECTED_B07_EXACT_NAME,
        EXPECTED_B07_SEMANTIC_SEARCH,
    )


def b07_evidence_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *B07_EVIDENCE_FIELDS)


def _frozen_b07_review_source_pairs() -> set[tuple[str, str]]:
    """Return the (review_key, source_key) universe of B07 in the frozen pack."""
    pack = load_tsv(GPT_REVIEW_PACK_PATH)
    b07 = [r for r in pack if r["batch_no"] == BATCH_ID]
    if len(b07) != EXPECTED_B07_ROWS:
        raise SystemExit(f"B07_PACK_ROW_DRIFT {len(b07)}")
    pairs = {(r["review_key"], r["source_key"]) for r in b07}
    if len(pairs) != EXPECTED_B07_ROWS:
        raise SystemExit("B07_PACK_PAIR_NOT_UNIQUE")
    return pairs


def _assert_dual_key_exact_pair(rows: list[dict]) -> None:
    """WO §7 dual-key guard: (review_key, source_key) pair set == frozen pack."""
    ev_pairs = {(r["review_key"], r["source_key"]) for r in rows}
    if len(ev_pairs) != len(rows):
        raise SystemExit("B07_EVIDENCE_PAIR_NOT_UNIQUE")
    review_keys = {r["review_key"] for r in rows}
    source_keys = {r["source_key"] for r in rows}
    if len(review_keys) != EXPECTED_B07_ROWS:
        raise SystemExit(f"B07_REVIEW_KEY_DUPLICATE {len(review_keys)}")
    if len(source_keys) != EXPECTED_B07_ROWS:
        raise SystemExit(f"B07_SOURCE_KEY_DUPLICATE {len(source_keys)}")
    frozen = _frozen_b07_review_source_pairs()
    if ev_pairs != frozen:
        raise SystemExit(
            "B07_REVIEW_SOURCE_PAIR_DRIFT "
            f"missing={len(frozen - ev_pairs)} unexpected={len(ev_pairs - frozen)}"
        )


def render_report(rows: list[dict], sha_value: str) -> str:
    with_candidates = sum(
        1 for r in rows if r["evidence_state"] == "CANDIDATES_FOUND"
    )
    no_candidates = sum(
        1 for r in rows if r["evidence_state"] == "NO_MECHANICAL_CANDIDATE"
    )
    unique_review = len({r["review_key"] for r in rows})
    unique_source = len({r["source_key"] for r in rows})
    unique_pairs = len({(r["review_key"], r["source_key"]) for r in rows})
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-B07-EVIDENCE-001 KOSHA B07 semantic review evidence
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KOSHA B07 Semantic Review Evidence

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

Same deterministic retrieval engine as B01-B06 — no schema change,
no scoring change, no new lexical resource. Only the batch selector differs.

## B07 composition

```text
B07 rows                              = {len(rows)}
EXACT_NAME_CANDIDATE                  = 0   (all 12 exact-name candidates in B01)
SEMANTIC_SEARCH_REQUIRED              = {len(rows)}
rows with mechanical candidates       = {with_candidates}
rows with zero mechanical candidates  = {no_candidates}
candidate cap                         = {CANDIDATE_CAP} per row
unique review_key                     = {unique_review}
unique source_key                     = {unique_source}
unique (review_key, source_key) pair  = {unique_pairs}
pair set                              = EXACT match with frozen B07 pack
```

## Key terminology note

```text
review_key = review-row / GPT decision manifest identity
source_key = KOSHA source-node identity

B06 WO §5-§9 used the label "source_key" for values that were
in fact review_key. The B06 freeze output preserved the correct
source_key on every row, so no B06 semantic row was rebound to
another source.

B06 DECISION MANIFEST KEY = review_key
B06 OUTPUT SOURCE IDENTITY = source_key
B06 DATA CORRUPTION = NO

B06 frozen artifacts are NOT rewritten by this WO.
```

## Cumulative KOSHA review evidence

```text
B01 evidence + review                = complete
B02 evidence + review                = complete
B03 evidence + review                = complete
B04 evidence + review                = complete
B05 evidence + review                = complete
B06 evidence + review                = complete
B07 evidence                         = complete (this WO)
B07 review                           = pending (GPT semantic review)
GPT decisions committed so far       = 600 / 620
B07 rows GPT-review-ready            = 20
REMAINING after B07 review           = 0
TOTAL FROZEN REVIEW UNIVERSE         = 620
```

## Frozen SHA

```text
RISK KOSHA B07 SEMANTIC EVIDENCE SHA = {sha_value}
```

## Verdict

```text
{WO_ID} = EVIDENCE_FROZEN / GPT_REVIEW_READY
B07 SEMANTIC DECISIONS = 0
KOSHA PRODUCTION MAPPINGS = 0
MERGE = NOT AUTHORIZED
NEXT = GPT KOSHA SEMANTIC REVIEW BATCH 07
STOP
```
"""


def write_all() -> dict:
    rows_a, _ = build_b07_evidence()
    rows_b, _ = build_b07_evidence()
    if rows_a != rows_b:
        raise SystemExit("B07_EVIDENCE_ROW_ORDER_DRIFT")
    _assert_dual_key_exact_pair(rows_a)
    sha_a = b07_evidence_sha(rows_a)
    sha_b = b07_evidence_sha(rows_b)
    if sha_a != sha_b:
        raise SystemExit(f"B07_EVIDENCE_SHA_DRIFT {sha_a} vs {sha_b}")

    write_tsv(rows_a, B07_EVIDENCE_PATH, B07_EVIDENCE_FIELDS)
    REPORT_PATH.write_text(render_report(rows_a, sha_a), encoding="utf-8")

    with_candidates = sum(1 for r in rows_a if r["evidence_state"] == "CANDIDATES_FOUND")
    no_candidates = sum(1 for r in rows_a if r["evidence_state"] == "NO_MECHANICAL_CANDIDATE")

    return {
        "b07_rows": len(rows_a),
        "rows_with_mechanical_candidates": with_candidates,
        "rows_with_zero_mechanical_candidates": no_candidates,
        "unique_review_key": len({r["review_key"] for r in rows_a}),
        "unique_source_key": len({r["source_key"] for r in rows_a}),
        "unique_review_source_pairs": len({(r["review_key"], r["source_key"]) for r in rows_a}),
        "b07_evidence_sha_run1": sha_a,
        "b07_evidence_sha_run2": sha_b,
        "b07_evidence_path": str(B07_EVIDENCE_PATH),
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
