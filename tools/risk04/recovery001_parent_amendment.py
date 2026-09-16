"""1-row Owner Approval Amendment for the L-02 child parent. Not Owner approval.

This pack freezes an explicit GPT parent decision. Cursor does not invent the
parent, mutate the original Owner Approval snapshot, or write canonical rows.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from tools.risk04.approve001_owner_approval_binding import (
    BINDING_PATH,
    FROZEN_OWNER_PACKAGE_SHA,
    binding_sha,
    build_binding,
)
from tools.risk04.materialize001_approved_canonical_draft import (
    FROZEN_BINDING_SHA,
    L02_CHILD_KEY,
    PLAN_PATH,
    SQL_PATH,
    plan_sha,
    sql_sha,
)
from tools.risk04.review007_preapproval_readiness import GPT_EMPTY
from tools.risk04.review014_remaining_parent_label_evidence import L02_KEY
from tools.risk04.review018_final_resolution_owner_package import (
    OWNER_PACKAGE_PATH,
    owner_package_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv, write_tsv
from tools.risk04.seed_review import universe_sha

# Explicit GPT freeze only. Cursor does not re-judge the parent.
# This is an explicit evidence pack, not a classifier.
AMENDMENT_ID = "RISK-04-APPROVE-002"
CHILD_KEY = L02_CHILD_KEY
CHILD_NAME = "의료시험및시운전공사실가스설비공사"
CHILD_SOURCE_KEY = "6731"
OLD_PARENT_KEY = L02_KEY
OLD_PARENT_NAME = "의료시험및시운전공사실가스공사 - - 대․중․소 분류대․중․소 분류"
OLD_PARENT_SOURCE_KEY = "673"
NEW_PARENT_KEY = "4d9e8f9fa87bd378789d8cf760fcc530d324b31228a4807c8d19549ba282a0af"
NEW_PARENT_NAME = "서비스설비공사"
SEMANTIC_DECISION = "NEAREST_APPROVED_ANCESTOR_AFTER_HOLD_PARENT_CONFIRMED"
SEMANTIC_BASIS = "HOLD_INTERMEDIATE_PARENT_SKIPPED_TO_UNIQUE_APPROVED_ANCESTOR"
SOURCE_CONTEXT_POLICY = "PRESERVE_ORIGINAL_HOLD_PARENT_IN_SOURCE_EVIDENCE"
FROZEN_PLAN_SHA = "48564af3da09cb659a6296ee36a6677faa05aef3f85b7aab2f1437baecd68056"
FROZEN_SQL_SHA = "f0602b25b4d72197435fec68bec20377db648fbd37a0a4e509e367432f527995"
RISK02_PATH = Path("supabase/migrations/20260915_risk_source_catalog.sql")
RISK03_PATH = Path("supabase/migrations/20260916_risk_canonical_mapping.sql")
RISK02_BLOB = "f09bec94a5815b0ceb61f1b4b1b038ebb4dced8d"
RISK03_BLOB = "68109f5e4e3a0f239e8fa153f7128240e4d2fb00"
PRODUCTION_PROJECT = "vwlahtguyggrhvslabax"
AMENDMENT_PATH = Path("docs/knowledge/risk/RISK04_OWNER_APPROVAL_AMENDMENT_001_v1.tsv")
RECEIPT_PATH = Path("docs/knowledge/risk/RISK04_SCHEMA_BOOTSTRAP_RECEIPT_v1.tsv")
REPORT_PATH = Path("docs/knowledge/risk/OBJ_risk04-recovery001-parent-amendment-schema-bootstrap_v1.md")
AMENDMENT_FIELDS = (
    "amendment_id",
    "review_concept_key",
    "semantic_kind",
    "canonical_label_candidate",
    "old_parent_review_concept_key",
    "old_parent_name",
    "new_parent_review_concept_key",
    "new_parent_name",
    "semantic_decision",
    "semantic_basis",
    "original_owner_package_sha",
    "source_context_policy",
    "owner_approval_state",
)
RECEIPT_FIELDS = (
    "project_ref",
    "risk02_migration_path",
    "risk02_blob",
    "risk02_sha256",
    "risk02_apply_status",
    "risk03_migration_path",
    "risk03_blob",
    "risk03_sha256",
    "risk03_apply_status",
    "risk_sources_count",
    "risk_source_nodes_count",
    "risk_records_count",
    "risk_canonical_nodes_count",
    "risk_source_mappings_count",
    "risk_canonical_node_sectors_count",
    "production_canonical_write",
)
RISK02_OBJECTS = (
    "risk_sources",
    "risk_snapshots",
    "risk_source_nodes",
    "risk_records",
    "risk_snapshot_memberships",
    "risk_accepted_snapshots",
)
RISK03_OBJECTS = (
    "risk_canonical_nodes",
    "risk_canonical_node_sectors",
    "risk_source_mappings",
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", f"HEAD:{path.as_posix()}"], text=True).strip()


def _assert_frozen_originals() -> dict:
    owner = load_tsv(OWNER_PACKAGE_PATH)
    binding = load_tsv(BINDING_PATH)
    if owner_package_sha(owner) != FROZEN_OWNER_PACKAGE_SHA:
        raise ValueError("owner package SHA drift")
    if binding_sha(binding) != FROZEN_BINDING_SHA:
        raise ValueError("approval binding SHA drift")
    if binding_sha(build_binding()) != FROZEN_BINDING_SHA:
        raise ValueError("rebuilt approval binding SHA drift")
    if plan_sha(load_tsv(PLAN_PATH)) != FROZEN_PLAN_SHA:
        raise ValueError("materialize plan SHA drift")
    if sql_sha(SQL_PATH.read_text(encoding="utf-8")) != FROZEN_SQL_SHA:
        raise ValueError("materialize SQL SHA drift")
    if git_blob(RISK02_PATH) != RISK02_BLOB:
        raise ValueError("RISK-02 migration blob drift")
    if git_blob(RISK03_PATH) != RISK03_BLOB:
        raise ValueError("RISK-03 migration blob drift")
    return {"owner": owner, "binding": binding}


def _approved_row(owner: list[dict], key: str) -> dict:
    matches = [row for row in owner if row["review_concept_key"] == key]
    if len(matches) != 1:
        raise ValueError(f"approved row count {key}={len(matches)}")
    return matches[0]


def build_amendment() -> list[dict]:
    pack = _assert_frozen_originals()
    owner = pack["owner"]
    child = _approved_row(owner, CHILD_KEY)
    parent = _approved_row(owner, NEW_PARENT_KEY)
    if child["canonical_label_candidate"] != CHILD_NAME:
        raise ValueError("child label drift")
    if child["semantic_kind"] != "PROCESS":
        raise ValueError("child kind drift")
    if child["source_keys"] != CHILD_SOURCE_KEY:
        raise ValueError("child source_key drift")
    if child["canonical_parent_candidate"] != OLD_PARENT_KEY:
        raise ValueError("old parent drift")
    if child["canonical_parent_candidate_name"] != OLD_PARENT_NAME:
        raise ValueError("old parent name drift")
    if parent["canonical_label_candidate"] != NEW_PARENT_NAME:
        raise ValueError("new parent name drift")
    if parent["canonical_parent_candidate"] not in {"", GPT_EMPTY}:
        raise ValueError("new parent is not READY_ROOT")
    if parent["preapproval_readiness"] != "READY_FOR_OWNER_REVIEW":
        raise ValueError("new parent readiness drift")
    if NEW_PARENT_KEY == CHILD_KEY:
        raise ValueError("new parent equals child")
    if NEW_PARENT_KEY == OLD_PARENT_KEY:
        raise ValueError("new parent equals HOLD L-02")
    if L02_KEY in {row["review_concept_key"] for row in owner}:
        raise ValueError("L-02 leaked into original package")
    return [
        {
            "amendment_id": AMENDMENT_ID,
            "review_concept_key": CHILD_KEY,
            "semantic_kind": "PROCESS",
            "canonical_label_candidate": CHILD_NAME,
            "old_parent_review_concept_key": OLD_PARENT_KEY,
            "old_parent_name": OLD_PARENT_NAME,
            "new_parent_review_concept_key": NEW_PARENT_KEY,
            "new_parent_name": NEW_PARENT_NAME,
            "semantic_decision": SEMANTIC_DECISION,
            "semantic_basis": SEMANTIC_BASIS,
            "original_owner_package_sha": FROZEN_OWNER_PACKAGE_SHA,
            "source_context_policy": SOURCE_CONTEXT_POLICY,
            "owner_approval_state": APPROVAL_STATE,
        }
    ]


def amendment_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *AMENDMENT_FIELDS)


def build_schema_receipt(status: dict) -> list[dict]:
    _assert_frozen_originals()
    return [
        {
            "project_ref": PRODUCTION_PROJECT,
            "risk02_migration_path": RISK02_PATH.as_posix(),
            "risk02_blob": RISK02_BLOB,
            "risk02_sha256": file_sha256(RISK02_PATH),
            "risk02_apply_status": status["risk02_apply_status"],
            "risk03_migration_path": RISK03_PATH.as_posix(),
            "risk03_blob": RISK03_BLOB,
            "risk03_sha256": file_sha256(RISK03_PATH),
            "risk03_apply_status": status["risk03_apply_status"],
            "risk_sources_count": str(status["risk_sources_count"]),
            "risk_source_nodes_count": str(status["risk_source_nodes_count"]),
            "risk_records_count": str(status["risk_records_count"]),
            "risk_canonical_nodes_count": str(status["risk_canonical_nodes_count"]),
            "risk_source_mappings_count": str(status["risk_source_mappings_count"]),
            "risk_canonical_node_sectors_count": str(status["risk_canonical_node_sectors_count"]),
            "production_canonical_write": str(status["production_canonical_write"]),
        }
    ]


def receipt_sha(rows: list[dict]) -> str:
    return universe_sha(rows, *RECEIPT_FIELDS)


def render_report(amendment: list[dict], a_sha: str, receipt: list[dict] | None) -> str:
    row = amendment[0]
    receipt_row = receipt[0] if receipt else {
        "risk02_apply_status": "PENDING",
        "risk03_apply_status": "PENDING",
        "risk_sources_count": "PENDING",
        "risk_source_nodes_count": "PENDING",
        "risk_records_count": "PENDING",
        "risk_canonical_nodes_count": "PENDING",
        "risk_source_mappings_count": "PENDING",
        "risk_canonical_node_sectors_count": "PENDING",
        "production_canonical_write": "0",
        "risk02_sha256": file_sha256(RISK02_PATH),
        "risk03_sha256": file_sha256(RISK03_PATH),
    }
    return f"""---
