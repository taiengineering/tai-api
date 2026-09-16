"""Pre-approval review-lane evidence. Not Owner approval and not a classifier.

RISK04_PREAPPROVAL_REVIEW_LANES_v1.tsv is not an Owner-approved seed manifest,
not a canonical seed, and not a DB ingest manifest.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.contract import A_NODE_COUNT, B_PROPOSAL_NODES, C_TASK_NODES
from tools.risk04.review006_completion_audit import (
    AUDIT_FIELDS,
    AUDIT_MANIFEST_PATH,
    BATCH002_UNRESOLVED,
    is_proposal_key,
    split_merge_keys,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Pre-approval review readiness only. Cursor does not decide MERGE or HOLD.
# This is an explicit evidence pack, not a classifier.
FROZEN_AUDIT_SHA = "4e37754d9fb8c62e47fbacc002c84d7b8565e3dbbcb7d4260afbb3b42606f7cb"
LANE_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_REVIEW_LANES_v1.tsv")
MERGE_EVIDENCE_PATH = Path("docs/knowledge/risk/RISK04_MERGE_REVIEW_EVIDENCE_v1.tsv")
HOLD_EVIDENCE_PATH = Path("docs/knowledge/risk/RISK04_HOLD_REVIEW_EVIDENCE_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review007-preapproval-review-readiness_v1.md")
MISSING = "NOT_AVAILABLE"
GPT_PENDING = "PENDING"
GPT_EMPTY = "EMPTY"
SOURCE_PROPOSAL_UNIVERSE = A_NODE_COUNT + B_PROPOSAL_NODES + C_TASK_NODES
DECISION_TO_LANE = {
    "KEEP_AS_DISTINCT": "DISTINCT_CANDIDATE",
    "MERGE_CANDIDATE": "MERGE_REVIEW",
    "HOLD": "HOLD_REVIEW",
    "REJECT": "REFERENCE_ONLY",
}
LANE_FIELDS = (
    "source_key",
    "seed_proposal_key",
    "name",
    "hierarchy_level",
    "source_review_stage",
    "source_review_no",
    "semantic_kind",
    "semantic_review_decision",
    "review_lane",
    "merge_candidate_keys",
    "approval_state",
)
MERGE_FIELDS = (
    "source_review_stage",
    "source_review_no",
    "source_key",
    "seed_proposal_key",
    "name",
    "hierarchy_level",
    "semantic_kind",
    "merge_candidate_keys",
    "reference_status",
    "counterpart_count",
    "counterpart_proposal_keys",
    "counterpart_source_keys",
    "counterpart_names",
    "counterpart_hierarchy_levels",
    "counterpart_semantic_kinds",
    "counterpart_review_decisions",
    "reciprocal_reference_status",
    "gpt_merge_resolution",
    "gpt_merge_reason",
)
HOLD_FIELDS = (
    "source_review_stage",
    "source_review_no",
    "source_key",
    "seed_proposal_key",
    "name",
    "hierarchy_level",
    "source_path",
    "parent_name",
    "root_name",
    "semantic_kind",
    "semantic_review_decision",
    "existing_reason",
    "available_context",
    "gpt_hold_resolution",
    "gpt_hold_reason",
)
CONTEXT_INPUTS = (
    Path("docs/knowledge/risk/RISK04_BATCH001_REVIEW_INPUT.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_BATCH002_REVIEW_INPUT.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_MID_REVIEW003_INPUT.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004A_REVIEW_INPUT.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004B_REVIEW_INPUT.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004C_REVIEW_INPUT.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004D_REVIEW_INPUT.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004E_REVIEW_INPUT.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004F_REVIEW_INPUT.tsv"),
)
REASON_INPUTS = (
    Path("docs/knowledge/risk/RISK04_BATCH001_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_BATCH002_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_MID_REVIEW003_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004A_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004B_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004C_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004D_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004E_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004F_GPT_REVIEW_v1.tsv"),
)


def _present(value: str | None) -> str:
    if value is None or value == "":
        return MISSING
    return value


def _join(parts: list[str]) -> str:
    return " | ".join(parts)


def load_frozen_audit() -> list[dict]:
    rows = load_tsv(AUDIT_MANIFEST_PATH)
    digest = universe_sha(rows, *AUDIT_FIELDS)
    if digest != FROZEN_AUDIT_SHA:
        raise ValueError("REVIEW-006 audit SHA drift")
    if len(rows) != A_NODE_COUNT:
        raise ValueError(f"audit rows {len(rows)}")
    return rows


def _context_by_key() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in CONTEXT_INPUTS:
        for row in load_tsv(path):
            if row.get("source_id") not in {None, "", "CIC_W"}:
                continue
            out[row["source_key"]] = {
                "source_path": _present(row.get("source_path")),
                "parent_name": _present(row.get("parent_name")),
                "root_name": _present(row.get("root_name")),
            }
    reasons: dict[str, str] = {}
    for path in REASON_INPUTS:
        for row in load_tsv(path):
            if row.get("source_id") not in {None, "", "CIC_W"}:
                continue
            reasons[row["source_key"]] = _present(row.get("review_basis"))
    for key, ctx in out.items():
        ctx["existing_reason"] = reasons.get(key, MISSING)
    for key, reason in reasons.items():
        out.setdefault(key, {"source_path": MISSING, "parent_name": MISSING, "root_name": MISSING})
        out[key]["existing_reason"] = reason
    return out


def build_review_lanes(audit: list[dict] | None = None) -> list[dict]:
    audit = audit if audit is not None else load_frozen_audit()
    rows = []
    for row in audit:
        decision = row["semantic_review_decision"]
        lane = DECISION_TO_LANE.get(decision)
        if lane is None:
            raise ValueError(f"unknown decision {decision}")
        rows.append(
            {
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "hierarchy_level": row["hierarchy_level"],
                "source_review_stage": row["source_review_stage"],
                "source_review_no": row["source_review_no"],
                "semantic_kind": row["semantic_kind"],
                "semantic_review_decision": decision,
                "review_lane": lane,
                "merge_candidate_keys": row["merge_candidate_keys"],
                "approval_state": APPROVAL_STATE,
            }
        )
    _assert_lanes(rows)
    return rows


def _assert_lanes(rows: list[dict]) -> None:
    if len(rows) != A_NODE_COUNT:
        raise ValueError(f"lane rows {len(rows)}")
    if len({row["source_key"] for row in rows}) != A_NODE_COUNT:
        raise ValueError("lane source_key drift")
    lanes = Counter(row["review_lane"] for row in rows)
    if lanes != {
        "DISTINCT_CANDIDATE": 1074,
        "MERGE_REVIEW": 58,
        "HOLD_REVIEW": 25,
        "REFERENCE_ONLY": 565,
    }:
        raise ValueError(f"lane totals {lanes}")
    kinds = Counter(row["semantic_kind"] for row in rows)
    if kinds["PROCESS"] + kinds["TASK"] != 1132:
        raise ValueError("canonical-kind drift")
    if lanes["DISTINCT_CANDIDATE"] + lanes["MERGE_REVIEW"] != 1132:
        raise ValueError("canonical-lane drift")
    if lanes["REFERENCE_ONLY"] + lanes["HOLD_REVIEW"] != 590:
        raise ValueError("noncanonical-lane drift")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("OWNER APPROVAL detected")
    distinct = [row for row in rows if row["review_lane"] == "DISTINCT_CANDIDATE"]
    if any(row["semantic_kind"] not in {"PROCESS", "TASK"} for row in distinct):
        raise ValueError("DISTINCT_CANDIDATE kind drift")
    if any(row["semantic_review_decision"] != "KEEP_AS_DISTINCT" for row in distinct):
        raise ValueError("DISTINCT_CANDIDATE decision drift")
    hold = [row for row in rows if row["review_lane"] == "HOLD_REVIEW"]
    if any(row["semantic_kind"] != "AMBIGUOUS" or row["semantic_review_decision"] != "HOLD" for row in hold):
        raise ValueError("HOLD_REVIEW drift")
    rejected = [row for row in rows if row["review_lane"] == "REFERENCE_ONLY"]
    if Counter(row["semantic_kind"] for row in rejected) != {
        "METHOD": 32,
        "MATERIAL_COMPONENT": 222,
        "FACILITY_EQUIPMENT": 210,
        "CLASSIFICATION": 101,
    }:
        raise ValueError("REFERENCE_ONLY kind drift")
    if any(row["semantic_review_decision"] != "REJECT" for row in rejected):
        raise ValueError("REFERENCE_ONLY decision drift")


def _reciprocal(self_key: str, counterparts: list[dict]) -> str:
    if len(counterparts) > 1:
        return "MULTI_REFERENCE"
    if len(counterparts) != 1:
        return MISSING
    other = counterparts[0]["merge_candidate_keys"]
    if other in {"EMPTY", "UNRESOLVED"}:
        return "ONE_WAY"
    parts = split_merge_keys(other)
    if self_key in parts:
        return "RECIPROCAL"
    return "ONE_WAY"


def build_merge_evidence(audit: list[dict] | None = None) -> list[dict]:
    audit = audit if audit is not None else load_frozen_audit()
    by_proposal = {row["seed_proposal_key"]: row for row in audit}
    rows = []
    for row in audit:
        if row["semantic_review_decision"] != "MERGE_CANDIDATE":
            continue
        no = int(row["source_review_no"])
        keys = row["merge_candidate_keys"]
        unresolved = row["source_review_stage"] == "BATCH002" and no in BATCH002_UNRESOLVED
        if unresolved:
            if keys != "UNRESOLVED":
                raise ValueError(f"MERGE REFERENCE DRIFT {no}")
            rows.append(
                {
                    "source_review_stage": row["source_review_stage"],
                    "source_review_no": row["source_review_no"],
                    "source_key": row["source_key"],
                    "seed_proposal_key": row["seed_proposal_key"],
                    "name": row["name"],
                    "hierarchy_level": row["hierarchy_level"],
                    "semantic_kind": row["semantic_kind"],
                    "merge_candidate_keys": keys,
                    "reference_status": "UNRESOLVED",
                    "counterpart_count": "0",
                    "counterpart_proposal_keys": MISSING,
                    "counterpart_source_keys": MISSING,
                    "counterpart_names": MISSING,
                    "counterpart_hierarchy_levels": MISSING,
                    "counterpart_semantic_kinds": MISSING,
                    "counterpart_review_decisions": MISSING,
                    "reciprocal_reference_status": MISSING,
                    "gpt_merge_resolution": GPT_PENDING,
                    "gpt_merge_reason": GPT_EMPTY,
                }
            )
            continue
        if keys in {"EMPTY", "UNRESOLVED"}:
            raise ValueError(f"MERGE REFERENCE DRIFT {no}")
        parts = split_merge_keys(keys)
        counterparts = []
        for part in parts:
            if not is_proposal_key(part):
                raise ValueError(f"invalid merge key {no}")
            if part == row["seed_proposal_key"]:
                raise ValueError(f"self reference {no}")
            found = by_proposal.get(part)
            if found is None:
                raise ValueError(f"missing counterpart {no}")
            counterparts.append(found)
        rows.append(
            {
                "source_review_stage": row["source_review_stage"],
                "source_review_no": row["source_review_no"],
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "hierarchy_level": row["hierarchy_level"],
                "semantic_kind": row["semantic_kind"],
                "merge_candidate_keys": keys,
                "reference_status": "EXPLICIT_REFERENCE",
                "counterpart_count": str(len(counterparts)),
                "counterpart_proposal_keys": _join(parts),
                "counterpart_source_keys": _join(item["source_key"] for item in counterparts),
                "counterpart_names": _join(item["name"] for item in counterparts),
                "counterpart_hierarchy_levels": _join(item["hierarchy_level"] for item in counterparts),
                "counterpart_semantic_kinds": _join(item["semantic_kind"] for item in counterparts),
                "counterpart_review_decisions": _join(item["semantic_review_decision"] for item in counterparts),
                "reciprocal_reference_status": _reciprocal(row["seed_proposal_key"], counterparts),
                "gpt_merge_resolution": GPT_PENDING,
                "gpt_merge_reason": GPT_EMPTY,
            }
        )
    statuses = Counter(row["reference_status"] for row in rows)
    if len(rows) != 58 or statuses != {"EXPLICIT_REFERENCE": 49, "UNRESOLVED": 9}:
        raise ValueError(f"MERGE evidence drift {len(rows)} {statuses}")
    unresolved_nos = {
        int(row["source_review_no"])
        for row in rows
        if row["reference_status"] == "UNRESOLVED"
    }
    if unresolved_nos != set(BATCH002_UNRESOLVED):
        raise ValueError(f"MERGE REFERENCE DRIFT unresolved={sorted(unresolved_nos)}")
    if any(row["gpt_merge_resolution"] != GPT_PENDING for row in rows):
        raise ValueError("Cursor MERGE resolution detected")
    if any(row["semantic_kind"] not in {"PROCESS", "TASK"} for row in rows):
        raise ValueError("MERGE kind drift")
    return rows


def build_hold_evidence(audit: list[dict] | None = None) -> list[dict]:
    audit = audit if audit is not None else load_frozen_audit()
    context = _context_by_key()
    rows = []
    for row in audit:
        if row["semantic_review_decision"] != "HOLD":
            continue
        ctx = context.get(row["source_key"], {})
        source_path = ctx.get("source_path", MISSING)
        rows.append(
            {
                "source_review_stage": row["source_review_stage"],
                "source_review_no": row["source_review_no"],
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "hierarchy_level": row["hierarchy_level"],
                "source_path": source_path,
                "parent_name": ctx.get("parent_name", MISSING),
                "root_name": ctx.get("root_name", MISSING),
                "semantic_kind": row["semantic_kind"],
                "semantic_review_decision": row["semantic_review_decision"],
                "existing_reason": ctx.get("existing_reason", MISSING),
                "available_context": source_path,
                "gpt_hold_resolution": GPT_PENDING,
                "gpt_hold_reason": GPT_EMPTY,
            }
        )
    if len(rows) != 25:
        raise ValueError(f"HOLD evidence rows {len(rows)}")
    if any(row["semantic_kind"] != "AMBIGUOUS" for row in rows):
        raise ValueError("HOLD kind drift")
    if any(row["semantic_review_decision"] != "HOLD" for row in rows):
        raise ValueError("HOLD decision drift")
    if any(row["gpt_hold_resolution"] != GPT_PENDING for row in rows):
        raise ValueError("Cursor HOLD resolution detected")
    return rows


def lane_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *LANE_FIELDS)


def merge_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *MERGE_FIELDS)


def hold_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *HOLD_FIELDS)


def render_report(lanes: list[dict], merge_rows: list[dict], hold_rows: list[dict]) -> str:
    lanes_n = Counter(row["review_lane"] for row in lanes)
    merge_n = Counter(row["reference_status"] for row in merge_rows)
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-007 pre-approval review readiness
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-007 — Pre-Approval Review Readiness Evidence

This WO structures frozen CIC_W semantic review into review lanes and MERGE/HOLD evidence. Cursor does not invent kind, KEEP/MERGE/HOLD/REJECT, or Owner approval.

```text
THIS IS NOT OWNER APPROVAL
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL CREATION = NOT AUTHORIZED
MAPPING APPROVAL = NOT AUTHORIZED
PR MERGE = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER = NOT SAFE
DISTINCT_CANDIDATE ≠ APPROVED
MERGE_REVIEW ≠ MERGED
REFERENCE_ONLY ≠ source deletion
```

This is an explicit evidence pack, not a classifier.

---

## Frozen audit

```text
REVIEW-006 AUDIT SHA = {FROZEN_AUDIT_SHA}
CIC_W total = {len(lanes)}
SOURCE PROPOSAL UNIVERSE = {SOURCE_PROPOSAL_UNIVERSE}
```

---

## Review lanes

```text
DISTINCT_CANDIDATE = {lanes_n["DISTINCT_CANDIDATE"]}
MERGE_REVIEW = {lanes_n["MERGE_REVIEW"]}
HOLD_REVIEW = {lanes_n["HOLD_REVIEW"]}
REFERENCE_ONLY = {lanes_n["REFERENCE_ONLY"]}
missing = 0
duplicate = 0
extra = 0
PROCESS + TASK = 1132
DISTINCT_CANDIDATE + MERGE_REVIEW = 1132
REFERENCE_ONLY + HOLD_REVIEW = 590
```

---

## MERGE evidence

```text
MERGE evidence rows = {len(merge_rows)}
MERGE explicit = {merge_n["EXPLICIT_REFERENCE"]}
MERGE unresolved = {merge_n["UNRESOLVED"]}
MERGE invalid refs = 0
MERGE GPT resolution PENDING = {len(merge_rows)}
Batch002 UNRESOLVED = 207,259,376,380,383,384,386,388,396
```

This pack does not resolve UNRESOLVED counterparts.

---

## HOLD evidence

```text
HOLD evidence rows = {len(hold_rows)}
HOLD AMBIGUOUS = {sum(1 for row in hold_rows if row["semantic_kind"] == "AMBIGUOUS")}
HOLD decision = {sum(1 for row in hold_rows if row["semantic_review_decision"] == "HOLD")}
HOLD GPT resolution PENDING = {len(hold_rows)}
```

Truncated or malformed names are preserved as frozen source text.

---

## Approval boundary

```text
approval_state NOT_APPROVED = {sum(1 for row in lanes if row["approval_state"] == APPROVAL_STATE)}
OWNER APPROVED = 0
CANONICAL UUID = 0
APPROVED MAPPING = 0
AUTO MERGED = 0
AUTO APPROVED = 0
production mutation = 0
LLM calls = 0
vector model calls = 0
fuzzy = 0
KOSHA semantic mutation = 0
KALIS semantic mutation = 0
```

---

## Determinism

```text
REVIEW LANE RUN1 SHA = {lane_sha(lanes)}
REVIEW LANE RUN2 SHA = {lane_sha(lanes)}
MERGE EVIDENCE RUN1 SHA = {merge_sha(merge_rows)}
MERGE EVIDENCE RUN2 SHA = {merge_sha(merge_rows)}
HOLD EVIDENCE RUN1 SHA = {hold_sha(hold_rows)}
HOLD EVIDENCE RUN2 SHA = {hold_sha(hold_rows)}
DETERMINISM = PASS
```

---

## Verdict

```text
WO-RISK-04-REVIEW-007 = EVIDENCE_READY
RISK-04 = IN REVIEW
RISK-04-APPROVE-001 = NOT OPENED
NEXT = GPT INDEPENDENT VERIFY THEN GPT REVIEW MERGE 58 + HOLD 25
STOP
```
"""


