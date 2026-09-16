"""RISK-04-APPROVE-002 parent amendment binding. No snapshot mutation and no materialization."""
from __future__ import annotations

from pathlib import Path

from tools.risk04.approve001_owner_approval_binding import (
    BINDING_PATH as ORIGINAL_BINDING_PATH,
    FROZEN_OWNER_PACKAGE_SHA,
    binding_sha as original_binding_sha,
    build_binding as build_original_binding,
)
from tools.risk04.approve002_parent_amendment_binding import (
    AMENDMENT_BINDING_FIELDS,
    AMENDMENT_BINDING_PATH,
    FROZEN_AMENDMENT_SHA,
    RECEIPT_PATH,
    amendment_binding_sha,
    build_amendment_binding,
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
from tools.risk04.review007_preapproval_readiness import GPT_EMPTY
from tools.risk04.review014_remaining_parent_label_evidence import L02_KEY
from tools.risk04.review018_final_resolution_owner_package import (
    OWNER_PACKAGE_PATH,
    owner_package_sha,
)
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv

GENERATOR = Path("tools/risk04/approve002_parent_amendment_binding.py")


def test_frozen_snapshots_unchanged():
    owner = load_tsv(OWNER_PACKAGE_PATH)
    amendment = load_tsv(AMENDMENT_PATH)
    assert owner_package_sha(owner) == FROZEN_OWNER_PACKAGE_SHA
    assert amendment_sha(amendment) == amendment_sha(build_amendment()) == FROZEN_AMENDMENT_SHA
    assert original_binding_sha(load_tsv(ORIGINAL_BINDING_PATH)) == original_binding_sha(build_original_binding()) == FROZEN_BINDING_SHA
    assert len(owner) == 1110
    assert len(amendment) == 1
    assert amendment[0]["owner_approval_state"] == APPROVAL_STATE
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in owner)
    assert L02_KEY not in {row["review_concept_key"] for row in owner}


def test_amendment_binding_exact():
    rows = load_tsv(AMENDMENT_BINDING_PATH)
    rebuilt = build_amendment_binding()
    owner = {row["review_concept_key"]: row for row in load_tsv(OWNER_PACKAGE_PATH)}
    parent = owner[NEW_PARENT_KEY]
    assert list(rows[0].keys()) == list(AMENDMENT_BINDING_FIELDS)
    assert len(rows) == 1
    row = rows[0]
    assert row["approval_id"] == "RISK-04-APPROVE-002"
    assert row["approval_type"] == "PARENT_AMENDMENT"
    assert row["approval_decision"] == "APPROVED"
    assert row["approval_state"] == "OWNER_APPROVED"
    assert row["binding_target"] == "AMENDMENT_PACKAGE_SHA_NOT_HEAD"
    assert row["amendment_package_sha256"] == FROZEN_AMENDMENT_SHA
    assert row["amendment_rows"] == "1"
    assert row["original_owner_package_sha256"] == FROZEN_OWNER_PACKAGE_SHA
    assert row["original_approval_id"] == "RISK-04-APPROVE-001"
    assert row["review_concept_key"] == CHILD_KEY
    assert row["old_parent_review_concept_key"] == OLD_PARENT_KEY == L02_KEY
    assert row["new_parent_review_concept_key"] == NEW_PARENT_KEY
    assert parent["canonical_label_candidate"] == NEW_PARENT_NAME
    assert parent["canonical_parent_candidate"] in {"", GPT_EMPTY}
    assert NEW_PARENT_KEY != CHILD_KEY
    assert NEW_PARENT_KEY != L02_KEY
    assert amendment_binding_sha(rows) == amendment_binding_sha(rebuilt)
    assert len(owner) == 1110


def test_effective_override_contract():
    owner = load_tsv(OWNER_PACKAGE_PATH)
    binding = load_tsv(AMENDMENT_BINDING_PATH)[0]
    overrides = [
        row
        for row in owner
        if row["review_concept_key"] == binding["review_concept_key"]
    ]
    assert len(owner) == 1110
    assert len(overrides) == 1
    assert binding["new_parent_review_concept_key"] == NEW_PARENT_KEY
    assert overrides[0]["canonical_parent_candidate"] == OLD_PARENT_KEY


def test_no_materialization_or_snapshot_rewrite():
    src = GENERATOR.read_text(encoding="utf-8")
    lowered = src.lower()
    assert "uuid4" not in src
    assert "canonical_uuid" not in lowered
    assert "psycopg" not in lowered
    assert "kiwipiepy" not in lowered
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "This is an explicit evidence pack, not a classifier." in src
    assert "write_tsv(rows, AMENDMENT_PATH" not in src
    assert "write_tsv(rows, ORIGINAL_BINDING_PATH" not in src
    assert not list(Path("supabase/migrations").glob("*approve002*"))
    receipt = RECEIPT_PATH.read_text(encoding="utf-8")
    assert "RISK-04-APPROVE-002 = EXECUTED" in receipt
    assert "OWNER APPROVAL = APPROVED" in receipt
    assert FROZEN_AMENDMENT_SHA in receipt
    assert "AMENDMENT ROWS = 1" in receipt
    assert "ORIGINAL OWNER APPROVAL = PRESERVED" in receipt
    assert FROZEN_OWNER_PACKAGE_SHA in receipt
    assert CHILD_KEY in receipt
    assert OLD_PARENT_KEY in receipt
    assert NEW_PARENT_KEY in receipt
    assert "L-02 = HOLD / NOT APPROVED" in receipt
    assert "CANONICAL WRITE = 0" in receipt
    assert "OWNER APPROVAL ≠ CANONICAL MATERIALIZATION" in receipt
    assert load_tsv(AMENDMENT_PATH)[0]["owner_approval_state"] == APPROVAL_STATE


def test_determinism_two_runs():
    first = build_amendment_binding()
    second = build_amendment_binding()
    on_disk = load_tsv(AMENDMENT_BINDING_PATH)
    assert amendment_binding_sha(first) == amendment_binding_sha(second) == amendment_binding_sha(on_disk)
