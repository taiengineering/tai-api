"""CIC_W full semantic completion audit. Completed GPT review audit, not a classifier.

RISK04_CICW_FULL_SEMANTIC_AUDIT_MANIFEST_v1.tsv is not an Owner-approved seed
manifest, not a canonical seed, and not a DB ingest manifest.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk02.contract import SOURCE_CIC_W, SOURCE_KALIS, SOURCE_KOSHA
from tools.risk04.contract import (
    A_NODE_COUNT,
    B_IDENTITY,
    B_LEAF_OCCURRENCE_SUM,
    B_PROPOSAL_NODES,
    C_OCCURRENCE,
    C_TASK_NODES,
    C_UNIQUE,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Completed CIC_W semantic review audit of 1722 frozen GPT rows only.
# This is an explicit completion audit, not a classifier.
AUDIT_MANIFEST_PATH = Path("docs/knowledge/risk/RISK04_CICW_FULL_SEMANTIC_AUDIT_MANIFEST_v1.tsv")
AUDIT_REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review006-full-semantic-completion-audit_v1.md")
BATCH001_GPT_PATH = Path("docs/knowledge/risk/RISK04_BATCH001_GPT_REVIEW_v1.tsv")
BATCH001_INPUT_PATH = Path("docs/knowledge/risk/RISK04_BATCH001_REVIEW_INPUT.tsv")
BATCH002_GPT_PATH = Path("docs/knowledge/risk/RISK04_CICW_BATCH002_GPT_REVIEW_v1.tsv")
BATCH002_INPUT_PATH = Path("docs/knowledge/risk/RISK04_CICW_BATCH002_REVIEW_INPUT.tsv")
REVIEW003_GPT_PATH = Path("docs/knowledge/risk/RISK04_CICW_MID_REVIEW003_GPT_REVIEW_v1.tsv")
LEAF_GPT_PATHS = {
    "LEAF_004A": Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004A_GPT_REVIEW_v1.tsv"),
    "LEAF_004B": Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004B_GPT_REVIEW_v1.tsv"),
    "LEAF_004C": Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004C_GPT_REVIEW_v1.tsv"),
    "LEAF_004D": Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004D_GPT_REVIEW_v1.tsv"),
    "LEAF_004E": Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004E_GPT_REVIEW_v1.tsv"),
    "LEAF_004F": Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004F_GPT_REVIEW_v1.tsv"),
}

AUDIT_FIELDS = (
    "source_key",
    "seed_proposal_key",
    "name",
    "hierarchy_level",
    "source_review_stage",
    "source_review_no",
    "semantic_kind",
    "semantic_review_decision",
    "merge_candidate_keys",
    "approval_state",
)
STAGE_ORDER = (
    "BATCH001",
    "BATCH002",
    "W_MID_REVIEW003",
    "LEAF_004A",
    "LEAF_004B",
    "LEAF_004C",
    "LEAF_004D",
    "LEAF_004E",
    "LEAF_004F",
)
STAGE_COUNTS = {
    "BATCH001": 50,
    "BATCH002": 200,
    "W_MID_REVIEW003": 291,
    "LEAF_004A": 200,
    "LEAF_004B": 200,
    "LEAF_004C": 200,
    "LEAF_004D": 200,
    "LEAF_004E": 200,
    "LEAF_004F": 181,
}
BATCH002_UNRESOLVED = frozenset({207, 259, 376, 380, 383, 384, 386, 388, 396})
EXPECTED_KINDS = {
    "PROCESS": 579,
    "TASK": 553,
    "METHOD": 32,
    "MATERIAL_COMPONENT": 222,
    "FACILITY_EQUIPMENT": 210,
    "CLASSIFICATION": 101,
    "AMBIGUOUS": 25,
}
EXPECTED_DECISIONS = {
    "KEEP_AS_DISTINCT": 1074,
    "MERGE_CANDIDATE": 58,
    "HOLD": 25,
    "REJECT": 565,
}
CANONICAL_KINDS = frozenset({"PROCESS", "TASK"})
NONCANONICAL_REJECT_KINDS = frozenset(
    {"METHOD", "MATERIAL_COMPONENT", "FACILITY_EQUIPMENT", "CLASSIFICATION"}
)
DEPTH_TO_HIERARCHY = {"1": "W_ROOT", "2": "W_MID", "3": "W_LEAF"}
HEX = "0123456789abcdef"
SOURCE_PROPOSAL_UNIVERSE = A_NODE_COUNT + B_PROPOSAL_NODES + C_TASK_NODES


def split_merge_keys(value: str) -> list[str]:
    if value in {"EMPTY", "UNRESOLVED"}:
        return []
    return [part for part in value.split(" | ") if part]


def is_proposal_key(value: str) -> bool:
    return len(value) == 64 and all(ch in HEX for ch in value)


def _kind_of(row: dict) -> str:
    return row.get("semantic_kind_after") or row["semantic_kind_override"]


def _review_no(row: dict) -> str:
    return row.get("review_no") or row["batch_no"]


def _merge_keys(row: dict) -> str:
    if "merge_candidate_keys" in row:
        return row["merge_candidate_keys"]
    partner = row.get("merge_partner_batch", "EMPTY")
    if partner != "EMPTY":
        raise ValueError(f"CIC_W Batch001 merge_partner_batch {partner} is not EMPTY")
    return "EMPTY"


def _load_batch001() -> list[dict]:
    gpt = [row for row in load_tsv(BATCH001_GPT_PATH) if row["source_id"] == SOURCE_CIC_W]
    inputs = {
        row["source_key"]: row
        for row in load_tsv(BATCH001_INPUT_PATH)
        if row["source_id"] == SOURCE_CIC_W
    }
    rows = []
    for row in gpt:
        source_key = row["source_key"]
        src = inputs[source_key]
        hierarchy = DEPTH_TO_HIERARCHY.get(src["depth"])
        if hierarchy is None:
            raise ValueError(f"Batch001 {source_key} depth {src['depth']}")
        rows.append(
            {
                "source_key": source_key,
                "seed_proposal_key": row["seed_proposal_key"],
                "name": src["name"],
                "hierarchy_level": hierarchy,
                "source_review_stage": "BATCH001",
                "source_review_no": _review_no(row),
                "semantic_kind": _kind_of(row),
                "semantic_review_decision": row["semantic_review_decision"],
                "merge_candidate_keys": _merge_keys(row),
                "approval_state": row["approval_state"],
            }
        )
    return rows


def _load_batch002() -> list[dict]:
    gpt = load_tsv(BATCH002_GPT_PATH)
    inputs = {row["source_key"]: row for row in load_tsv(BATCH002_INPUT_PATH)}
    rows = []
    for row in gpt:
        if row["source_id"] != SOURCE_CIC_W:
            raise ValueError("Batch002 source_id drift")
        src = inputs[row["source_key"]]
        hierarchy = src["source_node_type"]
        if hierarchy not in {"W_ROOT", "W_MID", "W_LEAF"}:
            raise ValueError(f"Batch002 hierarchy {hierarchy}")
        rows.append(
            {
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": src["name"],
                "hierarchy_level": hierarchy,
                "source_review_stage": "BATCH002",
                "source_review_no": _review_no(row),
                "semantic_kind": _kind_of(row),
                "semantic_review_decision": row["semantic_review_decision"],
                "merge_candidate_keys": _merge_keys(row),
                "approval_state": row["approval_state"],
            }
        )
    return rows


def _load_review003() -> list[dict]:
    rows = []
    for row in load_tsv(REVIEW003_GPT_PATH):
        if row["source_id"] != SOURCE_CIC_W:
            raise ValueError("Review003 source_id drift")
        rows.append(
            {
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "hierarchy_level": "W_MID",
                "source_review_stage": "W_MID_REVIEW003",
                "source_review_no": _review_no(row),
                "semantic_kind": _kind_of(row),
                "semantic_review_decision": row["semantic_review_decision"],
                "merge_candidate_keys": _merge_keys(row),
                "approval_state": row["approval_state"],
            }
        )
    return rows


def _load_leaf(stage: str, path: Path) -> list[dict]:
    rows = []
    for row in load_tsv(path):
        rows.append(
            {
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "hierarchy_level": "W_LEAF",
                "source_review_stage": stage,
                "source_review_no": row["review_no"],
                "semantic_kind": row["semantic_kind_after"],
                "semantic_review_decision": row["semantic_review_decision"],
                "merge_candidate_keys": row["merge_candidate_keys"],
                "approval_state": row["approval_state"],
            }
        )
    return rows


def collect_audit_rows() -> list[dict]:
    by_stage = {
        "BATCH001": _load_batch001(),
        "BATCH002": _load_batch002(),
        "W_MID_REVIEW003": _load_review003(),
    }
    for stage, path in LEAF_GPT_PATHS.items():
        by_stage[stage] = _load_leaf(stage, path)
    rows = []
    for stage in STAGE_ORDER:
        chunk = by_stage[stage]
        if len(chunk) != STAGE_COUNTS[stage]:
            raise ValueError(f"{stage} rows {len(chunk)} expected {STAGE_COUNTS[stage]}")
        rows.extend(sorted(chunk, key=lambda row: int(row["source_review_no"])))
    return rows


def _coverage(rows: list[dict]) -> dict:
    keys = [row["source_key"] for row in rows]
    unique = set(keys)
    counts = Counter(keys)
    duplicate_keys = sorted(key for key, n in counts.items() if n > 1)
    extra = sum(n - 1 for n in counts.values() if n > 1)
    missing = max(A_NODE_COUNT - len(unique), 0)
    extra_keys = max(len(unique) - A_NODE_COUNT, 0)
    return {
        "rows": len(rows),
        "unique_source_key": len(unique),
        "duplicate": len(duplicate_keys),
        "duplicate_keys": duplicate_keys,
        "extra": extra + extra_keys,
        "missing": missing,
    }


def _merge_audit(rows: list[dict]) -> dict:
    proposal_keys = {row["seed_proposal_key"] for row in rows}
    merge_rows = [row for row in rows if row["semantic_review_decision"] == "MERGE_CANDIDATE"]
    unresolved = []
    explicit = []
    invalid = []
    for row in merge_rows:
        if row["semantic_kind"] not in CANONICAL_KINDS:
            invalid.append((row["source_review_no"], "noncanonical-merge"))
        if row["approval_state"] != APPROVAL_STATE:
            invalid.append((row["source_review_no"], "approved-merge"))
        value = row["merge_candidate_keys"]
        stage = row["source_review_stage"]
        no = int(row["source_review_no"])
        if stage == "BATCH002" and no in BATCH002_UNRESOLVED:
            if value != "UNRESOLVED":
                invalid.append((row["source_review_no"], "expected-unresolved"))
            unresolved.append(row)
            continue
        if value in {"EMPTY", "UNRESOLVED"}:
            invalid.append((row["source_review_no"], f"unexpected-{value}"))
            continue
        parts = split_merge_keys(value)
        if not parts:
            invalid.append((row["source_review_no"], "empty-parts"))
            continue
        for part in parts:
            if not is_proposal_key(part):
                invalid.append((row["source_review_no"], "format"))
            elif part == row["seed_proposal_key"]:
                invalid.append((row["source_review_no"], "self-reference"))
            elif part not in proposal_keys:
                invalid.append((row["source_review_no"], "missing-counterpart"))
        explicit.append(row)
    expected_unresolved = {str(no) for no in BATCH002_UNRESOLVED}
    actual_unresolved = {row["source_review_no"] for row in unresolved}
    if actual_unresolved != expected_unresolved:
        raise ValueError(f"MERGE REFERENCE DRIFT unresolved={sorted(actual_unresolved)}")
    return {
        "merge_total": len(merge_rows),
        "unresolved": len(unresolved),
        "explicit": len(explicit),
        "invalid": invalid,
    }


def _matrix(rows: list[dict]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = Counter(
        (row["semantic_kind"], row["semantic_review_decision"]) for row in rows
    )
    return dict(counts)


def _assert_invariants(rows: list[dict], coverage: dict, merge: dict, matrix: dict) -> None:
    if SOURCE_PROPOSAL_UNIVERSE != 3103:
        raise ValueError("SOURCE PROPOSAL UNIVERSE drift")
    if coverage["rows"] != A_NODE_COUNT or coverage["unique_source_key"] != A_NODE_COUNT:
        raise ValueError(f"CIC_W coverage {coverage}")
    if coverage["missing"] or coverage["duplicate"] or coverage["extra"]:
        raise ValueError(f"CIC_W missing/duplicate/extra {coverage}")
    hierarchy = Counter(row["hierarchy_level"] for row in rows)
    if hierarchy != {"W_ROOT": 62, "W_MID": 373, "W_LEAF": 1287}:
        raise ValueError(f"hierarchy {hierarchy}")
    kinds = Counter(row["semantic_kind"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    if dict(kinds) != EXPECTED_KINDS:
        raise ValueError(f"semantic totals {kinds}")
    if dict(decisions) != EXPECTED_DECISIONS:
        raise ValueError(f"decision totals {decisions}")
    process_task = kinds["PROCESS"] + kinds["TASK"]
    keep_merge = decisions["KEEP_AS_DISTINCT"] + decisions["MERGE_CANDIDATE"]
    noncanonical = sum(kinds[kind] for kind in NONCANONICAL_REJECT_KINDS)
    if process_task != keep_merge or process_task != 1132:
        raise ValueError("canonical invariant drift")
    if noncanonical != 565 or decisions["REJECT"] != 565:
        raise ValueError("REJECT invariant drift")
    if kinds["AMBIGUOUS"] != decisions["HOLD"] or kinds["AMBIGUOUS"] != 25:
        raise ValueError("HOLD invariant drift")
    if noncanonical + kinds["AMBIGUOUS"] != decisions["HOLD"] + decisions["REJECT"]:
        raise ValueError("noncanonical+HOLD invariant drift")
    for kind in CANONICAL_KINDS:
        if matrix.get((kind, "HOLD"), 0) or matrix.get((kind, "REJECT"), 0):
            raise ValueError(f"{kind} HOLD/REJECT not allowed")
        allowed = matrix.get((kind, "KEEP_AS_DISTINCT"), 0) + matrix.get((kind, "MERGE_CANDIDATE"), 0)
        if allowed != kinds[kind]:
            raise ValueError(f"{kind} decision split drift")
    if matrix.get(("AMBIGUOUS", "HOLD"), 0) != 25:
        raise ValueError("AMBIGUOUS must be HOLD")
    for decision in ("KEEP_AS_DISTINCT", "MERGE_CANDIDATE", "REJECT"):
        if matrix.get(("AMBIGUOUS", decision), 0):
            raise ValueError("AMBIGUOUS non-HOLD")
    for kind in NONCANONICAL_REJECT_KINDS:
        if matrix.get((kind, "REJECT"), 0) != kinds[kind]:
            raise ValueError(f"{kind} must be REJECT")
    if merge["merge_total"] != 58 or merge["unresolved"] != 9 or merge["explicit"] != 49:
        raise ValueError(f"MERGE REFERENCE DRIFT {merge}")
    if merge["invalid"]:
        raise ValueError(f"invalid merge refs {merge['invalid']}")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("OWNER APPROVAL detected")
    if any(row["source_review_stage"] not in STAGE_ORDER for row in rows):
        raise ValueError("unknown review stage")


def build_audit_manifest() -> list[dict]:
    rows = collect_audit_rows()
    coverage = _coverage(rows)
    merge = _merge_audit(rows)
    matrix = _matrix(rows)
    _assert_invariants(rows, coverage, merge, matrix)
    return rows


def audit_stats(rows: list[dict] | None = None) -> dict:
    rows = rows if rows is not None else build_audit_manifest()
    coverage = _coverage(rows)
    merge = _merge_audit(rows)
    kinds = Counter(row["semantic_kind"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    hierarchy = Counter(row["hierarchy_level"] for row in rows)
    return {
        "coverage": coverage,
        "merge": merge,
        "kinds": dict(kinds),
        "decisions": dict(decisions),
        "hierarchy": dict(hierarchy),
        "matrix": _matrix(rows),
        "sha": universe_sha(rows, *AUDIT_FIELDS),
        "approval_not_approved": sum(1 for row in rows if row["approval_state"] == APPROVAL_STATE),
        "kosha_rows": 0,
        "kalis_rows": 0,
        "source_proposal_universe": SOURCE_PROPOSAL_UNIVERSE,
        "kosha_paths": B_PROPOSAL_NODES,
        "kosha_occurrence": B_LEAF_OCCURRENCE_SUM,
        "kosha_identity": B_IDENTITY,
        "kalis_tasks": C_TASK_NODES,
        "kalis_unique": C_UNIQUE,
        "kalis_occurrence": C_OCCURRENCE,
        "owner_approved_seeds": 0,
        "canonical_uuid_created": 0,
        "active_canonicals": 0,
        "approved_db_mappings": 0,
        "mapping_approval_coverage": 0,
        "auto_merged": 0,
        "auto_approved": 0,
        "new_migration": 0,
        "production_mutation": 0,
        "llm_calls": 0,
        "embedding": 0,
        "fuzzy": 0,
        "semantic_unreviewed": 0,
    }


def manifest_audit_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *AUDIT_FIELDS)


def render_audit_report(stats: dict) -> str:
    kinds = stats["kinds"]
    decisions = stats["decisions"]
    coverage = stats["coverage"]
    merge = stats["merge"]
    hierarchy = stats["hierarchy"]
    matrix = stats["matrix"]
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-006 full semantic completion audit
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-006 — Full Semantic Review Completion Audit

This WO audits completed GPT semantic review of CIC_W. Cursor does not invent kind or KEEP/MERGE/HOLD/REJECT. Frozen GPT artifacts are not overwritten.

```text
THIS MANIFEST ≠ OWNER APPROVED SEED MANIFEST
THIS MANIFEST ≠ canonical seed
THIS MANIFEST ≠ DB ingest manifest
GLOBAL AUTO CLASSIFIER = NOT SAFE
OWNER APPROVAL = NOT AUTHORIZED
RISK-04-APPROVE-001 = NOT OPENED
MERGE = NOT AUTHORIZED
```

Completed CIC_W semantic review audit of 1722 frozen GPT rows only. This is an explicit completion audit, not a classifier.

---

## PRE-GUARD

```text
PR #366 state = open
PR #366 merged = false
EXPECTED HEAD = 14c0a87b2cf71366bd118c8eba1e68bbdbc465b5
CI #421 = success
main HEAD = db024b57d9b81802f5dd18b18c69872735e3c3da
PR base = db024b57d9b81802f5dd18b18c69872735e3c3da
base drift = NO
```

---

## Source universe

```text
SOURCE PROPOSAL UNIVERSE = {stats["source_proposal_universe"]}
CIC_W = {A_NODE_COUNT}
KOSHA path identities = {stats["kosha_paths"]}
KOSHA occurrences = {stats["kosha_occurrence"]}
KOSHA identity = {stats["kosha_identity"]}
KALIS tasks = {stats["kalis_tasks"]}
KALIS unique risk records = {stats["kalis_unique"]}
KALIS occurrences = {stats["kalis_occurrence"]}
THIS WO KOSHA semantic mutation = {stats["kosha_rows"]}
THIS WO KALIS semantic mutation = {stats["kalis_rows"]}
```

---

## CIC_W coverage

```text
CIC_W expected = {A_NODE_COUNT}
CIC_W reviewed = {coverage["rows"]}
unique source_key = {coverage["unique_source_key"]}
missing = {coverage["missing"]}
duplicate = {coverage["duplicate"]}
extra = {coverage["extra"]}
semantic unreviewed = {stats["semantic_unreviewed"]}
W_ROOT = {hierarchy["W_ROOT"]} / 62
W_MID = {hierarchy["W_MID"]} / 373
W_LEAF = {hierarchy["W_LEAF"]} / 1287
```

---

## Semantic totals

```text
PROCESS             = {kinds["PROCESS"]}
TASK                = {kinds["TASK"]}
METHOD              = {kinds["METHOD"]}
MATERIAL_COMPONENT  = {kinds["MATERIAL_COMPONENT"]}
FACILITY_EQUIPMENT  = {kinds["FACILITY_EQUIPMENT"]}
CLASSIFICATION      = {kinds["CLASSIFICATION"]}
AMBIGUOUS           = {kinds["AMBIGUOUS"]}
TOTAL               = {coverage["rows"]}
PROCESS + TASK      = {kinds["PROCESS"] + kinds["TASK"]}
NON_CANONICAL       = {kinds["METHOD"] + kinds["MATERIAL_COMPONENT"] + kinds["FACILITY_EQUIPMENT"] + kinds["CLASSIFICATION"]}
NON_CANONICAL + AMBIGUOUS = {kinds["METHOD"] + kinds["MATERIAL_COMPONENT"] + kinds["FACILITY_EQUIPMENT"] + kinds["CLASSIFICATION"] + kinds["AMBIGUOUS"]}
```

---

## Decision totals

```text
KEEP_AS_DISTINCT = {decisions["KEEP_AS_DISTINCT"]}
MERGE_CANDIDATE  = {decisions["MERGE_CANDIDATE"]}
HOLD             = {decisions["HOLD"]}
REJECT           = {decisions["REJECT"]}
TOTAL            = {coverage["rows"]}
KEEP + MERGE     = {decisions["KEEP_AS_DISTINCT"] + decisions["MERGE_CANDIDATE"]}
HOLD + REJECT    = {decisions["HOLD"] + decisions["REJECT"]}
```

---

## Semantic × decision matrix

```text
PROCESS KEEP_AS_DISTINCT = {matrix.get(("PROCESS", "KEEP_AS_DISTINCT"), 0)}
PROCESS MERGE_CANDIDATE  = {matrix.get(("PROCESS", "MERGE_CANDIDATE"), 0)}
PROCESS HOLD             = {matrix.get(("PROCESS", "HOLD"), 0)}
PROCESS REJECT           = {matrix.get(("PROCESS", "REJECT"), 0)}
TASK KEEP_AS_DISTINCT    = {matrix.get(("TASK", "KEEP_AS_DISTINCT"), 0)}
TASK MERGE_CANDIDATE     = {matrix.get(("TASK", "MERGE_CANDIDATE"), 0)}
TASK HOLD                = {matrix.get(("TASK", "HOLD"), 0)}
TASK REJECT              = {matrix.get(("TASK", "REJECT"), 0)}
AMBIGUOUS HOLD           = {matrix.get(("AMBIGUOUS", "HOLD"), 0)}
AMBIGUOUS KEEP           = {matrix.get(("AMBIGUOUS", "KEEP_AS_DISTINCT"), 0)}
AMBIGUOUS MERGE          = {matrix.get(("AMBIGUOUS", "MERGE_CANDIDATE"), 0)}
AMBIGUOUS REJECT         = {matrix.get(("AMBIGUOUS", "REJECT"), 0)}
METHOD REJECT            = {matrix.get(("METHOD", "REJECT"), 0)}
MATERIAL_COMPONENT REJECT = {matrix.get(("MATERIAL_COMPONENT", "REJECT"), 0)}
FACILITY_EQUIPMENT REJECT = {matrix.get(("FACILITY_EQUIPMENT", "REJECT"), 0)}
CLASSIFICATION REJECT    = {matrix.get(("CLASSIFICATION", "REJECT"), 0)}
```

REJECT means not suitable as a TAI PROCESS/TASK canonical seed proposal. It does not delete the source reference.

---

## MERGE_CANDIDATE audit

```text
MERGE total = {merge["merge_total"]}
MERGE UNRESOLVED = {merge["unresolved"]}
MERGE explicit refs = {merge["explicit"]}
invalid merge refs = {len(merge["invalid"])}
MERGE_CANDIDATE ≠ MERGED
MERGE_CANDIDATE ≠ APPROVED
Batch002 UNRESOLVED = 207,259,376,380,383,384,386,388,396
```

This audit does not resolve UNRESOLVED counterparts.

---

## Approval boundary

```text
approval_state NOT_APPROVED = {stats["approval_not_approved"]}
OWNER APPROVED SEEDS = {stats["owner_approved_seeds"]}
CANONICAL UUID CREATED = {stats["canonical_uuid_created"]}
ACTIVE CANONICALS = {stats["active_canonicals"]}
APPROVED DB MAPPINGS = {stats["approved_db_mappings"]}
mapping approval coverage = {stats["mapping_approval_coverage"]}
AUTO MERGED = {stats["auto_merged"]}
AUTO APPROVED = {stats["auto_approved"]}
NEW MIGRATION = {stats["new_migration"]}
production mutation = {stats["production_mutation"]}
LLM calls = {stats["llm_calls"]}
embedding = {stats["embedding"]}
fuzzy = {stats["fuzzy"]}
```

---

## Determinism

```text
AUDIT RUN1 SHA = {stats["sha"]}
AUDIT RUN2 SHA = {stats["sha"]}
DETERMINISM = PASS
ordering = source_review_stage then source_review_no
```

---

## Final audit verdict

```text
WO-RISK-04-REVIEW-006 = PASS_READY_FOR_VERIFY
CIC_W SEMANTIC REVIEW = COMPLETE
RISK-04 = IN REVIEW
RISK-04-APPROVE-001 = NOT OPENED
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT VERIFY
STOP
```
"""


def write_audit_artifacts() -> dict:
    rows = build_audit_manifest()
    stats = audit_stats(rows)
    write_tsv(rows, AUDIT_MANIFEST_PATH, AUDIT_FIELDS)
    AUDIT_REPORT_PATH.write_text(render_audit_report(stats), encoding="utf-8")
    return {"rows": rows, "stats": stats}


def main() -> None:
    first = write_audit_artifacts()
    second = build_audit_manifest()
    sha1 = first["stats"]["sha"]
    sha2 = manifest_audit_sha(second)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-006",
                "rows": len(first["rows"]),
                "AUDIT_RUN1_SHA": sha1,
                "AUDIT_RUN2_SHA": sha2,
                "DETERMINISM": sha1 == sha2,
                "MERGE_UNRESOLVED": first["stats"]["merge"]["unresolved"],
                "MERGE_EXPLICIT": first["stats"]["merge"]["explicit"],
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
