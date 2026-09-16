"""RISK-04-RECOVERY-001 parent amendment and schema bootstrap. No original snapshot mutation."""
from __future__ import annotations

from pathlib import Path

from tools.risk04.approve001_owner_approval_binding import (
    BINDING_PATH,
    FROZEN_OWNER_PACKAGE_SHA,
    binding_sha,
    build_binding,
)
from tools.risk04.materialize001_approved_canonical_draft import (
    FROZEN_BINDING_SHA,
    PLAN_PATH,
    SQL_PATH,
    plan_sha,
    sql_sha,
)
from tools.risk04.recovery001_parent_amendment import (
    AMENDMENT_FIELDS,
    AMENDMENT_PATH,
    CHILD_KEY,
    CHILD_NAME,
    FROZEN_PLAN_SHA,
    FROZEN_SQL_SHA,
    NEW_PARENT_KEY,
    NEW_PARENT_NAME,
    OLD_PARENT_KEY,
    RECEIPT_FIELDS,
    RECEIPT_PATH,
    REPORT_PATH,
    RISK02_BLOB,
    RISK02_PATH,
    RISK03_BLOB,
    RISK03_PATH,
    SOURCE_CONTEXT_POLICY,
    amendment_sha,
    build_amendment,
    file_sha256,
    git_blob,
)
from tools.risk04.review007_preapproval_readiness import GPT_EMPTY
from tools.risk04.review014_remaining_parent_label_evidence import L02_KEY
from tools.risk04.review018_final_resolution_owner_package import (
    FINAL_MANIFEST_PATH,
    HOLD_PACKAGE_PATH,
    OWNER_PACKAGE_PATH,
    owner_package_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv

GENERATOR = Path("tools/risk04/recovery001_parent_amendment.py")
ORIGINAL_PATHS = (
    OWNER_PACKAGE_PATH,
    BINDING_PATH,
    HOLD_PACKAGE_PATH,
    FINAL_MANIFEST_PATH,
    PLAN_PATH,
    SQL_PATH,
    RISK02_PATH,
    RISK03_PATH,
)


def test_original_artifacts_unchanged():
    owner = load_tsv(OWNER_PACKAGE_PATH)
    assert owner_package_sha(owner) == FROZEN_OWNER_PACKAGE_SHA
    assert binding_sha(load_tsv(BINDING_PATH)) == binding_sha(build_binding()) == FROZEN_BINDING_SHA
    assert plan_sha(load_tsv(PLAN_PATH)) == FROZEN_PLAN_SHA
    assert sql_sha(SQL_PATH.read_text(encoding="utf-8")) == FROZEN_SQL_SHA
    assert git_blob(RISK02_PATH) == RISK02_BLOB
    assert git_blob(RISK03_PATH) == RISK03_BLOB
    assert L02_KEY not in {row["review_concept_key"] for row in owner}


def test_amendment_exact():
    rows = load_tsv(AMENDMENT_PATH)
    rebuilt = build_amendment()
    owner = {row["review_concept_key"]: row for row in load_tsv(OWNER_PACKAGE_PATH)}
    assert list(rows[0].keys()) == list(AMENDMENT_FIELDS)
    assert len(rows) == 1
    row = rows[0]
    child = owner[CHILD_KEY]
    parent = owner[NEW_PARENT_KEY]
    assert row["amendment_id"] == "RISK-04-APPROVE-002"
    assert row["review_concept_key"] == CHILD_KEY == child["review_concept_key"]
    assert row["semantic_kind"] == "PROCESS"
    assert row["canonical_label_candidate"] == CHILD_NAME
    assert row["old_parent_review_concept_key"] == OLD_PARENT_KEY == L02_KEY
    assert row["new_parent_review_concept_key"] == NEW_PARENT_KEY
    assert row["new_parent_name"] == NEW_PARENT_NAME == parent["canonical_label_candidate"]
    assert parent["canonical_parent_candidate"] in {"", GPT_EMPTY}
    assert parent["preapproval_readiness"] == "READY_FOR_OWNER_REVIEW"
    assert NEW_PARENT_KEY != CHILD_KEY
    assert NEW_PARENT_KEY != L02_KEY
    assert L02_KEY not in owner
    assert row["semantic_decision"] == "NEAREST_APPROVED_ANCESTOR_AFTER_HOLD_PARENT_CONFIRMED"
    assert row["semantic_basis"] == "HOLD_INTERMEDIATE_PARENT_SKIPPED_TO_UNIQUE_APPROVED_ANCESTOR"
    assert row["original_owner_package_sha"] == FROZEN_OWNER_PACKAGE_SHA
    assert row["source_context_policy"] == SOURCE_CONTEXT_POLICY
    assert row["owner_approval_state"] == APPROVAL_STATE
    assert amendment_sha(rows) == amendment_sha(rebuilt)


def test_no_original_mutation_or_write():
    src = GENERATOR.read_text(encoding="utf-8")
    lowered = src.lower()
    assert "uuid4" not in src
    assert "psycopg" not in lowered
    assert "create_client" not in lowered
    assert "execute_sql" not in lowered
    assert "kiwipiepy" not in lowered
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "This is an explicit evidence pack, not a classifier." in src
    assert "INSERT INTO public.risk_canonical_nodes" not in src
    assert "INSERT INTO public.risk_source_mappings" not in src
    assert not list(Path("supabase/migrations").glob("*recovery001*"))
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "PARENT LEAK = CONFIRMED" in report
    assert "OWNER AMENDMENT = REQUIRED" in report
    assert "ORIGINAL OWNER PACKAGE = UNCHANGED" in report
    assert "AMENDMENT OWNER APPROVAL = NOT YET" in report
    assert "MATERIALIZATION WRITE READY = NO" in report


def test_schema_receipt_consistency():
    rows = load_tsv(RECEIPT_PATH)
    assert list(rows[0].keys()) == list(RECEIPT_FIELDS)
    assert len(rows) == 1
    row = rows[0]
    assert row["project_ref"] == "vwlahtguyggrhvslabax"
    assert row["risk02_blob"] == RISK02_BLOB
    assert row["risk03_blob"] == RISK03_BLOB
    assert row["risk02_sha256"] == file_sha256(RISK02_PATH)
    assert row["risk03_sha256"] == file_sha256(RISK03_PATH)
    assert row["risk02_apply_status"] == "APPLIED"
    assert row["risk03_apply_status"] == "APPLIED"
    assert row["risk_sources_count"] == "3"
    assert row["risk_source_nodes_count"] == "0"
    assert row["risk_records_count"] == "0"
    assert row["risk_canonical_nodes_count"] == "0"
    assert row["risk_source_mappings_count"] == "0"
    assert row["risk_canonical_node_sectors_count"] == "0"
    assert row["production_canonical_write"] == "0"


def test_determinism_two_runs():
    first = build_amendment()
    second = build_amendment()
    assert amendment_sha(first) == amendment_sha(second)
    assert amendment_sha(first) == amendment_sha(load_tsv(AMENDMENT_PATH))
    assert ORIGINAL_PATHS
