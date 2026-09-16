"""Owner approval binding for the exact 1-row parent amendment. Not materialization.

This pack records an already-executed Owner decision against an immutable amendment
SHA. Cursor does not mutate the original Owner Approval, approve L-02, or write
canonical rows.
"""
from __future__ import annotations

from pathlib import Path

from tools.risk04.approve001_owner_approval_binding import (
    BINDING_PATH as ORIGINAL_BINDING_PATH,
    FROZEN_OWNER_PACKAGE_SHA,
    binding_sha as original_binding_sha,
    build_binding as build_original_binding,
)
from tools.risk04.materialize001_approved_canonical_draft import FROZEN_BINDING_SHA
from tools.risk04.recovery001_parent_amendment import (
    AMENDMENT_PATH,
    CHILD_KEY,
    NEW_PARENT_KEY,
    NEW_PARENT_NAME,
    OLD_PARENT_KEY,
    amendment_sha,
    build_amendment,
)
from tools.risk04.review014_remaining_parent_label_evidence import L02_KEY
from tools.risk04.review018_final_resolution_owner_package import (
    OWNER_PACKAGE_PATH,
    owner_package_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Binding only. Cursor does not execute Owner Approval or canonical materialization.
# This is an explicit evidence pack, not a classifier.
FROZEN_AMENDMENT_SHA = "e9bd6dc41bd50b2ec3c200f4b1017e37cce7e2a7b7ff26139fbaef46071aa365"
OWNER_EVENT_UTC = "2026-09-16T03:15:44Z"
EXECUTION_HEAD = "9ee2581ff091ce1bf0ab17c09915a24393d4831b"
AMENDMENT_BINDING_PATH = Path("docs/knowledge/risk/RISK04_OWNER_APPROVAL_AMENDMENT_BINDING_001_v1.tsv")
RECEIPT_PATH = Path("docs/knowledge/risk/OBJ_risk04-approve002-parent-amendment-execution-receipt_v1.md")
AMENDMENT_BINDING_FIELDS = (
    "approval_id",
    "approval_type",
    "approval_decision",
    "owner_approval_event_utc",
    "amendment_package_sha256",
    "amendment_rows",
    "original_owner_package_sha256",
    "original_approval_id",
    "review_concept_key",
    "old_parent_review_concept_key",
    "new_parent_review_concept_key",
    "binding_target",
    "approval_state",
)


def _assert_frozen_snapshots() -> dict:
    owner = load_tsv(OWNER_PACKAGE_PATH)
    amendment = load_tsv(AMENDMENT_PATH)
    rebuilt_amendment = build_amendment()
    original_binding = load_tsv(ORIGINAL_BINDING_PATH)
    if owner_package_sha(owner) != FROZEN_OWNER_PACKAGE_SHA:
        raise ValueError("owner package SHA drift")
    if amendment_sha(amendment) != FROZEN_AMENDMENT_SHA:
        raise ValueError("amendment package SHA drift")
    if amendment_sha(rebuilt_amendment) != FROZEN_AMENDMENT_SHA:
        raise ValueError("rebuilt amendment package SHA drift")
    if original_binding_sha(original_binding) != FROZEN_BINDING_SHA:
        raise ValueError("original approval binding SHA drift")
    if original_binding_sha(build_original_binding()) != FROZEN_BINDING_SHA:
        raise ValueError("rebuilt original approval binding SHA drift")
    if len(owner) != 1110:
        raise ValueError(f"owner package rows {len(owner)}")
    if len(amendment) != 1:
        raise ValueError(f"amendment rows {len(amendment)}")
    row = amendment[0]
    if row["review_concept_key"] != CHILD_KEY:
        raise ValueError("child key drift")
    if row["old_parent_review_concept_key"] != OLD_PARENT_KEY:
        raise ValueError("old parent drift")
    if row["new_parent_review_concept_key"] != NEW_PARENT_KEY:
        raise ValueError("new parent drift")
    if row["new_parent_name"] != NEW_PARENT_NAME:
        raise ValueError("new parent name drift")
    if row["owner_approval_state"] != APPROVAL_STATE:
        raise ValueError("amendment snapshot mutated")
    if L02_KEY in {item["review_concept_key"] for item in owner}:
        raise ValueError("L-02 leaked into original package")
    if NEW_PARENT_KEY not in {item["review_concept_key"] for item in owner}:
        raise ValueError("new parent missing from original package")
    return {"owner": owner, "amendment": amendment}


def build_amendment_binding() -> list[dict]:
    _assert_frozen_snapshots()
    return [
        {
            "approval_id": "RISK-04-APPROVE-002",
            "approval_type": "PARENT_AMENDMENT",
            "approval_decision": "APPROVED",
            "owner_approval_event_utc": OWNER_EVENT_UTC,
            "amendment_package_sha256": FROZEN_AMENDMENT_SHA,
            "amendment_rows": "1",
            "original_owner_package_sha256": FROZEN_OWNER_PACKAGE_SHA,
            "original_approval_id": "RISK-04-APPROVE-001",
            "review_concept_key": CHILD_KEY,
            "old_parent_review_concept_key": OLD_PARENT_KEY,
            "new_parent_review_concept_key": NEW_PARENT_KEY,
            "binding_target": "AMENDMENT_PACKAGE_SHA_NOT_HEAD",
            "approval_state": "OWNER_APPROVED",
        }
    ]


def amendment_binding_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *AMENDMENT_BINDING_FIELDS)


