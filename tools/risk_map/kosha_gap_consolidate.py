"""WO-RISK-KOSHA-GAP-CONSOLIDATE-001 KOSHA 196 GAP → consolidation review.

Mechanical grouping / evidence preparation only. Claude produces:
  * a coverage-priority + evidence-aggregated review pack (66 rows)
  * a mechanical family census (grouped by rule-based family hint)
  * the closure artifact for the 4 aggregate consistency exceptions
    (all VALID_CONTEXT_SPLIT per WO §1)

Claude does NOT create canonical UUIDs, does NOT rename or reparent,
does NOT decide new canonical names semantically. GPT is the semantic
consolidation authority; this tool just organizes the evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha
from tools.risk_map.kosha_620_aggregate import (
    FROZEN_CANONICAL_TASK_REFERENCE_SHA,
    _REVIEW_DIR,
    GAP_GROUPS_PATH,
    GAP_PATH,
)
from tools.risk_map.kosha_b01_semantic_evidence import (
    CANONICAL_TASK_REFERENCE_PATH,
    canonical_task_reference_sha,
)

WO_ID = "WO-RISK-KOSHA-GAP-CONSOLIDATE-001"

REVIEW_PACK_PATH = _REVIEW_DIR / "RISK_KOSHA_620_GAP_CONSOLIDATION_REVIEW_PACK_v1.tsv"
FAMILY_CENSUS_PATH = _REVIEW_DIR / "RISK_KOSHA_620_GAP_FAMILY_CENSUS_v1.tsv"
EXCEPTION_RESOLUTION_PATH = _REVIEW_DIR / "RISK_KOSHA_620_SEMANTIC_EXCEPTION_RESOLUTION_v1.tsv"
REPORT_PATH = _REVIEW_DIR / "OBJ_risk-kosha-gap-consolidation_v1.md"

EXPECTED_GAP_GROUPS = 66
EXPECTED_GAP_ROWS = 196
EXPECTED_EXCEPTION_ROWS = 4

# ---------------------------------------------------------------------------
# Mechanical family classifier — ordered first-match rules.
#
# The rules are transparent Korean-token pattern matches on the frozen
# `source_name_normalized` field. This is NOT semantic inference: it is a
# review aid so the human reviewer sees clusters. GPT is the authority for
# any actual family name / consolidation decision.
# ---------------------------------------------------------------------------

_FAMILY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # tunnel-support first (must precede generic TUNNEL_WORK)
    (
        "TUNNEL_SUPPORT_FAMILY",
        ("터널 강지보", "터널 락볼트", "터널 숏크리트", "터널 방수", "터널배수",
         "터널 특수보강", "터널 지보", "터널 라이닝"),
    ),
    ("TUNNEL_WORK_FAMILY", ("터널 ", "특수터널", "갱구", "라이닝거푸집")),
    ("BLASTING_FAMILY", ("발파",)),
    ("PILE_FAMILY", ("파일", "항타")),
    ("FORMWORK_FAMILY", ("갱폼", "거푸집", "슬립폼", "슬라이딩 폼", "슬립 폼")),
    ("MOBILIZATION_DELIVERY_FAMILY", ("반입", "자재반입", "장비반입")),
    ("REMOVAL_HAULOUT_FAMILY", ("반출", "토사반출")),
    ("GROUTING_FAMILY", ("그라우팅",)),
    ("REBAR_FAMILY", ("철근",)),
    ("CONCRETE_FAMILY", ("콘크리트",)),
    ("BACKFILL_COMPACT_FAMILY", ("되메움", "다짐")),
    ("UTILITY_PROTECTION_FAMILY", ("지장물", "접지")),
    ("PLASTER_FINISHING_FAMILY", ("미장", "견출")),
    ("LANDSCAPE_FAMILY", ("조경",)),
    ("ELECTRICAL_FAMILY", ("전기",)),
    ("EXCAVATION_FAMILY", ("굴착",)),
    ("PAVING_FAMILY", ("포장",)),
)


def _family_hint(label: str) -> str:
    for family, needles in _FAMILY_RULES:
        for needle in needles:
            if needle in label:
                return family
    return "UNCLASSIFIED"


def _coverage_priority(project_kind_count: int) -> str:
    if project_kind_count == 6:
        return "P1"
    if project_kind_count >= 3:
        return "P2"
    if project_kind_count == 2:
        return "P3"
    return "P4"


# ---------------------------------------------------------------------------
# Evidence candidate aggregation — pull the per-source-row mechanical
# candidates from the frozen B01-B07 evidence TSVs for every review_key in a
# GAP group. Union deduped by canonical_id.
# ---------------------------------------------------------------------------

_EVIDENCE_FILES = (
    "RISK_KOSHA_B01_SEMANTIC_EVIDENCE_v1.tsv",
    "RISK_KOSHA_B02_SEMANTIC_EVIDENCE_v1.tsv",
    "RISK_KOSHA_B03_SEMANTIC_EVIDENCE_v1.tsv",
    "RISK_KOSHA_B04_SEMANTIC_EVIDENCE_v1.tsv",
    "RISK_KOSHA_B05_SEMANTIC_EVIDENCE_v1.tsv",
    "RISK_KOSHA_B06_SEMANTIC_EVIDENCE_v1.tsv",
    "RISK_KOSHA_B07_SEMANTIC_EVIDENCE_v1.tsv",
)


def _load_all_evidence() -> dict[str, dict]:
    by_review: dict[str, dict] = {}
    for fname in _EVIDENCE_FILES:
        for r in load_tsv(_REVIEW_DIR / fname):
            by_review[r["review_key"]] = r
    if len(by_review) != 620:
        raise SystemExit(f"EVIDENCE_UNION_ROW_DRIFT {len(by_review)}")
    return by_review


def _candidates_for_review_keys(
    review_keys: list[str], evidence: dict[str, dict]
) -> tuple[int, str, str]:
    seen_ids: set[str] = set()
    seen_names: list[str] = []
    for rk in review_keys:
        ev = evidence.get(rk)
        if ev is None:
            raise SystemExit(f"EVIDENCE_ROW_MISSING {rk}")
        for i in range(1, 11):
            cid = ev.get(f"candidate_{i}_canonical_id", "") or ""
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                seen_names.append(ev.get(f"candidate_{i}_name", "") or "")
    return len(seen_ids), "|".join(sorted(seen_ids)), "|".join(sorted(seen_names))


# ---------------------------------------------------------------------------
# Review pack + family census
# ---------------------------------------------------------------------------

REVIEW_PACK_FIELDS: tuple[str, ...] = (
    "gap_group_id",
    "source_name_normalized",
    "work_type",
    "occurrence_rows",
    "project_kind_count",
    "project_kinds",
    "coverage_priority",
    "family_hint",
    "existing_candidate_count",
    "existing_candidate_ids",
    "existing_candidate_names",
    "review_keys",
    "source_keys",
    "gpt_consolidation_decision",
    "gpt_candidate_name",
    "gpt_candidate_parent",
    "gpt_reason",
)

FAMILY_CENSUS_FIELDS: tuple[str, ...] = (
    "family_hint",
    "group_count",
    "represented_source_rows",
    "project_kind_union",
)

EXCEPTION_RESOLUTION_FIELDS: tuple[str, ...] = (
    "group_id",
    "source_name_normalized",
    "work_type",
    "resolution",
    "general_context_target_id",
    "general_context_target_name",
    "tunnel_context_target_id",
    "tunnel_context_target_name",
    "row_count",
    "review_keys",
    "source_keys",
)


def build_review_pack() -> list[dict]:
    gap_groups = load_tsv(GAP_GROUPS_PATH)
    if len(gap_groups) != EXPECTED_GAP_GROUPS:
        raise SystemExit(f"GAP_GROUP_ROW_DRIFT {len(gap_groups)}")
    if sum(int(r["occurrence_rows"]) for r in gap_groups) != EXPECTED_GAP_ROWS:
        raise SystemExit("GAP_GROUP_OCCURRENCE_SUM_DRIFT")

    # Validate canonical reference SHA hasn't drifted (WO §12 target integrity
    # relied on this — we don't consume the reference here beyond the SHA
    # check, but if it drifts every downstream decision would need re-review).
    ref = load_tsv(CANONICAL_TASK_REFERENCE_PATH)
    if canonical_task_reference_sha(ref) != FROZEN_CANONICAL_TASK_REFERENCE_SHA:
        raise SystemExit("CANONICAL_TASK_REFERENCE_SHA_DRIFT")

    evidence = _load_all_evidence()

    out: list[dict] = []
    for g in gap_groups:
        review_keys = g["review_keys"].split("|") if g["review_keys"] else []
        project_kinds = g["project_kinds"].split("|") if g["project_kinds"] else []
        pk_count = len(project_kinds)
        cand_count, cand_ids, cand_names = _candidates_for_review_keys(
            review_keys, evidence
        )
        out.append(
            {
                "gap_group_id": g["gap_group_id"],
                "source_name_normalized": g["source_name_normalized"],
                "work_type": g["work_type"],
                "occurrence_rows": g["occurrence_rows"],
                "project_kind_count": str(pk_count),
                "project_kinds": g["project_kinds"],
                "coverage_priority": _coverage_priority(pk_count),
                "family_hint": _family_hint(g["source_name_normalized"]),
                "existing_candidate_count": str(cand_count),
                "existing_candidate_ids": cand_ids,
                "existing_candidate_names": cand_names,
                "review_keys": g["review_keys"],
                "source_keys": g["source_keys"],
                "gpt_consolidation_decision": "",
                "gpt_candidate_name": "",
                "gpt_candidate_parent": "",
                "gpt_reason": "",
            }
        )

    # Sort by (coverage_priority, family_hint, source_name_normalized) so
    # highest-coverage groups come first — a review-ergonomic ordering.
    priority_rank = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    out.sort(
        key=lambda r: (
            priority_rank[r["coverage_priority"]],
            r["family_hint"],
            r["source_name_normalized"],
        )
    )
    _assert_review_pack_shape(out)
    return out


def _assert_review_pack_shape(rows: list[dict]) -> None:
    if len(rows) != EXPECTED_GAP_GROUPS:
        raise SystemExit(f"REVIEW_PACK_ROW_DRIFT {len(rows)}")
    if sum(int(r["occurrence_rows"]) for r in rows) != EXPECTED_GAP_ROWS:
        raise SystemExit("REVIEW_PACK_OCCURRENCE_SUM_DRIFT")
    for r in rows:
        if r["gpt_consolidation_decision"]:
            raise SystemExit(f"REVIEW_PACK_PREMATURE_DECISION {r['gap_group_id']}")
        if r["gpt_candidate_name"] or r["gpt_candidate_parent"] or r["gpt_reason"]:
            raise SystemExit(f"REVIEW_PACK_PREMATURE_FIELDS {r['gap_group_id']}")
        pk = int(r["project_kind_count"])
        if pk < 1 or pk > 6:
            raise SystemExit(f"REVIEW_PACK_PK_COUNT_OUT_OF_RANGE {r['gap_group_id']}")
    priorities = Counter(r["coverage_priority"] for r in rows)
    if sum(priorities.values()) != EXPECTED_GAP_GROUPS:
        raise SystemExit("REVIEW_PACK_PRIORITY_SUM_DRIFT")


def build_family_census(review_pack: list[dict]) -> list[dict]:
    by_family: dict[str, list[dict]] = defaultdict(list)
    for r in review_pack:
        by_family[r["family_hint"]].append(r)
    out: list[dict] = []
    for family, grp in by_family.items():
        pk_union: set[str] = set()
        for r in grp:
            pk_union.update(r["project_kinds"].split("|") if r["project_kinds"] else [])
        out.append(
            {
                "family_hint": family,
                "group_count": str(len(grp)),
                "represented_source_rows": str(
                    sum(int(r["occurrence_rows"]) for r in grp)
                ),
                "project_kind_union": "|".join(sorted(pk_union)),
            }
        )
    # Sort descending by group_count then by name for stability.
    out.sort(key=lambda r: (-int(r["group_count"]), r["family_hint"]))
    total_groups = sum(int(r["group_count"]) for r in out)
    total_rows = sum(int(r["represented_source_rows"]) for r in out)
    if total_groups != EXPECTED_GAP_GROUPS:
        raise SystemExit(f"FAMILY_CENSUS_GROUP_SUM_DRIFT {total_groups}")
    if total_rows != EXPECTED_GAP_ROWS:
        raise SystemExit(f"FAMILY_CENSUS_ROW_SUM_DRIFT {total_rows}")
    return out


# ---------------------------------------------------------------------------
# Aggregate consistency exception closure — WO §1
# ---------------------------------------------------------------------------

_CONSISTENCY_PATH = _REVIEW_DIR / "RISK_KOSHA_620_SEMANTIC_CONSISTENCY_EXCEPTIONS_v1.tsv"

_TARGET_BLASTING_GENERAL = ("bae014b7-2474-48f7-b5c0-0e9f30a0ff56", "발파")
_TARGET_BLASTING_TUNNEL = ("473d69ee-4433-487f-bc43-c35c1f2ea28f", "발파굴착")


def build_exception_resolution() -> list[dict]:
    exceptions = load_tsv(_CONSISTENCY_PATH)
    if len(exceptions) != EXPECTED_EXCEPTION_ROWS:
        raise SystemExit(f"CONSISTENCY_EXCEPTION_DRIFT {len(exceptions)}")
    expected_ids = {"CE-0066", "CE-0067", "CE-0068", "CE-0069"}
    if {r["group_id"] for r in exceptions} != expected_ids:
        raise SystemExit("CONSISTENCY_EXCEPTION_GROUP_IDS_DRIFT")
    out: list[dict] = []
    for r in exceptions:
        # Every exception must be in 발파작업 and TARGET_CONFLICT only.
        if r["work_type"] != "발파작업":
            raise SystemExit(f"EXCEPTION_UNEXPECTED_WORKTYPE {r['group_id']}")
        if r["distinct_decisions"] != "MAP_EXISTING_CANONICAL":
            raise SystemExit(f"EXCEPTION_UNEXPECTED_DECISION {r['group_id']}")
        targets = set(r["distinct_target_ids"].split("|"))
        if targets != {
            _TARGET_BLASTING_GENERAL[0],
            _TARGET_BLASTING_TUNNEL[0],
        }:
            raise SystemExit(f"EXCEPTION_UNEXPECTED_TARGET_SET {r['group_id']}")
        out.append(
            {
                "group_id": r["group_id"],
                "source_name_normalized": r["source_name_normalized"],
                "work_type": r["work_type"],
                "resolution": "VALID_CONTEXT_SPLIT",
                "general_context_target_id": _TARGET_BLASTING_GENERAL[0],
                "general_context_target_name": _TARGET_BLASTING_GENERAL[1],
                "tunnel_context_target_id": _TARGET_BLASTING_TUNNEL[0],
                "tunnel_context_target_name": _TARGET_BLASTING_TUNNEL[1],
                "row_count": r["row_count"],
                "review_keys": r["review_keys"],
                "source_keys": r["source_keys"],
            }
        )
    out.sort(key=lambda r: r["group_id"])
    return out


# ---------------------------------------------------------------------------
# SHAs
# ---------------------------------------------------------------------------


def review_pack_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *REVIEW_PACK_FIELDS)


def family_census_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *FAMILY_CENSUS_FIELDS)


def exception_resolution_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *EXCEPTION_RESOLUTION_FIELDS)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def render_report(
    review_pack: list[dict],
    family_census: list[dict],
    exception_resolution: list[dict],
    shas: dict[str, str],
) -> str:
    priorities = Counter(r["coverage_priority"] for r in review_pack)
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-GAP-CONSOLIDATE-001 KOSHA canonical gap consolidation
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KOSHA 196 GAP → Canonical Candidate Consolidation

## THIS IS EVIDENCE PREPARATION ONLY

```text
THIS IS NOT CANONICAL CREATION
THIS IS NOT OWNER APPROVAL
THIS IS NOT PRODUCTION MATERIALIZATION
THIS DOES NOT LIFT KOSHA IDENTITY HOLD
FAMILY HINTS ARE REVIEW AIDS, NOT CANONICAL NAMES
```

Claude did not decide any consolidation semantically. The 66 review-pack
rows have blank GPT consolidation fields. GPT decides which of the 66
gap groups actually need new canonicals, which fold into existing
canonicals, and which fold into shared new parents.

## Aggregate consistency exceptions — CLOSED

```text
CE-0066 발파 암처리       = VALID_CONTEXT_SPLIT
CE-0067 발파 장약         = VALID_CONTEXT_SPLIT
CE-0068 발파 천공         = VALID_CONTEXT_SPLIT
CE-0069 발파 화약고 관리   = VALID_CONTEXT_SPLIT

general context target   = bae014b7 발파
tunnel context target    = 473d69ee 발파굴착

UNRESOLVED SEMANTIC CONFLICT = 0
```

Existing B01-B07 review rows are not rewritten.

## GAP consolidation

```text
SOURCE GAP ROWS                     = 196
SOURCE GAP GROUPS                   = {len(review_pack)}

Coverage priority breakdown:
  P1  (present in all 6 project kinds)   = {priorities.get("P1", 0)}
  P2  (present in 3-5 project kinds)     = {priorities.get("P2", 0)}
  P3  (present in 2 project kinds)       = {priorities.get("P3", 0)}
  P4  (present in exactly 1 project kind) = {priorities.get("P4", 0)}

MECHANICAL FAMILY GROUPS (hint clusters) = {len(family_census)}
```

Family cluster census (mechanical, ordered by group count):

```text
family_hint                              group_count   source_rows
""" + "\n".join(
        f'{r["family_hint"]:<40} {r["group_count"]:>10}   {r["represented_source_rows"]:>10}'
        for r in family_census
    ) + f"""
```

## Frozen output SHAs

```text
RISK KOSHA 620 GAP CONSOLIDATION REVIEW PACK SHA = {shas["review_pack"]}
RISK KOSHA 620 GAP FAMILY CENSUS SHA             = {shas["family_census"]}
RISK KOSHA 620 SEMANTIC EXCEPTION RESOLUTION SHA = {shas["exception_resolution"]}
```

## Verdict

```text
{WO_ID} = EVIDENCE_READY / GPT_CONSOLIDATION_REVIEW_READY
KOSHA REVIEWED = 620 / 620
SEMANTIC EXCEPTIONS = 0 unresolved
CANONICAL GAP ROWS = 196
CANONICAL GAP SOURCE GROUPS = {len(review_pack)}
CANONICAL CREATE = 0
KOSHA PRODUCTION MAPPING = 0
OWNER APPROVAL = NOT OPENED
MERGE = NOT AUTHORIZED
NEXT = GPT CANONICAL GAP CONSOLIDATION REVIEW
STOP
```
"""


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


