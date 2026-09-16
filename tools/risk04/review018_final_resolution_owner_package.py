"""Final GPT blocker freeze, final manifest rebuild, and Owner Approval Package.

This pack freezes explicit GPT resolutions. Cursor does not invent parents or
labels. OWNER APPROVAL PACKAGE CREATED is not Owner approval.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review007_preapproval_readiness import GPT_EMPTY, GPT_PENDING
from tools.risk04.review010_candidate_universe import (
    EXCLUSIONS_PATH,
    MEMBERS_PATH,
    UNIVERSE_PATH,
    exclusions_sha_rows,
    members_sha_rows,
    universe_sha_rows,
)
from tools.risk04.review013_resolution_freeze import FROZEN_EXCLUSIONS_SHA, FROZEN_MEMBERS_SHA, FROZEN_UNIVERSE_SHA, H05_KEY
from tools.risk04.review014_remaining_parent_label_evidence import L02_KEY
from tools.risk04.review016_preapproval_manifest_audit import (
    BLOCKER_PATH,
    MANIFEST_FIELDS,
    MANIFEST_PATH,
    graph_audit,
    membership_audit,
    manifest_sha,
    readiness_counts,
)
from tools.risk04.review017_final_blocker_resolution_pack import (
    FAMILY_PATH,
    FROZEN_MANIFEST_SHA,
    LABEL_A_KEY,
    LABEL_B_KEY,
    PACK_PATH,
    build_pack,
    family_sha,
    pack_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Explicit GPT freeze overlay only. Cursor does not re-judge parent or label.
# This is an explicit evidence pack, not a classifier.
FROZEN_REVIEW017_PACK_SHA = "fdbb378f6da3d172441a7c725b747a9db0673b3e77dfc224c9ee2ad7c9ce738a"
FROZEN_REVIEW017_FAMILY_SHA = "a84e23cf3e1f3532475ebdb408a3da2e9fb8cb7b60fa64627605964c6c1b4e44"
RESOLUTION_PATH = Path("docs/knowledge/risk/RISK04_FINAL_BLOCKER_RESOLUTION_GPT_v1.tsv")
FINAL_MANIFEST_PATH = Path("docs/knowledge/risk/RISK04_FINAL_PREAPPROVAL_CANONICAL_MANIFEST_v1.tsv")
OWNER_PACKAGE_PATH = Path("docs/knowledge/risk/RISK04_OWNER_APPROVAL_PACKAGE_v1.tsv")
HOLD_PACKAGE_PATH = Path("docs/knowledge/risk/RISK04_OWNER_APPROVAL_HOLD_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review018-final-resolution-owner-package_v1.md")
DAM_PARENT = "da54d4926aa79473fa6f89610338b0297765d601166ceb67ac95ba973da49bf0"
CONCRETE_PARENT = "13f01c1ad0d027cd2397d07a0e9eafb5222e1bbae9c0855e76a6ca66d279e062"
PIPE_PARENT = "b15cd2beb1d4901b6d710f491abe2a583003fdfe5fe6d98842ce0257c9159552"
RETAINING_PARENT = "bc68572923c8910b9b34b63d85b18ecc876df84b7e42beb1fe2750242dca64f0"
MASONRY_PARENT = "33f1ddfc015d1a5a3173d5aa56062b9af98458c2e93edc02b239d897ef4ba8d7"
PLASTER_PARENT = "f8f8f8c0ded720ede952c131be6396329a82ad7f1995efa930cff437b5ed9ffa"
EQUIP_KEY = "ba7464ebdf6a54c4e9f41527a34eb43bc81acd1179e83a68a1c0c6244ad03980"
ELEC_KEY = "5bc3acd70ef94be1828618eb4eee664445fda4b87144a9b0b917ff2c6a19b740"
AGGREGATE_KEY = "f0f16c06ab4cb90d25d4fe89308cc6c166adb5d47278506dbaf906f92a58573e"
FILTER_KEY = "512d3906fcf9a0079a12b908c439663d6703b7d06a660b8da1218d18275559b2"
STONE_KEY = "a630c5d19464d9db0acd3e5b3cab8465fe8990f4d36be03653fc000e17206066"
F011_KEYS = (
    "c96ac36c304825c29ee231af7f514ce0ac096e0522815892526a63eb98631e39",
    "18df971e963e4445f7d9de6e11e0f689795b23e52411ebe3f4e06552ab12c251",
    "7a439acd29dd65f69446cf3e5799efa47c52dc521704096d4356e2e021028380",
    "2a16ffd74a0b9293c8cb8525c8541550a2648d39748806d09ded8308b50594c7",
    "1828313c4385bdc9e07ad785dfebebadb97bd1cfabeadeaca85452d84fdbbf0c",
    "086cb7669fde42d8cb3ead1004aab5073c384f43c946be95d4066abffb8e0ff9",
    "708f590c9f35d785d6315ee7e29238697d00dd707c7dcda6060e2e370223b385",
    "e53153c5f2d624a42c97eec1ac937ceb3194bc799905a8e083045a94cb260c15",
)
F371_KEYS = (
    "96df527ccb239d96a2f604ac5848d689d174bacf9f0b5716d1c76dad7cc4375a",
    "5ec54c9e3d66b25af9d10f82992e53383ce691ada40eb88359f08b8700262026",
    "ef467a3e5fbf9bfabb1bb2275399ad3d5ed56372428997b0f7d746266158e69b",
    "e4bb13e2e59d60b4434332a68193eba5e027152d0c13595c4ca2514f748f50e5",
    "a20f051dae1cbf038a0939447b9d4f7508662cd0fbfe028db1c9208aca35e4f7",
    "fd98cd55706d3e5c006fe7f8b6e705649fdee425f66e36383a54d39a8fce5fcf",
)
F415_KEYS = (
    "6aeb0c0085624f5039e903e5cbfb5b103d4201624bf3e1428eb003241778d893",
    "a27352b5d662e6d1048eeecae66e47f5a993d2674b6fb0789eec4c268f846268",
)
F513_KEYS = (
    "547f6c3944eefedd97dfa5c18e9128c819c354b470395ca0ff4d247283db372d",
    "f043ecd7b1058a7909717535be66af98f91a496c01eff626b3aa3bac07ff7e89",
)
RESOLUTION_FIELDS = (
    "case_no",
    "review_concept_key",
    "blocker_type",
    "gpt_final_decision",
    "canonical_parent_candidate",
    "canonical_parent_candidate_name",
    "parent_readiness",
    "canonical_label_candidate",
    "label_basis",
    "label_readiness",
    "source_context_policy",
    "source_preservation",
    "owner_approval_eligible",
    "owner_approval_state",
    "resolution_notes",
)
PACKAGE_FIELDS = (
    "review_concept_key",
    "semantic_kind",
    "canonical_label_candidate",
    "canonical_parent_candidate",
    "canonical_parent_candidate_name",
    "source_member_count",
    "source_keys",
    "source_names",
    "source_context_policy",
    "preapproval_readiness",
    "owner_approval_state",
)
HOLD_FIELDS = PACKAGE_FIELDS + ("hold_reason", "owner_approval_eligible")


def _nearest(parent: str, name: str) -> dict[str, str]:
    return {
        "gpt_final_decision": "NEAREST_CANDIDATE_PARENT_CONFIRMED",
        "canonical_parent_candidate": parent,
        "canonical_parent_candidate_name": name,
        "parent_readiness": "READY",
        "canonical_label_candidate": GPT_EMPTY,
        "label_basis": GPT_EMPTY,
        "label_readiness": GPT_EMPTY,
        "source_context_policy": "PRESERVE_IN_SOURCE_MAPPING_EVIDENCE",
        "owner_approval_eligible": "YES",
        "resolution_notes": "excluded source parent remains REFERENCE_ONLY; nearest candidate ancestor is the parent candidate.",
    }


def _root(decision: str, notes: str) -> dict[str, str]:
    return {
        "gpt_final_decision": decision,
        "canonical_parent_candidate": GPT_EMPTY,
        "canonical_parent_candidate_name": GPT_EMPTY,
        "parent_readiness": "READY_ROOT",
        "canonical_label_candidate": GPT_EMPTY,
        "label_basis": GPT_EMPTY,
        "label_readiness": GPT_EMPTY,
        "source_context_policy": "PRESERVE_IN_SOURCE_MAPPING_EVIDENCE",
        "owner_approval_eligible": "YES",
        "resolution_notes": notes,
    }


def _label(label: str, notes: str) -> dict[str, str]:
    return {
        "gpt_final_decision": "CLEAN_LABEL_MEMBER_CONFIRMED",
        "canonical_parent_candidate": GPT_EMPTY,
        "canonical_parent_candidate_name": GPT_EMPTY,
        "parent_readiness": GPT_EMPTY,
        "canonical_label_candidate": label,
        "label_basis": "EXPLICIT_CONNECTOR_CLEAN_SOURCE_MEMBER",
        "label_readiness": "READY",
        "source_context_policy": "PRESERVE_RAW_SOURCE_LABELS",
        "owner_approval_eligible": "YES",
        "resolution_notes": notes,
    }


GPT_BY_KEY: dict[str, dict[str, str]] = {
    **{key: _nearest(DAM_PARENT, "댐공사") for key in F371_KEYS},
    AGGREGATE_KEY: _nearest(CONCRETE_PARENT, "철근콘크리트공사"),
    FILTER_KEY: _nearest(PIPE_PARENT, "토목배관공사및배수공사"),
    STONE_KEY: _nearest(RETAINING_PARENT, "옹벽공사"),
    **{key: _nearest(MASONRY_PARENT, "조적공사") for key in F415_KEYS},
    **{key: _nearest(PLASTER_PARENT, "미장공사") for key in F513_KEYS},
    **{
        key: _root(
            "ROOT_PROMOTION_CONFIRMED",
            "011 and 01 are excluded CLASSIFICATION. retained PROCESS/TASK is promoted to READY_ROOT. no new classification canonical.",
        )
        for key in F011_KEYS
    },
    EQUIP_KEY: _root(
        "ROOT_PROMOTION_CONFIRMED",
        "06 공통장비 is FACILITY_EQUIPMENT REFERENCE_ONLY. 장비운반 is promoted to READY_ROOT. no new 공통장비 canonical.",
    ),
    ELEC_KEY: _root(
        "ROOT_STATUS_CONFIRMED",
        "86/863/8631 remain one KEEP_SEPARATE concept. source root 86 is inside the same candidate. no new parent.",
    ),
    LABEL_A_KEY: _label(
        "배관및전로공사",
        "meaning-bearing token difference = 0. connector-normalized sequence identical. 및 member preserves explicit semantic text.",
    ),
    LABEL_B_KEY: _label(
        "배선및가선공사",
        "meaning-bearing token difference = 0. connector-normalized sequence identical. 및 member preserves explicit semantic text.",
    ),
    L02_KEY: {
        "gpt_final_decision": "HOLD_LABEL_CONFIRMED",
        "canonical_parent_candidate": GPT_EMPTY,
        "canonical_parent_candidate_name": GPT_EMPTY,
        "parent_readiness": GPT_EMPTY,
        "canonical_label_candidate": GPT_EMPTY,
        "label_basis": GPT_EMPTY,
        "label_readiness": "HOLD",
        "source_context_policy": "PRESERVE_RAW_SOURCE",
        "owner_approval_eligible": "NO",
        "resolution_notes": "carry-forward REVIEW-015 HOLD_LABEL_CONFIRMED. no label invention.",
    },
}


def _assert_frozen_inputs() -> dict:
    review_pack = load_tsv(PACK_PATH)
    families = load_tsv(FAMILY_PATH)
    manifest = load_tsv(MANIFEST_PATH)
    rebuilt_pack, rebuilt_fam = build_pack()
    if pack_sha(review_pack) != FROZEN_REVIEW017_PACK_SHA:
        raise ValueError("REVIEW-017 pack SHA drift")
    if pack_sha(rebuilt_pack) != FROZEN_REVIEW017_PACK_SHA:
        raise ValueError("REVIEW-017 pack rebuild SHA drift")
    if family_sha(families) != FROZEN_REVIEW017_FAMILY_SHA:
        raise ValueError("REVIEW-017 family SHA drift")
    if family_sha(rebuilt_fam) != FROZEN_REVIEW017_FAMILY_SHA:
        raise ValueError("REVIEW-017 family rebuild SHA drift")
    if manifest_sha(manifest) != FROZEN_MANIFEST_SHA:
        raise ValueError("REVIEW-016 manifest SHA drift")
    if universe_sha_rows(load_tsv(UNIVERSE_PATH)) != FROZEN_UNIVERSE_SHA:
        raise ValueError("REVIEW-010 universe SHA drift")
    if members_sha_rows(load_tsv(MEMBERS_PATH)) != FROZEN_MEMBERS_SHA:
        raise ValueError("REVIEW-010 members SHA drift")
    if exclusions_sha_rows(load_tsv(EXCLUSIONS_PATH)) != FROZEN_EXCLUSIONS_SHA:
        raise ValueError("REVIEW-010 exclusions SHA drift")
    if len(review_pack) != 26:
        raise ValueError("REVIEW-017 pack identity drift")
    if {row["review_concept_key"] for row in review_pack} != set(GPT_BY_KEY):
        raise ValueError("GPT key set drift vs REVIEW-017 pack")
    return {
        "review_pack": review_pack,
        "families": families,
        "manifest": manifest,
        "members": load_tsv(MEMBERS_PATH),
        "exclusions": load_tsv(EXCLUSIONS_PATH),
        "concepts": load_tsv(UNIVERSE_PATH),
    }


def build_resolution(review_pack: list[dict] | None = None) -> list[dict]:
    if review_pack is None:
        review_pack = _assert_frozen_inputs()["review_pack"]
    rows = []
    for src in review_pack:
        spec = GPT_BY_KEY[src["review_concept_key"]]
        rows.append(
            {
                "case_no": src["case_no"],
                "review_concept_key": src["review_concept_key"],
                "blocker_type": src["blocker_type"],
                "gpt_final_decision": spec["gpt_final_decision"],
                "canonical_parent_candidate": spec["canonical_parent_candidate"],
                "canonical_parent_candidate_name": spec["canonical_parent_candidate_name"],
                "parent_readiness": spec["parent_readiness"],
                "canonical_label_candidate": spec["canonical_label_candidate"],
                "label_basis": spec["label_basis"],
                "label_readiness": spec["label_readiness"],
                "source_context_policy": spec["source_context_policy"],
                "source_preservation": "YES",
                "owner_approval_eligible": spec["owner_approval_eligible"],
                "owner_approval_state": APPROVAL_STATE,
                "resolution_notes": spec["resolution_notes"],
            }
        )
    _validate_resolution(rows, review_pack)
    return rows


def _validate_resolution(rows: list[dict], review_pack: list[dict]) -> None:
    if len(rows) != 26:
        raise ValueError(f"resolution rows {len(rows)}")
    if {row["review_concept_key"] for row in rows} != {row["review_concept_key"] for row in review_pack}:
        raise ValueError("resolution key-set drift")
    cats = Counter(row["gpt_final_decision"] for row in rows)
    if cats["NEAREST_CANDIDATE_PARENT_CONFIRMED"] != 13:
        raise ValueError("nearest parent count drift")
    if cats["ROOT_PROMOTION_CONFIRMED"] != 9:
        raise ValueError("root promotion count drift")
    if cats["ROOT_STATUS_CONFIRMED"] != 1:
        raise ValueError("root status count drift")
    if cats["CLEAN_LABEL_MEMBER_CONFIRMED"] != 2:
        raise ValueError("clean label count drift")
    if cats["HOLD_LABEL_CONFIRMED"] != 1:
        raise ValueError("hold label count drift")
    if any(row["gpt_final_decision"] == GPT_PENDING for row in rows):
        raise ValueError("GPT pending leak")
    if any(row["owner_approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("owner approval leak")
    by_key = {row["review_concept_key"]: row for row in rows}
    if by_key[L02_KEY]["canonical_label_candidate"] != GPT_EMPTY:
        raise ValueError("L-02 invented label")
    if by_key[LABEL_A_KEY]["canonical_label_candidate"] != "배관및전로공사":
        raise ValueError("811 label drift")
    if by_key[LABEL_B_KEY]["canonical_label_candidate"] != "배선및가선공사":
        raise ValueError("812 label drift")
    for key in F371_KEYS:
        if by_key[key]["canonical_parent_candidate"] != DAM_PARENT:
            raise ValueError("F-371 parent drift")
    if by_key[AGGREGATE_KEY]["canonical_parent_candidate"] != CONCRETE_PARENT:
        raise ValueError("F-251 parent drift")
    if by_key[FILTER_KEY]["canonical_parent_candidate"] != PIPE_PARENT:
        raise ValueError("F-315 parent drift")
    if by_key[STONE_KEY]["canonical_parent_candidate"] != RETAINING_PARENT:
        raise ValueError("F-382 parent drift")
    for key in F415_KEYS:
        if by_key[key]["canonical_parent_candidate"] != MASONRY_PARENT:
            raise ValueError("F-415 parent drift")
    for key in F513_KEYS:
        if by_key[key]["canonical_parent_candidate"] != PLASTER_PARENT:
            raise ValueError("F-513 parent drift")
    for key in (*F011_KEYS, EQUIP_KEY, ELEC_KEY):
        if by_key[key]["parent_readiness"] != "READY_ROOT" or by_key[key]["canonical_parent_candidate"] != GPT_EMPTY:
            raise ValueError(f"root readiness drift {key}")


def _preapproval(label_ok: bool, parent_ready: str) -> str:
    parent_ok = parent_ready in {"READY", "READY_ROOT"}
    if label_ok and parent_ok:
        return "READY_FOR_OWNER_REVIEW"
    if not label_ok and not parent_ok:
        return "HOLD_LABEL_AND_PARENT"
    if not label_ok:
        return "HOLD_LABEL"
    return "HOLD_PARENT"


def build_final_manifest(base: list[dict] | None = None, resolution: list[dict] | None = None) -> list[dict]:
    if base is None or resolution is None:
        pack = _assert_frozen_inputs()
        base = pack["manifest"]
        resolution = build_resolution(pack["review_pack"])
    overlay = {row["review_concept_key"]: row for row in resolution}
    rows = []
    for src in base:
        row = dict(src)
        spec = overlay.get(src["review_concept_key"])
        if spec is None:
            rows.append(row)
            continue
        if spec["canonical_parent_candidate"] not in {"", GPT_EMPTY} or spec["parent_readiness"] == "READY_ROOT":
            row["canonical_parent_candidate"] = spec["canonical_parent_candidate"]
            row["canonical_parent_candidate_name"] = spec["canonical_parent_candidate_name"]
            row["parent_readiness"] = spec["parent_readiness"]
            row["parent_basis"] = spec["gpt_final_decision"]
        if spec["canonical_label_candidate"] not in {"", GPT_EMPTY} or spec["label_readiness"] == "HOLD":
            row["canonical_label_candidate"] = spec["canonical_label_candidate"]
            row["label_basis"] = spec["label_basis"] if spec["label_basis"] not in {"", GPT_EMPTY} else row["label_basis"]
            row["label_readiness"] = spec["label_readiness"]
        row["source_context_policy"] = spec["source_context_policy"]
        row["semantic_resolution_status"] = "GPT_RESOLVED"
        label_ok = row["canonical_label_candidate"] not in {"", GPT_EMPTY}
        row["preapproval_readiness"] = _preapproval(label_ok, row["parent_readiness"])
        row["hold_reason"] = "HOLD_LABEL_CONFIRMED" if row["preapproval_readiness"] == "HOLD_LABEL" else GPT_EMPTY
        row["owner_approval_state"] = APPROVAL_STATE
        rows.append(row)
    _validate_final_manifest(rows)
    return rows


def _validate_final_manifest(rows: list[dict]) -> None:
    if len(rows) != 1111 or len({row["review_concept_key"] for row in rows}) != 1111:
        raise ValueError("final manifest identity drift")
    kinds = Counter(row["semantic_kind"] for row in rows)
    if kinds["PROCESS"] != 557 or kinds["TASK"] != 554:
        raise ValueError(f"kind drift {kinds}")
    counts = readiness_counts(rows)
    if counts["READY_FOR_OWNER_REVIEW"] != 1110 or counts["HOLD_LABEL"] != 1:
        raise ValueError(f"readiness drift {counts}")
    if counts["HOLD_PARENT"] or counts["HOLD_LABEL_AND_PARENT"]:
        raise ValueError(f"unexpected parent hold {counts}")
    if any(row["owner_approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("owner approval leak")
    if any(row["semantic_resolution_status"] == GPT_PENDING for row in rows):
        raise ValueError("GPT pending leak")
    graph = graph_audit(rows)
    if graph["self_parent"] or graph["unknown_parent"] or graph["cycle"]:
        raise ValueError(f"graph issues {graph}")
    members = membership_audit(rows, load_tsv(MEMBERS_PATH), load_tsv(EXCLUSIONS_PATH))
    if members["missing"] or members["multi"] or members["exclusion_leak"]:
        raise ValueError(f"membership issues {members}")
    by_key = {row["review_concept_key"]: row for row in rows}
    if by_key[L02_KEY]["preapproval_readiness"] != "HOLD_LABEL":
        raise ValueError("L-02 readiness drift")
    if by_key[L02_KEY]["canonical_label_candidate"] != GPT_EMPTY:
        raise ValueError("L-02 invented label")
    if by_key[LABEL_A_KEY]["canonical_label_candidate"] != "배관및전로공사":
        raise ValueError("811 overlay drift")
    if by_key[LABEL_B_KEY]["canonical_label_candidate"] != "배선및가선공사":
        raise ValueError("812 overlay drift")
    holds = [row for row in rows if row["preapproval_readiness"] != "READY_FOR_OWNER_REVIEW"]
    if {row["review_concept_key"] for row in holds} != {L02_KEY}:
        raise ValueError("unexpected remaining hold")
    if sum(1 for row in rows if row["parent_readiness"] == "HOLD") != 0:
        raise ValueError("parent blockers remain")


def build_owner_package(manifest: list[dict] | None = None) -> list[dict]:
    if manifest is None:
        manifest = build_final_manifest()
    rows = []
    for src in manifest:
        if src["preapproval_readiness"] != "READY_FOR_OWNER_REVIEW":
            continue
        rows.append({field: src[field] for field in PACKAGE_FIELDS})
    if len(rows) != 1110:
        raise ValueError(f"owner package rows {len(rows)}")
    if any(row["owner_approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("owner package approval leak")
    return rows


def build_hold_package(manifest: list[dict] | None = None) -> list[dict]:
    if manifest is None:
        manifest = build_final_manifest()
    holds = [row for row in manifest if row["review_concept_key"] == L02_KEY]
    if len(holds) != 1:
        raise ValueError("hold package identity drift")
    src = holds[0]
    row = {field: src[field] for field in PACKAGE_FIELDS}
    row["hold_reason"] = "HOLD_LABEL_CONFIRMED"
    row["owner_approval_eligible"] = "NO"
    return [row]


def resolution_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *RESOLUTION_FIELDS)


def final_manifest_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *MANIFEST_FIELDS)


def owner_package_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *PACKAGE_FIELDS)


def hold_package_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *HOLD_FIELDS)


def render_report(
    resolution: list[dict],
    manifest: list[dict],
    owner: list[dict],
    hold: list[dict],
    shas: dict[str, str],
) -> str:
    counts = readiness_counts(manifest)
    cats = Counter(row["gpt_final_decision"] for row in resolution)
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-018 final resolution owner package
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-018 — Final Resolution Freeze + Owner Approval Package

This WO freezes explicit GPT resolutions and rebuilds the 1111-row proposal manifest. OWNER APPROVAL PACKAGE CREATED is not Owner approval. Cursor does not mint canonical UUIDs or write mappings.

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT CANONICAL CREATION
THIS IS NOT AN APPROVED CANONICAL PARENT MANIFEST
THIS IS NOT A CANONICAL LABEL MANIFEST
THIS IS NOT AN APPROVED MAPPING
OWNER APPROVAL PACKAGE CREATED ≠ OWNER APPROVED
READY_FOR_OWNER_REVIEW ≠ APPROVED
HOLD_LABEL_CONFIRMED ≠ LABEL INVENTED
RISK-04-APPROVE-001 = NOT OPENED
PR MERGE = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER = NOT SAFE
OBJ-SEARCH-DICT = SEPARATE STREAM
```

This is an explicit evidence pack, not a classifier.

---

## Census

```text
candidate concepts = 1111
PROCESS = 557
TASK = 554
source members = 1140
READY_FOR_OWNER_REVIEW = {counts["READY_FOR_OWNER_REVIEW"]}
HOLD = {counts["HOLD_LABEL"]}
HOLD_PARENT = {counts["HOLD_PARENT"]}
HOLD_LABEL_AND_PARENT = {counts["HOLD_LABEL_AND_PARENT"]}
GPT PENDING = 0
parent blockers = 0
label blockers unresolved = 0
frozen label HOLD = 1
NEAREST_CANDIDATE_PARENT_CONFIRMED = {cats["NEAREST_CANDIDATE_PARENT_CONFIRMED"]}
ROOT_PROMOTION_CONFIRMED = {cats["ROOT_PROMOTION_CONFIRMED"]}
ROOT_STATUS_CONFIRMED = {cats["ROOT_STATUS_CONFIRMED"]}
CLEAN_LABEL_MEMBER_CONFIRMED = {cats["CLEAN_LABEL_MEMBER_CONFIRMED"]}
HOLD_LABEL_CONFIRMED = {cats["HOLD_LABEL_CONFIRMED"]}
OWNER APPROVAL PACKAGE = {len(owner)}
OWNER APPROVAL HOLD = {len(hold)}
FULL 1111 APPROVAL READINESS = BLOCKED_BY_1_HOLD
OWNER APPROVAL PACKAGE READINESS = READY
OWNER APPROVED = 0
canonical UUID = 0
approved mapping = 0
production write = 0
```

---

## Snapshot

```text
OWNER APPROVAL PACKAGE SHA256 = {shas["owner"]}
RESOLUTION SHA256 = {shas["resolution"]}
FINAL MANIFEST SHA256 = {shas["manifest"]}
HOLD PACKAGE SHA256 = {shas["hold"]}
```

Future Owner Approval, if opened, must bind this exact package SHA rather than HEAD.

---

## Guard

```text
L-02 = HOLD_LABEL_CONFIRMED / EMPTY
H-05 exact key = {H05_KEY}
graph self-parent = 0
graph unknown parent = 0
graph cycle = 0
member missing = 0
member multi-assigned = 0
exclusion leakage = 0
LLM calls = 0
vector model calls = 0
fuzzy = 0
Kiwi runtime calls = 0
```

---

## Determinism

```text
RESOLUTION RUN1 SHA = {shas["resolution"]}
RESOLUTION RUN2 SHA = {shas["resolution"]}
FINAL MANIFEST RUN1 SHA = {shas["manifest"]}
FINAL MANIFEST RUN2 SHA = {shas["manifest"]}
OWNER PACKAGE RUN1 SHA = {shas["owner"]}
OWNER PACKAGE RUN2 SHA = {shas["owner"]}
HOLD PACKAGE RUN1 SHA = {shas["hold"]}
HOLD PACKAGE RUN2 SHA = {shas["hold"]}
DETERMINISM = PASS
```

---

## Verdict

```text
WO-RISK-04-REVIEW-018 = OWNER_PACKAGE_READY
RISK-04 = IN REVIEW
FULL 1111 APPROVAL READINESS = BLOCKED_BY_1_HOLD
OWNER APPROVAL PACKAGE READINESS = READY
RISK-04-APPROVE-001 = NOT OPENED
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT VERIFY
THEN ONLY IF USER EXPLICITLY APPROVES = RISK-04-APPROVE-001
STOP
```
"""


