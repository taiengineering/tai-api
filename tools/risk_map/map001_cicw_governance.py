"""WO-RISK-MAP-001 CIC_W approved-provenance → TAI canonical mapping governance.

Plan / evidence freeze only. No LLM. No fuzzy. No embedding. No auto name matching.
Reads repository evidence and emits an immutable 1139-row mapping proposal package.
DB write surface = 0.

Inputs (frozen repository evidence):
  * RISK04_OWNER_APPROVAL_PACKAGE_v1.tsv       (owner-approved 1110 concepts)
  * RISK04_OWNER_APPROVAL_HOLD_v1.tsv          (1 HOLD_LABEL concept, source 673)
  * RISK04_OWNER_APPROVAL_BINDING_v1.tsv       (approval binding + owner SHA)
  * RISK04_CANONICAL_MATERIALIZATION_RECEIPT_v1.tsv (1110 DRAFT canonical rows)
  * RISK04_PREAPPROVAL_EXCLUSIONS_v1.tsv       (582 semantic exclusions)
  * RISK02_SOURCE_INGEST_RECEIPT_v1.tsv        (source snapshot fingerprint)

Anchors emitted with every proposal row:
  * canonical_receipt_sha  = deterministic SHA over the canonical receipt
  * source_ingest_receipt_sha = deterministic SHA over the source ingest receipt
  * owner_package_sha      = owner-approval package fingerprint

CLI: python -m tools.risk_map.map001_cicw_governance
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from tools.risk02.contract import SOURCE_CIC_W
from tools.risk02.ingest001_source_core import (
    RECEIPT_PATH as SOURCE_INGEST_RECEIPT_PATH,
    receipt_sha as source_ingest_receipt_sha,
)
from tools.risk04.approve001_owner_approval_binding import FROZEN_OWNER_PACKAGE_SHA
from tools.risk04.identity import sha256_parts
from tools.risk04.materialize001_resume_effective_plan import (
    FROZEN_RECEIPT_SHA as FROZEN_CANONICAL_RECEIPT_SHA,
    RECEIPT_PATH as CANONICAL_RECEIPT_PATH,
    receipt_sha as canonical_receipt_sha,
)
from tools.risk04.review018_final_resolution_owner_package import (
    HOLD_PACKAGE_PATH,
    OWNER_PACKAGE_PATH,
    owner_package_sha,
)
from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

WO_ID = "WO-RISK-MAP-001"
OWNER_APPROVAL_ID = "RISK-04-APPROVE-001"

EXCLUSIONS_PATH = Path("docs/knowledge/risk/RISK04_PREAPPROVAL_EXCLUSIONS_v1.tsv")
PROPOSAL_PATH = Path("docs/knowledge/risk/RISK_MAP001_CICW_MAPPING_PROPOSAL_v1.tsv")
COVERAGE_PATH = Path("docs/knowledge/risk/RISK_MAP001_CICW_COVERAGE_v1.tsv")
REPORT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-map001-cicw-source-mapping-governance_v1.md"
)

# Frozen census — verified from repository evidence.
EXPECTED_APPROVED_CONCEPTS = 1110
EXPECTED_CANONICAL_RECEIPT_ROWS = 1110
EXPECTED_MAPPING_ROWS = 1139
EXPECTED_UNIQUE_SOURCE_KEYS = 1139
EXPECTED_PROMOTED_TARGETS = 1082
EXPECTED_PROMOTED_MAPPING_ROWS = 1082
EXPECTED_MERGED_TARGETS = 28
EXPECTED_MERGED_MAPPING_ROWS = 57
EXPECTED_HOLD_ROWS = 1
EXPECTED_HOLD_SOURCE_KEY = "673"
EXPECTED_EXCLUSIONS = 582
EXPECTED_CIC_W_TOTAL_ACCOUNTING = 1722

SOURCE_KEYS_SEPARATOR = "|"

PROPOSAL_FIELDS: tuple[str, ...] = (
    "mapping_plan_key",
    "source_id",
    "source_key",
    "source_name",
    "review_concept_key",
    "canonical_id",
    "canonical_name",
    "canonical_kind",
    "canonical_origin_type",
    "mapping_type",
    "mapping_status",
    "mapping_method",
    "evidence_basis",
    "source_context_policy",
    "owner_approval_id",
    "owner_package_sha",
    "canonical_receipt_sha",
    "source_ingest_receipt_sha",
)

COVERAGE_FIELDS: tuple[str, ...] = (
    "bucket",
    "count",
    "note",
)


def _split_pipe(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(SOURCE_KEYS_SEPARATOR) if part.strip()]


def _mapping_plan_key(source_key: str, canonical_id: str) -> str:
    """Deterministic review identity — NOT a DB primary key."""
    return sha256_parts(
        SOURCE_CIC_W,
        source_key,
        canonical_id,
        "EXACT_EQUIVALENT",
    )


def _load_inputs() -> dict:
    owner = load_tsv(OWNER_PACKAGE_PATH)
    if len(owner) != EXPECTED_APPROVED_CONCEPTS:
        raise SystemExit(f"OWNER_PACKAGE_ROWS {len(owner)}")
    if owner_package_sha(owner) != FROZEN_OWNER_PACKAGE_SHA:
        raise SystemExit("OWNER_PACKAGE_SHA_DRIFT")

    receipt = load_tsv(CANONICAL_RECEIPT_PATH)
    if len(receipt) != EXPECTED_CANONICAL_RECEIPT_ROWS:
        raise SystemExit(f"CANONICAL_RECEIPT_ROWS {len(receipt)}")
    if canonical_receipt_sha(receipt) != FROZEN_CANONICAL_RECEIPT_SHA:
        raise SystemExit("CANONICAL_RECEIPT_SHA_DRIFT")

    source_ingest = load_tsv(SOURCE_INGEST_RECEIPT_PATH)
    if len(source_ingest) != 3:
        raise SystemExit(f"SOURCE_INGEST_RECEIPT_ROWS {len(source_ingest)}")
    ingest_sha = source_ingest_receipt_sha(source_ingest)

    hold = load_tsv(HOLD_PACKAGE_PATH)
    if len(hold) != EXPECTED_HOLD_ROWS:
        raise SystemExit(f"HOLD_ROWS {len(hold)}")
    if hold[0]["source_keys"].strip() != EXPECTED_HOLD_SOURCE_KEY:
        raise SystemExit(f"HOLD_SOURCE_DRIFT {hold[0]['source_keys']!r}")

    exclusions = load_tsv(EXCLUSIONS_PATH)
    if len(exclusions) != EXPECTED_EXCLUSIONS:
        raise SystemExit(f"EXCLUSIONS_ROWS {len(exclusions)}")

    return {
        "owner": owner,
        "canonical_receipt": receipt,
        "source_ingest_receipt_sha": ingest_sha,
        "hold": hold,
        "exclusions": exclusions,
    }


def build_proposal(inputs: dict | None = None) -> list[dict]:
    inputs = inputs or _load_inputs()
    owner = inputs["owner"]
    receipt = inputs["canonical_receipt"]

    receipt_by_rck: dict[str, dict] = {r["review_concept_key"]: r for r in receipt}

    owner_rcks = {r["review_concept_key"] for r in owner}
    receipt_rcks = set(receipt_by_rck)
    if owner_rcks != receipt_rcks:
        raise SystemExit(
            "REVIEW_CONCEPT_KEY_JOIN_DRIFT owner_only=%d receipt_only=%d"
            % (len(owner_rcks - receipt_rcks), len(receipt_rcks - owner_rcks))
        )

    rows: list[dict] = []
    seen_source_keys: set[str] = set()

    for concept in owner:
        rck = concept["review_concept_key"]
        canonical = receipt_by_rck[rck]
        n_expected = int(concept["source_member_count"])
        source_keys = _split_pipe(concept["source_keys"])
        source_names = _split_pipe(concept["source_names"])
        if len(source_keys) != n_expected:
            raise SystemExit(
                f"SOURCE_KEYS_COUNT_MISMATCH rck={rck} expected={n_expected} "
                f"parsed={len(source_keys)}"
            )
        if len(source_names) != n_expected:
            raise SystemExit(
                f"SOURCE_NAMES_COUNT_MISMATCH rck={rck} expected={n_expected} "
                f"parsed={len(source_names)}"
            )
        for source_key, source_name in zip(source_keys, source_names):
            if source_key == EXPECTED_HOLD_SOURCE_KEY:
                raise SystemExit("HOLD_SOURCE_IN_APPROVED_PACKAGE 673")
            if source_key in seen_source_keys:
                raise SystemExit(f"DUPLICATE_SOURCE_KEY {source_key}")
            seen_source_keys.add(source_key)
            rows.append(
                {
                    "mapping_plan_key": _mapping_plan_key(source_key, canonical["canonical_id"]),
                    "source_id": SOURCE_CIC_W,
                    "source_key": source_key,
                    "source_name": source_name,
                    "review_concept_key": rck,
                    "canonical_id": canonical["canonical_id"],
                    "canonical_name": canonical["name"],
                    "canonical_kind": canonical["node_kind"],
                    "canonical_origin_type": canonical["origin_type"],
                    "mapping_type": "EXACT_EQUIVALENT",
                    "mapping_status": "PROPOSED",
                    "mapping_method": "MANUAL_REVIEW",
                    "evidence_basis": "OWNER_APPROVED_CONCEPT_MEMBERSHIP",
                    "source_context_policy": concept["source_context_policy"],
                    "owner_approval_id": OWNER_APPROVAL_ID,
                    "owner_package_sha": FROZEN_OWNER_PACKAGE_SHA,
                    "canonical_receipt_sha": FROZEN_CANONICAL_RECEIPT_SHA,
                    "source_ingest_receipt_sha": inputs["source_ingest_receipt_sha"],
                }
            )

    rows.sort(key=lambda r: (r["source_id"], r["source_key"], r["canonical_id"]))

    _assert_census(rows, inputs)
    return rows


def _assert_census(rows: list[dict], inputs: dict) -> None:
    if len(rows) != EXPECTED_MAPPING_ROWS:
        raise SystemExit(f"MAPPING_ROW_COUNT_DRIFT {len(rows)}")

    unique_source_keys = {r["source_key"] for r in rows}
    if len(unique_source_keys) != EXPECTED_UNIQUE_SOURCE_KEYS:
        raise SystemExit(f"UNIQUE_SOURCE_KEY_DRIFT {len(unique_source_keys)}")

    if any(r["source_id"] != SOURCE_CIC_W for r in rows):
        raise SystemExit("NON_CIC_W_ROW_PRESENT")

    types = {r["mapping_type"] for r in rows}
    if types != {"EXACT_EQUIVALENT"}:
        raise SystemExit(f"MAPPING_TYPE_DRIFT {types}")
    statuses = {r["mapping_status"] for r in rows}
    if statuses != {"PROPOSED"}:
        raise SystemExit(f"MAPPING_STATUS_DRIFT {statuses}")
    methods = {r["mapping_method"] for r in rows}
    if methods != {"MANUAL_REVIEW"}:
        raise SystemExit(f"MAPPING_METHOD_DRIFT {methods}")

    canonical_targets = {r["canonical_id"] for r in rows}
    if len(canonical_targets) != EXPECTED_APPROVED_CONCEPTS:
        raise SystemExit(f"CANONICAL_COVERAGE_DRIFT covered={len(canonical_targets)}")

    promoted_rows = [
        r for r in rows if r["canonical_origin_type"] == "PROMOTED_FROM_SOURCE"
    ]
    merged_rows = [
        r for r in rows if r["canonical_origin_type"] == "MERGED_FROM_REVIEWED_SOURCES"
    ]
    if len(promoted_rows) != EXPECTED_PROMOTED_MAPPING_ROWS:
        raise SystemExit(f"PROMOTED_MAP_DRIFT {len(promoted_rows)}")
    if len(merged_rows) != EXPECTED_MERGED_MAPPING_ROWS:
        raise SystemExit(f"MERGED_MAP_DRIFT {len(merged_rows)}")
    promoted_targets = {r["canonical_id"] for r in promoted_rows}
    merged_targets = {r["canonical_id"] for r in merged_rows}
    if len(promoted_targets) != EXPECTED_PROMOTED_TARGETS:
        raise SystemExit(f"PROMOTED_TARGET_DRIFT {len(promoted_targets)}")
    if len(merged_targets) != EXPECTED_MERGED_TARGETS:
        raise SystemExit(f"MERGED_TARGET_DRIFT {len(merged_targets)}")

    if EXPECTED_HOLD_SOURCE_KEY in unique_source_keys:
        raise SystemExit("HOLD_SOURCE_LEAKED")

    exclusion_source_keys = {r["source_key"] for r in inputs["exclusions"]}
    overlap = unique_source_keys & exclusion_source_keys
    if overlap:
        raise SystemExit(f"EXCLUSION_OVERLAP {len(overlap)}")

    total_accounted = (
        EXPECTED_MAPPING_ROWS + EXPECTED_HOLD_ROWS + EXPECTED_EXCLUSIONS
    )
    if total_accounted != EXPECTED_CIC_W_TOTAL_ACCOUNTING:
        raise SystemExit(f"CIC_W_ACCOUNTING_DRIFT {total_accounted}")


def build_coverage(rows: list[dict]) -> list[dict]:
    return [
        {
            "bucket": "CIC_W_TOTAL_NODES",
            "count": str(EXPECTED_CIC_W_TOTAL_ACCOUNTING),
            "note": "risk_source_nodes count for source_id=CIC_W",
        },
        {
            "bucket": "MAPPING_PROPOSED",
            "count": str(len(rows)),
            "note": "OWNER_APPROVED_CONCEPT_MEMBERSHIP → EXACT_EQUIVALENT / PROPOSED",
        },
        {
            "bucket": "UNIQUE_SOURCE_KEYS",
            "count": str(len({r["source_key"] for r in rows})),
            "note": "one source key maps to exactly one canonical target",
        },
        {
            "bucket": "CANONICAL_TARGETS_COVERED",
            "count": str(len({r["canonical_id"] for r in rows})),
            "note": "of 1110 DRAFT canonical rows",
        },
        {
            "bucket": "PROMOTED_TARGETS",
            "count": str(EXPECTED_PROMOTED_TARGETS),
            "note": f"{EXPECTED_PROMOTED_MAPPING_ROWS} mapping rows (1:1)",
        },
        {
            "bucket": "MERGED_TARGETS",
            "count": str(EXPECTED_MERGED_TARGETS),
            "note": f"{EXPECTED_MERGED_MAPPING_ROWS} mapping rows (N:1)",
        },
        {
            "bucket": "UNMAPPED_HOLD_LABEL",
            "count": str(EXPECTED_HOLD_ROWS),
            "note": f"source_key={EXPECTED_HOLD_SOURCE_KEY}; semantic label HOLD, not NO_MATCH",
        },
        {
            "bucket": "SEMANTIC_EXCLUSIONS",
            "count": str(EXPECTED_EXCLUSIONS),
            "note": "carried forward from RISK04_PREAPPROVAL_EXCLUSIONS_v1.tsv",
        },
        {
            "bucket": "ACCOUNTING_SUM",
            "count": str(
                EXPECTED_MAPPING_ROWS + EXPECTED_HOLD_ROWS + EXPECTED_EXCLUSIONS
            ),
            "note": "MAPPING + HOLD + EXCLUSIONS = CIC_W total",
        },
        {
            "bucket": "OVERLAP_EXCLUSIONS_VS_MAPPING",
            "count": "0",
            "note": "no source_key appears in both",
        },
        {
            "bucket": "KOSHA_MAPPING",
            "count": "0",
            "note": "out of scope in WO-RISK-MAP-001",
        },
        {
            "bucket": "KALIS_MAPPING",
            "count": "0",
            "note": "out of scope in WO-RISK-MAP-001",
        },
        {
            "bucket": "PRODUCTION_MAPPING_WRITE",
            "count": "0",
            "note": "immutable proposal freeze only",
        },
    ]


def proposal_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *PROPOSAL_FIELDS)


def render_report(rows: list[dict], inputs: dict, sha: str) -> str:
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: WO-RISK-MAP-001 CIC_W approved-provenance source mapping governance
version: 1
status: active
owner: taiwang
---

# {WO_ID} — CIC_W Source Mapping Governance (Plan / Evidence Freeze)

Owner-approved TAI canonical concepts (1110) are the semantic authority. This
package converts approved concept membership into an immutable source →
canonical mapping proposal. No search identity, no fuzzy, no LLM. Production
mapping write = 0.

## Anchors

```text
CANONICAL RECEIPT SHA        = {FROZEN_CANONICAL_RECEIPT_SHA}
SOURCE INGEST RECEIPT SHA    = {inputs["source_ingest_receipt_sha"]}
OWNER PACKAGE SHA            = {FROZEN_OWNER_PACKAGE_SHA}
OWNER APPROVAL ID            = {OWNER_APPROVAL_ID}
```

Owner approval of canonical concept membership is NOT approval of the mapping
package. Mapping approval is a separate future WO.

## Scope

```text
source_id in scope           = CIC_W (only)
KOSHA mapping                = 0
KALIS mapping                = 0
```

## Census

```text
approved concepts            = {EXPECTED_APPROVED_CONCEPTS}
expanded CIC_W source members = {EXPECTED_MAPPING_ROWS}
unique source keys           = {EXPECTED_UNIQUE_SOURCE_KEYS}
canonical targets covered    = {len({r['canonical_id'] for r in rows})} / {EXPECTED_APPROVED_CONCEPTS}

PROMOTED targets             = {EXPECTED_PROMOTED_TARGETS}
PROMOTED mapping rows        = {EXPECTED_PROMOTED_MAPPING_ROWS}
MERGED targets               = {EXPECTED_MERGED_TARGETS}
MERGED mapping rows          = {EXPECTED_MERGED_MAPPING_ROWS}

mapping_type                 = EXACT_EQUIVALENT (all {len(rows)} rows)
mapping_status               = PROPOSED (all {len(rows)} rows)
mapping_method               = MANUAL_REVIEW (all {len(rows)} rows)

HOLD source (source_key=673) = present in HOLD package, NOT in mapping proposal
semantic exclusions          = {EXPECTED_EXCLUSIONS}
CIC_W total accounting       = {EXPECTED_MAPPING_ROWS} + {EXPECTED_HOLD_ROWS} + {EXPECTED_EXCLUSIONS} = {EXPECTED_CIC_W_TOTAL_ACCOUNTING}
```

## Evidence basis

Every proposal row's `evidence_basis = OWNER_APPROVED_CONCEPT_MEMBERSHIP`. The
provenance is the semantic review + Owner package approval, not name or path
similarity.

## Package SHA

```text
RISK MAP001 PROPOSAL SHA     = {sha}
```

This SHA is the anchor for the subsequent SOURCE MAPPING APPROVAL WO. It does
not by itself grant mapping approval.

## Guardrails

```text
production risk_source_mappings write = 0
canonical unchanged (1110 DRAFT / 0 ACTIVE / 0 canonical_code assigned)
mapping_status APPROVED               = 0
NO_MATCH / AMBIGUOUS / REJECTED rows  = 0
LLM / fuzzy / embedding used          = 0
```

## Verdict

```text
{WO_ID} = MAPPING_PROPOSAL_FROZEN / EVIDENCE_READY
PRODUCTION MAPPING = NOT MATERIALIZED
APPROVED MAPPING = 0
NEXT = GPT INDEPENDENT VERIFY
THEN = OWNER MAPPING APPROVAL
MERGE = NOT AUTHORIZED
STOP
```
"""


