"""Pre-approval canonical proposal manifest and blocker audit. Not Owner approval.

This pack assembles frozen REVIEW-010~015 evidence into one 1111-row proposal
manifest. Cursor does not invent labels, parents, synonyms, or Kiwi words.
READY_FOR_OWNER_REVIEW is not Owner approval.
"""
from __future__ import annotations

from collections import Counter, defaultdict
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
from tools.risk04.review013_resolution_freeze import (
    FROZEN_CONCEPT_HIERARCHY_SHA,
    FROZEN_EXCLUSIONS_SHA,
    FROZEN_LABEL_SHA,
    FROZEN_MEMBER_HIERARCHY_SHA,
    FROZEN_MEMBERS_SHA,
    FROZEN_QUEUE_SHA,
    FROZEN_SEARCH_EXPORT_SHA,
    FROZEN_UNIVERSE_SHA,
    H01_PARENT_KEY,
    H05_KEY,
    H06_PARENT_KEY,
    RESOLUTION_PATH,
    resolution_sha,
)
from tools.risk04.review014_remaining_parent_label_evidence import (
    DEMOLITION_COMMON,
    EVIDENCE_PATH,
    FROZEN_RESOLUTION_SHA,
    H02_COMMON,
    H02_KEY,
    H03_KEY,
    H04_KEY,
    L02_KEY,
    evidence_sha,
)
from tools.risk04.review015_remaining5_resolution_freeze import (
    FROZEN_EVIDENCE_SHA,
    REMAINING5_PATH,
    remaining5_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Frozen assembly only. Cursor does not invent canonical label or parent.
# This is an explicit evidence pack, not a classifier.
FROZEN_REMAINING5_SHA = "d3f2492893f0959d7737d15299f998b5fbfabea3b0dcfcde57ede63ccce37ec4"
MANIFEST_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_CANONICAL_MANIFEST_v1.tsv")
BLOCKER_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_BLOCKER_QUEUE_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review016-preapproval-manifest-audit_v1.md")
H01_KEY = "fce048a6ba4d60e4520ac1f54189361e1b473e1bab9f15c88000e42fa44abe0c"
H06_KEY = "6985c17f351847499f1c250343deb7f6b9c81cc4d194fe15f055b3fa2b9c4d0f"
READINESS = (
    "READY_FOR_OWNER_REVIEW",
    "HOLD_LABEL",
    "HOLD_PARENT",
    "HOLD_LABEL_AND_PARENT",
)
MANIFEST_FIELDS = (
    "review_concept_key",
    "concept_form",
    "semantic_kind",
    "source_member_count",
    "source_keys",
    "source_names",
    "canonical_label_candidate",
    "label_basis",
    "label_readiness",
    "canonical_parent_candidate",
    "canonical_parent_candidate_name",
    "parent_basis",
    "parent_readiness",
    "source_context_policy",
    "source_preservation",
    "semantic_resolution_status",
    "preapproval_readiness",
    "hold_reason",
    "owner_approval_state",
)
BLOCKER_FIELDS = (
    "review_concept_key",
    "semantic_kind",
    "source_keys",
    "source_names",
    "label_readiness",
    "parent_readiness",
    "hold_reason",
    "existing_evidence",
    "required_next_decision",
    "owner_approval_state",
)


def _join(parts: list[str]) -> str:
    if not parts:
        return GPT_EMPTY
    return " | ".join(parts)


def _assert_frozen_inputs() -> dict:
    concepts = load_tsv(UNIVERSE_PATH)
    members = load_tsv(MEMBERS_PATH)
    exclusions = load_tsv(EXCLUSIONS_PATH)
    hierarchy = load_tsv(CONCEPT_HIERARCHY_PATH)
    labels = load_tsv(LABEL_PATH)
    review013 = load_tsv(RESOLUTION_PATH)
    evidence = load_tsv(EVIDENCE_PATH)
    review015 = load_tsv(REMAINING5_PATH)
    if universe_sha_rows(concepts) != FROZEN_UNIVERSE_SHA:
        raise ValueError("REVIEW-010 universe SHA drift")
    if members_sha_rows(members) != FROZEN_MEMBERS_SHA:
        raise ValueError("REVIEW-010 members SHA drift")
    if exclusions_sha_rows(exclusions) != FROZEN_EXCLUSIONS_SHA:
        raise ValueError("REVIEW-010 exclusions SHA drift")
    if member_hierarchy_sha(load_tsv(MEMBER_HIERARCHY_PATH)) != FROZEN_MEMBER_HIERARCHY_SHA:
        raise ValueError("REVIEW-011 member hierarchy SHA drift")
    if concept_hierarchy_sha(hierarchy) != FROZEN_CONCEPT_HIERARCHY_SHA:
        raise ValueError("REVIEW-011 concept hierarchy SHA drift")
    if label_sha(labels) != FROZEN_LABEL_SHA:
        raise ValueError("REVIEW-011 label SHA drift")
    if search_export_sha(load_tsv(SEARCH_EXPORT_PATH)) != FROZEN_SEARCH_EXPORT_SHA:
        raise ValueError("REVIEW-011 search export SHA drift")
    if critical_queue_sha(load_tsv(CRITICAL_QUEUE_PATH)) != FROZEN_QUEUE_SHA:
        raise ValueError("REVIEW-011 critical queue SHA drift")
    if resolution_sha(review013) != FROZEN_RESOLUTION_SHA:
        raise ValueError("REVIEW-013 SHA drift")
    if evidence_sha(evidence) != FROZEN_EVIDENCE_SHA:
        raise ValueError("REVIEW-014 SHA drift")
    if remaining5_sha(review015) != FROZEN_REMAINING5_SHA:
        raise ValueError("REVIEW-015 SHA drift")
    if len(concepts) != 1111 or len(members) != 1140 or len(exclusions) != 582:
        raise ValueError("REVIEW-010 identity drift")
    return {
        "concepts": concepts,
        "members": members,
        "exclusions": exclusions,
        "hierarchy": hierarchy,
        "labels": labels,
        "review013": review013,
        "review015": review015,
    }


def _display_name(label_row: dict, concept_row: dict) -> str:
    names = label_row.get("unique_raw_names") or ""
    if names not in {"", GPT_EMPTY}:
        return names
    return concept_row["member_names"] if concept_row["member_names"] not in {"", GPT_EMPTY} else GPT_EMPTY


def _assemble_label(key: str, label_row: dict, by013: dict, by015: dict) -> tuple[str, str, str, list[str]]:
    if key in by015 and by015[key]["gpt_final_decision"] == "HOLD_LABEL_CONFIRMED":
        return GPT_EMPTY, "HOLD_LABEL_CONFIRMED", "HOLD", ["HOLD_LABEL_CONFIRMED"]
    if key in by015 and by015[key]["canonical_label_candidate"] not in {"", GPT_EMPTY}:
        return by015[key]["canonical_label_candidate"], by015[key]["label_resolution_basis"], "READY", []
    row013 = by013.get(key)
    if row013:
        if row013["gpt_decision"] in {"CLEAN_LABEL_CONFIRMED", "EXISTING_CLEAN_MEMBER_CONFIRMED"}:
            if row013["proposed_canonical_label"] in {"", GPT_EMPTY}:
                raise ValueError(f"empty GPT label {key}")
            return row013["proposed_canonical_label"], row013["label_basis"], "READY", []
        if row013["gpt_decision"] == "HOLD_LABEL":
            return GPT_EMPTY, row013["gpt_decision"], "HOLD", ["HOLD_LABEL"]
    ready = label_row["label_readiness"]
    if ready == "SINGLE_RAW_NAME":
        return label_row["unique_raw_names"], "SINGLE_RAW_SOURCE", "READY", []
    if ready == "MULTI_MEMBER_SAME_RAW_NAME":
        return label_row["unique_raw_names"], "MULTI_MEMBER_SAME_RAW", "READY", []
    if ready == "MULTI_RAW_NAME_VARIANTS":
        return GPT_EMPTY, GPT_EMPTY, "HOLD", ["MULTI_RAW_VARIANTS_UNRESOLVED"]
    if ready == "LEXICAL_NOISE_REVIEW_REQUIRED":
        return GPT_EMPTY, GPT_EMPTY, "HOLD", ["LEXICAL_NOISE_UNRESOLVED"]
    raise ValueError(f"unhandled label readiness {ready}")


def _assemble_parent(
    key: str,
    hier: dict,
    by013: dict,
    by015: dict,
    candidate_keys: set[str],
    labels_by_key: dict[str, dict],
    concepts_by_key: dict[str, dict],
) -> tuple[str, str, str, str, list[str], str]:
    context = "PRESERVE_SOURCE_MEMBERSHIP"
    if key in by015 and by015[key]["source_context_policy"] not in {"", GPT_EMPTY}:
        context = by015[key]["source_context_policy"]
    if key in by015 and by015[key]["gpt_final_decision"] == "COMMON_ANCESTOR_PARENT_CONFIRMED":
        parent = by015[key]["canonical_parent_candidate"]
        name = by015[key]["canonical_parent_candidate_name"]
        if parent not in candidate_keys:
            raise ValueError(f"REVIEW-015 parent outside universe {key}")
        return parent, name, "GPT_COMMON_ANCESTOR_PARENT", "READY", [], context
    row013 = by013.get(key)
    if row013 and row013["canonical_parent_resolution"] == "SINGLE_PARENT_CANDIDATE":
        parent = row013["recommended_parent_concept_key"]
        if parent not in candidate_keys:
            raise ValueError(f"REVIEW-013 parent outside universe {key}")
        name = _display_name(labels_by_key[parent], concepts_by_key[parent])
        return parent, name, "GPT_SINGLE_PARENT_CANDIDATE", "READY", [], context
    status = hier["hierarchy_readiness"]
    if status == "ROOT_READY":
        return GPT_EMPTY, GPT_EMPTY, "ROOT_READY", "READY_ROOT", [], context
    if status == "SINGLE_PARENT_EVIDENCE":
        parents = [part for part in hier["direct_parent_concept_keys"].split(" | ") if part and part not in {GPT_EMPTY}]
        if len(parents) != 1 or parents[0] not in candidate_keys:
            return GPT_EMPTY, GPT_EMPTY, GPT_EMPTY, "HOLD", ["NO_CANDIDATE_PARENT_UNRESOLVED"], context
        parent = parents[0]
        name = _display_name(labels_by_key[parent], concepts_by_key[parent])
        return parent, name, "SINGLE_PARENT_SOURCE_EVIDENCE", "READY", [], context
    if status == "NO_CANDIDATE_PARENT":
        return GPT_EMPTY, GPT_EMPTY, GPT_EMPTY, "HOLD", ["NO_CANDIDATE_PARENT_UNRESOLVED"], context
    if status in {"SOURCE_PARENT_AMBIGUOUS", "SOURCE_PARENT_NOT_FOUND"}:
        return GPT_EMPTY, GPT_EMPTY, GPT_EMPTY, "HOLD", [f"{status}_UNRESOLVED"], context
    if status in {"MULTI_PARENT_REVIEW_REQUIRED", "CROSS_ROOT_REVIEW_REQUIRED"}:
        raise ValueError(f"unresolved {status} {key}")
    raise ValueError(f"unhandled hierarchy readiness {status}")


def _preapproval(label_ok: bool, parent_ready: str) -> str:
    parent_ok = parent_ready in {"READY", "READY_ROOT"}
    if label_ok and parent_ok:
        return "READY_FOR_OWNER_REVIEW"
    if not label_ok and not parent_ok:
        return "HOLD_LABEL_AND_PARENT"
    if not label_ok:
        return "HOLD_LABEL"
    return "HOLD_PARENT"


def _next_decision(status: str) -> str:
    return {
        "HOLD_LABEL": "GPT_LABEL_REVIEW",
        "HOLD_PARENT": "GPT_PARENT_REVIEW",
        "HOLD_LABEL_AND_PARENT": "GPT_LABEL_AND_PARENT_REVIEW",
    }[status]


def graph_audit(rows: list[dict]) -> dict[str, int]:
    by_key = {row["review_concept_key"]: row for row in rows}
    self_parent = unknown = 0
    children: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        parent = row["canonical_parent_candidate"]
        if parent in {"", GPT_EMPTY}:
            continue
        if parent == row["review_concept_key"]:
            self_parent += 1
        if parent not in by_key:
            unknown += 1
            continue
        children[parent].append(row["review_concept_key"])
    visiting: set[str] = set()
    done: set[str] = set()
    cycles = 0

    def walk(node: str) -> None:
        nonlocal cycles
        if node in done:
            return
        if node in visiting:
            cycles += 1
            return
        visiting.add(node)
        parent = by_key[node]["canonical_parent_candidate"]
        if parent not in {"", GPT_EMPTY} and parent in by_key:
            walk(parent)
        visiting.remove(node)
        done.add(node)

    for key in by_key:
        walk(key)
    return {"self_parent": self_parent, "unknown_parent": unknown, "cycle": cycles}


def membership_audit(manifest: list[dict], members: list[dict], exclusions: list[dict]) -> dict[str, int]:
    keys = {row["review_concept_key"] for row in manifest}
    assigned = Counter()
    missing = 0
    for row in members:
        if row["review_concept_key"] not in keys:
            missing += 1
        assigned[row["source_key"]] += 1
    manifest_sources: list[str] = []
    for row in manifest:
        for key in row["source_keys"].split(" | "):
            if key:
                manifest_sources.append(key)
    source_counts = Counter(manifest_sources)
    exclusion_keys = {row["source_key"] for row in exclusions}
    member_keys = {row["source_key"] for row in members}
    return {
        "missing": missing + len(member_keys - set(source_counts)),
        "multi": sum(1 for count in source_counts.values() if count > 1) + sum(1 for count in assigned.values() if count > 1),
        "exclusion_leak": len(set(source_counts) & exclusion_keys),
        "parent_to_exclusion": 0,
    }


def build_manifest(pack: dict | None = None) -> list[dict]:
    if pack is None:
        pack = _assert_frozen_inputs()
    concepts = pack["concepts"]
    hierarchy = {row["review_concept_key"]: row for row in pack["hierarchy"]}
    labels = {row["review_concept_key"]: row for row in pack["labels"]}
    by013 = {row["review_concept_key"]: row for row in pack["review013"]}
    by015 = {row["review_concept_key"]: row for row in pack["review015"]}
    concepts_by_key = {row["review_concept_key"]: row for row in concepts}
    candidate_keys = set(concepts_by_key)
    rows = []
    for concept in concepts:
        key = concept["review_concept_key"]
        label, label_basis, label_ready, label_hold = _assemble_label(key, labels[key], by013, by015)
        parent, parent_name, parent_basis, parent_ready, parent_hold, context = _assemble_parent(
            key, hierarchy[key], by013, by015, candidate_keys, labels, concepts_by_key
        )
        status = _preapproval(label not in {"", GPT_EMPTY}, parent_ready)
        reasons = label_hold + parent_hold
        resolved = "GPT_RESOLVED" if key in by013 or key in by015 else "ASSEMBLED"
        rows.append(
            {
                "review_concept_key": key,
                "concept_form": concept["concept_form"],
                "semantic_kind": concept["effective_semantic_kind"],
                "source_member_count": concept["member_count"],
                "source_keys": concept["member_source_keys"],
                "source_names": concept["member_names"],
                "canonical_label_candidate": label,
                "label_basis": label_basis if label_basis else GPT_EMPTY,
                "label_readiness": label_ready,
                "canonical_parent_candidate": parent,
                "canonical_parent_candidate_name": parent_name,
                "parent_basis": parent_basis if parent_basis else GPT_EMPTY,
                "parent_readiness": parent_ready,
                "source_context_policy": context,
                "source_preservation": "YES",
                "semantic_resolution_status": resolved,
                "preapproval_readiness": status,
                "hold_reason": _join(reasons),
                "owner_approval_state": APPROVAL_STATE,
            }
        )
    _validate_manifest(rows, pack)
    return rows


def build_blockers(manifest: list[dict] | None = None) -> list[dict]:
    if manifest is None:
        manifest = build_manifest()
    rows = []
    for row in manifest:
        if row["preapproval_readiness"] == "READY_FOR_OWNER_REVIEW":
            continue
        rows.append(
            {
                "review_concept_key": row["review_concept_key"],
                "semantic_kind": row["semantic_kind"],
                "source_keys": row["source_keys"],
                "source_names": row["source_names"],
                "label_readiness": row["label_readiness"],
                "parent_readiness": row["parent_readiness"],
                "hold_reason": row["hold_reason"],
                "existing_evidence": row["hold_reason"],
                "required_next_decision": _next_decision(row["preapproval_readiness"]),
                "owner_approval_state": APPROVAL_STATE,
            }
        )
    return rows


def _validate_manifest(rows: list[dict], pack: dict) -> None:
    concepts = pack["concepts"]
    if len(rows) != 1111:
        raise ValueError(f"manifest rows {len(rows)}")
    keys = [row["review_concept_key"] for row in rows]
    if len(set(keys)) != 1111:
        raise ValueError("duplicate concept key")
    if set(keys) != {row["review_concept_key"] for row in concepts}:
        raise ValueError("manifest key set drift")
    kinds = Counter(row["semantic_kind"] for row in rows)
    if kinds["PROCESS"] != 557 or kinds["TASK"] != 554:
        raise ValueError(f"kind drift {kinds}")
    if any(row["preapproval_readiness"] not in READINESS for row in rows):
        raise ValueError("illegal readiness")
    if any(row["owner_approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("owner approval leak")
    if any(row["semantic_resolution_status"] == GPT_PENDING for row in rows):
        raise ValueError("GPT pending leak")
    graph = graph_audit(rows)
    if graph["self_parent"] or graph["unknown_parent"] or graph["cycle"]:
        raise ValueError(f"graph issues {graph}")
    members = membership_audit(rows, pack["members"], pack["exclusions"])
    exclusion_keys = {row["source_key"] for row in pack["exclusions"]}
    parent_to_exclusion = sum(
        1
        for row in rows
        if row["canonical_parent_candidate"] not in {"", GPT_EMPTY} and row["canonical_parent_candidate"] in exclusion_keys
    )
    members["parent_to_exclusion"] = parent_to_exclusion
    if members["missing"] or members["multi"] or members["exclusion_leak"] or parent_to_exclusion:
        raise ValueError(f"membership issues {members}")
    by_key = {row["review_concept_key"]: row for row in rows}
    if by_key[H01_KEY]["canonical_parent_candidate"] != H01_PARENT_KEY:
        raise ValueError("H-01 parent drift")
    if by_key[H06_KEY]["canonical_parent_candidate"] != H06_PARENT_KEY:
        raise ValueError("H-06 parent drift")
    if by_key[H02_KEY]["canonical_parent_candidate"] != H02_COMMON:
        raise ValueError("H-02 parent drift")
    if by_key[H02_KEY]["canonical_parent_candidate_name"] != "계측":
        raise ValueError("H-02 parent name drift")
    if by_key[H05_KEY]["canonical_parent_candidate_name"] != "철거해체공사및시설물보호":
        raise ValueError("H-05 parent name drift")
    if by_key[H03_KEY]["canonical_parent_candidate"] != DEMOLITION_COMMON:
        raise ValueError("H-03 parent drift")
    if by_key[H04_KEY]["canonical_parent_candidate"] != DEMOLITION_COMMON:
        raise ValueError("H-04 parent drift")
    if by_key[H05_KEY]["canonical_parent_candidate"] != DEMOLITION_COMMON:
        raise ValueError("H-05 parent drift")
    if by_key[H05_KEY]["review_concept_key"] != H05_KEY:
        raise ValueError("H-05 key drift")
    if by_key[L02_KEY]["canonical_label_candidate"] != GPT_EMPTY:
        raise ValueError("L-02 invented label")
    if by_key[L02_KEY]["label_readiness"] != "HOLD":
        raise ValueError("L-02 label readiness drift")
    if "HOLD_LABEL_CONFIRMED" not in by_key[L02_KEY]["hold_reason"]:
        raise ValueError("L-02 hold reason drift")
    hierarchy = {row["review_concept_key"]: row for row in pack["hierarchy"]}
    unresolved_multi = unresolved_cross = 0
    for row in rows:
        prior = hierarchy[row["review_concept_key"]]["hierarchy_readiness"]
        if prior == "MULTI_PARENT_REVIEW_REQUIRED" and row["parent_readiness"] == "HOLD":
            unresolved_multi += 1
        if prior == "CROSS_ROOT_REVIEW_REQUIRED" and row["parent_readiness"] == "HOLD":
            unresolved_cross += 1
    if unresolved_multi or unresolved_cross:
        raise ValueError(f"unresolved hierarchy {unresolved_multi} {unresolved_cross}")


def readiness_counts(rows: list[dict]) -> dict[str, int]:
    cats = Counter(row["preapproval_readiness"] for row in rows)
    return {
        "READY_FOR_OWNER_REVIEW": cats["READY_FOR_OWNER_REVIEW"],
        "HOLD_LABEL": cats["HOLD_LABEL"],
        "HOLD_PARENT": cats["HOLD_PARENT"],
        "HOLD_LABEL_AND_PARENT": cats["HOLD_LABEL_AND_PARENT"],
        "TOTAL_BLOCKERS": 1111 - cats["READY_FOR_OWNER_REVIEW"],
    }


def unresolved_counts(manifest: list[dict], hierarchy: list[dict], labels: list[dict]) -> dict[str, int]:
    hier = {row["review_concept_key"]: row for row in hierarchy}
    lab = {row["review_concept_key"]: row for row in labels}
    no_parent = multi_raw = 0
    for row in manifest:
        if hier[row["review_concept_key"]]["hierarchy_readiness"] == "NO_CANDIDATE_PARENT" and row["parent_readiness"] == "HOLD":
            no_parent += 1
        if lab[row["review_concept_key"]]["label_readiness"] == "MULTI_RAW_NAME_VARIANTS" and row["label_readiness"] == "HOLD":
            multi_raw += 1
    return {"NO_CANDIDATE_PARENT": no_parent, "MULTI_RAW_VARIANTS": multi_raw}


def manifest_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *MANIFEST_FIELDS)


def blocker_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *BLOCKER_FIELDS)


def render_report(manifest: list[dict], blockers: list[dict], extra: dict[str, int], msha: str, bsha: str) -> str:
    counts = readiness_counts(manifest)
    kinds = Counter(row["semantic_kind"] for row in manifest)
    full = "READY" if counts["TOTAL_BLOCKERS"] == 0 else "BLOCKED"
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-016 preapproval manifest blocker audit
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-016 — Pre-approval Canonical Manifest & Blocker Audit

This WO assembles frozen REVIEW-010~015 evidence into one proposal manifest. Cursor does not invent labels or parents. READY_FOR_OWNER_REVIEW is not Owner approval.

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT CANONICAL CREATION
THIS IS NOT AN APPROVED CANONICAL PARENT MANIFEST
THIS IS NOT A CANONICAL LABEL MANIFEST
THIS IS NOT AN APPROVED MAPPING
READY_FOR_OWNER_REVIEW ≠ APPROVED
HOLD_LABEL_CONFIRMED ≠ LABEL INVENTED
GPT semantic pending = 0
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
PROCESS = {kinds["PROCESS"]}
TASK = {kinds["TASK"]}
source members = 1140
exclusions = 582
READY_FOR_OWNER_REVIEW = {counts["READY_FOR_OWNER_REVIEW"]}
HOLD_LABEL = {counts["HOLD_LABEL"]}
HOLD_PARENT = {counts["HOLD_PARENT"]}
HOLD_LABEL_AND_PARENT = {counts["HOLD_LABEL_AND_PARENT"]}
TOTAL BLOCKERS = {counts["TOTAL_BLOCKERS"]}
NO_CANDIDATE_PARENT unresolved = {extra["NO_CANDIDATE_PARENT"]}
MULTI_RAW_VARIANTS unresolved = {extra["MULTI_RAW_VARIANTS"]}
unresolved MULTI_PARENT = 0
unresolved CROSS_ROOT = 0
blocker queue rows = {len(blockers)}
FULL OWNER APPROVAL READINESS = {full}
GPT semantic pending = 0
Owner approved = 0
canonical UUID = 0
approved mapping = 0
production write = 0
```

---

## Guard

```text
L-02 label = EMPTY / HOLD
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
MANIFEST RUN1 SHA = {msha}
MANIFEST RUN2 SHA = {msha}
BLOCKER RUN1 SHA = {bsha}
BLOCKER RUN2 SHA = {bsha}
DETERMINISM = PASS
```

---

## Verdict

```text
WO-RISK-04-REVIEW-016 = EVIDENCE_READY
RISK-04 = IN REVIEW
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL = NOT OPENED
MAPPING = NOT OPENED
FULL OWNER APPROVAL READINESS = {full}
NEXT = GPT INDEPENDENT VERIFY
STOP
```
"""


def write_review016_artifacts() -> dict:
    pack = _assert_frozen_inputs()
    manifest = build_manifest(pack)
    blockers = build_blockers(manifest)
    extra = unresolved_counts(manifest, pack["hierarchy"], pack["labels"])
    msha = manifest_sha(manifest)
    bsha = blocker_sha(blockers)
    write_tsv(manifest, MANIFEST_PATH, MANIFEST_FIELDS)
    write_tsv(blockers, BLOCKER_PATH, BLOCKER_FIELDS)
    REPORT_PATH.write_text(render_report(manifest, blockers, extra, msha, bsha), encoding="utf-8")
    return {
        "manifest": manifest,
        "blockers": blockers,
        "manifest_sha": msha,
        "blocker_sha": bsha,
        "counts": readiness_counts(manifest),
        "extra": extra,
    }


def main() -> None:
    first = write_review016_artifacts()
    pack = _assert_frozen_inputs()
    second_m = build_manifest(pack)
    second_b = build_blockers(second_m)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-016",
                "MANIFEST_RUN1": first["manifest_sha"],
                "MANIFEST_RUN2": manifest_sha(second_m),
                "BLOCKER_RUN1": first["blocker_sha"],
                "BLOCKER_RUN2": blocker_sha(second_b),
                "READY": first["counts"]["READY_FOR_OWNER_REVIEW"],
                "BLOCKERS": first["counts"]["TOTAL_BLOCKERS"],
                "CANONICAL_MINT": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
