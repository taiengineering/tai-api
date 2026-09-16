"""Batch 002 GPT semantic decisions. Not an approved-seed manifest."""
from __future__ import annotations

from pathlib import Path

from tools.risk04.review_decisions import APPROVAL_STATE, write_tsv
from tools.risk04.review002 import BATCH002_PATH, load_batch002, worksheet_sha
from tools.risk04.seed_review import universe_sha

FROZEN_BATCH002_SHA = "81377ba5e1f5b3e8f80d0c3d237843ccc563fbaece02cea9eb0d2cb4c83fd806"
BATCH002_GPT_PATH = Path("docs/knowledge/risk/RISK04_CICW_BATCH002_GPT_REVIEW_v1.tsv")
BATCH002_RESULT_PATH = Path("docs/knowledge/risk/RISK04_CICW_BATCH002_REVIEW_RESULT.tsv")

GPT002_FIELDS = (
    "batch_no",
    "seed_proposal_key",
    "source_id",
    "source_key",
    "kind_before",
    "semantic_review_decision",
    "semantic_kind_override",
    "merge_candidate_keys",
    "review_basis",
    "approval_state",
)
RESULT002_FIELDS = (
    "batch_no",
    "seed_proposal_key",
    "source_id",
    "source_key",
    "semantic_kind_before",
    "semantic_kind_after",
    "semantic_review_decision",
    "merge_candidate_keys",
    "approval_state",
)


def _span(*parts: int | tuple[int, int]) -> frozenset[int]:
    out: set[int] = set()
    for part in parts:
        if isinstance(part, int):
            out.add(part)
        else:
            start, end = part
            out.update(range(start, end + 1))
    return frozenset(out)


PROCESS_KEEP = _span(
    (203, 204), 206, (208, 258), (260, 261), 265, (267, 274), (278, 280),
    (282, 285), (287, 291), (293, 303), (306, 314), (317, 320), 322,
    (324, 326), (328, 329), 331, 346, (374, 375), (377, 379), (381, 382),
    385, 387, (389, 391),
)
PROCESS_MERGE = _span(207, 259, 376, 380, 383, 384, 386, 388)
TASK_KEEP = _span(
    335, (339, 345), 348, 350, 352, 354, 356, (360, 362), (367, 370), 373, 392,
)
TASK_MERGE = _span(396)
METHOD_REJECT = _span(315, 316)
MATERIAL_REJECT = _span(
    266, 275, 276, 277, 330, 347, 349, 351, 358, 359, 363, 365, 366,
)
FACILITY_REJECT = _span(
    205, 264, 281, 286, 292, 305, 327, 334, 353, 357, 364, 371, 372, 394, 395, 397,
)
CLASSIFICATION_REJECT = _span(
    201, 202, 262, 263, 304, 321, 323, 332, 333, 336, 337, 338, 393, 398, 399, 400,
)
AMBIGUOUS_HOLD = _span(355)


def _validate_coverage() -> None:
    union = (
        PROCESS_KEEP | PROCESS_MERGE | TASK_KEEP | TASK_MERGE | METHOD_REJECT
        | MATERIAL_REJECT | FACILITY_REJECT | CLASSIFICATION_REJECT | AMBIGUOUS_HOLD
    )
    if union != frozenset(range(201, 401)):
        missing = sorted(frozenset(range(201, 401)) - union)
        extra = sorted(union - frozenset(range(201, 401)))
        raise ValueError(f"Batch002 coverage missing={missing} extra={extra}")
    if len(PROCESS_KEEP) != 121 or len(PROCESS_MERGE) != 8:
        raise ValueError("PROCESS counts")
    if len(TASK_KEEP) != 22 or len(TASK_MERGE) != 1:
        raise ValueError("TASK counts")
    if len(MATERIAL_REJECT) != 13 or len(FACILITY_REJECT) != 16:
        raise ValueError("REJECT kind counts")
    if len(CLASSIFICATION_REJECT) != 16 or len(METHOD_REJECT) != 2:
        raise ValueError("CLASSIFICATION/METHOD counts")


