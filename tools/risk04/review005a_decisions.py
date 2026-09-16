"""LEAF Batch004A GPT semantic decisions. Completed review freeze, not a classifier."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review005a_pack import (
    FROZEN_004A_SHA,
    INPUT_004A_PATH,
    PACK_004A_PATH,
    assert_frozen_004a,
    compact_pack_sha,
)
from tools.risk04.review004_leaf_routing import load_leaf_batch
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

FROZEN_COMPACT_SHA = "d571198e51be1a206450ecaa737168d9bf07ab8dfe2bb9a1a6dce3b58d9b07f9"
GPT_004A_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004A_GPT_REVIEW_v1.tsv")
RESULT_004A_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004A_REVIEW_RESULT.tsv")

GPT004A_FIELDS = (
    "review_no",
    "seed_proposal_key",
    "source_key",
    "name",
    "semantic_kind_before",
    "semantic_kind_after",
    "semantic_review_decision",
    "merge_candidate_keys",
    "review_basis",
    "approval_state",
)
RESULT004A_FIELDS = (
    "review_no",
    "seed_proposal_key",
    "source_key",
    "name",
    "semantic_kind_before",
    "semantic_kind_after",
    "semantic_review_decision",
    "merge_candidate_keys",
    "approval_state",
)

MERGE_856 = 856
MERGE_864 = 864
MERGE_KEY_856 = "2475027daba149f900315ad926df730d26003b1bd51bf7ee39a48146edeea87f"
MERGE_KEY_864 = "62c40ab49ffebadda5db8d0ee88ad789c6dd22dd16a5132d72c8d2d90a4e793d"


def _span(*parts: int | tuple[int, int]) -> frozenset[int]:
    out: set[int] = set()
    for part in parts:
        if isinstance(part, int):
            out.add(part)
        else:
            start, end = part
            out.update(range(start, end + 1))
    return frozenset(out)


# Completed GPT review of review_no 692-891 only. Not a parent/family/suffix classifier.
PROCESS_KIND = _span(692, 695, 697, 699, (759, 761))
TASK_KIND = _span(
    (693, 694), 696, 698, (762, 770), 772, (810, 816), (831, 841),
    (844, 847), (849, 864), (875, 891),
)
METHOD_KIND = _span(872, 873)
MATERIAL_KIND = _span(795, 796, 797, 809, 874)
FACILITY_KIND = _span((708, 758), 771, (775, 782), (842, 843), 848, (865, 871))
CLASSIFICATION_KIND = _span((700, 707), (773, 774), (783, 794), (798, 808), (817, 830))
MERGE_CANDIDATE = frozenset({MERGE_856, MERGE_864})


def _validate_coverage() -> None:
    union = PROCESS_KIND | TASK_KIND | METHOD_KIND | MATERIAL_KIND | FACILITY_KIND | CLASSIFICATION_KIND
    if union != frozenset(range(692, 892)):
        missing = sorted(frozenset(range(692, 892)) - union)
        extra = sorted(union - frozenset(range(692, 892)))
        raise ValueError(f"004A coverage missing={missing} extra={extra}")
    sizes = {
        "PROCESS": len(PROCESS_KIND),
        "TASK": len(TASK_KIND),
        "METHOD": len(METHOD_KIND),
        "MATERIAL_COMPONENT": len(MATERIAL_KIND),
        "FACILITY_EQUIPMENT": len(FACILITY_KIND),
        "CLASSIFICATION": len(CLASSIFICATION_KIND),
    }
    expected = {
        "PROCESS": 7,
        "TASK": 69,
        "METHOD": 2,
        "MATERIAL_COMPONENT": 5,
        "FACILITY_EQUIPMENT": 70,
        "CLASSIFICATION": 47,
    }
    if sizes != expected:
        raise ValueError(f"004A kind set sizes {sizes}")
    if MERGE_CANDIDATE - TASK_KIND:
        raise ValueError("MERGE_CANDIDATE must be TASK")


def kind_for_004a(review_no: int) -> str:
    _validate_coverage()
    if review_no in PROCESS_KIND:
        return "PROCESS"
    if review_no in TASK_KIND:
        return "TASK"
    if review_no in METHOD_KIND:
        return "METHOD"
    if review_no in MATERIAL_KIND:
        return "MATERIAL_COMPONENT"
    if review_no in FACILITY_KIND:
        return "FACILITY_EQUIPMENT"
    if review_no in CLASSIFICATION_KIND:
        return "CLASSIFICATION"
    raise ValueError(f"no 004A kind for {review_no}")


def decision_for_004a(review_no: int, kind: str) -> str:
    if kind not in {"PROCESS", "TASK"}:
        return "REJECT"
    if review_no in MERGE_CANDIDATE:
        return "MERGE_CANDIDATE"
    return "KEEP_AS_DISTINCT"


def review_basis(kind: str, decision: str) -> str:
    return f"GPT_004A_{decision}_{kind}"


def merge_keys_for(review_no: int) -> str:
    if review_no == MERGE_856:
        return MERGE_KEY_856
    if review_no == MERGE_864:
        return MERGE_KEY_864
    return "EMPTY"


def assert_frozen_004a_pack() -> list[dict]:
    assert_frozen_004a()
    rows = load_tsv(PACK_004A_PATH)
    digest = compact_pack_sha(rows)
    if digest != FROZEN_COMPACT_SHA:
        raise ValueError("frozen 004A compact SHA mismatch")
    if [int(row["review_no"]) for row in rows] != list(range(692, 892)):
        raise ValueError("004A compact numbering drift")
    by_no = {int(row["review_no"]): row for row in rows}
    if by_no[MERGE_856]["seed_proposal_key"] != MERGE_KEY_864:
        raise ValueError("856 proposal key mismatch")
    if by_no[MERGE_864]["seed_proposal_key"] != MERGE_KEY_856:
        raise ValueError("864 proposal key mismatch")
    if by_no[MERGE_856]["name"] != "동적계측" or by_no[MERGE_864]["name"] != "동적계측":
        raise ValueError("merge pair name mismatch")
    return rows


def build_004a_gpt_manifest() -> list[dict]:
    frozen = assert_frozen_004a_pack()
    input_rows = load_leaf_batch(INPUT_004A_PATH)
    before = {row["review_no"]: row["current_semantic_kind"] for row in input_rows}
    rows = []
    for row in frozen:
        review_no = int(row["review_no"])
        kind = kind_for_004a(review_no)
        decision = decision_for_004a(review_no, kind)
        rows.append(
            {
                "review_no": str(review_no),
                "seed_proposal_key": row["seed_proposal_key"],
                "source_key": row["source_key"],
                "name": row["name"],
                "semantic_kind_before": before[row["review_no"]],
                "semantic_kind_after": kind,
                "semantic_review_decision": decision,
                "merge_candidate_keys": merge_keys_for(review_no),
                "review_basis": review_basis(kind, decision),
                "approval_state": APPROVAL_STATE,
            }
        )
    kinds = Counter(row["semantic_kind_after"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    expected_kinds = {
        "PROCESS": 7,
        "TASK": 69,
        "METHOD": 2,
        "MATERIAL_COMPONENT": 5,
        "FACILITY_EQUIPMENT": 70,
        "CLASSIFICATION": 47,
    }
    if kinds != expected_kinds:
        raise ValueError(f"004A kind totals {kinds}")
    if decisions != {"KEEP_AS_DISTINCT": 74, "MERGE_CANDIDATE": 2, "REJECT": 124}:
        raise ValueError(f"004A decision totals {decisions}")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("approval_state must be NOT_APPROVED")
    if any(row["semantic_kind_after"] == "AMBIGUOUS" for row in rows):
        raise ValueError("004A AMBIGUOUS must be 0")
    if any(row["semantic_kind_before"] != "AMBIGUOUS" for row in rows):
        raise ValueError("004A kind_before must be AMBIGUOUS")
    return rows


def build_004a_result(manifest: list[dict] | None = None) -> list[dict]:
    manifest = manifest if manifest is not None else build_004a_gpt_manifest()
    return [
        {
            "review_no": row["review_no"],
            "seed_proposal_key": row["seed_proposal_key"],
            "source_key": row["source_key"],
            "name": row["name"],
            "semantic_kind_before": row["semantic_kind_before"],
            "semantic_kind_after": row["semantic_kind_after"],
            "semantic_review_decision": row["semantic_review_decision"],
            "merge_candidate_keys": row["merge_candidate_keys"],
            "approval_state": APPROVAL_STATE,
        }
        for row in manifest
    ]


def manifest_004a_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *GPT004A_FIELDS)


def write_004a_decision_artifacts() -> dict:
    manifest = build_004a_gpt_manifest()
    result = build_004a_result(manifest)
    write_tsv(manifest, GPT_004A_PATH, GPT004A_FIELDS)
    write_tsv(result, RESULT_004A_PATH, RESULT004A_FIELDS)
    return {"manifest": manifest, "result": result, "sha": manifest_004a_sha(manifest)}


def main() -> None:
    out = write_004a_decision_artifacts()
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-005A-DECISION-001",
                "004A_INPUT_SHA": FROZEN_004A_SHA,
                "004A_COMPACT_SHA": FROZEN_COMPACT_SHA,
                "MANIFEST_SHA": out["sha"],
                "rows": len(out["manifest"]),
                "INPUT_PATH": str(INPUT_004A_PATH),
                "PACK_PATH": str(PACK_004A_PATH),
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
