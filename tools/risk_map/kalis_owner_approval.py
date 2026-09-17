"""WO-RISK-KALIS-MATERIALIZE-001 Owner approval binding.

Deterministic transcription of the Owner's decision (2026-09-17) onto the
frozen 48-row Owner mapping candidate pack. Claude Code does NOT re-decide;
it echoes Owner's authority into a signed binding artifact ready for
production materialization.

Decision (Owner authority, dated 2026-09-17):
  APPROVE :  9 rows  |  family = 장약 및 발파작업  →  발파굴착 (NARROWER_THAN)
  HOLD    : 39 rows  |  용접작업 29 + 양생작업 5 + 인발작업 5 (POSSIBLE_RELATED)
  TOTAL   : 48 rows
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
from tools.risk_map.kalis_map001_semantic_freeze import (
    OWNER_CANDIDATE_FIELDS,
    OWNER_CANDIDATE_PATH,
    owner_candidate_sha,
)

FROZEN_OWNER_CANDIDATE_SHA = (
    "848b896fe46829c53d09e6b7a6af52deacd5ebe66ba021af8a5ca2a799b3052f"
)

WO_ID = "WO-RISK-KALIS-MATERIALIZE-001"
APPROVAL_ID = "RISK-KALIS-MAP-APPROVE-001"
OWNER_APPROVAL_DATE = "2026-09-17"

APPROVE_FAMILY_NAME = "장약 및 발파작업"
APPROVE_TARGET_CANONICAL_ID = "473d69ee-4433-487f-bc43-c35c1f2ea28f"
APPROVE_TARGET_CANONICAL_NAME = "발파굴착"

EXPECTED_TOTAL = 48
EXPECTED_APPROVE = 9
EXPECTED_HOLD = 39

OWNER_APPROVAL_PATH = Path("docs/knowledge/risk/RISK_KALIS_OWNER_APPROVAL_v1.tsv")
OWNER_REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk-kalis-owner-approval_v1.md")

OWNER_APPROVAL_FIELDS: tuple[str, ...] = OWNER_CANDIDATE_FIELDS + (
    "approval_id",
    "owner_approval_date",
)

REASON_APPROVE = f"OWNER_APPROVED_{OWNER_APPROVAL_DATE}"
REASON_HOLD = f"OWNER_HOLD_{OWNER_APPROVAL_DATE}"


def _load_owner_candidates() -> list[dict]:
    rows = load_tsv(OWNER_CANDIDATE_PATH)
    if len(rows) != EXPECTED_TOTAL:
        raise SystemExit(f"OWNER_CANDIDATE_ROW_DRIFT {len(rows)}")
    got = owner_candidate_sha(rows)
    if got != FROZEN_OWNER_CANDIDATE_SHA:
        raise SystemExit(f"OWNER_CANDIDATE_SHA_DRIFT {got}")
    if list(rows[0].keys()) != list(OWNER_CANDIDATE_FIELDS):
        raise SystemExit("OWNER_CANDIDATE_FIELD_DRIFT")
    for r in rows:
        if r["owner_decision"] or r["owner_reason"]:
            raise SystemExit(f"OWNER_DECISION_PRE_POPULATED {r['review_key']}")
    return rows


def build_owner_approval() -> list[dict]:
    candidates = _load_owner_candidates()

    out: list[dict] = []
    for r in candidates:
        if r["name_normalized"] == APPROVE_FAMILY_NAME:
            if r["semantic_decision"] != "NARROWER_THAN":
                raise SystemExit(f"APPROVE_FAMILY_UNEXPECTED_DECISION {r['review_key']}")
            if r["target_canonical_id"] != APPROVE_TARGET_CANONICAL_ID:
                raise SystemExit(f"APPROVE_FAMILY_UNEXPECTED_TARGET {r['review_key']}")
            if r["target_canonical_name"] != APPROVE_TARGET_CANONICAL_NAME:
                raise SystemExit(f"APPROVE_FAMILY_UNEXPECTED_TARGET_NAME {r['review_key']}")
            decision = "APPROVE"
            reason = REASON_APPROVE
        else:
            if r["semantic_decision"] != "POSSIBLE_RELATED":
                raise SystemExit(f"HOLD_FAMILY_UNEXPECTED_DECISION {r['review_key']}")
            if r["name_normalized"] not in {"용접작업", "양생작업", "인발작업"}:
                raise SystemExit(f"UNEXPECTED_HOLD_FAMILY {r['name_normalized']}")
            decision = "HOLD"
            reason = REASON_HOLD
        out.append(
            {
                **r,
                "owner_decision": decision,
                "owner_reason": reason,
                "approval_id": APPROVAL_ID,
                "owner_approval_date": OWNER_APPROVAL_DATE,
            }
        )
    out.sort(key=lambda r: r["review_key"])
    _assert_owner_binding(out)
    return out


def _assert_owner_binding(rows: list[dict]) -> None:
    if len(rows) != EXPECTED_TOTAL:
        raise SystemExit(f"OWNER_BINDING_ROW_DRIFT {len(rows)}")
    decisions = Counter(r["owner_decision"] for r in rows)
    if decisions != Counter({"APPROVE": EXPECTED_APPROVE, "HOLD": EXPECTED_HOLD}):
        raise SystemExit(f"OWNER_DECISION_CENSUS_DRIFT {dict(decisions)}")

    approved = [r for r in rows if r["owner_decision"] == "APPROVE"]
    if len({r["source_key"] for r in approved}) != EXPECTED_APPROVE:
        raise SystemExit("APPROVED_SOURCE_KEY_NOT_UNIQUE")
    if {r["name_normalized"] for r in approved} != {APPROVE_FAMILY_NAME}:
        raise SystemExit("APPROVED_FAMILY_DRIFT")
    if {r["target_canonical_id"] for r in approved} != {APPROVE_TARGET_CANONICAL_ID}:
        raise SystemExit("APPROVED_TARGET_DRIFT")
    if {r["mapping_type"] for r in approved} != {"NARROWER_THAN"}:
        raise SystemExit("APPROVED_MAPPING_TYPE_DRIFT")

    hold = [r for r in rows if r["owner_decision"] == "HOLD"]
    if {r["name_normalized"] for r in hold} != {"용접작업", "양생작업", "인발작업"}:
        raise SystemExit("HOLD_FAMILY_DRIFT")
    if {r["mapping_type"] for r in hold} != {"POSSIBLE_RELATED"}:
        raise SystemExit("HOLD_MAPPING_TYPE_DRIFT")

    # HOLD source_keys must never appear in APPROVE set.
    hold_keys = {r["source_key"] for r in hold}
    approved_keys = {r["source_key"] for r in approved}
    if hold_keys & approved_keys:
        raise SystemExit("HOLD_LEAKED_INTO_APPROVED_SET")


def owner_approval_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *OWNER_APPROVAL_FIELDS)


def render_owner_report(rows: list[dict], sha_value: str) -> str:
    decisions = Counter(r["owner_decision"] for r in rows)
    hold_counts = Counter(
        r["name_normalized"] for r in rows if r["owner_decision"] == "HOLD"
    )
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KALIS-MATERIALIZE-001 Owner approval binding
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KALIS Owner Approval Binding (Frozen)

## Owner authority

```text
OWNER APPROVAL ID       = {APPROVAL_ID}
OWNER APPROVAL DATE     = {OWNER_APPROVAL_DATE}
```

## Decision

```text
APPROVE                 = {decisions.get("APPROVE", 0)}
HOLD                    = {decisions.get("HOLD", 0)}
REJECTED                = 0
TOTAL                   = {sum(decisions.values())}
```

APPROVED family:

```text
{APPROVE_FAMILY_NAME}
  semantic         = NARROWER_THAN
  target_canonical = {APPROVE_TARGET_CANONICAL_ID}
  target_name      = {APPROVE_TARGET_CANONICAL_NAME}
  source rows      = {decisions.get("APPROVE", 0)}
```

HOLD families:

```text
용접작업              = {hold_counts.get("용접작업", 0)}
양생작업              = {hold_counts.get("양생작업", 0)}
인발작업              = {hold_counts.get("인발작업", 0)}
```

## Contract

```text
FROZEN OWNER APPROVAL BINDING SHA = {sha_value}

CANONICAL CREATE        = 0
CANONICAL RENAME        = 0
SECTOR WRITE            = 0
ACTIVE TRANSITION       = 0
PRODUCTION MATERIALIZED = NOT EXECUTED (this artifact is authority only)

FROZEN EVIDENCE REVERIFIED = NO
```

## Verdict

```text
{WO_ID} owner binding = FROZEN
NEXT = kalis_materialize_approved --execute
STOP
```
"""


def write_all() -> dict:
    rows_a = build_owner_approval()
    rows_b = build_owner_approval()
    if rows_a != rows_b:
        raise SystemExit("OWNER_APPROVAL_ROW_ORDER_DRIFT")
    sha_a = owner_approval_sha(rows_a)
    sha_b = owner_approval_sha(rows_b)
    if sha_a != sha_b:
        raise SystemExit(f"OWNER_APPROVAL_SHA_DRIFT {sha_a} vs {sha_b}")

    write_tsv(rows_a, OWNER_APPROVAL_PATH, OWNER_APPROVAL_FIELDS)
    OWNER_REPORT_PATH.write_text(render_owner_report(rows_a, sha_a), encoding="utf-8")

    decisions = Counter(r["owner_decision"] for r in rows_a)
    return {
        "owner_candidate_rows": len(rows_a),
        "approved": decisions.get("APPROVE", 0),
        "hold": decisions.get("HOLD", 0),
        "rejected": 0,
        "owner_approval_sha_run1": sha_a,
        "owner_approval_sha_run2": sha_b,
        "owner_approval_path": str(OWNER_APPROVAL_PATH),
        "owner_report_path": str(OWNER_REPORT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} owner approval binding")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
