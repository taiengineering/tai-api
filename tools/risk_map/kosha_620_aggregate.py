"""WO-RISK-KOSHA-AGGREGATE-001 KOSHA 620-row semantic aggregate.

Mechanical aggregation of the 7 frozen GPT semantic review TSVs into a
single 620-row SoT plus mechanical statistics. Claude does NOT re-decide
any semantic outcome. No LLM, no fuzzy, no embedding, no synonym
expansion, no production DB write, no canonical creation.

Outputs (all under docs/knowledge/risk/):
  * RISK_KOSHA_620_GPT_SEMANTIC_AGGREGATE_v1.tsv             620 rows
  * RISK_KOSHA_620_MAPPING_CANDIDATES_v1.tsv                  75 rows
  * RISK_KOSHA_620_AMBIGUOUS_v1.tsv                           78 rows
  * RISK_KOSHA_620_CANONICAL_GAP_v1.tsv                      196 rows
  * RISK_KOSHA_620_NO_MATCH_v1.tsv                           271 rows
  * RISK_KOSHA_620_SEMANTIC_CONSISTENCY_EXCEPTIONS_v1.tsv    n groups
  * RISK_KOSHA_620_CANONICAL_GAP_GROUPS_v1.tsv               n groups
  * RISK_KOSHA_620_NO_MATCH_GROUPS_v1.tsv                    n groups
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
from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS
from tools.risk_map.kosha_b01_semantic_evidence import (
    CANONICAL_TASK_REFERENCE_PATH,
    canonical_task_reference_sha,
)

WO_ID = "WO-RISK-KOSHA-AGGREGATE-001"

FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)

_REVIEW_DIR = Path("docs/knowledge/risk")
_EVIDENCE_DIR = Path("docs/knowledge/risk")

# Frozen per-batch SHAs (WO §2). Any drift blocks aggregation.
FROZEN_BATCHES: tuple[tuple[str, str, str, int, str], ...] = (
    (
        "B01",
        "RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv",
        "RISK_KOSHA_B01_SEMANTIC_EVIDENCE_v1.tsv",
        100,
        "4b39776f3404f100a182fa23727c74f5cb239036b78ac25d99c82b46662f8bfd",
    ),
    (
        "B02",
        "RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv",
        "RISK_KOSHA_B02_SEMANTIC_EVIDENCE_v1.tsv",
        100,
        "59dbdf26645b536aac2cd16b3cdaac477de29be793aa3d0a2c209b210e20b787",
    ),
    (
        "B03",
        "RISK_KOSHA_B03_GPT_SEMANTIC_REVIEW_v1.tsv",
        "RISK_KOSHA_B03_SEMANTIC_EVIDENCE_v1.tsv",
        100,
        "4dda24f4d3c930249e23c36f3062117cde3063f5182a7fa7a08d1d9fa1e69885",
    ),
    (
        "B04",
        "RISK_KOSHA_B04_GPT_SEMANTIC_REVIEW_v1.tsv",
        "RISK_KOSHA_B04_SEMANTIC_EVIDENCE_v1.tsv",
        100,
        "5d76544dae6c2f509a842baf8f8d394db339d62ffb3f9b6789091f637856815b",
    ),
    (
        "B05",
        "RISK_KOSHA_B05_GPT_SEMANTIC_REVIEW_v1.tsv",
        "RISK_KOSHA_B05_SEMANTIC_EVIDENCE_v1.tsv",
        100,
        "feb52cb79c36abb1f1fad96f4b7f61d3b04d57e9550696d17d85b69f6b37cda2",
    ),
    (
        "B06",
        "RISK_KOSHA_B06_GPT_SEMANTIC_REVIEW_v1.tsv",
        "RISK_KOSHA_B06_SEMANTIC_EVIDENCE_v1.tsv",
        100,
        "2d4015cf8f5c8e38d55e7fecaae48b0f07b088a23199363e332ac8b717def581",
    ),
    (
        "B07",
        "RISK_KOSHA_B07_GPT_SEMANTIC_REVIEW_v1.tsv",
        "RISK_KOSHA_B07_SEMANTIC_EVIDENCE_v1.tsv",
        20,
        "a2d64c551c1104eb304859773a0a74417560410c3d58f5cf3112d4c6abb2d5ba",
    ),
)

EXPECTED_TOTAL = 620

EXPECTED_CENSUS: dict[tuple[str, str], int] = {
    ("MAP_EXISTING_CANONICAL", "EXACT_EQUIVALENT"): 6,
    ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 40,
    ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 29,
    ("AMBIGUOUS", "AMBIGUOUS"): 78,
    ("CANONICAL_GAP", ""): 196,
    ("NO_MATCH", "NO_MATCH"): 271,
}

# The aggregate row schema extends the per-batch review schema with the
# frozen normalized labels (joined from the evidence TSVs) and a batch tag.
AGGREGATE_FIELDS: tuple[str, ...] = DECISION_FIELDS + (
    "source_name_normalized",
    "source_path_normalized",
    "batch_no",
)


AGGREGATE_PATH = _REVIEW_DIR / "RISK_KOSHA_620_GPT_SEMANTIC_AGGREGATE_v1.tsv"
MAPPING_PATH = _REVIEW_DIR / "RISK_KOSHA_620_MAPPING_CANDIDATES_v1.tsv"
AMBIGUOUS_PATH = _REVIEW_DIR / "RISK_KOSHA_620_AMBIGUOUS_v1.tsv"
GAP_PATH = _REVIEW_DIR / "RISK_KOSHA_620_CANONICAL_GAP_v1.tsv"
NO_MATCH_PATH = _REVIEW_DIR / "RISK_KOSHA_620_NO_MATCH_v1.tsv"
CONSISTENCY_PATH = _REVIEW_DIR / "RISK_KOSHA_620_SEMANTIC_CONSISTENCY_EXCEPTIONS_v1.tsv"
GAP_GROUPS_PATH = _REVIEW_DIR / "RISK_KOSHA_620_CANONICAL_GAP_GROUPS_v1.tsv"
NO_MATCH_GROUPS_PATH = _REVIEW_DIR / "RISK_KOSHA_620_NO_MATCH_GROUPS_v1.tsv"
REPORT_PATH = _REVIEW_DIR / "OBJ_risk-kosha-620-aggregate-semantic-consistency_v1.md"

CONSISTENCY_FIELDS: tuple[str, ...] = (
    "group_id",
    "source_name_normalized",
    "work_type",
    "row_count",
    "project_kinds",
    "distinct_decisions",
    "distinct_mapping_types",
    "distinct_target_ids",
    "distinct_signatures",
    "exception_type",
    "review_keys",
    "source_keys",
)

GAP_GROUP_FIELDS: tuple[str, ...] = (
    "gap_group_id",
    "source_name_normalized",
    "work_type",
    "occurrence_rows",
    "project_kinds",
    "source_paths",
    "review_keys",
    "source_keys",
)

NO_MATCH_GROUP_FIELDS: tuple[str, ...] = GAP_GROUP_FIELDS  # same shape


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _load_frozen_batch(review_file: str, evidence_file: str, sha: str) -> list[dict]:
    review_rows = load_tsv(_REVIEW_DIR / review_file)
    got = universe_sha(review_rows, *DECISION_FIELDS)
    if got != sha:
        raise SystemExit(f"BATCH_REVIEW_SHA_DRIFT {review_file}: {got} vs {sha}")
    evidence_rows = load_tsv(_EVIDENCE_DIR / evidence_file)
    ev_by_pair = {
        (r["review_key"], r["source_key"]): r for r in evidence_rows
    }
    joined: list[dict] = []
    for r in review_rows:
        pair = (r["review_key"], r["source_key"])
        ev = ev_by_pair.get(pair)
        if ev is None:
            raise SystemExit(
                f"EVIDENCE_PAIR_MISSING {review_file} {pair}"
            )
        row = dict(r)
        row["source_name_normalized"] = ev["source_name_normalized"]
        row["source_path_normalized"] = ev["source_path_normalized"]
        row["batch_no"] = r["review_batch"]
        joined.append(row)
    return joined


def build_aggregate() -> list[dict]:
    all_rows: list[dict] = []
    per_batch_counts = []
    for batch_no, review_file, evidence_file, expected, sha in FROZEN_BATCHES:
        rows = _load_frozen_batch(review_file, evidence_file, sha)
        if len(rows) != expected:
            raise SystemExit(
                f"BATCH_ROW_DRIFT {batch_no} {len(rows)} vs {expected}"
            )
        per_batch_counts.append((batch_no, len(rows)))
        all_rows.extend(rows)
    if len(all_rows) != EXPECTED_TOTAL:
        raise SystemExit(f"AGGREGATE_ROW_DRIFT {len(all_rows)}")
    # Deterministic sort by (batch_no, review_key)
    all_rows.sort(key=lambda r: (r["batch_no"], r["review_key"]))
    _assert_key_partition(all_rows)
    _assert_census(all_rows)
    _assert_target_integrity(all_rows)
    return all_rows


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def _assert_key_partition(rows: list[dict]) -> None:
    if len(rows) != EXPECTED_TOTAL:
        raise SystemExit(f"AGGREGATE_TOTAL_DRIFT {len(rows)}")
    if len({r["review_key"] for r in rows}) != EXPECTED_TOTAL:
        raise SystemExit("AGGREGATE_REVIEW_KEY_NOT_UNIQUE")
    if len({r["source_key"] for r in rows}) != EXPECTED_TOTAL:
        raise SystemExit("AGGREGATE_SOURCE_KEY_NOT_UNIQUE")
    if len({(r["review_key"], r["source_key"]) for r in rows}) != EXPECTED_TOTAL:
        raise SystemExit("AGGREGATE_PAIR_NOT_UNIQUE")


def _assert_census(rows: list[dict]) -> None:
    seen = Counter((r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows)
    if dict(seen) != EXPECTED_CENSUS:
        raise SystemExit(f"AGGREGATE_CENSUS_DRIFT got={dict(seen)}")


def _assert_target_integrity(rows: list[dict]) -> None:
    ref = load_tsv(CANONICAL_TASK_REFERENCE_PATH)
    if canonical_task_reference_sha(ref) != FROZEN_CANONICAL_TASK_REFERENCE_SHA:
        raise SystemExit("CANONICAL_TASK_REFERENCE_SHA_DRIFT")
    valid = {r["canonical_id"] for r in ref}
    for r in rows:
        dec = r["gpt_semantic_decision"]
        tgt = r["gpt_target_canonical_id"]
        mtype = r["gpt_mapping_type"]
        if dec == "MAP_EXISTING_CANONICAL":
            if not tgt:
                raise SystemExit(f"MAPPING_CANDIDATE_TARGET_BLANK {r['review_key']}")
            if tgt not in valid:
                raise SystemExit(
                    f"MAPPING_CANDIDATE_TARGET_OUT_OF_UNIVERSE {r['review_key']} {tgt}"
                )
            if mtype not in {"EXACT_EQUIVALENT", "NARROWER_THAN", "POSSIBLE_RELATED"}:
                raise SystemExit(
                    f"MAPPING_CANDIDATE_TYPE_INVALID {r['review_key']} {mtype}"
                )
        else:
            if tgt:
                raise SystemExit(f"NON_MAPPING_TARGET_NONBLANK {r['review_key']}")
            if dec == "CANONICAL_GAP" and mtype:
                raise SystemExit(f"CANONICAL_GAP_TYPE_NONBLANK {r['review_key']}")


# ---------------------------------------------------------------------------
# Bucket outputs
# ---------------------------------------------------------------------------


def _split_buckets(rows: list[dict]) -> dict[str, list[dict]]:
    mapping = [r for r in rows if r["gpt_semantic_decision"] == "MAP_EXISTING_CANONICAL"]
    ambiguous = [r for r in rows if r["gpt_semantic_decision"] == "AMBIGUOUS"]
    gap = [r for r in rows if r["gpt_semantic_decision"] == "CANONICAL_GAP"]
    no_match = [r for r in rows if r["gpt_semantic_decision"] == "NO_MATCH"]
    if len(mapping) != 75:
        raise SystemExit(f"MAPPING_CANDIDATE_COUNT_DRIFT {len(mapping)}")
    if len(ambiguous) != 78:
        raise SystemExit(f"AMBIGUOUS_COUNT_DRIFT {len(ambiguous)}")
    if len(gap) != 196:
        raise SystemExit(f"CANONICAL_GAP_COUNT_DRIFT {len(gap)}")
    if len(no_match) != 271:
        raise SystemExit(f"NO_MATCH_COUNT_DRIFT {len(no_match)}")
    if len(mapping) + len(ambiguous) + len(gap) + len(no_match) != EXPECTED_TOTAL:
        raise SystemExit("BUCKET_UNION_DRIFT")
    return {
        "mapping": mapping,
        "ambiguous": ambiguous,
        "gap": gap,
        "no_match": no_match,
    }


# ---------------------------------------------------------------------------
# Consistency exceptions (WO §6-§7)
# ---------------------------------------------------------------------------


def _semantic_signature(r: dict) -> tuple[str, str, str]:
    return (
        r["gpt_semantic_decision"],
        r["gpt_mapping_type"],
        r["gpt_target_canonical_id"],
    )


def _classify_exception(signatures: set[tuple[str, str, str]]) -> str:
    if len(signatures) < 2:
        return ""
    tags = ["MULTI_SIGNATURE_REVIEW_REQUIRED"]
    decisions = {s[0] for s in signatures}
    types = {s[1] for s in signatures}
    targets = {s[2] for s in signatures}
    if len(decisions) > 1:
        tags.append("DECISION_CONFLICT_REVIEW_REQUIRED")
    if len(types) > 1 and len(decisions) == 1:
        tags.append("TYPE_CONFLICT_REVIEW_REQUIRED")
    if (
        len(targets) > 1
        and any(t for t in targets)
        and len(decisions) == 1
        and len(types) == 1
    ):
        tags.append("TARGET_CONFLICT_REVIEW_REQUIRED")
    return "|".join(tags)


def _build_consistency_exceptions(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grouped[(r["work_type"], r["source_name_normalized"])].append(r)
    exceptions: list[dict] = []
    for gid, ((work_type, norm), grp) in enumerate(
        sorted(grouped.items(), key=lambda kv: (kv[0][1], kv[0][0])), start=1
    ):
        signatures = {_semantic_signature(r) for r in grp}
        if len(signatures) < 2:
            continue
        etype = _classify_exception(signatures)
        exceptions.append(
            {
                "group_id": f"CE-{gid:04d}",
                "source_name_normalized": norm,
                "work_type": work_type,
                "row_count": str(len(grp)),
                "project_kinds": "|".join(sorted({r["project_kind"] for r in grp})),
                "distinct_decisions": "|".join(sorted({s[0] for s in signatures})),
                "distinct_mapping_types": "|".join(sorted({s[1] for s in signatures})),
                "distinct_target_ids": "|".join(sorted({s[2] for s in signatures})),
                "distinct_signatures": str(len(signatures)),
                "exception_type": etype,
                "review_keys": "|".join(sorted(r["review_key"] for r in grp)),
                "source_keys": "|".join(sorted(r["source_key"] for r in grp)),
            }
        )
    exceptions.sort(key=lambda r: r["group_id"])
    return exceptions


# ---------------------------------------------------------------------------
# Gap / no-match groups (WO §8-§9) — mechanical label statistics only.
# ---------------------------------------------------------------------------


def _build_label_groups(rows: list[dict], id_prefix: str) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grouped[(r["work_type"], r["source_name_normalized"])].append(r)
    out: list[dict] = []
    for gid, ((work_type, norm), grp) in enumerate(
        sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0][1], kv[0][0])),
        start=1,
    ):
        out.append(
            {
                "gap_group_id": f"{id_prefix}-{gid:04d}",
                "source_name_normalized": norm,
                "work_type": work_type,
                "occurrence_rows": str(len(grp)),
                "project_kinds": "|".join(sorted({r["project_kind"] for r in grp})),
                "source_paths": "|".join(sorted({r["source_path"] for r in grp})),
                "review_keys": "|".join(sorted(r["review_key"] for r in grp)),
                "source_keys": "|".join(sorted(r["source_key"] for r in grp)),
            }
        )
    return out


# ---------------------------------------------------------------------------
# SHAs
# ---------------------------------------------------------------------------


def aggregate_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *AGGREGATE_FIELDS)


def bucket_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *AGGREGATE_FIELDS)


def consistency_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *CONSISTENCY_FIELDS)


def gap_group_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *GAP_GROUP_FIELDS)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def render_report(
    rows: list[dict],
    buckets: dict[str, list[dict]],
    exceptions: list[dict],
    gap_groups: list[dict],
    no_match_groups: list[dict],
    shas: dict[str, str],
) -> str:
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-AGGREGATE-001 KOSHA 620 aggregate semantic consistency
version: 1
status: active
owner: taiwang
---

# {WO_ID} — KOSHA 620 Aggregate Semantic Consistency

## THIS IS AGGREGATION ONLY

```text
THIS IS NOT OWNER APPROVAL
THIS IS NOT CANONICAL CREATION
THIS IS NOT PRODUCTION MATERIALIZATION
THIS DOES NOT LIFT KOSHA IDENTITY HOLD
```

Claude did not re-decide any semantic outcome. Every row is the verbatim
GPT decision from the B01-B07 frozen review artifacts, joined with the
frozen normalized label from the corresponding evidence TSV.

## Aggregate counts

```text
TOTAL                        = {len(rows)}
MAPPING CANDIDATES           = {len(buckets["mapping"])}
  EXACT_EQUIVALENT           = {EXPECTED_CENSUS[("MAP_EXISTING_CANONICAL", "EXACT_EQUIVALENT")]}
  NARROWER_THAN              = {EXPECTED_CENSUS[("MAP_EXISTING_CANONICAL", "NARROWER_THAN")]}
  POSSIBLE_RELATED           = {EXPECTED_CENSUS[("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED")]}
AMBIGUOUS                    = {len(buckets["ambiguous"])}
CANONICAL_GAP                = {len(buckets["gap"])}
NO_MATCH                     = {len(buckets["no_match"])}

Non-mapping (78 + 196 + 271) = {len(buckets["ambiguous"]) + len(buckets["gap"]) + len(buckets["no_match"])}
```

## Consistency exceptions

```text
group key                        = (work_type, source_name_normalized)
consistency exception groups     = {len(exceptions)}
```

Each exception group has ≥2 distinct decision signatures across
review rows sharing the same normalized label + work_type. These are
candidates for GPT semantic exception review — Claude classified them
mechanically but did not resolve them.

## Canonical GAP groups (label + work_type context)

```text
group key                        = (work_type, source_name_normalized)
distinct GAP context groups      = {len(gap_groups)}
```

## NO_MATCH groups (label + work_type context)

```text
group key                        = (work_type, source_name_normalized)
distinct NO_MATCH context groups = {len(no_match_groups)}
```

## Frozen inputs

Per-batch GPT review SHAs (locked, WO §2):

```text
B01 = 4b39776f3404f100a182fa23727c74f5cb239036b78ac25d99c82b46662f8bfd
B02 = 59dbdf26645b536aac2cd16b3cdaac477de29be793aa3d0a2c209b210e20b787
B03 = 4dda24f4d3c930249e23c36f3062117cde3063f5182a7fa7a08d1d9fa1e69885
B04 = 5d76544dae6c2f509a842baf8f8d394db339d62ffb3f9b6789091f637856815b
B05 = feb52cb79c36abb1f1fad96f4b7f61d3b04d57e9550696d17d85b69f6b37cda2
B06 = 2d4015cf8f5c8e38d55e7fecaae48b0f07b088a23199363e332ac8b717def581
B07 = a2d64c551c1104eb304859773a0a74417560410c3d58f5cf3112d4c6abb2d5ba

CANONICAL TASK REFERENCE = {FROZEN_CANONICAL_TASK_REFERENCE_SHA}
```

## Frozen output SHAs

```text
RISK KOSHA 620 AGGREGATE SHA                       = {shas["aggregate"]}
RISK KOSHA 620 MAPPING CANDIDATES SHA              = {shas["mapping"]}
RISK KOSHA 620 AMBIGUOUS SHA                       = {shas["ambiguous"]}
RISK KOSHA 620 CANONICAL_GAP SHA                   = {shas["gap"]}
RISK KOSHA 620 NO_MATCH SHA                        = {shas["no_match"]}
RISK KOSHA 620 CONSISTENCY EXCEPTIONS SHA          = {shas["consistency"]}
RISK KOSHA 620 CANONICAL_GAP GROUPS SHA            = {shas["gap_groups"]}
RISK KOSHA 620 NO_MATCH GROUPS SHA                 = {shas["no_match_groups"]}
```

## Verdict

```text
{WO_ID} = AGGREGATE_FROZEN / GPT_EXCEPTION_REVIEW_READY
TOTAL KOSHA REVIEWED = 620 / 620
OWNER APPROVAL = NOT OPENED
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
MERGE = NOT AUTHORIZED
NEXT = GPT AGGREGATE EXCEPTION REVIEW + CANONICAL GAP CONSOLIDATION
STOP
```
"""


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


