"""Remaining CIC_W W_LEAF 1181 full-review routing. Cursor does not decide leaf kind."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from tools.risk02.contract import SOURCE_CIC_W
from tools.risk04.identity import parent_path
from tools.risk04.review002 import _index_tree, lexical_cues, root_of
from tools.risk04.review002_decisions import build_batch002_gpt_manifest
from tools.risk04.review003_decisions import (
    FROZEN_REVIEW003_SHA,
    build_review003_gpt_manifest,
    write_review003_decision_artifacts,
)
from tools.risk04.review_decisions import build_gpt_manifest, write_tsv
from tools.risk04.seed_review import DEFAULT_ROOT, build_raw_seed_plan, universe_sha
from tools.risk04.semantic_gate import apply_semantic_gate

SAMPLE_LIMIT = 10
REVIEW_NO_START = 692
BATCH_SIZES = (200, 200, 200, 200, 200, 181)
BATCH_LABELS = ("004A", "004B", "004C", "004D", "004E", "004F")
LEAF_DIR = Path("docs/knowledge/risk")
LEAF_PATHS = tuple(LEAF_DIR / f"RISK04_CICW_LEAF_BATCH{label}_REVIEW_INPUT.tsv" for label in BATCH_LABELS)

LEAF_FIELDS = (
    "review_no",
    "seed_proposal_key",
    "source_id",
    "source_key",
    "name",
    "source_path",
    "root_name",
    "root_source_key",
    "parent_name",
    "parent_source_key",
    "parent_path",
    "parent_semantic_kind",
    "parent_review_decision",
    "parent_leaf_family_policy",
    "sibling_count",
    "sibling_names",
    "same_name_cicw_count",
    "same_name_cicw_paths",
    "same_name_other_source_count",
    "same_name_other_source_refs",
    "reviewed_sibling_count",
    "reviewed_sibling_refs",
    "lexical_cues",
    "current_semantic_kind",
    "current_review_decision",
    "gpt_semantic_kind",
    "gpt_review_decision",
    "merge_candidate_keys",
    "gpt_reason",
)


def _join(parts: list[str]) -> str:
    return " | ".join(parts)


def reviewed_cicw_after_003(root: Path = DEFAULT_ROOT) -> dict[str, dict]:
    by_key: dict[str, dict] = {}
    for row in build_gpt_manifest():
        if row["source_id"] != SOURCE_CIC_W:
            continue
        by_key[row["source_key"]] = {
            "batch_no": row["batch_no"],
            "seed_proposal_key": row["seed_proposal_key"],
            "semantic_kind": row["semantic_kind_override"],
            "decision": row["semantic_review_decision"],
            "family_policy": "NOT_ASSESSED",
        }
    for row in build_batch002_gpt_manifest():
        by_key[row["source_key"]] = {
            "batch_no": row["batch_no"],
            "seed_proposal_key": row["seed_proposal_key"],
            "semantic_kind": row["semantic_kind_override"],
            "decision": row["semantic_review_decision"],
            "family_policy": "NOT_ASSESSED",
        }
    for row in build_review003_gpt_manifest(root):
        by_key[row["source_key"]] = {
            "batch_no": row["batch_no"],
            "seed_proposal_key": row["seed_proposal_key"],
            "semantic_kind": row["semantic_kind_after"],
            "decision": row["semantic_review_decision"],
            "family_policy": row["gpt_leaf_family_policy"],
        }
    if len(by_key) != 541:
        raise ValueError(f"CIC_W reviewed aggregate {len(by_key)} != 541")
    return by_key


def leaf_batch_path(label: str) -> Path:
    return LEAF_DIR / f"RISK04_CICW_LEAF_BATCH{label}_REVIEW_INPUT.tsv"


def build_leaf_routing(root: Path = DEFAULT_ROOT) -> dict:
    raw = build_raw_seed_plan(root)
    if len(raw["proposals"]) != 3103:
        raise ValueError(f"SOURCE PROPOSAL UNIVERSE {len(raw['proposals'])}")
    gated = apply_semantic_gate(raw["proposals"])
    a_nodes = raw["source_plan"]["_plan"]["a_nodes"]
    by_key, children = _index_tree(a_nodes)
    proposal_by_src = {row["origin_source_key"]: row for row in gated if row["origin_source_id"] == SOURCE_CIC_W}
    reviewed = reviewed_cicw_after_003(root)
    types = Counter(n["node_type"] for n in a_nodes)
    if types["W_ROOT"] != 62 or types["W_MID"] != 373 or types["W_LEAF"] != 1287:
        raise ValueError(f"CIC_W hierarchy {types}")
    roots = [n for n in a_nodes if n["node_type"] == "W_ROOT"]
    mids = [n for n in a_nodes if n["node_type"] == "W_MID"]
    leaves = [n for n in a_nodes if n["node_type"] == "W_LEAF"]
    if any(n["source_key"] not in reviewed for n in roots):
        raise ValueError("W_ROOT remaining")
    if any(n["source_key"] not in reviewed for n in mids):
        raise ValueError("W_MID remaining")
    remain = [n for n in leaves if n["source_key"] not in reviewed]
    reviewed_leaves = [n for n in leaves if n["source_key"] in reviewed]
    if len(reviewed_leaves) != 106 or len(remain) != 1181:
        raise ValueError(f"W_LEAF split reviewed={len(reviewed_leaves)} remain={len(remain)}")
    remain.sort(key=lambda n: (root_of(n, by_key)["source_key"], n.get("parent_source_key") or "", n["source_key"]))
    cic_by_name: dict[str, list[dict]] = defaultdict(list)
    for node in a_nodes:
        cic_by_name[node["name_normalized"]].append(node)
    for group in cic_by_name.values():
        group.sort(key=lambda n: n["source_key"])
    other_by_name: dict[str, list[dict]] = defaultdict(list)
    for row in gated:
        if row["origin_source_id"] == SOURCE_CIC_W:
            continue
        other_by_name[row["proposed_name_normalized"]].append(row)
    rows = []
    for i, node in enumerate(remain):
        proposal = proposal_by_src[node["source_key"]]
        if proposal["semantic_kind"] != "AMBIGUOUS" or proposal["semantic_review_decision"] != "UNREVIEWED":
            raise ValueError(f"remaining LEAF not AMBIGUOUS/UNREVIEWED: {node['source_key']}")
        parent_key = node.get("parent_source_key") or ""
        parent = by_key.get(parent_key)
        if parent is None or parent["node_type"] != "W_MID":
            raise ValueError("STRUCTURE DRIFT: W_LEAF parent is not W_MID")
        parent_overlay = reviewed.get(parent_key)
        if parent_overlay is None:
            raise ValueError(f"unreviewed parent MID {parent_key}")
        policy = parent_overlay["family_policy"]
        root = root_of(node, by_key)
        siblings = [n for n in children.get(parent_key, []) if n["source_key"] != node["source_key"]]
        if any(n["node_type"] != "W_LEAF" for n in siblings):
            raise ValueError("STRUCTURE DRIFT: leaf sibling is not W_LEAF")
        rev_sibs = [n for n in siblings if n["source_key"] in reviewed]
        name = node["name_normalized"]
        cic_peers = cic_by_name[name]
        other_peers = sorted(
            other_by_name.get(name, []),
            key=lambda p: (p["origin_source_id"], p["source_path"], p["origin_source_key"]),
        )
        rows.append(
            {
                "review_no": str(REVIEW_NO_START + i),
                "seed_proposal_key": proposal["seed_proposal_key"],
                "source_id": SOURCE_CIC_W,
                "source_key": node["source_key"],
                "name": name,
                "source_path": node["path_normalized"],
                "root_name": root["name_normalized"],
                "root_source_key": root["source_key"],
                "parent_name": parent["name_normalized"],
                "parent_source_key": parent_key,
                "parent_path": parent_path(node["path_normalized"]),
                "parent_semantic_kind": parent_overlay["semantic_kind"],
                "parent_review_decision": parent_overlay["decision"],
                "parent_leaf_family_policy": policy,
                "sibling_count": str(len(siblings)),
                "sibling_names": _join([n["name_normalized"] for n in siblings[:SAMPLE_LIMIT]]),
                "same_name_cicw_count": str(len(cic_peers)),
                "same_name_cicw_paths": _join([p["path_normalized"] for p in cic_peers[:SAMPLE_LIMIT]]),
                "same_name_other_source_count": str(len(other_peers)),
                "same_name_other_source_refs": _join(
                    [f"{p['origin_source_id']}:{p['source_path']}" for p in other_peers[:SAMPLE_LIMIT]]
                ),
                "reviewed_sibling_count": str(len(rev_sibs)),
                "reviewed_sibling_refs": _join(
                    [
                        f"{n['source_key']}:{n['name_normalized']}:{reviewed[n['source_key']]['semantic_kind']}:{reviewed[n['source_key']]['decision']}"
                        for n in rev_sibs[:SAMPLE_LIMIT]
                    ]
                ),
                "lexical_cues": lexical_cues(name),
                "current_semantic_kind": "AMBIGUOUS",
                "current_review_decision": "UNREVIEWED",
                "gpt_semantic_kind": "PENDING",
                "gpt_review_decision": "PENDING",
                "merge_candidate_keys": "EMPTY",
                "gpt_reason": "EMPTY",
            }
        )
    if [int(row["review_no"]) for row in rows] != list(range(692, 1873)):
        raise ValueError("leaf review_no drift")
    if any(row["gpt_semantic_kind"] != "PENDING" for row in rows):
        raise ValueError("Cursor must not fill GPT LEAF decisions")
    batches = []
    start = 0
    for size in BATCH_SIZES:
        batches.append(rows[start : start + size])
        start += size
    if start != len(rows):
        raise ValueError("leaf batch partition drift")
    kinds_rev = Counter(item["semantic_kind"] for item in reviewed.values())
    dec_rev = Counter(item["decision"] for item in reviewed.values())
    facts = {
        "CIC_W_reviewed": 541,
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
        "W_MID_reviewed": 373,
        "W_LEAF_reviewed": 106,
        "W_LEAF_remaining": 1181,
        "unreviewed_PROCESS": 0,
        "unreviewed_AMBIGUOUS": 1181,
        "GLOBAL_AUTO_CLASSIFIER": "NOT SAFE",
        "FROZEN_REVIEW003_SHA": FROZEN_REVIEW003_SHA,
        "batch_sizes": [len(batch) for batch in batches],
    }
    expected = {
        "PROCESS": 383,
        "TASK": 25,
        "METHOD": 4,
        "MATERIAL_COMPONENT": 37,
        "FACILITY_EQUIPMENT": 47,
        "CLASSIFICATION": 28,
        "AMBIGUOUS": 17,
    }
    if kinds_rev != expected:
        raise ValueError(f"reviewed kind aggregate {dict(kinds_rev)}")
    if dec_rev != {"KEEP_AS_DISTINCT": 379, "MERGE_CANDIDATE": 29, "HOLD": 17, "REJECT": 116}:
        raise ValueError(f"reviewed decision aggregate {dict(dec_rev)}")
    return {
        "rows": rows,
        "batches": batches,
        "sha": universe_sha(rows, *LEAF_FIELDS),
        "batch_shas": [universe_sha(batch, *LEAF_FIELDS) for batch in batches],
        "facts": facts,
        "source_plan": raw["source_plan"],
        "reviewed": reviewed,
        "remain_keys": [n["source_key"] for n in remain],
    }


def write_leaf_batches(batches: list[list[dict]]) -> None:
    for path, batch in zip(LEAF_PATHS, batches, strict=True):
        write_tsv(batch, path, LEAF_FIELDS)


def load_leaf_batch(path: Path) -> list[dict]:
    import csv

    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def load_leaf_universe() -> list[dict]:
    rows = []
    for path in LEAF_PATHS:
        rows.extend(load_leaf_batch(path))
    return rows


def main() -> None:
    mid = write_review003_decision_artifacts()
    pack = build_leaf_routing()
    write_leaf_batches(pack["batches"])
    slim = {
        "WO": "WO-RISK-04-REVIEW-004",
        "W_MID_MANIFEST_SHA": mid["sha"],
        "LEAF_ROUTING_SHA": pack["sha"],
        "batch_shas": {label: digest for label, digest in zip(BATCH_LABELS, pack["batch_shas"], strict=True)},
        "facts": pack["facts"],
        "GPT_LEAF_PENDING": 1181,
        "CANONICAL_UUID_CREATED": 0,
        "AUTO_APPROVED": 0,
        "db_write": 0,
    }
    print(json.dumps(slim, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
