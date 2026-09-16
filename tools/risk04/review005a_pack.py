"""LEAF Batch004A compact GPT adjudication pack. Cursor does not decide semantic kind."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from tools.risk04.review004_leaf_routing import LEAF_FIELDS, load_leaf_batch
from tools.risk04.review_decisions import write_tsv
from tools.risk04.seed_review import universe_sha

FROZEN_004A_SHA = "23e15185bc004c62432f8044596995a1106759d2f1febe399bd76c6b9265c894"
INPUT_004A_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004A_REVIEW_INPUT.tsv")
PACK_004A_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004A_GPT_REVIEW_PACK.tsv")
GROUPS_004A_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004A_PARENT_GROUPS.md")

COMPACT_FIELDS = (
    "review_no",
    "seed_proposal_key",
    "source_key",
    "name",
    "source_path",
    "root_name",
    "root_source_key",
    "parent_name",
    "parent_source_key",
    "parent_semantic_kind",
    "parent_review_decision",
    "parent_leaf_family_policy",
    "sibling_count",
    "sibling_names",
    "reviewed_sibling_count",
    "reviewed_sibling_refs",
    "same_name_cicw_count",
    "same_name_cicw_paths",
    "same_name_other_source_count",
    "same_name_other_source_refs",
    "lexical_cues",
    "gpt_semantic_kind",
    "gpt_review_decision",
    "merge_candidate_keys",
    "gpt_reason",
)

FORBIDDEN_SUMMARY = (
    "이 family는 PROCESS다",
    "이 자식들은 TASK다",
    "자동 적용 가능",
    "canonical 후보",
)


def assert_frozen_004a() -> list[dict]:
    rows = load_leaf_batch(INPUT_004A_PATH)
    digest = universe_sha(rows, *LEAF_FIELDS)
    if digest != FROZEN_004A_SHA:
        raise ValueError("frozen 004A input SHA mismatch")
    if len(rows) != 200:
        raise ValueError(f"004A rows {len(rows)}")
    if [int(row["review_no"]) for row in rows] != list(range(692, 892)):
        raise ValueError("004A review_no drift")
    if any(row["gpt_semantic_kind"] != "PENDING" for row in rows):
        raise ValueError("004A input already has GPT kind")
    return rows


def build_compact_pack(rows: list[dict] | None = None) -> list[dict]:
    rows = rows if rows is not None else assert_frozen_004a()
    pack = []
    for row in rows:
        pack.append(
            {
                "review_no": row["review_no"],
                "seed_proposal_key": row["seed_proposal_key"],
                "source_key": row["source_key"],
                "name": row["name"],
                "source_path": row["source_path"],
                "root_name": row["root_name"],
                "root_source_key": row["root_source_key"],
                "parent_name": row["parent_name"],
                "parent_source_key": row["parent_source_key"],
                "parent_semantic_kind": row["parent_semantic_kind"],
                "parent_review_decision": row["parent_review_decision"],
                "parent_leaf_family_policy": row["parent_leaf_family_policy"],
                "sibling_count": row["sibling_count"],
                "sibling_names": row["sibling_names"],
                "reviewed_sibling_count": row["reviewed_sibling_count"],
                "reviewed_sibling_refs": row["reviewed_sibling_refs"],
                "same_name_cicw_count": row["same_name_cicw_count"],
                "same_name_cicw_paths": row["same_name_cicw_paths"],
                "same_name_other_source_count": row["same_name_other_source_count"],
                "same_name_other_source_refs": row["same_name_other_source_refs"],
                "lexical_cues": row["lexical_cues"],
                "gpt_semantic_kind": "PENDING",
                "gpt_review_decision": "PENDING",
                "merge_candidate_keys": "EMPTY",
                "gpt_reason": "EMPTY",
            }
        )
    if [row["seed_proposal_key"] for row in pack] != [row["seed_proposal_key"] for row in rows]:
        raise ValueError("compact proposal key drift")
    if [row["source_key"] for row in pack] != [row["source_key"] for row in rows]:
        raise ValueError("compact source_key drift")
    if [int(row["review_no"]) for row in pack] != list(range(692, 892)):
        raise ValueError("compact review_no reordered")
    original = {row["seed_proposal_key"] for row in rows}
    compact = {row["seed_proposal_key"] for row in pack}
    if original != compact:
        raise ValueError("compact keyset mismatch")
    return pack


def compact_pack_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *COMPACT_FIELDS)


def parent_groups(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["root_source_key"], row["parent_source_key"])].append(row)
    out = []
    for root_key, parent_key in sorted(grouped):
        kids = grouped[(root_key, parent_key)]
        nos = [int(row["review_no"]) for row in kids]
        sibling_refs = []
        seen_refs = set()
        for row in kids:
            for ref in (row["reviewed_sibling_refs"] or "").split(" | "):
                if ref and ref not in seen_refs:
                    seen_refs.add(ref)
                    sibling_refs.append(ref)
        first = kids[0]
        out.append(
            {
                "root_name": first["root_name"],
                "root_source_key": first["root_source_key"],
                "parent_source_key": first["parent_source_key"],
                "parent_name": first["parent_name"],
                "parent_semantic_kind": first["parent_semantic_kind"],
                "parent_review_decision": first["parent_review_decision"],
                "parent_leaf_family_policy": first["parent_leaf_family_policy"],
                "child_count": len(kids),
                "review_no_min": min(nos),
                "review_no_max": max(nos),
                "review_no_list": ",".join(str(n) for n in nos),
                "child_names": " | ".join(row["name"] for row in kids),
                "reviewed_sibling_evidence": " | ".join(sibling_refs),
            }
        )
    return out


def render_parent_groups(groups: list[dict]) -> str:
    lines = [
        "---",
        "class: records",
        "type: report",
        "scope: knowledge",
        "project: risk",
        "title: OBJ-RISK-04 REVIEW-005A LEAF 004A parent groups",
        "version: 1",
        "status: active",
        "owner: taiwang",
        "---",
        "",
        "# LEAF Batch004A parent group evidence",
        "",
        "Source/evidence summary only. Parent kind, family policy, sibling kind, and same-name hits are not leaf decisions.",
        "",
        "```text",
        "004A rows = 200",
        "review_no = 692..891",
        f"parent groups = {len(groups)}",
        "gpt_semantic_kind = PENDING 200",
        "gpt_review_decision = PENDING 200",
        "```",
        "",
    ]
    for group in groups:
        lines.extend(
            [
                f"## {group['parent_source_key']} {group['parent_name']}",
                "",
                "```text",
                f"root = {group['root_name']} / {group['root_source_key']}",
                f"parent source_key = {group['parent_source_key']}",
                f"parent name = {group['parent_name']}",
                f"parent semantic kind = {group['parent_semantic_kind']}",
                f"parent review decision = {group['parent_review_decision']}",
                f"parent family policy = {group['parent_leaf_family_policy']}",
                f"004A child count = {group['child_count']}",
                f"004A review_no range = {group['review_no_min']}..{group['review_no_max']}",
                f"004A review_no list = {group['review_no_list']}",
                f"child names = {group['child_names']}",
                f"reviewed sibling evidence = {group['reviewed_sibling_evidence'] or 'EMPTY'}",
                "```",
                "",
            ]
        )
    text = "\n".join(lines).rstrip() + "\n"
    for phrase in FORBIDDEN_SUMMARY:
        if phrase in text:
            raise ValueError(f"forbidden summary phrase: {phrase}")
    return text


def write_review005a() -> dict:
    source = assert_frozen_004a()
    pack = build_compact_pack(source)
    write_tsv(pack, PACK_004A_PATH, COMPACT_FIELDS)
    groups = parent_groups(pack)
    GROUPS_004A_PATH.write_text(render_parent_groups(groups), encoding="utf-8")
    return {
        "rows": pack,
        "sha": compact_pack_sha(pack),
        "groups": groups,
        "input_sha": FROZEN_004A_SHA,
        "parent_groups": len(groups),
    }


def main() -> None:
    out = write_review005a()
    print(
        json.dumps(
            {
                "WO": "WO-RISK-04-REVIEW-005A",
                "004A_INPUT_SHA": out["input_sha"],
                "COMPACT_SHA": out["sha"],
                "rows": len(out["rows"]),
                "parent_groups": out["parent_groups"],
                "GPT_PENDING": 200,
                "CANONICAL_UUID_CREATED": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
