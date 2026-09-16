"""Remaining CIC_W W_MID 291 evidence pack. Cursor does not decide kind or family policy."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from tools.risk02.contract import SOURCE_CIC_W
from tools.risk04.review002 import (
    _index_tree,
    lexical_cues,
    root_of,
)
from tools.risk04.review002_decisions import (
    FROZEN_BATCH002_SHA,
    build_batch002_gpt_manifest,
    write_batch002_review_artifacts,
)
from tools.risk04.review_decisions import build_gpt_manifest, write_tsv
from tools.risk04.seed_review import DEFAULT_ROOT, build_raw_seed_plan, universe_sha
from tools.risk04.semantic_gate import apply_semantic_gate

REVIEW003_PATH = Path("docs/knowledge/risk/RISK04_CICW_MID_REVIEW003_INPUT.tsv")
BATCH_NO_START = 401
CHILD_DISPLAY_MAX = 20
SAMPLE_LIMIT = 10

WORKSHEET_FIELDS = (
    "batch_no",
    "seed_proposal_key",
    "source_id",
    "source_key",
    "source_node_type",
    "name",
    "source_path",
    "root_name",
    "root_source_key",
    "depth",
    "current_semantic_kind",
    "current_review_decision",
    "root_semantic_kind",
    "root_review_decision",
    "root_review_batch_no",
    "direct_child_count",
    "direct_child_keys",
    "direct_child_names",
    "children_truncated",
    "reviewed_child_count",
    "reviewed_child_process",
    "reviewed_child_task",
    "reviewed_child_method",
    "reviewed_child_material_component",
    "reviewed_child_facility_equipment",
    "reviewed_child_classification",
    "reviewed_child_ambiguous",
    "unreviewed_child_count",
    "reviewed_child_keep",
    "reviewed_child_merge_candidate",
    "reviewed_child_hold",
    "reviewed_child_reject",
    "reviewed_child_refs",
    "unreviewed_child_refs",
    "reviewed_child_mechanical_state",
    "gpt_leaf_family_policy",
    "same_name_mid_count",
    "same_name_mid_paths",
    "same_name_other_source_count",
    "same_name_other_source_refs",
    "sibling_mid_count",
    "sample_sibling_mids",
    "reviewed_sibling_count",
    "reviewed_sibling_refs",
    "lexical_cues",
    "gpt_semantic_kind",
    "gpt_review_decision",
    "merge_candidate_keys",
    "gpt_reason",
)


def _join(parts: list[str]) -> str:
    return " | ".join(parts)


def reviewed_cicw_index() -> dict[str, dict]:
    """source_key -> GPT overlay for CIC_W Batch001+Batch002. Not approval."""
    by_key: dict[str, dict] = {}
    for row in build_gpt_manifest():
        if row["source_id"] != SOURCE_CIC_W:
            continue
        by_key[row["source_key"]] = {
            "batch_no": row["batch_no"],
            "seed_proposal_key": row["seed_proposal_key"],
            "semantic_kind": row["semantic_kind_override"],
            "decision": row["semantic_review_decision"],
        }
    for row in build_batch002_gpt_manifest():
        by_key[row["source_key"]] = {
            "batch_no": row["batch_no"],
            "seed_proposal_key": row["seed_proposal_key"],
            "semantic_kind": row["semantic_kind_override"],
            "decision": row["semantic_review_decision"],
        }
    if len(by_key) != 250:
        raise ValueError(f"CIC_W reviewed aggregate {len(by_key)} != 250")
    return by_key


def _mechanical_state(reviewed_n: int, child_n: int, kinds: set[str]) -> str:
    if reviewed_n == 0:
        return "NO_REVIEWED_CHILDREN"
    multi = len(kinds) > 1
    if reviewed_n == child_n:
        return "ALL_REVIEWED_MULTI_KIND" if multi else "ALL_REVIEWED_SINGLE_KIND"
    return "PARTIAL_REVIEW_MULTI_KIND" if multi else "PARTIAL_REVIEW_SINGLE_KIND"


def build_review003(root: Path = DEFAULT_ROOT) -> dict:
    raw = build_raw_seed_plan(root)
    gated = apply_semantic_gate(raw["proposals"])
    a_nodes = raw["source_plan"]["_plan"]["a_nodes"]
    by_key, children = _index_tree(a_nodes)
    proposal_by_src = {row["origin_source_key"]: row for row in gated if row["origin_source_id"] == SOURCE_CIC_W}
    reviewed = reviewed_cicw_index()
    mids = [n for n in a_nodes if n["node_type"] == "W_MID"]
    if len(mids) != 373:
        raise ValueError(f"W_MID total {len(mids)}")
    reviewed_mids = [n for n in mids if n["source_key"] in reviewed]
    remain = [n for n in mids if n["source_key"] not in reviewed]
    if len(reviewed_mids) != 82 or len(remain) != 291:
        raise ValueError(f"W_MID split reviewed={len(reviewed_mids)} remain={len(remain)}")
    if set(n["source_key"] for n in reviewed_mids) & set(n["source_key"] for n in remain):
        raise ValueError("reviewed/remain MID intersection")
    remain.sort(key=lambda n: n["source_key"])
    for node in remain:
        proposal = proposal_by_src[node["source_key"]]
        if proposal["semantic_kind"] != "AMBIGUOUS" or proposal["semantic_review_decision"] != "UNREVIEWED":
            raise ValueError(f"remaining MID not AMBIGUOUS/UNREVIEWED: {node['source_key']}")
    mid_by_name: dict[str, list[dict]] = defaultdict(list)
    for node in mids:
        mid_by_name[node["name_normalized"]].append(node)
    other_by_name: dict[str, list[dict]] = defaultdict(list)
    for row in gated:
        if row["origin_source_id"] == SOURCE_CIC_W:
            continue
        other_by_name[row["proposed_name_normalized"]].append(row)
    mids_by_root: dict[str, list[dict]] = defaultdict(list)
    for node in mids:
        mids_by_root[root_of(node, by_key)["source_key"]].append(node)
    for group in mids_by_root.values():
        group.sort(key=lambda n: n["source_key"])
    rows = []
    family_states = Counter()
    child_counts = []
    covered = 0
    for i, node in enumerate(remain):
        kids = list(children.get(node["source_key"], []))
        kids.sort(key=lambda n: n["source_key"])
        non_leaf = [n for n in kids if n["node_type"] != "W_LEAF"]
        if non_leaf:
            raise ValueError("STRUCTURE DRIFT: W_MID direct child is not W_LEAF")
        child_counts.append(len(kids))
        truncated = "YES" if len(kids) > CHILD_DISPLAY_MAX else "NO"
        shown = kids[:CHILD_DISPLAY_MAX]
        rev_kids = [n for n in kids if n["source_key"] in reviewed]
        unrev_kids = [n for n in kids if n["source_key"] not in reviewed]
        if len(rev_kids) + len(unrev_kids) != len(kids):
            raise ValueError("child arithmetic drift")
        if rev_kids:
            covered += 1
        kind_counts = Counter(reviewed[n["source_key"]]["semantic_kind"] for n in rev_kids)
        dec_counts = Counter(reviewed[n["source_key"]]["decision"] for n in rev_kids)
        state = _mechanical_state(len(rev_kids), len(kids), set(kind_counts))
        family_states[state] += 1
        root = root_of(node, by_key)
        root_overlay = reviewed[root["source_key"]]
        siblings = [n for n in mids_by_root[root["source_key"]] if n["source_key"] != node["source_key"]]
        rev_sibs = [n for n in siblings if n["source_key"] in reviewed]
        name = node["name_normalized"]
        mid_peers = sorted(mid_by_name[name], key=lambda n: n["source_key"])
        other_peers = sorted(
            other_by_name.get(name, []),
            key=lambda p: (p["origin_source_id"], p["source_path"], p["origin_source_key"]),
        )
        proposal = proposal_by_src[node["source_key"]]
        rows.append(
            {
                "batch_no": str(BATCH_NO_START + i),
                "seed_proposal_key": proposal["seed_proposal_key"],
                "source_id": SOURCE_CIC_W,
                "source_key": node["source_key"],
                "source_node_type": "W_MID",
                "name": name,
                "source_path": node["path_normalized"],
                "root_name": root["name_normalized"],
                "root_source_key": root["source_key"],
                "depth": "2",
                "current_semantic_kind": "AMBIGUOUS",
                "current_review_decision": "UNREVIEWED",
                "root_semantic_kind": root_overlay["semantic_kind"],
                "root_review_decision": root_overlay["decision"],
                "root_review_batch_no": str(root_overlay["batch_no"]),
                "direct_child_count": str(len(kids)),
                "direct_child_keys": _join([n["source_key"] for n in shown]),
                "direct_child_names": _join([n["name_normalized"] for n in shown]),
                "children_truncated": truncated,
                "reviewed_child_count": str(len(rev_kids)),
                "reviewed_child_process": str(kind_counts.get("PROCESS", 0)),
                "reviewed_child_task": str(kind_counts.get("TASK", 0)),
                "reviewed_child_method": str(kind_counts.get("METHOD", 0)),
                "reviewed_child_material_component": str(kind_counts.get("MATERIAL_COMPONENT", 0)),
                "reviewed_child_facility_equipment": str(kind_counts.get("FACILITY_EQUIPMENT", 0)),
                "reviewed_child_classification": str(kind_counts.get("CLASSIFICATION", 0)),
                "reviewed_child_ambiguous": str(kind_counts.get("AMBIGUOUS", 0)),
                "unreviewed_child_count": str(len(unrev_kids)),
                "reviewed_child_keep": str(dec_counts.get("KEEP_AS_DISTINCT", 0)),
                "reviewed_child_merge_candidate": str(dec_counts.get("MERGE_CANDIDATE", 0)),
                "reviewed_child_hold": str(dec_counts.get("HOLD", 0)),
                "reviewed_child_reject": str(dec_counts.get("REJECT", 0)),
                "reviewed_child_refs": _join(
                    [
                        f"{n['source_key']}:{n['name_normalized']}:{reviewed[n['source_key']]['semantic_kind']}:{reviewed[n['source_key']]['decision']}"
                        for n in rev_kids[:CHILD_DISPLAY_MAX]
                    ]
                ),
                "unreviewed_child_refs": _join(
                    [f"{n['source_key']}:{n['name_normalized']}" for n in unrev_kids[:CHILD_DISPLAY_MAX]]
                ),
                "reviewed_child_mechanical_state": state,
                "gpt_leaf_family_policy": "PENDING",
                "same_name_mid_count": str(len(mid_peers)),
                "same_name_mid_paths": _join([p["path_normalized"] for p in mid_peers[:SAMPLE_LIMIT]]),
                "same_name_other_source_count": str(len(other_peers)),
                "same_name_other_source_refs": _join(
                    [f"{p['origin_source_id']}:{p['source_path']}" for p in other_peers[:SAMPLE_LIMIT]]
                ),
                "sibling_mid_count": str(len(siblings)),
                "sample_sibling_mids": _join([n["name_normalized"] for n in siblings[:SAMPLE_LIMIT]]),
                "reviewed_sibling_count": str(len(rev_sibs)),
                "reviewed_sibling_refs": _join(
                    [
                        f"{n['source_key']}:{n['name_normalized']}:{reviewed[n['source_key']]['semantic_kind']}:{reviewed[n['source_key']]['decision']}"
                        for n in rev_sibs[:SAMPLE_LIMIT]
                    ]
                ),
                "lexical_cues": lexical_cues(name),
                "gpt_semantic_kind": "PENDING",
                "gpt_review_decision": "PENDING",
                "merge_candidate_keys": "EMPTY",
                "gpt_reason": "EMPTY",
            }
        )
    if any(row["gpt_semantic_kind"] != "PENDING" for row in rows):
        raise ValueError("Cursor must not fill GPT MID decisions")
    if [int(row["batch_no"]) for row in rows] != list(range(401, 692)):
        raise ValueError("REVIEW003 numbering drift")
    digest = universe_sha(rows, *WORKSHEET_FIELDS)
    avg = (sum(child_counts) / len(child_counts)) if child_counts else 0
    kinds_rev = Counter(item["semantic_kind"] for item in reviewed.values())
    dec_rev = Counter(item["decision"] for item in reviewed.values())
    facts = {
        "CIC_W_reviewed": 250,
        "reviewed_PROCESS": kinds_rev["PROCESS"],
        "reviewed_TASK": kinds_rev["TASK"],
        "reviewed_METHOD": kinds_rev["METHOD"],
        "reviewed_MATERIAL_COMPONENT": kinds_rev["MATERIAL_COMPONENT"],
        "reviewed_FACILITY_EQUIPMENT": kinds_rev["FACILITY_EQUIPMENT"],
        "reviewed_CLASSIFICATION": kinds_rev["CLASSIFICATION"],
        "reviewed_AMBIGUOUS": kinds_rev["AMBIGUOUS"],
        "KEEP_AS_DISTINCT": dec_rev["KEEP_AS_DISTINCT"],
        "MERGE_CANDIDATE": dec_rev["MERGE_CANDIDATE"],
        "HOLD": dec_rev["HOLD"],
        "REJECT": dec_rev["REJECT"],
        "W_ROOT_reviewed": 62,
        "W_MID_total": 373,
        "W_MID_reviewed": 82,
        "W_MID_remaining": 291,
        "REVIEW003": len(rows),
        "NO_REVIEWED_CHILDREN": family_states["NO_REVIEWED_CHILDREN"],
        "PARTIAL_REVIEW_SINGLE_KIND": family_states["PARTIAL_REVIEW_SINGLE_KIND"],
        "PARTIAL_REVIEW_MULTI_KIND": family_states["PARTIAL_REVIEW_MULTI_KIND"],
        "ALL_REVIEWED_SINGLE_KIND": family_states["ALL_REVIEWED_SINGLE_KIND"],
        "ALL_REVIEWED_MULTI_KIND": family_states["ALL_REVIEWED_MULTI_KIND"],
        "MID_with_children": sum(1 for n in child_counts if n > 0),
        "MID_child_min": min(child_counts) if child_counts else 0,
        "MID_child_max": max(child_counts) if child_counts else 0,
        "MID_child_avg": round(avg, 4),
        "MID_reviewed_child_coverage_count": covered,
        "MID_reviewed_child_coverage_pct": round(100.0 * covered / len(rows), 2),
        "GLOBAL_AUTO_CLASSIFIER": "NOT SAFE",
        "FROZEN_BATCH002_SHA": FROZEN_BATCH002_SHA,
    }
    return {
        "rows": rows,
        "sha": digest,
        "facts": facts,
        "source_plan": raw["source_plan"],
        "reviewed": reviewed,
        "remain_keys": [n["source_key"] for n in remain],
        "reviewed_mid_keys": [n["source_key"] for n in reviewed_mids],
    }


def write_review003(rows: list[dict], dest: Path = REVIEW003_PATH) -> None:
    write_tsv(rows, dest, WORKSHEET_FIELDS)


def load_review003(path: Path = REVIEW003_PATH) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main() -> None:
    batch002 = write_batch002_review_artifacts()
    pack = build_review003()
    write_review003(pack["rows"])
    slim = {
        "WO": "WO-RISK-04-REVIEW-003",
        "BATCH002_MANIFEST_SHA": batch002["sha"],
        "REVIEW003_SHA": pack["sha"],
        "facts": pack["facts"],
        "GPT_PENDING": 291,
        "CANONICAL_UUID_CREATED": 0,
        "AUTO_APPROVED": 0,
        "db_write": 0,
    }
    print(json.dumps(slim, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
