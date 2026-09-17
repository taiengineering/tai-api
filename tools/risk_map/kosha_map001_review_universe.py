"""WO-RISK-KOSHA-MAP-001A KOSHA source → canonical mapping review universe.

Evidence-only. Zero production write surface. No LLM. No fuzzy. No embedding.
No auto EXACT_EQUIVALENT / APPROVED / NO_MATCH decisions. This tool builds:

  * RISK_KOSHA_MAP001_REVIEW_UNIVERSE_v1.tsv   — 620 DETAIL_PROCESS review rows
  * RISK_KOSHA_MAP001_GPT_REVIEW_PACK_v1.tsv   — same 620 rows batched for GPT review
  * RISK_KOSHA_MAP001_COVERAGE_v1.tsv          — accounting manifest
  * OBJ_risk-kosha-map001-review-universe_v1.md — verdict report

Inputs are only frozen repository evidence:
  * tools.risk02.plan_source_core.build_plan()   — deterministic KOSHA node plan
  * RISK04_CANONICAL_MATERIALIZATION_RECEIPT_v1.tsv (canonical TASK anchor)

Exact-name lookup uses `name_normalized` equality only. It never marks a hit
as EXACT_EQUIVALENT / APPROVED — those decisions belong to a later GPT +
Owner Approval WO.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from tools.risk02.contract import SOURCE_KOSHA
from tools.risk02.plan_source_core import build_plan
from tools.risk04.identity import sha256_parts
from tools.risk04.materialize001_resume_effective_plan import (
    FROZEN_RECEIPT_SHA as FROZEN_CANONICAL_RECEIPT_SHA,
    RECEIPT_PATH as CANONICAL_RECEIPT_PATH,
    receipt_sha as canonical_receipt_sha,
)
from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha
from tools.risk02.ingest001_source_core import (
    RECEIPT_PATH as SOURCE_INGEST_RECEIPT_PATH,
    receipt_sha as source_ingest_receipt_sha,
)

WO_ID = "WO-RISK-KOSHA-MAP-001A"

REVIEW_UNIVERSE_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_MAP001_REVIEW_UNIVERSE_v1.tsv"
)
GPT_REVIEW_PACK_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_MAP001_GPT_REVIEW_PACK_v1.tsv"
)
COVERAGE_PATH = Path("docs/knowledge/risk/RISK_KOSHA_MAP001_COVERAGE_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk-kosha-map001-review-universe_v1.md")

# Frozen expected census (WO §7 / §11).
EXPECTED_KOSHA_TOTAL = 787
EXPECTED_PROJECT_KIND = 6
EXPECTED_WORK_TYPE = 161
EXPECTED_DETAIL_PROCESS = 620
EXPECTED_RAW_LEAF_OCCURRENCE_SUM = 626
EXPECTED_PATH_IDENTITIES = 620
EXPECTED_DUPLICATE_GROUPS = 3
EXPECTED_DUPLICATE_EXTRAS = 6
EXPECTED_EXACT_NAME_HITS = 12
EXPECTED_NO_EXACT_NAME = 608
EXPECTED_MULTI_TARGET_AMBIGUITY = 0

BATCH_SIZE = 100  # WO §27

REVIEW_UNIVERSE_FIELDS: tuple[str, ...] = (
    "review_key",
    "source_id",
    "source_key",
    "project_kind",
    "work_type",
    "detail_process",
    "source_name",
    "source_name_normalized",
    "source_path",
    "source_path_normalized",
    "source_identity_status",
    "source_occurrence_count",
    "duplicate_occurrence_flag",
    "canonical_kind_required",
    "exact_name_hit_count",
    "exact_name_canonical_id",
    "exact_name_canonical_name",
    "exact_name_canonical_parent",
    "exact_name_canonical_origin_type",
    "candidate_class",
    "recommended_mapping_type",
    "mapping_method_hint",
    "review_status",
    "semantic_decision",
    "semantic_target_canonical_id",
    "semantic_mapping_type",
    "semantic_reason",
)

GPT_REVIEW_PACK_FIELDS: tuple[str, ...] = ("batch_no",) + REVIEW_UNIVERSE_FIELDS

COVERAGE_FIELDS: tuple[str, ...] = ("bucket", "count", "note")


def _review_key(source_key: str) -> str:
    return sha256_parts(SOURCE_KOSHA, source_key, "KOSHA_MAP001_REVIEW")


def _load_canonical_tasks() -> tuple[
    list[dict],
    dict[str, list[dict]],
    dict[str, dict],
]:
    """Return (task rows, by_normalized_name -> [rows], by_canonical_id -> row)."""
    receipt_rows = load_tsv(CANONICAL_RECEIPT_PATH)
    if len(receipt_rows) != 1110:
        raise SystemExit(f"CANONICAL_RECEIPT_ROWS {len(receipt_rows)}")
    if canonical_receipt_sha(receipt_rows) != FROZEN_CANONICAL_RECEIPT_SHA:
        raise SystemExit("CANONICAL_RECEIPT_SHA_DRIFT")

    tasks = [r for r in receipt_rows if r["node_kind"] == "TASK"]
    by_name: dict[str, list[dict]] = defaultdict(list)
    for r in tasks:
        by_name[r["name_normalized"]].append(r)
    by_id = {r["canonical_id"]: r for r in tasks}
    # Include PROCESS rows in by_id too, so parent_canonical_id lookups resolve
    # even when the parent is a PROCESS above a TASK.
    for r in receipt_rows:
        by_id.setdefault(r["canonical_id"], r)
    return tasks, dict(by_name), by_id


def _kosha_plan_nodes() -> tuple[list[dict], list[dict], list[dict], dict[str, int]]:
    """Return (project_kind_nodes, work_type_nodes, detail_process_nodes, leaf_occurrence)."""
    plan = build_plan()
    b_nodes = plan["_plan"]["b_nodes"]
    if not b_nodes:
        raise SystemExit("KOSHA_PLAN_EMPTY")
    if plan["B"]["identity"] != "HOLD":
        raise SystemExit(f"KOSHA_IDENTITY_STATUS_DRIFT {plan['B']['identity']}")

    project = [n for n in b_nodes if n["node_type"] == "PROJECT_KIND"]
    work = [n for n in b_nodes if n["node_type"] == "WORK_TYPE"]
    detail = [n for n in b_nodes if n["node_type"] == "DETAIL_PROCESS"]

    if len(project) != EXPECTED_PROJECT_KIND:
        raise SystemExit(f"PROJECT_KIND_COUNT_DRIFT {len(project)}")
    if len(work) != EXPECTED_WORK_TYPE:
        raise SystemExit(f"WORK_TYPE_COUNT_DRIFT {len(work)}")
    if len(detail) != EXPECTED_DETAIL_PROCESS:
        raise SystemExit(f"DETAIL_PROCESS_COUNT_DRIFT {len(detail)}")

    leaf_occ: dict[str, int] = {}
    for m in plan["_plan"]["membership"]:
        if (
            m["source_id"] == SOURCE_KOSHA
            and m["member_kind"] == "NODE"
        ):
            # Only DETAIL_PROCESS carries a real occurrence count > 1;
            # PROJECT_KIND / WORK_TYPE contribute 1 each.
            leaf_occ[m["member_key"]] = m["occurrence_count"]

    return project, work, detail, leaf_occ


def build_review_universe() -> tuple[list[dict], list[dict]]:
    """Return (universe_rows, unresolved_exact_name_conflicts)."""
    project, work, detail, leaf_occ = _kosha_plan_nodes()
    project_by_key = {n["source_key"]: n for n in project}
    work_by_key = {n["source_key"]: n for n in work}

    _, canonical_by_name, canonical_by_id = _load_canonical_tasks()

    total_leaf_occurrence = sum(
        leaf_occ.get(n["source_key"], 0) for n in detail
    )
    if total_leaf_occurrence != EXPECTED_RAW_LEAF_OCCURRENCE_SUM:
        raise SystemExit(
            f"LEAF_OCCURRENCE_SUM_DRIFT {total_leaf_occurrence}"
        )

    dup_groups = sum(1 for n in detail if leaf_occ.get(n["source_key"], 0) > 1)
    if dup_groups != EXPECTED_DUPLICATE_GROUPS:
        raise SystemExit(f"DUPLICATE_GROUPS_DRIFT {dup_groups}")
    dup_extras = sum(
        max(leaf_occ.get(n["source_key"], 0) - 1, 0) for n in detail
    )
    if dup_extras != EXPECTED_DUPLICATE_EXTRAS:
        raise SystemExit(f"DUPLICATE_EXTRAS_DRIFT {dup_extras}")

    rows: list[dict] = []
    exact_hits = 0
    no_hits = 0
    ambig = 0

    for node in detail:
        work_parent = work_by_key.get(node["parent_source_key"])
        project_parent = (
            project_by_key.get(work_parent["parent_source_key"])
            if work_parent
            else None
        )
        occurrence = leaf_occ.get(node["source_key"], 0)
        if occurrence < 1:
            raise SystemExit(f"OCCURRENCE_ZERO {node['source_key']}")

        candidates = canonical_by_name.get(node["name_normalized"], [])
        if len(candidates) == 0:
            no_hits += 1
            exact_hit_count = 0
            canonical = None
        elif len(candidates) == 1:
            exact_hits += 1
            exact_hit_count = 1
            canonical = candidates[0]
        else:
            ambig += 1
            exact_hit_count = len(candidates)
            canonical = None  # sanitized: do not pick a target from a tie

        if canonical is not None:
            parent = canonical_by_id.get(canonical["parent_canonical_id"])
            parent_name = parent["name"] if parent else ""
            candidate_class = "EXACT_NAME_CANDIDATE"
            recommended_mapping_type = "POSSIBLE_RELATED"
            mapping_method_hint = "EXACT_NAME"
            can_id = canonical["canonical_id"]
            can_name = canonical["name"]
            can_origin = canonical["origin_type"]
        else:
            parent_name = ""
            candidate_class = "SEMANTIC_SEARCH_REQUIRED"
            recommended_mapping_type = ""
            mapping_method_hint = ""
            can_id = ""
            can_name = ""
            can_origin = ""

        rows.append(
            {
                "review_key": _review_key(node["source_key"]),
                "source_id": SOURCE_KOSHA,
                "source_key": node["source_key"],
                "project_kind": project_parent["name_raw"] if project_parent else "",
                "work_type": work_parent["name_raw"] if work_parent else "",
                "detail_process": node["name_raw"],
                "source_name": node["name_raw"],
                "source_name_normalized": node["name_normalized"],
                "source_path": node["path_raw"],
                "source_path_normalized": node["path_normalized"],
                "source_identity_status": "HOLD",
                "source_occurrence_count": str(occurrence),
                "duplicate_occurrence_flag": "YES" if occurrence > 1 else "NO",
                "canonical_kind_required": "TASK",
                "exact_name_hit_count": str(exact_hit_count),
                "exact_name_canonical_id": can_id,
                "exact_name_canonical_name": can_name,
                "exact_name_canonical_parent": parent_name,
                "exact_name_canonical_origin_type": can_origin,
                "candidate_class": candidate_class,
                "recommended_mapping_type": recommended_mapping_type,
                "mapping_method_hint": mapping_method_hint,
                "review_status": "REVIEW_REQUIRED",
                "semantic_decision": "",
                "semantic_target_canonical_id": "",
                "semantic_mapping_type": "",
                "semantic_reason": "",
            }
        )

    if len(rows) != EXPECTED_DETAIL_PROCESS:
        raise SystemExit(f"ROW_COUNT_DRIFT {len(rows)}")
    unique = {r["source_key"] for r in rows}
    if len(unique) != EXPECTED_DETAIL_PROCESS:
        raise SystemExit(f"UNIQUE_SOURCE_KEY_DRIFT {len(unique)}")
    if exact_hits != EXPECTED_EXACT_NAME_HITS:
        raise SystemExit(f"EXACT_HIT_COUNT_DRIFT {exact_hits}")
    if no_hits != EXPECTED_NO_EXACT_NAME:
        raise SystemExit(f"NO_EXACT_HIT_COUNT_DRIFT {no_hits}")
    if ambig != EXPECTED_MULTI_TARGET_AMBIGUITY:
        raise SystemExit(f"AMBIGUITY_COUNT_DRIFT {ambig}")

    rows.sort(
        key=lambda r: (
            0 if int(r["exact_name_hit_count"]) > 0 else 1,
            r["project_kind"],
            r["work_type"],
            r["source_name_normalized"],
            r["source_key"],
        )
    )
    return rows, []


def _batchify(rows: list[dict]) -> list[dict]:
    packed: list[dict] = []
    for idx, row in enumerate(rows):
        batch_no = (idx // BATCH_SIZE) + 1
        packed.append({"batch_no": f"B{batch_no:02d}", **row})
    return packed


def build_coverage(rows: list[dict]) -> list[dict]:
    exact_hit_families = Counter(
        r["exact_name_canonical_name"]
        for r in rows
        if r["exact_name_canonical_name"]
    )
    exact_hit_count = sum(1 for r in rows if r["candidate_class"] == "EXACT_NAME_CANDIDATE")
    no_hit_count = sum(1 for r in rows if r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED")
    dup_flag_count = sum(1 for r in rows if r["duplicate_occurrence_flag"] == "YES")
    occurrence_sum = sum(int(r["source_occurrence_count"]) for r in rows)
    return [
        {"bucket": "KOSHA_TOTAL_NODES", "count": str(EXPECTED_KOSHA_TOTAL), "note": "PROJECT_KIND + WORK_TYPE + DETAIL_PROCESS"},
        {"bucket": "PROJECT_KIND_CONTEXT_ONLY", "count": str(EXPECTED_PROJECT_KIND), "note": "not a mapping target"},
        {"bucket": "WORK_TYPE_CONTEXT_ONLY", "count": str(EXPECTED_WORK_TYPE), "note": "not a mapping target"},
        {"bucket": "DETAIL_PROCESS_REVIEW_UNIVERSE", "count": str(EXPECTED_DETAIL_PROCESS), "note": "620 review rows in this WO"},
        {"bucket": "RAW_LEAF_OCCURRENCES", "count": str(occurrence_sum), "note": "must equal 626 (KOSHA raw source rows)"},
        {"bucket": "PATH_IDENTITIES", "count": str(EXPECTED_PATH_IDENTITIES), "note": "unique DETAIL_PROCESS identities preserved"},
        {"bucket": "IDENTITY_STATUS", "count": "HOLD", "note": "frozen from RISK-02; not lifted by this WO"},
        {"bucket": "DUPLICATE_OCCURRENCE_GROUPS", "count": str(dup_flag_count), "note": "leaf identities with occurrence_count > 1"},
        {"bucket": "DUPLICATE_RAW_EXTRAS", "count": str(EXPECTED_DUPLICATE_EXTRAS), "note": "extra raw rows collapsed onto duplicate identities"},
        {"bucket": "EXACT_NAME_SOURCE_HITS", "count": str(exact_hit_count), "note": "unique canonical TASK by name_normalized"},
        {"bucket": "NO_EXACT_NAME_ROWS", "count": str(no_hit_count), "note": "SEMANTIC_SEARCH_REQUIRED — NOT NO_MATCH"},
        {"bucket": "MULTI_TARGET_EXACT_NAME_AMBIGUITY", "count": str(EXPECTED_MULTI_TARGET_AMBIGUITY), "note": "0 by frozen production canonical anchor"},
        {"bucket": "SEMANTIC_DECISIONS", "count": "0", "note": "deferred to GPT semantic review WO"},
        {"bucket": "APPROVED_DECISIONS", "count": "0", "note": "no owner mapping approval yet"},
        {"bucket": "NO_MATCH_DECISIONS", "count": "0", "note": "cannot be assigned mechanically"},
        {"bucket": "PRODUCTION_KOSHA_MAPPINGS", "count": "0", "note": "no DB write in this WO"},
        {
            "bucket": "EXACT_NAME_FAMILIES",
            "count": ";".join(f"{k}={v}" for k, v in sorted(exact_hit_families.items())),
            "note": "candidate evidence only — same name != EXACT_EQUIVALENT",
        },
    ]


def universe_sha_for_rows(rows: list[dict]) -> str:
    return universe_sha(rows, *REVIEW_UNIVERSE_FIELDS)


def pack_sha_for_rows(rows: list[dict]) -> str:
    return universe_sha(rows, *GPT_REVIEW_PACK_FIELDS)


def render_report(
    universe_rows: list[dict],
    coverage_rows: list[dict],
    universe_sha_value: str,
    pack_sha_value: str,
    source_ingest_sha: str,
) -> str:
    coverage_lines = "\n".join(
        f"{r['bucket']} = {r['count']}  # {r['note']}" for r in coverage_rows
    )
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-MAP-001A KOSHA source mapping review universe
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KOSHA Source Mapping Review Universe

## THIS IS NOT MAPPING APPROVAL

```text
THIS IS NOT MAPPING APPROVAL
THIS IS NOT PRODUCTION MATERIALIZATION
THIS DOES NOT LIFT KOSHA IDENTITY HOLD
THIS DOES NOT CREATE CANONICAL NODES
THIS DOES NOT DECIDE NO_MATCH FOR ANY ROW
```

## Anchors

```text
CANONICAL MATERIALIZATION RECEIPT SHA = {FROZEN_CANONICAL_RECEIPT_SHA}
SOURCE INGEST RECEIPT SHA             = {source_ingest_sha}
```

## Review universe

```text
{coverage_lines}
```

`EXACT_NAME_CANDIDATE` rows carry `recommended_mapping_type = POSSIBLE_RELATED`,
never `EXACT_EQUIVALENT`. `SEMANTIC_SEARCH_REQUIRED` rows carry a blank target
and are **not** `NO_MATCH`. Both classes require GPT semantic review before any
Owner mapping approval WO can be opened.

## Frozen SHAs

```text
RISK KOSHA MAP001 REVIEW UNIVERSE SHA = {universe_sha_value}
RISK KOSHA MAP001 GPT REVIEW PACK SHA = {pack_sha_value}
```

## Verdict

```text
{WO_ID} = REVIEW_UNIVERSE_FROZEN / EVIDENCE_READY
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
CANONICAL = 1110 DRAFT / 0 ACTIVE (unchanged)
MERGE = NOT AUTHORIZED
NEXT = GPT KOSHA SEMANTIC REVIEW BATCH 01
STOP
```
"""


