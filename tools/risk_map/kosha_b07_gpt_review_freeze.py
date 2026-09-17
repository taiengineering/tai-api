"""WO-RISK-KOSHA-B07-REVIEW-001 GPT KOSHA B07 semantic decision freeze.

Transcription-only tool — same contract as B01-B06 freeze. GPT is the
semantic authority; this tool ONLY:

  * Verifies frozen input SHAs (B07 evidence + canonical TASK reference).
  * Verifies the 20-key GPT_DECISIONS manifest matches the B07 review_key
    universe. Per WO §2 the manifest is keyed by `review_key`; each
    frozen evidence row's `source_key` is preserved alongside it in the
    freeze output (WO §11 pair-preservation contract).
  * Emits the freeze TSV + census + report.
  * Never touches production or any writable DB surface.

Terminology (locked in by WO-B07 §2):
  * review_key = review-row / GPT semantic decision identity
  * source_key = KOSHA source-node identity
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
from tools.risk_map.kosha_b01_gpt_review_freeze import CENSUS_FIELDS, DECISION_FIELDS
from tools.risk_map.kosha_b01_semantic_evidence import (
    CANONICAL_TASK_REFERENCE_PATH,
    canonical_task_reference_sha,
)
from tools.risk_map.kosha_b07_semantic_evidence import (
    B07_EVIDENCE_PATH,
    b07_evidence_sha,
)

WO_ID = "WO-RISK-KOSHA-B07-REVIEW-001"
REVIEW_AUTHORITY = "GPT"
REVIEW_BATCH = "B07"

FROZEN_B07_EVIDENCE_SHA = (
    "b1c9ed4280fc971257561a2696df5748c9411c50a0c9330805375d7114af0060"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)

DECISION_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B07_GPT_SEMANTIC_REVIEW_v1.tsv"
)
CENSUS_TSV_PATH = Path(
    "docs/knowledge/risk/RISK_KOSHA_B07_GPT_SEMANTIC_CENSUS_v1.tsv"
)
REPORT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-kosha-b07-gpt-semantic-review_v1.md"
)


# ---------------------------------------------------------------------------
# GPT decision manifest — verbatim transcription of the reviewer's decisions.
# Reuses the 3 canonical TASK targets from B06 (no new canonical creation).
# ---------------------------------------------------------------------------

_TARGET_REBAR = "be965f09-464b-4d53-9be4-d72f44d3d1ee"                     # 철근가공및조립
_TARGET_TUNNEL_BLAST_EXCAVATION = "473d69ee-4433-487f-bc43-c35c1f2ea28f"   # 발파굴착
_TARGET_TUNNEL_WATERPROOF = "30fe37a0-0bd8-4c44-bd9b-76b3625115f5"         # 터널방수


# §4 NARROWER_THAN (5 rows)
_NARROWER_THAN: tuple[tuple[str, str, str, str], ...] = (
    (
        "75dbc84108299d287026eb95a0426e6c831aeb74c4ca8e08c041297d6230ea15",
        _TARGET_REBAR,
        "REBAR_ASSEMBLY_IS_A_SPECIFIC_COMPONENT_OF_CANONICAL_REBAR_PROCESSING_AND_ASSEMBLY",
        "HIGH",
    ),
    (
        "f449a909c96b3130df58e4dddc3d5ce3dfce6c82354ce73a8898440fdd55825b",
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        "TUNNEL_BLASTING_IS_A_SPECIFIC_BLASTING_PHASE_WITHIN_CANONICAL_TUNNEL_BLAST_EXCAVATION",
        "HIGH",
    ),
    (
        "166e996febc82f5819036f19d1c507552a0e0e6b73495158d54519b23b604a80",
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        "TUNNEL_EXPLOSIVE_CHARGING_IS_A_SPECIFIC_SUBACTIVITY_OF_CANONICAL_TUNNEL_BLAST_EXCAVATION",
        "HIGH",
    ),
    (
        "a41cc96a883fec6378a14ed2ea86681f3b252f5aa8369eebf1e2dc9fc1dbd577",
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        "TUNNEL_BLAST_HOLE_DRILLING_IS_A_SPECIFIC_SUBACTIVITY_OF_CANONICAL_TUNNEL_BLAST_EXCAVATION",
        "HIGH",
    ),
    (
        "3894195db2f8db54621298d038f680606f466dfc95afc25dca93c8fa62394f01",
        _TARGET_TUNNEL_WATERPROOF,
        "TUNNEL_WATERPROOF_SHEET_INSTALLATION_IS_A_SPECIFIC_SUBACTIVITY_OF_CANONICAL_TUNNEL_WATERPROOFING",
        "HIGH",
    ),
)


# §5 POSSIBLE_RELATED (1 row)
_POSSIBLE_RELATED: tuple[tuple[str, str, str], ...] = (
    (
        "ceff2e72593ece5888b377cc404f0a75341917e13ea29c421bc1d1236c46aa78",
        _TARGET_REBAR,
        "SOURCE_AND_CANONICAL_SHARE_REBAR_PROCESSING_BUT_DIFFER_ON_TRANSPORT_VERSUS_ASSEMBLY_COMPONENT",
    ),
)


# §6 AMBIGUOUS (2 rows) — HIGH: 콘크리트타설, MEDIUM: 터널 특수보강.
_REASON_CONCRETE = (
    "GENERIC_CONCRETE_PLACEMENT_DOES_NOT_DISTINGUISH_AMONG_MULTIPLE_"
    "CONCRETE_PLACEMENT_CANONICAL_TASKS"
)
_REASON_SPECIAL_TUNNEL_REINFORCEMENT = (
    "GENERIC_SPECIAL_TUNNEL_REINFORCEMENT_DOES_NOT_IDENTIFY_A_SINGLE_REINFORCEMENT_METHOD_OR_CANONICAL_TASK"
)

_AMBIGUOUS: tuple[tuple[str, str, str], ...] = (
    # 콘크리트타설
    ("fd78399b1be303af3221c5dceaf8fd6e7c517de0ecd2794cac7c83d6fce8aecd", _REASON_CONCRETE, "HIGH"),
    # 터널 특수보강
    ("92e8ce3fb60173e1756f7fc5d055efb81f9800313cd07b8220c3fd3d95040a38", _REASON_SPECIAL_TUNNEL_REINFORCEMENT, "MEDIUM"),
)


# §7 CANONICAL_GAP (7 rows) — all MEDIUM, same reason.
_CANONICAL_GAP_KEYS: tuple[str, ...] = (
    "b77a59a395b32320328db7bfe2f4adc7038d05bc2070f2855d3f614b43aaf14f",  # 철근반입
    "f8e1ae148fdaf9a81a0fba1d6d388e3bf343dccafc7761005bb74d787a63f140",  # 콘크리트 반입
    "e9400c436ab90156e3288fd42af8d3cbfcd9a8d884c7197edfa7d2daf30a8df1",  # 터널 버럭처리
    "2c6c20a1b1e14e72e2b34a73c37d7318fba2a91895be9a9e073b568c7a081ce3",  # 터널배수
    "9089154fbbc698affd5b16d090ab70136ae349866bcd3d46e2cd1b12d91d8941",  # 터널 강지보
    "f24cd96f8ab480d9e70d1df744fce5f42c1691317fade6e3fecf9da63bc5f72e",  # 터널 락볼트
    "bc063d0af6abd966eb77a18123ab0b296d70300491236412c24ceb822183a857",  # 터널 숏크리트
)


# §8 NO_MATCH (5 rows) — all HIGH, same reason.
_NO_MATCH_KEYS: tuple[str, ...] = (
    "5c800f63f14312ed1444235845a40cf6f5363f2118ffdf6903c049949fe1390a",  # 작업환경 (분진)
    "fcf2c40e71eac68f1b657313385b23a6eba4ea184165bd3b8fd640b050548158",  # 작업환경 (조명)
    "516885dcc39e2039efde07a32448211b30ca99e3cc234ab0130895834822477b",  # 작업환경 (환기)
    "aab35b3a56cba653ec6e7fcba48d5a436d9dc9088292630c5c262f2349bbafca",  # 특수터널 (Shield 공법)
    "bb65e3719d0dd018a6390376f060cf9f42b61fbf394407b14a94f9fa6369e7c8",  # 특수터널 (TBM공법)
)


_CANONICAL_GAP_REASON = (
    "VALID_TASK_BUT_NO_SUITABLE_SINGLE_CANONICAL_TASK_IN_FROZEN_REFERENCE"
)
_NO_MATCH_REASON = (
    "SOURCE_CONCEPT_IS_NOT_A_TASK_SEMANTIC_FOR_CURRENT_CANONICAL_TASK_UNIVERSE"
)


EXPECTED_CENSUS: dict[tuple[str, str], int] = {
    ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 5,
    ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 1,
    ("AMBIGUOUS", "AMBIGUOUS"): 2,
    ("CANONICAL_GAP", ""): 7,
    ("NO_MATCH", "NO_MATCH"): 5,
}


def _build_manifest() -> dict[str, dict[str, str]]:
    manifest: dict[str, dict[str, str]] = {}
    for key, target, reason, confidence in _NARROWER_THAN:
        manifest[key] = {
            "gpt_semantic_decision": "MAP_EXISTING_CANONICAL",
            "gpt_target_canonical_id": target,
            "gpt_mapping_type": "NARROWER_THAN",
            "gpt_reason": reason,
            "gpt_confidence_class": confidence,
        }
    for key, target, reason in _POSSIBLE_RELATED:
        manifest[key] = {
            "gpt_semantic_decision": "MAP_EXISTING_CANONICAL",
            "gpt_target_canonical_id": target,
            "gpt_mapping_type": "POSSIBLE_RELATED",
            "gpt_reason": reason,
            "gpt_confidence_class": "MEDIUM",
        }
    for key, reason, confidence in _AMBIGUOUS:
        manifest[key] = {
            "gpt_semantic_decision": "AMBIGUOUS",
            "gpt_target_canonical_id": "",
            "gpt_mapping_type": "AMBIGUOUS",
            "gpt_reason": reason,
            "gpt_confidence_class": confidence,
        }
    for key in _CANONICAL_GAP_KEYS:
        manifest[key] = {
            "gpt_semantic_decision": "CANONICAL_GAP",
            "gpt_target_canonical_id": "",
            "gpt_mapping_type": "",
            "gpt_reason": _CANONICAL_GAP_REASON,
            "gpt_confidence_class": "MEDIUM",
        }
    for key in _NO_MATCH_KEYS:
        manifest[key] = {
            "gpt_semantic_decision": "NO_MATCH",
            "gpt_target_canonical_id": "",
            "gpt_mapping_type": "NO_MATCH",
            "gpt_reason": _NO_MATCH_REASON,
            "gpt_confidence_class": "HIGH",
        }
    return manifest


GPT_DECISIONS: dict[str, dict[str, str]] = _build_manifest()


def _assert_manifest_shape() -> None:
    groups = {
        "NARROWER_THAN": len(_NARROWER_THAN),
        "POSSIBLE_RELATED": len(_POSSIBLE_RELATED),
        "AMBIGUOUS": len(_AMBIGUOUS),
        "CANONICAL_GAP": len(_CANONICAL_GAP_KEYS),
        "NO_MATCH": len(_NO_MATCH_KEYS),
    }
    total = sum(groups.values())
    if total != 20:
        raise SystemExit(f"MANIFEST_TOTAL_DRIFT {total} - {groups}")
    if len(GPT_DECISIONS) != 20:
        raise SystemExit(f"MANIFEST_KEY_DUPLICATE {len(GPT_DECISIONS)}")
    if groups != {
        "NARROWER_THAN": 5,
        "POSSIBLE_RELATED": 1,
        "AMBIGUOUS": 2,
        "CANONICAL_GAP": 7,
        "NO_MATCH": 5,
    }:
        raise SystemExit(f"MANIFEST_GROUP_COUNT_DRIFT {groups}")


_assert_manifest_shape()


# ---------------------------------------------------------------------------
# Freeze artifact
# ---------------------------------------------------------------------------


def _canonical_name_lookup() -> dict[str, str]:
    ref = load_tsv(CANONICAL_TASK_REFERENCE_PATH)
    if canonical_task_reference_sha(ref) != FROZEN_CANONICAL_TASK_REFERENCE_SHA:
        raise SystemExit("CANONICAL_TASK_REFERENCE_SHA_DRIFT")
    return {r["canonical_id"]: r["name"] for r in ref}


def _load_b07_evidence() -> list[dict]:
    rows = load_tsv(B07_EVIDENCE_PATH)
    if len(rows) != 20:
        raise SystemExit(f"B07_EVIDENCE_ROW_DRIFT {len(rows)}")
    if b07_evidence_sha(rows) != FROZEN_B07_EVIDENCE_SHA:
        raise SystemExit("B07_EVIDENCE_SHA_DRIFT")
    return rows


def build_decisions() -> list[dict]:
    b07 = _load_b07_evidence()
    canonical_names = _canonical_name_lookup()

    b07_review_keys = {r["review_key"] for r in b07}
    if len(b07_review_keys) != 20:
        raise SystemExit("B07_REVIEW_KEY_NOT_UNIQUE")
    manifest_keys = set(GPT_DECISIONS)
    missing = b07_review_keys - manifest_keys
    unexpected = manifest_keys - b07_review_keys
    if missing or unexpected:
        raise SystemExit(
            f"MANIFEST_REVIEW_SET_DRIFT missing={len(missing)} unexpected={len(unexpected)}"
        )

    # WO §2/§11 pair preservation: build a (review_key -> source_key) map from
    # the frozen evidence rows and re-check the emitted (review_key, source_key)
    # set matches the frozen set.
    ev_pairs = {(r["review_key"], r["source_key"]) for r in b07}
    if len(ev_pairs) != 20:
        raise SystemExit("B07_EVIDENCE_PAIR_NOT_UNIQUE")

    out: list[dict] = []
    for row in b07:
        decision = GPT_DECISIONS[row["review_key"]]
        target_id = decision["gpt_target_canonical_id"]
        if target_id:
            name = canonical_names.get(target_id)
            if not name:
                raise SystemExit(
                    f"TARGET_CANONICAL_ID_UNKNOWN {target_id} for {row['review_key']}"
                )
        else:
            name = ""
        out.append(
            {
                "review_key": row["review_key"],
                "source_key": row["source_key"],
                "project_kind": row["project_kind"],
                "work_type": row["work_type"],
                "source_name": row["source_name"],
                "source_path": row["source_path"],
                "gpt_semantic_decision": decision["gpt_semantic_decision"],
                "gpt_target_canonical_id": target_id,
                "gpt_target_canonical_name": name,
                "gpt_mapping_type": decision["gpt_mapping_type"],
                "gpt_reason": decision["gpt_reason"],
                "gpt_confidence_class": decision["gpt_confidence_class"],
                "input_evidence_sha": FROZEN_B07_EVIDENCE_SHA,
                "canonical_reference_sha": FROZEN_CANONICAL_TASK_REFERENCE_SHA,
                "review_authority": REVIEW_AUTHORITY,
                "review_batch": REVIEW_BATCH,
            }
        )

    out.sort(key=lambda r: r["review_key"])
    out_pairs = {(r["review_key"], r["source_key"]) for r in out}
    if out_pairs != ev_pairs:
        raise SystemExit("B07_DECISION_PAIR_PRESERVATION_DRIFT")
    _assert_decision_census(out)
    return out


def _assert_decision_census(rows: list[dict]) -> None:
    seen = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    if dict(seen) != EXPECTED_CENSUS:
        raise SystemExit(
            f"DECISION_CENSUS_DRIFT expected={EXPECTED_CENSUS} got={dict(seen)}"
        )
    targeted = [r for r in rows if r["gpt_target_canonical_id"]]
    if len(targeted) != 6:
        raise SystemExit(f"TARGETED_ROW_DRIFT {len(targeted)}")
    for r in targeted:
        if not r["gpt_target_canonical_name"]:
            raise SystemExit(f"TARGET_NAME_MISSING {r['review_key']}")
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    if len(blank) != 14:
        raise SystemExit(f"BLANK_TARGET_ROW_DRIFT {len(blank)}")
    distinct = {r["gpt_target_canonical_id"] for r in targeted}
    if len(distinct) != 3:
        raise SystemExit(f"DISTINCT_TARGET_UUID_DRIFT {len(distinct)}")


def build_census(rows: list[dict]) -> list[dict]:
    counts = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    keys_sorted = sorted(counts, key=lambda k: (k[0], k[1]))
    census = [
        {
            "gpt_semantic_decision": decision,
            "gpt_mapping_type": mtype,
            "count": str(counts[(decision, mtype)]),
        }
        for decision, mtype in keys_sorted
    ]
    census.append(
        {
            "gpt_semantic_decision": "TOTAL",
            "gpt_mapping_type": "",
            "count": str(sum(counts.values())),
        }
    )
    return census


def decision_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *DECISION_FIELDS)


def census_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *CENSUS_FIELDS)


def render_report(rows: list[dict], census: list[dict], sha_value: str) -> str:
    counts = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-KOSHA-B07-REVIEW-001 GPT KOSHA B07 semantic review
version: 1
status: active
owner: taiwang
---

# {WO_ID} — GPT KOSHA B07 Semantic Review (Frozen, Final Batch)

## THIS IS GPT SEMANTIC REVIEW

```text
THIS IS GPT SEMANTIC REVIEW
THIS IS NOT OWNER MAPPING APPROVAL
THIS IS NOT PRODUCTION MATERIALIZATION
THIS DOES NOT LIFT KOSHA IDENTITY HOLD
CANONICAL_GAP IS REVIEW-ONLY (not a DB mapping_type)
NO_MATCH IS REVIEW-ONLY UNTIL OWNER APPROVAL
```

## Inputs (frozen)

```text
B07 SEMANTIC EVIDENCE SHA         = {FROZEN_B07_EVIDENCE_SHA}
CANONICAL TASK REFERENCE SHA      = {FROZEN_CANONICAL_TASK_REFERENCE_SHA}
```

## Authority

```text
review_authority                  = {REVIEW_AUTHORITY}
review_batch                      = {REVIEW_BATCH}
transcription tool                = tools/risk_map/kosha_b07_gpt_review_freeze.py
manifest key                      = review_key
```

Claude performed no semantic inference. The GPT reviewer supplied 20
explicit per-review_key decisions; this tool echoes them into the freeze
artifact while preserving the corresponding `source_key` from the frozen
B07 evidence row.

## Decision census

```text
MAP_EXISTING_CANONICAL / NARROWER_THAN      = {counts.get(("MAP_EXISTING_CANONICAL", "NARROWER_THAN"), 0)}
MAP_EXISTING_CANONICAL / POSSIBLE_RELATED   = {counts.get(("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"), 0)}
AMBIGUOUS       (AMBIGUOUS)                 = {counts.get(("AMBIGUOUS", "AMBIGUOUS"), 0)}
CANONICAL_GAP                               = {counts.get(("CANONICAL_GAP", ""), 0)}
NO_MATCH        (NO_MATCH)                  = {counts.get(("NO_MATCH", "NO_MATCH"), 0)}
TOTAL                                       = {sum(counts.values())}
EXACT_EQUIVALENT                            = 0
targeted (canonical_id present)             = 6 / 20
blank-target                                = 14 / 20
distinct canonical targets                  = 3
```

B07 is almost entirely a repeat of semantic families already decided in
B06; no new canonical was created. All 6 targeted rows resolve to one of
three targets already used in earlier batches:

```text
be965f09-464b-4d53-9be4-d72f44d3d1ee  철근가공및조립
473d69ee-4433-487f-bc43-c35c1f2ea28f  발파굴착
30fe37a0-0bd8-4c44-bd9b-76b3625115f5  터널방수
```

Tunnel-specific note: 터널 숏크리트 remains CANONICAL_GAP — the
current canonical 갱구숏크리트 covers only the portal, not the
full tunnel bore. Shield / TBM 특수터널 rows are NO_MATCH because
they label a construction method rather than a specific TASK.

## Frozen SHA

```text
RISK KOSHA B07 GPT SEMANTIC REVIEW SHA = {sha_value}
```

## Cumulative KOSHA semantic review — COMPLETE

```text
B01 reviewed          = 100
B02 reviewed          = 100
B03 reviewed          = 100
B04 reviewed          = 100
B05 reviewed          = 100
B06 reviewed          = 100
B07 reviewed          =  20
TOTAL KOSHA REVIEWED  = 620 / 620
REMAINING             = 0
```

## Verdict

```text
{WO_ID} = GPT_SEMANTIC_REVIEW_FROZEN / COMPLETE
OWNER APPROVAL = NOT OPENED
KOSHA MAPPING APPROVAL = NOT OPENED
KOSHA PRODUCTION MAPPING = 0
MERGE = NOT AUTHORIZED
NEXT = GPT LEAN VERIFY
THEN = KOSHA 620 AGGREGATE SEMANTIC CONSISTENCY
STOP
```
"""


