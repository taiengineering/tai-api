"""Pre-canonical semantic-kind gate. Not DB node_kind and not approval."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools.risk02.contract import SOURCE_CIC_W, SOURCE_KALIS, SOURCE_KOSHA
from tools.risk04.review_decisions import (
    APPROVAL_STATE,
    CANONICAL_SEMANTIC_KINDS,
    CHG1_RESULT_FIELDS,
    CHG1_RESULT_PATH,
    GPT_MANIFEST_FIELDS,
    GPT_MANIFEST_PATH,
    SEMANTIC_KINDS,
    build_gpt_manifest,
    manifest_sha,
    seed_state_for,
    write_tsv,
)
from tools.risk04.seed_review import DEFAULT_ROOT, build_raw_seed_plan, universe_sha

UNRESOLVED = "UNRESOLVED"
SEMANTIC_KIND_SOURCE_OVERRIDE = "EXPLICIT_REVIEW_OVERRIDE"
SEMANTIC_KIND_SOURCE_DEFAULT = "DEFAULT_UNREVIEWED"


def default_semantic(proposal: dict) -> tuple[str, str, str, str]:
    """semantic_kind, semantic_kind_source, seed_candidate_state, semantic_review_decision."""
    source = proposal["origin_source_id"]
    if source == SOURCE_CIC_W:
        return "AMBIGUOUS", SEMANTIC_KIND_SOURCE_DEFAULT, "PENDING_SEMANTIC_REVIEW", "UNREVIEWED"
    if source in {SOURCE_KALIS, SOURCE_KOSHA}:
        return "TASK", "SOURCE_NODE_KIND", "CANDIDATE", "UNREVIEWED"
    raise ValueError(f"unknown source {source}")


def apply_semantic_gate(proposals: list[dict], manifest: list[dict] | None = None) -> list[dict]:
    manifest = manifest if manifest is not None else build_gpt_manifest()
    by_key = {row["seed_proposal_key"]: row for row in manifest}
    out = []
    for proposal in proposals:
        kind, source, state, decision = default_semantic(proposal)
        overlay = by_key.get(proposal["seed_proposal_key"])
        partner = "EMPTY"
        if overlay:
            kind = overlay["semantic_kind_override"]
            source = SEMANTIC_KIND_SOURCE_OVERRIDE
            decision = overlay["semantic_review_decision"]
            state = seed_state_for(decision, kind)
            partner = overlay["merge_partner_batch"]
        if kind not in SEMANTIC_KINDS:
            raise ValueError(f"invalid semantic_kind {kind}")
        if proposal["origin_source_id"] == SOURCE_CIC_W and overlay is None and kind == "PROCESS":
            raise ValueError("unreviewed CIC_W must not default PROCESS")
        row = dict(proposal)
        row["semantic_kind"] = kind
        row["semantic_kind_source"] = source
        row["seed_candidate_state"] = state
        row["semantic_review_decision"] = decision
        row["merge_partner_batch"] = partner
        row["approval_state"] = APPROVAL_STATE
        row["kind_before"] = proposal["proposed_node_kind"]
        out.append(row)
    return out


def mapping_for_gated(proposal: dict) -> dict:
    canonical_ok = (
        proposal["semantic_kind"] in CANONICAL_SEMANTIC_KINDS
        and proposal["seed_candidate_state"] == "CANDIDATE"
    )
    if canonical_ok:
        return {
            "source_id": proposal["origin_source_id"],
            "source_key": proposal["origin_source_key"],
            "target_seed_proposal_key": proposal["seed_proposal_key"],
            "recommended_mapping_type": "POSSIBLE_RELATED",
            "recommended_mapping_method": "EXACT_PATH" if proposal["exact_path_support_count"] else "EXACT_NAME",
            "review_status": "REVIEW_READY",
            "mapping_approval_blocked": True,
            "evidence": {
                "seed_proposal_key": proposal["seed_proposal_key"],
                "not_canonical_id": True,
                "auto_approved": False,
                "semantic_kind": proposal["semantic_kind"],
                "seed_candidate_state": proposal["seed_candidate_state"],
            },
        }
    mapping_type = UNRESOLVED
    if proposal["semantic_kind"] == "AMBIGUOUS":
        reason = "semantic review pending; AMBIGUOUS is not NO_MATCH"
    elif proposal["seed_candidate_state"] == "MERGE_REVIEW":
        reason = "MERGE_CANDIDATE pair unresolved; mapping approval blocked"
    elif proposal["seed_candidate_state"] == "REJECTED":
        reason = "semantic REJECT; not a canonical mapping target"
    elif proposal["seed_candidate_state"] == "HOLD":
        reason = "semantic HOLD; mapping approval blocked"
    else:
        reason = "non-canonical semantic kind cannot be a seed target"
    return {
        "source_id": proposal["origin_source_id"],
        "source_key": proposal["origin_source_key"],
        "target_seed_proposal_key": None,
        "recommended_mapping_type": mapping_type,
        "recommended_mapping_method": "MANUAL_REVIEW",
        "review_status": "HOLD",
        "mapping_approval_blocked": True,
        "evidence": {
            "reason": reason,
            "not_no_match": proposal["semantic_kind"] == "AMBIGUOUS",
            "semantic_kind": proposal["semantic_kind"],
            "seed_candidate_state": proposal["seed_candidate_state"],
            "auto_approved": False,
        },
    }


def build_gated_mappings(proposals: list[dict]) -> list[dict]:
    rows = [mapping_for_gated(row) for row in proposals]
    if any(row.get("review_status") == "APPROVED" for row in rows):
        raise ValueError("mapping APPROVED is forbidden")
    non_canonical = [row for row in proposals if row["semantic_kind"] not in CANONICAL_SEMANTIC_KINDS]
    for proposal, mapping in zip(proposals, rows):
        if proposal["semantic_kind"] not in CANONICAL_SEMANTIC_KINDS:
            if mapping["target_seed_proposal_key"] is not None:
                raise ValueError("non-canonical kind used as mapping target")
            if mapping["recommended_mapping_type"] == "POSSIBLE_RELATED":
                raise ValueError("POSSIBLE_RELATED to non-canonical self target")
            if mapping["recommended_mapping_type"] == "NO_MATCH" and proposal["semantic_kind"] == "AMBIGUOUS":
                raise ValueError("AMBIGUOUS must not become NO_MATCH")
    del non_canonical
    return sorted(rows, key=lambda row: (row["source_id"], row["source_key"]))


def semantic_distribution(proposals: list[dict]) -> dict:
    kinds = Counter(row["semantic_kind"] for row in proposals)
    cic = [row for row in proposals if row["origin_source_id"] == SOURCE_CIC_W]
    cic_reviewed = [row for row in cic if row["semantic_kind_source"] == SEMANTIC_KIND_SOURCE_OVERRIDE]
    cic_unreviewed = [row for row in cic if row["semantic_kind_source"] != SEMANTIC_KIND_SOURCE_OVERRIDE]
    kalis = [row for row in proposals if row["origin_source_id"] == SOURCE_KALIS]
    kalis_auto_hold = sum(
        1
        for row in kalis
        if row["review_status"] == "HOLD"
        and row["semantic_review_decision"] == "UNREVIEWED"
        and row["metadata"].get("same_name_multi_parent")
    )
    return {
        "source_proposal_universe": len(proposals),
        "semantic_kind": dict(kinds),
        "semantic_PROCESS": kinds["PROCESS"],
        "semantic_TASK": kinds["TASK"],
        "semantic_AMBIGUOUS": kinds["AMBIGUOUS"],
        "semantic_NON_CANONICAL": sum(
            kinds[k] for k in kinds if k not in CANONICAL_SEMANTIC_KINDS
        ),
        "CIC_W": len(cic),
        "CIC_W_reviewed": len(cic_reviewed),
        "CIC_W_unreviewed": len(cic_unreviewed),
        "CIC_W_unreviewed_PROCESS": sum(1 for row in cic_unreviewed if row["semantic_kind"] == "PROCESS"),
        "CIC_W_unreviewed_AMBIGUOUS": sum(1 for row in cic_unreviewed if row["semantic_kind"] == "AMBIGUOUS"),
        "CIC_W_reviewed_PROCESS": sum(1 for row in cic_reviewed if row["semantic_kind"] == "PROCESS"),
        "CIC_W_reviewed_AMBIGUOUS": sum(1 for row in cic_reviewed if row["semantic_kind"] == "AMBIGUOUS"),
        "CIC_W_reviewed_MATERIAL_COMPONENT": sum(
            1 for row in cic_reviewed if row["semantic_kind"] == "MATERIAL_COMPONENT"
        ),
        "CIC_W_reviewed_FACILITY_EQUIPMENT": sum(
            1 for row in cic_reviewed if row["semantic_kind"] == "FACILITY_EQUIPMENT"
        ),
        "CIC_W_reviewed_CLASSIFICATION": sum(
            1 for row in cic_reviewed if row["semantic_kind"] == "CLASSIFICATION"
        ),
        "KALIS": len(kalis),
        "KALIS_same_name_multi_parent_auto_HOLD": kalis_auto_hold,
        "OWNER_APPROVED_SEEDS": 0,
        "CANONICAL_UUID_CREATED": 0,
        "AUTO_APPROVED": 0,
        "AUTO_MERGED": 0,
    }


def chg1_result_rows(gated: list[dict], manifest: list[dict]) -> list[dict]:
    by_key = {row["seed_proposal_key"]: row for row in gated}
    rows = []
    for item in manifest:
        proposal = by_key[item["seed_proposal_key"]]
        rows.append(
            {
                "batch_no": item["batch_no"],
                "seed_proposal_key": item["seed_proposal_key"],
                "source_id": item["source_id"],
                "source_key": item["source_key"],
                "semantic_kind_before": item["kind_before"],
                "semantic_kind_after": proposal["semantic_kind"],
                "semantic_review_decision": item["semantic_review_decision"],
                "merge_partner_batch": item["merge_partner_batch"],
                "seed_candidate_state": proposal["seed_candidate_state"],
                "approval_state": APPROVAL_STATE,
            }
        )
    return rows


def build_chg1_plan(root: Path = DEFAULT_ROOT) -> dict:
    seed = build_raw_seed_plan(root)
    manifest = build_gpt_manifest()
    gated = apply_semantic_gate(seed["proposals"], manifest)
    mappings = build_gated_mappings(gated)
    dist = semantic_distribution(gated)
    semantic_sha = universe_sha(
        gated,
        "seed_proposal_key",
        "semantic_kind",
        "semantic_kind_source",
        "seed_candidate_state",
        "semantic_review_decision",
        "merge_partner_batch",
    )
    relation_sha = universe_sha(
        mappings,
        "source_id",
        "source_key",
        "target_seed_proposal_key",
        "recommended_mapping_type",
        "review_status",
    )
    result_rows = chg1_result_rows(gated, manifest)
    return {
        "proposals": gated,
        "mappings": mappings,
        "manifest": manifest,
        "result_rows": result_rows,
        "distribution": dist,
        "source_plan": seed["source_plan"],
        "eligible": seed["eligible"],
        "metrics": seed["metrics"],
        "manifest_sha": manifest_sha(manifest),
        "semantic_sha": semantic_sha,
        "relation_sha": relation_sha,
        "source_relation_review_universe": len(mappings),
        "mapping_approval_coverage": 0,
        "no_match": sum(1 for row in mappings if row["recommended_mapping_type"] == "NO_MATCH"),
    }


def build_chg1_report(root: Path = DEFAULT_ROOT) -> dict:
    plan = build_chg1_plan(root)
    dist = plan["distribution"]
    a = plan["source_plan"]["A"]
    b = plan["source_plan"]["B"]
    c = plan["source_plan"]["C"]
    summary = {
        "WO": "WO-RISK-04-CHG1",
        "NEW_MIGRATION": 0,
        "SOURCE_PROPOSAL_UNIVERSE": dist["source_proposal_universe"],
        "SEMANTIC_KIND_GATE": "PASS",
        "CIC_W_nodes": dist["CIC_W"],
        "CIC_W_reviewed": dist["CIC_W_reviewed"],
        "CIC_W_unreviewed": dist["CIC_W_unreviewed"],
        "CIC_W_unreviewed_PROCESS": dist["CIC_W_unreviewed_PROCESS"],
        "CIC_W_unreviewed_AMBIGUOUS": dist["CIC_W_unreviewed_AMBIGUOUS"],
        "CIC_W_reviewed_PROCESS": dist["CIC_W_reviewed_PROCESS"],
        "CIC_W_reviewed_AMBIGUOUS": dist["CIC_W_reviewed_AMBIGUOUS"],
        "CIC_W_reviewed_MATERIAL_COMPONENT": dist["CIC_W_reviewed_MATERIAL_COMPONENT"],
        "CIC_W_reviewed_FACILITY_EQUIPMENT": dist["CIC_W_reviewed_FACILITY_EQUIPMENT"],
        "CIC_W_reviewed_CLASSIFICATION": dist["CIC_W_reviewed_CLASSIFICATION"],
        "semantic_PROCESS": dist["semantic_PROCESS"],
        "semantic_TASK": dist["semantic_TASK"],
        "semantic_AMBIGUOUS": dist["semantic_AMBIGUOUS"],
        "semantic_NON_CANONICAL": dist["semantic_NON_CANONICAL"],
        "KALIS_tasks": dist["KALIS"],
        "KALIS_same_name_multi_parent_auto_HOLD": dist["KALIS_same_name_multi_parent_auto_HOLD"],
        "SOURCE_RELATION_REVIEW_UNIVERSE": plan["source_relation_review_universe"],
        "mapping_approval_coverage": 0,
        "AUTO_MERGED": 0,
        "AUTO_APPROVED": 0,
        "OWNER_APPROVED_SEEDS": 0,
        "CANONICAL_UUID_CREATED": 0,
        "ACTIVE_CANONICALS": 0,
        "APPROVED_DB_MAPPINGS": 0,
        "SEMANTIC_SHA": plan["semantic_sha"],
        "RELATION_SHA": plan["relation_sha"],
        "MANIFEST_SHA": plan["manifest_sha"],
        "A_nodes": a["nodes"],
        "B_raw_rows": b["rows"],
        "B_path_identities": b["path_identities"],
        "B_identity": b["identity"],
        "B_occurrence": b["leaf_occurrence_sum"],
        "C_unique_content": c["unique_content"],
        "C_occurrence": c["occurrence_sum"],
        "NO_MATCH_CANDIDATES": plan["no_match"],
        "db_write": 0,
        "RECOMMENDATION": "PASS CANDIDATE",
        "RISK_04_APPROVE_001": "NOT OPENED",
    }
    summary["_plan"] = plan
    return summary


def write_chg1_artifacts(summary: dict) -> None:
    plan = summary["_plan"]
    write_tsv(plan["manifest"], GPT_MANIFEST_PATH, GPT_MANIFEST_FIELDS)
    write_tsv(plan["result_rows"], CHG1_RESULT_PATH, CHG1_RESULT_FIELDS)
    root = Path("artifacts/risk04")
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in summary.items() if k != "_plan"}
    reports.joinpath("chg1_summary.json").write_text(
        json.dumps(slim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    summary = build_chg1_report()
    write_chg1_artifacts(summary)
    slim = {k: v for k, v in summary.items() if k != "_plan"}
    print(json.dumps(slim, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
