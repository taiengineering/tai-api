"""WO-RISK-MAP-APPROVE-001 CIC_W source mapping package Owner approval binding.

Records an already-executed Owner decision against the immutable
RISK_MAP001_CICW_MAPPING_PROPOSAL_v1.tsv package. This tool does NOT:
  * approve rows on the Owner's behalf,
  * mutate the frozen proposal or coverage files,
  * write to any risk_source_mappings row in production,
  * transition canonical rows to ACTIVE,
  * authorize PR merge or downstream materialization.

Binding identity SHA per WO §18 is computed over a fixed subset of fields and
deliberately excludes the timestamp and repository HEAD — the same approval
package must produce the same binding SHA regardless of when it is re-run.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from tools.risk04.approve001_owner_approval_binding import FROZEN_OWNER_PACKAGE_SHA
from tools.risk04.materialize001_resume_effective_plan import (
    FROZEN_RECEIPT_SHA as FROZEN_CANONICAL_RECEIPT_SHA,
)
from tools.risk04.review_decisions import load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha
from tools.risk_map.map001_cicw_governance import (
    COVERAGE_PATH,
    EXPECTED_MAPPING_ROWS,
    PROPOSAL_FIELDS,
    PROPOSAL_PATH,
    build_proposal,
    proposal_sha,
)

WO_ID = "WO-RISK-MAP-APPROVE-001"
APPROVAL_ID = "RISK-MAP-APPROVE-001"

# Frozen: this is the exact package SHA the Owner approved.
FROZEN_PROPOSAL_SHA = "036d293c6e2fa506922c53ffcfdd44476ec903fdc639e2c12b73815d4401f026"
FROZEN_SOURCE_INGEST_RECEIPT_SHA = (
    "9493ff9f5515eec26daf0204589d1fa3dbb8128f2b58f3590f49244ebb4ecef4"
)

# Recorded from the actual Owner approval message in this session. Execution
# metadata only; does NOT contribute to the binding identity SHA (WO §18).
OWNER_APPROVAL_EVENT_UTC = "2026-09-16T20:37:16Z"
REPOSITORY_HEAD_AT_EXECUTION = "e1c887d3345b873a884027e9a71977906b9d16be"

BINDING_PATH = Path("docs/knowledge/risk/RISK_MAP001_OWNER_APPROVAL_BINDING_v1.tsv")
RECEIPT_PATH = Path(
    "docs/knowledge/risk/OBJ_risk-map-approve001-owner-approval-execution-receipt_v1.md"
)

BINDING_FIELDS: tuple[str, ...] = (
    "approval_id",
    "approval_state",
    "approval_target",
    "proposal_file",
    "proposal_rows",
    "proposal_sha256",
    "canonical_receipt_sha",
    "source_ingest_receipt_sha",
    "canonical_owner_package_sha",
    "mapping_type",
    "mapping_method",
    "scope_source_id",
    "owner_approval_event_utc",
    "repository_head_at_execution",
    "binding_target",
    "production_write_authorized",
    "materialization_authorized",
    "merge_authorized",
)

# WO §18: binding identity SHA covers this subset — timestamp and HEAD excluded
# so re-execution against the same approved package yields the same binding SHA.
BINDING_IDENTITY_FIELDS: tuple[str, ...] = (
    "approval_id",
    "approval_state",
    "proposal_rows",
    "proposal_sha256",
    "canonical_receipt_sha",
    "source_ingest_receipt_sha",
    "canonical_owner_package_sha",
    "mapping_type",
    "mapping_method",
    "scope_source_id",
    "binding_target",
)


def _verify_anchors() -> None:
    proposal_rows = load_tsv(PROPOSAL_PATH)
    if len(proposal_rows) != EXPECTED_MAPPING_ROWS:
        raise SystemExit(
            f"PROPOSAL_ROW_COUNT_DRIFT expected={EXPECTED_MAPPING_ROWS} "
            f"got={len(proposal_rows)}"
        )

    fresh = build_proposal()
    if len(fresh) != EXPECTED_MAPPING_ROWS:
        raise SystemExit(f"REBUILD_ROW_COUNT_DRIFT {len(fresh)}")
    if proposal_sha(fresh) != FROZEN_PROPOSAL_SHA:
        raise SystemExit(f"PROPOSAL_SHA_DRIFT rebuild={proposal_sha(fresh)}")
    if proposal_sha(proposal_rows) != FROZEN_PROPOSAL_SHA:
        raise SystemExit(
            f"PROPOSAL_SHA_DRIFT on_disk={proposal_sha(proposal_rows)}"
        )

    # Scope + composition guardrails on the disk proposal.
    if any(row["source_id"] != "CIC_W" for row in proposal_rows):
        raise SystemExit("PROPOSAL_SCOPE_DRIFT non-CIC_W row present")
    if {row["mapping_type"] for row in proposal_rows} != {"EXACT_EQUIVALENT"}:
        raise SystemExit("PROPOSAL_MAPPING_TYPE_DRIFT")
    if {row["mapping_status"] for row in proposal_rows} != {"PROPOSED"}:
        raise SystemExit("PROPOSAL_MAPPING_STATUS_DRIFT")
    if {row["mapping_method"] for row in proposal_rows} != {"MANUAL_REVIEW"}:
        raise SystemExit("PROPOSAL_MAPPING_METHOD_DRIFT")
    if {row["evidence_basis"] for row in proposal_rows} != {
        "OWNER_APPROVED_CONCEPT_MEMBERSHIP"
    }:
        raise SystemExit("PROPOSAL_EVIDENCE_BASIS_DRIFT")
    for row in proposal_rows:
        if row["source_key"] == "673":
            raise SystemExit("HOLD_SOURCE_LEAKED_INTO_PROPOSAL")
        if row["canonical_receipt_sha"] != FROZEN_CANONICAL_RECEIPT_SHA:
            raise SystemExit("PROPOSAL_CANONICAL_ANCHOR_DRIFT")
        if row["source_ingest_receipt_sha"] != FROZEN_SOURCE_INGEST_RECEIPT_SHA:
            raise SystemExit("PROPOSAL_SOURCE_ANCHOR_DRIFT")
        if row["owner_package_sha"] != FROZEN_OWNER_PACKAGE_SHA:
            raise SystemExit("PROPOSAL_OWNER_PACKAGE_ANCHOR_DRIFT")

    # Coverage manifest must exist and reflect the frozen accounting.
    if not COVERAGE_PATH.exists():
        raise SystemExit("COVERAGE_MANIFEST_MISSING")


def build_binding() -> list[dict]:
    _verify_anchors()
    return [
        {
            "approval_id": APPROVAL_ID,
            "approval_state": "OWNER_APPROVED",
            "approval_target": "CIC_W_SOURCE_TO_CANONICAL_MAPPING_PACKAGE",
            "proposal_file": PROPOSAL_PATH.name,
            "proposal_rows": str(EXPECTED_MAPPING_ROWS),
            "proposal_sha256": FROZEN_PROPOSAL_SHA,
            "canonical_receipt_sha": FROZEN_CANONICAL_RECEIPT_SHA,
            "source_ingest_receipt_sha": FROZEN_SOURCE_INGEST_RECEIPT_SHA,
            "canonical_owner_package_sha": FROZEN_OWNER_PACKAGE_SHA,
            "mapping_type": "EXACT_EQUIVALENT",
            "mapping_method": "MANUAL_REVIEW",
            "scope_source_id": "CIC_W",
            "owner_approval_event_utc": OWNER_APPROVAL_EVENT_UTC,
            "repository_head_at_execution": REPOSITORY_HEAD_AT_EXECUTION,
            "binding_target": "PACKAGE_SHA_NOT_HEAD",
            "production_write_authorized": "NO",
            "materialization_authorized": "NO",
            "merge_authorized": "NO",
        }
    ]


def binding_identity_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *BINDING_IDENTITY_FIELDS)


def render_receipt(rows: list[dict], sha: str) -> str:
    row = rows[0]
    return f"""---
