"""Batch 001 semantic-review evidence. Cursor does not decide KEEP/MERGE/HOLD/REJECT."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from tools.risk02.contract import SOURCE_CIC_W, SOURCE_KALIS, SOURCE_KOSHA
from tools.risk02.identity import sha256_parts
from tools.risk04.identity import parent_path
from tools.risk04.review_batch import BATCH_FIELDS, batch_sha
from tools.risk04.seed_review import DEFAULT_ROOT, build_seed_plan, universe_sha

FROZEN_BATCH_PATH = Path("docs/knowledge/risk/RISK04_BATCH001.tsv")
REVIEW_INPUT_PATH = Path("docs/knowledge/risk/RISK04_BATCH001_REVIEW_INPUT.tsv")
FROZEN_BATCH_SHA = "955b3c11f092b657b54d3d94f639270f767da4156c6a3710663deeeabbb4c4b8"
OWNER_PENDING = "PENDING"
OWNER_EMPTY = "EMPTY"
PATH_LIMIT = 10
CHILD_SAMPLE_LIMIT = 5
RISK_SAMPLE_LIMIT = 3
FLAG_SEP = "|"
CHILD_SEP = " | "
PATH_SEP = " | "

WORKSHEET_FIELDS = (
    "batch_no",
    "seed_proposal_key",
    "kind",
    "name",
    "source_id",
    "source_key",
    "source_path",
    "parent_path",
    "grandparent_path",
    "depth",
    "is_leaf",
    "child_count",
    "sample_children",
    "support_count",
    "risk_content_support",
    "source_occurrence_support",
    "same_name_count",
    "same_name_compatible_kind_count",
    "same_name_incompatible_kind_count",
    "same_name_paths",
    "risk_sample_1",
    "risk_sample_2",
    "risk_sample_3",
    "mechanical_flags",
    "generator_review_status",
    "generator_ambiguity_status",
    "owner_decision",
    "merge_candidate_keys",
    "owner_reason",
)


def _cell(value: object) -> str:
    return " ".join(str(value or "").replace("\t", " ").replace("\n", " ").split())


def grandparent_path(path_normalized: str) -> str:
    return parent_path(parent_path(path_normalized))


def load_frozen_batch(path: Path = FROZEN_BATCH_PATH) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            missing = [field for field in BATCH_FIELDS if field not in row]
            if missing:
                raise ValueError(f"frozen batch missing fields: {missing}")
            rows.append(
                {
                    "seed_proposal_key": row["seed_proposal_key"],
                    "kind": row["kind"],
                    "name": row["name"],
                    "source_id": row["source_id"],
                    "source_key": row["source_key"],
                    "source_path": row["source_path"],
                    "support_count": int(row["support_count"]),
                    "risk_content_support": int(row["risk_content_support"]),
                    "review_status": row["review_status"],
                    "ambiguity_status": row["ambiguity_status"],
                }
            )
    return rows


def assert_frozen_batch(rows: list[dict]) -> str:
    if len(rows) != 100:
        raise ValueError(f"frozen batch count {len(rows)} != 100")
    digest = batch_sha(rows)
    if digest != FROZEN_BATCH_SHA:
        raise ValueError("frozen Batch 001 SHA mismatch")
    keys = [row["seed_proposal_key"] for row in rows]
    if len(set(keys)) != 100:
        raise ValueError("frozen batch duplicate proposal keys")
    return digest


def _index_nodes(source_plan: dict) -> tuple[dict[tuple[str, str], dict], dict[tuple[str, str], list[dict]]]:
    plan = source_plan["_plan"]
    nodes = plan["a_nodes"] + plan["b_nodes"] + plan["c_nodes"]
    by_key = {(n["source_id"], n["source_key"]): n for n in nodes}
    children: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for node in nodes:
        parent = node.get("parent_source_key")
        if parent:
            children[(node["source_id"], parent)].append(node)
    for group in children.values():
        group.sort(key=lambda n: n["source_key"])
    return by_key, children


def _index_proposals(proposals: list[dict]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    by_key = {row["seed_proposal_key"]: row for row in proposals}
    by_name: dict[str, list[dict]] = defaultdict(list)
    for row in proposals:
        by_name[row["proposed_name_normalized"]].append(row)
    return by_key, by_name


def _risk_sample_text(rec: dict) -> str:
    obj = "/".join(part for part in (rec.get("hazard_object_big"), rec.get("hazard_object_mid")) if part)
    loc = "/".join(
        part
        for part in (
            rec.get("hazard_location_big"),
            rec.get("hazard_location_mid"),
            rec.get("hazard_location_small"),
        )
        if part
    )
    return _cell(
        f"객체={obj}; 위치={loc}; 원인={rec.get('cause')}; "
        f"인적={rec.get('human_damage')}; 물적={rec.get('property_damage')}; "
        f"가능={rec.get('likelihood')}; 심각={rec.get('severity')}"
    )


def _risk_samples(
    source_key: str,
    records: list[dict],
    occurrence_counts: dict[str, int],
) -> list[str]:
    matched = [rec for rec in records if rec["task_source_key"] == source_key]
    matched.sort(
        key=lambda rec: (-int(occurrence_counts.get(rec["content_key"], 1)), rec["content_key"])
    )
    texts = [_risk_sample_text(rec) for rec in matched[:RISK_SAMPLE_LIMIT]]
    while len(texts) < RISK_SAMPLE_LIMIT:
        texts.append("")
    return texts


def _flags(
    *,
    child_count: int,
    same_name_rows: list[dict],
    kind: str,
    source_id: str,
    risk_content_support: int,
) -> str:
    flags = []
    if child_count > 0:
        flags.append("HAS_CHILDREN")
    if child_count == 0:
        flags.append("IS_LEAF")
    compatible = [row for row in same_name_rows if row["proposed_node_kind"] == kind]
    parents = {row["source_parent_path"] for row in compatible}
    if len(parents) > 1:
        flags.append("SAME_NAME_MULTI_PARENT")
    sources = {row["origin_source_id"] for row in same_name_rows}
    if any(src != source_id for src in sources):
        flags.append("CROSS_SOURCE_SAME_NAME")
    if any(row["proposed_node_kind"] != kind for row in same_name_rows):
        flags.append("INCOMPATIBLE_KIND")
    if risk_content_support > 0:
        flags.append("HIGH_RISK_SUPPORT")
    if source_id == SOURCE_KOSHA:
        flags.append("B_IDENTITY_HOLD")
    return FLAG_SEP.join(flags)


def enrich_batch_row(
    batch_no: int,
    batch_row: dict,
    *,
    by_proposal: dict[str, dict],
    by_name: dict[str, list[dict]],
    by_node: dict[tuple[str, str], dict],
    children: dict[tuple[str, str], list[dict]],
    c_records: list[dict],
    occurrence_counts: dict[str, int],
) -> dict:
    key = batch_row["seed_proposal_key"]
    proposal = by_proposal.get(key)
    if proposal is None:
        raise ValueError(f"proposal missing for batch key {key}")
    node = by_node.get((batch_row["source_id"], batch_row["source_key"]))
    if node is None:
        raise ValueError(f"source node missing for {batch_row['source_id']}:{batch_row['source_key']}")
    kids = children.get((batch_row["source_id"], batch_row["source_key"]), [])
    child_count = len(kids)
    sample = [n["name_normalized"] for n in kids[:CHILD_SAMPLE_LIMIT]]
    same_name_rows = by_name[proposal["proposed_name_normalized"]]
    compatible = [row for row in same_name_rows if row["proposed_node_kind"] == proposal["proposed_node_kind"]]
    incompatible = [row for row in same_name_rows if row["proposed_node_kind"] != proposal["proposed_node_kind"]]
    path_rows = sorted(
        same_name_rows,
        key=lambda row: (row["origin_source_id"], row["source_path"], row["seed_proposal_key"]),
    )
    path_labels = []
    seen_paths: set[tuple[str, str]] = set()
    for row in path_rows:
        label = (row["origin_source_id"], row["source_path"])
        if label in seen_paths:
            continue
        seen_paths.add(label)
        path_labels.append(f"{row['origin_source_id']}:{row['source_path']}")
        if len(path_labels) >= PATH_LIMIT:
            break
    samples = ["", "", ""]
    if batch_row["source_id"] == SOURCE_KALIS:
        samples = _risk_samples(batch_row["source_key"], c_records, occurrence_counts)
    parent = proposal["source_parent_path"]
    return {
        "batch_no": str(batch_no),
        "seed_proposal_key": key,
        "kind": batch_row["kind"],
        "name": batch_row["name"],
        "source_id": batch_row["source_id"],
        "source_key": batch_row["source_key"],
        "source_path": batch_row["source_path"],
        "parent_path": parent,
        "grandparent_path": grandparent_path(batch_row["source_path"]),
        "depth": str(int(node["depth"])),
        "is_leaf": "YES" if child_count == 0 else "NO",
        "child_count": str(child_count),
        "sample_children": CHILD_SEP.join(sample),
        "support_count": str(proposal["support_count"]),
        "risk_content_support": str(proposal["risk_content_support"]),
        "source_occurrence_support": str(proposal["source_occurrence_support"]),
        "same_name_count": str(len(same_name_rows)),
        "same_name_compatible_kind_count": str(len(compatible)),
        "same_name_incompatible_kind_count": str(len(incompatible)),
        "same_name_paths": PATH_SEP.join(path_labels),
        "risk_sample_1": samples[0],
        "risk_sample_2": samples[1],
        "risk_sample_3": samples[2],
        "mechanical_flags": _flags(
            child_count=child_count,
            same_name_rows=same_name_rows,
            kind=proposal["proposed_node_kind"],
            source_id=batch_row["source_id"],
            risk_content_support=int(proposal["risk_content_support"]),
        ),
        "generator_review_status": batch_row["review_status"],
        "generator_ambiguity_status": batch_row["ambiguity_status"],
        "owner_decision": OWNER_PENDING,
        "merge_candidate_keys": OWNER_EMPTY,
        "owner_reason": OWNER_EMPTY,
    }


def build_review_input(root: Path = DEFAULT_ROOT, batch_path: Path = FROZEN_BATCH_PATH) -> dict:
    frozen = load_frozen_batch(batch_path)
    frozen_sha = assert_frozen_batch(frozen)
    seed = build_seed_plan(root)
    by_proposal, by_name = _index_proposals(seed["proposals"])
    by_node, children = _index_nodes(seed["source_plan"])
    frozen_keys = [row["seed_proposal_key"] for row in frozen]
    universe_keys = set(by_proposal)
    missing = [key for key in frozen_keys if key not in universe_keys]
    extra = 0
    if missing:
        raise ValueError(f"frozen keys missing from universe: {len(missing)}")
    rows = []
    for i, batch_row in enumerate(frozen, start=1):
        rows.append(
            enrich_batch_row(
                i,
                batch_row,
                by_proposal=by_proposal,
                by_name=by_name,
                by_node=by_node,
                children=children,
                c_records=seed["source_plan"]["_plan"]["c_records"],
                occurrence_counts=seed["source_plan"]["_plan"]["c_occurrence_counts"],
            )
        )
    if any(row["owner_decision"] != OWNER_PENDING for row in rows):
        raise ValueError("Cursor must not fill owner_decision")
    if any(row["kind"] not in {"PROCESS", "TASK"} for row in rows):
        raise ValueError("unexpected proposal kind")
    digest = review_input_sha(rows)
    return {
        "rows": rows,
        "frozen_sha": frozen_sha,
        "review_input_sha": digest,
        "missing": len(missing),
        "extra": extra,
        "duplicate": 0,
        "facts": summarize_facts(rows, seed),
        "source_plan": seed["source_plan"],
        "metrics": seed["metrics"],
    }


def review_input_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *WORKSHEET_FIELDS)


def summarize_facts(rows: list[dict], seed: dict) -> dict:
    process = [row for row in rows if row["kind"] == "PROCESS"]
    task = [row for row in rows if row["kind"] == "TASK"]
    cic = [row for row in rows if row["source_id"] == SOURCE_CIC_W]
    kalis = [row for row in rows if row["source_id"] == SOURCE_KALIS]
    kosha = [row for row in rows if row["source_id"] == SOURCE_KOSHA]
    process_leaf = sum(1 for row in process if row["is_leaf"] == "YES")
    names = defaultdict(list)
    for row in rows:
        names[row["name"]].append(row)
    same_name_groups = sum(1 for group in names.values() if len(group) > 1)
    multi_parent = sum(1 for row in rows if "SAME_NAME_MULTI_PARENT" in row["mechanical_flags"].split(FLAG_SEP))
    compat_groups = 0
    incompat_groups = 0
    for name, group in names.items():
        kinds = {row["kind"] for row in group}
        if len(group) > 1 and len(kinds) == 1:
            compat_groups += 1
        if len(kinds) > 1:
            incompat_groups += 1
    risk_vals = [int(row["risk_content_support"]) for row in kalis]
    risk_vals.sort()
    universe_by_name: dict[str, list[dict]] = defaultdict(list)
    for proposal in seed["proposals"]:
        universe_by_name[proposal["proposed_name_normalized"]].append(proposal)
    universe_incompat = 0
    universe_compat_multi = 0
    universe_multi_parent = 0
    for group in universe_by_name.values():
        kinds = {row["proposed_node_kind"] for row in group}
        if len(kinds) > 1:
            universe_incompat += 1
        kind_groups: dict[str, list[dict]] = defaultdict(list)
        for row in group:
            kind_groups[row["proposed_node_kind"]].append(row)
        for peers in kind_groups.values():
            if len(peers) > 1:
                universe_compat_multi += 1
            if len({row["source_parent_path"] for row in peers}) > 1:
                universe_multi_parent += 1
    cic_depths = Counter(row["depth"] for row in cic)
    a_by_key = {n["source_key"]: n for n in seed["source_plan"]["_plan"]["a_nodes"]}
    node_types = [a_by_key[row["source_key"]]["node_type"] for row in cic]
    return {
        "batch_count": len(rows),
        "process": len(process),
        "task": len(task),
        "cic_w": len(cic),
        "kalis": len(kalis),
        "kosha": len(kosha),
        "process_leaf": process_leaf,
        "process_non_leaf": len(process) - process_leaf,
        "task_same_name_multi_parent": sum(
            1 for row in task if "SAME_NAME_MULTI_PARENT" in row["mechanical_flags"].split(FLAG_SEP)
        ),
        "same_name_groups": same_name_groups,
        "same_name_multi_parent_rows": multi_parent,
        "compatible_kind_same_name_groups": compat_groups,
        "incompatible_kind_same_name_groups": incompat_groups,
        "owner_pending": sum(1 for row in rows if row["owner_decision"] == OWNER_PENDING),
        "keep_as_distinct": 0,
        "merge_candidate": 0,
        "hold": 0,
        "reject": 0,
        "cic_w_node_types": dict(Counter(node_types)),
        "cic_w_depths": dict(cic_depths),
        "kalis_risk_min": risk_vals[0] if risk_vals else 0,
        "kalis_risk_max": risk_vals[-1] if risk_vals else 0,
        "kalis_risk_median": risk_vals[len(risk_vals) // 2] if risk_vals else 0,
        "universe_incompatible_kind_name_groups": universe_incompat,
        "universe_compatible_kind_multi_name_groups": universe_compat_multi,
        "universe_compatible_kind_multi_parent_groups": universe_multi_parent,
        "seed_universe_total": seed["metrics"]["total"],
        "systemic_kind_rule_issue": "PENDING GPT",
    }


def write_review_input(rows: list[dict], dest: Path = REVIEW_INPUT_PATH) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(WORKSHEET_FIELDS), delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in WORKSHEET_FIELDS})


def load_review_input(path: Path = REVIEW_INPUT_PATH) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main() -> None:
    pack = build_review_input()
    write_review_input(pack["rows"])
    slim = {
        "WO": "WO-RISK-04-REVIEW-001",
        "FROZEN_BATCH_SHA": pack["frozen_sha"],
        "REVIEW_INPUT_SHA": pack["review_input_sha"],
        "missing": pack["missing"],
        "extra": pack["extra"],
        "duplicate": pack["duplicate"],
        "facts": pack["facts"],
        "owner_decision_pending": 100,
        "KEEP_AS_DISTINCT": 0,
        "MERGE_CANDIDATE": 0,
        "HOLD": 0,
        "REJECT": 0,
        "SYSTEMIC_KIND_RULE_ISSUE": "PENDING GPT",
        "CANONICAL_UUID_CREATED": 0,
        "AUTO_APPROVED": 0,
        "db_write": 0,
    }
    print(json.dumps(slim, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
