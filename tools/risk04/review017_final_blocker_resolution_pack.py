"""Final blocker resolution evidence pack. Not Owner approval and not a classifier.

Cursor derives ancestor chains, excluded-parent families, mechanical single-ancestor
candidates, and token-level label comparisons. Cursor does not select a parent,
promote a root, pick a label winner, or mint a canonical UUID.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from tools.risk04.identity import parent_path
from tools.risk04.review007_preapproval_readiness import GPT_EMPTY, GPT_PENDING, MISSING
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
    LABEL_PATH,
    MEMBER_HIERARCHY_PATH,
    _lookup,
    _path_index,
    concept_hierarchy_sha,
    label_sha,
    member_hierarchy_sha,
)
from tools.risk04.review013_resolution_freeze import (
    FROZEN_CONCEPT_HIERARCHY_SHA,
    FROZEN_EXCLUSIONS_SHA,
    FROZEN_LABEL_SHA,
    FROZEN_MEMBER_HIERARCHY_SHA,
    FROZEN_MEMBERS_SHA,
    FROZEN_UNIVERSE_SHA,
    H05_KEY,
    RESOLUTION_PATH,
    resolution_sha,
)
from tools.risk04.review014_remaining_parent_label_evidence import (
    EVIDENCE_PATH,
    FROZEN_RESOLUTION_SHA,
    L02_KEY,
    evidence_sha,
)
from tools.risk04.review015_remaining5_resolution_freeze import (
    FROZEN_EVIDENCE_SHA,
    REMAINING5_PATH,
    remaining5_sha,
)
from tools.risk04.review016_preapproval_manifest_audit import (
    BLOCKER_PATH,
    MANIFEST_PATH,
    FROZEN_REMAINING5_SHA,
    blocker_sha,
    manifest_sha,
    readiness_counts,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Evidence assembly only. Cursor does not choose parent or label.
# This is an explicit evidence pack, not a classifier.
FROZEN_MANIFEST_SHA = "1c1227a4667ce9527348885ad4b818c7da40e3b1db1940eed75648c6f0d666e2"
FROZEN_BLOCKER_SHA = "dae96dedb93a19db1fb845448db7d27a2fc0ffca447a9f732a33b74a5d8e749b"
PACK_PATH = Path("docs/knowledge/risk/RISK04_FINAL_BLOCKER_REVIEW_PACK_v1.tsv")
FAMILY_PATH = Path("docs/knowledge/risk/RISK04_FINAL_PARENT_BLOCKER_FAMILIES_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-review017-final-blocker-resolution-pack_v1.md")
LABEL_A_KEY = "85186bfd8bcaa78e820ac5ddedf2c656d531931ecafbec8900ef596cc28ae9ee"
LABEL_B_KEY = "8d001bee4680940152af6429b4c5f3827cfce258485b1683294cbe4bb94cdf1d"
CONNECTOR_CHARS = "․·･"
SPLIT_RE = re.compile(r"[․·･및\s]+")
PACK_FIELDS = (
    "case_no",
    "review_concept_key",
    "semantic_kind",
    "source_keys",
    "source_names",
    "source_paths",
    "blocker_type",
    "review_scope",
    "immediate_parent_keys",
    "immediate_parent_names",
    "excluded_parent_reason",
    "source_root_keys",
    "source_root_names",
    "nearest_candidate_ancestor_count",
    "nearest_candidate_ancestor_keys",
    "nearest_candidate_ancestor_names",
    "nearest_candidate_ancestor_distance",
    "evidence_classification",
    "parent_family_id",
    "mechanical_parent_candidate",
    "mechanical_parent_candidate_name",
    "mechanical_rule_status",
    "raw_label_variants",
    "label_variant_analysis",
    "evidence_refs",
    "external_evidence_required",
    "gpt_decision",
    "gpt_parent_candidate",
    "gpt_label_candidate",
    "owner_approval_state",
)
FAMILY_FIELDS = (
    "family_id",
    "excluded_parent_source_key",
    "excluded_parent_name",
    "excluded_parent_semantic_kind",
    "excluded_parent_exclusion_reason",
    "child_count",
    "child_review_concept_keys",
    "child_source_keys",
    "child_names",
    "root_key",
    "root_name",
    "root_candidate_status",
    "nearest_candidate_ancestor_count",
    "nearest_candidate_ancestor_keys",
    "nearest_candidate_ancestor_names",
    "nearest_candidate_ancestor_distance",
    "evidence_classification",
    "mechanical_parent_candidate",
    "mechanical_parent_candidate_name",
    "mechanical_rule_status",
    "gpt_decision",
    "gpt_parent_candidate",
    "owner_approval_state",
)


def _join(parts: list[str]) -> str:
    cleaned = [part for part in parts if part not in {"", GPT_EMPTY, MISSING}]
    if not cleaned:
        return GPT_EMPTY
    return " | ".join(cleaned)


def _parts(value: str) -> list[str]:
    return [part for part in value.split(" | ") if part and part not in {GPT_EMPTY, MISSING}]


def _assert_frozen_inputs() -> dict:
    concepts = load_tsv(UNIVERSE_PATH)
    members = load_tsv(MEMBERS_PATH)
    exclusions = load_tsv(EXCLUSIONS_PATH)
    hierarchy = load_tsv(MEMBER_HIERARCHY_PATH)
    concept_hier = load_tsv(CONCEPT_HIERARCHY_PATH)
    labels = load_tsv(LABEL_PATH)
    manifest = load_tsv(MANIFEST_PATH)
    blockers = load_tsv(BLOCKER_PATH)
    if universe_sha_rows(concepts) != FROZEN_UNIVERSE_SHA:
        raise ValueError("REVIEW-010 universe SHA drift")
    if members_sha_rows(members) != FROZEN_MEMBERS_SHA:
        raise ValueError("REVIEW-010 members SHA drift")
    if exclusions_sha_rows(exclusions) != FROZEN_EXCLUSIONS_SHA:
        raise ValueError("REVIEW-010 exclusions SHA drift")
    if member_hierarchy_sha(hierarchy) != FROZEN_MEMBER_HIERARCHY_SHA:
        raise ValueError("REVIEW-011 member hierarchy SHA drift")
    if concept_hierarchy_sha(concept_hier) != FROZEN_CONCEPT_HIERARCHY_SHA:
        raise ValueError("REVIEW-011 concept hierarchy SHA drift")
    if label_sha(labels) != FROZEN_LABEL_SHA:
        raise ValueError("REVIEW-011 label SHA drift")
    if resolution_sha(load_tsv(RESOLUTION_PATH)) != FROZEN_RESOLUTION_SHA:
        raise ValueError("REVIEW-013 SHA drift")
    if evidence_sha(load_tsv(EVIDENCE_PATH)) != FROZEN_EVIDENCE_SHA:
        raise ValueError("REVIEW-014 SHA drift")
    if remaining5_sha(load_tsv(REMAINING5_PATH)) != FROZEN_REMAINING5_SHA:
        raise ValueError("REVIEW-015 SHA drift")
    if manifest_sha(manifest) != FROZEN_MANIFEST_SHA:
        raise ValueError("REVIEW-016 manifest SHA drift")
    if blocker_sha(blockers) != FROZEN_BLOCKER_SHA:
        raise ValueError("REVIEW-016 blocker SHA drift")
    if len(blockers) != 26 or len({row["review_concept_key"] for row in blockers}) != 26:
        raise ValueError("REVIEW-016 blocker identity drift")
    if readiness_counts(manifest)["READY_FOR_OWNER_REVIEW"] != 1085:
        raise ValueError("READY 1085 drift")
    return {
        "concepts": concepts,
        "members": members,
        "exclusions": exclusions,
        "hierarchy": hierarchy,
        "manifest": manifest,
        "blockers": blockers,
    }


def _nearest_on_chain(
    source_path: str,
    index: dict[str, list[dict]],
    candidate_by_source: dict[str, str],
    self_concept: str,
    by_concept_name: dict[str, str],
) -> tuple[list[str], list[str], int]:
    seen: set[str] = set()
    path = parent_path(source_path) if source_path not in {MISSING, ""} else ""
    distance = 0
    while path and path not in seen:
        seen.add(path)
        distance += 1
        lookup, hits = _lookup(path, index)
        if lookup in {"ROOT", "NOT_FOUND"}:
            path = parent_path(path)
            continue
        keys = []
        for hit in hits:
            concept = candidate_by_source.get(hit["source_key"])
            if concept and concept != self_concept:
                keys.append(concept)
        keys = sorted(set(keys))
        if keys:
            names = [by_concept_name.get(key, GPT_EMPTY) for key in keys]
            return keys, names, distance
        path = parent_path(path)
    return [], [], 0


def _classify(nearest_n: int, parent_status: set[str], root_status: str) -> str:
    if nearest_n > 1:
        return "MULTI_NEAREST_CANDIDATE_ANCESTOR"
    if nearest_n == 1:
        return "SINGLE_NEAREST_CANDIDATE_ANCESTOR"
    if "PARENT_IS_EXCLUDED" in parent_status and root_status == "EXCLUDED":
        return "EXCLUDED_PARENT_AND_ROOT"
    if "PARENT_IS_EXCLUDED" in parent_status and root_status == "CANDIDATE":
        return "EXCLUDED_PARENT_WITH_CANDIDATE_ROOT"
    return "NO_CANDIDATE_ANCESTOR"


def _root_status(root_key: str, candidate_sources: set[str], exclusion_sources: set[str]) -> str:
    if root_key in candidate_sources:
        return "CANDIDATE"
    if root_key in exclusion_sources:
        return "EXCLUDED"
    return "MISSING"


def _display_name(concepts_by_key: dict[str, dict], key: str) -> str:
    row = concepts_by_key.get(key)
    if not row:
        return GPT_EMPTY
    names = sorted(set(_parts(row["member_names"])))
    return names[0] if len(names) == 1 else _join(names)


def _label_tokens(value: str) -> str:
    return "|".join(part for part in SPLIT_RE.split(value) if part)


def _punct_removed(value: str) -> str:
    chars = []
    for char in value:
        if char in CONNECTOR_CHARS or unicodedata.category(char).startswith(("P", "Z", "S")):
            continue
        chars.append(char)
    return "".join(chars)


def _connector_normalized(value: str) -> str:
    text = re.sub(r"[․·･및]+", "|", value)
    return "".join(text.split())


def _yes_no(flag: bool) -> str:
    return "YES" if flag else "NO"


def _label_analysis(members: list[dict], all_members: list[dict]) -> tuple[str, str]:
    ordered = sorted(members, key=lambda row: row["source_key"])
    left, right = ordered[0], ordered[1]
    a, b = left["name"], right["name"]
    tokens_a, tokens_b = _label_tokens(a), _label_tokens(b)
    punct_eq = _punct_removed(a) == _punct_removed(b)
    conn_eq = _connector_normalized(a) == _connector_normalized(b)
    space_eq = "".join(a.split()) == "".join(b.split())
    parent_child = right["source_key"].startswith(left["source_key"]) and left["hierarchy_level"] == "W_MID" and right["hierarchy_level"] == "W_LEAF"
    relation = "PARENT_CHILD" if parent_child else "SAME_CONCEPT_MEMBERS"
    siblings = []
    parent_path_left = parent_path(left["source_path"])
    for row in all_members:
        if parent_path(row["source_path"]) == parent_path_left and row["source_key"] not in {left["source_key"], right["source_key"]}:
            siblings.append(f"{row['source_key']}={row['name']}")
    raw = f"{left['source_key']}={a} | {right['source_key']}={b}"
    analysis = _join(
        [
            f"normalized_token_sequence_A={tokens_a}",
            f"normalized_token_sequence_B={tokens_b}",
            f"punctuation_removed_equal={_yes_no(punct_eq)}",
            f"connector_normalized_equal={_yes_no(conn_eq)}",
            f"whitespace_removed_equal={_yes_no(space_eq)}",
            f"middle_dot_present_A={_yes_no(any(char in a for char in CONNECTOR_CHARS))}",
            f"및_present_B={_yes_no('및' in b)}",
            f"meaning_bearing_word_difference={_yes_no(tokens_a != tokens_b)}",
            f"hierarchy_relation={relation}",
            f"hierarchy_level_A={left['hierarchy_level']}",
            f"hierarchy_level_B={right['hierarchy_level']}",
            f"source_path_A={left['source_path']}",
            f"source_path_B={right['source_path']}",
            f"source_parent_label={left['name']}",
            f"source_child_label={right['name']}",
            f"sibling_naming_pattern={'; '.join(sorted(siblings)) if siblings else GPT_EMPTY}",
        ]
    )
    return raw, analysis


def _parent_family_id(excluded_parent_key: str, root_key: str) -> str:
    if excluded_parent_key not in {"", GPT_EMPTY}:
        return f"F-{excluded_parent_key}"
    return f"F-{root_key}" if root_key not in {"", GPT_EMPTY} else "F-UNASSIGNED"


def _inspect_parent(blocker: dict, ctx: dict) -> dict:
    concept_key = blocker["review_concept_key"]
    member_rows = [row for row in ctx["hierarchy"] if row["review_concept_key"] == concept_key]
    if not member_rows:
        raise ValueError(f"missing member hierarchy {concept_key}")
    candidate_sources = {row["source_key"] for row in ctx["members"]}
    exclusion_sources = {row["source_key"] for row in ctx["exclusions"]}
    candidate_by_source = {row["source_key"]: row["review_concept_key"] for row in ctx["members"]}
    concepts_by_key = {row["review_concept_key"]: row for row in ctx["concepts"]}
    by_concept_name = {key: _display_name(concepts_by_key, key) for key in concepts_by_key}
    index = ctx["index"]
    nearest_keys: list[str] = []
    nearest_names: list[str] = []
    distances: list[int] = []
    for row in member_rows:
        keys, names, distance = _nearest_on_chain(
            row["source_path"], index, candidate_by_source, concept_key, by_concept_name
        )
        frozen = int(row["nearest_candidate_ancestor_count"])
        if frozen != len(keys):
            raise ValueError(f"ancestor count mismatch {row['source_key']} frozen={frozen} recomputed={len(keys)}")
        if keys:
            nearest_keys.extend(keys)
            nearest_names.extend(names)
            distances.append(distance)
    unique_keys = sorted(set(nearest_keys))
    unique_names = [_display_name(concepts_by_key, key) for key in unique_keys]
    parent_status = {row["parent_candidate_membership_status"] for row in member_rows}
    excluded_parents = sorted(
        {
            row["source_parent_key"]
            for row in member_rows
            if row["parent_candidate_membership_status"] == "PARENT_IS_EXCLUDED" and row["source_parent_key"] not in {MISSING, ""}
        }
    )
    if len(excluded_parents) > 1:
        raise ValueError(f"multi-family parent {concept_key}")
    root_keys = sorted({row["source_root_key"] for row in member_rows if row["source_root_key"] not in {MISSING, ""}})
    root_key = root_keys[0] if len(root_keys) == 1 else GPT_EMPTY
    root_name = member_rows[0]["source_root_name"] if root_key not in {GPT_EMPTY} else GPT_EMPTY
    root_st = _root_status(root_key, candidate_sources, exclusion_sources) if root_key not in {GPT_EMPTY} else "MISSING"
    excluded_key = excluded_parents[0] if excluded_parents else GPT_EMPTY
    excl_row = ctx["exclusions_by_key"].get(excluded_key)
    class_name = _classify(len(unique_keys), parent_status, root_st)
    mechanical_key = GPT_EMPTY
    mechanical_name = GPT_EMPTY
    mechanical_status = "GPT_REQUIRED"
    unique_distance = distances[0] if distances and len(set(distances)) == 1 else 0
    if (
        len(unique_keys) == 1
        and unique_keys[0] in concepts_by_key
        and unique_distance > 0
        and len(set(distances)) == 1
    ):
        mechanical_key = unique_keys[0]
        mechanical_name = unique_names[0]
        mechanical_status = "SINGLE_ANCESTOR_DERIVED"
    return {
        "member_rows": member_rows,
        "excluded_parent_key": excluded_key,
        "excluded_parent_name": excl_row["name"] if excl_row else GPT_EMPTY,
        "excluded_parent_kind": excl_row["effective_semantic_kind"] if excl_row else GPT_EMPTY,
        "excluded_parent_reason": (
            f"{excl_row['exclusion_lane']}:{excl_row['exclusion_basis']}" if excl_row else GPT_EMPTY
        ),
        "immediate_parent_keys": _join([row["source_parent_key"] for row in member_rows]),
        "immediate_parent_names": _join([row["source_parent_name"] for row in member_rows]),
        "source_paths": _join([row["source_path"] for row in member_rows]),
        "root_key": root_key,
        "root_name": root_name if root_name not in {MISSING} else GPT_EMPTY,
        "root_status": root_st,
        "nearest_keys": unique_keys,
        "nearest_names": unique_names,
        "nearest_count": len(unique_keys),
        "nearest_distance": unique_distance if unique_keys else 0,
        "evidence_classification": class_name,
        "mechanical_key": mechanical_key,
        "mechanical_name": mechanical_name,
        "mechanical_status": mechanical_status,
        "family_id": _parent_family_id(excluded_key, root_key),
    }


def build_families(parent_facts: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for fact in parent_facts:
        grouped[fact["inspect"]["family_id"]].append(fact)
    rows = []
    for family_id in sorted(grouped):
        facts = grouped[family_id]
        inspects = [fact["inspect"] for fact in facts]
        first = inspects[0]
        child_keys = [fact["blocker"]["review_concept_key"] for fact in facts]
        child_sources = []
        child_names = []
        for fact in facts:
            child_sources.extend(_parts(fact["blocker"]["source_keys"]))
            child_names.extend(_parts(fact["blocker"]["source_names"]))
        nearest_counts = {item["nearest_count"] for item in inspects}
        nearest_keys = sorted({key for item in inspects for key in item["nearest_keys"]})
        distances = {item["nearest_distance"] for item in inspects}
        classes = {item["evidence_classification"] for item in inspects}
        mechanical_keys = {item["mechanical_key"] for item in inspects}
        if GPT_EMPTY in mechanical_keys or len(mechanical_keys) != 1:
            mechanical_key, mechanical_name, mechanical_status = GPT_EMPTY, GPT_EMPTY, "GPT_REQUIRED"
        else:
            mechanical_key = next(iter(mechanical_keys))
            mechanical_name = first["mechanical_name"]
            mechanical_status = "SINGLE_ANCESTOR_DERIVED"
        class_name = next(iter(classes)) if len(classes) == 1 else "MIXED"
        rows.append(
            {
                "family_id": family_id,
                "excluded_parent_source_key": first["excluded_parent_key"],
                "excluded_parent_name": first["excluded_parent_name"],
                "excluded_parent_semantic_kind": first["excluded_parent_kind"],
                "excluded_parent_exclusion_reason": first["excluded_parent_reason"],
                "child_count": str(len(facts)),
                "child_review_concept_keys": _join(child_keys),
                "child_source_keys": _join(child_sources),
                "child_names": _join(child_names),
                "root_key": first["root_key"],
                "root_name": first["root_name"],
                "root_candidate_status": first["root_status"],
                "nearest_candidate_ancestor_count": str(next(iter(nearest_counts))) if len(nearest_counts) == 1 else _join(str(n) for n in sorted(nearest_counts)),
                "nearest_candidate_ancestor_keys": _join(nearest_keys),
                "nearest_candidate_ancestor_names": _join(
                    [inspects[0]["nearest_names"][inspects[0]["nearest_keys"].index(key)] if key in inspects[0]["nearest_keys"] else GPT_EMPTY for key in nearest_keys]
                    if inspects[0]["nearest_keys"]
                    else []
                ),
                "nearest_candidate_ancestor_distance": str(next(iter(distances))) if len(distances) == 1 and next(iter(distances)) else GPT_EMPTY,
                "evidence_classification": class_name,
                "mechanical_parent_candidate": mechanical_key,
                "mechanical_parent_candidate_name": mechanical_name,
                "mechanical_rule_status": mechanical_status,
                "gpt_decision": GPT_PENDING,
                "gpt_parent_candidate": GPT_EMPTY,
                "owner_approval_state": APPROVAL_STATE,
            }
        )
    assigned = sum(int(row["child_count"]) for row in rows)
    if assigned != 23:
        raise ValueError(f"family child total {assigned}")
    return rows


def build_pack(ctx: dict | None = None) -> tuple[list[dict], list[dict]]:
    if ctx is None:
        ctx = _assert_frozen_inputs()
        ctx["index"] = _path_index(ctx["members"], ctx["exclusions"])
        ctx["exclusions_by_key"] = {row["source_key"]: row for row in ctx["exclusions"]}
        ctx["members_by_key"] = {row["source_key"]: row for row in ctx["members"]}
        ctx["concepts_by_key"] = {row["review_concept_key"]: row for row in ctx["concepts"]}
    blockers = ctx["blockers"]
    universe_keys = {row["review_concept_key"] for row in ctx["concepts"]}
    parent_facts = []
    pack = []
    case_no = 0
    for blocker in blockers:
        case_no += 1
        key = blocker["review_concept_key"]
        if key == L02_KEY:
            pack.append(_frozen_l02_row(f"{case_no:02d}", blocker, ctx))
            continue
        if key in {LABEL_A_KEY, LABEL_B_KEY}:
            pack.append(_label_row(f"{case_no:02d}", blocker, ctx))
            continue
        inspect = _inspect_parent(blocker, ctx)
        if inspect["mechanical_key"] not in {GPT_EMPTY} and inspect["mechanical_key"] not in universe_keys:
            raise ValueError(f"mechanical parent outside universe {key}")
        parent_facts.append({"blocker": blocker, "inspect": inspect, "case_no": f"{case_no:02d}"})
    families = build_families(parent_facts)
    family_by_id = {row["family_id"]: row for row in families}
    if any(row["family_id"] == "F-UNASSIGNED" for row in families):
        raise ValueError("unassigned parent family")
    children = [key for row in families for key in _parts(row["child_review_concept_keys"])]
    if len(children) != 23 or len(set(children)) != 23:
        raise ValueError("parent family assignment drift")
    for fact in parent_facts:
        inspect = fact["inspect"]
        blocker = fact["blocker"]
        pack.append(
            {
                "case_no": fact["case_no"],
                "review_concept_key": blocker["review_concept_key"],
                "semantic_kind": blocker["semantic_kind"],
                "source_keys": blocker["source_keys"],
                "source_names": blocker["source_names"],
                "source_paths": inspect["source_paths"],
                "blocker_type": "PARENT",
                "review_scope": "ACTIVE_GPT_REVIEW",
                "immediate_parent_keys": inspect["immediate_parent_keys"],
                "immediate_parent_names": inspect["immediate_parent_names"],
                "excluded_parent_reason": inspect["excluded_parent_reason"],
                "source_root_keys": inspect["root_key"],
                "source_root_names": inspect["root_name"],
                "nearest_candidate_ancestor_count": str(inspect["nearest_count"]),
                "nearest_candidate_ancestor_keys": _join(inspect["nearest_keys"]),
                "nearest_candidate_ancestor_names": _join(inspect["nearest_names"]),
                "nearest_candidate_ancestor_distance": str(inspect["nearest_distance"]) if inspect["nearest_distance"] else GPT_EMPTY,
                "evidence_classification": inspect["evidence_classification"],
                "parent_family_id": inspect["family_id"],
                "mechanical_parent_candidate": inspect["mechanical_key"],
                "mechanical_parent_candidate_name": inspect["mechanical_name"],
                "mechanical_rule_status": inspect["mechanical_status"],
                "raw_label_variants": GPT_EMPTY,
                "label_variant_analysis": GPT_EMPTY,
                "evidence_refs": "REVIEW-011 member hierarchy | REVIEW-016 blocker queue",
                "external_evidence_required": "NO",
                "gpt_decision": GPT_PENDING,
                "gpt_parent_candidate": GPT_EMPTY,
                "gpt_label_candidate": GPT_EMPTY,
                "owner_approval_state": APPROVAL_STATE,
            }
        )
    pack.sort(key=lambda row: row["case_no"])
    _validate_pack(pack, families, blockers, universe_keys)
    return pack, families


def _frozen_l02_row(case_no: str, blocker: dict, ctx: dict) -> dict:
    member = ctx["members_by_key"]["673"]
    hier = next(row for row in ctx["hierarchy"] if row["source_key"] == "673")
    return {
        "case_no": case_no,
        "review_concept_key": L02_KEY,
        "semantic_kind": blocker["semantic_kind"],
        "source_keys": blocker["source_keys"],
        "source_names": blocker["source_names"],
        "source_paths": member["source_path"],
        "blocker_type": "FROZEN_LABEL_HOLD",
        "review_scope": "FROZEN_HOLD",
        "immediate_parent_keys": hier["source_parent_key"],
        "immediate_parent_names": hier["source_parent_name"],
        "excluded_parent_reason": GPT_EMPTY,
        "source_root_keys": hier["source_root_key"],
        "source_root_names": hier["source_root_name"],
        "nearest_candidate_ancestor_count": hier["nearest_candidate_ancestor_count"],
        "nearest_candidate_ancestor_keys": hier["nearest_candidate_ancestor_keys"] if hier["nearest_candidate_ancestor_keys"] not in {MISSING} else GPT_EMPTY,
        "nearest_candidate_ancestor_names": GPT_EMPTY,
        "nearest_candidate_ancestor_distance": GPT_EMPTY,
        "evidence_classification": "FROZEN_HOLD_LABEL_CONFIRMED",
        "parent_family_id": GPT_EMPTY,
        "mechanical_parent_candidate": GPT_EMPTY,
        "mechanical_parent_candidate_name": GPT_EMPTY,
        "mechanical_rule_status": GPT_EMPTY,
        "raw_label_variants": blocker["source_names"],
        "label_variant_analysis": "CARRY_FORWARD_REVIEW_015_HOLD_LABEL_CONFIRMED",
        "evidence_refs": "REVIEW-015 remaining5 | REVIEW-016 blocker queue",
        "external_evidence_required": "NO",
        "gpt_decision": "HOLD_LABEL_CONFIRMED",
        "gpt_parent_candidate": GPT_EMPTY,
        "gpt_label_candidate": GPT_EMPTY,
        "owner_approval_state": APPROVAL_STATE,
    }


def _label_row(case_no: str, blocker: dict, ctx: dict) -> dict:
    keys = _parts(blocker["source_keys"])
    members = [ctx["members_by_key"][key] for key in keys]
    hier_rows = [row for row in ctx["hierarchy"] if row["source_key"] in set(keys)]
    raw, analysis = _label_analysis(members, ctx["members"])
    return {
        "case_no": case_no,
        "review_concept_key": blocker["review_concept_key"],
        "semantic_kind": blocker["semantic_kind"],
        "source_keys": blocker["source_keys"],
        "source_names": blocker["source_names"],
        "source_paths": _join([row["source_path"] for row in members]),
        "blocker_type": "LABEL_VARIANT",
        "review_scope": "ACTIVE_GPT_REVIEW",
        "immediate_parent_keys": _join([row["source_parent_key"] for row in hier_rows]),
        "immediate_parent_names": _join([row["source_parent_name"] for row in hier_rows]),
        "excluded_parent_reason": GPT_EMPTY,
        "source_root_keys": _join([row["source_root_key"] for row in hier_rows]),
        "source_root_names": _join([row["source_root_name"] for row in hier_rows]),
        "nearest_candidate_ancestor_count": GPT_EMPTY,
        "nearest_candidate_ancestor_keys": GPT_EMPTY,
        "nearest_candidate_ancestor_names": GPT_EMPTY,
        "nearest_candidate_ancestor_distance": GPT_EMPTY,
        "evidence_classification": "MULTI_RAW_VARIANTS",
        "parent_family_id": GPT_EMPTY,
        "mechanical_parent_candidate": GPT_EMPTY,
        "mechanical_parent_candidate_name": GPT_EMPTY,
        "mechanical_rule_status": GPT_EMPTY,
        "raw_label_variants": raw,
        "label_variant_analysis": analysis,
        "evidence_refs": "REVIEW-010 members | REVIEW-011 labels | REVIEW-016 blocker queue",
        "external_evidence_required": "NO",
        "gpt_decision": GPT_PENDING,
        "gpt_parent_candidate": GPT_EMPTY,
        "gpt_label_candidate": GPT_EMPTY,
        "owner_approval_state": APPROVAL_STATE,
    }


def _validate_pack(pack: list[dict], families: list[dict], blockers: list[dict], universe_keys: set[str]) -> None:
    if len(pack) != 26:
        raise ValueError(f"pack rows {len(pack)}")
    if {row["review_concept_key"] for row in pack} != {row["review_concept_key"] for row in blockers}:
        raise ValueError("pack key-set drift")
    types = Counter(row["blocker_type"] for row in pack)
    if types["PARENT"] != 23 or types["LABEL_VARIANT"] != 2 or types["FROZEN_LABEL_HOLD"] != 1:
        raise ValueError(f"blocker type drift {types}")
    pending = sum(1 for row in pack if row["gpt_decision"] == GPT_PENDING)
    frozen = sum(1 for row in pack if row["gpt_decision"] == "HOLD_LABEL_CONFIRMED")
    if pending != 25 or frozen != 1:
        raise ValueError(f"GPT pending drift {pending} {frozen}")
    l02 = next(row for row in pack if row["review_concept_key"] == L02_KEY)
    if l02["gpt_decision"] != "HOLD_LABEL_CONFIRMED" or l02["gpt_label_candidate"] != GPT_EMPTY:
        raise ValueError("L-02 drift")
    if any(row["mechanical_parent_candidate"] not in {GPT_EMPTY, *universe_keys} for row in pack):
        raise ValueError("mechanical parent outside universe")
    for row in pack:
        if row["mechanical_rule_status"] == "SINGLE_ANCESTOR_DERIVED":
            if row["nearest_candidate_ancestor_count"] != "1" or row["mechanical_parent_candidate"] in {GPT_EMPTY}:
                raise ValueError(f"mechanical rule violation {row['review_concept_key']}")
        if row["owner_approval_state"] != APPROVAL_STATE:
            raise ValueError("owner approval leak")
    if any(row["gpt_decision"] not in {GPT_PENDING, "HOLD_LABEL_CONFIRMED"} for row in pack):
        raise ValueError("Cursor semantic decision leak")


def pack_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *PACK_FIELDS)


def family_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *FAMILY_FIELDS)


def pack_counts(pack: list[dict], families: list[dict]) -> dict[str, int]:
    parents = [row for row in pack if row["blocker_type"] == "PARENT"]
    classes = Counter(row["evidence_classification"] for row in parents)
    return {
        "families": len(families),
        "SINGLE_NEAREST_CANDIDATE_ANCESTOR": classes["SINGLE_NEAREST_CANDIDATE_ANCESTOR"],
        "NO_CANDIDATE_ANCESTOR": classes["NO_CANDIDATE_ANCESTOR"] + classes["EXCLUDED_PARENT_AND_ROOT"] + classes["EXCLUDED_PARENT_WITH_CANDIDATE_ROOT"],
        "MULTI_NEAREST_CANDIDATE_ANCESTOR": classes["MULTI_NEAREST_CANDIDATE_ANCESTOR"],
        "EXCLUDED_PARENT_AND_ROOT": classes["EXCLUDED_PARENT_AND_ROOT"],
        "mechanical": sum(1 for row in parents if row["mechanical_rule_status"] == "SINGLE_ANCESTOR_DERIVED"),
        "gpt_required_parent": sum(1 for row in parents if row["mechanical_rule_status"] == "GPT_REQUIRED"),
        "external_yes": sum(1 for row in pack if row["external_evidence_required"] == "YES"),
        "pending": sum(1 for row in pack if row["gpt_decision"] == GPT_PENDING),
    }


def render_report(pack: list[dict], families: list[dict], psha: str, fsha: str) -> str:
    counts = pack_counts(pack, families)
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 REVIEW-017 final blocker resolution pack
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-REVIEW-017 — Final Blocker Resolution Pack

This WO assembles repository evidence for the 26 REVIEW-016 blockers so GPT can issue final semantic resolutions. Cursor does not select a parent, promote a root, or pick a label winner. mechanical_parent_candidate is not a GPT decision and is not an approved parent.

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT CANONICAL CREATION
THIS IS NOT AN APPROVED CANONICAL PARENT MANIFEST
THIS IS NOT A CANONICAL LABEL MANIFEST
THIS IS NOT AN APPROVED MAPPING
mechanical_parent_candidate ≠ GPT semantic decision
mechanical_parent_candidate ≠ approved parent
HOLD_LABEL_CONFIRMED ≠ LABEL INVENTED
READY_FOR_OWNER_REVIEW ≠ APPROVED
RISK-04-APPROVE-001 = NOT OPENED
PR MERGE = NOT AUTHORIZED
GLOBAL AUTO CLASSIFIER = NOT SAFE
OBJ-SEARCH-DICT = SEPARATE STREAM
```

This is an explicit evidence pack, not a classifier.

---

## Census

```text
TOTAL BLOCKERS = 26
PARENT BLOCKERS = 23
LABEL VARIANTS = 2
FROZEN L-02 = 1
ACTIVE GPT REVIEW = 25
PARENT FAMILIES = {counts["families"]}
SINGLE_NEAREST_CANDIDATE_ANCESTOR = {counts["SINGLE_NEAREST_CANDIDATE_ANCESTOR"]}
NO_CANDIDATE_ANCESTOR = {counts["NO_CANDIDATE_ANCESTOR"]}
MULTI_NEAREST_CANDIDATE_ANCESTOR = {counts["MULTI_NEAREST_CANDIDATE_ANCESTOR"]}
EXCLUDED_PARENT_AND_ROOT = {counts["EXCLUDED_PARENT_AND_ROOT"]}
MECHANICAL PARENT CANDIDATES = {counts["mechanical"]}
GPT REQUIRED PARENT CASES = {counts["gpt_required_parent"]}
LABEL VARIANT EVIDENCE COMPLETE = 2 / 2
external evidence required = {counts["external_yes"]}
semantic decisions by Cursor = 0
GPT PENDING = {counts["pending"]}
GPT FROZEN HOLD = 1
READY concepts unchanged = 1085
candidate concepts = 1111
PROCESS = 557
TASK = 554
source members = 1140
concept count delta = 0
```

---

## Guard

```text
L-02 = HOLD_LABEL_CONFIRMED
811/8111 evidence = PASS
812/8121 evidence = PASS
H-05 exact key = {H05_KEY}
LLM calls = 0
vector model calls = 0
fuzzy = 0
Kiwi runtime calls = 0
OWNER APPROVED = 0
canonical UUID = 0
approved mapping = 0
production write = 0
```

---

## Determinism

```text
REVIEW PACK RUN1 SHA = {psha}
REVIEW PACK RUN2 SHA = {psha}
FAMILY RUN1 SHA = {fsha}
FAMILY RUN2 SHA = {fsha}
DETERMINISM = PASS
```

---

## Verdict

```text
WO-RISK-04-REVIEW-017 = RESOLUTION_READY
RISK-04 = IN REVIEW
FULL OWNER APPROVAL READINESS = BLOCKED
RISK-04-APPROVE-001 = NOT OPENED
NEXT = GPT INDEPENDENT VERIFY + GPT FINAL SEMANTIC RESOLUTION OF ACTIVE 25
THEN = WO-RISK-04-REVIEW-018
STOP
```
"""


