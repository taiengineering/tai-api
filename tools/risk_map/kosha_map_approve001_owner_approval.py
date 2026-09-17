"""WO-RISK-KOSHA-MAP-APPROVE-001 KOSHA source-mapping Owner Approval execution.

Transcribes the deterministic Owner decision onto the frozen 75-row KOSHA
mapping candidate SoT and emits the binding + receipt. No production DB
write, no canonical mutation, no semantic re-decision, and NOT a merge
gate — this WO records the Owner's mapping approval only.

Decision map (WO §2):
  * EXACT_EQUIVALENT  ×  6   → APPROVE
  * NARROWER_THAN     × 40   → APPROVE
  * POSSIBLE_RELATED  × 29   → HOLD
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha
from tools.risk_map.kosha_620_aggregate import (
    AGGREGATE_FIELDS,
    MAPPING_PATH,
    _REVIEW_DIR,
    bucket_sha,
)

WO_ID = "WO-RISK-KOSHA-MAP-APPROVE-001"
APPROVAL_ID = "RISK-KOSHA-MAP-APPROVE-001"

FROZEN_MAPPING_CANDIDATES_SHA = (
    "4952310fafda56d620f10a53a4c4faa765c73338157e1992c6d690428e4f869a"
)

EXPECTED_TOTAL = 75
EXPECTED_EXACT = 6
EXPECTED_NARROWER = 40
EXPECTED_POSSIBLE = 29
EXPECTED_APPROVED = EXPECTED_EXACT + EXPECTED_NARROWER   # 46
EXPECTED_HOLD = EXPECTED_POSSIBLE                         # 29
EXPECTED_REJECTED = 0

DECISION_APPROVE = "APPROVE"
DECISION_HOLD = "HOLD"

REASON_APPROVE = "OWNER_APPROVED_DIRECT_SEMANTIC_MAPPING"
REASON_HOLD = "OWNER_HELD_POSSIBLE_RELATED_FOR_FUTURE_REVIEW"

# WO §2 decision map — the ONLY authoritative source of Owner intent here.
_DECISION_BY_TYPE: dict[str, tuple[str, str]] = {
    "EXACT_EQUIVALENT": (DECISION_APPROVE, REASON_APPROVE),
    "NARROWER_THAN": (DECISION_APPROVE, REASON_APPROVE),
    "POSSIBLE_RELATED": (DECISION_HOLD, REASON_HOLD),
}

BINDING_PATH = _REVIEW_DIR / "RISK_KOSHA_MAP_APPROVE001_OWNER_APPROVAL_BINDING_v1.tsv"
RECEIPT_PATH = _REVIEW_DIR / (
    "OBJ_risk-kosha-map-approve001-owner-approval-execution-receipt_v1.md"
)

BINDING_FIELDS: tuple[str, ...] = (
    "approval_id",
    "review_key",
    "source_key",
    "project_kind",
    "work_type",
    "source_name",
    "source_path",
    "target_canonical_id",
    "target_canonical_name",
    "mapping_type",
    "gpt_confidence_class",
    "owner_decision",
    "owner_reason",
    "source_aggregate_sha",
)


# ---------------------------------------------------------------------------
# Input load + guard
# ---------------------------------------------------------------------------


def _load_frozen_candidates() -> list[dict]:
    rows = load_tsv(MAPPING_PATH)
    if len(rows) != EXPECTED_TOTAL:
        raise SystemExit(f"MAPPING_CANDIDATE_ROW_DRIFT {len(rows)}")
    got_sha = bucket_sha(rows)
    if got_sha != FROZEN_MAPPING_CANDIDATES_SHA:
        raise SystemExit(f"MAPPING_CANDIDATE_SHA_DRIFT {got_sha}")
    counts = Counter(r["gpt_mapping_type"] for r in rows)
    if counts.get("EXACT_EQUIVALENT", 0) != EXPECTED_EXACT:
        raise SystemExit(f"EXACT_COUNT_DRIFT {counts.get('EXACT_EQUIVALENT')}")
    if counts.get("NARROWER_THAN", 0) != EXPECTED_NARROWER:
        raise SystemExit(f"NARROWER_COUNT_DRIFT {counts.get('NARROWER_THAN')}")
    if counts.get("POSSIBLE_RELATED", 0) != EXPECTED_POSSIBLE:
        raise SystemExit(f"POSSIBLE_RELATED_COUNT_DRIFT {counts.get('POSSIBLE_RELATED')}")
    return rows


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------


def build_binding() -> list[dict]:
    candidates = _load_frozen_candidates()

    review_keys = {r["review_key"] for r in candidates}
    source_keys = {r["source_key"] for r in candidates}
    pair_set = {(r["review_key"], r["source_key"]) for r in candidates}
    if len(review_keys) != EXPECTED_TOTAL:
        raise SystemExit("CANDIDATE_REVIEW_KEY_NOT_UNIQUE")
    if len(source_keys) != EXPECTED_TOTAL:
        raise SystemExit("CANDIDATE_SOURCE_KEY_NOT_UNIQUE")
    if len(pair_set) != EXPECTED_TOTAL:
        raise SystemExit("CANDIDATE_PAIR_NOT_UNIQUE")

    out: list[dict] = []
    for r in candidates:
        mtype = r["gpt_mapping_type"]
        if mtype not in _DECISION_BY_TYPE:
            raise SystemExit(f"CANDIDATE_UNEXPECTED_MAPPING_TYPE {mtype}")
        decision, reason = _DECISION_BY_TYPE[mtype]
        if not r["gpt_target_canonical_id"]:
            raise SystemExit(f"CANDIDATE_TARGET_BLANK {r['review_key']}")
        if not r["gpt_target_canonical_name"]:
            raise SystemExit(f"CANDIDATE_TARGET_NAME_BLANK {r['review_key']}")
        out.append(
            {
                "approval_id": APPROVAL_ID,
                "review_key": r["review_key"],
                "source_key": r["source_key"],
                "project_kind": r["project_kind"],
                "work_type": r["work_type"],
                "source_name": r["source_name"],
                "source_path": r["source_path"],
                "target_canonical_id": r["gpt_target_canonical_id"],
                "target_canonical_name": r["gpt_target_canonical_name"],
                "mapping_type": mtype,
                "gpt_confidence_class": r["gpt_confidence_class"],
                "owner_decision": decision,
                "owner_reason": reason,
                "source_aggregate_sha": FROZEN_MAPPING_CANDIDATES_SHA,
            }
        )

    out.sort(key=lambda r: r["review_key"])
    _assert_binding_shape(out, pair_set)
    return out


def _assert_binding_shape(
    rows: list[dict], expected_pair_set: set[tuple[str, str]]
) -> None:
    if len(rows) != EXPECTED_TOTAL:
        raise SystemExit(f"BINDING_ROW_DRIFT {len(rows)}")
    out_pairs = {(r["review_key"], r["source_key"]) for r in rows}
    if out_pairs != expected_pair_set:
        raise SystemExit(
            "BINDING_PAIR_SET_DRIFT "
            f"missing={len(expected_pair_set - out_pairs)} "
            f"unexpected={len(out_pairs - expected_pair_set)}"
        )
    decisions = Counter(r["owner_decision"] for r in rows)
    if decisions.get(DECISION_APPROVE, 0) != EXPECTED_APPROVED:
        raise SystemExit(f"APPROVED_COUNT_DRIFT {decisions.get(DECISION_APPROVE)}")
    if decisions.get(DECISION_HOLD, 0) != EXPECTED_HOLD:
        raise SystemExit(f"HOLD_COUNT_DRIFT {decisions.get(DECISION_HOLD)}")
    if len(decisions) != 2:
        raise SystemExit(f"BINDING_UNEXPECTED_DECISION_UNIVERSE {dict(decisions)}")
    # Every APPROVE row must be EXACT or NARROWER; every HOLD row must be POSSIBLE.
    for r in rows:
        if r["owner_decision"] == DECISION_APPROVE:
            if r["mapping_type"] not in {"EXACT_EQUIVALENT", "NARROWER_THAN"}:
                raise SystemExit(f"APPROVE_TYPE_MISMATCH {r['review_key']}")
            if r["owner_reason"] != REASON_APPROVE:
                raise SystemExit(f"APPROVE_REASON_MISMATCH {r['review_key']}")
        else:
            if r["mapping_type"] != "POSSIBLE_RELATED":
                raise SystemExit(f"HOLD_TYPE_MISMATCH {r['review_key']}")
            if r["owner_reason"] != REASON_HOLD:
                raise SystemExit(f"HOLD_REASON_MISMATCH {r['review_key']}")
        if not r["target_canonical_id"]:
            raise SystemExit(f"BINDING_TARGET_BLANK {r['review_key']}")
        if not r["target_canonical_name"]:
            raise SystemExit(f"BINDING_TARGET_NAME_BLANK {r['review_key']}")


def binding_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *BINDING_FIELDS)


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------


def render_receipt(rows: list[dict], sha_value: str) -> str:
    decisions = Counter(r["owner_decision"] for r in rows)
    mtype_counts = Counter(r["mapping_type"] for r in rows)
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-MAP-APPROVE-001 owner approval execution receipt
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KOSHA Mapping Owner Approval Execution Receipt

## Scope

```text
OWNER MAPPING APPROVAL EXECUTED

OWNER APPROVAL ID          = {APPROVAL_ID}

SOURCE SoT                 = {MAPPING_PATH.name}
SOURCE SHA                 = {FROZEN_MAPPING_CANDIDATES_SHA}

TOTAL CANDIDATES           = {len(rows)}
APPROVED                   = {decisions.get(DECISION_APPROVE, 0)}
HOLD                       = {decisions.get(DECISION_HOLD, 0)}
REJECTED                   = 0

EXACT_EQUIVALENT APPROVED  = {mtype_counts.get("EXACT_EQUIVALENT", 0)}
NARROWER_THAN APPROVED     = {mtype_counts.get("NARROWER_THAN", 0)}
POSSIBLE_RELATED HOLD      = {mtype_counts.get("POSSIBLE_RELATED", 0)}
```

## This receipt does NOT

```text
CANONICAL CONCEPT APPROVAL           = NOT EXECUTED
CANONICAL CREATE / RENAME / REPARENT = NOT EXECUTED
CANONICAL ACTIVE                     = NOT EXECUTED
PRODUCTION MATERIALIZATION           = NOT EXECUTED
KOSHA PRODUCTION MAPPINGS            = 0
MERGE                                = NOT AUTHORIZED
```

## Scope closure (WO §9)

```text
AMBIGUOUS            = 78  HOLD OUTSIDE PACKAGE
CANONICAL_GAP        = 196 BACKLOG (evidence complete, further GPT review DEFERRED)
NO_MATCH             = 271 EXCLUDED

TOTAL non-mapping    = 545
```

None of these are opened for new work by this WO. GPT consolidation
review of the 66-row gap review pack is deferred.

## Frozen output SHA

```text
RISK KOSHA MAP APPROVE001 OWNER APPROVAL BINDING SHA = {sha_value}
```

## Verdict

```text
{WO_ID}         = PASS / CLOSED
OWNER APPROVAL   = EXECUTED
APPROVED         = 46
HOLD             = 29
REJECTED         = 0
PRODUCTION WRITE = 0
MERGE            = NOT AUTHORIZED
NEXT             = WO-RISK-KOSHA-MAP-MATERIALIZE-001
STOP
```
"""


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


