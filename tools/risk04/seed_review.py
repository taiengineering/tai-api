"""Deterministic canonical seed-proposal universe. No language-model or vector similarity."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from tools.risk02.contract import SOURCE_CIC_W, SOURCE_KALIS, SOURCE_KOSHA
from tools.risk02.identity import sha256_parts
from tools.risk02.plan_source_core import build_plan
from tools.risk03.candidates import mapping_nodes_for_source
from tools.risk03.contract import B_IDENTITY
from tools.risk04.contract import PROPOSED_ORIGIN_TYPE, SECTOR_HINT
from tools.risk04.identity import parent_path, proposed_kind, seed_proposal_key

DEFAULT_ROOT = Path("artifacts/risk01")
FORBIDDEN_REVIEW = {"ACTIVE", "APPROVED"}


def _task_support(c_records: list[dict], occurrence_counts: dict[str, int]) -> tuple[Counter[str], Counter[str]]:
    content: Counter[str] = Counter()
    occ: Counter[str] = Counter()
    for rec in c_records:
        key = rec["task_source_key"]
        content[key] += 1
        occ[key] += int(occurrence_counts.get(rec["content_key"], 1))
    return content, occ


def _indexes(nodes: list[dict]) -> tuple[dict[tuple[str, str], list[dict]], dict[tuple[str, str], list[dict]]]:
    by_name: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_path: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for node in nodes:
        kind = proposed_kind(node)
        by_name[(node["name_normalized"], kind)].append(node)
        by_path[(node["path_normalized"], kind)].append(node)
    return by_name, by_path


def build_seed_proposals(
    eligible: list[dict],
    *,
    b_leaf_occ: dict[str, int] | None = None,
    c_records: list[dict] | None = None,
    occurrence_counts: dict[str, int] | None = None,
) -> list[dict]:
    b_leaf_occ = b_leaf_occ or {}
    content_by_task, occ_by_task = _task_support(c_records or [], occurrence_counts or {})
    by_name, by_path = _indexes(eligible)
    rows = []
    for node in eligible:
        kind = proposed_kind(node)
        name = node["name_normalized"]
        path = node["path_normalized"]
        parent = parent_path(path)
        name_peers = by_name[(name, kind)]
        path_peers = by_path[(path, kind)]
        other_sources_name = {n["source_id"] for n in name_peers if n["source_id"] != node["source_id"]}
        other_sources_path = {n["source_id"] for n in path_peers if n["source_id"] != node["source_id"]}
        incompatible = any(
            parent_path(peer["path_normalized"]) != parent
            for peer in name_peers
            if peer["source_key"] != node["source_key"] or peer["source_id"] != node["source_id"]
        )
        if node["source_id"] == SOURCE_KOSHA:
            occurrence = int(b_leaf_occ.get(node["source_key"], 1))
            risk_content = 0
            risk_occ = 0
        elif node["source_id"] == SOURCE_KALIS:
            occurrence = int(occ_by_task.get(node["source_key"], 0))
            risk_content = int(content_by_task.get(node["source_key"], 0))
            risk_occ = occurrence
        else:
            occurrence = 1
            risk_content = 0
            risk_occ = 0
        supporting = sorted(
            {
                f"{peer['source_id']}:{peer['source_key']}"
                for peer in name_peers
                if not (peer["source_id"] == node["source_id"] and peer["source_key"] == node["source_key"])
            }
        )
        merge_review = bool(other_sources_name)
        hold = incompatible
        review_status = "HOLD" if hold else "REVIEW_READY"
        if review_status in FORBIDDEN_REVIEW:
            raise ValueError("generator emitted forbidden status")
        rows.append(
            {
                "seed_proposal_key": seed_proposal_key(node["source_id"], node["source_key"], kind),
                "proposed_node_kind": kind,
                "proposed_name": node["name_raw"],
                "proposed_name_normalized": name,
                "origin_source_id": node["source_id"],
                "origin_source_key": node["source_key"],
                "source_path": path,
                "source_parent_path": parent,
                "proposed_origin_type": PROPOSED_ORIGIN_TYPE,
                "sector_hint": SECTOR_HINT,
                "supporting_source_refs": supporting,
                "support_count": len(other_sources_name) + 1,
                "exact_name_support_count": len(other_sources_name),
                "exact_path_support_count": len(other_sources_path),
                "risk_content_support": risk_content,
                "source_occurrence_support": occurrence,
                "risk_occurrence_count": risk_occ,
                "review_status": review_status,
                "review_reason": (
                    "same normalized name with incompatible parent context"
                    if hold
                    else "deterministic source promotion candidate; not approved"
                ),
                "ambiguity_status": "HOLD" if hold else "NONE",
                "merge_review_required": merge_review,
                "canonical_uuid": None,
                "b_identity": B_IDENTITY if node["source_id"] == SOURCE_KOSHA else None,
                "metadata": {
                    "source_node_type": node["node_type"],
                    "priority_score_is_not_approval": True,
                    "auto_merged": False,
                },
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -row["exact_path_support_count"],
            -row["exact_name_support_count"],
            -row["risk_content_support"],
            -row["source_occurrence_support"],
            row["proposed_node_kind"],
            row["proposed_name_normalized"],
            row["origin_source_id"],
            row["origin_source_key"],
        ),
    )


def build_mapping_candidates(proposals: list[dict]) -> list[dict]:
    by_key = {(row["origin_source_id"], row["origin_source_key"]): row for row in proposals}
    rows = []
    for proposal in proposals:
        key = (proposal["origin_source_id"], proposal["origin_source_key"])
        target = by_key.get(key)
        if target is None:
            rows.append(
                {
                    "source_id": proposal["origin_source_id"],
                    "source_key": proposal["origin_source_key"],
                    "target_seed_proposal_key": None,
                    "recommended_mapping_type": "NO_MATCH",
                    "recommended_mapping_method": "MANUAL_REVIEW",
                    "review_status": "HOLD",
                    "evidence": {"reason": "no seed proposal for source node"},
                }
            )
            continue
        rows.append(
            {
                "source_id": proposal["origin_source_id"],
                "source_key": proposal["origin_source_key"],
                "target_seed_proposal_key": target["seed_proposal_key"],
                "recommended_mapping_type": "POSSIBLE_RELATED",
                "recommended_mapping_method": "EXACT_PATH" if target["exact_path_support_count"] else "EXACT_NAME",
                "review_status": target["review_status"],
                "evidence": {
                    "source_path": target["source_path"],
                    "seed_proposal_key": target["seed_proposal_key"],
                    "not_canonical_id": True,
                    "auto_exact_equivalent": False,
                    "auto_approved": False,
                },
            }
        )
    return sorted(rows, key=lambda row: (row["source_id"], row["source_key"]))


def eligible_nodes(source_plan: dict) -> tuple[list[dict], list[dict], list[dict]]:
    a_nodes = mapping_nodes_for_source(SOURCE_CIC_W, source_plan["_plan"]["a_nodes"])
    b_nodes = mapping_nodes_for_source(SOURCE_KOSHA, source_plan["_plan"]["b_nodes"])
    c_nodes = mapping_nodes_for_source(SOURCE_KALIS, source_plan["_plan"]["c_nodes"])
    return a_nodes, b_nodes, c_nodes


def summarize_proposals(proposals: list[dict]) -> dict:
    kinds = Counter(row["proposed_node_kind"] for row in proposals)
    origins = Counter(row["origin_source_id"] for row in proposals)
    return {
        "total": len(proposals),
        "process": kinds["PROCESS"],
        "task": kinds["TASK"],
        "A_origin": origins[SOURCE_CIC_W],
        "B_origin": origins[SOURCE_KOSHA],
        "C_origin": origins[SOURCE_KALIS],
        "multi_source_supported": sum(1 for row in proposals if row["exact_name_support_count"] > 0),
        "ambiguous": sum(1 for row in proposals if row["ambiguity_status"] == "HOLD"),
        "hold": sum(1 for row in proposals if row["review_status"] == "HOLD"),
        "review_ready": sum(1 for row in proposals if row["review_status"] == "REVIEW_READY"),
        "auto_merged": 0,
        "canonical_uuid_created": 0,
        "active_canonicals": 0,
        "approved": sum(1 for row in proposals if row["review_status"] in FORBIDDEN_REVIEW),
    }


def universe_sha(rows: list[dict], *fields: str) -> str:
    payload = [{k: row[k] for k in fields} for row in rows]
    return sha256_parts(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def build_seed_plan(root: Path = DEFAULT_ROOT) -> dict:
    source_plan = build_plan(root)
    a_nodes, b_nodes, c_nodes = eligible_nodes(source_plan)
    eligible = a_nodes + b_nodes + c_nodes
    leaf_keys = {n["source_key"] for n in b_nodes}
    b_leaf_occ = {
        m["member_key"]: m["occurrence_count"]
        for m in source_plan["_plan"]["membership"]
        if m["source_id"] == SOURCE_KOSHA
        and m["member_kind"] == "NODE"
        and m["member_key"] in leaf_keys
    }
    proposals = build_seed_proposals(
        eligible,
        b_leaf_occ=b_leaf_occ,
        c_records=source_plan["_plan"]["c_records"],
        occurrence_counts=source_plan["_plan"]["c_occurrence_counts"],
    )
    mappings = build_mapping_candidates(proposals)
    metrics = summarize_proposals(proposals)
    no_match = sum(1 for row in mappings if row["recommended_mapping_type"] == "NO_MATCH")
    seed_sha = universe_sha(
        proposals,
        "seed_proposal_key",
        "proposed_node_kind",
        "origin_source_id",
        "origin_source_key",
        "review_status",
    )
    mapping_sha = universe_sha(
        mappings,
        "source_id",
        "source_key",
        "target_seed_proposal_key",
        "recommended_mapping_type",
        "review_status",
    )
    return {
        "proposals": proposals,
        "mappings": mappings,
        "metrics": metrics,
        "no_match_candidates": no_match,
        "pending_mapping_candidates": len(mappings),
        "seed_universe_sha": seed_sha,
        "mapping_review_sha": mapping_sha,
        "source_plan": source_plan,
        "eligible": {"A": a_nodes, "B": b_nodes, "C": c_nodes},
    }


def no_match_candidate(source_id: str, source_key: str) -> dict:
    return {
        "source_id": source_id,
        "source_key": source_key,
        "target_seed_proposal_key": None,
        "recommended_mapping_type": "NO_MATCH",
        "recommended_mapping_method": "MANUAL_REVIEW",
        "review_status": "HOLD",
        "evidence": {"reason": "no seed proposal for source node", "canonical_id": None},
    }


def build_report(root: Path = DEFAULT_ROOT) -> dict:
    from tools.risk04.ingest_readiness import readiness_sha, source_ingest_readiness
    from tools.risk04.review_batch import batch_rows, batch_sha, select_batch

    seed = build_seed_plan(root)
    batch = select_batch(seed["proposals"])
    batch_view = batch_rows(batch)
    readiness = source_ingest_readiness(seed["source_plan"])
    forbidden = any(row["review_status"] in FORBIDDEN_REVIEW for row in seed["proposals"])
    if forbidden or any(row.get("canonical_uuid") for row in seed["proposals"]):
        raise ValueError("seed review emitted APPROVED/ACTIVE or canonical UUID")
    summary = {
        "WO": "WO-RISK-04",
        "NEW_MIGRATION": 0,
        "PHYSICAL_MODEL_DECISION": "NEW_RISK_CANONICAL",
        "MODEL_D": "APPROVED / FROZEN",
        "SEED_PROPOSAL_IDENTITY": "DETERMINISTIC",
        "CANONICAL_UUID_CREATED": 0,
        "AUTO_APPROVED": 0,
        "ACTIVE_CANONICALS": 0,
        "APPROVED_DB_MAPPINGS": 0,
        "AUTO_MERGED": 0,
        "A": {
            "source_nodes": len(seed["eligible"]["A"]),
            "origin_proposals": seed["metrics"]["A_origin"],
        },
        "B": {
            "raw_rows": seed["source_plan"]["B"]["rows"],
            "proposal_nodes": len(seed["eligible"]["B"]),
            "identity": seed["source_plan"]["B"]["identity"],
            "occurrence_sum": seed["source_plan"]["B"]["leaf_occurrence_sum"],
            "origin_proposals": seed["metrics"]["B_origin"],
        },
        "C": {
            "task_nodes": len(seed["eligible"]["C"]),
            "unique_content": seed["source_plan"]["C"]["unique_content"],
            "occurrence_sum": seed["source_plan"]["C"]["occurrence_sum"],
            "origin_proposals": seed["metrics"]["C_origin"],
        },
        "SEED_UNIVERSE": seed["metrics"],
        "REVIEW_BATCH_001": {
            "count": len(batch_view),
            "process": sum(1 for row in batch_view if row["kind"] == "PROCESS"),
            "task": sum(1 for row in batch_view if row["kind"] == "TASK"),
            "hold": sum(1 for row in batch_view if row["review_status"] == "HOLD"),
            "review_ready": sum(1 for row in batch_view if row["review_status"] == "REVIEW_READY"),
            "sha256": batch_sha(batch_view),
        },
        "PENDING_MAPPING_CANDIDATES": seed["pending_mapping_candidates"],
        "NO_MATCH_CANDIDATES": seed["no_match_candidates"],
        "SOURCE_INGEST": readiness["status"],
        "source_node_orphan": readiness["source_node_orphan"],
        "snapshot_orphan": readiness["snapshot_orphan"],
        "membership_orphan": readiness["membership_orphan"],
        "C_task_orphan": readiness["C_task_orphan"],
        "CANONICAL_INGEST": "NOT AUTHORIZED",
        "MAPPING_INGEST": "NOT AUTHORIZED",
        "MIGRATION_APPLY": 0,
        "SEED_UNIVERSE_SHA": seed["seed_universe_sha"],
        "MAPPING_REVIEW_SHA": seed["mapping_review_sha"],
        "READINESS_SHA": readiness_sha(readiness),
        "LLM": 0,
        "vector_similarity": 0,
        "string_auto_map": 0,
        "customer_data_used": 0,
        "db_write": 0,
        "OWNER_REVIEW": "REQUIRED",
        "RECOMMENDATION": "REVIEW_READY" if readiness["status"] != "NOT_READY" else "BLOCKED",
    }
    summary["_plan"] = {"proposals": seed["proposals"], "mappings": seed["mappings"], "batch": batch_view}
    return summary


def write_local_artifacts(summary: dict) -> None:
    from tools.risk04.review_batch import write_batch_tsv

    root = Path("artifacts/risk04")
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in summary.items() if k != "_plan"}
    reports.joinpath("summary.json").write_text(
        json.dumps(slim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (root / "seed_universe.jsonl").open("w", encoding="utf-8") as fh:
        for row in summary["_plan"]["proposals"]:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (root / "mapping_review_universe.jsonl").open("w", encoding="utf-8") as fh:
        for row in summary["_plan"]["mappings"]:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_batch_tsv(summary["_plan"]["batch"], root / "REVIEW_BATCH_001.tsv")


def main() -> None:
    summary = build_report(DEFAULT_ROOT)
    write_local_artifacts(summary)
    dest = Path("docs/knowledge/risk/RISK04_BATCH001.tsv")
    from tools.risk04.review_batch import write_batch_tsv

    write_batch_tsv(summary["_plan"]["batch"], dest)
    slim = {k: v for k, v in summary.items() if k != "_plan"}
    print(json.dumps(slim, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
