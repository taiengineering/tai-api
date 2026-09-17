"""WO-RISK-KALIS-SEMANTIC-FREEZE-001 KALIS 40-family semantic freeze.

Transcription-only. GPT decided all 40 family classifications; this tool
does NOT re-decide anything, does NOT create canonicals, does NOT touch
production. It:

  * Verifies frozen R1 inputs (task universe + review universe + summary).
  * Verifies the 40-key GPT_FAMILY_DECISIONS manifest matches the KALIS
    family universe exactly (by task_name_normalized).
  * Expands the family decision to all 761 rows via family_key.
  * Emits family freeze + row freeze + owner-candidate package + report.
  * Semantic decision census (WO §3):
        AMBIGUOUS         = 21
        CANONICAL_GAP     = 14
        POSSIBLE_RELATED  =  3
        NARROWER_THAN     =  1
        NO_MATCH          =  1
        EXACT_EQUIVALENT  =  0

Terminology (locked from KOSHA B07 onward):
  review_key  = review artifact identity
  source_key  = KALIS source-node identity
  family_key  = normalized task-name grouping aid (NOT canonical identity)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha
from tools.risk_map.kalis_map001_review_universe import (
    REVIEW_SUMMARY_PATH,
    REVIEW_UNIVERSE_PATH,
    TASK_UNIVERSE_PATH,
    review_summary_sha,
    review_universe_sha,
)

WO_ID = "WO-RISK-KALIS-SEMANTIC-FREEZE-001"

FROZEN_REVIEW_UNIVERSE_SHA = (
    "50446a5c9fa421f09beb1425ffe8d90649b29e50bafe93f46d8913a085ed497d"
)
FROZEN_REVIEW_SUMMARY_SHA = (
    "96b5dc4403078e33c325e22265b316dc1ba970aef4ee347e2e9143caae2aa8a0"
)
FROZEN_TASK_UNIVERSE_SHA = (
    "6efd9047b4f6c001321c43496f27c21b538556b76fd2b90a6035cc2972db6ad4"
)

EXPECTED_FAMILIES = 40
EXPECTED_ROWS = 761

# ---------------------------------------------------------------------------
# GPT decision manifest — verbatim WO §3 transcription
# ---------------------------------------------------------------------------

_AMBIGUOUS_NAMES: tuple[str, ...] = (
    "설치작업", "마감작업", "이동", "굴착작업", "해체작업", "운반작업",
    "타설작업", "연결작업", "절단작업", "조립작업", "거치작업", "도장작업",
    "정리작업", "천공작업", "확인 및 점검작업", "쌓기작업", "전기작업",
    "준비작업", "설비작업", "청소작업", "측량작업",
)

_CANONICAL_GAP_NAMES: tuple[str, ...] = (
    "양중작업", "인양작업", "고소작업", "부설 및 다짐작업", "적재작업",
    "항타 및 항발작업", "상차 및 하역작업", "매설작업", "보수 및 교체작업",
    "정비작업", "반출작업", "벌목작업", "절취작업", "형틀 및 목공",
)

# (family name, target canonical id, target canonical name)
_POSSIBLE_RELATED: tuple[tuple[str, str, str], ...] = (
    ("용접작업", "bf3841d0-71ea-4464-a7d9-d0dcdc3dfa33", "궤도현장용접"),
    ("양생작업", "3258e587-68ab-40c8-80df-dd4fa0db60b7", "콘크리트양생"),
    ("인발작업", "06e686fc-0062-46af-b4f2-72027b7a4668", "RockBolt축력및인발측정"),
)

_NARROWER_THAN: tuple[tuple[str, str, str], ...] = (
    ("장약 및 발파작업", "473d69ee-4433-487f-bc43-c35c1f2ea28f", "발파굴착"),
)

_NO_MATCH_NAMES: tuple[str, ...] = ("기타",)


_REASON_AMBIGUOUS = (
    "MULTIPLE_CANDIDATE_CANONICALS_OR_CONTEXT_DEPENDENT_MEANING_INSUFFICIENT_"
    "EVIDENCE_FOR_SINGLE_MAPPING"
)
_REASON_CANONICAL_GAP = (
    "INDEPENDENT_KALIS_TASK_CONCEPT_WITHOUT_SUITABLE_EXISTING_CANONICAL_TARGET"
)
_REASON_NO_MATCH = "CATCH_ALL_LABEL_NOT_A_TASK_CONCEPT"

_REASON_POSSIBLE_RELATED: dict[str, str] = {
    "용접작업": "GENERIC_WELDING_IS_BROADER_THAN_CANONICAL_TRACK_ONSITE_WELDING",
    "양생작업": "GENERIC_CURING_MAY_ALIGN_WITH_CONCRETE_CURING_BUT_NOT_STRICTLY_EQUIVALENT",
    "인발작업": "GENERIC_PULL_OUT_MAY_RELATE_TO_ROCKBOLT_AXIAL_FORCE_AND_PULL_TEST_BUT_PURPOSE_DIFFERS",
}
_REASON_NARROWER_THAN: dict[str, str] = {
    "장약 및 발파작업": (
        "EXPLOSIVE_CHARGING_AND_BLASTING_IS_A_SPECIFIC_SUBACTIVITY_OF_"
        "CANONICAL_TUNNEL_BLAST_EXCAVATION"
    ),
}


def _build_family_manifest() -> dict[str, dict[str, str]]:
    manifest: dict[str, dict[str, str]] = {}
    for name in _AMBIGUOUS_NAMES:
        manifest[name] = {
            "semantic_decision": "AMBIGUOUS",
            "mapping_type": "AMBIGUOUS",
            "target_canonical_id": "",
            "target_canonical_name": "",
            "owner_default": "HOLD",
            "production_candidate": "NO",
            "gpt_reason": _REASON_AMBIGUOUS,
        }
    for name in _CANONICAL_GAP_NAMES:
        manifest[name] = {
            "semantic_decision": "CANONICAL_GAP",
            "mapping_type": "",
            "target_canonical_id": "",
            "target_canonical_name": "",
            "owner_default": "HOLD",
            "production_candidate": "NO",
            "gpt_reason": _REASON_CANONICAL_GAP,
        }
    for name, tid, tname in _POSSIBLE_RELATED:
        manifest[name] = {
            "semantic_decision": "POSSIBLE_RELATED",
            "mapping_type": "POSSIBLE_RELATED",
            "target_canonical_id": tid,
            "target_canonical_name": tname,
            "owner_default": "HOLD",
            "production_candidate": "YES_HOLD_ONLY",
            "gpt_reason": _REASON_POSSIBLE_RELATED[name],
        }
    for name, tid, tname in _NARROWER_THAN:
        manifest[name] = {
            "semantic_decision": "NARROWER_THAN",
            "mapping_type": "NARROWER_THAN",
            "target_canonical_id": tid,
            "target_canonical_name": tname,
            "owner_default": "UNDECIDED",
            "production_candidate": "YES",
            "gpt_reason": _REASON_NARROWER_THAN[name],
        }
    for name in _NO_MATCH_NAMES:
        manifest[name] = {
            "semantic_decision": "NO_MATCH",
            "mapping_type": "NO_MATCH",
            "target_canonical_id": "",
            "target_canonical_name": "",
            "owner_default": "REJECT",
            "production_candidate": "NO",
            "gpt_reason": _REASON_NO_MATCH,
        }
    return manifest


GPT_FAMILY_DECISIONS: dict[str, dict[str, str]] = _build_family_manifest()


def _assert_manifest_shape() -> None:
    counts = {
        "AMBIGUOUS": len(_AMBIGUOUS_NAMES),
        "CANONICAL_GAP": len(_CANONICAL_GAP_NAMES),
        "POSSIBLE_RELATED": len(_POSSIBLE_RELATED),
        "NARROWER_THAN": len(_NARROWER_THAN),
        "NO_MATCH": len(_NO_MATCH_NAMES),
    }
    total = sum(counts.values())
    if total != EXPECTED_FAMILIES:
        raise SystemExit(f"MANIFEST_TOTAL_DRIFT {total} {counts}")
    if len(GPT_FAMILY_DECISIONS) != EXPECTED_FAMILIES:
        raise SystemExit(
            f"MANIFEST_KEY_DUPLICATE {len(GPT_FAMILY_DECISIONS)} vs {total}"
        )
    if counts != {
        "AMBIGUOUS": 21,
        "CANONICAL_GAP": 14,
        "POSSIBLE_RELATED": 3,
        "NARROWER_THAN": 1,
        "NO_MATCH": 1,
    }:
        raise SystemExit(f"MANIFEST_GROUP_COUNT_DRIFT {counts}")


_assert_manifest_shape()

# ---------------------------------------------------------------------------
# Paths & fields
# ---------------------------------------------------------------------------

_ROOT = Path("docs/knowledge/risk")

FAMILY_FREEZE_PATH = _ROOT / "RISK_KALIS_SEMANTIC_FAMILY_FREEZE_v1.tsv"
ROW_FREEZE_PATH = _ROOT / "RISK_KALIS_SEMANTIC_ROW_FREEZE_v1.tsv"
OWNER_CANDIDATE_PATH = _ROOT / "RISK_KALIS_OWNER_MAPPING_CANDIDATES_v1.tsv"
REPORT_PATH = _ROOT / "OBJ_risk-kalis-semantic-freeze_v1.md"


FAMILY_FREEZE_FIELDS: tuple[str, ...] = (
    "family_key",
    "task_name",
    "task_name_normalized",
    "occurrence_count",
    "semantic_decision",
    "mapping_type",
    "target_canonical_id",
    "target_canonical_name",
    "owner_default",
    "production_candidate",
    "gpt_reason",
)


ROW_FREEZE_FIELDS: tuple[str, ...] = (
    "review_key",
    "source_key",
    "family_key",
    "work_big",
    "work_mid",
    "name_raw",
    "name_normalized",
    "path_raw",
    "semantic_decision",
    "mapping_type",
    "target_canonical_id",
    "target_canonical_name",
    "owner_default",
    "production_candidate",
)


OWNER_CANDIDATE_FIELDS: tuple[str, ...] = ROW_FREEZE_FIELDS + (
    "owner_decision",
    "owner_reason",
)


# ---------------------------------------------------------------------------
# Anchor verification
# ---------------------------------------------------------------------------


def _verify_anchors() -> tuple[list[dict], list[dict]]:
    universe = load_tsv(REVIEW_UNIVERSE_PATH)
    if len(universe) != EXPECTED_ROWS:
        raise SystemExit(f"REVIEW_UNIVERSE_ROW_DRIFT {len(universe)}")
    if review_universe_sha(universe) != FROZEN_REVIEW_UNIVERSE_SHA:
        raise SystemExit("REVIEW_UNIVERSE_SHA_DRIFT")

    summary = load_tsv(REVIEW_SUMMARY_PATH)
    if len(summary) != EXPECTED_FAMILIES:
        raise SystemExit(f"REVIEW_SUMMARY_ROW_DRIFT {len(summary)}")
    if review_summary_sha(summary) != FROZEN_REVIEW_SUMMARY_SHA:
        raise SystemExit("REVIEW_SUMMARY_SHA_DRIFT")

    task_universe = load_tsv(TASK_UNIVERSE_PATH)
    from tools.risk_map.kalis_map001_review_universe import TASK_UNIVERSE_FIELDS
    if universe_sha(task_universe, *TASK_UNIVERSE_FIELDS) != FROZEN_TASK_UNIVERSE_SHA:
        raise SystemExit("TASK_UNIVERSE_SHA_DRIFT")

    # Manifest ↔ summary set equality.
    summary_names = {r["task_name_normalized"] for r in summary}
    manifest_names = set(GPT_FAMILY_DECISIONS)
    missing = summary_names - manifest_names
    unexpected = manifest_names - summary_names
    if missing or unexpected:
        raise SystemExit(
            f"MANIFEST_FAMILY_SET_DRIFT missing={sorted(missing)} unexpected={sorted(unexpected)}"
        )
    return universe, summary


# ---------------------------------------------------------------------------
# Build family + row freeze
# ---------------------------------------------------------------------------


def build_family_freeze() -> list[dict]:
    _universe, summary = _verify_anchors()
    out: list[dict] = []
    for s in summary:
        name = s["task_name_normalized"]
        decision = GPT_FAMILY_DECISIONS[name]
        out.append(
            {
                "family_key": s["family_key"],
                "task_name": s["task_name"],
                "task_name_normalized": name,
                "occurrence_count": s["occurrence_count"],
                "semantic_decision": decision["semantic_decision"],
                "mapping_type": decision["mapping_type"],
                "target_canonical_id": decision["target_canonical_id"],
                "target_canonical_name": decision["target_canonical_name"],
                "owner_default": decision["owner_default"],
                "production_candidate": decision["production_candidate"],
                "gpt_reason": decision["gpt_reason"],
            }
        )
    out.sort(key=lambda r: r["family_key"])
    _assert_family_freeze_shape(out)
    return out


def _assert_family_freeze_shape(rows: list[dict]) -> None:
    if len(rows) != EXPECTED_FAMILIES:
        raise SystemExit(f"FAMILY_FREEZE_ROW_DRIFT {len(rows)}")
    if len({r["family_key"] for r in rows}) != EXPECTED_FAMILIES:
        raise SystemExit("FAMILY_FREEZE_KEY_NOT_UNIQUE")
    if sum(int(r["occurrence_count"]) for r in rows) != EXPECTED_ROWS:
        raise SystemExit("FAMILY_FREEZE_OCCURRENCE_SUM_DRIFT")
    census = Counter(r["semantic_decision"] for r in rows)
    expected = {
        "AMBIGUOUS": 21,
        "CANONICAL_GAP": 14,
        "POSSIBLE_RELATED": 3,
        "NARROWER_THAN": 1,
        "NO_MATCH": 1,
    }
    if dict(census) != expected:
        raise SystemExit(f"FAMILY_FREEZE_CENSUS_DRIFT {dict(census)}")
    # EXACT_EQUIVALENT must not appear.
    if any(r["semantic_decision"] == "EXACT_EQUIVALENT" for r in rows):
        raise SystemExit("FAMILY_FREEZE_UNEXPECTED_EXACT")
    for r in rows:
        d = r["semantic_decision"]
        if d in {"POSSIBLE_RELATED", "NARROWER_THAN"}:
            if not r["target_canonical_id"]:
                raise SystemExit(f"FAMILY_TARGET_BLANK {r['task_name_normalized']}")
            if not r["target_canonical_name"]:
                raise SystemExit(f"FAMILY_TARGET_NAME_BLANK {r['task_name_normalized']}")
        else:
            if r["target_canonical_id"] or r["target_canonical_name"]:
                raise SystemExit(f"NON_MAPPING_TARGET_NONBLANK {r['task_name_normalized']}")


def build_row_freeze() -> list[dict]:
    universe, _summary = _verify_anchors()
    family_by_key = {r["family_key"]: r for r in build_family_freeze()}
    out: list[dict] = []
    for u in universe:
        fam = family_by_key.get(u["family_key"])
        if fam is None:
            raise SystemExit(f"ROW_FAMILY_MISSING {u['review_key']}")
        out.append(
            {
                "review_key": u["review_key"],
                "source_key": u["source_key"],
                "family_key": u["family_key"],
                "work_big": u["work_big"],
                "work_mid": u["work_mid"],
                "name_raw": u["name_raw"],
                "name_normalized": u["name_normalized"],
                "path_raw": u["path_raw"],
                "semantic_decision": fam["semantic_decision"],
                "mapping_type": fam["mapping_type"],
                "target_canonical_id": fam["target_canonical_id"],
                "target_canonical_name": fam["target_canonical_name"],
                "owner_default": fam["owner_default"],
                "production_candidate": fam["production_candidate"],
            }
        )
    out.sort(key=lambda r: r["review_key"])
    _assert_row_freeze_shape(out)
    return out


def _assert_row_freeze_shape(rows: list[dict]) -> None:
    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"ROW_FREEZE_ROW_DRIFT {len(rows)}")
    if len({r["review_key"] for r in rows}) != EXPECTED_ROWS:
        raise SystemExit("ROW_FREEZE_REVIEW_KEY_NOT_UNIQUE")
    if len({r["source_key"] for r in rows}) != EXPECTED_ROWS:
        raise SystemExit("ROW_FREEZE_SOURCE_KEY_NOT_UNIQUE")
    # No Owner column should exist here (Owner column lives on the candidate pack).
    if "owner_decision" in rows[0]:
        raise SystemExit("ROW_FREEZE_HAS_OWNER_COLUMN")
    for r in rows:
        d = r["semantic_decision"]
        if d in {"POSSIBLE_RELATED", "NARROWER_THAN"}:
            if not r["target_canonical_id"]:
                raise SystemExit(f"ROW_MAPPING_TARGET_BLANK {r['review_key']}")
        else:
            if r["target_canonical_id"] or r["target_canonical_name"]:
                raise SystemExit(f"ROW_NONMAPPING_TARGET_NONBLANK {r['review_key']}")


def build_owner_candidates() -> list[dict]:
    row_freeze = build_row_freeze()
    include = {"POSSIBLE_RELATED", "NARROWER_THAN"}
    out: list[dict] = []
    for r in row_freeze:
        if r["semantic_decision"] not in include:
            continue
        out.append(
            {
                **r,
                "owner_decision": "",
                "owner_reason": "",
            }
        )
    out.sort(key=lambda r: r["review_key"])
    # Sanity: 4 families' occurrence sum.
    fam_freeze = build_family_freeze()
    cand_family_occ = sum(
        int(f["occurrence_count"])
        for f in fam_freeze
        if f["semantic_decision"] in include
    )
    if len(out) != cand_family_occ:
        raise SystemExit(
            f"OWNER_CANDIDATE_ROW_SUM_DRIFT rows={len(out)} family_occ={cand_family_occ}"
        )
    for r in out:
        if r["owner_decision"] or r["owner_reason"]:
            raise SystemExit(f"OWNER_DECISION_PREMATURE {r['review_key']}")
    return out


# ---------------------------------------------------------------------------
# SHAs
# ---------------------------------------------------------------------------


def family_freeze_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *FAMILY_FREEZE_FIELDS)


def row_freeze_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *ROW_FREEZE_FIELDS)


def owner_candidate_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *OWNER_CANDIDATE_FIELDS)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def render_report(
    family: list[dict],
    rows: list[dict],
    owner_pack: list[dict],
    shas: dict[str, str],
) -> str:
    census = Counter(r["semantic_decision"] for r in family)
    cand_family_count = sum(
        1 for f in family if f["semantic_decision"] in {"POSSIBLE_RELATED", "NARROWER_THAN"}
    )
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KALIS-SEMANTIC-FREEZE-001 KALIS 40-family semantic freeze
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KALIS Semantic Freeze (40 families / 761 rows)

## THIS IS GPT SEMANTIC REVIEW FREEZE

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT PRODUCTION MAPPING
THIS DOES NOT CREATE OR MUTATE CANONICALS
THIS DOES NOT LIFT KALIS IDENTITY HOLD
FAMILY IS REVIEW COMPRESSION AID
FAMILY IS NOT CANONICAL IDENTITY
```

Claude Code performed no semantic inference. The GPT reviewer supplied
40 family decisions; this tool echoes them into the family freeze and
deterministically expands them to all 761 KALIS TASK rows via family_key.

## Anchors (frozen)

```text
review universe SHA   = {FROZEN_REVIEW_UNIVERSE_SHA}
review summary SHA    = {FROZEN_REVIEW_SUMMARY_SHA}
task universe SHA     = {FROZEN_TASK_UNIVERSE_SHA}
```

## Family census

```text
AMBIGUOUS          = {census.get("AMBIGUOUS", 0)}
CANONICAL_GAP      = {census.get("CANONICAL_GAP", 0)}
POSSIBLE_RELATED   = {census.get("POSSIBLE_RELATED", 0)}
NARROWER_THAN      = {census.get("NARROWER_THAN", 0)}
NO_MATCH           = {census.get("NO_MATCH", 0)}
EXACT_EQUIVALENT   = 0
TOTAL              = {sum(census.values())}
```

Occurrence expansion:

```text
family rows                    = {len(family)}
row freeze rows                = {len(rows)}
owner candidate families       = {cand_family_count}
owner candidate rows           = {len(owner_pack)}
```

Owner candidate detail (per family):

```text
{chr(10).join(
    f'  {f["task_name_normalized"]:<16}  decision={f["semantic_decision"]:<16}  '
    f'occ={f["occurrence_count"]:>3}  target={f["target_canonical_name"]}'
    for f in family
    if f["semantic_decision"] in {"POSSIBLE_RELATED", "NARROWER_THAN"}
)}
```

## Frozen output SHAs

```text
KALIS SEMANTIC FAMILY FREEZE SHA   = {shas["family"]}
KALIS SEMANTIC ROW FREEZE SHA      = {shas["row"]}
KALIS OWNER MAPPING CANDIDATES SHA = {shas["owner"]}
```

## Frozen evidence reused (not reverified)

```text
PR #362 / #363 / #364 / #366 / #374 = MERGED
KOSHA MAPPING = 46 APPROVED (in production)
CIC_W MAPPING = 1139 APPROVED (in production)
KALIS PRODUCTION MAPPING = 0
```

## Verdict

```text
{WO_ID} = PASS / OWNER_REVIEW_READY
FAMILIES = 40 / 40
ROW EXPANSION = 761 / 761
OWNER APPROVAL = NOT OPENED
KALIS PRODUCTION MAPPING = 0
CANONICAL MUTATION = 0
MAPPING WRITE = 0
MERGE = NOT AUTHORIZED
NEXT = GPT DELTA-ONLY VERIFY → OWNER APPROVAL
STOP
```
"""


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------