def write_all() -> dict:
    ingest_rows = load_tsv(SOURCE_INGEST_RECEIPT_PATH)
    source_ingest_sha = source_ingest_receipt_sha(ingest_rows)

    universe_a, _ = build_review_universe()
    universe_b, _ = build_review_universe()
    if universe_a != universe_b:
        raise SystemExit("DETERMINISM_ROW_ORDER_DRIFT")

    universe_sha_a = universe_sha_for_rows(universe_a)
    universe_sha_b = universe_sha_for_rows(universe_b)
    if universe_sha_a != universe_sha_b:
        raise SystemExit(f"UNIVERSE_SHA_DRIFT {universe_sha_a} vs {universe_sha_b}")

    pack_rows_a = _batchify(universe_a)
    pack_rows_b = _batchify(universe_b)
    pack_sha_a = pack_sha_for_rows(pack_rows_a)
    pack_sha_b = pack_sha_for_rows(pack_rows_b)
    if pack_sha_a != pack_sha_b or pack_rows_a != pack_rows_b:
        raise SystemExit("PACK_SHA_DRIFT")

    coverage = build_coverage(universe_a)

    write_tsv(universe_a, REVIEW_UNIVERSE_PATH, REVIEW_UNIVERSE_FIELDS)
    write_tsv(pack_rows_a, GPT_REVIEW_PACK_PATH, GPT_REVIEW_PACK_FIELDS)
    write_tsv(coverage, COVERAGE_PATH, COVERAGE_FIELDS)
    REPORT_PATH.write_text(
        render_report(
            universe_a, coverage, universe_sha_a, pack_sha_a, source_ingest_sha
        ),
        encoding="utf-8",
    )

    return {
        "kosha_nodes": EXPECTED_KOSHA_TOTAL,
        "project_kind": EXPECTED_PROJECT_KIND,
        "work_type": EXPECTED_WORK_TYPE,
        "detail_process": EXPECTED_DETAIL_PROCESS,
        "review_universe_rows": len(universe_a),
        "exact_name_hits": sum(
            1 for r in universe_a if r["candidate_class"] == "EXACT_NAME_CANDIDATE"
        ),
        "no_exact_name": sum(
            1 for r in universe_a if r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED"
        ),
        "multi_target_ambiguity": 0,
        "semantic_decisions": sum(1 for r in universe_a if r["semantic_decision"]),
        "review_universe_sha_run1": universe_sha_a,
        "review_universe_sha_run2": universe_sha_b,
        "gpt_pack_sha_run1": pack_sha_a,
        "gpt_pack_sha_run2": pack_sha_b,
        "batches": (len(universe_a) + BATCH_SIZE - 1) // BATCH_SIZE,
        "canonical_receipt_sha": FROZEN_CANONICAL_RECEIPT_SHA,
        "source_ingest_receipt_sha": source_ingest_sha,
        "review_universe_path": str(REVIEW_UNIVERSE_PATH),
        "gpt_review_pack_path": str(GPT_REVIEW_PACK_PATH),
        "coverage_path": str(COVERAGE_PATH),
        "report_path": str(REPORT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} review universe generator")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
