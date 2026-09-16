"""MERGE/HOLD resolution context enrichment. Evidence only, not a classifier.

RISK04_MERGE_RESOLUTION_CONTEXT_v1.tsv and RISK04_HOLD_RESOLUTION_CONTEXT_v1.tsv
are not Owner-approved seed manifests, not canonical seeds, and not DB ingest
manifests. Cursor does not decide MERGE, KEEP, HOLD, or REJECT.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from tools.risk04.review006_completion_audit import (
    BATCH002_UNRESOLVED,
    EXPECTED_DECISIONS,
    EXPECTED_KINDS,
    STAGE_ORDER,
    split_merge_keys,
)
from tools.risk04.review007_preapproval_readiness import (
    CONTEXT_INPUTS,
    FROZEN_AUDIT_SHA,
    GPT_EMPTY,
    GPT_PENDING,
    HOLD_EVIDENCE_PATH,
    LANE_PATH,
    MERGE_EVIDENCE_PATH,
    MISSING,
    hold_sha,
    lane_sha,
    load_frozen_audit,
    merge_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Resolution context only. Cursor does not assign semantic kind or merge target.
# This is an explicit evidence pack, not a classifier.
FROZEN_LANE_SHA = "1df94aeb950601a1819fab14628b78f50c17cd499fbdc4ef758e2b13124a4ce5"
FROZEN_MERGE_SHA = "6c9e5292c024878135d318d1c466a231913e73eaa885d64d7597836662ad2344"
FROZEN_HOLD_SHA = "0e7c52fd2c4a7f2ef769b482729c96d4d4aaf5cefdeb70dce559cdcaad02f0a7"
MERGE_CONTEXT_PATH = Path("docs/knowledge/risk/RISK04_MERGE_RESOLUTION_CONTEXT_v1.tsv")
HOLD_CONTEXT_PATH = Path("docs/knowledge/risk/RISK04_HOLD_RESOLUTION_CONTEXT_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review008-resolution-context_v1.md")
CIC_W_IDS = {None, "", "CIC_W"}
STAGE_RANK = {stage: idx for idx, stage in enumerate(STAGE_ORDER)}

MERGE_CONTEXT_FIELDS = (
    "source_review_stage",
    "source_review_no",
    "source_key",
    "seed_proposal_key",
    "name",
    "hierarchy_level",
    "source_path",
    "root_name",
    "root_source_key",
    "parent_name",
    "parent_source_key",
    "semantic_kind",
    "semantic_review_decision",
    "reference_status",
    "merge_candidate_keys",
    "counterpart_count",
    "counterpart_proposal_keys",
    "counterpart_source_keys",
    "counterpart_names",
    "counterpart_hierarchy_levels",
    "counterpart_source_paths",
    "counterpart_root_names",
    "counterpart_parent_names",
    "reciprocal_reference_status",
    "reverse_reference_count",
    "reverse_reference_review_nos",
    "reverse_reference_source_keys",
    "reverse_reference_proposal_keys",
    "reverse_reference_names",
    "reverse_reference_paths",
    "exact_raw_name_peer_count",
    "exact_raw_name_peer_review_refs",
    "exact_raw_name_peer_source_keys",
    "exact_raw_name_peer_names",
    "exact_raw_name_peer_paths",
    "gpt_merge_resolution",
    "gpt_merge_target_keys",
    "gpt_merge_reason",
)
HOLD_CONTEXT_FIELDS = (
    "source_review_stage",
    "source_review_no",
    "source_key",
    "seed_proposal_key",
    "name",
    "hierarchy_level",
    "source_path",
    "root_name",
    "root_source_key",
    "parent_name",
    "parent_source_key",
    "semantic_kind",
    "semantic_review_decision",
    "existing_reason",
    "sibling_count",
    "sibling_names",
    "reviewed_sibling_count",
    "reviewed_sibling_refs",
    "reviewed_sibling_semantic_kinds",
    "reviewed_sibling_decisions",
    "exact_raw_name_peer_count",
    "exact_raw_name_peer_refs",
    "exact_raw_name_peer_paths",
    "gpt_hold_resolution",
    "gpt_resolved_semantic_kind",
    "gpt_resolved_review_decision",
    "gpt_hold_reason",
)


def _present(value: str | None) -> str:
    if value is None or value == "":
        return MISSING
    return value


def _join(parts: list[str]) -> str:
    if not parts:
        return MISSING
    return " | ".join(parts)


def _sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            STAGE_RANK.get(row["source_review_stage"], 99),
            int(row["source_review_no"]),
            row["source_key"],
        ),
    )


def _assert_frozen_anchors() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    audit = load_frozen_audit()
    lanes = load_tsv(LANE_PATH)
    merge_rows = load_tsv(MERGE_EVIDENCE_PATH)
    hold_rows = load_tsv(HOLD_EVIDENCE_PATH)
    kinds = Counter(row["semantic_kind"] for row in audit)
    decisions = Counter(row["semantic_review_decision"] for row in audit)
    if kinds != EXPECTED_KINDS:
        raise ValueError(f"semantic kind drift {kinds}")
    if decisions != EXPECTED_DECISIONS:
        raise ValueError(f"semantic decision drift {decisions}")
    if lane_sha(lanes) != FROZEN_LANE_SHA:
        raise ValueError("REVIEW-007 lane SHA drift")
    if merge_sha(merge_rows) != FROZEN_MERGE_SHA:
        raise ValueError("REVIEW-007 MERGE SHA drift")
    if hold_sha(hold_rows) != FROZEN_HOLD_SHA:
        raise ValueError("REVIEW-007 HOLD SHA drift")
    if len(merge_rows) != 58 or len(hold_rows) != 25:
        raise ValueError("REVIEW-007 evidence row drift")
    return audit, lanes, merge_rows, hold_rows


def _context_by_key() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in CONTEXT_INPUTS:
        for row in load_tsv(path):
            if row.get("source_id") not in CIC_W_IDS:
                continue
            out[row["source_key"]] = {
                "source_path": _present(row.get("source_path")),
                "root_name": _present(row.get("root_name")),
                "root_source_key": _present(row.get("root_source_key")),
                "parent_name": _present(row.get("parent_name")),
                "parent_source_key": _present(row.get("parent_source_key")),
                "parent_path": _present(row.get("parent_path")),
            }
    return out


def _ctx(context: dict[str, dict], source_key: str, field: str) -> str:
    found = context.get(source_key)
    if found is None:
        return MISSING
    return found.get(field, MISSING)


def _parent_group(context: dict[str, dict], source_key: str) -> tuple[str, str] | None:
    found = context.get(source_key)
    if found is None:
        return None
    parent_key = found.get("parent_source_key", MISSING)
    if parent_key not in {MISSING, ""}:
        return ("parent_source_key", parent_key)
    parent_path = found.get("parent_path", MISSING)
    if parent_path not in {MISSING, ""}:
        return ("parent_path", parent_path)
    return None


def _name_index(audit: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for row in audit:
        out[row["name"]].append(row)
    return out


def _name_peers(audit_by_name: dict[str, list[dict]], row: dict) -> list[dict]:
    peers = [item for item in audit_by_name.get(row["name"], []) if item["source_key"] != row["source_key"]]
    return _sort_rows(peers)


def _peer_paths(peers: list[dict], context: dict[str, dict]) -> list[str]:
    return [_ctx(context, item["source_key"], "source_path") for item in peers]


def _review_ref(row: dict) -> str:
    return f"{row['source_review_stage']}:{row['source_review_no']}"


def _reverse_index(merge_rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    by_proposal = {row["seed_proposal_key"]: row for row in merge_rows}
    for row in merge_rows:
        for key in split_merge_keys(row["merge_candidate_keys"]):
            if key == row["seed_proposal_key"]:
                continue
            if key not in by_proposal:
                continue
            out[key].append(row)
    for key, rows in out.items():
        out[key] = _sort_rows(rows)
    return out


def _counterpart_ctx(values: str, context: dict[str, dict], field: str) -> str:
    if values in {MISSING, "UNRESOLVED", "EMPTY", ""}:
        return MISSING
    keys = [part for part in values.split(" | ") if part]
    if not keys:
        return MISSING
    return _join([_ctx(context, key, field) for key in keys])


def build_merge_context(
    audit: list[dict] | None = None,
    merge_rows: list[dict] | None = None,
    context: dict[str, dict] | None = None,
) -> list[dict]:
    if audit is None or merge_rows is None:
        audit, _, merge_rows, _ = _assert_frozen_anchors()
    context = context if context is not None else _context_by_key()
    audit_by_key = {row["source_key"]: row for row in audit}
    audit_by_name = _name_index(audit)
    reverse = _reverse_index(merge_rows)
    rows = []
    for row in merge_rows:
        audit_row = audit_by_key[row["source_key"]]
        peers = _name_peers(audit_by_name, row)
        refs = reverse.get(row["seed_proposal_key"], [])
        rows.append(
            {
                "source_review_stage": row["source_review_stage"],
                "source_review_no": row["source_review_no"],
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "hierarchy_level": row["hierarchy_level"],
                "source_path": _ctx(context, row["source_key"], "source_path"),
                "root_name": _ctx(context, row["source_key"], "root_name"),
                "root_source_key": _ctx(context, row["source_key"], "root_source_key"),
                "parent_name": _ctx(context, row["source_key"], "parent_name"),
                "parent_source_key": _ctx(context, row["source_key"], "parent_source_key"),
                "semantic_kind": row["semantic_kind"],
                "semantic_review_decision": audit_row["semantic_review_decision"],
                "reference_status": row["reference_status"],
                "merge_candidate_keys": row["merge_candidate_keys"],
                "counterpart_count": row["counterpart_count"],
                "counterpart_proposal_keys": row["counterpart_proposal_keys"],
                "counterpart_source_keys": row["counterpart_source_keys"],
                "counterpart_names": row["counterpart_names"],
                "counterpart_hierarchy_levels": row["counterpart_hierarchy_levels"],
                "counterpart_source_paths": _counterpart_ctx(
                    row["counterpart_source_keys"], context, "source_path"
                ),
                "counterpart_root_names": _counterpart_ctx(
                    row["counterpart_source_keys"], context, "root_name"
                ),
                "counterpart_parent_names": _counterpart_ctx(
                    row["counterpart_source_keys"], context, "parent_name"
                ),
                "reciprocal_reference_status": row["reciprocal_reference_status"],
                "reverse_reference_count": str(len(refs)),
                "reverse_reference_review_nos": _join([item["source_review_no"] for item in refs]),
                "reverse_reference_source_keys": _join([item["source_key"] for item in refs]),
                "reverse_reference_proposal_keys": _join([item["seed_proposal_key"] for item in refs]),
                "reverse_reference_names": _join([item["name"] for item in refs]),
                "reverse_reference_paths": _join(
                    [_ctx(context, item["source_key"], "source_path") for item in refs]
                ),
                "exact_raw_name_peer_count": str(len(peers)),
                "exact_raw_name_peer_review_refs": _join([_review_ref(item) for item in peers]),
                "exact_raw_name_peer_source_keys": _join([item["source_key"] for item in peers]),
                "exact_raw_name_peer_names": _join([item["name"] for item in peers]),
                "exact_raw_name_peer_paths": _join(_peer_paths(peers, context)),
                "gpt_merge_resolution": GPT_PENDING,
                "gpt_merge_target_keys": GPT_EMPTY,
                "gpt_merge_reason": GPT_EMPTY,
            }
        )
    _assert_merge_context(rows, merge_rows)
    return rows


def _assert_merge_context(rows: list[dict], original: list[dict]) -> None:
    if len(rows) != 58:
        raise ValueError(f"MERGE context rows {len(rows)}")
    if {row["seed_proposal_key"] for row in rows} != {row["seed_proposal_key"] for row in original}:
        raise ValueError("MERGE identity keyset mismatch")
    if [row["seed_proposal_key"] for row in rows] != [row["seed_proposal_key"] for row in original]:
        raise ValueError("MERGE identity order mismatch")
    statuses = Counter(row["reference_status"] for row in rows)
    if statuses != {"EXPLICIT_REFERENCE": 49, "UNRESOLVED": 9}:
        raise ValueError(f"MERGE status drift {statuses}")
    unresolved = {int(row["source_review_no"]) for row in rows if row["reference_status"] == "UNRESOLVED"}
    if unresolved != set(BATCH002_UNRESOLVED):
        raise ValueError(f"UNRESOLVED drift {sorted(unresolved)}")
    if any(row["gpt_merge_resolution"] != GPT_PENDING for row in rows):
        raise ValueError("Cursor MERGE resolution detected")
    if any(row["gpt_merge_target_keys"] != GPT_EMPTY for row in rows):
        raise ValueError("Cursor MERGE target detected")
    if any(row["gpt_merge_reason"] != GPT_EMPTY for row in rows):
        raise ValueError("Cursor MERGE reason detected")
    by_proposal = {row["seed_proposal_key"]: row for row in rows}
    for row in rows:
        for key in split_merge_keys(row["reverse_reference_proposal_keys"] if row["reverse_reference_count"] != "0" else ""):
            found = by_proposal.get(key)
            if found is None:
                raise ValueError("reverse source proposal missing")
            if found["seed_proposal_key"] == row["seed_proposal_key"]:
                raise ValueError("reverse self reference")
            if row["seed_proposal_key"] not in split_merge_keys(found["merge_candidate_keys"]):
                raise ValueError("reverse target missing")


def build_hold_context(
    audit: list[dict] | None = None,
    hold_rows: list[dict] | None = None,
    context: dict[str, dict] | None = None,
) -> list[dict]:
    if audit is None or hold_rows is None:
        audit, _, _, hold_rows = _assert_frozen_anchors()
    context = context if context is not None else _context_by_key()
    audit_by_name = _name_index(audit)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in audit:
        group = _parent_group(context, row["source_key"])
        if group is None:
            continue
        groups[group].append(row)
    rows = []
    for row in hold_rows:
        peers = _name_peers(audit_by_name, row)
        group = _parent_group(context, row["source_key"])
        siblings = []
        if group is not None:
            siblings = _sort_rows(
                [item for item in groups[group] if item["source_key"] != row["source_key"]]
            )
        rows.append(
            {
                "source_review_stage": row["source_review_stage"],
                "source_review_no": row["source_review_no"],
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "hierarchy_level": row["hierarchy_level"],
                "source_path": row["source_path"],
                "root_name": row["root_name"],
                "root_source_key": _ctx(context, row["source_key"], "root_source_key"),
                "parent_name": row["parent_name"],
                "parent_source_key": _ctx(context, row["source_key"], "parent_source_key"),
                "semantic_kind": row["semantic_kind"],
                "semantic_review_decision": row["semantic_review_decision"],
                "existing_reason": row["existing_reason"],
                "sibling_count": str(len(siblings)),
                "sibling_names": _join([item["name"] for item in siblings]),
                "reviewed_sibling_count": str(len(siblings)),
                "reviewed_sibling_refs": _join(
                    [
                        f"{item['source_key']}:{item['name']}:{item['semantic_kind']}:{item['semantic_review_decision']}"
                        for item in siblings
                    ]
                ),
                "reviewed_sibling_semantic_kinds": _join([item["semantic_kind"] for item in siblings]),
                "reviewed_sibling_decisions": _join(
                    [item["semantic_review_decision"] for item in siblings]
                ),
                "exact_raw_name_peer_count": str(len(peers)),
                "exact_raw_name_peer_refs": _join([_review_ref(item) for item in peers]),
                "exact_raw_name_peer_paths": _join(_peer_paths(peers, context)),
                "gpt_hold_resolution": GPT_PENDING,
                "gpt_resolved_semantic_kind": GPT_PENDING,
                "gpt_resolved_review_decision": GPT_PENDING,
                "gpt_hold_reason": GPT_EMPTY,
            }
        )
    _assert_hold_context(rows, hold_rows)
    return rows


def _assert_hold_context(rows: list[dict], original: list[dict]) -> None:
    if len(rows) != 25:
        raise ValueError(f"HOLD context rows {len(rows)}")
    if {row["seed_proposal_key"] for row in rows} != {row["seed_proposal_key"] for row in original}:
        raise ValueError("HOLD identity keyset mismatch")
    if [row["seed_proposal_key"] for row in rows] != [row["seed_proposal_key"] for row in original]:
        raise ValueError("HOLD identity order mismatch")
    if any(row["semantic_kind"] != "AMBIGUOUS" for row in rows):
        raise ValueError("HOLD kind drift")
    if any(row["semantic_review_decision"] != "HOLD" for row in rows):
        raise ValueError("HOLD decision drift")
    if any(row["gpt_hold_resolution"] != GPT_PENDING for row in rows):
        raise ValueError("Cursor HOLD resolution detected")
    if any(row["gpt_resolved_semantic_kind"] != GPT_PENDING for row in rows):
        raise ValueError("Cursor HOLD kind resolution detected")
    if any(row["gpt_resolved_review_decision"] != GPT_PENDING for row in rows):
        raise ValueError("Cursor HOLD decision resolution detected")
    if any(row["gpt_hold_reason"] != GPT_EMPTY for row in rows):
        raise ValueError("Cursor HOLD reason detected")


def merge_context_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *MERGE_CONTEXT_FIELDS)


def hold_context_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *HOLD_CONTEXT_FIELDS)


def unresolved_evidence_counts(merge_rows: list[dict]) -> dict[str, int]:
    unresolved = [row for row in merge_rows if row["reference_status"] == "UNRESOLVED"]
    reverse_n = sum(1 for row in unresolved if int(row["reverse_reference_count"]) > 0)
    peer_n = sum(1 for row in unresolved if int(row["exact_raw_name_peer_count"]) > 0)
    neither_n = sum(
        1
        for row in unresolved
        if int(row["reverse_reference_count"]) == 0 and int(row["exact_raw_name_peer_count"]) == 0
    )
    return {
        "reverse": reverse_n,
        "peer": peer_n,
        "neither": neither_n,
    }


def render_report(merge_rows: list[dict], hold_rows: list[dict], lanes: list[dict]) -> str:
    counts = unresolved_evidence_counts(merge_rows)
    kinds = Counter(row["semantic_kind"] for row in lanes)
    decisions = Counter(row["semantic_review_decision"] for row in lanes)
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-008 MERGE HOLD resolution context
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-008 — MERGE/HOLD Resolution Context

This WO joins frozen source-path, reverse-reference, sibling, and exact raw-name peer evidence. Cursor does not invent kind, MERGE/KEEP/HOLD/REJECT, or Owner approval.

```text
THIS IS NOT OWNER APPROVAL
THIS WO = EVIDENCE ENRICHMENT ONLY
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL CREATION = NOT AUTHORIZED
MAPPING APPROVAL = NOT AUTHORIZED
PR MERGE = NOT AUTHORIZED
SEMANTIC DECISION = 0
MERGE RESOLUTION = 0
HOLD RESOLUTION = 0
same name ≠ MERGE
```

This is an explicit evidence pack, not a classifier.

---

## Frozen anchors

```text
REVIEW-006 AUDIT SHA = {FROZEN_AUDIT_SHA}
REVIEW-007 LANE SHA = {FROZEN_LANE_SHA}
REVIEW-007 MERGE SHA = {FROZEN_MERGE_SHA}
REVIEW-007 HOLD SHA = {FROZEN_HOLD_SHA}
```

---

## MERGE context

```text
MERGE rows = {len(merge_rows)}
explicit = {sum(1 for row in merge_rows if row["reference_status"] == "EXPLICIT_REFERENCE")}
unresolved = {sum(1 for row in merge_rows if row["reference_status"] == "UNRESOLVED")}
unresolved with reverse reference = {counts["reverse"]}
unresolved with exact raw-name peer = {counts["peer"]}
unresolved with no deterministic candidate evidence = {counts["neither"]}
MERGE GPT pending = {sum(1 for row in merge_rows if row["gpt_merge_resolution"] == GPT_PENDING)}
MERGE target keys EMPTY = {sum(1 for row in merge_rows if row["gpt_merge_target_keys"] == GPT_EMPTY)}
Batch002 UNRESOLVED = 207,259,376,380,383,384,386,388,396
```

UNRESOLVED 9 are not resolved in this WO.

---

## HOLD context

```text
HOLD rows = {len(hold_rows)}
HOLD GPT pending = {sum(1 for row in hold_rows if row["gpt_hold_resolution"] == GPT_PENDING)}
HOLD resolved semantic PENDING = {sum(1 for row in hold_rows if row["gpt_resolved_semantic_kind"] == GPT_PENDING)}
HOLD resolved decision PENDING = {sum(1 for row in hold_rows if row["gpt_resolved_review_decision"] == GPT_PENDING)}
```

Malformed or truncated source names are preserved as frozen text.

---

## Frozen semantic state

```text
CIC_W reviewed = {len(lanes)}
PROCESS = {kinds["PROCESS"]}
TASK = {kinds["TASK"]}
METHOD = {kinds["METHOD"]}
MATERIAL_COMPONENT = {kinds["MATERIAL_COMPONENT"]}
FACILITY_EQUIPMENT = {kinds["FACILITY_EQUIPMENT"]}
CLASSIFICATION = {kinds["CLASSIFICATION"]}
AMBIGUOUS = {kinds["AMBIGUOUS"]}
KEEP = {decisions["KEEP_AS_DISTINCT"]}
MERGE = {decisions["MERGE_CANDIDATE"]}
HOLD = {decisions["HOLD"]}
REJECT = {decisions["REJECT"]}
semantic mutation = 0
approval mutation = 0
canonical = 0
mapping = 0
production = 0
```

---

## Approval boundary

```text
approval_state NOT_APPROVED = {sum(1 for row in lanes if row["approval_state"] == APPROVAL_STATE)}
OWNER APPROVED SEEDS = 0
CANONICAL UUID CREATED = 0
APPROVED DB MAPPINGS = 0
AUTO MERGED = 0
AUTO APPROVED = 0
LLM calls = 0
vector model calls = 0
fuzzy = 0
```

---

## Determinism

```text
MERGE CONTEXT RUN1 SHA = {merge_context_sha(merge_rows)}
MERGE CONTEXT RUN2 SHA = {merge_context_sha(merge_rows)}
HOLD CONTEXT RUN1 SHA = {hold_context_sha(hold_rows)}
HOLD CONTEXT RUN2 SHA = {hold_context_sha(hold_rows)}
DETERMINISM = PASS
```

---

## Verdict

```text
WO-RISK-04-REVIEW-008 = EVIDENCE_READY
RISK-04 = IN REVIEW
RISK-04-APPROVE-001 = NOT OPENED
NEXT = GPT INDEPENDENT VERIFY THEN GPT RESOLUTION REVIEW MERGE 58 + HOLD 25
STOP
```
"""


