"""GPT/Owner Batch 001 semantic decisions. Not an approved-seed manifest."""
from __future__ import annotations

import csv
from pathlib import Path

from tools.risk04.review_batch import batch_sha
from tools.risk04.review_evidence import FROZEN_BATCH_PATH, FROZEN_BATCH_SHA, load_frozen_batch
from tools.risk04.seed_review import universe_sha

SEMANTIC_KINDS = (
    "PROCESS",
    "TASK",
    "METHOD",
    "MATERIAL_COMPONENT",
    "FACILITY_EQUIPMENT",
    "CLASSIFICATION",
    "AMBIGUOUS",
)
CANONICAL_SEMANTIC_KINDS = frozenset({"PROCESS", "TASK"})
SEED_CANDIDATE_STATES = (
    "CANDIDATE",
    "PENDING_SEMANTIC_REVIEW",
    "NON_CANONICAL_KIND",
    "MERGE_REVIEW",
    "HOLD",
    "REJECTED",
)
REVIEW_DECISIONS = ("KEEP_AS_DISTINCT", "MERGE_CANDIDATE", "HOLD", "REJECT", "UNREVIEWED")
APPROVAL_STATE = "NOT_APPROVED"
GPT_MANIFEST_PATH = Path("docs/knowledge/risk/RISK04_BATCH001_GPT_REVIEW_v1.tsv")
CHG1_RESULT_PATH = Path("docs/knowledge/risk/RISK04_BATCH001_CHG1_RESULT.tsv")

GPT_MANIFEST_FIELDS = (
    "batch_no",
    "seed_proposal_key",
    "source_id",
    "source_key",
    "kind_before",
    "semantic_review_decision",
    "semantic_kind_override",
    "merge_partner_batch",
    "review_basis",
    "approval_state",
)
CHG1_RESULT_FIELDS = (
    "batch_no",
    "seed_proposal_key",
    "source_id",
    "source_key",
    "semantic_kind_before",
    "semantic_kind_after",
    "semantic_review_decision",
    "merge_partner_batch",
    "seed_candidate_state",
    "approval_state",
)

MERGE_PAIRS = (
    (1, 5),
    (2, 4),
    (3, 10),
    (6, 11),
    (7, 22),
    (8, 47),
    (13, 14),
    (15, 24),
    (16, 26),
    (20, 30),
    (29, 37),
)
KALIS_KEEP = (
    9, 12, 17, 18, 19, 21, 23, 25, 27, 28, 33, 34, 35, 36, 38, 40, 41, 42, 43, 44, 45, 46, 48, 49, 50,
)
KALIS_HOLD = (31,)
KALIS_REJECT = (32, 39)
CIC_W_KEEP_PROCESS = (
    51, 54, 57, 60, 62, 64, 65, 66, 68, 69, 70, 71, 72, 75, 86, 87, 89, 90, 91, 92, 94, 95, 99, 100,
)
CIC_W_HOLD_AMBIGUOUS = (
    55, 56, 59, 61, 63, 67, 73, 74, 77, 79, 80, 82, 83, 84, 88, 93,
)
CIC_W_REJECT_MATERIAL = (52, 53, 58, 81, 85, 96, 97)
CIC_W_REJECT_FACILITY = (76, 78)
CIC_W_REJECT_CLASSIFICATION = (98,)


def merge_partner_map() -> dict[int, int]:
    partners: dict[int, int] = {}
    for left, right in MERGE_PAIRS:
        if left in partners or right in partners:
            raise ValueError("merge pair collision")
        partners[left] = right
        partners[right] = left
    return partners


def _validate_coverage() -> None:
    kalis = set(KALIS_KEEP) | set(merge_partner_map()) | set(KALIS_HOLD) | set(KALIS_REJECT)
    cic = (
        set(CIC_W_KEEP_PROCESS)
        | set(CIC_W_HOLD_AMBIGUOUS)
        | set(CIC_W_REJECT_MATERIAL)
        | set(CIC_W_REJECT_FACILITY)
        | set(CIC_W_REJECT_CLASSIFICATION)
    )
    if kalis != set(range(1, 51)):
        raise ValueError(f"KALIS batch coverage {sorted(kalis)}")
    if cic != set(range(51, 101)):
        raise ValueError(f"CIC_W batch coverage {sorted(cic)}")
    if len(KALIS_KEEP) != 25 or len(merge_partner_map()) != 22:
        raise ValueError("KALIS decision counts")
    if len(CIC_W_KEEP_PROCESS) != 24 or len(CIC_W_HOLD_AMBIGUOUS) != 16:
        raise ValueError("CIC_W decision counts")


