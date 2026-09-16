"""LEAF Batch004E GPT semantic decisions. Completed review freeze, not a classifier."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review004_leaf_routing import load_leaf_batch
from tools.risk04.review005e_pack import (
    FROZEN_004E_SHA,
    INPUT_004E_PATH,
    PACK_004E_PATH,
    assert_frozen_004e,
    compact_pack_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

FROZEN_COMPACT_SHA = "4da3ae49ff00597b24118fb7421d8ca724fc83e7ba80798a802cb2a0772a3bd5"
GPT_004E_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004E_GPT_REVIEW_v1.tsv")
RESULT_004E_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004E_REVIEW_RESULT.tsv")

GPT004E_FIELDS = (
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
RESULT004E_FIELDS = (
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

SELF_KEYS = {
    1501: "88e1a0da33adf4caee41b1aa36257015274e056a5131cf094a187051371296da",
    1548: "56c69ff9e69d81b5711d9ad23ada3a61a84f35c03391264527ef70137f3b4c64",
    1652: "70cdc930e9ba3d50a6353e9b2e64b87663bcf96f014e2a19889b794333b33081",
    1654: "28f705a03a84f2f9978aa74a5eba7fafb8181b4bf06db01ef83ab25f083c4376",
}
MERGE_COUNTERPART = {
    1501: SELF_KEYS[1548],
    1548: SELF_KEYS[1501],
    1652: SELF_KEYS[1654],
    1654: SELF_KEYS[1652],
}
NAMED_KIND = {
    1492: ("인조석외벽붙이기", "TASK"),
    1501: ("계단채임판(라이저)석재붙이기", "TASK"),
    1508: ("석재거친다듬마감 - - 대․중․소 분류대․중․소 분류", "TASK"),
    1548: ("계단채임판(라이저)석재붙이기", "TASK"),
    1553: ("합성수지쉬트", "MATERIAL_COMPONENT"),
    1555: ("카페트깔기", "TASK"),
    1556: ("이중바닥판(Accessfloor)", "MATERIAL_COMPONENT"),
    1559: ("시멘트계판재칸막이", "FACILITY_EQUIPMENT"),
    1563: ("벽체석고보드붙이기", "TASK"),
    1590: ("오일스테인", "MATERIAL_COMPONENT"),
    1591: ("목재방부칠", "TASK"),
    1632: ("붙박이안내설비", "FACILITY_EQUIPMENT"),
    1637: ("안내표식시설", "FACILITY_EQUIPMENT"),
    1641: ("의자", "FACILITY_EQUIPMENT"),
    1648: ("교목이식공사", "TASK"),
    1652: ("지피류및초화류식재", "TASK"),
    1654: ("지피류및초화류식재", "TASK"),
    1660: ("생태복원공사", "PROCESS"),
    1663: ("수경시설물설치", "TASK"),
    1672: ("전정", "TASK"),
    1679: ("설비별배관공사", "PROCESS"),
    1687: ("펌프공사", "PROCESS"),
    1690: ("천공공사", "PROCESS"),
}


def _span(*parts: int | tuple[int, int]) -> frozenset[int]:
    out: set[int] = set()
    for part in parts:
        if isinstance(part, int):
            out.add(part)
        else:
            start, end = part
            out.update(range(start, end + 1))
    return frozenset(out)


# Completed GPT review of review_no 1492..1691 only.
# This is an explicit decision freeze, not a classifier.
PROCESS_KIND = _span(1660, (1679, 1691))
TASK_KIND = _span(
    (1492, 1552), 1555, 1557, (1563, 1589), (1591, 1592), (1648, 1659), (1661, 1678),
)
METHOD_KIND: frozenset[int] = frozenset()
MATERIAL_KIND = _span((1553, 1554), 1556, 1558, 1590, (1593, 1631))
FACILITY_KIND = _span((1559, 1562), (1632, 1647))
CLASSIFICATION_KIND: frozenset[int] = frozenset()
AMBIGUOUS_KIND: frozenset[int] = frozenset()
MERGE_CANDIDATE = frozenset(MERGE_COUNTERPART)


def _validate_coverage() -> None:
    union = (
        PROCESS_KIND | TASK_KIND | METHOD_KIND | MATERIAL_KIND
        | FACILITY_KIND | CLASSIFICATION_KIND | AMBIGUOUS_KIND
    )
    expected_range = frozenset(range(1492, 1692))
    if union != expected_range:
        missing = sorted(expected_range - union)
        extra = sorted(union - expected_range)
        raise ValueError(f"004E coverage missing={missing} extra={extra}")
    sizes = {
        "PROCESS": len(PROCESS_KIND),
        "TASK": len(TASK_KIND),
        "METHOD": len(METHOD_KIND),
        "MATERIAL_COMPONENT": len(MATERIAL_KIND),
        "FACILITY_EQUIPMENT": len(FACILITY_KIND),
        "CLASSIFICATION": len(CLASSIFICATION_KIND),
        "AMBIGUOUS": len(AMBIGUOUS_KIND),
    }
    expected = {
        "PROCESS": 14,
        "TASK": 122,
        "METHOD": 0,
        "MATERIAL_COMPONENT": 44,
        "FACILITY_EQUIPMENT": 20,
        "CLASSIFICATION": 0,
        "AMBIGUOUS": 0,
    }
    if sizes != expected:
        raise ValueError(f"004E kind set sizes {sizes}")
    overlap = 0
    buckets = (
        PROCESS_KIND, TASK_KIND, METHOD_KIND, MATERIAL_KIND,
        FACILITY_KIND, CLASSIFICATION_KIND, AMBIGUOUS_KIND,
    )
    for i, left in enumerate(buckets):
        for right in buckets[i + 1 :]:
            overlap += len(left & right)
    if overlap:
        raise ValueError(f"004E kind overlap {overlap}")
    if MERGE_CANDIDATE - TASK_KIND:
        raise ValueError("004E MERGE_CANDIDATE must be TASK")


def kind_for_004e(review_no: int) -> str:
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
    if review_no in AMBIGUOUS_KIND:
        return "AMBIGUOUS"
    raise ValueError(f"no 004E kind for {review_no}")


def decision_for_004e(review_no: int, kind: str) -> str:
    if kind == "AMBIGUOUS":
        return "HOLD"
    if kind not in {"PROCESS", "TASK"}:
        return "REJECT"
    if review_no in MERGE_CANDIDATE:
        return "MERGE_CANDIDATE"
    return "KEEP_AS_DISTINCT"


def review_basis(kind: str, decision: str) -> str:
    return f"GPT_004E_{decision}_{kind}"


def merge_keys_for(review_no: int) -> str:
    return MERGE_COUNTERPART.get(review_no, "EMPTY")


def assert_frozen_004e_pack() -> list[dict]:
    assert_frozen_004e()
    rows = load_tsv(PACK_004E_PATH)
    digest = compact_pack_sha(rows)
    if digest != FROZEN_COMPACT_SHA:
        raise ValueError("frozen 004E compact SHA mismatch")
    if [int(row["review_no"]) for row in rows] != list(range(1492, 1692)):
        raise ValueError("004E compact numbering drift")
    by_no = {int(row["review_no"]): row for row in rows}
    for no, key in SELF_KEYS.items():
        if by_no[no]["seed_proposal_key"] != key:
            raise ValueError(f"{no} proposal key mismatch")
    for no, (name, _) in NAMED_KIND.items():
        if by_no[no]["name"] != name:
            raise ValueError(f"{no} identity mismatch")
    return rows


def build_004e_gpt_manifest() -> list[dict]:
    frozen = assert_frozen_004e_pack()
    input_rows = load_leaf_batch(INPUT_004E_PATH)
    before = {row["review_no"]: row["current_semantic_kind"] for row in input_rows}
    rows = []
    for row in frozen:
        review_no = int(row["review_no"])
        kind = kind_for_004e(review_no)
        decision = decision_for_004e(review_no, kind)
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
        "PROCESS": 14,
        "TASK": 122,
        "MATERIAL_COMPONENT": 44,
        "FACILITY_EQUIPMENT": 20,
    }
    if kinds != expected_kinds:
        raise ValueError(f"004E kind totals {kinds}")
    if decisions != {"KEEP_AS_DISTINCT": 132, "MERGE_CANDIDATE": 4, "REJECT": 64}:
        raise ValueError(f"004E decision totals {decisions}")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("approval_state must be NOT_APPROVED")
    if any(row["semantic_kind_before"] != "AMBIGUOUS" for row in rows):
        raise ValueError("004E kind_before must be AMBIGUOUS")
    if any(row["semantic_kind_after"] in {"METHOD", "CLASSIFICATION", "AMBIGUOUS"} for row in rows):
        raise ValueError("004E METHOD/CLASSIFICATION/AMBIGUOUS must be 0")
    if any(row["semantic_review_decision"] == "HOLD" for row in rows):
        raise ValueError("004E HOLD must be 0")
    by_no = {int(row["review_no"]): row for row in rows}
    for left, right in ((1501, 1548), (1652, 1654)):
        if by_no[left]["merge_candidate_keys"] != by_no[right]["seed_proposal_key"]:
            raise ValueError(f"{left}/{right} not reciprocal")
        if by_no[right]["merge_candidate_keys"] != by_no[left]["seed_proposal_key"]:
            raise ValueError(f"{right}/{left} not reciprocal")
        if by_no[left]["semantic_review_decision"] != "MERGE_CANDIDATE":
            raise ValueError(f"{left} must be MERGE_CANDIDATE")
        if by_no[right]["semantic_review_decision"] != "MERGE_CANDIDATE":
            raise ValueError(f"{right} must be MERGE_CANDIDATE")
    empty = [
        row for row in rows
        if int(row["review_no"]) not in MERGE_CANDIDATE and row["merge_candidate_keys"] != "EMPTY"
    ]
    if empty:
        raise ValueError("004E extra merge keys")
    for no, (name, kind) in NAMED_KIND.items():
        if by_no[no]["name"] != name or by_no[no]["semantic_kind_after"] != kind:
            raise ValueError(f"{no} named freeze mismatch")
        if by_no[no]["name"].encode("utf-8") != name.encode("utf-8"):
            raise ValueError(f"{no} name bytes mutated")
    return rows


def build_004e_result(manifest: list[dict] | None = None) -> list[dict]:
    manifest = manifest if manifest is not None else build_004e_gpt_manifest()
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


def manifest_004e_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *GPT004E_FIELDS)


def write_004e_decision_artifacts() -> dict:
    manifest = build_004e_gpt_manifest()
    result = build_004e_result(manifest)
    write_tsv(manifest, GPT_004E_PATH, GPT004E_FIELDS)
    write_tsv(result, RESULT_004E_PATH, RESULT004E_FIELDS)
    return {"manifest": manifest, "result": result, "sha": manifest_004e_sha(manifest)}


def main() -> None:
    out = write_004e_decision_artifacts()
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-005E-DECISION-001",
                "004E_INPUT_SHA": FROZEN_004E_SHA,
                "004E_COMPACT_SHA": FROZEN_COMPACT_SHA,
                "MANIFEST_SHA": out["sha"],
                "rows": len(out["manifest"]),
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