class: records
type: report
scope: knowledge
project: risk
title: OBJ-RISK-04 RECOVERY-001 parent amendment schema bootstrap
version: 1
status: active
owner: taiwang
---

# OBJ-RISK-04-RECOVERY-001 — Parent Amendment And Schema Bootstrap

This pack freezes one explicit GPT parent correction and records RISK-02 then RISK-03 schema bootstrap. Cursor did not invent the parent. Original Owner Approval remains byte-immutable. Canonical materialization stays closed until the amendment SHA is Owner-approved.

```text
PARENT LEAK = CONFIRMED
CHILD = {row["review_concept_key"]}
OLD PARENT = {row["old_parent_review_concept_key"]} / HOLD
NEW PARENT = {row["new_parent_review_concept_key"]} / {row["new_parent_name"]}
GPT SEMANTIC RESOLUTION = COMPLETE
OWNER AMENDMENT = REQUIRED
AMENDMENT PACKAGE ROWS = 1
AMENDMENT PACKAGE SHA = {a_sha}
ORIGINAL OWNER PACKAGE = UNCHANGED
ORIGINAL OWNER PACKAGE SHA = {FROZEN_OWNER_PACKAGE_SHA}
AMENDMENT OWNER APPROVAL = NOT YET
MATERIALIZATION WRITE READY = NO
```

