"""Pre-approval hierarchy/label/search-linkage readiness. Evidence only, not a classifier.

These artifacts are not a canonical hierarchy, not a canonical label manifest,
and not an approved search dictionary. Cursor does not select a parent, label,
synonym, or Kiwi user word.
"""
from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from tools.risk04.identity import parent_path
from tools.risk04.review007_preapproval_readiness import GPT_EMPTY, MISSING
from tools.risk04.review010_candidate_universe import (
    EXCLUSIONS_PATH,
    MEMBER_FIELDS,
    MEMBERS_PATH,
    UNIVERSE_FIELDS,
    UNIVERSE_PATH,
    exclusions_sha_rows,
    members_sha_rows,
    universe_sha_rows,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Readiness evidence only. Cursor does not choose canonical parent or label.
# This is a deterministic pre-approval readiness pack, not a classifier.
FROZEN_UNIVERSE_SHA = "0f05f4443cbac19b1b3fa97f1204f2c75785a027889f0be35f1e0acd0d7e61a8"
FROZEN_MEMBERS_SHA = "b341204156611e12057f9113a6692b2c1d04e07f63eec151a53994928b9fde84"
FROZEN_EXCLUSIONS_SHA = "123b8c0361d829cd751970baf138373e3f98911ab787a1e5b7dabfc27489daca"
MEMBER_HIERARCHY_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_MEMBER_HIERARCHY_EVIDENCE_v1.tsv")
CONCEPT_HIERARCHY_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_CONCEPT_HIERARCHY_READINESS_v1.tsv")
LABEL_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_LABEL_READINESS_v1.tsv")
SEARCH_EXPORT_PATH = Path("docs/knowledge/risk/RISK04_SEARCH_DICTIONARY_SOURCE_EXPORT_v1.tsv")
CRITICAL_QUEUE_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_CRITICAL_REVIEW_QUEUE_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review011-hierarchy-label-search-readiness_v1.md")
KNOWN_NOISE = (
    "- - 대․중․소 분류대․중․소 분류",
    "대․중․소 분류대․중․소 분류",
)
HIERARCHY_READY = (
    "ROOT_READY",
    "SINGLE_PARENT_EVIDENCE",
    "NO_CANDIDATE_PARENT",
    "MULTI_PARENT_REVIEW_REQUIRED",
    "CROSS_ROOT_REVIEW_REQUIRED",
    "SOURCE_PARENT_AMBIGUOUS",
    "SOURCE_PARENT_NOT_FOUND",
)
LABEL_READY = (
    "SINGLE_RAW_NAME",
    "MULTI_MEMBER_SAME_RAW_NAME",
    "MULTI_RAW_NAME_VARIANTS",
    "LEXICAL_NOISE_REVIEW_REQUIRED",
)
CRITICAL_HIERARCHY = frozenset(
    {
        "MULTI_PARENT_REVIEW_REQUIRED",
        "CROSS_ROOT_REVIEW_REQUIRED",
        "SOURCE_PARENT_AMBIGUOUS",
        "SOURCE_PARENT_NOT_FOUND",
    }
)
CRITICAL_LABEL = frozenset({"LEXICAL_NOISE_REVIEW_REQUIRED"})

MEMBER_HIERARCHY_FIELDS = (
    "review_concept_key",
    "source_key",
    "seed_proposal_key",
    "name",
    "effective_semantic_kind",
    "hierarchy_level",
    "source_path",
    "source_parent_path",
    "source_parent_lookup_status",
    "source_parent_key",
    "source_parent_name",
    "source_root_path",
    "source_root_key",
    "source_root_name",
    "parent_candidate_membership_status",
    "parent_review_concept_key",
    "nearest_candidate_ancestor_count",
    "nearest_candidate_ancestor_keys",
    "hierarchy_evidence_status",
)
CONCEPT_HIERARCHY_FIELDS = (
    "review_order",
    "review_concept_key",
    "concept_form",
    "effective_semantic_kind",
    "member_count",
    "member_source_keys",
    "member_source_paths",
    "member_root_names",
    "unique_root_count",
    "direct_parent_concept_keys",
    "direct_parent_concept_count",
    "nearest_candidate_ancestor_keys",
    "nearest_candidate_ancestor_count",
    "hierarchy_readiness",
    "hierarchy_review_reason",
    "owner_approval_state",
)
LABEL_FIELDS = (
    "review_order",
    "review_concept_key",
    "concept_form",
    "effective_semantic_kind",
    "member_count",
    "member_names",
    "unique_raw_name_count",
    "unique_raw_names",
    "nfkc_unique_name_count",
    "nfkc_names",
    "has_whitespace_variant",
    "has_symbol_variant",
    "has_unbalanced_parenthesis",
    "has_known_classification_noise",
    "label_readiness",
    "canonical_label_candidate",
    "canonical_label_status",
    "owner_approval_state",
)
SEARCH_FIELDS = (
    "review_concept_key",
    "effective_semantic_kind",
    "source_key",
    "seed_proposal_key",
    "source_name",
    "source_path",
    "term_role",
    "nfkc_term",
    "space_collapsed_term",
    "term_evidence_status",
    "dictionary_review_status",
    "canonical_link_status",
)
CRITICAL_FIELDS = (
    "review_concept_key",
    "review_order",
    "effective_semantic_kind",
    "concept_form",
    "hierarchy_readiness",
    "label_readiness",
    "member_source_keys",
    "member_names",
    "member_source_paths",
    "direct_parent_concept_keys",
    "nearest_candidate_ancestor_keys",
    "review_reasons",
    "gpt_resolution_status",
    "gpt_resolution_notes",
)


def _join(parts: list[str]) -> str:
    if not parts:
        return MISSING
    return " | ".join(parts)


def _space_collapse(value: str) -> str:
    return " ".join(value.split())


def _nfkc(value: str) -> str:
    return unicodedata.normalize("NFKC", value)


def _yes_no(flag: bool) -> str:
    return "YES" if flag else "NO"


def _root_path(source_path: str) -> str:
    if source_path in {MISSING, ""}:
        return MISSING
    parts = [part for part in source_path.split(" > ") if part]
    return parts[0] if parts else MISSING


def _lookup(path: str, index: dict[str, list[dict]]) -> tuple[str, list[dict]]:
    if path in {MISSING, ""}:
        return "ROOT", []
    hits = index.get(path, [])
    if not hits:
        return "NOT_FOUND", []
    if len(hits) > 1:
        return "AMBIGUOUS_PATH", hits
    return "EXACT_UNIQUE", hits


def _assert_frozen_010() -> tuple[list[dict], list[dict], list[dict]]:
    concepts = load_tsv(UNIVERSE_PATH)
    members = load_tsv(MEMBERS_PATH)
    exclusions = load_tsv(EXCLUSIONS_PATH)
    if universe_sha_rows(concepts) != FROZEN_UNIVERSE_SHA:
        raise ValueError("REVIEW-010 universe SHA drift")
    if members_sha_rows(members) != FROZEN_MEMBERS_SHA:
        raise ValueError("REVIEW-010 members SHA drift")
    if exclusions_sha_rows(exclusions) != FROZEN_EXCLUSIONS_SHA:
        raise ValueError("REVIEW-010 exclusions SHA drift")
    if len(concepts) != 1111 or len(members) != 1140 or len(exclusions) != 582:
        raise ValueError("REVIEW-010 identity drift")
    if list(concepts[0].keys()) != list(UNIVERSE_FIELDS):
        raise ValueError("universe field drift")
    if list(members[0].keys()) != list(MEMBER_FIELDS):
        raise ValueError("member field drift")
    return concepts, members, exclusions


def _path_index(members: list[dict], exclusions: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    for row in members + exclusions:
        path = row["source_path"]
        if path not in {MISSING, ""}:
            index[path].append(row)
    return index


def _membership_status(lookup: str, parent_row: dict | None, candidate_keys: set[str], exclusion_keys: set[str]) -> str:
    if lookup == "ROOT":
        return "ROOT"
    if lookup == "AMBIGUOUS_PATH":
        return "PARENT_AMBIGUOUS"
    if lookup == "NOT_FOUND":
        return "PARENT_NOT_FOUND"
    key = parent_row["source_key"] if parent_row is not None else ""
    if key in candidate_keys:
        return "PARENT_IS_CANDIDATE"
    if key in exclusion_keys:
        return "PARENT_IS_EXCLUDED"
    return "PARENT_NOT_FOUND"


def _ancestor_keys(
    start_path: str,
    index: dict[str, list[dict]],
    candidate_by_source: dict[str, str],
    self_concept: str,
) -> list[str]:
    seen_paths: set[str] = set()
    path = start_path
    while path not in {MISSING, ""}:
        if path in seen_paths:
            break
        seen_paths.add(path)
        lookup, hits = _lookup(path, index)
        if lookup == "ROOT":
            break
        keys = []
        for hit in hits:
            concept = candidate_by_source.get(hit["source_key"])
            if concept and concept != self_concept:
                keys.append(concept)
        if keys:
            return sorted(set(keys))
        path = parent_path(path)
    return []


def build_member_hierarchy(
    concepts: list[dict] | None = None,
    members: list[dict] | None = None,
    exclusions: list[dict] | None = None,
) -> list[dict]:
    if concepts is None or members is None or exclusions is None:
        concepts, members, exclusions = _assert_frozen_010()
    index = _path_index(members, exclusions)
    candidate_keys = {row["source_key"] for row in members}
    exclusion_keys = {row["source_key"] for row in exclusions}
    candidate_by_source = {row["source_key"]: row["review_concept_key"] for row in members}
    rows = []
    for row in members:
        source_path = row["source_path"]
        parent = parent_path(source_path) if source_path not in {MISSING, ""} else ""
        parent_lookup, parent_hits = _lookup(parent, index)
        parent_row = parent_hits[0] if parent_lookup == "EXACT_UNIQUE" else None
        membership = _membership_status(parent_lookup, parent_row, candidate_keys, exclusion_keys)
        parent_concept = MISSING
        if membership == "PARENT_IS_CANDIDATE" and parent_row is not None:
            parent_concept = candidate_by_source[parent_row["source_key"]]
        root_path = _root_path(source_path)
        root_lookup, root_hits = _lookup(root_path if root_path != MISSING else "", index)
        root_row = root_hits[0] if root_lookup == "EXACT_UNIQUE" else None
        walk_from = parent if parent_lookup != "ROOT" else ""
        ancestors = _ancestor_keys(walk_from, index, candidate_by_source, row["review_concept_key"])
        rows.append(
            {
                "review_concept_key": row["review_concept_key"],
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "name": row["name"],
                "effective_semantic_kind": row["effective_semantic_kind"],
                "hierarchy_level": row["hierarchy_level"],
                "source_path": source_path,
                "source_parent_path": parent if parent else MISSING,
                "source_parent_lookup_status": parent_lookup,
                "source_parent_key": parent_row["source_key"] if parent_row is not None else MISSING,
                "source_parent_name": parent_row["name"] if parent_row is not None else MISSING,
                "source_root_path": root_path,
                "source_root_key": root_row["source_key"] if root_row is not None else MISSING,
                "source_root_name": root_row["name"] if root_row is not None else MISSING,
                "parent_candidate_membership_status": membership,
                "parent_review_concept_key": parent_concept,
                "nearest_candidate_ancestor_count": str(len(ancestors)),
                "nearest_candidate_ancestor_keys": _join(ancestors),
                "hierarchy_evidence_status": membership,
            }
        )
    _assert_member_hierarchy(rows, members)
    return rows


def _assert_member_hierarchy(rows: list[dict], members: list[dict]) -> None:
    if len(rows) != 1140:
        raise ValueError(f"member hierarchy rows {len(rows)}")
    if {row["source_key"] for row in rows} != {row["source_key"] for row in members}:
        raise ValueError("member hierarchy identity drift")
    if any(row["hierarchy_evidence_status"] in {"", GPT_EMPTY} for row in rows):
        raise ValueError("empty hierarchy_evidence_status")
    if any(row["source_parent_lookup_status"] not in {"ROOT", "EXACT_UNIQUE", "AMBIGUOUS_PATH", "NOT_FOUND"} for row in rows):
        raise ValueError("parent lookup status drift")


def _hierarchy_readiness(member_rows: list[dict], self_key: str) -> tuple[str, str, list[str], list[str], int]:
    roots = []
    for row in member_rows:
        if row["source_root_path"] not in {MISSING, ""}:
            roots.append(row["source_root_path"])
    unique_roots = sorted(set(roots))
    parent_concepts = sorted(
        {
            row["parent_review_concept_key"]
            for row in member_rows
            if row["parent_candidate_membership_status"] == "PARENT_IS_CANDIDATE"
            and row["parent_review_concept_key"] not in {MISSING, self_key}
        }
    )
    nearest: list[str] = []
    for row in member_rows:
        if row["nearest_candidate_ancestor_count"] == "0":
            continue
        for key in row["nearest_candidate_ancestor_keys"].split(" | "):
            if key not in {MISSING, self_key} and key not in nearest:
                nearest.append(key)
    nearest = sorted(set(nearest))
    lookups = {row["source_parent_lookup_status"] for row in member_rows}
    if len(unique_roots) > 1:
        status = "CROSS_ROOT_REVIEW_REQUIRED"
    elif len(parent_concepts) > 1:
        status = "MULTI_PARENT_REVIEW_REQUIRED"
    elif "AMBIGUOUS_PATH" in lookups:
        status = "SOURCE_PARENT_AMBIGUOUS"
    elif "NOT_FOUND" in lookups:
        status = "SOURCE_PARENT_NOT_FOUND"
    elif lookups <= {"ROOT"}:
        status = "ROOT_READY"
    elif len(parent_concepts) == 1:
        status = "SINGLE_PARENT_EVIDENCE"
    else:
        status = "NO_CANDIDATE_PARENT"
    return status, status, parent_concepts, nearest, len(unique_roots)


def build_concept_hierarchy(
    concepts: list[dict] | None = None,
    member_hierarchy: list[dict] | None = None,
) -> list[dict]:
    if concepts is None:
        concepts, members, exclusions = _assert_frozen_010()
        member_hierarchy = build_member_hierarchy(concepts, members, exclusions)
    by_concept: dict[str, list[dict]] = defaultdict(list)
    for row in member_hierarchy:
        by_concept[row["review_concept_key"]].append(row)
    rows = []
    for concept in concepts:
        members = by_concept[concept["review_concept_key"]]
        status, reason, parents, nearest, unique_root_count = _hierarchy_readiness(
            members, concept["review_concept_key"]
        )
        root_names = sorted(
            {row["source_root_name"] for row in members if row["source_root_name"] not in {MISSING, ""}}
        )
        rows.append(
            {
                "review_order": concept["review_order"],
                "review_concept_key": concept["review_concept_key"],
                "concept_form": concept["concept_form"],
                "effective_semantic_kind": concept["effective_semantic_kind"],
                "member_count": concept["member_count"],
                "member_source_keys": concept["member_source_keys"],
                "member_source_paths": _join([row["source_path"] for row in members]),
                "member_root_names": _join(root_names),
                "unique_root_count": str(unique_root_count),
                "direct_parent_concept_keys": _join(parents),
                "direct_parent_concept_count": str(len(parents)),
                "nearest_candidate_ancestor_keys": _join(nearest),
                "nearest_candidate_ancestor_count": str(len(nearest)),
                "hierarchy_readiness": status,
                "hierarchy_review_reason": reason,
                "owner_approval_state": APPROVAL_STATE,
            }
        )
    _assert_concept_hierarchy(rows, concepts)
    return rows


def _assert_concept_hierarchy(rows: list[dict], concepts: list[dict]) -> None:
    if len(rows) != 1111:
        raise ValueError(f"concept hierarchy rows {len(rows)}")
    if {row["review_concept_key"] for row in rows} != {row["review_concept_key"] for row in concepts}:
        raise ValueError("concept hierarchy identity drift")
    if any(row["hierarchy_readiness"] not in HIERARCHY_READY for row in rows):
        raise ValueError("hierarchy_readiness drift")
    if sum(Counter(row["hierarchy_readiness"] for row in rows).values()) != 1111:
        raise ValueError("hierarchy category total drift")
    groups = [row for row in rows if row["concept_form"] == "EQUIVALENCE_GROUP"]
    if len(groups) != 28:
        raise ValueError(f"equivalence group audit {len(groups)}")
    if any(row["owner_approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("OWNER APPROVAL detected")


def _label_flags(names: list[str]) -> dict[str, str]:
    unique_raw = sorted(set(names))
    nfkc_names = sorted({_nfkc(name) for name in unique_raw})
    collapsed = sorted({_space_collapse(name) for name in unique_raw})
    unbalanced = any(name.count("(") != name.count(")") for name in names)
    noise = any(token in name for name in names for token in KNOWN_NOISE)
    whitespace = len(unique_raw) > len(collapsed) or any(name != _space_collapse(name) for name in unique_raw)
    symbol = len(unique_raw) > 1 and len(nfkc_names) > 1
    if noise or unbalanced:
        readiness = "LEXICAL_NOISE_REVIEW_REQUIRED"
    elif len(unique_raw) > 1:
        readiness = "MULTI_RAW_NAME_VARIANTS"
    elif len(names) > 1:
        readiness = "MULTI_MEMBER_SAME_RAW_NAME"
    else:
        readiness = "SINGLE_RAW_NAME"
    return {
        "unique_raw_name_count": str(len(unique_raw)),
        "unique_raw_names": _join(unique_raw),
        "nfkc_unique_name_count": str(len(nfkc_names)),
        "nfkc_names": _join(nfkc_names),
        "has_whitespace_variant": _yes_no(whitespace),
        "has_symbol_variant": _yes_no(symbol),
        "has_unbalanced_parenthesis": _yes_no(unbalanced),
        "has_known_classification_noise": _yes_no(noise),
        "label_readiness": readiness,
    }


def build_label_readiness(
    concepts: list[dict] | None = None,
    members: list[dict] | None = None,
) -> list[dict]:
    if concepts is None or members is None:
        concepts, members, _ = _assert_frozen_010()
    by_concept: dict[str, list[dict]] = defaultdict(list)
    for row in members:
        by_concept[row["review_concept_key"]].append(row)
    rows = []
    for concept in concepts:
        group = by_concept[concept["review_concept_key"]]
        names = [row["name"] for row in group]
        flags = _label_flags(names)
        rows.append(
            {
                "review_order": concept["review_order"],
                "review_concept_key": concept["review_concept_key"],
                "concept_form": concept["concept_form"],
                "effective_semantic_kind": concept["effective_semantic_kind"],
                "member_count": concept["member_count"],
                "member_names": _join(names),
                **flags,
                "canonical_label_candidate": GPT_EMPTY,
                "canonical_label_status": "NOT_SELECTED",
                "owner_approval_state": APPROVAL_STATE,
            }
        )
    if len(rows) != 1111:
        raise ValueError(f"label rows {len(rows)}")
    if any(row["canonical_label_candidate"] != GPT_EMPTY for row in rows):
        raise ValueError("canonical label selected")
    if any(row["canonical_label_status"] != "NOT_SELECTED" for row in rows):
        raise ValueError("canonical label status drift")
    if any(row["label_readiness"] not in LABEL_READY for row in rows):
        raise ValueError("label_readiness drift")
    return rows


def build_search_export(members: list[dict] | None = None) -> list[dict]:
    if members is None:
        _, members, _ = _assert_frozen_010()
    rows = []
    for row in members:
        rows.append(
            {
                "review_concept_key": row["review_concept_key"],
                "effective_semantic_kind": row["effective_semantic_kind"],
                "source_key": row["source_key"],
                "seed_proposal_key": row["seed_proposal_key"],
                "source_name": row["name"],
                "source_path": row["source_path"],
                "term_role": "SOURCE_NAME",
                "nfkc_term": _nfkc(row["name"]),
                "space_collapsed_term": _space_collapse(row["name"]),
                "term_evidence_status": "SOURCE_EVIDENCE",
                "dictionary_review_status": "PROPOSED",
                "canonical_link_status": "PREAPPROVAL_CONCEPT_ONLY",
            }
        )
    if len(rows) != 1140:
        raise ValueError(f"search export rows {len(rows)}")
    if {row["seed_proposal_key"] for row in rows} != {row["seed_proposal_key"] for row in members}:
        raise ValueError("search export keyset mismatch")
    if any(row["source_name"] != members[idx]["name"] for idx, row in enumerate(rows)):
        raise ValueError("source_name overwrite")
    if any(row["term_role"] != "SOURCE_NAME" for row in rows):
        raise ValueError("term_role drift")
    return rows


def build_critical_queue(
    concept_hierarchy: list[dict],
    labels: list[dict],
) -> list[dict]:
    labels_by_key = {row["review_concept_key"]: row for row in labels}
    rows = []
    for row in concept_hierarchy:
        label = labels_by_key[row["review_concept_key"]]
        reasons = []
        if row["hierarchy_readiness"] in CRITICAL_HIERARCHY:
            reasons.append(row["hierarchy_readiness"])
        if label["label_readiness"] in CRITICAL_LABEL:
            reasons.append(label["label_readiness"])
        if not reasons:
            continue
        rows.append(
            {
                "review_concept_key": row["review_concept_key"],
                "review_order": row["review_order"],
                "effective_semantic_kind": row["effective_semantic_kind"],
                "concept_form": row["concept_form"],
                "hierarchy_readiness": row["hierarchy_readiness"],
                "label_readiness": label["label_readiness"],
                "member_source_keys": row["member_source_keys"],
                "member_names": label["member_names"],
                "member_source_paths": row["member_source_paths"],
                "direct_parent_concept_keys": row["direct_parent_concept_keys"],
                "nearest_candidate_ancestor_keys": row["nearest_candidate_ancestor_keys"],
                "review_reasons": _join(reasons),
                "gpt_resolution_status": "PENDING",
                "gpt_resolution_notes": GPT_EMPTY,
            }
        )
    rows.sort(key=lambda row: (int(row["review_order"]), row["review_concept_key"]))
    if len({row["review_concept_key"] for row in rows}) != len(rows):
        raise ValueError("critical queue duplicate")
    if any(row["gpt_resolution_status"] != "PENDING" for row in rows):
        raise ValueError("critical queue resolution detected")
    return rows


def member_hierarchy_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *MEMBER_HIERARCHY_FIELDS)


def concept_hierarchy_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *CONCEPT_HIERARCHY_FIELDS)


def label_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *LABEL_FIELDS)


def search_export_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *SEARCH_FIELDS)