def write_all() -> dict:
    review_pack_a = build_review_pack()
    review_pack_b = build_review_pack()
    if review_pack_a != review_pack_b:
        raise SystemExit("REVIEW_PACK_ROW_ORDER_DRIFT")
    sha_a = review_pack_sha(review_pack_a)
    sha_b = review_pack_sha(review_pack_b)
    if sha_a != sha_b:
        raise SystemExit(f"REVIEW_PACK_SHA_DRIFT {sha_a} vs {sha_b}")

    family_census = build_family_census(review_pack_a)
    exception_resolution = build_exception_resolution()

    shas = {
        "review_pack": sha_a,
        "family_census": family_census_sha(family_census),
        "exception_resolution": exception_resolution_sha(exception_resolution),
    }

    write_tsv(review_pack_a, REVIEW_PACK_PATH, REVIEW_PACK_FIELDS)
    write_tsv(family_census, FAMILY_CENSUS_PATH, FAMILY_CENSUS_FIELDS)
    write_tsv(exception_resolution, EXCEPTION_RESOLUTION_PATH, EXCEPTION_RESOLUTION_FIELDS)
    REPORT_PATH.write_text(
        render_report(review_pack_a, family_census, exception_resolution, shas),
        encoding="utf-8",
    )

    priorities = Counter(r["coverage_priority"] for r in review_pack_a)
    return {
        "gap_groups": len(review_pack_a),
        "gap_source_rows": EXPECTED_GAP_ROWS,
        "p1": priorities.get("P1", 0),
        "p2": priorities.get("P2", 0),
        "p3": priorities.get("P3", 0),
        "p4": priorities.get("P4", 0),
        "mechanical_family_groups": len(family_census),
        "exception_resolutions": len(exception_resolution),
        "unresolved_exceptions": 0,
        "review_pack_sha_run1": sha_a,
        "review_pack_sha_run2": sha_b,
        "shas": shas,
        "review_pack_path": str(REVIEW_PACK_PATH),
        "family_census_path": str(FAMILY_CENSUS_PATH),
        "exception_resolution_path": str(EXCEPTION_RESOLUTION_PATH),
        "report_path": str(REPORT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} evidence generator")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
