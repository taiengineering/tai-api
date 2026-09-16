"""Remaining parent/label blocker evidence. Not a classifier and not Owner approval.

Cursor does not select a canonical parent, canonical label, or architecture option.
KEEP_CONCEPT from REVIEW-013 is frozen identity only. This pack records source
ancestor facts, schema facts, and L-02 raw provenance.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from tools.risk04.review007_preapproval_readiness import GPT_EMPTY, GPT_PENDING, MISSING
from tools.risk04.review009_resolution_freeze import MERGE_GPT_PATH
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
    H05_KEY,
    RESOLUTION_PATH,
    resolution_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Remaining blocker evidence only. Cursor does not choose parent, label, or architecture.
# This is an explicit evidence pack, not a classifier.
FROZEN_RESOLUTION_SHA = "28d0bc4e45206894cbcd1668be1fc744ac0dce5f2fc84021745011feeb3fd686"
EVIDENCE_PATH = Path("docs/knowledge/risk/RISK04_REMAINING_PARENT_LABEL_EVIDENCE_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review014-remaining-parent-label-evidence_v1.md")
CANONICAL_MIGRATION = Path("supabase/migrations/20260916_risk_canonical_mapping.sql")
A_SNAPSHOT_SHA = "bef821019cd32ad9512f865d179852652d1f7aa9536be41b68c6e403fe0baa29"
A_EXTRACTED_SHA = "2cafbe1a1e1ca42e7f5120e1563049c50f717a42a2396fdf1e983920748e9b7d"
L02_EXTRACTED_WINDOW = (
    "673.의료시험및시운전공사실가스공사\n- W-38 -\n대․중․소 분류대․중․소 분류"
    "6731.의료시험및시운전공사실가스설비공사"
)
H02_KEY = "b96f9d30b8931f4768261890e851dbc2960bd14e6d98e1db0078be9a5d6da033"
H03_KEY = "4a6cae8b65bedc11b1616a7a667a747d748907580ba113761f735b55675f5ece"
H04_KEY = "d7a4359635a90a4ae705a4e232e3096c0bbe9b47aa7a1b3470e92af01ce3674e"
L02_KEY = "b04a22eac59269ecbefbb8cb7b88dbc9bb80873d12c84cd2a917409e70d1dd4b"
H02_PARENTS = (
    "9d99ccebbabc3543fa22a500a689aa9c9635bf56f19b31ae3a4c0a79be7f3c4a",
    "22c25c4d80b5f322322cf132f90fa62ee6252d49235e769b6fb93ec87f34cc77",
)
H02_COMMON = "1a13ea0495c762c614f4fa5cbcf476764c9287e017255d6e15df7cb6defa5748"
DEMOLITION_PARENTS = (
    "7813a8d1e3c60d92b3956e15f6ed59cb0f8161ab2b50edab4d4f901288342ed0",
    "3c3ea3dc55db80472b59e9cf2576dc14a2029e2402467451af504591ead80e56",
)
DEMOLITION_COMMON = "13ef25655bb8802c9f2248fa72aa1339b99db5cd94f16bd2ae8d59f8ac83db00"
CASES = (
    ("H-02", H02_KEY, "PARENT_MODELING"),
    ("H-03", H03_KEY, "PARENT_MODELING"),
    ("H-04", H04_KEY, "PARENT_MODELING"),
    ("H-05", H05_KEY, "PARENT_MODELING"),
    ("L-02", L02_KEY, "LABEL_HOLD"),
)
EVIDENCE_FIELDS = (
    "case_id",
    "review_concept_key",
    "source_keys",
    "issue_type",
    "direct_parent_concept_keys",
    "direct_parent_names",
    "direct_parent_count",
    "common_candidate_ancestor_key",
    "common_candidate_ancestor_name",
    "common_candidate_ancestor_distance",
    "common_ancestor_evidence_status",
    "current_canonical_structure",
    "source_context_preservable",
    "architecture_evidence_refs",
    "parent_family_sibling_names",
    "review009_member_resolutions",
    "same_name_peer_paths",
    "raw_name",
    "raw_child_names",
    "raw_child_source_keys",
    "raw_sibling_names",
    "raw_provenance_status",
    "raw_evidence_refs",
    "external_evidence_required",
    "semantic_decision",
    "canonical_parent_candidate",
    "canonical_label_candidate",
    "gpt_resolution_status",
    "owner_approval_state",
)


def _join(parts: list[str]) -> str:
    if not parts:
        return GPT_EMPTY
    return " | ".join(parts)


def _assert_frozen_inputs() -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    concepts = load_tsv(UNIVERSE_PATH)
    members = load_tsv(MEMBERS_PATH)
    exclusions = load_tsv(EXCLUSIONS_PATH)
    hierarchy = load_tsv(MEMBER_HIERARCHY_PATH)
    resolution = load_tsv(RESOLUTION_PATH)
    if universe_sha_rows(concepts) != FROZEN_UNIVERSE_SHA:
        raise ValueError("REVIEW-010 universe SHA drift")
    if members_sha_rows(members) != FROZEN_MEMBERS_SHA:
        raise ValueError("REVIEW-010 members SHA drift")
    if exclusions_sha_rows(exclusions) != FROZEN_EXCLUSIONS_SHA:
        raise ValueError("REVIEW-010 exclusions SHA drift")
    if member_hierarchy_sha(hierarchy) != FROZEN_MEMBER_HIERARCHY_SHA:
        raise ValueError("REVIEW-011 member hierarchy SHA drift")
    if concept_hierarchy_sha(load_tsv(CONCEPT_HIERARCHY_PATH)) != FROZEN_CONCEPT_HIERARCHY_SHA:
        raise ValueError("REVIEW-011 concept hierarchy SHA drift")
    if label_sha(load_tsv(LABEL_PATH)) != FROZEN_LABEL_SHA:
        raise ValueError("REVIEW-011 label SHA drift")
    if search_export_sha(load_tsv(SEARCH_EXPORT_PATH)) != FROZEN_SEARCH_EXPORT_SHA:
        raise ValueError("REVIEW-011 search export SHA drift")
    if critical_queue_sha(load_tsv(CRITICAL_QUEUE_PATH)) != FROZEN_QUEUE_SHA:
        raise ValueError("REVIEW-011 critical queue SHA drift")
    if resolution_sha(resolution) != FROZEN_RESOLUTION_SHA:
        raise ValueError("REVIEW-013 resolution SHA drift")
    if len(concepts) != 1111:
        raise ValueError("concept count drift")
    return concepts, members, exclusions, hierarchy, resolution


def inspect_architecture() -> dict[str, str]:
    sql = CANONICAL_MIGRATION.read_text(encoding="utf-8")
    has_parent_id = "parent_id uuid REFERENCES public.risk_canonical_nodes (id)," in sql
    has_mapping = "CREATE TABLE IF NOT EXISTS public.risk_source_mappings (" in sql
    has_evidence = "evidence jsonb NOT NULL DEFAULT '{}'::jsonb" in sql
    forbidden = (
        "CREATE TABLE IF NOT EXISTS public.risk_canonical_parents",
        "CREATE TABLE IF NOT EXISTS public.risk_canonical_relations",
        "alternate_hierarchy",
        "multi_parent",
    )
    if any(token in sql for token in forbidden):
        structure = "MULTI_PARENT_RELATION_EXISTS"
    elif has_parent_id:
        structure = "SINGLE_PARENT_ONLY"
    else:
        structure = "OTHER"
    preservable = "YES" if has_mapping and has_evidence else "UNVERIFIED"
    refs = [
        "supabase/migrations/20260916_risk_canonical_mapping.sql#risk_canonical_nodes.parent_id",
        "supabase/migrations/20260916_risk_canonical_mapping.sql#risk_source_mappings.evidence",
        "supabase/migrations/20260916_risk_canonical_mapping.sql#mapping_type",
    ]
    return {
        "current_canonical_structure": structure,
        "source_context_preservable": preservable,
        "architecture_evidence_refs": _join(refs),
    }


def parsed_l02_names() -> tuple[str, str]:
    section = re.sub(r"W-\d+", " ", L02_EXTRACTED_WINDOW)
    pairs = re.findall(r"(\d{2,4})\.([^0-9]+)", section)
    by_code = {}
    for code, name in pairs:
        cleaned = re.sub(r"[\s/·ㆍ・,]+", " ", name).strip()
        by_code[code] = cleaned
    if "673" not in by_code or "6731" not in by_code:
        raise ValueError("L-02 extracted window missing 673/6731")
    return by_code["673"], by_code["6731"]


def _by_source(hierarchy: list[dict]) -> dict[str, dict]:
    return {row["source_key"]: row for row in hierarchy}


def _parent_chain(source_key: str, by_src: dict[str, dict]) -> list[dict]:
    chain: list[dict] = []
    seen: set[str] = set()
    current = by_src[source_key]
    while True:
        parent_key = current["source_parent_key"]
        if parent_key in {"", MISSING} or parent_key in seen or parent_key not in by_src:
            break
        seen.add(parent_key)
        parent = by_src[parent_key]
        chain.append(parent)
        current = parent
    return chain


def _common_ancestor(member_keys: list[str], by_src: dict[str, dict]) -> tuple[str, str, str, str]:
    chains = []
    for key in member_keys:
        direct = _parent_chain(key, by_src)
        if not direct:
            raise ValueError(f"missing parent chain {key}")
        chains.append(direct)
    chain_key_lists = [[row["review_concept_key"] for row in chain] for chain in chains]
    first_keys = chain_key_lists[0]
    other = [set(keys) for keys in chain_key_lists[1:]]
    for idx, concept_key in enumerate(first_keys):
        if all(concept_key in group for group in other):
            distances = [keys.index(concept_key) for keys in chain_key_lists]
            name = chains[0][idx]["name"]
            return concept_key, name, _join(str(d) for d in distances), "NEAREST_COMMON_CANDIDATE_ANCESTOR"
    return GPT_EMPTY, GPT_EMPTY, GPT_EMPTY, "NO_COMMON_CANDIDATE_ANCESTOR"


def _siblings(parent_key: str, by_src: dict[str, dict]) -> list[dict]:
    return sorted(
        [row for row in by_src.values() if row["source_parent_key"] == parent_key],
        key=lambda row: row["source_key"],
    )


def _same_name_peers(name: str, member_keys: set[str], hierarchy: list[dict]) -> list[str]:
    paths = []
    for row in hierarchy:
        if row["name"] == name and row["source_key"] not in member_keys:
            paths.append(f"{row['source_key']}:{row['source_path']}")
    return sorted(paths)


def build_evidence(
    concepts: list[dict] | None = None,
    hierarchy: list[dict] | None = None,
    resolution: list[dict] | None = None,
) -> list[dict]:
    if concepts is None or hierarchy is None or resolution is None:
        concepts, _, _, hierarchy, resolution = _assert_frozen_inputs()
    by_src = _by_source(hierarchy)
    by_resolution = {row["review_concept_key"]: row for row in resolution}
    merge_by_key = {row["source_key"]: row["gpt_merge_resolution"] for row in load_tsv(MERGE_GPT_PATH)}
    architecture = inspect_architecture()
    parsed_673, parsed_6731 = parsed_l02_names()
    rows = []
    for case_id, concept_key, issue in CASES:
        frozen = by_resolution[concept_key]
        member_keys = [key for key in frozen["source_keys"].split(" | ") if key]
        member_rows = [by_src[key] for key in member_keys]
        parent_rows = []
        for member in member_rows:
            chain = _parent_chain(member["source_key"], by_src)
            if chain:
                parent_rows.append(chain[0])
        parent_keys = [row["review_concept_key"] for row in parent_rows]
        parent_names = [row["name"] for row in parent_rows]
        if issue == "PARENT_MODELING":
            common_key, common_name, distances, status = _common_ancestor(member_keys, by_src)
            sibling_names = []
            seen_sib: set[str] = set()
            for parent in parent_rows:
                for sib in _siblings(parent["source_key"], by_src):
                    token = f"{sib['source_key']}:{sib['name']}"
                    if token not in seen_sib:
                        seen_sib.add(token)
                        sibling_names.append(token)
            merge_bits = []
            for key in member_keys:
                merge_bits.append(f"{key}:{merge_by_key.get(key, GPT_EMPTY)}")
            if case_id in {"H-03", "H-04", "H-05"}:
                for extra in ("1869", "1879"):
                    merge_bits.append(f"{extra}:{merge_by_key.get(extra, GPT_EMPTY)}")
            raw_child = GPT_EMPTY
            raw_child_keys = GPT_EMPTY
            raw_siblings = GPT_EMPTY
            provenance = GPT_EMPTY
            raw_refs = GPT_EMPTY
            external = "NO"
        else:
            common_key = GPT_EMPTY
            common_name = GPT_EMPTY
            distances = GPT_EMPTY
            status = "NOT_APPLICABLE"
            sibling_names = [f"{row['source_key']}:{row['name']}" for row in _siblings(member_rows[0]["source_parent_key"], by_src)]
            merge_bits = [GPT_EMPTY]
            children = _siblings("673", by_src)
            raw_child = _join(row["name"] for row in children)
            raw_child_keys = _join(row["source_key"] for row in children)
            raw_siblings = _join(row["name"] for row in _siblings("67", by_src))
            if parsed_673 != member_rows[0]["name"]:
                raise ValueError("L-02 parsed window != frozen source_name")
            if "6731" not in raw_child_keys:
                raise ValueError("L-02 child 6731 missing")
            if parsed_6731 not in raw_child:
                raise ValueError("L-02 child name drift")
            provenance = "RAW_SOURCE_SHOWS_PARSER_CORRUPTION"
            raw_refs = _join(
                [
                    "artifacts/risk01/source_a/cic_annex_extracted.txt",
                    f"A_SNAPSHOT_SHA={A_SNAPSHOT_SHA}",
                    f"A_EXTRACTED_SHA={A_EXTRACTED_SHA}",
                    "tools/risk01/analyze_3way.py:parse_a_works",
                    "docs/knowledge/risk/OBJ_risk01-3way-taxonomy-contract_v1.md",
                ]
            )
            external = "NO"
        rows.append(
            {
                "case_id": case_id,
                "review_concept_key": concept_key,
                "source_keys": frozen["source_keys"],
                "issue_type": issue,
                "direct_parent_concept_keys": _join(parent_keys),
                "direct_parent_names": _join(parent_names),
                "direct_parent_count": str(len(parent_keys)),
                "common_candidate_ancestor_key": common_key,
                "common_candidate_ancestor_name": common_name,
                "common_candidate_ancestor_distance": distances,
                "common_ancestor_evidence_status": status,
                "current_canonical_structure": architecture["current_canonical_structure"],
                "source_context_preservable": architecture["source_context_preservable"],
                "architecture_evidence_refs": architecture["architecture_evidence_refs"],
                "parent_family_sibling_names": _join(sibling_names),
                "review009_member_resolutions": _join(merge_bits),
                "same_name_peer_paths": _join(
                    _same_name_peers(member_rows[0]["name"], set(member_keys), hierarchy)
                ),
                "raw_name": member_rows[0]["name"] if len(member_rows) == 1 else _join(row["name"] for row in member_rows),
                "raw_child_names": raw_child,
                "raw_child_source_keys": raw_child_keys,
                "raw_sibling_names": raw_siblings,
                "raw_provenance_status": provenance,
                "raw_evidence_refs": raw_refs,
                "external_evidence_required": external,
                "semantic_decision": "NOT_SELECTED",
                "canonical_parent_candidate": GPT_EMPTY,
                "canonical_label_candidate": GPT_EMPTY,
                "gpt_resolution_status": GPT_PENDING,
                "owner_approval_state": APPROVAL_STATE,
            }
        )
    _validate(rows, by_src)
    return rows


def _validate(rows: list[dict], by_src: dict[str, dict]) -> None:
    if len(rows) != 5 or len({row["case_id"] for row in rows}) != 5:
        raise ValueError("evidence identity drift")
    if [row["case_id"] for row in rows] != [case[0] for case in CASES]:
        raise ValueError("case order drift")
    by_id = {row["case_id"]: row for row in rows}
    if by_id["H-05"]["review_concept_key"] != H05_KEY:
        raise ValueError("H-05 key drift")
    for case_id in ("H-02", "H-03", "H-04", "H-05"):
        if by_id[case_id]["direct_parent_count"] != "2":
            raise ValueError(f"{case_id} parent count drift")
        if by_id[case_id]["common_ancestor_evidence_status"] != "NEAREST_COMMON_CANDIDATE_ANCESTOR":
            raise ValueError(f"{case_id} common ancestor missing")
    if set(by_id["H-02"]["direct_parent_concept_keys"].split(" | ")) != set(H02_PARENTS):
        raise ValueError("H-02 parent key drift")
    if by_id["H-02"]["common_candidate_ancestor_key"] != H02_COMMON:
        raise ValueError("H-02 common ancestor drift")
    for case_id in ("H-03", "H-04", "H-05"):
        if set(by_id[case_id]["direct_parent_concept_keys"].split(" | ")) != set(DEMOLITION_PARENTS):
            raise ValueError(f"{case_id} demolition parent drift")
        if by_id[case_id]["common_candidate_ancestor_key"] != DEMOLITION_COMMON:
            raise ValueError(f"{case_id} demolition ancestor drift")
    if "673" not in by_id["L-02"]["source_keys"]:
        raise ValueError("L-02 source 673 missing")
    if "6731" not in by_id["L-02"]["raw_child_source_keys"]:
        raise ValueError("L-02 child 6731 missing")
    if by_src["6731"]["source_parent_key"] != "673":
        raise ValueError("6731 parent drift")
    if any(row["semantic_decision"] != "NOT_SELECTED" for row in rows):
        raise ValueError("semantic decision leak")
    if any(row["canonical_parent_candidate"] != GPT_EMPTY for row in rows):
        raise ValueError("canonical parent leak")
    if any(row["canonical_label_candidate"] != GPT_EMPTY for row in rows):
        raise ValueError("canonical label leak")
    if any(row["gpt_resolution_status"] != GPT_PENDING for row in rows):
        raise ValueError("gpt status drift")
    if any(row["owner_approval_state"] != APPROVAL_STATE for row in rows):
        raise ValueError("owner approval leak")
    if any(row["current_canonical_structure"] != "SINGLE_PARENT_ONLY" for row in rows):
        raise ValueError("architecture drift")
    if any(row["source_context_preservable"] != "YES" for row in rows):
        raise ValueError("mapping evidence drift")


def evidence_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *EVIDENCE_FIELDS)


def render_report(rows: list[dict], sha: str) -> str:
    by_id = {row["case_id"]: row for row in rows}
    lines = [
        "CASE | ISSUE | EVIDENCE STATUS | GPT DECISION",
        f"H-02 | PARENT_MODELING | {by_id['H-02']['common_ancestor_evidence_status']} | PENDING",
        f"H-03 | PARENT_MODELING | {by_id['H-03']['common_ancestor_evidence_status']} | PENDING",
        f"H-04 | PARENT_MODELING | {by_id['H-04']['common_ancestor_evidence_status']} | PENDING",
        f"H-05 | PARENT_MODELING | {by_id['H-05']['common_ancestor_evidence_status']} | PENDING",
        f"L-02 | LABEL_HOLD      | {by_id['L-02']['raw_provenance_status']} | PENDING",
    ]
    table = "\n".join(lines)
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-014 remaining parent label evidence
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-014 — Remaining Parent / Label Blocker Evidence

This WO records source-ancestor, schema, and L-02 provenance facts for five unresolved blockers. Cursor does not select a canonical parent, canonical label, multi-parent architecture, or Owner approval.

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT A CANONICAL PARENT SELECTION
THIS IS NOT A CANONICAL LABEL
THIS IS NOT AN ARCHITECTURE DECISION
NEAREST_COMMON_CANDIDATE_ANCESTOR ≠ canonical parent_id
RAW_SOURCE_SHOWS_PARSER_CORRUPTION ≠ restored label
review_concept_key ≠ canonical UUID
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL CREATION = NOT AUTHORIZED
MAPPING APPROVAL = NOT AUTHORIZED
PR MERGE = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER = NOT SAFE
```

This is an explicit evidence pack, not a classifier.

---

## Case table

```text
{table}
```

---

## Parent modeling

```text
H-02 direct parents = {by_id["H-02"]["direct_parent_count"]}
H-02 direct parent names = {by_id["H-02"]["direct_parent_names"]}
H-02 common ancestor = {by_id["H-02"]["common_candidate_ancestor_name"]}
H-02 common ancestor key = {by_id["H-02"]["common_candidate_ancestor_key"]}
H-02 distance = {by_id["H-02"]["common_candidate_ancestor_distance"]}
H-03/H-04/H-05 common ancestor = {by_id["H-03"]["common_candidate_ancestor_name"]}
H-03/H-04/H-05 common ancestor key = {by_id["H-03"]["common_candidate_ancestor_key"]}
H-03/H-04/H-05 distance = {by_id["H-03"]["common_candidate_ancestor_distance"]}
REVIEW-009 배관철거/장비철거/잡철물철거 = MERGE_CONFIRMED frozen
REVIEW-009 기타설비철거 = KEEP_SEPARATE frozen
```

Cursor does not choose among selecting one source parent, lifting to the common ancestor, or separating canonical parent_id from source-context relations.

---

## Canonical structure measured

```text
CANONICAL STRUCTURE = {rows[0]["current_canonical_structure"]}
SOURCE CONTEXT PRESERVABLE OUTSIDE parent_id = {rows[0]["source_context_preservable"]}
EVIDENCE = {rows[0]["architecture_evidence_refs"]}
NEW MIGRATION = 0
```

`risk_canonical_nodes.parent_id` is a single nullable self-FK. No canonical multi-parent relation table exists in the measured migration. `risk_source_mappings.evidence` can store source path/context separately from canonical `parent_id`.

---

## L-02 raw provenance

```text
source_key = 673
child source_key = 6731
raw_name = {by_id["L-02"]["raw_name"]}
raw_child_names = {by_id["L-02"]["raw_child_names"]}
raw_provenance_status = {by_id["L-02"]["raw_provenance_status"]}
external_evidence_required = {by_id["L-02"]["external_evidence_required"]}
canonical_label_candidate = EMPTY
```

Frozen extracted window after `673.` continues through page marker `- W-38 -` and table header `대․중․소 분류대․중․소 분류` until `6731.`. `parse_a_works` strips `W-\\d+` then captures `([^0-9]+)`, which is why the header remains on source_key 673. The remaining stem is present as a single extracted token; this pack does not split or restore it.

---

## Guard

```text
semantic_decision NOT_SELECTED = 5
canonical_parent_candidate EMPTY = 5
canonical_label_candidate EMPTY = 5
gpt_resolution_status PENDING = 5
owner_approval_state NOT_APPROVED = 5
canonical UUID created = 0
approved mapping = 0
production DB write = 0
new migration = 0
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
WO-RISK-04-REVIEW-014 = EVIDENCE_READY
RISK-04 = IN REVIEW
RISK-04-APPROVE-001 = NOT OPENED
CANONICAL = NOT OPENED
MAPPING = NOT OPENED
NEXT = GPT INDEPENDENT VERIFY THEN GPT SEMANTIC RESOLUTION OF 5 CASES
STOP
```
"""


def write_review014_artifacts() -> dict:
    concepts, _, _, hierarchy, resolution = _assert_frozen_inputs()
    rows = build_evidence(concepts, hierarchy, resolution)
    sha = evidence_sha(rows)
    write_tsv(rows, EVIDENCE_PATH, EVIDENCE_FIELDS)
    REPORT_PATH.write_text(render_report(rows, sha), encoding="utf-8")
    return {"rows": rows, "sha": sha}


def main() -> None:
    first = write_review014_artifacts()
    concepts, _, _, hierarchy, resolution = _assert_frozen_inputs()
    second = build_evidence(concepts, hierarchy, resolution)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-014",
                "RUN1": first["sha"],
                "RUN2": evidence_sha(second),
                "ROWS": len(first["rows"]),
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
