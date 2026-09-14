"""Deterministic source→canonical candidate generator. No language-model or vector similarity."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from tools.risk02.contract import SOURCE_CIC_W, SOURCE_KALIS, SOURCE_KOSHA
from tools.risk02.identity import sha256_parts
from tools.risk02.plan_source_core import build_plan
from tools.risk03.contract import (
    B_IDENTITY,
    B_LEAF_OCCURRENCE_SUM,
    B_PATH_IDENTITIES,
    B_RAW_ROWS,
    C_OCCURRENCE,
    C_UNIQUE,
    PHYSICAL_MODEL_DECISION,
    SOURCE_NODE_KIND_TO_CANONICAL,
)
from tools.risk03.fixtures import synthetic_canonical_nodes
from tools.risk03.identity import canonical_path, is_consumer_eligible, proposal_key

DEFAULT_ROOT = Path("artifacts/risk01")


def _kind(source_node: dict) -> str:
    return SOURCE_NODE_KIND_TO_CANONICAL[source_node["node_type"]]


def _index_canonicals(canonicals: list[dict]) -> tuple[dict[str, dict], dict[tuple[str, str], list[dict]]]:
    by_id = {node["id"]: node for node in canonicals}
    by_name_kind: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for node in canonicals:
        by_name_kind[(node["name_normalized"], node["node_kind"])].append(node)
    return by_id, by_name_kind


def classify_source_node(source_node: dict, canonicals: list[dict]) -> list[dict]:
    by_id, by_name_kind = _index_canonicals(canonicals)
    kind = _kind(source_node)
    name_hits = list(by_name_kind.get((source_node["name_normalized"], kind), ()))
    path_hits = [
        node
        for node in name_hits
        if canonical_path(by_id, node) == source_node["path_normalized"]
    ]
    evidence_base = {
        "source_path": source_node["path_normalized"],
        "source_node_name": source_node["name_normalized"],
        "source_node_kind": source_node["node_type"],
        "canonical_kind": kind,
        "normalization_rule": "NFC whitespace punctuation collapse via risk01.norm_name",
    }
    if len(name_hits) > 1:
        rows = []
        for node in name_hits:
            rows.append(
                _candidate_row(
                    source_node,
                    node,
                    by_id,
                    candidate_class="AMBIGUOUS",
                    mapping_type="AMBIGUOUS",
                    mapping_status="HOLD",
                    mapping_method="EXACT_NAME",
                    reason="same normalized name in multiple canonical contexts",
                    extra=evidence_base,
                )
            )
        return rows
    if path_hits:
        node = path_hits[0]
        return [
            _candidate_row(
                source_node,
                node,
                by_id,
                candidate_class="EXACT_PATH_CANDIDATE",
                mapping_type="POSSIBLE_RELATED",
                mapping_status="PROPOSED",
                mapping_method="EXACT_PATH",
                reason="normalized full path equals canonical path; not auto EXACT_EQUIVALENT",
                extra=evidence_base,
            )
        ]
    if name_hits:
        node = name_hits[0]
        return [
            _candidate_row(
                source_node,
                node,
                by_id,
                candidate_class="EXACT_NAME_CANDIDATE",
                mapping_type="POSSIBLE_RELATED",
                mapping_status="PROPOSED",
                mapping_method="EXACT_NAME",
                reason="normalized leaf name match with different hierarchy context",
                extra=evidence_base,
            )
        ]
    return [
        {
            "proposal_key": proposal_key(
                source_node["source_id"], source_node["source_key"], None, "NO_MATCH"
            ),
            "source_id": source_node["source_id"],
            "source_key": source_node["source_key"],
            "canonical_id": None,
            "mapping_type": "NO_MATCH",
            "mapping_status": "HOLD",
            "mapping_method": "MANUAL_REVIEW",
            "candidate_class": "UNMATCHED",
            "evidence": {
                **evidence_base,
                "canonical_path": None,
                "canonical_name": None,
                "canonical_kind": kind,
                "candidate_reason": "no normalized name match against current DRAFT fixtures",
                "review_note": "NO_MATCH is retained as evidence, not deleted",
            },
            "row_number_used": False,
        }
    ]


def _candidate_row(
    source_node: dict,
    canonical: dict,
    by_id: dict[str, dict],
    *,
    candidate_class: str,
    mapping_type: str,
    mapping_status: str,
    mapping_method: str,
    reason: str,
    extra: dict,
) -> dict:
    return {
        "proposal_key": proposal_key(
            source_node["source_id"],
            source_node["source_key"],
            canonical["id"],
            mapping_type,
        ),
        "source_id": source_node["source_id"],
        "source_key": source_node["source_key"],
        "canonical_id": canonical["id"],
        "mapping_type": mapping_type,
        "mapping_status": mapping_status,
        "mapping_method": mapping_method,
        "candidate_class": candidate_class,
        "evidence": {
            **extra,
            "canonical_path": canonical_path(by_id, canonical),
            "canonical_name": canonical["name_normalized"],
            "canonical_parent": by_id.get(canonical.get("parent_id") or "", {}).get("name_normalized"),
            "candidate_reason": reason,
            "review_note": "PROPOSED/HOLD only. AUTO APPROVED = 0.",
        },
        "row_number_used": False,
    }


def mapping_nodes_for_source(source_id: str, nodes: list[dict]) -> list[dict]:
    if source_id == SOURCE_KOSHA:
        return [n for n in nodes if n["node_type"] == "DETAIL_PROCESS"]
    if source_id == SOURCE_KALIS:
        return [n for n in nodes if n["node_type"] == "TASK"]
    return list(nodes)


def generate_candidates(
    source_nodes: list[dict],
    canonicals: list[dict] | None = None,
) -> list[dict]:
    canonicals = canonicals if canonicals is not None else synthetic_canonical_nodes()
    rows: list[dict] = []
    for node in source_nodes:
        rows.extend(classify_source_node(node, canonicals))
    return sorted(
        rows,
        key=lambda row: (
            row["source_id"],
            row["source_key"],
            row["canonical_id"] or "",
            row["mapping_type"],
            row["proposal_key"],
        ),
    )


def summarize_candidates(rows: list[dict], source_id: str) -> dict:
    subset = [row for row in rows if row["source_id"] == source_id]
    keys = {row["source_key"] for row in subset}
    classes = defaultdict(int)
    for row in subset:
        classes[row["candidate_class"]] += 1
    approved = sum(1 for row in subset if is_consumer_eligible(row["mapping_status"]))
    return {
        "source_nodes_analyzed": len(keys),
        "candidate_rows": len(subset),
        "exact_path_candidates": classes["EXACT_PATH_CANDIDATE"],
        "exact_name_candidates": classes["EXACT_NAME_CANDIDATE"],
        "ambiguous": classes["AMBIGUOUS"],
        "unmatched": classes["UNMATCHED"],
        "approved_mappings": approved,
    }


def approved_exact_equivalent_conflicts(rows: list[dict]) -> list[tuple[str, str]]:
    seen: dict[tuple[str, str], str] = {}
    conflicts = []
    for row in rows:
        if row["mapping_status"] != "APPROVED" or row["mapping_type"] != "EXACT_EQUIVALENT":
            continue
        key = (row["source_id"], row["source_key"])
        canonical_id = row["canonical_id"]
        if key in seen and seen[key] != canonical_id:
            conflicts.append(key)
        else:
            seen[key] = canonical_id
    return conflicts


def build_candidate_plan(root: Path = DEFAULT_ROOT) -> dict:
    source_plan = build_plan(root)
    canonicals = synthetic_canonical_nodes()
    a_nodes = mapping_nodes_for_source(SOURCE_CIC_W, source_plan["_plan"]["a_nodes"])
    b_nodes = mapping_nodes_for_source(SOURCE_KOSHA, source_plan["_plan"]["b_nodes"])
    c_nodes = mapping_nodes_for_source(SOURCE_KALIS, source_plan["_plan"]["c_nodes"])
    assert not any("번호" in node.get("source_key", "") for node in b_nodes)
    candidates = generate_candidates(a_nodes + b_nodes + c_nodes, canonicals)
    if approved_exact_equivalent_conflicts(candidates):
        raise ValueError("APPROVED EXACT_EQUIVALENT cannot target two canonicals")
    summary = {
        "WO": "WO-RISK-03",
        "PHYSICAL_MODEL_DECISION": PHYSICAL_MODEL_DECISION,
        "db_write": 0,
        "production_canonical_rows": 0,
        "production_mapping_rows": 0,
        "AUTO_APPROVED": 0,
        "MODEL_D": "APPROVED / FROZEN",
        "B": {
            "identity": B_IDENTITY,
            "raw_rows": source_plan["B"]["rows"],
            "path_identities": source_plan["B"]["path_identities"],
            "leaf_occurrence_sum": source_plan["B"]["leaf_occurrence_sum"],
            **summarize_candidates(candidates, SOURCE_KOSHA),
        },
        "A": summarize_candidates(candidates, SOURCE_CIC_W),
        "C": {
            "unique_content": source_plan["C"]["unique_content"],
            "occurrence_sum": source_plan["C"]["occurrence_sum"],
            "record_direct_canonical": 0,
            **summarize_candidates(candidates, SOURCE_KALIS),
        },
        "canonical_fixtures": len(canonicals),
        "APPROVED_COVERAGE": "NOT YET MEASURED",
        "LLM": 0,
        "vector_similarity": 0,
        "string_auto_map": 0,
        "cross_source_merge": 0,
    }
    assert summary["B"]["raw_rows"] == B_RAW_ROWS
    assert summary["B"]["path_identities"] == B_PATH_IDENTITIES
    assert summary["B"]["leaf_occurrence_sum"] == B_LEAF_OCCURRENCE_SUM
    assert summary["C"]["unique_content"] == C_UNIQUE
    assert summary["C"]["occurrence_sum"] == C_OCCURRENCE
    payload = {
        "proposal_keys": [row["proposal_key"] for row in candidates],
        "classes": [row["candidate_class"] for row in candidates],
        "metrics": {
            "A": summary["A"],
            "B": {k: summary["B"][k] for k in ("identity", "source_nodes_analyzed", "unmatched")},
            "C": {k: summary["C"][k] for k in ("source_nodes_analyzed", "unmatched")},
        },
    }
    summary["determinism_sha"] = sha256_parts(
        json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )
    summary["_plan"] = {"candidates": candidates, "canonicals": canonicals}
    return summary


def write_report(summary: dict, dest: Path) -> None:
    slim = {k: v for k, v in summary.items() if k != "_plan"}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(slim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    summary = build_candidate_plan(DEFAULT_ROOT)
    write_report(summary, Path("artifacts/risk03/reports/summary.json"))
    slim = {k: v for k, v in summary.items() if k != "_plan"}
    print(json.dumps(slim, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