def write_all() -> dict:
    family_a = build_family_freeze()
    family_b = build_family_freeze()
    if family_a != family_b:
        raise SystemExit("FAMILY_FREEZE_ROW_ORDER_DRIFT")
    sha_f_a = family_freeze_sha(family_a)
    sha_f_b = family_freeze_sha(family_b)
    if sha_f_a != sha_f_b:
        raise SystemExit(f"FAMILY_FREEZE_SHA_DRIFT {sha_f_a} vs {sha_f_b}")

    row_a = build_row_freeze()
    row_b = build_row_freeze()
    if row_a != row_b:
        raise SystemExit("ROW_FREEZE_ROW_ORDER_DRIFT")
    sha_r_a = row_freeze_sha(row_a)
    sha_r_b = row_freeze_sha(row_b)
    if sha_r_a != sha_r_b:
        raise SystemExit(f"ROW_FREEZE_SHA_DRIFT {sha_r_a} vs {sha_r_b}")

    owner_a = build_owner_candidates()
    owner_b = build_owner_candidates()
    if owner_a != owner_b:
        raise SystemExit("OWNER_CANDIDATE_ROW_ORDER_DRIFT")
    sha_o_a = owner_candidate_sha(owner_a)
    sha_o_b = owner_candidate_sha(owner_b)
    if sha_o_a != sha_o_b:
        raise SystemExit(f"OWNER_CANDIDATE_SHA_DRIFT {sha_o_a} vs {sha_o_b}")

    shas = {"family": sha_f_a, "row": sha_r_a, "owner": sha_o_a}

    write_tsv(family_a, FAMILY_FREEZE_PATH, FAMILY_FREEZE_FIELDS)
    write_tsv(row_a, ROW_FREEZE_PATH, ROW_FREEZE_FIELDS)
    write_tsv(owner_a, OWNER_CANDIDATE_PATH, OWNER_CANDIDATE_FIELDS)
    REPORT_PATH.write_text(render_report(family_a, row_a, owner_a, shas), encoding="utf-8")

    return {
        "family_rows": len(family_a),
        "row_freeze_rows": len(row_a),
        "owner_candidate_families": sum(
            1 for f in family_a
            if f["semantic_decision"] in {"POSSIBLE_RELATED", "NARROWER_THAN"}
        ),
        "owner_candidate_rows": len(owner_a),
        "family_sha_run1": sha_f_a,
        "family_sha_run2": sha_f_b,
        "row_sha_run1": sha_r_a,
        "row_sha_run2": sha_r_b,
        "owner_pack_sha_run1": sha_o_a,
        "owner_pack_sha_run2": sha_o_b,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} semantic freeze")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
