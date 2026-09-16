"""LEAF Batch004C compact GPT adjudication pack. Cursor does not decide semantic kind."""
from __future__ import annotations

import json
from pathlib import Path

from tools.risk04.review004_leaf_routing import LEAF_FIELDS, load_leaf_batch
from tools.risk04.review005a_pack import COMPACT_FIELDS, compact_pack_sha, parent_groups
from tools.risk04.review_decisions import write_tsv
from tools.risk04.seed_review import universe_sha

FROZEN_004C_SHA = "665a3c376c218315d4adceb32ff3d5a81da72af90eda76442d823fd6ac8e1f72"
INPUT_004C_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004C_REVIEW_INPUT.tsv")
PACK_004C_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004C_GPT_REVIEW_PACK.tsv")
GROUPS_004C_PATH = Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004C_PARENT_GROUPS.md")

FORBIDDEN_SUMMARY = (
    "이 family는 PROCESS",
    "이 child는 TASK",
    "canonical 후보",
    "merge 가능",
    "동일 개념",
    "자동분류 가능",
)


def assert_frozen_004c() -> list[dict]:
    rows = load_leaf_batch(INPUT_004C_PATH)
    digest = universe_sha(rows, *LEAF_FIELDS)
    if digest != FROZEN_004C_SHA:
        raise ValueError("frozen 004C input SHA mismatch")
    if len(rows) != 200:
        raise ValueError(f"004C rows {len(rows)}")
    if [int(row["review_no"]) for row in rows] != list(range(1092, 1292)):
        raise ValueError("004C review_no drift")
    if any(row["gpt_semantic_kind"] != "PENDING" for row in rows):
        raise ValueError("004C input already has GPT kind")
    return rows


def build_compact_pack_004c(rows: list[dict] | None = None) -> list[dict]:
    rows = rows if rows is not None else assert_frozen_004c()
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
    for field in ("review_no", "seed_proposal_key", "source_key", "name", "source_path"):
        if [row[field] for row in pack] != [row[field] for row in rows]:
            raise ValueError(f"compact {field} drift")
    if [int(row["review_no"]) for row in pack] != list(range(1092, 1292)):
        raise ValueError("compact review_no range drift")
    if {row["seed_proposal_key"] for row in pack} != {row["seed_proposal_key"] for row in rows}:
        raise ValueError("compact keyset mismatch")
    return pack


def render_parent_groups_004c(groups: list[dict]) -> str:
    lines = [
        "---",
        "class: records",
        "type: report",
        "scope: knowledge",
        "project: risk",
        "title: OBJ-RISK-04 REVIEW-005C LEAF 004C parent groups",
        "version: 1",
        "status: active",
        "owner: taiwang",
        "---",
        "",
        "# LEAF Batch004C parent group evidence",
        "",
        "Source/evidence summary only. Parent kind, family policy, sibling kind, and same-name hits are not leaf decisions.",
        "",
        "```text",
        "004C rows = 200",
        "review_no = 1092..1291",
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
                f"root name = {group['root_name']}",
                f"root source_key = {group['root_source_key']}",
                f"parent name = {group['parent_name']}",
                f"parent source_key = {group['parent_source_key']}",
                f"parent semantic kind = {group['parent_semantic_kind']}",
                f"parent review decision = {group['parent_review_decision']}",
                f"parent family policy = {group['parent_leaf_family_policy']}",
                f"004C child count = {group['child_count']}",
                f"004C review_no list = {group['review_no_list']}",
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


def write_review005c() -> dict:
    source = assert_frozen_004c()
    pack = build_compact_pack_004c(source)
    write_tsv(pack, PACK_004C_PATH, COMPACT_FIELDS)
    groups = parent_groups(pack)
    GROUPS_004C_PATH.write_text(render_parent_groups_004c(groups), encoding="utf-8")
    return {
        "rows": pack,
        "sha": compact_pack_sha(pack),
        "groups": groups,
        "input_sha": FROZEN_004C_SHA,
        "parent_groups": len(groups),
    }


def main() -> None:
    out = write_review005c()
    print(
        json.dumps(
            {
                "WO": "WO-RISK-04-REVIEW-005C",
                "004C_INPUT_SHA": out["input_sha"],
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