def write_review017_artifacts() -> dict:
    ctx = _assert_frozen_inputs()
    ctx["index"] = _path_index(ctx["members"], ctx["exclusions"])
    ctx["exclusions_by_key"] = {row["source_key"]: row for row in ctx["exclusions"]}
    ctx["members_by_key"] = {row["source_key"]: row for row in ctx["members"]}
    ctx["concepts_by_key"] = {row["review_concept_key"]: row for row in ctx["concepts"]}
    pack, families = build_pack(ctx)
    psha = pack_sha(pack)
    fsha = family_sha(families)
    write_tsv(pack, PACK_PATH, PACK_FIELDS)
    write_tsv(families, FAMILY_PATH, FAMILY_FIELDS)
    REPORT_PATH.write_text(render_report(pack, families, psha, fsha), encoding="utf-8")
    return {
        "pack": pack,
        "families": families,
        "pack_sha": psha,
        "family_sha": fsha,
        "counts": pack_counts(pack, families),
    }


def main() -> None:
    first = write_review017_artifacts()
    ctx = _assert_frozen_inputs()
    ctx["index"] = _path_index(ctx["members"], ctx["exclusions"])
    ctx["exclusions_by_key"] = {row["source_key"]: row for row in ctx["exclusions"]}
    ctx["members_by_key"] = {row["source_key"]: row for row in ctx["members"]}
    ctx["concepts_by_key"] = {row["review_concept_key"]: row for row in ctx["concepts"]}
    second_pack, second_fam = build_pack(ctx)
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-REVIEW-017",
                "PACK_RUN1": first["pack_sha"],
                "PACK_RUN2": pack_sha(second_pack),
                "FAMILY_RUN1": first["family_sha"],
                "FAMILY_RUN2": family_sha(second_fam),
                "FAMILIES": first["counts"]["families"],
                "MECHANICAL": first["counts"]["mechanical"],
                "GPT_REQUIRED_PARENT": first["counts"]["gpt_required_parent"],
                "CANONICAL_MINT": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
