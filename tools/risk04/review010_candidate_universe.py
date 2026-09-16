"""Pre-approval candidate universe projection. Not Owner approval and not a classifier.

RISK04_PREAPPROVAL_CANDIDATE_UNIVERSE_v1.tsv is not an Owner-approved seed
manifest, not a canonical seed, and not a DB ingest manifest. review_concept_key
is a pre-approval review identity only. Cursor does not select a survivor,
canonical name, canonical parent, or UUID.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

from tools.risk04.review006_completion_audit import EXPECTED_DECISIONS, EXPECTED_KINDS
from tools.risk04.review007_preapproval_readiness import (
    CONTEXT_INPUTS,
    FROZEN_AUDIT_SHA,
    HOLD_EVIDENCE_PATH,
    LANE_PATH,
    MERGE_EVIDENCE_PATH,
    MISSING,
    hold_sha,
    lane_sha,
    load_frozen_audit,
    merge_sha,
)
from tools.risk04.review008_resolution_context import (
    FROZEN_HOLD_SHA,
    FROZEN_LANE_SHA,
    FROZEN_MERGE_SHA,
    HOLD_CONTEXT_PATH,
    MERGE_CONTEXT_PATH,
    hold_context_sha,
    merge_context_sha,
)
from tools.risk04.review009_resolution_freeze import (
    EQUIVALENCE_GROUPS,
    FROZEN_HOLD_CONTEXT_SHA,
    FROZEN_MERGE_CONTEXT_SHA,
    HOLD_GPT_PATH,
    HOLD_METHOD_REJECT,
    HOLD_RETAIN,
    HOLD_TASK_KEEP,
    KEEP_SEPARATE,
    MERGE_GPT_PATH,
    hold_gpt_sha,
    merge_gpt_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Deterministic projection of frozen REVIEW-009 overlay only.
# This is a deterministic pre-approval projection, not a classifier.
FROZEN_MERGE_GPT_SHA = "906ada1b158ca43915c59591a94aba0aa908476b5c6c8f19c759c2cbd1c1086f"
FROZEN_HOLD_GPT_SHA = "a73c2d2708eaf653a95280ab8e769d1e3c2690bddb3eb5c80d08c55d8e725dec"
UNIVERSE_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_CANDIDATE_UNIVERSE_v1.tsv")
MEMBERS_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_CANDIDATE_MEMBERS_v1.tsv")
EXCLUSIONS_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_EXCLUSIONS_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review010-preapproval-candidate-universe_v1.md")
CONCEPT_PREFIX = "RISK04_PREAPPROVAL_CONCEPT_V1"
CIC_W_IDS = {None, "", "CIC_W"}
CANONICAL_KINDS = frozenset({"PROCESS", "TASK"})

UNIVERSE_FIELDS = (
    "review_order",
    "review_concept_key",
    "concept_form",
    "effective_semantic_kind",
    "candidate_basis",
    "member_count",
    "member_source_keys",
    "member_seed_proposal_keys",
    "member_names",
    "member_hierarchy_levels",
    "member_source_paths",
    "member_review_refs",
    "owner_approval_state",
)
MEMBER_FIELDS = (
    "review_concept_key",
    "concept_form",
    "source_key",
    "seed_proposal_key",
    "name",
    "hierarchy_level",
    "source_path",
    "effective_semantic_kind",
    "source_candidate_origin",
    "owner_approval_state",
)
EXCLUSION_FIELDS = (
    "source_key",
    "seed_proposal_key",
    "name",
    "hierarchy_level",
    "source_path",
    "effective_semantic_kind",
    "exclusion_lane",
    "exclusion_basis",
    "owner_approval_state",
)


def _present(value: str | None) -> str:
    if value is None or value == "":
        return MISSING
    return value


def _join(parts: list[str]) -> str:
    return " | ".join(parts)


def review_concept_key(member_proposal_keys: list[str]) -> str:
    payload = CONCEPT_PREFIX + "\n" + "\n".join(sorted(member_proposal_keys))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _paths_by_key() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in CONTEXT_INPUTS:
        for row in load_tsv(path):
            if row.get("source_id") not in CIC_W_IDS:
                continue
            out[row["source_key"]] = _present(row.get("source_path"))
    return out


def _assert_frozen() -> tuple[list[dict], list[dict], list[dict]]:
    audit = load_frozen_audit()
    lanes = load_tsv(LANE_PATH)
    merge_gpt = load_tsv(MERGE_GPT_PATH)
    hold_gpt = load_tsv(HOLD_GPT_PATH)
    if Counter(row["semantic_kind"] for row in audit) != EXPECTED_KINDS:
        raise ValueError("frozen kind drift")
    if Counter(row["semantic_review_decision"] for row in audit) != EXPECTED_DECISIONS:
        raise ValueError("frozen decision drift")
    if lane_sha(lanes) != FROZEN_LANE_SHA:
        raise ValueError("REVIEW-007 lane SHA drift")
    if merge_sha(load_tsv(MERGE_EVIDENCE_PATH)) != FROZEN_MERGE_SHA:
        raise ValueError("REVIEW-007 MERGE SHA drift")
    if hold_sha(load_tsv(HOLD_EVIDENCE_PATH)) != FROZEN_HOLD_SHA:
        raise ValueError("REVIEW-007 HOLD SHA drift")
    if merge_context_sha(load_tsv(MERGE_CONTEXT_PATH)) != FROZEN_MERGE_CONTEXT_SHA:
        raise ValueError("REVIEW-008 MERGE context SHA drift")
    if hold_context_sha(load_tsv(HOLD_CONTEXT_PATH)) != FROZEN_HOLD_CONTEXT_SHA:
        raise ValueError("REVIEW-008 HOLD context SHA drift")
    if merge_gpt_sha(merge_gpt) != FROZEN_MERGE_GPT_SHA:
        raise ValueError("REVIEW-009 MERGE GPT SHA drift")
    if hold_gpt_sha(hold_gpt) != FROZEN_HOLD_GPT_SHA:
        raise ValueError("REVIEW-009 HOLD GPT SHA drift")
    return audit, merge_gpt, hold_gpt


def _group_index() -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for group in EQUIVALENCE_GROUPS:
        frozen = tuple(group)
        for key in frozen:
            if key in out:
                raise ValueError(f"group overlap {key}")
            out[key] = frozen
    if len(EQUIVALENCE_GROUPS) != 28:
        raise ValueError("group count drift")
    members = {key for group in EQUIVALENCE_GROUPS for key in group}
    if len(members) != 57:
        raise ValueError("group member drift")
    if "825" in members:
        raise ValueError("825 in G02")
    if set(EQUIVALENCE_GROUPS[7]) != {"831", "8311"}:
        raise ValueError("G08 split drift")
    if set(EQUIVALENCE_GROUPS[15]) != {"822", "8222"}:
        raise ValueError("G16 split drift")
    return out


def _effective_rows(audit: list[dict], merge_gpt: list[dict], hold_gpt: list[dict]) -> list[dict]:
    hold_by_key = {row["source_key"]: row for row in hold_gpt}
    merge_by_key = {row["source_key"]: row for row in merge_gpt}
    confirmed = {row["source_key"] for row in merge_gpt if row["gpt_merge_resolution"] == "MERGE_CONFIRMED"}
    keep_sep = {row["source_key"] for row in merge_gpt if row["gpt_merge_resolution"] == "KEEP_SEPARATE"}
    hold_task = {row["source_key"] for row in hold_gpt if row["gpt_resolved_review_decision"] == "KEEP_AS_DISTINCT"}
    hold_method = {row["source_key"] for row in hold_gpt if row["gpt_resolved_review_decision"] == "REJECT"}
    hold_retain = {row["source_key"] for row in hold_gpt if row["gpt_hold_resolution"] == "RETAIN_HOLD"}
    if confirmed != {row["source_key"] for row in merge_gpt} - keep_sep:
        raise ValueError("MERGE overlay drift")
    if set(keep_sep) != {item[0] for item in KEEP_SEPARATE.values()}:
        raise ValueError("KEEP_SEPARATE overlay drift")
    if hold_task != {item[0] for item in HOLD_TASK_KEEP.values()}:
        raise ValueError("HOLD TASK overlay drift")
    if hold_method != {item[0] for item in HOLD_METHOD_REJECT.values()}:
        raise ValueError("HOLD METHOD overlay drift")
    if hold_retain != {item[0] for item in HOLD_RETAIN.values()}:
        raise ValueError("HOLD RETAIN overlay drift")
    rows = []
    for ordinal, row in enumerate(audit, start=1):
        hold = hold_by_key.get(row["source_key"])
        merge = merge_by_key.get(row["source_key"])
        if hold is not None:
            kind = hold["gpt_resolved_semantic_kind"]
            decision = hold["gpt_resolved_review_decision"]
        else:
            kind = row["semantic_kind"]
            decision = row["semantic_review_decision"]
        if row["source_key"] in hold_task:
            origin = "HOLD_RESOLVED_TASK"
            basis = "HOLD_RESOLVED_TASK"
            lane = "CANDIDATE"
            exclusion_basis = ""
        elif row["source_key"] in keep_sep:
            origin = "MERGE_KEEP_SEPARATE"
            basis = "KEEP_SEPARATE"
            lane = "CANDIDATE"
            exclusion_basis = ""
        elif row["source_key"] in confirmed:
            origin = "MERGE_CONFIRMED"
            basis = "MERGE_CONFIRMED_GROUP"
            lane = "CANDIDATE"
            exclusion_basis = ""
        elif decision == "KEEP_AS_DISTINCT":
            origin = "ORIGINAL_KEEP"
            basis = "KEEP_AS_DISTINCT"
            lane = "CANDIDATE"
            exclusion_basis = ""
        elif row["source_key"] in hold_retain:
            origin = ""
            basis = ""
            lane = "HOLD_RETAIN"
            exclusion_basis = "HOLD_RETAIN"
        elif row["source_key"] in hold_method:
            origin = ""
            basis = ""
            lane = "REFERENCE_ONLY"
            exclusion_basis = "HOLD_RESOLVED_METHOD"
        elif decision == "REJECT":
            origin = ""
            basis = ""
            lane = "REFERENCE_ONLY"
            exclusion_basis = "ORIGINAL_REJECT"
        else:
            raise ValueError(f"unresolved overlay {row['source_key']}")
        rows.append(
            {
                "ordinal": ordinal,
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "hierarchy_level": row["hierarchy_level"],
                "source_review_stage": row["source_review_stage"],
                "source_review_no": row["source_review_no"],
                "effective_semantic_kind": kind,
                "origin": origin,
                "basis": basis,
                "lane": lane,
                "exclusion_basis": exclusion_basis,
            }
        )
    return rows


def _member_bundle(members: list[dict], paths: dict[str, str]) -> dict[str, str]:
    ordered = sorted(members, key=lambda row: row["seed_proposal_key"])
    return {
        "member_count": str(len(ordered)),
        "member_source_keys": _join([row["source_key"] for row in ordered]),
        "member_seed_proposal_keys": _join([row["seed_proposal_key"] for row in ordered]),
        "member_names": _join([row["name"] for row in ordered]),
        "member_hierarchy_levels": _join([row["hierarchy_level"] for row in ordered]),
        "member_source_paths": _join([paths.get(row["source_key"], MISSING) for row in ordered]),
        "member_review_refs": _join(
            [f"{row['source_review_stage']}:{row['source_review_no']}" for row in ordered]
        ),
    }


def build_candidate_universe(
    audit: list[dict] | None = None,
    merge_gpt: list[dict] | None = None,
    hold_gpt: list[dict] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    if audit is None or merge_gpt is None or hold_gpt is None:
        audit, merge_gpt, hold_gpt = _assert_frozen()
    paths = _paths_by_key()
    effective = _effective_rows(audit, merge_gpt, hold_gpt)
    by_key = {row["source_key"]: row for row in effective}
    groups = _group_index()
    candidates = [row for row in effective if row["effective_semantic_kind"] in CANONICAL_KINDS]
    exclusions_src = [row for row in effective if row["effective_semantic_kind"] not in CANONICAL_KINDS]
    grouped_keys = set(groups)
    concepts: list[dict] = []
    members: list[dict] = []
    seen_members: set[str] = set()
    for group in EQUIVALENCE_GROUPS:
        group_rows = [by_key[key] for key in group]
        kinds = {row["effective_semantic_kind"] for row in group_rows}
        if kinds != {"PROCESS"} and kinds != {"TASK"}:
            raise ValueError(f"mixed group kinds {group}")
        if any(row["source_key"] not in {item["source_key"] for item in candidates} for row in group_rows):
            raise ValueError(f"non-candidate group member {group}")
        key = review_concept_key([row["seed_proposal_key"] for row in group_rows])
        bundle = _member_bundle(group_rows, paths)
        concepts.append(
            {
                "review_order": str(min(row["ordinal"] for row in group_rows)),
                "review_concept_key": key,
                "concept_form": "EQUIVALENCE_GROUP",
                "effective_semantic_kind": next(iter(kinds)),
                "candidate_basis": "MERGE_CONFIRMED_GROUP",
                **bundle,
                "owner_approval_state": APPROVAL_STATE,
            }
        )
        for row in sorted(group_rows, key=lambda item: item["ordinal"]):
            if row["source_key"] in seen_members:
                raise ValueError(f"duplicate member {row['source_key']}")
            seen_members.add(row["source_key"])
            members.append(
                {
                    "review_concept_key": key,
                    "concept_form": "EQUIVALENCE_GROUP",
                    "source_key": row["source_key"],
                    "seed_proposal_key": row["seed_proposal_key"],
                    "name": row["name"],
                    "hierarchy_level": row["hierarchy_level"],
                    "source_path": paths.get(row["source_key"], MISSING),
                    "effective_semantic_kind": row["effective_semantic_kind"],
                    "source_candidate_origin": row["origin"],
                    "owner_approval_state": APPROVAL_STATE,
                }
            )
    for row in candidates:
        if row["source_key"] in grouped_keys:
            continue
        if row["source_key"] in seen_members:
            raise ValueError(f"singleton duplicate {row['source_key']}")
        seen_members.add(row["source_key"])
        key = review_concept_key([row["seed_proposal_key"]])
        bundle = _member_bundle([row], paths)
        concepts.append(
            {
                "review_order": str(row["ordinal"]),
                "review_concept_key": key,
                "concept_form": "SINGLETON",
                "effective_semantic_kind": row["effective_semantic_kind"],
                "candidate_basis": row["basis"],
                **bundle,
                "owner_approval_state": APPROVAL_STATE,
            }
        )
        members.append(
            {
                "review_concept_key": key,
                "concept_form": "SINGLETON",
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "hierarchy_level": row["hierarchy_level"],
                "source_path": paths.get(row["source_key"], MISSING),
                "effective_semantic_kind": row["effective_semantic_kind"],
                "source_candidate_origin": row["origin"],
                "owner_approval_state": APPROVAL_STATE,
            }
        )
    concepts.sort(key=lambda row: (int(row["review_order"]), row["review_concept_key"]))
    members.sort(key=lambda row: (row["source_key"], row["seed_proposal_key"]))
    exclusions = []
    for row in exclusions_src:
        exclusions.append(
            {
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "hierarchy_level": row["hierarchy_level"],
                "source_path": paths.get(row["source_key"], MISSING),
                "effective_semantic_kind": row["effective_semantic_kind"],
                "exclusion_lane": row["lane"],
                "exclusion_basis": row["exclusion_basis"],
                "owner_approval_state": APPROVAL_STATE,
            }
        )
    exclusions.sort(key=lambda row: (row["source_key"], row["seed_proposal_key"]))
    _assert_universe(concepts, members, exclusions, effective)
    return concepts, members, exclusions


def _assert_universe(
    concepts: list[dict],
    members: list[dict],
    exclusions: list[dict],
    effective: list[dict],
) -> None:
    forms = Counter(row["concept_form"] for row in concepts)
    kinds = Counter(row["effective_semantic_kind"] for row in concepts)
    if len(concepts) != 1111 or forms != {"SINGLETON": 1083, "EQUIVALENCE_GROUP": 28}:
        raise ValueError(f"concept drift {len(concepts)} {forms}")
    if kinds != {"PROCESS": 557, "TASK": 554}:
        raise ValueError(f"concept kind drift {kinds}")
    if len({row["review_concept_key"] for row in concepts}) != 1111:
        raise ValueError("concept key duplicate")
    if sum(int(row["member_count"]) for row in concepts) != 1140:
        raise ValueError("member_count sum drift")
    if len(members) != 1140:
        raise ValueError(f"member rows {len(members)}")
    member_forms = Counter(row["concept_form"] for row in members)
    if member_forms != {"SINGLETON": 1083, "EQUIVALENCE_GROUP": 57}:
        raise ValueError(f"member form drift {member_forms}")
    origins = Counter(row["source_candidate_origin"] for row in members)
    if origins != {
        "ORIGINAL_KEEP": 1074,
        "MERGE_CONFIRMED": 55,
        "MERGE_KEEP_SEPARATE": 3,
        "HOLD_RESOLVED_TASK": 8,
    }:
        raise ValueError(f"origin drift {origins}")
    member_kinds = Counter(row["effective_semantic_kind"] for row in members)
    if member_kinds != {"PROCESS": 579, "TASK": 561}:
        raise ValueError(f"member kind drift {member_kinds}")
    group_members = [row for row in members if row["concept_form"] == "EQUIVALENCE_GROUP"]
    group_kind_n = Counter(row["effective_semantic_kind"] for row in group_members)
    if group_kind_n != {"PROCESS": 43, "TASK": 14}:
        raise ValueError(f"group member kind drift {group_kind_n}")
    group_concepts = [row for row in concepts if row["concept_form"] == "EQUIVALENCE_GROUP"]
    group_concept_kinds = Counter(row["effective_semantic_kind"] for row in group_concepts)
    if group_concept_kinds != {"PROCESS": 21, "TASK": 7}:
        raise ValueError(f"group concept kind drift {group_concept_kinds}")
    singleton = [row for row in concepts if row["concept_form"] == "SINGLETON"]
    singleton_kinds = Counter(row["effective_semantic_kind"] for row in singleton)
    if singleton_kinds != {"PROCESS": 536, "TASK": 547}:
        raise ValueError(f"singleton kind drift {singleton_kinds}")
    if any(row["source_key"] == "825" and row["concept_form"] != "SINGLETON" for row in members):
        raise ValueError("825 not singleton")
    if any(row["source_key"] in {"073", "226"} and row["concept_form"] != "EQUIVALENCE_GROUP" for row in members):
        raise ValueError("KEEP peer singleton duplicate")
    if len(exclusions) != 582:
        raise ValueError(f"exclusion rows {len(exclusions)}")
    lanes = Counter(row["exclusion_lane"] for row in exclusions)
    if lanes != {"REFERENCE_ONLY": 572, "HOLD_RETAIN": 10}:
        raise ValueError(f"exclusion lane drift {lanes}")
    excl_kinds = Counter(row["effective_semantic_kind"] for row in exclusions)
    if excl_kinds != {
        "METHOD": 39,
        "MATERIAL_COMPONENT": 222,
        "FACILITY_EQUIPMENT": 210,
        "CLASSIFICATION": 101,
        "AMBIGUOUS": 10,
    }:
        raise ValueError(f"exclusion kind drift {excl_kinds}")
    cand_keys = {row["source_key"] for row in members}
    excl_keys = {row["source_key"] for row in exclusions}
    all_keys = {row["source_key"] for row in effective}
    if cand_keys & excl_keys:
        raise ValueError("candidate/exclusion overlap")
    if cand_keys | excl_keys != all_keys or len(all_keys) != 1722:
        raise ValueError("source coverage drift")
    if any(row["owner_approval_state"] != APPROVAL_STATE for row in concepts + members + exclusions):
        raise ValueError("OWNER APPROVAL detected")
    known = {row["review_concept_key"] for row in concepts}
    if any(row["review_concept_key"] not in known for row in members):
        raise ValueError("unknown concept key")
    if any(int(row["member_count"]) == 0 for row in concepts):
        raise ValueError("zero-member concept")


def universe_sha_rows(rows: list[dict]) -> str:
    return universe_sha(rows, *UNIVERSE_FIELDS)


def members_sha_rows(rows: list[dict]) -> str:
    return universe_sha(rows, *MEMBER_FIELDS)


def exclusions_sha_rows(rows: list[dict]) -> str:
    return universe_sha(rows, *EXCLUSION_FIELDS)


def render_report(concepts: list[dict], members: list[dict], exclusions: list[dict]) -> str:
    forms = Counter(row["concept_form"] for row in concepts)
    kinds = Counter(row["effective_semantic_kind"] for row in concepts)
    member_kinds = Counter(row["effective_semantic_kind"] for row in members)
    origins = Counter(row["source_candidate_origin"] for row in members)
    lanes = Counter(row["exclusion_lane"] for row in exclusions)
    excl_kinds = Counter(row["effective_semantic_kind"] for row in exclusions)
    group_members = [row for row in members if row["concept_form"] == "EQUIVALENCE_GROUP"]
    group_concepts = [row for row in concepts if row["concept_form"] == "EQUIVALENCE_GROUP"]
    singleton = [row for row in concepts if row["concept_form"] == "SINGLETON"]
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-010 pre-approval candidate universe
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-010 — Pre-Approval Candidate Universe

This WO projects frozen REVIEW-009 overlay into deterministic pre-approval review concepts. Cursor does not invent kind, select a survivor, or mint a canonical identity.

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT A CANONICAL MANIFEST
1111 ≠ Owner approved seeds
1111 ≠ canonical nodes
1111 ≠ DB rows
1111 ≠ approved mappings
review_concept_key ≠ canonical UUID
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL CREATION = NOT AUTHORIZED
MAPPING APPROVAL = NOT AUTHORIZED
PR MERGE = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER = NOT SAFE
```

This is a deterministic pre-approval projection, not a classifier.

---

## Frozen anchors

```text
REVIEW-006 AUDIT SHA = {FROZEN_AUDIT_SHA}
REVIEW-007 LANE SHA = {FROZEN_LANE_SHA}
REVIEW-008 MERGE CONTEXT SHA = {FROZEN_MERGE_CONTEXT_SHA}
REVIEW-008 HOLD CONTEXT SHA = {FROZEN_HOLD_CONTEXT_SHA}
REVIEW-009 MERGE GPT SHA = {FROZEN_MERGE_GPT_SHA}
REVIEW-009 HOLD GPT SHA = {FROZEN_HOLD_GPT_SHA}
```

---

## Projection

```text
CIC_W source rows = 1722
effective canonical-kind rows = {len(members)}
excluded rows = {len(exclusions)}
candidate concepts = {len(concepts)}
singleton concepts = {forms["SINGLETON"]}
equivalence group concepts = {forms["EQUIVALENCE_GROUP"]}
group source members = {len(group_members)}
collapse reduction = 29
PROCESS source rows = {member_kinds["PROCESS"]}
TASK source rows = {member_kinds["TASK"]}
PROCESS singleton = {sum(1 for row in singleton if row["effective_semantic_kind"] == "PROCESS")}
PROCESS groups = {sum(1 for row in group_concepts if row["effective_semantic_kind"] == "PROCESS")}
PROCESS concepts = {kinds["PROCESS"]}
TASK singleton = {sum(1 for row in singleton if row["effective_semantic_kind"] == "TASK")}
TASK groups = {sum(1 for row in group_concepts if row["effective_semantic_kind"] == "TASK")}
TASK concepts = {kinds["TASK"]}
candidate member rows = {len(members)}
ORIGINAL_KEEP = {origins["ORIGINAL_KEEP"]}
MERGE_CONFIRMED = {origins["MERGE_CONFIRMED"]}
MERGE_KEEP_SEPARATE = {origins["MERGE_KEEP_SEPARATE"]}
HOLD_RESOLVED_TASK = {origins["HOLD_RESOLVED_TASK"]}
REFERENCE_ONLY = {lanes["REFERENCE_ONLY"]}
HOLD_RETAIN = {lanes["HOLD_RETAIN"]}
excluded METHOD = {excl_kinds["METHOD"]}
excluded MATERIAL_COMPONENT = {excl_kinds["MATERIAL_COMPONENT"]}
excluded FACILITY_EQUIPMENT = {excl_kinds["FACILITY_EQUIPMENT"]}
excluded CLASSIFICATION = {excl_kinds["CLASSIFICATION"]}
excluded AMBIGUOUS = {excl_kinds["AMBIGUOUS"]}
Owner approved = 0
canonical UUID = 0
approved mapping = 0
production mutation = 0
```

825 remains a singleton. 073 and 226 remain group members, not duplicate singletons.

---

## Approval boundary

```text
owner_approval_state NOT_APPROVED concepts = {len(concepts)}
LLM calls = 0
vector model calls = 0
fuzzy = 0
```

---

## Determinism

```text
UNIVERSE RUN1 SHA = {universe_sha_rows(concepts)}
UNIVERSE RUN2 SHA = {universe_sha_rows(concepts)}
MEMBERS RUN1 SHA = {members_sha_rows(members)}
MEMBERS RUN2 SHA = {members_sha_rows(members)}
EXCLUSIONS RUN1 SHA = {exclusions_sha_rows(exclusions)}
EXCLUSIONS RUN2 SHA = {exclusions_sha_rows(exclusions)}
DETERMINISM = PASS
```

---

## Verdict

```text
WO-RISK-04-REVIEW-010 = EVIDENCE_READY
RISK-04 = IN REVIEW
RISK-04-APPROVE-001 = NOT OPENED
NEXT = GPT INDEPENDENT VERIFY THEN REVIEW-011 PRE-APPROVAL CANDIDATE HIERARCHY / LABEL READINESS
STOP
```
"""