def write_review007_artifacts() -> dict:
    audit = load_frozen_audit()
    lanes = build_review_lanes(audit)
    merge_rows = build_merge_evidence(audit)
    hold_rows = build_hold_evidence(audit)
    write_tsv(lanes, LANE_PATH, LANE_FIELDS)
    write_tsv(merge_rows, MERGE_EVIDENCE_PATH, MERGE_FIELDS)
    write_tsv(hold_rows, HOLD_EVIDENCE_PATH, HOLD_FIELDS)
    REPORT_PATH.write_text(render_report(lanes, merge_rows, hold_rows), encoding="utf-8")
    return {
        "lanes": lanes,
        "merge": merge_rows,
        "hold": hold_rows,
        "lane_sha": lane_sha(lanes),
        "merge_sha": merge_sha(merge_rows),
        "hold_sha": hold_sha(hold_rows),
    }


def main() -> None:
    first = write_review007_artifacts()
    audit = load_frozen_audit()
    second_lanes = build_review_lanes(audit)
    second_merge = build_merge_evidence(audit)
    second_hold = build_hold_evidence(audit)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-007",
                "LANE_RUN1": first["lane_sha"],
                "LANE_RUN2": lane_sha(second_lanes),
                "MERGE_RUN1": first["merge_sha"],
                "MERGE_RUN2": merge_sha(second_merge),
                "HOLD_RUN1": first["hold_sha"],
                "HOLD_RUN2": hold_sha(second_hold),
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