This is an explicit evidence pack, not a classifier.

---

## Source Context Preservation

```text
source_context_policy = {SOURCE_CONTEXT_POLICY}
original_source_parent_review_concept_key = {OLD_PARENT_KEY}
original_source_parent_source_key = {OLD_PARENT_SOURCE_KEY}
original_source_parent_status = HOLD_LABEL_CONFIRMED
canonical parent skip =
L-02 → {NEW_PARENT_NAME}
```

---

## Frozen Migration Anchors

```text
RISK-02 blob = {RISK02_BLOB}
RISK-02 SHA256 = {receipt_row["risk02_sha256"]}
RISK-03 blob = {RISK03_BLOB}
RISK-03 SHA256 = {receipt_row["risk03_sha256"]}
```

---

## Production Schema

```text
production project = {PRODUCTION_PROJECT}
PRODUCTION RISK02 SCHEMA = {receipt_row["risk02_apply_status"]}
PRODUCTION RISK03 SCHEMA = {receipt_row["risk03_apply_status"]}
risk_sources = {receipt_row["risk_sources_count"]}
risk_source_nodes = {receipt_row["risk_source_nodes_count"]}
risk_records = {receipt_row["risk_records_count"]}
CANONICAL ROWS = {receipt_row["risk_canonical_nodes_count"]}
risk_source_mappings = {receipt_row["risk_source_mappings_count"]}
risk_canonical_node_sectors = {receipt_row["risk_canonical_node_sectors_count"]}
production_canonical_write = {receipt_row["production_canonical_write"]}
SOURCE INGEST = 0
```

