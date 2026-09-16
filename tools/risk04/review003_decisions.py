"""GPT W_MID 291 review freeze. Compact encoding of completed decisions, not a classifier."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk02.contract import SOURCE_CIC_W
from tools.risk04.review_decisions import APPROVAL_STATE, write_tsv
from tools.risk04.review003 import WORKSHEET_FIELDS, load_review003
from tools.risk04.seed_review import DEFAULT_ROOT, build_raw_seed_plan, universe_sha

FROZEN_REVIEW003_SHA = "4fb7357d0fb6396ea9f63f03d49b6c5af9c62ac7fce6f2c9b510652c5e2ee72b"
REVIEW003_GPT_PATH = Path("docs/knowledge/risk/RISK04_CICW_MID_REVIEW003_GPT_REVIEW_v1.tsv")
REVIEW003_RESULT_PATH = Path("docs/knowledge/risk/RISK04_CICW_MID_REVIEW003_RESULT.tsv")

GPT003_FIELDS = (
    "batch_no",
    "seed_proposal_key",
    "source_id",
    "source_key",
    "name",
    "semantic_kind_before",
    "semantic_kind_after",
    "semantic_review_decision",
    "merge_candidate_keys",
    "review_basis",
    "gpt_leaf_family_policy",
    "approval_state",
)
RESULT003_FIELDS = (
    "batch_no",
    "seed_proposal_key",
    "source_id",
    "source_key",
    "semantic_kind_before",
    "semantic_kind_after",
    "semantic_review_decision",
    "merge_candidate_keys",
    "gpt_leaf_family_policy",
    "approval_state",
)

# Completed GPT review of batch 401-691 only. Not a depth/parent/name classifier.
TASK_KIND = frozenset({410, 411})
METHOD_REJECT = frozenset({457, 462})
MATERIAL_REJECT = frozenset(
    {463, 524, 525, 532, 540, 546, 547, 548, 549, 550, 551, 552, 561, 584, 585, 586, 587}
)
FACILITY_REJECT = frozenset(
    {
        401, 402, 403, 404, 405, 412, 413, 414, 415, 416, 484, 492, 501, 502, 503,
        506, 516, 517, 518, 519, 520, 521, 558, 559, 560, 589, 590, 591, 592,
    }
)
CLASSIFICATION_REJECT = frozenset(
    {459, 460, 461, 471, 482, 483, 515, 593, 594, 595, 596}
)
MERGE_CANDIDATE = frozenset(
    {410, 610, 622, 623, 640, 642, 643, 648, 657, 658, 660, 661, 664, 665, 668, 677, 679, 680, 681, 683}
)
MERGE_RELATIONS: dict[int, tuple[str, ...]] = {
    410: ("052", "0521"),
    610: ("626", "6263"),
    622: ("671", "6711"),
    623: ("672", "6721"),
    640: ("731", "7311"),
    642: ("733", "7331"),
    643: ("734", "7341"),
    648: ("741", "7411"),
    657: ("811", "8111"),
    658: ("812", "8121"),
    660: ("821", "8212"),
    661: ("822", "831", "8222", "8311"),
    664: ("825", "863", "8631"),
    665: ("831", "822", "8311", "8222"),
    668: ("834", "8341"),
    677: ("854", "8541"),
    679: ("862", "8621"),
    680: ("863", "825", "8631"),
    681: ("864", "8641"),
    683: ("912", "9121"),
}


def _validate_coverage() -> None:
    overrides = TASK_KIND | METHOD_REJECT | MATERIAL_REJECT | FACILITY_REJECT | CLASSIFICATION_REJECT
    if len(TASK_KIND) != 2 or len(METHOD_REJECT) != 2:
        raise ValueError("TASK/METHOD override counts")
    if len(MATERIAL_REJECT) != 17 or len(FACILITY_REJECT) != 29 or len(CLASSIFICATION_REJECT) != 11:
        raise ValueError("REJECT kind override counts")
    if len(overrides) != 61:
        raise ValueError(f"override union {len(overrides)}")
    process_n = 291 - len(overrides)
    if process_n != 230:
        raise ValueError(f"PROCESS remainder {process_n}")
    if MERGE_CANDIDATE & (METHOD_REJECT | MATERIAL_REJECT | FACILITY_REJECT | CLASSIFICATION_REJECT):
        raise ValueError("MERGE_CANDIDATE on non-canonical kind")
    if MERGE_CANDIDATE - (TASK_KIND | set(range(401, 692))):
        raise ValueError("MERGE_CANDIDATE outside 401-691")
    if set(MERGE_RELATIONS) != MERGE_CANDIDATE:
        raise ValueError("MERGE_RELATIONS keys mismatch")


def kind_for_review003(batch_no: int) -> str:
    _validate_coverage()
    if batch_no in TASK_KIND:
        return "TASK"
    if batch_no in METHOD_REJECT:
        return "METHOD"
    if batch_no in MATERIAL_REJECT:
        return "MATERIAL_COMPONENT"
    if batch_no in FACILITY_REJECT:
        return "FACILITY_EQUIPMENT"
    if batch_no in CLASSIFICATION_REJECT:
        return "CLASSIFICATION"
    if 401 <= batch_no <= 691:
        return "PROCESS"
    raise ValueError(f"no REVIEW003 kind for {batch_no}")


def decision_for_review003(batch_no: int, kind: str) -> str:
    if kind not in {"PROCESS", "TASK"}:
        return "REJECT"
    if batch_no in MERGE_CANDIDATE:
        return "MERGE_CANDIDATE"
    return "KEEP_AS_DISTINCT"


def family_policy_for(mechanical_state: str, direct_child_count: int) -> str:
    """GPT-specified mapping of mechanical child-review state. Not child-kind assignment."""
    if mechanical_state == "ALL_REVIEWED_SINGLE_KIND":
        return "SAFE_SINGLE_KIND_FAMILY"
    if mechanical_state in {"PARTIAL_REVIEW_MULTI_KIND", "ALL_REVIEWED_MULTI_KIND"}:
        return "MIXED_FAMILY"
    if mechanical_state == "NO_REVIEWED_CHILDREN" and direct_child_count == 0:
        return "NO_CHILDREN"
    return "INSUFFICIENT_EVIDENCE"


def review_basis(kind: str, decision: str) -> str:
    return f"GPT_REVIEW003_{decision}_{kind}"


def assert_frozen_review003() -> list[dict]:
    rows = load_review003()
    digest = universe_sha(rows, *WORKSHEET_FIELDS)
    if digest != FROZEN_REVIEW003_SHA:
        raise ValueError("frozen REVIEW003 input SHA mismatch")
    if [int(row["batch_no"]) for row in rows] != list(range(401, 692)):
        raise ValueError("REVIEW003 numbering drift")
    return rows


def cicw_proposal_keys(root: Path = DEFAULT_ROOT) -> dict[str, str]:
    raw = build_raw_seed_plan(root)
    by_key: dict[str, str] = {}
    for row in raw["proposals"]:
        if row["origin_source_id"] != SOURCE_CIC_W:
            continue
        key = row["origin_source_key"]
        if key in by_key:
            raise ValueError(f"duplicate CIC_W source_key {key}")
        by_key[key] = row["seed_proposal_key"]
    if len(raw["proposals"]) != 3103:
        raise ValueError(f"SOURCE PROPOSAL UNIVERSE {len(raw['proposals'])}")
    return by_key


def merge_keys_for(batch_no: int, source_key: str, proposal_keys: dict[str, str]) -> str:
    if batch_no not in MERGE_RELATIONS:
        return "EMPTY"
    members = MERGE_RELATIONS[batch_no]
    if source_key not in members:
        raise ValueError(f"batch {batch_no} source_key {source_key} not in merge relation {members}")
    counterparts = []
    for key in members:
        if key == source_key:
            continue
        resolved = proposal_keys.get(key)
        if not resolved:
            raise ValueError(f"merge counterpart {key} missing from proposal universe")
        counterparts.append((key, resolved))
    counterparts.sort(key=lambda item: item[0])
    return " | ".join(item[1] for item in counterparts)


def build_review003_gpt_manifest(root: Path = DEFAULT_ROOT) -> list[dict]:
    frozen = assert_frozen_review003()
    proposal_keys = cicw_proposal_keys(root)
    rows = []
    for row in frozen:
        batch_no = int(row["batch_no"])
        kind = kind_for_review003(batch_no)
        decision = decision_for_review003(batch_no, kind)
        policy = family_policy_for(row["reviewed_child_mechanical_state"], int(row["direct_child_count"]))
        merge_keys = merge_keys_for(batch_no, row["source_key"], proposal_keys)
        if decision == "MERGE_CANDIDATE" and merge_keys == "EMPTY":
            raise ValueError(f"MERGE_CANDIDATE {batch_no} missing counterparts")
        if decision != "MERGE_CANDIDATE" and merge_keys != "EMPTY":
            raise ValueError(f"non-merge {batch_no} has merge keys")
        if row["seed_proposal_key"] != proposal_keys.get(row["source_key"]):
            raise ValueError(f"proposal key drift {row['source_key']}")
        rows.append(
            {
                "batch_no": str(batch_no),
                "seed_proposal_key": row["seed_proposal_key"],
                "source_id": SOURCE_CIC_W,
                "source_key": row["source_key"],
                "name": row["name"],
                "semantic_kind_before": row["current_semantic_kind"],
                "semantic_kind_after": kind,
                "semantic_review_decision": decision,
                "merge_candidate_keys": merge_keys,
                "review_basis": review_basis(kind, decision),
                "gpt_leaf_family_policy": policy,
                "approval_state": APPROVAL_STATE,
            }
        )
    kinds = Counter(row["semantic_kind_after"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    policies = Counter(row["gpt_leaf_family_policy"] for row in rows)
    expected_kinds = {
        "PROCESS": 230,
        "TASK": 2,
        "METHOD": 2,
        "MATERIAL_COMPONENT": 17,
        "FACILITY_EQUIPMENT": 29,
        "CLASSIFICATION": 11,
    }
    if kinds != expected_kinds:
        raise ValueError(f"REVIEW003 kind totals {kinds}")
    if decisions != {"KEEP_AS_DISTINCT": 212, "MERGE_CANDIDATE": 20, "REJECT": 59}:
        raise ValueError(f"REVIEW003 decision totals {decisions}")
    if policies != {
        "SAFE_SINGLE_KIND_FAMILY": 13,
        "MIXED_FAMILY": 2,
        "INSUFFICIENT_EVIDENCE": 230,
        "NO_CHILDREN": 46,
    }:
        raise ValueError(f"family policy totals {policies}")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("approval_state must be NOT_APPROVED")
    if any(row["semantic_kind_after"] == "AMBIGUOUS" for row in rows):
        raise ValueError("REVIEW003 AMBIGUOUS must be 0")
    return rows


def build_review003_result(manifest: list[dict] | None = None) -> list[dict]:
    manifest = manifest if manifest is not None else build_review003_gpt_manifest()
    return [
        {
            "batch_no": row["batch_no"],
            "seed_proposal_key": row["seed_proposal_key"],
            "source_id": row["source_id"],
            "source_key": row["source_key"],
            "semantic_kind_before": row["semantic_kind_before"],
            "semantic_kind_after": row["semantic_kind_after"],
            "semantic_review_decision": row["semantic_review_decision"],
            "merge_candidate_keys": row["merge_candidate_keys"],
            "gpt_leaf_family_policy": row["gpt_leaf_family_policy"],
            "approval_state": APPROVAL_STATE,
        }
        for row in manifest
    ]


def review003_manifest_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *GPT003_FIELDS)


def write_review003_decision_artifacts(root: Path = DEFAULT_ROOT) -> dict:
    manifest = build_review003_gpt_manifest(root)
    result = build_review003_result(manifest)
    write_tsv(manifest, REVIEW003_GPT_PATH, GPT003_FIELDS)
    write_tsv(result, REVIEW003_RESULT_PATH, RESULT003_FIELDS)
    return {"manifest": manifest, "result": result, "sha": review003_manifest_sha(manifest)}