class: records
type: receipt
scope: knowledge
project: risk
title: {WO_ID} Owner mapping approval execution receipt
version: 1
status: active
owner: taiwang
---

# {WO_ID} — Owner Mapping Approval Execution Receipt

## Approval

```text
OWNER APPROVAL           = EXECUTED
APPROVAL ID              = {row["approval_id"]}
APPROVAL STATE           = {row["approval_state"]}
APPROVAL TARGET          = EXACT MAPPING PACKAGE SNAPSHOT
PROPOSAL FILE            = {row["proposal_file"]}
PROPOSAL ROWS            = {row["proposal_rows"]}
PROPOSAL SHA             = {row["proposal_sha256"]}
```

## Anchors

```text
CANONICAL RECEIPT SHA        = {row["canonical_receipt_sha"]}
SOURCE INGEST RECEIPT SHA    = {row["source_ingest_receipt_sha"]}
CANONICAL OWNER PACKAGE SHA  = {row["canonical_owner_package_sha"]}
```

## Binding identity

```text
RISK MAP APPROVAL BINDING SHA = {sha}
BINDING TARGET               = {row["binding_target"]}
```

Binding identity SHA is computed over the fields
`{", ".join(BINDING_IDENTITY_FIELDS)}` — timestamp and HEAD are intentionally
excluded, so the same approved package yields the same binding identity across
re-executions.