def write_all() -> dict:
    rows_a = build_binding()
    rows_b = build_binding()
    if rows_a != rows_b:
        raise SystemExit("BINDING_ROW_ORDER_DRIFT")
    sha_a = binding_sha(rows_a)
    sha_b = binding_sha(rows_b)
    if sha_a != sha_b:
        raise SystemExit(f"BINDING_SHA_DRIFT {sha_a} vs {sha_b}")

    write_tsv(rows_a, BINDING_PATH, BINDING_FIELDS)
    RECEIPT_PATH.write_text(render_receipt(rows_a, sha_a), encoding="utf-8")

    decisions = Counter(r["owner_decision"] for r in rows_a)
    mtypes = Counter(r["mapping_type"] for r in rows_a)
    return {
        "binding_rows": len(rows_a),
        "approved": decisions.get(DECISION_APPROVE, 0),
        "hold": decisions.get(DECISION_HOLD, 0),
        "rejected": 0,
        "exact_approved": mtypes.get("EXACT_EQUIVALENT", 0),
        "narrower_approved": mtypes.get("NARROWER_THAN", 0),
        "possible_related_hold": mtypes.get("POSSIBLE_RELATED", 0),
        "binding_sha_run1": sha_a,
        "binding_sha_run2": sha_b,
        "candidate_sot_sha": FROZEN_MAPPING_CANDIDATES_SHA,
        "binding_path": str(BINDING_PATH),
        "receipt_path": str(RECEIPT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} owner approval executor")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
