"""Owner approval binding for the exact 1110-row snapshot. Not canonical materialization.

This pack records an already-executed Owner decision against an immutable package
SHA. Cursor does not approve rows, mutate the snapshot, mint UUIDs, or write mappings.
"""
from __future__ import annotations

from pathlib import Path

from tools.risk04.review014_remaining_parent_label_evidence import L02_KEY
from tools.risk04.review018_final_resolution_owner_package import (
    FINAL_MANIFEST_PATH,
    HOLD_PACKAGE_PATH,
    OWNER_PACKAGE_PATH,
    RESOLUTION_PATH,
    final_manifest_sha,
    hold_package_sha,
    owner_package_sha,
    resolution_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Binding only. Cursor does not execute Owner Approval or canonical materialization.
# This is an explicit evidence pack, not a classifier.
FROZEN_OWNER_PACKAGE_SHA = "62c2c50e3c0becbe23a686735d1a7e50ed8bce2f3fa23c539d2250b68227c2d7"
FROZEN_HOLD_PACKAGE_SHA = "d588f9b0917ed2f0ea6e990c38db86a1700d0e74afdfe9eec536220970fd68da"
FROZEN_FINAL_MANIFEST_SHA = "2db684e0d6026f2bea1686f8188f01686638611b7068f43803cc5a83e54069c0"
FROZEN_RESOLUTION_SHA = "d8e8558cba209fdae76a3f97b8255fa7d05aa3081b0c7868821e7d322cd3de55"
EXECUTION_HEAD = "7ee8ca892c417b92dae9fe9837ffc291e13c2a2e"
OWNER_EVENT_UTC = "2026-09-16T02:03:38Z"
BINDING_PATH = Path("docs/knowledge/risk/RISK04_OWNER_APPROVAL_BINDING_v1.tsv")
RECEIPT_PATH = Path("docs/knowledge/risk/OBJ_risk04-approve001-owner-approval-execution-receipt_v1.md")
BINDING_FIELDS = (
    "approval_id",
    "approval_scope",
    "approval_decision",
    "owner_approval_event_utc",
    "owner_package_sha256",
    "owner_package_rows",
    "hold_package_sha256",
    "hold_package_rows",
    "final_manifest_sha256",
    "final_resolution_sha256",
    "repository_head_at_execution",
    "binding_target",
    "hold_policy",
    "approval_state",
)


def _assert_frozen_snapshots() -> dict:
    owner = load_tsv(OWNER_PACKAGE_PATH)
    hold = load_tsv(HOLD_PACKAGE_PATH)
    manifest = load_tsv(FINAL_MANIFEST_PATH)
    resolution = load_tsv(RESOLUTION_PATH)
    if owner_package_sha(owner) != FROZEN_OWNER_PACKAGE_SHA:
        raise ValueError("owner package SHA drift")
    if hold_package_sha(hold) != FROZEN_HOLD_PACKAGE_SHA:
        raise ValueError("hold package SHA drift")
    if final_manifest_sha(manifest) != FROZEN_FINAL_MANIFEST_SHA:
        raise ValueError("final manifest SHA drift")
    if resolution_sha(resolution) != FROZEN_RESOLUTION_SHA:
        raise ValueError("final resolution SHA drift")
    if len(owner) != 1110:
        raise ValueError(f"owner package rows {len(owner)}")
    if len(hold) != 1:
        raise ValueError(f"hold package rows {len(hold)}")
    if hold[0]["review_concept_key"] != L02_KEY:
        raise ValueError("hold key drift")
    if hold[0]["canonical_label_candidate"] != "EMPTY":
        raise ValueError("L-02 label drift")
    if any(row["owner_approval_state"] != APPROVAL_STATE for row in owner):
        raise ValueError("owner package snapshot mutated")
    if any(row["owner_approval_state"] != APPROVAL_STATE for row in hold):
        raise ValueError("hold package snapshot mutated")
    if L02_KEY in {row["review_concept_key"] for row in owner}:
        raise ValueError("L-02 leaked into approval package")
    return {"owner": owner, "hold": hold, "manifest": manifest, "resolution": resolution}


def build_binding() -> list[dict]:
    _assert_frozen_snapshots()
    return [
        {
            "approval_id": "RISK-04-APPROVE-001",
            "approval_scope": "EXACT_OWNER_APPROVAL_PACKAGE_SNAPSHOT",
            "approval_decision": "APPROVED",
            "owner_approval_event_utc": OWNER_EVENT_UTC,
            "owner_package_sha256": FROZEN_OWNER_PACKAGE_SHA,
            "owner_package_rows": "1110",
            "hold_package_sha256": FROZEN_HOLD_PACKAGE_SHA,
            "hold_package_rows": "1",
            "final_manifest_sha256": FROZEN_FINAL_MANIFEST_SHA,
            "final_resolution_sha256": FROZEN_RESOLUTION_SHA,
            "repository_head_at_execution": EXECUTION_HEAD,
            "binding_target": "PACKAGE_SHA_NOT_HEAD",
            "hold_policy": "EXCLUDED_FROM_APPROVAL",
            "approval_state": "OWNER_APPROVED",
        }
    ]


def binding_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *BINDING_FIELDS)