def render_receipt(rows: list[dict], sha: str) -> str:
    row = rows[0]
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 APPROVE-002 parent amendment execution receipt
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-APPROVE-002 — Parent Amendment Owner Approval Receipt

This receipt binds an already-executed Owner decision to an immutable 1-row amendment snapshot. Cursor did not create the approval. The original 1110-row Owner Approval remains byte-immutable. OWNER APPROVAL ≠ CANONICAL MATERIALIZATION.

```text
THIS IS NOT CANONICAL CREATION
THIS IS NOT AN APPROVED MAPPING
THIS IS NOT A PRODUCTION DB WRITE
THIS IS NOT L-02 APPROVAL
OWNER APPROVAL ≠ CANONICAL MATERIALIZATION
APPROVAL BINDING = AMENDMENT PACKAGE SHA, NOT HEAD
amendment snapshot row state = NOT_APPROVED
binding approval state = OWNER_APPROVED
L-02 = HOLD / NOT APPROVED
PR MERGE = NOT AUTHORIZED
```

This is an explicit evidence pack, not a classifier.

---

## Execution

```text
RISK-04-APPROVE-002 = EXECUTED
OWNER APPROVAL = APPROVED
APPROVAL ID = {row["approval_id"]}
OWNER APPROVAL EVENT UTC = {row["owner_approval_event_utc"]}
APPROVAL TARGET = EXACT 1-ROW AMENDMENT SHA
AMENDMENT PACKAGE SHA = {row["amendment_package_sha256"]}
AMENDMENT ROWS = 1
ORIGINAL OWNER APPROVAL = PRESERVED
ORIGINAL OWNER PACKAGE SHA = {row["original_owner_package_sha256"]}
ORIGINAL APPROVAL ID = {row["original_approval_id"]}
CHILD = {row["review_concept_key"]}
OLD PARENT = {row["old_parent_review_concept_key"]} / HOLD
NEW PARENT = {row["new_parent_review_concept_key"]} / {NEW_PARENT_NAME}
L-02 = HOLD / NOT APPROVED
BINDING TARGET = {row["binding_target"]}
APPROVAL STATE = {row["approval_state"]}
BINDING SHA = {sha}
EFFECTIVE APPROVED CONCEPTS = 1110
EFFECTIVE PARENT OVERRIDES = 1
CANONICAL WRITE = 0
```

---

## After Approval

```text
BASE OWNER APPROVAL = 1110 rows / {FROZEN_OWNER_PACKAGE_SHA}
PLUS APPROVED AMENDMENT = 1 parent override / {FROZEN_AMENDMENT_SHA}
CANONICAL PRODUCTION WRITE = 0
MAPPING WRITE = 0
ACTIVE = 0
L-02 MATERIALIZE = 0
SOURCE INGEST = 0
```

---

## Verdict

```text
RISK-04-APPROVE-002 = EXECUTED / EVIDENCE_READY
NEXT = GPT INDEPENDENT VERIFY
THEN = RESUME WO-RISK-04-MATERIALIZE-001
WITH ORIGINAL OWNER PACKAGE SHA
+
APPROVED AMENDMENT SHA
MERGE = NOT AUTHORIZED
STOP
```
"""


def write_approve002_artifacts() -> dict:
    rows = build_amendment_binding()
    sha = amendment_binding_sha(rows)
    write_tsv(rows, AMENDMENT_BINDING_PATH, AMENDMENT_BINDING_FIELDS)
    RECEIPT_PATH.write_text(render_receipt(rows, sha), encoding="utf-8")
    return {"rows": rows, "sha": sha}


def main() -> None:
    import subprocess

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != EXECUTION_HEAD:
        raise SystemExit(f"HEAD mismatch {head} != {EXECUTION_HEAD}")
    first = write_approve002_artifacts()
    second = build_amendment_binding()
    print(
        __import__("json").dumps(
            {
                "WO": "RISK-04-APPROVE-002",
                "RUN1": first["sha"],
                "RUN2": amendment_binding_sha(second),
                "AMENDMENT_PACKAGE_SHA": FROZEN_AMENDMENT_SHA,
                "ORIGINAL_OWNER_PACKAGE_SHA": FROZEN_OWNER_PACKAGE_SHA,
                "AMENDMENT_ROWS": 1,
                "EFFECTIVE_APPROVED_CONCEPTS": 1110,
                "CANONICAL_WRITE": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