def write_all() -> dict:
    inputs = _load_inputs()

    rows_run1 = build_proposal(inputs)
    sha_run1 = proposal_sha(rows_run1)

    rows_run2 = build_proposal(inputs)
    sha_run2 = proposal_sha(rows_run2)

    if sha_run1 != sha_run2:
        raise SystemExit(f"DETERMINISM_DRIFT {sha_run1} vs {sha_run2}")
    if rows_run1 != rows_run2:
        raise SystemExit("DETERMINISM_ROW_ORDER_DRIFT")

    coverage = build_coverage(rows_run1)

    write_tsv(rows_run1, PROPOSAL_PATH, PROPOSAL_FIELDS)
    write_tsv(coverage, COVERAGE_PATH, COVERAGE_FIELDS)
    REPORT_PATH.write_text(
        render_report(rows_run1, inputs, sha_run1), encoding="utf-8"
    )

    return {
        "rows": len(rows_run1),
        "unique_source_keys": len({r["source_key"] for r in rows_run1}),
        "canonical_targets_covered": len({r["canonical_id"] for r in rows_run1}),
        "proposal_sha_run1": sha_run1,
        "proposal_sha_run2": sha_run2,
        "source_ingest_receipt_sha": inputs["source_ingest_receipt_sha"],
        "canonical_receipt_sha": FROZEN_CANONICAL_RECEIPT_SHA,
        "owner_package_sha": FROZEN_OWNER_PACKAGE_SHA,
        "proposal_path": str(PROPOSAL_PATH),
        "coverage_path": str(COVERAGE_PATH),
        "report_path": str(REPORT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} governance plan")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