def render_receipt(rows: list[dict], sha: str) -> str:
    row = rows[0]
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 APPROVE-001 owner approval execution receipt
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-APPROVE-001 — Owner Approval Execution Receipt

This receipt binds an already-executed Owner decision to an immutable package snapshot. Cursor did not create the approval. OWNER APPROVAL ≠ CANONICAL MATERIALIZATION.

```text
THIS IS NOT CANONICAL CREATION
THIS IS NOT AN APPROVED MAPPING
THIS IS NOT A PRODUCTION DB WRITE
OWNER APPROVAL ≠ CANONICAL MATERIALIZATION
APPROVAL BINDING = PACKAGE SHA, NOT HEAD
snapshot row state = PREAPPROVAL SNAPSHOT STATE
binding approval state = OWNER_APPROVED
L-02 = NOT APPROVED / HOLD
PR MERGE = NOT AUTHORIZED
```

This is an explicit evidence pack, not a classifier.

---

## Execution

```text
OWNER APPROVAL = EXECUTED
APPROVAL ID = {row["approval_id"]}
OWNER APPROVAL EVENT UTC = {row["owner_approval_event_utc"]}
APPROVAL TARGET = EXACT PACKAGE SNAPSHOT
OWNER PACKAGE ROWS = 1110
OWNER PACKAGE SHA256 = {row["owner_package_sha256"]}
HOLD ROWS = 1
HOLD PACKAGE SHA256 = {row["hold_package_sha256"]}
L-02 = NOT APPROVED / HOLD
APPROVAL BINDING = PACKAGE SHA, NOT HEAD
BINDING TARGET = {row["binding_target"]}
APPROVAL STATE = {row["approval_state"]}
REPOSITORY HEAD AT EXECUTION = {row["repository_head_at_execution"]}
FINAL MANIFEST SHA256 = {row["final_manifest_sha256"]}
FINAL RESOLUTION SHA256 = {row["final_resolution_sha256"]}
BINDING SHA256 = {sha}
```

---

## After Approval

```text
OWNER APPROVED SNAPSHOT ROWS = 1110
OWNER HOLD = 1
CANONICAL UUID CREATED = 0
ACTIVE CANONICAL = 0
APPROVED MAPPING ROWS WRITTEN = 0
PRODUCTION DB WRITE = 0
NEW MIGRATION = 0
```

---

## Verdict

```text
RISK-04-APPROVE-001 = EXECUTED / EVIDENCE_READY
MERGE = NOT AUTHORIZED
NEXT = GPT INDEPENDENT VERIFY OF OWNER APPROVAL RECEIPT
THEN = CANONICAL MATERIALIZATION WO
STOP
```
"""


def write_approve001_artifacts() -> dict:
    rows = build_binding()
    sha = binding_sha(rows)
    write_tsv(rows, BINDING_PATH, BINDING_FIELDS)
    RECEIPT_PATH.write_text(render_receipt(rows, sha), encoding="utf-8")
    return {"rows": rows, "sha": sha}


def main() -> None:
    import subprocess

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != EXECUTION_HEAD:
        raise SystemExit(f"HEAD mismatch {head} != {EXECUTION_HEAD}")
    first = write_approve001_artifacts()
    second = build_binding()
    print(
        __import__("json").dumps(
            {
                "WO": "RISK-04-APPROVE-001",
                "RUN1": first["sha"],
                "RUN2": binding_sha(second),
                "OWNER_PACKAGE_SHA": FROZEN_OWNER_PACKAGE_SHA,
                "HOLD_PACKAGE_SHA": FROZEN_HOLD_PACKAGE_SHA,
                "APPROVED_ROWS": 1110,
                "HOLD_ROWS": 1,
                "CANONICAL_MINT": 0,
                "db_write": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