def write_all() -> dict:
    rows_a = build_decisions()
    rows_b = build_decisions()
    if rows_a != rows_b:
        raise SystemExit("DECISION_ROW_ORDER_DRIFT")
    sha_a = decision_sha(rows_a)
    sha_b = decision_sha(rows_b)
    if sha_a != sha_b:
        raise SystemExit(f"DECISION_SHA_DRIFT {sha_a} vs {sha_b}")

    census = build_census(rows_a)
    write_tsv(rows_a, DECISION_TSV_PATH, DECISION_FIELDS)
    write_tsv(census, CENSUS_TSV_PATH, CENSUS_FIELDS)
    REPORT_PATH.write_text(render_report(rows_a, census, sha_a), encoding="utf-8")

    return {
        "decision_rows": len(rows_a),
        "targeted_rows": sum(1 for r in rows_a if r["gpt_target_canonical_id"]),
        "blank_target_rows": sum(1 for r in rows_a if not r["gpt_target_canonical_id"]),
        "distinct_targets": len({r["gpt_target_canonical_id"] for r in rows_a if r["gpt_target_canonical_id"]}),
        "decision_sha_run1": sha_a,
        "decision_sha_run2": sha_b,
        "census_sha": census_sha(census),
        "decision_path": str(DECISION_TSV_PATH),
        "census_path": str(CENSUS_TSV_PATH),
        "report_path": str(REPORT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} freeze")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