---

## Verdict

```text
WO-RISK-04-RECOVERY-001 = AMENDMENT_READY / SCHEMA_READY
NEXT = GPT INDEPENDENT VERIFY
THEN = OWNER APPROVAL OF EXACT 1-ROW AMENDMENT SHA
THEN = RESUME WO-RISK-04-MATERIALIZE-001
MERGE = NOT AUTHORIZED
STOP
```
"""


def write_amendment_artifacts() -> dict:
    rows = build_amendment()
    sha = amendment_sha(rows)
    write_tsv(rows, AMENDMENT_PATH, AMENDMENT_FIELDS)
    REPORT_PATH.write_text(render_report(rows, sha, None), encoding="utf-8")
    return {"rows": rows, "sha": sha}


def write_recovery_artifacts(schema_status: dict) -> dict:
    amendment = write_amendment_artifacts()
    receipt = build_schema_receipt(schema_status)
    write_tsv(receipt, RECEIPT_PATH, RECEIPT_FIELDS)
    REPORT_PATH.write_text(render_report(amendment["rows"], amendment["sha"], receipt), encoding="utf-8")
    return {"amendment": amendment["rows"], "sha": amendment["sha"], "receipt": receipt}


def main() -> None:
    first = write_amendment_artifacts()
    second = build_amendment()
    print(
        __import__("json").dumps(
            {
                "WO": "WO-RISK-04-RECOVERY-001",
                "RUN1": first["sha"],
                "RUN2": amendment_sha(second),
                "ROWS": 1,
                "ORIGINAL_OWNER_PACKAGE_SHA": FROZEN_OWNER_PACKAGE_SHA,
                "AMENDMENT_OWNER_APPROVAL": "NOT_APPROVED",
                "CANONICAL_WRITE": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