def write_all() -> dict:
    rows_a = build_aggregate()
    rows_b = build_aggregate()
    if rows_a != rows_b:
        raise SystemExit("AGGREGATE_ROW_ORDER_DRIFT")
    sha_a = aggregate_sha(rows_a)
    sha_b = aggregate_sha(rows_b)
    if sha_a != sha_b:
        raise SystemExit(f"AGGREGATE_SHA_DRIFT {sha_a} vs {sha_b}")

    buckets = _split_buckets(rows_a)
    exceptions = _build_consistency_exceptions(rows_a)
    gap_groups = _build_label_groups(buckets["gap"], "GAP")
    no_match_groups = _build_label_groups(buckets["no_match"], "NM")

    shas = {
        "aggregate": sha_a,
        "mapping": bucket_sha(buckets["mapping"]),
        "ambiguous": bucket_sha(buckets["ambiguous"]),
        "gap": bucket_sha(buckets["gap"]),
        "no_match": bucket_sha(buckets["no_match"]),
        "consistency": consistency_sha(exceptions),
        "gap_groups": gap_group_sha(gap_groups),
        "no_match_groups": gap_group_sha(no_match_groups),
    }

    write_tsv(rows_a, AGGREGATE_PATH, AGGREGATE_FIELDS)
    write_tsv(buckets["mapping"], MAPPING_PATH, AGGREGATE_FIELDS)
    write_tsv(buckets["ambiguous"], AMBIGUOUS_PATH, AGGREGATE_FIELDS)
    write_tsv(buckets["gap"], GAP_PATH, AGGREGATE_FIELDS)
    write_tsv(buckets["no_match"], NO_MATCH_PATH, AGGREGATE_FIELDS)
    write_tsv(exceptions, CONSISTENCY_PATH, CONSISTENCY_FIELDS)
    write_tsv(gap_groups, GAP_GROUPS_PATH, GAP_GROUP_FIELDS)
    write_tsv(no_match_groups, NO_MATCH_GROUPS_PATH, NO_MATCH_GROUP_FIELDS)
    REPORT_PATH.write_text(
        render_report(rows_a, buckets, exceptions, gap_groups, no_match_groups, shas),
        encoding="utf-8",
    )

    return {
        "aggregate_rows": len(rows_a),
        "mapping_candidates": len(buckets["mapping"]),
        "ambiguous": len(buckets["ambiguous"]),
        "canonical_gap": len(buckets["gap"]),
        "no_match": len(buckets["no_match"]),
        "consistency_exception_groups": len(exceptions),
        "canonical_gap_groups": len(gap_groups),
        "no_match_groups": len(no_match_groups),
        "aggregate_sha_run1": sha_a,
        "aggregate_sha_run2": sha_b,
        "shas": shas,
        "aggregate_path": str(AGGREGATE_PATH),
        "report_path": str(REPORT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} aggregate generator")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