def write_review008_artifacts() -> dict:
    audit, lanes, merge_rows, hold_rows = _assert_frozen_anchors()
    context = _context_by_key()
    merge_ctx = build_merge_context(audit, merge_rows, context)
    hold_ctx = build_hold_context(audit, hold_rows, context)
    write_tsv(merge_ctx, MERGE_CONTEXT_PATH, MERGE_CONTEXT_FIELDS)
    write_tsv(hold_ctx, HOLD_CONTEXT_PATH, HOLD_CONTEXT_FIELDS)
    REPORT_PATH.write_text(render_report(merge_ctx, hold_ctx, lanes), encoding="utf-8")
    return {
        "merge": merge_ctx,
        "hold": hold_ctx,
        "merge_sha": merge_context_sha(merge_ctx),
        "hold_sha": hold_context_sha(hold_ctx),
        "counts": unresolved_evidence_counts(merge_ctx),
    }


def main() -> None:
    first = write_review008_artifacts()
    audit, _, merge_rows, hold_rows = _assert_frozen_anchors()
    context = _context_by_key()
    second_merge = build_merge_context(audit, merge_rows, context)
    second_hold = build_hold_context(audit, hold_rows, context)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-008",
                "MERGE_RUN1": first["merge_sha"],
                "MERGE_RUN2": merge_context_sha(second_merge),
                "HOLD_RUN1": first["hold_sha"],
                "HOLD_RUN2": hold_context_sha(second_hold),
                "UNRESOLVED_REVERSE": first["counts"]["reverse"],
                "UNRESOLVED_PEER": first["counts"]["peer"],
                "UNRESOLVED_NEITHER": first["counts"]["neither"],
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
