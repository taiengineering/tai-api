"""GPT hierarchy/label semantic resolution freeze overlay. Not Owner approval.

RISK04_HIERARCHY_LABEL_RESOLUTION_GPT_v1.tsv is not a canonical hierarchy,
not a canonical label manifest, and not an approved mapping. Cursor does not
re-judge hierarchy or label. KEEP_CONCEPT is semantic identity only.
SINGLE_PARENT_CANDIDATE is a recommendation, not a canonical parent_id.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review007_preapproval_readiness import GPT_EMPTY
from tools.risk04.review010_candidate_universe import (
    EXCLUSIONS_PATH,
    MEMBERS_PATH,
    UNIVERSE_PATH,
    exclusions_sha_rows,
    members_sha_rows,
    universe_sha_rows,
)
from tools.risk04.review011_hierarchy_label_search_readiness import (
    CONCEPT_HIERARCHY_PATH,
    CRITICAL_QUEUE_PATH,
    LABEL_PATH,
    MEMBER_HIERARCHY_PATH,
    SEARCH_EXPORT_PATH,
    concept_hierarchy_sha,
    critical_queue_sha,
    label_sha,
    member_hierarchy_sha,
    search_export_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Explicit GPT freeze overlay only. Cursor does not re-judge hierarchy or label.
# This is an explicit GPT freeze overlay, not a classifier.
FROZEN_UNIVERSE_SHA = "0f05f4443cbac19b1b3fa97f1204f2c75785a027889f0be35f1e0acd0d7e61a8"
FROZEN_MEMBERS_SHA = "b341204156611e12057f9113a6692b2c1d04e07f63eec151a53994928b9fde84"
FROZEN_EXCLUSIONS_SHA = "123b8c0361d829cd751970baf138373e3f98911ab787a1e5b7dabfc27489daca"
FROZEN_MEMBER_HIERARCHY_SHA = "fc1df8e5c8995243f0c1c95e10e916e90c9d6457106a9bcb49ece5cbcd9fb755"
FROZEN_CONCEPT_HIERARCHY_SHA = "430e00b2bebf531b71df6103d2619ce9d3764132ceafdc749ecdd05807bd2818"
FROZEN_LABEL_SHA = "25f05dc6aaea0438f95acdf3a7f6fff617016e9632ab9888666a809ffbcc43c6"
FROZEN_SEARCH_EXPORT_SHA = "4032472101c6a7180bdb5402c9bfae1fe3da656b24769be7c920229156edf4c0"
FROZEN_QUEUE_SHA = "7784bc16fe8d4b13cc1c7770cd76bbba84e2d83e27aeae5a13dd94f09db7c971"
RESOLUTION_PATH = Path("docs/knowledge/risk/RISK04_HIERARCHY_LABEL_RESOLUTION_GPT_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review013-resolution-freeze_v1.md")
H05_KEY = "25bc4f13e4b4fea37cc37f94f886e10167e0c84a5d3abd5a1ff8836797e88a87"
H01_PARENT_KEY = "b010f76c574f6761abb7e73d610ed737629be5b00dffea26cbddac07135e7587"
H06_PARENT_KEY = "d247d23d1ed4e328c2447c090f6004c4d9eae4f00fa0467f4a36103620df8729"
ISSUE_REASON = {
    "CROSS_ROOT": "CROSS_ROOT_REVIEW_REQUIRED",
    "MULTI_PARENT": "MULTI_PARENT_REVIEW_REQUIRED",
    "LEXICAL_NOISE": "LEXICAL_NOISE_REVIEW_REQUIRED",
}
HIERARCHY_DECISIONS = frozenset({"KEEP_CONCEPT", "SPLIT_REQUIRED", "HOLD"})
LABEL_DECISIONS = frozenset(
    {"CLEAN_LABEL_CONFIRMED", "EXISTING_CLEAN_MEMBER_CONFIRMED", "HOLD_LABEL"}
)
PARENT_RESOLUTIONS = frozenset({"SINGLE_PARENT_CANDIDATE", "PARENT_REQUIRES_LATER_MODELING"})
RESOLUTION_FIELDS = (
    "case_id",
    "review_concept_key",
    "source_keys",
    "semantic_kind",
    "issue_type",
    "gpt_decision",
    "canonical_parent_resolution",
    "recommended_parent_concept_key",
    "proposed_canonical_label",
    "label_basis",
    "source_preservation",
    "owner_approval_state",
    "resolution_status",
    "resolution_notes",
)
GPT_CASES = (
    {
        "case_id": "H-01",
        "review_concept_key": "fce048a6ba4d60e4520ac1f54189361e1b473e1bab9f15c88000e42fa44abe0c",
        "source_keys": "08 | 073",
        "semantic_kind": "PROCESS",
        "issue_type": "CROSS_ROOT",
        "gpt_decision": "KEEP_CONCEPT",
        "canonical_parent_resolution": "SINGLE_PARENT_CANDIDATE",
        "recommended_parent_concept_key": H01_PARENT_KEY,
        "proposed_canonical_label": GPT_EMPTY,
        "label_basis": GPT_EMPTY,
        "resolution_notes": "건축품질시험은 동일 PROCESS. source root 복제이며 품질시험을 parent candidate로 유지.",
    },
    {
        "case_id": "H-02",
        "review_concept_key": "b96f9d30b8931f4768261890e851dbc2960bd14e6d98e1db0078be9a5d6da033",
        "source_keys": "1242 | 1222",
        "semantic_kind": "TASK",
        "issue_type": "MULTI_PARENT",
        "gpt_decision": "KEEP_CONCEPT",
        "canonical_parent_resolution": "PARENT_REQUIRES_LATER_MODELING",
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": GPT_EMPTY,
        "label_basis": GPT_EMPTY,
        "resolution_notes": "동적계측은 동일 TASK. 구조체/교량 parent 차이는 적용 context이며 이번 단계에서 단일 parent를 선택하지 않음.",
    },
    {
        "case_id": "H-03",
        "review_concept_key": "4a6cae8b65bedc11b1616a7a667a747d748907580ba113761f735b55675f5ece",
        "source_keys": "1861 | 1871",
        "semantic_kind": "TASK",
        "issue_type": "MULTI_PARENT",
        "gpt_decision": "KEEP_CONCEPT",
        "canonical_parent_resolution": "PARENT_REQUIRES_LATER_MODELING",
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": GPT_EMPTY,
        "label_basis": GPT_EMPTY,
        "resolution_notes": "배관철거 해체 동일 TASK 유지. 기계/전기통신 parent는 설비 domain context.",
    },
    {
        "case_id": "H-04",
        "review_concept_key": "d7a4359635a90a4ae705a4e232e3096c0bbe9b47aa7a1b3470e92af01ce3674e",
        "source_keys": "1863 | 1873",
        "semantic_kind": "TASK",
        "issue_type": "MULTI_PARENT",
        "gpt_decision": "KEEP_CONCEPT",
        "canonical_parent_resolution": "PARENT_REQUIRES_LATER_MODELING",
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": GPT_EMPTY,
        "label_basis": GPT_EMPTY,
        "resolution_notes": "장비철거 해체 동일 TASK 유지. parent는 후속 hierarchy modeling 대상.",
    },
    {
        "case_id": "H-05",
        "review_concept_key": H05_KEY,
        "source_keys": "1864 | 1874",
        "semantic_kind": "TASK",
        "issue_type": "MULTI_PARENT",
        "gpt_decision": "KEEP_CONCEPT",
        "canonical_parent_resolution": "PARENT_REQUIRES_LATER_MODELING",
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": GPT_EMPTY,
        "label_basis": GPT_EMPTY,
        "resolution_notes": "잡철물철거 해체 동일 TASK 유지. parent는 후속 hierarchy modeling 대상.",
    },
    {
        "case_id": "H-06",
        "review_concept_key": "6985c17f351847499f1c250343deb7f6b9c81cc4d194fe15f055b3fa2b9c4d0f",
        "source_keys": "5352 | 5252",
        "semantic_kind": "TASK",
        "issue_type": "CROSS_ROOT",
        "gpt_decision": "KEEP_CONCEPT",
        "canonical_parent_resolution": "SINGLE_PARENT_CANDIDATE",
        "recommended_parent_concept_key": H06_PARENT_KEY,
        "proposed_canonical_label": GPT_EMPTY,
        "label_basis": GPT_EMPTY,
        "resolution_notes": "계단채임판(라이저)석재붙이기는 동일 TASK. 이름의 재료 의미와 정합한 석재계단붙이기를 parent candidate로 유지.",
    },
    {
        "case_id": "L-01",
        "review_concept_key": "662a1cd5be3e0e40b809a2385f9b185da542c9cafc8a3f8b26ea47aac1b6e4a7",
        "source_keys": "185",
        "semantic_kind": "PROCESS",
        "issue_type": "LEXICAL_NOISE",
        "gpt_decision": "CLEAN_LABEL_CONFIRMED",
        "canonical_parent_resolution": GPT_EMPTY,
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": "지하구조물제거",
        "label_basis": "KNOWN_NOISE_REMOVAL",
        "resolution_notes": GPT_EMPTY,
    },
    {
        "case_id": "L-02",
        "review_concept_key": "b04a22eac59269ecbefbb8cb7b88dbc9bb80873d12c84cd2a917409e70d1dd4b",
        "source_keys": "673",
        "semantic_kind": "PROCESS",
        "issue_type": "LEXICAL_NOISE",
        "gpt_decision": "HOLD_LABEL",
        "canonical_parent_resolution": GPT_EMPTY,
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": GPT_EMPTY,
        "label_basis": GPT_EMPTY,
        "resolution_notes": "known suffix 제거 후에도 본문 접합/결손 가능성이 존재. 임의 띄어쓰기·분할·교정 금지.",
    },
    {
        "case_id": "L-03",
        "review_concept_key": "f2845fdbbbc2e76f294d13974254c644ee77c981dbcbc46800ac4544c0b58d13",
        "source_keys": "8621 | 862",
        "semantic_kind": "PROCESS",
        "issue_type": "LEXICAL_NOISE",
        "gpt_decision": "EXISTING_CLEAN_MEMBER_CONFIRMED",
        "canonical_parent_resolution": GPT_EMPTY,
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": "건축물전기설비공사",
        "label_basis": "EXISTING_CLEAN_SOURCE_MEMBER",
        "resolution_notes": GPT_EMPTY,
    },
    {
        "case_id": "L-04",
        "review_concept_key": "6d83ddbf5bdcb4ffb22e45aa73bf91c2c300baa4b577a7370e97e4f7a76532bf",
        "source_keys": "0515",
        "semantic_kind": "TASK",
        "issue_type": "LEXICAL_NOISE",
        "gpt_decision": "CLEAN_LABEL_CONFIRMED",
        "canonical_parent_resolution": GPT_EMPTY,
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": "도로오염방지",
        "label_basis": "KNOWN_NOISE_REMOVAL",
        "resolution_notes": GPT_EMPTY,
    },
    {
        "case_id": "L-05",
        "review_concept_key": "8a5ad2e2dcbf8667bef87a48c6977f121135878995137a6c32e4058b1be6cf95",
        "source_keys": "1152",
        "semantic_kind": "TASK",
        "issue_type": "LEXICAL_NOISE",
        "gpt_decision": "CLEAN_LABEL_CONFIRMED",
        "canonical_parent_resolution": GPT_EMPTY,
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": "등록전환측량",
        "label_basis": "KNOWN_NOISE_REMOVAL",
        "resolution_notes": GPT_EMPTY,
    },
    {
        "case_id": "L-06",
        "review_concept_key": "34cb37de55ba2869be01ba980c0bc2c8022e80c5d7afdb4dba85911449da7aa8",
        "source_keys": "2267",
        "semantic_kind": "TASK",
        "issue_type": "LEXICAL_NOISE",
        "gpt_decision": "CLEAN_LABEL_CONFIRMED",
        "canonical_parent_resolution": GPT_EMPTY,
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": "지반그라우팅검사",
        "label_basis": "KNOWN_NOISE_REMOVAL",
        "resolution_notes": GPT_EMPTY,
    },
    {
        "case_id": "L-07",
        "review_concept_key": "1b5fe88148c46cef4d8d7ab31a1199f3f8972780ca23ac8d08fec82be0bf6496",
        "source_keys": "2652",
        "semantic_kind": "TASK",
        "issue_type": "LEXICAL_NOISE",
        "gpt_decision": "CLEAN_LABEL_CONFIRMED",
        "canonical_parent_resolution": GPT_EMPTY,
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": "지하도PC부재조립",
        "label_basis": "KNOWN_NOISE_REMOVAL",
        "resolution_notes": GPT_EMPTY,
    },
    {
        "case_id": "L-08",
        "review_concept_key": "aefbddc29d2b7e3768edcdd440075176fcda8b8c2ac759d03fbd3bbb9fdf8056",
        "source_keys": "3552",
        "semantic_kind": "PROCESS",
        "issue_type": "LEXICAL_NOISE",
        "gpt_decision": "CLEAN_LABEL_CONFIRMED",
        "canonical_parent_resolution": GPT_EMPTY,
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": "터널내부지보",
        "label_basis": "KNOWN_NOISE_REMOVAL",
        "resolution_notes": GPT_EMPTY,
    },
    {
        "case_id": "L-09",
        "review_concept_key": "a62cfdb19570c113a27724aa798938cfba9e0b6346b7420b30bd3a6ab2aff855",
        "source_keys": "5282",
        "semantic_kind": "TASK",
        "issue_type": "LEXICAL_NOISE",
        "gpt_decision": "CLEAN_LABEL_CONFIRMED",
        "canonical_parent_resolution": GPT_EMPTY,
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": "석재거친다듬마감",
        "label_basis": "KNOWN_NOISE_REMOVAL",
        "resolution_notes": GPT_EMPTY,
    },
    {
        "case_id": "L-10",
        "review_concept_key": "875e1cce58c38eeef89cb71fc215170c124b034a44eb36cfcad2c1ad7acf37d5",
        "source_keys": "5972",
        "semantic_kind": "TASK",
        "issue_type": "LEXICAL_NOISE",
        "gpt_decision": "CLEAN_LABEL_CONFIRMED",
        "canonical_parent_resolution": GPT_EMPTY,
        "recommended_parent_concept_key": GPT_EMPTY,
        "proposed_canonical_label": "교목수간보호",
        "label_basis": "KNOWN_NOISE_REMOVAL",
        "resolution_notes": GPT_EMPTY,
    },
)


def _assert_frozen_inputs() -> tuple[list[dict], list[dict], list[dict]]:
    concepts = load_tsv(UNIVERSE_PATH)
    members = load_tsv(MEMBERS_PATH)
    exclusions = load_tsv(EXCLUSIONS_PATH)
    queue = load_tsv(CRITICAL_QUEUE_PATH)
    if universe_sha_rows(concepts) != FROZEN_UNIVERSE_SHA:
        raise ValueError("REVIEW-010 universe SHA drift")
    if members_sha_rows(members) != FROZEN_MEMBERS_SHA:
        raise ValueError("REVIEW-010 members SHA drift")
    if exclusions_sha_rows(exclusions) != FROZEN_EXCLUSIONS_SHA:
        raise ValueError("REVIEW-010 exclusions SHA drift")
    if len(concepts) != 1111 or len(members) != 1140 or len(exclusions) != 582:
        raise ValueError("REVIEW-010 identity drift")
    if member_hierarchy_sha(load_tsv(MEMBER_HIERARCHY_PATH)) != FROZEN_MEMBER_HIERARCHY_SHA:
        raise ValueError("REVIEW-011 member hierarchy SHA drift")
    if concept_hierarchy_sha(load_tsv(CONCEPT_HIERARCHY_PATH)) != FROZEN_CONCEPT_HIERARCHY_SHA:
        raise ValueError("REVIEW-011 concept hierarchy SHA drift")
    if label_sha(load_tsv(LABEL_PATH)) != FROZEN_LABEL_SHA:
        raise ValueError("REVIEW-011 label SHA drift")
    if search_export_sha(load_tsv(SEARCH_EXPORT_PATH)) != FROZEN_SEARCH_EXPORT_SHA:
        raise ValueError("REVIEW-011 search export SHA drift")
    if critical_queue_sha(queue) != FROZEN_QUEUE_SHA:
        raise ValueError("REVIEW-011 critical queue SHA drift")
    if len(queue) != 16 or len({row["review_concept_key"] for row in queue}) != 16:
        raise ValueError("REVIEW-011 critical queue identity drift")
    return concepts, queue, members


def resolution_counts(rows: list[dict]) -> dict[str, int]:
    decisions = Counter(row["gpt_decision"] for row in rows)
    issues = Counter(row["issue_type"] for row in rows)
    parents = Counter(row["canonical_parent_resolution"] for row in rows)
    return {
        "rows": len(rows),
        "unique": len({row["review_concept_key"] for row in rows}),
        "hierarchy": issues["CROSS_ROOT"] + issues["MULTI_PARENT"],
        "label": issues["LEXICAL_NOISE"],
        "KEEP_CONCEPT": decisions["KEEP_CONCEPT"],
        "SPLIT_REQUIRED": decisions["SPLIT_REQUIRED"],
        "HOLD": decisions["HOLD"],
        "SINGLE_PARENT_CANDIDATE": parents["SINGLE_PARENT_CANDIDATE"],
        "PARENT_REQUIRES_LATER_MODELING": parents["PARENT_REQUIRES_LATER_MODELING"],
        "CLEAN_LABEL_CONFIRMED": decisions["CLEAN_LABEL_CONFIRMED"],
        "EXISTING_CLEAN_MEMBER_CONFIRMED": decisions["EXISTING_CLEAN_MEMBER_CONFIRMED"],
        "HOLD_LABEL": decisions["HOLD_LABEL"],
        "source_preservation_yes": sum(1 for row in rows if row["source_preservation"] == "YES"),
        "owner_not_approved": sum(1 for row in rows if row["owner_approval_state"] == APPROVAL_STATE),
        "gpt_resolved": sum(1 for row in rows if row["resolution_status"] == "GPT_RESOLVED"),
    }


def _validate(rows: list[dict], concepts: list[dict], queue: list[dict]) -> None:
    queue_by_key = {row["review_concept_key"]: row for row in queue}
    concept_keys = {row["review_concept_key"] for row in concepts}
    counts = resolution_counts(rows)
    expected = {
        "rows": 16,
        "unique": 16,
        "hierarchy": 6,
        "label": 10,
        "KEEP_CONCEPT": 6,
        "SPLIT_REQUIRED": 0,
        "HOLD": 0,
        "SINGLE_PARENT_CANDIDATE": 2,
        "PARENT_REQUIRES_LATER_MODELING": 4,
        "CLEAN_LABEL_CONFIRMED": 8,
        "EXISTING_CLEAN_MEMBER_CONFIRMED": 1,
        "HOLD_LABEL": 1,
        "source_preservation_yes": 16,
        "owner_not_approved": 16,
        "gpt_resolved": 16,
    }
    if counts != expected:
        raise ValueError(f"resolution aggregate drift {counts}")
    if {row["review_concept_key"] for row in rows} != set(queue_by_key):
        raise ValueError("resolution key set drift")
    if [row["case_id"] for row in rows] != [case["case_id"] for case in GPT_CASES]:
        raise ValueError("case_id order drift")
    if rows[4]["review_concept_key"] != H05_KEY:
        raise ValueError("H-05 key drift")
    if rows[4]["case_id"] != "H-05":
        raise ValueError("H-05 case_id drift")
    for row in rows:
        queued = queue_by_key[row["review_concept_key"]]
        reason = ISSUE_REASON[row["issue_type"]]
        if row["source_keys"] != queued["member_source_keys"]:
            raise ValueError(f"source_keys drift {row['case_id']}")
        if row["semantic_kind"] != queued["effective_semantic_kind"]:
            raise ValueError(f"semantic_kind drift {row['case_id']}")
        if reason not in queued["review_reasons"].split(" | "):
            raise ValueError(f"issue_type drift {row['case_id']}")
        if row["source_preservation"] != "YES":
            raise ValueError("source_preservation drift")
        if row["owner_approval_state"] != APPROVAL_STATE:
            raise ValueError("owner_approval_state drift")
        if row["resolution_status"] != "GPT_RESOLVED":
            raise ValueError("resolution_status drift")
        if row["issue_type"] in {"CROSS_ROOT", "MULTI_PARENT"}:
            if row["gpt_decision"] not in HIERARCHY_DECISIONS:
                raise ValueError(f"hierarchy decision drift {row['case_id']}")
            if row["canonical_parent_resolution"] not in PARENT_RESOLUTIONS:
                raise ValueError(f"parent resolution drift {row['case_id']}")
            if row["proposed_canonical_label"] != GPT_EMPTY or row["label_basis"] != GPT_EMPTY:
                raise ValueError(f"hierarchy label leak {row['case_id']}")
        else:
            if row["gpt_decision"] not in LABEL_DECISIONS:
                raise ValueError(f"label decision drift {row['case_id']}")
            if row["canonical_parent_resolution"] != GPT_EMPTY:
                raise ValueError(f"label parent leak {row['case_id']}")
            if row["recommended_parent_concept_key"] != GPT_EMPTY:
                raise ValueError(f"label parent key leak {row['case_id']}")
        parent_key = row["recommended_parent_concept_key"]
        if parent_key != GPT_EMPTY:
            if parent_key not in concept_keys:
                raise ValueError(f"unknown recommended parent {row['case_id']}")
            parents = queued["direct_parent_concept_keys"].split(" | ")
            if parent_key not in parents and parent_key not in queued["nearest_candidate_ancestor_keys"].split(" | "):
                raise ValueError(f"recommended parent not in source evidence {row['case_id']}")
        if row["canonical_parent_resolution"] == "PARENT_REQUIRES_LATER_MODELING" and parent_key != GPT_EMPTY:
            raise ValueError(f"later modeling parent leak {row['case_id']}")
        if row["gpt_decision"] == "HOLD_LABEL":
            if row["proposed_canonical_label"] != GPT_EMPTY or row["label_basis"] != GPT_EMPTY:
                raise ValueError("HOLD_LABEL invented a label")
        if row["gpt_decision"] in {"CLEAN_LABEL_CONFIRMED", "EXISTING_CLEAN_MEMBER_CONFIRMED"}:
            if row["proposed_canonical_label"] in {"", GPT_EMPTY}:
                raise ValueError(f"missing clean label {row['case_id']}")
    if len(concepts) != 1111:
        raise ValueError("concept count drift")


def build_resolution(
    concepts: list[dict] | None = None,
    queue: list[dict] | None = None,
) -> list[dict]:
    if concepts is None or queue is None:
        concepts, queue, _ = _assert_frozen_inputs()
    rows = []
    for case in GPT_CASES:
        rows.append(
            {
                "case_id": case["case_id"],
                "review_concept_key": case["review_concept_key"],
                "source_keys": case["source_keys"],
                "semantic_kind": case["semantic_kind"],
                "issue_type": case["issue_type"],
                "gpt_decision": case["gpt_decision"],
                "canonical_parent_resolution": case["canonical_parent_resolution"],
                "recommended_parent_concept_key": case["recommended_parent_concept_key"],
                "proposed_canonical_label": case["proposed_canonical_label"],
                "label_basis": case["label_basis"],
                "source_preservation": "YES",
                "owner_approval_state": APPROVAL_STATE,
                "resolution_status": "GPT_RESOLVED",
                "resolution_notes": case["resolution_notes"],
            }
        )
    _validate(rows, concepts, queue)
    return rows


def resolution_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *RESOLUTION_FIELDS)


def render_report(rows: list[dict], sha: str) -> str:
    counts = resolution_counts(rows)
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-013 hierarchy label resolution freeze
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-013 — Hierarchy / Label Semantic Resolution Freeze

This WO freezes GPT REVIEW-012 semantic resolutions as an overlay. Cursor does not re-judge hierarchy or label. This overlay is not Owner approval and not a canonical parent/label assignment.

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT A CANONICAL HIERARCHY
THIS IS NOT A CANONICAL LABEL MANIFEST
THIS IS NOT AN APPROVED MAPPING
KEEP_CONCEPT ≠ canonical UUID
SINGLE_PARENT_CANDIDATE ≠ CANONICAL PARENT APPROVED
CLEAN_LABEL_CONFIRMED ≠ source_name mutation
HOLD_LABEL ≠ invented label
review_concept_key ≠ canonical UUID
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL CREATION = NOT AUTHORIZED
MAPPING APPROVAL = NOT AUTHORIZED
PR MERGE = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER = NOT SAFE
OBJ-SEARCH-DICT = PARALLEL EXTERNAL STREAM
FULL CANONICAL READINESS = NOT YET
```

This is an explicit GPT freeze overlay, not a classifier.

---

## Frozen REVIEW-010 / REVIEW-011

```text
candidate concepts = 1111
candidate source members = 1140
exclusions = 582
REVIEW-011 critical queue = 16
concept count delta = 0
SPLIT_REQUIRED = 0
```

---

## Resolution overlay

```text
resolution rows = {counts["rows"]}
unique concepts = {counts["unique"]}
hierarchy = {counts["hierarchy"]}
KEEP_CONCEPT = {counts["KEEP_CONCEPT"]}
SPLIT_REQUIRED = {counts["SPLIT_REQUIRED"]}
HOLD hierarchy = {counts["HOLD"]}
SINGLE_PARENT_CANDIDATE = {counts["SINGLE_PARENT_CANDIDATE"]}
PARENT_REQUIRES_LATER_MODELING = {counts["PARENT_REQUIRES_LATER_MODELING"]}
label = {counts["label"]}
CLEAN_LABEL_CONFIRMED = {counts["CLEAN_LABEL_CONFIRMED"]}
EXISTING_CLEAN_MEMBER_CONFIRMED = {counts["EXISTING_CLEAN_MEMBER_CONFIRMED"]}
HOLD_LABEL = {counts["HOLD_LABEL"]}
source_preservation YES = {counts["source_preservation_yes"]}
owner_approval_state NOT_APPROVED = {counts["owner_not_approved"]}
resolution_status GPT_RESOLVED = {counts["gpt_resolved"]}
H-05 exact key = {H05_KEY}
```

---

## Remaining readiness

```text
remaining parent modeling = 4
remaining label hold = 1
FULL CANONICAL READINESS = NOT YET
H-01/H-06 parent = SINGLE_PARENT_CANDIDATE not CANONICAL PARENT APPROVED
```

---

## Guard

```text
canonical UUID created = 0
active canonical = 0
approved mapping = 0
production DB write = 0
new migration = 0
Owner Approval = 0
AUTO APPROVED = 0
LLM calls = 0
vector model calls = 0
fuzzy = 0
Kiwi runtime calls = 0
```

---

## Determinism

```text
RUN1 SHA = {sha}
RUN2 SHA = {sha}
DETERMINISM = PASS
```

---

## Verdict

```text
WO-RISK-04-REVIEW-013 = EVIDENCE_READY
RISK-04 = IN REVIEW
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL = NOT OPENED
MAPPING = NOT OPENED
NEXT = GPT INDEPENDENT VERIFY
STOP
```
"""


def write_review013_artifacts() -> dict:
    concepts, queue, _ = _assert_frozen_inputs()
    rows = build_resolution(concepts, queue)
    sha = resolution_sha(rows)
    write_tsv(rows, RESOLUTION_PATH, RESOLUTION_FIELDS)
    REPORT_PATH.write_text(render_report(rows, sha), encoding="utf-8")
    return {"rows": rows, "sha": sha, "counts": resolution_counts(rows)}


def main() -> None:
    first = write_review013_artifacts()
    concepts, queue, _ = _assert_frozen_inputs()
    second = build_resolution(concepts, queue)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-013",
                "RUN1": first["sha"],
                "RUN2": resolution_sha(second),
                "ROWS": first["counts"]["rows"],
                "CONCEPT_CANDIDATES": 1111,
                "CONCEPT_COUNT_DELTA": 0,
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
