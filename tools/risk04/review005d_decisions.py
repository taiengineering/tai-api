"""LEAF Batch004D GPT semantic decisions. Completed review freeze, not a classifier."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review004_leaf_routing import load_leaf_batch
from tools.risk04.review005d_pack import (
    FROZEN_004D_SHA,
    INPUT_004D_PATH,
    PACK_004D_PATH,
    assert_frozen_004d,
    compact_pack_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

FROZEN_COMPACT_SHA = "12732309181ec3f78fe66720e8efa9046a876a0ac28c177311445d4f86f05b6a"
GPT_004D_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004D_GPT_REVIEW_v1.tsv")
RESULT_004D_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004D_REVIEW_RESULT.tsv")

GPT004D_FIELDS = (
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
RESULT004D_FIELDS = (
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

NAMED_KIND = {
    1292: ("프레스", "FACILITY_EQUIPMENT"),
    1293: ("방부처리", "TASK"),
    1308: ("부속기와", "MATERIAL_COMPONENT"),
    1334: ("탄성시트방수", "TASK"),
    1350: ("아크릴계발수제", "MATERIAL_COMPONENT"),
    1379: ("진동방지공사", "PROCESS"),
    1380: ("방음공사", "PROCESS"),
    1381: ("철재프레임", "MATERIAL_COMPONENT"),
    1404: ("직선금속계단", "FACILITY_EQUIPMENT"),
    1420: ("간단구조", "CLASSIFICATION"),
    1421: ("보통구조", "CLASSIFICATION"),
    1422: ("복잡구조", "CLASSIFICATION"),
    1425: ("창틀", "MATERIAL_COMPONENT"),
    1426: ("창문 - - 대․중․소 분류대․중․소 분류", "FACILITY_EQUIPMENT"),
    1437: ("절단및가공", "TASK"),
    1445: ("코킹부속공사", "PROCESS"),
    1453: ("회반죽미장", "TASK"),
    1455: ("돌로마이트플라스터", "MATERIAL_COMPONENT"),
    1468: ("바닥판넬히팅시스템", "FACILITY_EQUIPMENT"),
    1475: ("미장준비공사", "PROCESS"),
    1482: ("화강석내벽붙이기", "TASK"),
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


# Completed GPT review of review_no 1292..1491 only.
# This is an explicit decision freeze, not a classifier.
PROCESS_KIND = _span((1379, 1380), 1445, 1475)
TASK_KIND = _span(
    (1293, 1297), (1300, 1307), (1311, 1316), (1334, 1349), (1358, 1378), 1385,
    (1409, 1410), 1413, (1418, 1419), 1437, (1440, 1444), (1453, 1454),
    (1459, 1462), (1466, 1467), (1469, 1474), (1476, 1491),
)
METHOD_KIND: frozenset[int] = frozenset()
MATERIAL_KIND = _span(
    (1308, 1310), (1317, 1328), 1332, (1350, 1357), (1381, 1384), (1386, 1403),
    (1411, 1412), (1416, 1417), 1425, (1429, 1436), (1438, 1439), (1446, 1452),
    (1455, 1458), (1463, 1465),
)
FACILITY_KIND = _span(
    1292, (1298, 1299), (1329, 1331), 1333, (1404, 1408), (1414, 1415),
    (1423, 1424), (1426, 1428), 1468,
)
CLASSIFICATION_KIND = _span((1420, 1422))
AMBIGUOUS_KIND: frozenset[int] = frozenset()


def _validate_coverage() -> None:
    union = (
        PROCESS_KIND | TASK_KIND | METHOD_KIND | MATERIAL_KIND
        | FACILITY_KIND | CLASSIFICATION_KIND | AMBIGUOUS_KIND
    )
    expected_range = frozenset(range(1292, 1492))
    if union != expected_range:
        missing = sorted(expected_range - union)
        extra = sorted(union - expected_range)
        raise ValueError(f"004D coverage missing={missing} extra={extra}")
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
        "PROCESS": 4,
        "TASK": 98,
        "METHOD": 0,
        "MATERIAL_COMPONENT": 75,
        "FACILITY_EQUIPMENT": 20,
        "CLASSIFICATION": 3,
        "AMBIGUOUS": 0,
    }
    if sizes != expected:
        raise ValueError(f"004D kind set sizes {sizes}")
    overlap = 0
    buckets = (
        PROCESS_KIND, TASK_KIND, METHOD_KIND, MATERIAL_KIND,
        FACILITY_KIND, CLASSIFICATION_KIND, AMBIGUOUS_KIND,
    )
    for i, left in enumerate(buckets):
        for right in buckets[i + 1 :]:
            overlap += len(left & right)
    if overlap:
        raise ValueError(f"004D kind overlap {overlap}")


def kind_for_004d(review_no: int) -> str:
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
    raise ValueError(f"no 004D kind for {review_no}")


def decision_for_004d(kind: str) -> str:
    if kind == "AMBIGUOUS":
        return "HOLD"
    if kind in {"PROCESS", "TASK"}:
        return "KEEP_AS_DISTINCT"
    return "REJECT"


def review_basis(kind: str, decision: str) -> str:
    return f"GPT_004D_{decision}_{kind}"


def assert_frozen_004d_pack() -> list[dict]:
    assert_frozen_004d()
    rows = load_tsv(PACK_004D_PATH)
    digest = compact_pack_sha(rows)
    if digest != FROZEN_COMPACT_SHA:
        raise ValueError("frozen 004D compact SHA mismatch")
    if [int(row["review_no"]) for row in rows] != list(range(1292, 1492)):
        raise ValueError("004D compact numbering drift")
    by_no = {int(row["review_no"]): row for row in rows}
    for no, (name, _) in NAMED_KIND.items():
        if by_no[no]["name"] != name:
            raise ValueError(f"{no} identity mismatch")
    return rows


def build_004d_gpt_manifest() -> list[dict]:
    frozen = assert_frozen_004d_pack()
    input_rows = load_leaf_batch(INPUT_004D_PATH)
    before = {row["review_no"]: row["current_semantic_kind"] for row in input_rows}
    rows = []
    for row in frozen:
        review_no = int(row["review_no"])
        kind = kind_for_004d(review_no)
        decision = decision_for_004d(kind)
        rows.append(
            {
                "review_no": str(review_no),
                "seed_proposal_key": row["seed_proposal_key"],
                "source_key": row["source_key"],
                "name": row["name"],
                "semantic_kind_before": before[row["review_no"]],
                "semantic_kind_after": kind,
                "semantic_review_decision": decision,
                "merge_candidate_keys": "EMPTY",
                "review_basis": review_basis(kind, decision),
                "approval_state": APPROVAL_STATE,
            }
        )
    kinds = Counter(row["semantic_kind_after"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    expected_kinds = {
        "PROCESS": 4,
        "TASK": 98,
        "MATERIAL_COMPONENT": 75,
        "FACILITY_EQUIPMENT": 20,
        "CLASSIFICATION": 3,
    }
    if kinds != expected_kinds:
        raise ValueError(f"004D kind totals {kinds}")
    if decisions != {"KEEP_AS_DISTINCT": 102, "REJECT": 98}:
        raise ValueError(f"004D decision totals {decisions}")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("approval_state must be NOT_APPROVED")
    if any(row["semantic_kind_before"] != "AMBIGUOUS" for row in rows):
        raise ValueError("004D kind_before must be AMBIGUOUS")
    if any(row["merge_candidate_keys"] != "EMPTY" for row in rows):
        raise ValueError("004D merge_candidate_keys must be EMPTY")
    if any(row["semantic_kind_after"] == "METHOD" for row in rows):
        raise ValueError("004D METHOD must be 0")
    if any(row["semantic_kind_after"] == "AMBIGUOUS" for row in rows):
        raise ValueError("004D AMBIGUOUS must be 0")
    if any(row["semantic_review_decision"] in {"MERGE_CANDIDATE", "HOLD"} for row in rows):
        raise ValueError("004D MERGE/HOLD must be 0")
    by_no = {int(row["review_no"]): row for row in rows}
    for no, (name, kind) in NAMED_KIND.items():
        if by_no[no]["name"] != name or by_no[no]["semantic_kind_after"] != kind:
            raise ValueError(f"{no} named freeze mismatch")
        if by_no[no]["name"].encode("utf-8") != name.encode("utf-8"):
            raise ValueError(f"{no} name bytes mutated")
    return rows


def build_004d_result(manifest: list[dict] | None = None) -> list[dict]:
    manifest = manifest if manifest is not None else build_004d_gpt_manifest()
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


def manifest_004d_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *GPT004D_FIELDS)


def write_004d_decision_artifacts() -> dict:
    manifest = build_004d_gpt_manifest()
    result = build_004d_result(manifest)
    write_tsv(manifest, GPT_004D_PATH, GPT004D_FIELDS)
    write_tsv(result, RESULT_004D_PATH, RESULT004D_FIELDS)
    return {"manifest": manifest, "result": result, "sha": manifest_004d_sha(manifest)}


def main() -> None:
    out = write_004d_decision_artifacts()
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-005D-DECISION-001",
                "004D_INPUT_SHA": FROZEN_004D_SHA,
                "004D_COMPACT_SHA": FROZEN_COMPACT_SHA,
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