## Scope

```text
scope_source_id          = {row["scope_source_id"]}
mapping_type             = {row["mapping_type"]} (all {row["proposal_rows"]} rows)
mapping_method           = {row["mapping_method"]} (all {row["proposal_rows"]} rows)
KOSHA mapping            = 0
KALIS mapping            = 0
source 673 mapping       = 0  (HOLD_LABEL preserved)
```

## What this approval does NOT authorize

```text
OWNER MAPPING APPROVAL != PRODUCTION MAPPING MATERIALIZATION
OWNER MAPPING APPROVAL != CANONICAL ACTIVE TRANSITION

production_write_authorized  = {row["production_write_authorized"]}
materialization_authorized   = {row["materialization_authorized"]}
merge_authorized             = {row["merge_authorized"]}
```

Downstream materialization is a separate WO whose inputs are:

```text
RISK MAP001 PROPOSAL SHA        = {row["proposal_sha256"]}
RISK MAP APPROVAL BINDING SHA   = {sha}
```

## Execution metadata (evidence-only, not in binding SHA)

```text
owner_approval_event_utc      = {row["owner_approval_event_utc"]}
repository_head_at_execution  = {row["repository_head_at_execution"]}
```

## Verdict

```text
{WO_ID} = OWNER_APPROVAL_BOUND / EVIDENCE_READY
PRODUCTION MAPPING           = NOT MATERIALIZED
APPROVED PRODUCTION ROWS     = 0
MATERIALIZATION              = NOT OPENED
MERGE                        = NOT AUTHORIZED
NEXT                         = GPT INDEPENDENT VERIFY
STOP
```
"""


def write_all() -> dict:
    rows = build_binding()
    sha = binding_identity_sha(rows)

    # Re-invoke to confirm deterministic identity.
    rows_again = build_binding()
    sha_again = binding_identity_sha(rows_again)
    if sha != sha_again:
        raise SystemExit(f"BINDING_SHA_DRIFT {sha} vs {sha_again}")

    write_tsv(rows, BINDING_PATH, BINDING_FIELDS)
    RECEIPT_PATH.write_text(render_receipt(rows, sha), encoding="utf-8")

    return {
        "approval_id": APPROVAL_ID,
        "approval_state": "OWNER_APPROVED",
        "proposal_rows": EXPECTED_MAPPING_ROWS,
        "proposal_sha": FROZEN_PROPOSAL_SHA,
        "canonical_receipt_sha": FROZEN_CANONICAL_RECEIPT_SHA,
        "source_ingest_receipt_sha": FROZEN_SOURCE_INGEST_RECEIPT_SHA,
        "canonical_owner_package_sha": FROZEN_OWNER_PACKAGE_SHA,
        "binding_identity_sha": sha,
        "binding_path": str(BINDING_PATH),
        "receipt_path": str(RECEIPT_PATH),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"{WO_ID} owner approval binding")
    parser.parse_args(list(argv) if argv is not None else None)
    result = write_all()
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
