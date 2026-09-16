"""CIC_W Batch 002 hierarchical evidence pack. Cursor does not decide semantic kind."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from tools.risk02.contract import SOURCE_CIC_W
from tools.risk04.identity import parent_path
from tools.risk04.review_decisions import build_gpt_manifest
from tools.risk04.review_evidence import FROZEN_BATCH_SHA, load_frozen_batch
from tools.risk04.seed_review import DEFAULT_ROOT, build_raw_seed_plan, universe_sha
from tools.risk04.semantic_gate import apply_semantic_gate

BATCH002_PATH = Path("docs/knowledge/risk/RISK04_CICW_BATCH002_REVIEW_INPUT.tsv")
LOCAL_CENSUS = Path("artifacts/risk04/review002/cicw_unreviewed_census.jsonl")
BATCH002_TARGET = 200
MID_CAP = 70
BATCH_NO_START = 201
SAMPLE_LIMIT = 10
LEAF_ROOT_SHARE_MAX = 0.25
LEAF_PARENT_SHARE_MAX = 0.10
MATERIAL_LIKE_TOKENS = ("블록", "판넬", "말뚝", "유리", "Pile", "부재")

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
    "parent_name",
    "parent_source_key",
    "parent_path",
    "grandparent_name",
    "grandparent_path",
    "depth",
    "is_leaf",
    "child_count",
    "descendant_count",
    "descendant_leaf_count",
    "sample_children",
    "sibling_count",
    "sample_siblings",
    "ancestor_chain",
    "same_name_cicw_count",
    "same_name_cicw_paths",
    "same_name_other_source_count",
    "same_name_other_source_refs",
    "reviewed_anchor_relation",
    "reviewed_anchor_batch_no",
    "reviewed_anchor_name",
    "reviewed_anchor_semantic_kind",
    "reviewed_anchor_decision",
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


def lexical_cues(name: str) -> str:
    cues = []
    if name.endswith("공사"):
        cues.append("ENDS_WITH_공사")
    if "공법" in name:
        cues.append("CONTAINS_공법")
    if name.endswith("작업"):
        cues.append("ENDS_WITH_작업")
    if "설비" in name:
        cues.append("CONTAINS_설비")
    if any(token in name for token in MATERIAL_LIKE_TOKENS):
        cues.append("MATERIAL_LIKE_TOKEN")
    return "|".join(cues) if cues else "NONE"


def _index_tree(a_nodes: list[dict]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    by_key = {n["source_key"]: n for n in a_nodes}
    children: dict[str, list[dict]] = defaultdict(list)
    for node in a_nodes:
        parent = node.get("parent_source_key")
        if parent:
            children[parent].append(node)
    for group in children.values():
        group.sort(key=lambda n: n["source_key"])
    return by_key, children


def root_of(node: dict, by_key: dict[str, dict]) -> dict:
    cur = node
    seen: set[str] = set()
    while cur.get("parent_source_key"):
        if cur["source_key"] in seen:
            break
        seen.add(cur["source_key"])
        parent = by_key.get(cur["parent_source_key"])
        if parent is None:
            break
        cur = parent
    return cur


def descendants(source_key: str, children: dict[str, list[dict]]) -> list[dict]:
    out: list[dict] = []
    stack = list(children.get(source_key, ()))
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(children.get(node["source_key"], ()))
    return out


def ancestor_chain(node: dict, by_key: dict[str, dict]) -> str:
    names = [node["name_normalized"]]
    cur = node
    seen: set[str] = set()
    while cur.get("parent_source_key"):
        if cur["source_key"] in seen:
            break
        seen.add(cur["source_key"])
        parent = by_key.get(cur["parent_source_key"])
        if parent is None:
            break
        names.append(parent["name_normalized"])
        cur = parent
    names.reverse()
    return " > ".join(names)


def _select_leaves_round_robin(leaves: list[dict], quota: int, by_key: dict[str, dict]) -> list[dict]:
    buckets: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in leaves:
        node = row["node"]
        root_key = root_of(node, by_key)["source_key"]
        parent_key = node.get("parent_source_key") or ""
        buckets[root_key][parent_key].append(row)
    for root_key in buckets:
        for parent_key in buckets[root_key]:
            buckets[root_key][parent_key].sort(key=lambda item: item["node"]["source_key"])
    roots_sorted = sorted(buckets)
    parents_sorted = {root: sorted(buckets[root]) for root in roots_sorted}
    parent_rr = {root: 0 for root in roots_sorted}
    picked: list[dict] = []
    exhausted: set[str] = set()
    while len(picked) < quota and len(exhausted) < len(roots_sorted):
        progressed = False
        for root in roots_sorted:
            if len(picked) >= quota:
                break
            if root in exhausted:
                continue
            n_parents = len(parents_sorted[root])
            chosen = None
            for _ in range(n_parents):
                parent = parents_sorted[root][parent_rr[root] % n_parents]
                parent_rr[root] += 1
                bucket = buckets[root][parent]
                if bucket:
                    chosen = bucket.pop(0)
                    break
            if chosen is None:
                exhausted.add(root)
                continue
            picked.append(chosen)
            progressed = True
        if not progressed:
            break
    if len(picked) != quota:
        raise ValueError(f"leaf quota unmet: {len(picked)} != {quota}")
    return picked


def _assert_leaf_concentration(selected: list[dict]) -> None:
    leaves = [row for row in selected if row["node"]["node_type"] == "W_LEAF"]
    if not leaves:
        return
    root_counts = Counter(row["root_source_key"] for row in leaves)
    parent_counts = Counter(row["node"].get("parent_source_key") or "" for row in leaves)
    max_root = max(root_counts.values()) / len(leaves)
    max_parent = max(parent_counts.values()) / len(leaves)
    if max_root > LEAF_ROOT_SHARE_MAX:
        raise ValueError(f"leaf max root share {max_root:.4f} > 0.25")
    if max_parent > LEAF_PARENT_SHARE_MAX:
        raise ValueError(f"leaf max parent share {max_parent:.4f} > 0.10")


def select_batch002(pool: list[dict], by_key: dict[str, dict], children: dict[str, list[dict]]) -> list[dict]:
    if len(pool) < BATCH002_TARGET:
        raise ValueError(f"candidate pool {len(pool)} < {BATCH002_TARGET}")
    roots = [row for row in pool if row["node"]["node_type"] == "W_ROOT"]
    if len(roots) > BATCH002_TARGET:
        raise ValueError("W_ROOT > 200; STOP")
    roots = sorted(roots, key=lambda row: row["node"]["source_key"])
    selected = list(roots)
    remaining = BATCH002_TARGET - len(selected)
    mid_quota = min(MID_CAP, remaining)
    mids = [row for row in pool if row["node"]["node_type"] == "W_MID"]
    mids.sort(key=lambda row: (-row["child_count"], row["node"]["source_key"]))
    selected.extend(mids[:mid_quota])
    remaining = BATCH002_TARGET - len(selected)
    used = {row["proposal"]["seed_proposal_key"] for row in selected}
    leaves = [
        row
        for row in pool
        if row["node"]["node_type"] == "W_LEAF" and row["proposal"]["seed_proposal_key"] not in used
    ]
    selected.extend(_select_leaves_round_robin(leaves, remaining, by_key))
    if len(selected) != BATCH002_TARGET:
        raise ValueError(f"Batch002 size {len(selected)} != {BATCH002_TARGET}")
    _assert_leaf_concentration(selected)
    return selected


def _anchor(node: dict, by_key: dict[str, dict], reviewed: list[dict]) -> dict:
    node_parent = node.get("parent_source_key")
    node_root = root_of(node, by_key)["source_key"]
    ranked: list[tuple[int, int, dict, str]] = []
    for item in reviewed:
        rel = "NONE"
        rev = item["node"]
        if rev["source_key"] == node.get("parent_source_key"):
            rel = "PARENT"
        elif node["source_key"] == rev.get("parent_source_key"):
            rel = "CHILD"
        elif node_parent and node_parent == rev.get("parent_source_key"):
            rel = "SIBLING"
        elif node_root == item["root_source_key"]:
            rel = "SAME_ROOT"
        if rel == "NONE":
            continue
        rank = {"CHILD": 0, "PARENT": 1, "SIBLING": 2, "SAME_ROOT": 3}[rel]
        ranked.append((rank, int(item["batch_no"]), item, rel))
    if not ranked:
        return {
            "reviewed_anchor_relation": "NONE",
            "reviewed_anchor_batch_no": "EMPTY",
            "reviewed_anchor_name": "EMPTY",
            "reviewed_anchor_semantic_kind": "EMPTY",
            "reviewed_anchor_decision": "EMPTY",
        }
    ranked.sort(key=lambda row: (row[0], row[1], row[2]["node"]["source_key"]))
    best = ranked[0]
    item = best[2]
    return {
        "reviewed_anchor_relation": best[3],
        "reviewed_anchor_batch_no": str(item["batch_no"]),
        "reviewed_anchor_name": item["node"]["name_normalized"],
        "reviewed_anchor_semantic_kind": item["semantic_kind"],
        "reviewed_anchor_decision": item["decision"],
    }


def _enrich_row(
    batch_no: int,
    item: dict,
    *,
    by_key: dict[str, dict],
    children: dict[str, list[dict]],
    cic_by_name: dict[str, list[dict]],
    other_by_name: dict[str, list[dict]],
    reviewed: list[dict],
) -> dict:
    node = item["node"]
    proposal = item["proposal"]
    root = root_of(node, by_key)
    parent = by_key.get(node.get("parent_source_key") or "")
    grandparent = by_key.get(parent["parent_source_key"]) if parent and parent.get("parent_source_key") else None
    kids = children.get(node["source_key"], [])
    desc = descendants(node["source_key"], children)
    siblings = [
        n for n in children.get(node.get("parent_source_key") or "", []) if n["source_key"] != node["source_key"]
    ]
    name = node["name_normalized"]
    cic_peers = cic_by_name.get(name, [])
    other_peers = other_by_name.get(name, [])
    anchor = _anchor(node, by_key, reviewed)
    parent_path_value = parent_path(node["path_normalized"])
    return {
        "batch_no": str(batch_no),
        "seed_proposal_key": proposal["seed_proposal_key"],
        "source_id": SOURCE_CIC_W,
        "source_key": node["source_key"],
        "source_node_type": node["node_type"],
        "name": name,
        "source_path": node["path_normalized"],
        "root_name": root["name_normalized"],
        "root_source_key": root["source_key"],
        "parent_name": parent["name_normalized"] if parent else "",
        "parent_source_key": node.get("parent_source_key") or "",
        "parent_path": parent_path_value,
        "grandparent_name": grandparent["name_normalized"] if grandparent else "",
        "grandparent_path": parent_path(parent_path_value),
        "depth": str(int(node["depth"])),
        "is_leaf": "YES" if not kids else "NO",
        "child_count": str(len(kids)),
        "descendant_count": str(len(desc)),
        "descendant_leaf_count": str(sum(1 for n in desc if n["node_type"] == "W_LEAF")),
        "sample_children": _join([n["name_normalized"] for n in kids[:SAMPLE_LIMIT]]),
        "sibling_count": str(len(siblings)),
        "sample_siblings": _join([n["name_normalized"] for n in siblings[:SAMPLE_LIMIT]]),
        "ancestor_chain": ancestor_chain(node, by_key),
        "same_name_cicw_count": str(len(cic_peers)),
        "same_name_cicw_paths": _join([p["path_normalized"] for p in cic_peers[:SAMPLE_LIMIT]]),
        "same_name_other_source_count": str(len(other_peers)),
        "same_name_other_source_refs": _join(
            [f"{p['origin_source_id']}:{p['source_path']}" for p in other_peers[:SAMPLE_LIMIT]]
        ),
        **anchor,
        "lexical_cues": lexical_cues(name),
        "current_semantic_kind": "AMBIGUOUS",
        "current_review_decision": "UNREVIEWED",
        "gpt_semantic_kind": "PENDING",
        "gpt_review_decision": "PENDING",
        "merge_candidate_keys": "EMPTY",
        "gpt_reason": "EMPTY",
    }


def _pool_and_census(root: Path = DEFAULT_ROOT) -> dict:
    raw = build_raw_seed_plan(root)
    gated = apply_semantic_gate(raw["proposals"])
    a_nodes = raw["source_plan"]["_plan"]["a_nodes"]
    by_key, children = _index_tree(a_nodes)
    cic = [row for row in gated if row["origin_source_id"] == SOURCE_CIC_W]
    unreviewed = [
        row
        for row in cic
        if row["semantic_kind"] == "AMBIGUOUS" and row["semantic_review_decision"] == "UNREVIEWED"
    ]
    reviewed_n = sum(1 for row in cic if row["semantic_kind_source"] == "EXPLICIT_REVIEW_OVERRIDE")
    if len(cic) != 1722 or len(unreviewed) != 1672 or reviewed_n != 50:
        raise ValueError("CIC_W pool drift")
    if any(row["semantic_kind"] == "PROCESS" for row in unreviewed):
        raise ValueError("unreviewed CIC_W PROCESS != 0")
    batch001_keys = {row["seed_proposal_key"] for row in load_frozen_batch()}
    if any(row["seed_proposal_key"] in batch001_keys for row in unreviewed):
        raise ValueError("unreviewed pool overlaps Batch001")
    unrev_keys = {row["seed_proposal_key"] for row in unreviewed}
    proposal_by_src = {row["origin_source_key"]: row for row in cic}
    pool = []
    for node in a_nodes:
        proposal = proposal_by_src[node["source_key"]]
        if proposal["seed_proposal_key"] not in unrev_keys:
            continue
        pool.append(
            {
                "node": node,
                "proposal": proposal,
                "child_count": len(children.get(node["source_key"], [])),
                "root_source_key": root_of(node, by_key)["source_key"],
            }
        )
    if len(pool) != 1672:
        raise ValueError(f"unreviewed attached pool {len(pool)}")
    types_all = Counter(n["node_type"] for n in a_nodes)
    types_unrev = Counter(row["node"]["node_type"] for row in pool)
    return {
        "raw": raw,
        "gated": gated,
        "a_nodes": a_nodes,
        "by_key": by_key,
        "children": children,
        "pool": pool,
        "cic": cic,
        "batch001_keys": batch001_keys,
        "types_all": dict(types_all),
        "types_unrev": dict(types_unrev),
        "unique_roots_all": len({root_of(n, by_key)["source_key"] for n in a_nodes}),
        "unique_parents_all": len({n.get("parent_source_key") for n in a_nodes if n.get("parent_source_key")}),
        "max_depth": max(n["depth"] for n in a_nodes),
        "max_child_count": max((len(v) for v in children.values()), default=0),
    }


def build_review002(root: Path = DEFAULT_ROOT) -> dict:
    ctx = _pool_and_census(root)
    selected = select_batch002(ctx["pool"], ctx["by_key"], ctx["children"])
    keys = [row["proposal"]["seed_proposal_key"] for row in selected]
    if len(set(keys)) != 200:
        raise ValueError("Batch002 duplicate proposal keys")
    if set(keys) & ctx["batch001_keys"]:
        raise ValueError("Batch001 overlap")
    cic_by_name: dict[str, list[dict]] = defaultdict(list)
    for node in ctx["a_nodes"]:
        cic_by_name[node["name_normalized"]].append(node)
    other_by_name: dict[str, list[dict]] = defaultdict(list)
    for row in ctx["gated"]:
        if row["origin_source_id"] == SOURCE_CIC_W:
            continue
        other_by_name[row["proposed_name_normalized"]].append(row)
    manifest = {row["seed_proposal_key"]: row for row in build_gpt_manifest()}
    proposal_by_src = {row["origin_source_key"]: row for row in ctx["cic"]}
    reviewed = []
    for node in ctx["a_nodes"]:
        proposal = proposal_by_src[node["source_key"]]
        overlay = manifest.get(proposal["seed_proposal_key"])
        if overlay is None or overlay["source_id"] != SOURCE_CIC_W:
            continue
        reviewed.append(
            {
                "node": node,
                "batch_no": overlay["batch_no"],
                "semantic_kind": overlay["semantic_kind_override"],
                "decision": overlay["semantic_review_decision"],
                "root_source_key": root_of(node, ctx["by_key"])["source_key"],
            }
        )
    rows = [
        _enrich_row(
            BATCH_NO_START + i,
            item,
            by_key=ctx["by_key"],
            children=ctx["children"],
            cic_by_name=cic_by_name,
            other_by_name=other_by_name,
            reviewed=reviewed,
        )
        for i, item in enumerate(selected)
    ]
    if any(row["gpt_review_decision"] != "PENDING" for row in rows):
        raise ValueError("Cursor must not fill GPT decisions")
    if any(row["current_semantic_kind"] != "AMBIGUOUS" for row in rows):
        raise ValueError("Batch002 must remain AMBIGUOUS")
    digest = worksheet_sha(rows)
    types = Counter(row["source_node_type"] for row in rows)
    leaf_rows = [row for row in rows if row["source_node_type"] == "W_LEAF"]
    leaf_root = Counter(row["root_source_key"] for row in leaf_rows)
    leaf_parent = Counter(row["parent_source_key"] for row in leaf_rows)
    all_roots = {root_of(n, ctx["by_key"])["source_key"] for n in ctx["a_nodes"]}
    all_parents = {n.get("parent_source_key") for n in ctx["a_nodes"] if n.get("parent_source_key")}
    covered_roots = {row["root_source_key"] for row in rows}
    covered_parents = {row["parent_source_key"] for row in rows if row["parent_source_key"]}
    facts = {
        "CIC_W_total": 1722,
        "CIC_W_reviewed": 50,
        "CIC_W_unreviewed": 1672,
        "W_ROOT": ctx["types_all"].get("W_ROOT", 0),
        "W_MID": ctx["types_all"].get("W_MID", 0),
        "W_LEAF": ctx["types_all"].get("W_LEAF", 0),
        "unreviewed_W_ROOT": ctx["types_unrev"].get("W_ROOT", 0),
        "unreviewed_W_MID": ctx["types_unrev"].get("W_MID", 0),
        "unreviewed_W_LEAF": ctx["types_unrev"].get("W_LEAF", 0),
        "unique_roots_all": ctx["unique_roots_all"],
        "unique_parents_all": ctx["unique_parents_all"],
        "max_depth": ctx["max_depth"],
        "max_child_count": ctx["max_child_count"],
        "BATCH002": len(rows),
        "BATCH002_W_ROOT": types["W_ROOT"],
        "BATCH002_W_MID": types["W_MID"],
        "BATCH002_W_LEAF": types["W_LEAF"],
        "root_coverage_count": len(covered_roots),
        "root_coverage_pct": round(100.0 * len(covered_roots) / len(all_roots), 2),
        "parent_coverage_count": len(covered_parents),
        "parent_coverage_pct": round(100.0 * len(covered_parents) / len(all_parents), 2),
        "selected_leaf_parent_count": len({row["parent_source_key"] for row in leaf_rows}),
        "leaf_max_root_share": round(max(leaf_root.values()) / len(leaf_rows), 4) if leaf_rows else 0,
        "leaf_max_parent_share": round(max(leaf_parent.values()) / len(leaf_rows), 4) if leaf_rows else 0,
        "MAX_ROOT_SHARE": round(max(Counter(row["root_source_key"] for row in rows).values()) / len(rows), 4),
        "Batch001_overlap": 0,
        "duplicates": 0,
        "gpt_pending": 200,
        "CIC_W_unreviewed_PROCESS": 0,
    }
    return {
        "rows": rows,
        "sha": digest,
        "facts": facts,
        "pool": ctx["pool"],
        "source_plan": ctx["raw"]["source_plan"],
        "batch001_sha": FROZEN_BATCH_SHA,
    }


def worksheet_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *WORKSHEET_FIELDS)


def write_batch002(rows: list[dict], dest: Path = BATCH002_PATH) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(WORKSHEET_FIELDS), delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in WORKSHEET_FIELDS})


def write_local_census(pool: list[dict]) -> None:
    LOCAL_CENSUS.parent.mkdir(parents=True, exist_ok=True)
    with LOCAL_CENSUS.open("w", encoding="utf-8") as fh:
        for item in sorted(pool, key=lambda row: row["node"]["source_key"]):
            node = item["node"]
            fh.write(
                json.dumps(
                    {
                        "seed_proposal_key": item["proposal"]["seed_proposal_key"],
                        "source_key": node["source_key"],
                        "node_type": node["node_type"],
                        "name": node["name_normalized"],
                        "path": node["path_normalized"],
                        "depth": node["depth"],
                        "child_count": item["child_count"],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def load_batch002(path: Path = BATCH002_PATH) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main() -> None:
    pack = build_review002()
    write_batch002(pack["rows"])
    write_local_census(pack["pool"])
    slim = {
        "WO": "WO-RISK-04-REVIEW-002",
        "BATCH002_SHA": pack["sha"],
        "facts": pack["facts"],
        "KEEP_AS_DISTINCT": 0,
        "MERGE_CANDIDATE": 0,
        "HOLD": 0,
        "REJECT": 0,
        "CANONICAL_UUID_CREATED": 0,
        "AUTO_APPROVED": 0,
        "db_write": 0,
    }
    print(json.dumps(slim, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
