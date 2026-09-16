"""LEAF Batch004C GPT semantic decisions. Completed review freeze, not a classifier."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review004_leaf_routing import load_leaf_batch
from tools.risk04.review005c_pack import (
    FROZEN_004C_SHA,
    INPUT_004C_PATH,
    PACK_004C_PATH,
    assert_frozen_004c,
    compact_pack_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

FROZEN_COMPACT_SHA = "0c9ba5a0f26b33b15a77766e51d94970df49c59f1ba868fa90434c6470d483b1"
GPT_004C_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004C_GPT_REVIEW_v1.tsv")
RESULT_004C_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004C_REVIEW_RESULT.tsv")

GPT004C_FIELDS = (
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
RESULT004C_FIELDS = (
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

HOLD_NOS = frozenset({1205, 1206, 1207, 1208, 1209})
HOLD_NAMES = {
    1205: "중질토사(N=",
    1206: "경질토사(N=",
    1207: "최경질토사(N=",
    1208: "자갈석인연질토사(N=",
    1209: "자갈석인경질토(N=",
}
NAMED_KIND = {
    1092: ("관부사", "TASK"),
    1103: ("여과설비설치", "TASK"),
    1122: ("포장거푸집", "FACILITY_EQUIPMENT"),
    1178: ("배수배관", "MATERIAL_COMPONENT"),
    1189: ("터널락볼트", "MATERIAL_COMPONENT"),
    1232: ("시버스", "FACILITY_EQUIPMENT"),
    1246: ("석축쌓기", "TASK"),
    1260: ("유리블록쌓기", "TASK"),
    1261: ("유리블록판넬설치", "TASK"),
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


# Completed GPT review of review_no 1092..1291 only.
# This is not a parent/family/name/suffix classifier.
PROCESS_KIND = _span(
    1096, (1118, 1120), (1124, 1128), 1154, 1181, (1198, 1201), 1203,
    (1225, 1226), 1228, (1230, 1231), 1233, (1236, 1237),
)
TASK_KIND = _span(
    (1092, 1093), 1095, 1103, (1105, 1113), 1121, (1139, 1153), (1155, 1158),
    (1162, 1168), (1182, 1183), (1186, 1188), (1190, 1195), 1202, (1210, 1212),
    (1220, 1224), (1238, 1241), 1246, (1260, 1267), (1271, 1275), 1282,
    (1284, 1285), (1287, 1291),
)
METHOD_KIND: frozenset[int] = frozenset()
MATERIAL_KIND = _span(
    1094, (1114, 1117), 1123, 1178, 1189, (1213, 1219), 1229, (1242, 1244),
    (1249, 1259), (1268, 1270), (1276, 1281), 1283, 1286,
)
FACILITY_KIND = _span(
    (1097, 1102), 1104, 1122, (1129, 1138), (1159, 1161), (1169, 1177),
    (1179, 1180), (1184, 1185), (1196, 1197), 1204, 1227, 1232, (1234, 1235),
    1245, (1247, 1248),
)
CLASSIFICATION_KIND: frozenset[int] = frozenset()
AMBIGUOUS_KIND = HOLD_NOS


def _validate_coverage() -> None:
    union = (
        PROCESS_KIND | TASK_KIND | METHOD_KIND | MATERIAL_KIND
        | FACILITY_KIND | CLASSIFICATION_KIND | AMBIGUOUS_KIND
    )
    expected_range = frozenset(range(1092, 1292))
    if union != expected_range:
        missing = sorted(expected_range - union)
        extra = sorted(union - expected_range)
        raise ValueError(f"004C coverage missing={missing} extra={extra}")
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
        "PROCESS": 24,
        "TASK": 86,
        "METHOD": 0,
        "MATERIAL_COMPONENT": 41,
        "FACILITY_EQUIPMENT": 44,
        "CLASSIFICATION": 0,
        "AMBIGUOUS": 5,
    }
    if sizes != expected:
        raise ValueError(f"004C kind set sizes {sizes}")
    overlap = 0
    buckets = (
        PROCESS_KIND, TASK_KIND, METHOD_KIND, MATERIAL_KIND,
        FACILITY_KIND, CLASSIFICATION_KIND, AMBIGUOUS_KIND,
    )
    for i, left in enumerate(buckets):
        for right in buckets[i + 1 :]:
            overlap += len(left & right)
    if overlap:
        raise ValueError(f"004C kind overlap {overlap}")


def kind_for_004c(review_no: int) -> str:
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
    raise ValueError(f"no 004C kind for {review_no}")


def decision_for_004c(kind: str) -> str:
    if kind == "AMBIGUOUS":
        return "HOLD"
    if kind in {"PROCESS", "TASK"}:
        return "KEEP_AS_DISTINCT"
    return "REJECT"


def review_basis(kind: str, decision: str) -> str:
    return f"GPT_004C_{decision}_{kind}"


def assert_frozen_004c_pack() -> list[dict]:
    assert_frozen_004c()
    rows = load_tsv(PACK_004C_PATH)
    digest = compact_pack_sha(rows)
    if digest != FROZEN_COMPACT_SHA:
        raise ValueError("frozen 004C compact SHA mismatch")
    if [int(row["review_no"]) for row in rows] != list(range(1092, 1292)):
        raise ValueError("004C compact numbering drift")
    by_no = {int(row["review_no"]): row for row in rows}
    for no, name in HOLD_NAMES.items():
        if by_no[no]["name"] != name:
            raise ValueError(f"{no} truncated name restored or drifted")
    for no, (name, _) in NAMED_KIND.items():
        if by_no[no]["name"] != name:
            raise ValueError(f"{no} identity mismatch")
    return rows


def build_004c_gpt_manifest() -> list[dict]:
    frozen = assert_frozen_004c_pack()
    input_rows = load_leaf_batch(INPUT_004C_PATH)
    before = {row["review_no"]: row["current_semantic_kind"] for row in input_rows}
    rows = []
    for row in frozen:
        review_no = int(row["review_no"])
        kind = kind_for_004c(review_no)
        decision = decision_for_004c(kind)
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
        "PROCESS": 24,
        "TASK": 86,
        "MATERIAL_COMPONENT": 41,
        "FACILITY_EQUIPMENT": 44,
        "AMBIGUOUS": 5,
    }
    if kinds != expected_kinds:
        raise ValueError(f"004C kind totals {kinds}")
    if decisions != {"KEEP_AS_DISTINCT": 110, "HOLD": 5, "REJECT": 85}:
        raise ValueError(f"004C decision totals {decisions}")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("approval_state must be NOT_APPROVED")
    if any(row["semantic_kind_before"] != "AMBIGUOUS" for row in rows):
        raise ValueError("004C kind_before must be AMBIGUOUS")
    if any(row["merge_candidate_keys"] != "EMPTY" for row in rows):
        raise ValueError("004C merge_candidate_keys must be EMPTY")
    if any(row["semantic_kind_after"] == "METHOD" for row in rows):
        raise ValueError("004C METHOD must be 0")
    if any(row["semantic_kind_after"] == "CLASSIFICATION" for row in rows):
        raise ValueError("004C CLASSIFICATION must be 0")
    by_no = {int(row["review_no"]): row for row in rows}
    for no in HOLD_NOS:
        if by_no[no]["semantic_kind_after"] != "AMBIGUOUS" or by_no[no]["semantic_review_decision"] != "HOLD":
            raise ValueError(f"{no} must remain AMBIGUOUS/HOLD")
        if by_no[no]["name"] != HOLD_NAMES[no]:
            raise ValueError(f"{no} truncated name mutated")
    for no, (name, kind) in NAMED_KIND.items():
        if by_no[no]["name"] != name or by_no[no]["semantic_kind_after"] != kind:
            raise ValueError(f"{no} named freeze mismatch")
    for no in range(1276, 1282):
        if by_no[no]["semantic_kind_after"] != "MATERIAL_COMPONENT":
            raise ValueError(f"{no} must be MATERIAL_COMPONENT")
    return rows


def build_004c_result(manifest: list[dict] | None = None) -> list[dict]:
    manifest = manifest if manifest is not None else build_004c_gpt_manifest()
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


def manifest_004c_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *GPT004C_FIELDS)


def write_004c_decision_artifacts() -> dict:
    manifest = build_004c_gpt_manifest()
    result = build_004c_result(manifest)
    write_tsv(manifest, GPT_004C_PATH, GPT004C_FIELDS)
    write_tsv(result, RESULT_004C_PATH, RESULT004C_FIELDS)
    return {"manifest": manifest, "result": result, "sha": manifest_004c_sha(manifest)}


def main() -> None:
    out = write_004c_decision_artifacts()
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-005C-DECISION-001",
                "004C_INPUT_SHA": FROZEN_004C_SHA,
                "004C_COMPACT_SHA": FROZEN_COMPACT_SHA,
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