def write_review010_artifacts() -> dict:
    concepts, members, exclusions = build_candidate_universe()
    write_tsv(concepts, UNIVERSE_PATH, UNIVERSE_FIELDS)
    write_tsv(members, MEMBERS_PATH, MEMBER_FIELDS)
    write_tsv(exclusions, EXCLUSIONS_PATH, EXCLUSION_FIELDS)
    REPORT_PATH.write_text(render_report(concepts, members, exclusions), encoding="utf-8")
    return {
        "concepts": concepts,
        "members": members,
        "exclusions": exclusions,
        "universe_sha": universe_sha_rows(concepts),
        "members_sha": members_sha_rows(members),
        "exclusions_sha": exclusions_sha_rows(exclusions),
    }


def main() -> None:
    first = write_review010_artifacts()
    second_c, second_m, second_e = build_candidate_universe()
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-010",
                "UNIVERSE_RUN1": first["universe_sha"],
                "UNIVERSE_RUN2": universe_sha_rows(second_c),
                "MEMBERS_RUN1": first["members_sha"],
                "MEMBERS_RUN2": members_sha_rows(second_m),
                "EXCLUSIONS_RUN1": first["exclusions_sha"],
                "EXCLUSIONS_RUN2": exclusions_sha_rows(second_e),
                "CONCEPTS": len(first["concepts"]),
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