def decision_for_batch002(batch_no: int) -> tuple[str, str, str]:
    _validate_coverage()
    if batch_no in PROCESS_KEEP:
        return "KEEP_AS_DISTINCT", "PROCESS", "GPT_BATCH002_KEEP_PROCESS"
    if batch_no in PROCESS_MERGE:
        return "MERGE_CANDIDATE", "PROCESS", "GPT_BATCH002_MERGE_CANDIDATE_PROCESS"
    if batch_no in TASK_KEEP:
        return "KEEP_AS_DISTINCT", "TASK", "GPT_BATCH002_KEEP_TASK"
    if batch_no in TASK_MERGE:
        return "MERGE_CANDIDATE", "TASK", "GPT_BATCH002_MERGE_CANDIDATE_TASK"
    if batch_no in METHOD_REJECT:
        return "REJECT", "METHOD", "GPT_BATCH002_REJECT_METHOD"
    if batch_no in MATERIAL_REJECT:
        return "REJECT", "MATERIAL_COMPONENT", "GPT_BATCH002_REJECT_MATERIAL_COMPONENT"
    if batch_no in FACILITY_REJECT:
        return "REJECT", "FACILITY_EQUIPMENT", "GPT_BATCH002_REJECT_FACILITY_EQUIPMENT"
    if batch_no in CLASSIFICATION_REJECT:
        return "REJECT", "CLASSIFICATION", "GPT_BATCH002_REJECT_CLASSIFICATION"
    if batch_no in AMBIGUOUS_HOLD:
        return "HOLD", "AMBIGUOUS", "GPT_BATCH002_HOLD_AMBIGUOUS"
    raise ValueError(f"no Batch002 decision for {batch_no}")


def assert_frozen_batch002() -> list[dict]:
    rows = load_batch002()
    digest = worksheet_sha(rows)
    if digest != FROZEN_BATCH002_SHA:
        raise ValueError("frozen Batch002 input SHA mismatch")
    if [int(row["batch_no"]) for row in rows] != list(range(201, 401)):
        raise ValueError("Batch002 numbering drift")
    return rows


def build_batch002_gpt_manifest() -> list[dict]:
    frozen = assert_frozen_batch002()
    rows = []
    for row in frozen:
        batch_no = int(row["batch_no"])
        decision, kind, basis = decision_for_batch002(batch_no)
        merge_keys = "UNRESOLVED" if decision == "MERGE_CANDIDATE" else "EMPTY"
        rows.append(
            {
                "batch_no": str(batch_no),
                "seed_proposal_key": row["seed_proposal_key"],
                "source_id": row["source_id"],
                "source_key": row["source_key"],
                "kind_before": row["current_semantic_kind"],
                "semantic_review_decision": decision,
                "semantic_kind_override": kind,
                "merge_candidate_keys": merge_keys,
                "review_basis": basis,
                "approval_state": APPROVAL_STATE,
            }
        )
    kind_counts: dict[str, int] = {}
    decision_counts: dict[str, int] = {}
    expected_kinds = {
        "PROCESS": 129,
        "TASK": 23,
        "METHOD": 2,
        "MATERIAL_COMPONENT": 13,
        "FACILITY_EQUIPMENT": 16,
        "CLASSIFICATION": 16,
        "AMBIGUOUS": 1,
    }
    expected_decisions = {
        "KEEP_AS_DISTINCT": 143,
        "MERGE_CANDIDATE": 9,
        "HOLD": 1,
        "REJECT": 47,
    }
    for row in rows:
        kind_counts[row["semantic_kind_override"]] = kind_counts.get(row["semantic_kind_override"], 0) + 1
        decision_counts[row["semantic_review_decision"]] = decision_counts.get(row["semantic_review_decision"], 0) + 1
    if kind_counts != expected_kinds:
        raise ValueError(f"Batch002 kind totals {kind_counts}")
    if decision_counts != expected_decisions:
        raise ValueError(f"Batch002 decision totals {decision_counts}")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("approval_state must be NOT_APPROVED")
    return rows


def build_batch002_result(manifest: list[dict] | None = None) -> list[dict]:
    manifest = manifest if manifest is not None else build_batch002_gpt_manifest()
    return [
        {
            "batch_no": row["batch_no"],
            "seed_proposal_key": row["seed_proposal_key"],
            "source_id": row["source_id"],
            "source_key": row["source_key"],
            "semantic_kind_before": row["kind_before"],
            "semantic_kind_after": row["semantic_kind_override"],
            "semantic_review_decision": row["semantic_review_decision"],
            "merge_candidate_keys": row["merge_candidate_keys"],
            "approval_state": APPROVAL_STATE,
        }
        for row in manifest
    ]


def batch002_manifest_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *GPT002_FIELDS)


def write_batch002_review_artifacts() -> dict:
    manifest = build_batch002_gpt_manifest()
    result = build_batch002_result(manifest)
    write_tsv(manifest, BATCH002_GPT_PATH, GPT002_FIELDS)
    write_tsv(result, BATCH002_RESULT_PATH, RESULT002_FIELDS)
    return {
        "manifest": manifest,
        "result": result,
        "sha": batch002_manifest_sha(manifest),
    }
