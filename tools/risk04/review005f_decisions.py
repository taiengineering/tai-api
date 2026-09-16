"""LEAF Batch004F GPT semantic decisions. Completed review freeze, not a classifier."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review004_leaf_routing import load_leaf_batch
from tools.risk04.review005f_pack import (
    FROZEN_004F_SHA,
    INPUT_004F_PATH,
    PACK_004F_PATH,
    REVIEW_NOS,
    assert_frozen_004f,
    compact_pack_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

FROZEN_COMPACT_SHA = "ea3bdf209e916fa9a50090a581c94d313c52c96ba06002f9e28969ea11dae625"
GPT_004F_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004F_GPT_REVIEW_v1.tsv")
RESULT_004F_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004F_REVIEW_RESULT.tsv")

GPT004F_FIELDS = (
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
RESULT004F_FIELDS = (
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

MERGE_RELATIONS = {
    1718: frozenset({"626", "6263"}),
    1719: frozenset({"6311", "6312"}),
    1739: frozenset({"672", "6721"}),
    1764: frozenset({"733", "7331"}),
    1765: frozenset({"734", "7341"}),
    1792: frozenset({"812", "8121"}),
    1797: frozenset({"821", "8212"}),
    1799: frozenset({"822", "831", "8222", "8311"}),
    1817: frozenset({"834", "8341"}),
    1851: frozenset({"854", "8541"}),
    1860: frozenset({"862", "8621"}),
    1862: frozenset({"825", "863", "8631"}),
    1864: frozenset({"864", "8641"}),
    1866: frozenset({"912", "9121"}),
}
MERGE_SELF = {
    1718: "6263",
    1719: "6312",
    1739: "6721",
    1764: "7331",
    1765: "7341",
    1792: "8121",
    1797: "8212",
    1799: "8222",
    1817: "8341",
    1851: "8541",
    1860: "8621",
    1862: "8631",
    1864: "8641",
    1866: "9121",
}
# Counterpart proposal keys resolved once via cicw_proposal_keys(); frozen so CI need not rebuild seed plan.
MERGE_COUNTERPART = {
    1718: "bc0a4d662ca7b0941b18787498ac8e30f6e33685ce168afed16810ad25ee929e",
    1719: "cfc316505b91f515b236b535dd0c5eb1db0852793a57837ffcc5d855577f9829",
    1739: "2cd5380b46c25ebe366a610accb7c2a9896377f1679e394367c8976dc5513886",
    1764: "825fafb2cb0c673e04be97f4b5951a6ee10a97422da44fabc817689fa15d0b35",
    1765: "5b2b1b50650cc366df922ba1bb6f8a8b3c7d34b465948b859afc640e34ddaee7",
    1792: "e066088663d01d820767c3f0971b34fad3f3e906d1fc5237d06f74f293fb3ac2",
    1797: "cdd59d0734b914f44b5e6cb52823916adb204ac8c117ecfc2656b8261f512d03",
    1799: "229db50c74c354e18b6457206c64fb830f0d02fa46e3b2ae916af1743d349b31 | a3535fa6836e0e8e66cd0b9b64611148cf9b2c72b48a554d16d2301b942d74dd | 73d311c8d9d65139be81ac55e8cf8a4a6237baf090c49709d93b57caacae7c89",
    1817: "be3f8539a8d95a286eddcc524bd4392df0ff4652858972562bfbe6ee74ec5a15",
    1851: "96527325df7971e7f4c1d22c14a05d134d66fe99b39dcd22c452bd101e80424b",
    1860: "88c0dada461143da9fec7a2d6d7847c8d729b73c49e551a8b4a4b12688bf9e4d",
    1862: "6657f500b9d1bfe59b90e693c9d3fabc9d494f04b2f72d9ec0ff1560bc83fc17 | f5b741c5432767b697db7c6b3ed10a4f5da683bad0a3f3cd5934dad29d2e2cb3",
    1864: "2be093b6b695a920b45aac3c2b1c265a3b6cc36cd5900805256cf1213d30778b",
    1866: "63506a7a577baed3c7ee7e0e1e9945e209308bed1d4fcd9b7c50f22bb2d8db7e",
}
NAMED_KIND = {
    1694: ("강재제작설치 조립공사", "TASK"),
    1696: ("도장및방청공사", "TASK"),
    1697: ("터파기및되메우기공사", "TASK"),
    1702: ("공조기및팬공사", "PROCESS"),
    1718: ("냉온수기설치공사", "PROCESS"),
    1719: ("위생기구류공사", "PROCESS"),
    1722: ("소방설비기기류별설치공사", "TASK"),
    1739: ("세탁장비설비공사", "PROCESS"),
    1764: ("폐기물처리설비공사", "PROCESS"),
    1765: ("탈취설비공사", "PROCESS"),
    1792: ("배선및가선공사", "PROCESS"),
    1798: ("배전설비별기기류설치공사", "TASK"),
    1804: ("기타설비", "CLASSIFICATION"),
    1807: ("신호설비", "FACILITY_EQUIPMENT"),
    1810: ("전기설비기타공사", "CLASSIFICATION"),
    1817: ("예비전원설비공사", "PROCESS"),
    1818: ("비상용발전기설비", "FACILITY_EQUIPMENT"),
    1819: ("축전지설비", "FACILITY_EQUIPMENT"),
    1820: ("무정전전원설비", "FACILITY_EQUIPMENT"),
    1821: ("기타설비", "CLASSIFICATION"),
    1844: ("소방전기설비개별기기설치공사", "TASK"),
    1851: ("방범전기설비공사", "PROCESS"),
    1860: ("건축물전기설비공사 - - 대․중․소 분류대․중․소 분류", "PROCESS"),
    1862: ("기타전기설비공사", "PROCESS"),
    1864: ("안전관련전기설비공사", "PROCESS"),
    1865: ("기타공사", "CLASSIFICATION"),
    1866: ("기계설비시험 시운전공사", "PROCESS"),
    1872: ("통신설비시험 시운전공사", "PROCESS"),
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


# Completed GPT review of review_no 1692..1872 only.
# This is an explicit decision freeze, not a classifier.
PROCESS_KIND = _span(
    (1692, 1693), 1695, 1699, 1702, (1718, 1721), (1726, 1755), (1758, 1767),
    (1775, 1786), (1788, 1790), (1792, 1794), 1797, (1799, 1803), (1805, 1806),
    1808, (1811, 1814), (1816, 1817), (1822, 1830), (1832, 1833), (1835, 1843),
    (1846, 1858), (1860, 1864), (1866, 1872),
)
TASK_KIND = _span(
    1694, (1696, 1697), (1700, 1701), (1703, 1708), (1710, 1717), (1722, 1725),
    (1756, 1757), (1768, 1774), 1796, 1798, 1809, 1815, 1844,
)
METHOD_KIND: frozenset[int] = frozenset()
MATERIAL_KIND: frozenset[int] = frozenset()
FACILITY_KIND = _span(1807, (1818, 1820))
CLASSIFICATION_KIND = _span(
    1698, 1709, 1787, 1791, 1795, 1804, 1810, 1821, 1831, 1834, 1845, 1859, 1865,
)
AMBIGUOUS_KIND: frozenset[int] = frozenset()
MERGE_CANDIDATE = frozenset(MERGE_RELATIONS)


def _validate_coverage() -> None:
    union = (
        PROCESS_KIND | TASK_KIND | METHOD_KIND | MATERIAL_KIND
        | FACILITY_KIND | CLASSIFICATION_KIND | AMBIGUOUS_KIND
    )
    expected_range = frozenset(REVIEW_NOS)
    if union != expected_range:
        missing = sorted(expected_range - union)
        extra = sorted(union - expected_range)
        raise ValueError(f"004F coverage missing={missing} extra={extra}")
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
        "PROCESS": 127,
        "TASK": 37,
        "METHOD": 0,
        "MATERIAL_COMPONENT": 0,
        "FACILITY_EQUIPMENT": 4,
        "CLASSIFICATION": 13,
        "AMBIGUOUS": 0,
    }
    if sizes != expected:
        raise ValueError(f"004F kind set sizes {sizes}")
    overlap = 0
    buckets = (
        PROCESS_KIND, TASK_KIND, METHOD_KIND, MATERIAL_KIND,
        FACILITY_KIND, CLASSIFICATION_KIND, AMBIGUOUS_KIND,
    )
    for i, left in enumerate(buckets):
        for right in buckets[i + 1 :]:
            overlap += len(left & right)
    if overlap:
        raise ValueError(f"004F kind overlap {overlap}")
    if MERGE_CANDIDATE - PROCESS_KIND:
        raise ValueError("004F MERGE_CANDIDATE must be PROCESS")
    if set(MERGE_SELF) != set(MERGE_RELATIONS) or set(MERGE_COUNTERPART) != set(MERGE_RELATIONS):
        raise ValueError("004F MERGE_SELF drift")


def kind_for_004f(review_no: int) -> str:
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
    raise ValueError(f"no 004F kind for {review_no}")


def decision_for_004f(review_no: int, kind: str) -> str:
    if kind == "AMBIGUOUS":
        return "HOLD"
    if kind not in {"PROCESS", "TASK"}:
        return "REJECT"
    if review_no in MERGE_CANDIDATE:
        return "MERGE_CANDIDATE"
    return "KEEP_AS_DISTINCT"


def review_basis(kind: str, decision: str) -> str:
    return f"GPT_004F_{decision}_{kind}"


def merge_keys_for(review_no: int, source_key: str) -> str:
    if review_no not in MERGE_RELATIONS:
        return "EMPTY"
    members = MERGE_RELATIONS[review_no]
    if source_key not in members:
        raise ValueError(f"{review_no} source_key {source_key} not in {members}")
    if source_key != MERGE_SELF[review_no]:
        raise ValueError(f"{review_no} expected source_key {MERGE_SELF[review_no]}")
    return MERGE_COUNTERPART[review_no]


def assert_frozen_004f_pack() -> list[dict]:
    assert_frozen_004f()
    rows = load_tsv(PACK_004F_PATH)
    digest = compact_pack_sha(rows)
    if digest != FROZEN_COMPACT_SHA:
        raise ValueError("frozen 004F compact SHA mismatch")
    if [int(row["review_no"]) for row in rows] != REVIEW_NOS:
        raise ValueError("004F compact numbering drift")
    by_no = {int(row["review_no"]): row for row in rows}
    for no, key in MERGE_SELF.items():
        if by_no[no]["source_key"] != key:
            raise ValueError(f"{no} source_key mismatch")
    for no, (name, _) in NAMED_KIND.items():
        if by_no[no]["name"] != name:
            raise ValueError(f"{no} identity mismatch")
    return rows


def build_004f_gpt_manifest() -> list[dict]:
    frozen = assert_frozen_004f_pack()
    input_rows = load_leaf_batch(INPUT_004F_PATH)
    before = {row["review_no"]: row["current_semantic_kind"] for row in input_rows}
    rows = []
    for row in frozen:
        review_no = int(row["review_no"])
        kind = kind_for_004f(review_no)
        decision = decision_for_004f(review_no, kind)
        merge_keys = merge_keys_for(review_no, row["source_key"])
        if decision == "MERGE_CANDIDATE" and merge_keys == "EMPTY":
            raise ValueError(f"MERGE_CANDIDATE {review_no} missing counterparts")
        if decision != "MERGE_CANDIDATE" and merge_keys != "EMPTY":
            raise ValueError(f"non-merge {review_no} has merge keys")
        rows.append(
            {
                "review_no": str(review_no),
                "seed_proposal_key": row["seed_proposal_key"],
                "source_key": row["source_key"],
                "name": row["name"],
                "semantic_kind_before": before[row["review_no"]],
                "semantic_kind_after": kind,
                "semantic_review_decision": decision,
                "merge_candidate_keys": merge_keys,
                "review_basis": review_basis(kind, decision),
                "approval_state": APPROVAL_STATE,
            }
        )
    kinds = Counter(row["semantic_kind_after"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    expected_kinds = {
        "PROCESS": 127,
        "TASK": 37,
        "FACILITY_EQUIPMENT": 4,
        "CLASSIFICATION": 13,
    }
    if kinds != expected_kinds:
        raise ValueError(f"004F kind totals {kinds}")
    if decisions != {"KEEP_AS_DISTINCT": 150, "MERGE_CANDIDATE": 14, "REJECT": 17}:
        raise ValueError(f"004F decision totals {decisions}")
    if any(row["approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("approval_state must be NOT_APPROVED")
    if any(row["semantic_kind_before"] != "AMBIGUOUS" for row in rows):
        raise ValueError("004F kind_before must be AMBIGUOUS")
    if any(row["semantic_kind_after"] in {"METHOD", "MATERIAL_COMPONENT", "AMBIGUOUS"} for row in rows):
        raise ValueError("004F METHOD/MATERIAL/AMBIGUOUS must be 0")
    if any(row["semantic_review_decision"] == "HOLD" for row in rows):
        raise ValueError("004F HOLD must be 0")
    by_no = {int(row["review_no"]): row for row in rows}
    for no, (name, kind) in NAMED_KIND.items():
        if by_no[no]["name"] != name or by_no[no]["semantic_kind_after"] != kind:
            raise ValueError(f"{no} named freeze mismatch")
        if by_no[no]["name"].encode("utf-8") != name.encode("utf-8"):
            raise ValueError(f"{no} name bytes mutated")
    empty = [row for row in rows if int(row["review_no"]) not in MERGE_CANDIDATE]
    if len(empty) != 167 or any(row["merge_candidate_keys"] != "EMPTY" for row in empty):
        raise ValueError("004F extra merge keys")
    return rows


def build_004f_result(manifest: list[dict] | None = None) -> list[dict]:
    manifest = manifest if manifest is not None else build_004f_gpt_manifest()
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


def manifest_004f_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *GPT004F_FIELDS)


def write_004f_decision_artifacts() -> dict:
    manifest = build_004f_gpt_manifest()
    result = build_004f_result(manifest)
    write_tsv(manifest, GPT_004F_PATH, GPT004F_FIELDS)
    write_tsv(result, RESULT_004F_PATH, RESULT004F_FIELDS)
    return {"manifest": manifest, "result": result, "sha": manifest_004f_sha(manifest)}


def main() -> None:
    out = write_004f_decision_artifacts()
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-005F-DECISION-001",
                "004F_INPUT_SHA": FROZEN_004F_SHA,
                "004F_COMPACT_SHA": FROZEN_COMPACT_SHA,
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