def write_review018_artifacts() -> dict:
    inputs = _assert_frozen_inputs()
    resolution = build_resolution(inputs["review_pack"])
    manifest = build_final_manifest(inputs["manifest"], resolution)
    owner = build_owner_package(manifest)
    hold = build_hold_package(manifest)
    shas = {
        "resolution": resolution_sha(resolution),
        "manifest": final_manifest_sha(manifest),
        "owner": owner_package_sha(owner),
        "hold": hold_package_sha(hold),
    }
    write_tsv(resolution, RESOLUTION_PATH, RESOLUTION_FIELDS)
    write_tsv(manifest, FINAL_MANIFEST_PATH, MANIFEST_FIELDS)
    write_tsv(owner, OWNER_PACKAGE_PATH, PACKAGE_FIELDS)
    write_tsv(hold, HOLD_PACKAGE_PATH, HOLD_FIELDS)
    REPORT_PATH.write_text(render_report(resolution, manifest, owner, hold, shas), encoding="utf-8")
    return {"resolution": resolution, "manifest": manifest, "owner": owner, "hold": hold, "shas": shas}


def main() -> None:
    first = write_review018_artifacts()
    inputs = _assert_frozen_inputs()
    resolution = build_resolution(inputs["review_pack"])
    manifest = build_final_manifest(inputs["manifest"], resolution)
    owner = build_owner_package(manifest)
    hold = build_hold_package(manifest)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-018",
                "RESOLUTION_RUN1": first["shas"]["resolution"],
                "RESOLUTION_RUN2": resolution_sha(resolution),
                "MANIFEST_RUN1": first["shas"]["manifest"],
                "MANIFEST_RUN2": final_manifest_sha(manifest),
                "OWNER_RUN1": first["shas"]["owner"],
                "OWNER_RUN2": owner_package_sha(owner),
                "HOLD_RUN1": first["shas"]["hold"],
                "HOLD_RUN2": hold_package_sha(hold),
                "READY": 1110,
                "HOLD": 1,
                "CANONICAL_MINT": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