def decision_for_batch(batch_no: int) -> tuple[str, str, str]:
    """Return (semantic_review_decision, semantic_kind_override, review_basis)."""
    _validate_coverage()
    if batch_no in merge_partner_map():
        return "MERGE_CANDIDATE", "TASK", "GPT_REVIEW_MERGE_CANDIDATE_PAIR"
    if batch_no in KALIS_KEEP:
        return "KEEP_AS_DISTINCT", "TASK", "GPT_REVIEW_KEEP_TASK_CONTEXT"
    if batch_no in KALIS_HOLD:
        return "HOLD", "TASK", "GPT_REVIEW_HOLD_UNSPECIFIC_TASK"
    if batch_no in KALIS_REJECT:
        return "REJECT", "TASK", "GPT_REVIEW_REJECT_INSUFFICIENT_TASK_BOUNDARY"
    if batch_no in CIC_W_KEEP_PROCESS:
        return "KEEP_AS_DISTINCT", "PROCESS", "GPT_REVIEW_KEEP_PROCESS"
    if batch_no in CIC_W_HOLD_AMBIGUOUS:
        return "HOLD", "AMBIGUOUS", "GPT_REVIEW_HOLD_KIND_UNRESOLVED"
    if batch_no in CIC_W_REJECT_MATERIAL:
        return "REJECT", "MATERIAL_COMPONENT", "GPT_REVIEW_REJECT_MATERIAL_COMPONENT"
    if batch_no in CIC_W_REJECT_FACILITY:
        return "REJECT", "FACILITY_EQUIPMENT", "GPT_REVIEW_REJECT_FACILITY_EQUIPMENT"
    if batch_no in CIC_W_REJECT_CLASSIFICATION:
        return "REJECT", "CLASSIFICATION", "GPT_REVIEW_REJECT_CLASSIFICATION"
    raise ValueError(f"no GPT decision for batch_no={batch_no}")


def seed_state_for(decision: str, semantic_kind: str) -> str:
    if decision == "MERGE_CANDIDATE":
        return "MERGE_REVIEW"
    if decision == "HOLD":
        return "HOLD"
    if decision == "REJECT":
        return "REJECTED"
    if decision == "KEEP_AS_DISTINCT" and semantic_kind in CANONICAL_SEMANTIC_KINDS:
        return "CANDIDATE"
    if semantic_kind not in CANONICAL_SEMANTIC_KINDS:
        return "NON_CANONICAL_KIND"
    return "PENDING_SEMANTIC_REVIEW"


def build_gpt_manifest(frozen_path: Path = FROZEN_BATCH_PATH) -> list[dict]:
    frozen = load_frozen_batch(frozen_path)
    digest = batch_sha(frozen)
    if digest != FROZEN_BATCH_SHA:
        raise ValueError("frozen Batch 001 SHA mismatch")
    partners = merge_partner_map()
    rows = []
    for i, batch in enumerate(frozen, start=1):
        decision, kind, basis = decision_for_batch(i)
        partner = partners.get(i)
        rows.append(
            {
                "batch_no": str(i),
                "seed_proposal_key": batch["seed_proposal_key"],
                "source_id": batch["source_id"],
                "source_key": batch["source_key"],
                "kind_before": batch["kind"],
                "semantic_review_decision": decision,
                "semantic_kind_override": kind,
                "merge_partner_batch": str(partner) if partner is not None else "EMPTY",
                "review_basis": basis,
                "approval_state": APPROVAL_STATE,
            }
        )
    counts = {
        "KEEP_AS_DISTINCT": 0,
        "MERGE_CANDIDATE": 0,
        "HOLD": 0,
        "REJECT": 0,
    }
    for row in rows:
        counts[row["semantic_review_decision"]] += 1
    if counts != {"KEEP_AS_DISTINCT": 49, "MERGE_CANDIDATE": 22, "HOLD": 17, "REJECT": 12}:
        raise ValueError(f"GPT decision totals {counts}")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("approval_state must be NOT_APPROVED")
    return rows


def manifest_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *GPT_MANIFEST_FIELDS)


def write_tsv(rows: list[dict], dest: Path, fields: tuple[str, ...]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fields), delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def load_tsv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))