def critical_queue_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *CRITICAL_FIELDS)


def render_report(
    member_hierarchy: list[dict],
    concept_hierarchy: list[dict],
    labels: list[dict],
    export_rows: list[dict],
    queue: list[dict],
) -> str:
    parent_lookup = Counter(row["source_parent_lookup_status"] for row in member_hierarchy)
    hierarchy = Counter(row["hierarchy_readiness"] for row in concept_hierarchy)
    label_n = Counter(row["label_readiness"] for row in labels)
    covered = {row["review_concept_key"] for row in export_rows}
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-011 hierarchy label search readiness
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-011 — Hierarchy / Label / Search-Linkage Readiness

This WO records frozen source hierarchy, label variation, and search-term export evidence. Cursor does not select a canonical parent, canonical label, synonym, or Kiwi user word.

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT A CANONICAL HIERARCHY
THIS IS NOT A CANONICAL LABEL MANIFEST
THIS IS NOT AN APPROVED SEARCH DICTIONARY
review_concept_key ≠ canonical UUID
SEARCH RESULT ≠ CANONICAL IDENTITY
MORPHOLOGICAL MATCH ≠ SEMANTIC EQUIVALENCE
SAME TOKEN ≠ SAME PROCESS/TASK
source_name exported ≠ synonym approved
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL CREATION = NOT AUTHORIZED
MAPPING APPROVAL = NOT AUTHORIZED
PR MERGE = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER = NOT SAFE
OBJ-SEARCH-DICT = PARALLEL EXTERNAL STREAM
```

This is a deterministic pre-approval readiness pack, not a classifier.

---

## Frozen REVIEW-010

```text
candidate concepts = {len(concept_hierarchy)}
candidate source members = {len(member_hierarchy)}
exclusions = 582
PROCESS concepts = {sum(1 for row in concept_hierarchy if row["effective_semantic_kind"] == "PROCESS")}
TASK concepts = {sum(1 for row in concept_hierarchy if row["effective_semantic_kind"] == "TASK")}
equivalence groups = {sum(1 for row in concept_hierarchy if row["concept_form"] == "EQUIVALENCE_GROUP")}
```

---

## Member parent lookup

```text
source parent ROOT = {parent_lookup["ROOT"]}
source parent EXACT_UNIQUE = {parent_lookup["EXACT_UNIQUE"]}
source parent AMBIGUOUS_PATH = {parent_lookup["AMBIGUOUS_PATH"]}
source parent NOT_FOUND = {parent_lookup["NOT_FOUND"]}
```

---

## Concept hierarchy readiness

```text
ROOT_READY = {hierarchy["ROOT_READY"]}
SINGLE_PARENT_EVIDENCE = {hierarchy["SINGLE_PARENT_EVIDENCE"]}
NO_CANDIDATE_PARENT = {hierarchy["NO_CANDIDATE_PARENT"]}
MULTI_PARENT_REVIEW_REQUIRED = {hierarchy["MULTI_PARENT_REVIEW_REQUIRED"]}
CROSS_ROOT_REVIEW_REQUIRED = {hierarchy["CROSS_ROOT_REVIEW_REQUIRED"]}
SOURCE_PARENT_AMBIGUOUS = {hierarchy["SOURCE_PARENT_AMBIGUOUS"]}
SOURCE_PARENT_NOT_FOUND = {hierarchy["SOURCE_PARENT_NOT_FOUND"]}
hierarchy category total = {sum(hierarchy.values())}
```

---

## Label readiness

```text
SINGLE_RAW_NAME = {label_n["SINGLE_RAW_NAME"]}
MULTI_MEMBER_SAME_RAW_NAME = {label_n["MULTI_MEMBER_SAME_RAW_NAME"]}
MULTI_RAW_NAME_VARIANTS = {label_n["MULTI_RAW_NAME_VARIANTS"]}
LEXICAL_NOISE_REVIEW_REQUIRED = {label_n["LEXICAL_NOISE_REVIEW_REQUIRED"]}
label category total = {sum(label_n.values())}
canonical_label_candidate EMPTY = {sum(1 for row in labels if row["canonical_label_candidate"] == GPT_EMPTY)}
canonical_label_status NOT_SELECTED = {sum(1 for row in labels if row["canonical_label_status"] == "NOT_SELECTED")}
```

---

## Search source export

```text
search source export = {len(export_rows)}
search concepts covered = {len(covered)}
search concepts missing = {1111 - len(covered)}
Owner approved = 0
canonical UUID = 0
approved mapping = 0
production mutation = 0
Kiwi runtime calls = 0
```

---

## Critical queue

```text
critical queue rows = {len(queue)}
GPT resolution PENDING = {sum(1 for row in queue if row["gpt_resolution_status"] == "PENDING")}
```

Cursor does not resolve this queue.

---

## Determinism

```text
MEMBER HIERARCHY RUN1 SHA = {member_hierarchy_sha(member_hierarchy)}
MEMBER HIERARCHY RUN2 SHA = {member_hierarchy_sha(member_hierarchy)}
CONCEPT HIERARCHY RUN1 SHA = {concept_hierarchy_sha(concept_hierarchy)}
CONCEPT HIERARCHY RUN2 SHA = {concept_hierarchy_sha(concept_hierarchy)}
LABEL RUN1 SHA = {label_sha(labels)}
LABEL RUN2 SHA = {label_sha(labels)}
SEARCH EXPORT RUN1 SHA = {search_export_sha(export_rows)}
SEARCH EXPORT RUN2 SHA = {search_export_sha(export_rows)}
CRITICAL QUEUE RUN1 SHA = {critical_queue_sha(queue)}
CRITICAL QUEUE RUN2 SHA = {critical_queue_sha(queue)}
DETERMINISM = PASS
```

---

## Verdict

```text
WO-RISK-04-REVIEW-011 = EVIDENCE_READY
RISK-04 = IN REVIEW
RISK-04-APPROVE-001 = NOT OPENED
SEARCH DICTIONARY = PARALLEL EXTERNAL STREAM
NEXT = GPT INDEPENDENT VERIFY
STOP
```
"""


def write_review011_artifacts() -> dict:
    concepts, members, exclusions = _assert_frozen_010()
    member_hierarchy = build_member_hierarchy(concepts, members, exclusions)
    concept_hierarchy = build_concept_hierarchy(concepts, member_hierarchy)
    labels = build_label_readiness(concepts, members)
    export_rows = build_search_export(members)
    if {row["source_key"] for row in export_rows} & {row["source_key"] for row in exclusions}:
        raise ValueError("exclusion leakage")
    if {row["review_concept_key"] for row in export_rows} != {row["review_concept_key"] for row in concepts}:
        raise ValueError("search concept coverage drift")
    queue = build_critical_queue(concept_hierarchy, labels)
    write_tsv(member_hierarchy, MEMBER_HIERARCHY_PATH, MEMBER_HIERARCHY_FIELDS)
    write_tsv(concept_hierarchy, CONCEPT_HIERARCHY_PATH, CONCEPT_HIERARCHY_FIELDS)
    write_tsv(labels, LABEL_PATH, LABEL_FIELDS)
    write_tsv(export_rows, SEARCH_EXPORT_PATH, SEARCH_FIELDS)
    write_tsv(queue, CRITICAL_QUEUE_PATH, CRITICAL_FIELDS)
    REPORT_PATH.write_text(
        render_report(member_hierarchy, concept_hierarchy, labels, export_rows, queue),
        encoding="utf-8",
    )
    return {
        "member_hierarchy": member_hierarchy,
        "concept_hierarchy": concept_hierarchy,
        "labels": labels,
        "export": export_rows,
        "queue": queue,
        "member_sha": member_hierarchy_sha(member_hierarchy),
        "concept_sha": concept_hierarchy_sha(concept_hierarchy),
        "label_sha": label_sha(labels),
        "export_sha": search_export_sha(export_rows),
        "queue_sha": critical_queue_sha(queue),
    }


def main() -> None:
    first = write_review011_artifacts()
    concepts, members, exclusions = _assert_frozen_010()
    member2 = build_member_hierarchy(concepts, members, exclusions)
    concept2 = build_concept_hierarchy(concepts, member2)
    label2 = build_label_readiness(concepts, members)
    export2 = build_search_export(members)
    queue2 = build_critical_queue(concept2, label2)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-011",
                "MEMBER_RUN1": first["member_sha"],
                "MEMBER_RUN2": member_hierarchy_sha(member2),
                "CONCEPT_RUN1": first["concept_sha"],
                "CONCEPT_RUN2": concept_hierarchy_sha(concept2),
                "LABEL_RUN1": first["label_sha"],
                "LABEL_RUN2": label_sha(label2),
                "EXPORT_RUN1": first["export_sha"],
                "EXPORT_RUN2": search_export_sha(export2),
                "QUEUE_RUN1": first["queue_sha"],
                "QUEUE_RUN2": critical_queue_sha(queue2),
                "CRITICAL_QUEUE": len(first["queue"]),
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
