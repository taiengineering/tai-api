"""Deterministic REVIEW_BATCH_001. Priority is not approval."""
from __future__ import annotations

import csv
from pathlib import Path

from tools.risk04.contract import BATCH_KIND_CAP, BATCH_MAX
from tools.risk04.seed_review import universe_sha

BATCH_FIELDS = (
    "seed_proposal_key",
    "kind",
    "name",
    "source_id",
    "source_key",
    "source_path",
    "support_count",
    "risk_content_support",
    "review_status",
    "ambiguity_status",
)


def select_batch(proposals: list[dict], limit: int = BATCH_MAX, kind_cap: int = BATCH_KIND_CAP) -> list[dict]:
    process = [row for row in proposals if row["proposed_node_kind"] == "PROCESS"]
    task = [row for row in proposals if row["proposed_node_kind"] == "TASK"]
    chosen: list[dict] = []
    chosen.extend(process[:kind_cap])
    chosen.extend(task[:kind_cap])
    leftover_quota = limit - len(chosen)
    if leftover_quota > 0:
        used = {row["seed_proposal_key"] for row in chosen}
        rest = [row for row in proposals if row["seed_proposal_key"] not in used]
        chosen.extend(rest[:leftover_quota])
    chosen = chosen[:limit]
    return sorted(
        chosen,
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


def batch_rows(proposals: list[dict]) -> list[dict]:
    return [
        {
            "seed_proposal_key": row["seed_proposal_key"],
            "kind": row["proposed_node_kind"],
            "name": row["proposed_name_normalized"],
            "source_id": row["origin_source_id"],
            "source_key": row["origin_source_key"],
            "source_path": row["source_path"],
            "support_count": row["support_count"],
            "risk_content_support": row["risk_content_support"],
            "review_status": row["review_status"],
            "ambiguity_status": row["ambiguity_status"],
        }
        for row in proposals
    ]


def batch_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *BATCH_FIELDS)


def write_batch_tsv(rows: list[dict], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(BATCH_FIELDS), delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in BATCH_FIELDS})
