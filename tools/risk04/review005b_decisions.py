"""LEAF Batch004B GPT semantic decisions. Completed review freeze, not a classifier."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review004_leaf_routing import load_leaf_batch
from tools.risk04.review005b_pack import (
    FROZEN_004B_SHA,
    INPUT_004B_PATH,
    PACK_004B_PATH,
    assert_frozen_004b,
    compact_pack_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

FROZEN_COMPACT_SHA = "d253c143a54c034858115cfbc87e45559c64217dbf76a80a6205c2a0e217f360"
GPT_004B_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004B_GPT_REVIEW_v1.tsv")
RESULT_004B_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004B_REVIEW_RESULT.tsv")

GPT004B_FIELDS = (
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
RESULT004B_FIELDS = (
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

HOLD_NOS = frozenset({1057, 1058, 1059})
HOLD_NAMES = {1057: "저층(", 1058: "중층(", 1059: "고층("}
MID_226_KEY = "f7a1596f18911a69dd36553dd57ea436c77e2784b46c546e458d1d2a6c3ea582"
SELF_KEYS = {
    909: "45671bfb7fc32294bcfa774b47bcbc0a85c9a7f0c9f1d228df06c453922720bc",
    916: "f735a494d289df44d97a9189ed73941340ce5ec36cfcf5ce2cfecc6fefd56e1a",
    911: "4e9d201ccd71db8368ab1cf60b32bcc24c87ec745775ba2700818bf08c32a59c",
    918: "a870dc299a2e636bd8359d389419bb6035bbf90046189a1c7904c33afa6e0b1d",
    912: "af4f33085cb270d3d05561d8e98768f512b3a0cecc2ccec2b69faa7dd855a2c3",
    919: "dd95046844e6680c62f9699173fefd8616750d9b66bada182338b23d346b894b",
    915: "3e4b1972ffc759e66391b08fb0511df3610216890600df4205507a3a36ba40ba",
    922: "802d551a9eeb63a7b55a5300dbe2757f6186c7f8c0bdfdcac908b0028a557b13",
    985: "c1896baa7ac98169b9fe93eb307f15a571901e874ca894eb0aebc9415872f538",
}
MERGE_COUNTERPART = {
    909: SELF_KEYS[916],
    916: SELF_KEYS[909],
    911: SELF_KEYS[918],
    918: SELF_KEYS[911],
    912: SELF_KEYS[919],
    919: SELF_KEYS[912],
    915: SELF_KEYS[922],
    922: SELF_KEYS[915],
    985: MID_226_KEY,
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


# Completed GPT review of review_no 892-1091 only. Not a parent/family/suffix classifier.
PROCESS_KIND = _span((958, 959), 985, (1006, 1017), 1024, 1030, 1032, 1036, 1039)
TASK_KIND = _span(
    (892, 953), (955, 957), 960, (983, 984), 986, (1002, 1005), (1018, 1019),
    (1021, 1023), 1025, (1033, 1034), (1040, 1056), (1067, 1078), (1083, 1086),
    (1090, 1091),
)
METHOD_KIND = _span((961, 982), 987, (999, 1001))
MATERIAL_KIND = _span((988, 992), (996, 998), 1035, (1037, 1038), (1060, 1066), (1087, 1088))
FACILITY_KIND = _span(954, 1031, (1081, 1082), 1089)
CLASSIFICATION_KIND = _span((993, 995), 1020, (1026, 1029), (1079, 1080))
AMBIGUOUS_KIND = HOLD_NOS
MERGE_CANDIDATE = frozenset(MERGE_COUNTERPART)


def _validate_coverage() -> None:
    union = (
        PROCESS_KIND | TASK_KIND | METHOD_KIND | MATERIAL_KIND
        | FACILITY_KIND | CLASSIFICATION_KIND | AMBIGUOUS_KIND
    )
    if union != frozenset(range(892, 1092)):
        missing = sorted(frozenset(range(892, 1092)) - union)
        extra = sorted(union - frozenset(range(892, 1092)))
        raise ValueError(f"004B coverage missing={missing} extra={extra}")
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
        "PROCESS": 20,
        "TASK": 116,
        "METHOD": 26,
        "MATERIAL_COMPONENT": 20,
        "FACILITY_EQUIPMENT": 5,
        "CLASSIFICATION": 10,
        "AMBIGUOUS": 3,
    }
    if sizes != expected:
        raise ValueError(f"004B kind set sizes {sizes}")
    if MERGE_CANDIDATE - (TASK_KIND | PROCESS_KIND):
        raise ValueError("MERGE_CANDIDATE must be PROCESS or TASK")
    if 985 not in PROCESS_KIND or MERGE_CANDIDATE - {985} - TASK_KIND:
        raise ValueError("004B merge membership")


def kind_for_004b(review_no: int) -> str:
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
    raise ValueError(f"no 004B kind for {review_no}")


def decision_for_004b(review_no: int, kind: str) -> str:
    if kind == "AMBIGUOUS":
        return "HOLD"
    if kind not in {"PROCESS", "TASK"}:
        return "REJECT"
    if review_no in MERGE_CANDIDATE:
        return "MERGE_CANDIDATE"
    return "KEEP_AS_DISTINCT"


def review_basis(kind: str, decision: str) -> str:
    return f"GPT_004B_{decision}_{kind}"


def merge_keys_for(review_no: int) -> str:
    return MERGE_COUNTERPART.get(review_no, "EMPTY")


def assert_frozen_004b_pack() -> list[dict]:
    assert_frozen_004b()
    rows = load_tsv(PACK_004B_PATH)
    digest = compact_pack_sha(rows)
    if digest != FROZEN_COMPACT_SHA:
        raise ValueError("frozen 004B compact SHA mismatch")
    if [int(row["review_no"]) for row in rows] != list(range(892, 1092)):
        raise ValueError("004B compact numbering drift")
    by_no = {int(row["review_no"]): row for row in rows}
    for no, key in SELF_KEYS.items():
        if by_no[no]["seed_proposal_key"] != key:
            raise ValueError(f"{no} proposal key mismatch")
    if by_no[985]["source_key"] != "2263" or by_no[985]["name"] != "지반그라우팅":
        raise ValueError("985 identity mismatch")
    for no, name in HOLD_NAMES.items():
        if by_no[no]["name"] != name:
            raise ValueError(f"{no} truncated name restored or drifted")
    return rows


def build_004b_gpt_manifest() -> list[dict]:
    frozen = assert_frozen_004b_pack()
    input_rows = load_leaf_batch(INPUT_004B_PATH)
    before = {row["review_no"]: row["current_semantic_kind"] for row in input_rows}
    rows = []
    for row in frozen:
        review_no = int(row["review_no"])
        kind = kind_for_004b(review_no)
        decision = decision_for_004b(review_no, kind)
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
        "PROCESS": 20,
        "TASK": 116,
        "METHOD": 26,
        "MATERIAL_COMPONENT": 20,
        "FACILITY_EQUIPMENT": 5,
        "CLASSIFICATION": 10,
        "AMBIGUOUS": 3,
    }
    if kinds != expected_kinds:
        raise ValueError(f"004B kind totals {kinds}")
    if decisions != {"KEEP_AS_DISTINCT": 127, "MERGE_CANDIDATE": 9, "HOLD": 3, "REJECT": 61}:
        raise ValueError(f"004B decision totals {decisions}")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("approval_state must be NOT_APPROVED")
    if any(row["semantic_kind_before"] != "AMBIGUOUS" for row in rows):
        raise ValueError("004B kind_before must be AMBIGUOUS")
    by_no = {int(row["review_no"]): row for row in rows}
    if by_no[909]["merge_candidate_keys"] != by_no[916]["seed_proposal_key"]:
        raise ValueError("909/916 not reciprocal")
    if by_no[916]["merge_candidate_keys"] != by_no[909]["seed_proposal_key"]:
        raise ValueError("916/909 not reciprocal")
    if by_no[985]["merge_candidate_keys"] != MID_226_KEY:
        raise ValueError("985 counterpart is not W_MID 226")
    for no in HOLD_NOS:
        if by_no[no]["semantic_kind_after"] != "AMBIGUOUS" or by_no[no]["semantic_review_decision"] != "HOLD":
            raise ValueError(f"{no} must remain AMBIGUOUS/HOLD")
        if by_no[no]["name"] != HOLD_NAMES[no]:
            raise ValueError(f"{no} truncated name mutated")
    return rows


def build_004b_result(manifest: list[dict] | None = None) -> list[dict]:
    manifest = manifest if manifest is not None else build_004b_gpt_manifest()
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


def manifest_004b_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *GPT004B_FIELDS)


def write_004b_decision_artifacts() -> dict:
    manifest = build_004b_gpt_manifest()
    result = build_004b_result(manifest)
    write_tsv(manifest, GPT_004B_PATH, GPT004B_FIELDS)
    write_tsv(result, RESULT_004B_PATH, RESULT004B_FIELDS)
    return {"manifest": manifest, "result": result, "sha": manifest_004b_sha(manifest)}


def main() -> None:
    out = write_004b_decision_artifacts()
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-005B-DECISION-001",
                "004B_INPUT_SHA": FROZEN_004B_SHA,
                "004B_COMPACT_SHA": FROZEN_COMPACT_SHA,
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
