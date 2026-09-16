"""RISK-04-APPROVE-001 owner approval binding. No snapshot mutation and no materialization."""
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
from tools.risk04.review_decisions import APPROVAL_STATE, load_tsv
from tools.risk04.approve001_owner_approval_binding import (
    BINDING_FIELDS,
    BINDING_PATH,
    EXECUTION_HEAD,
    FROZEN_FINAL_MANIFEST_SHA,
    FROZEN_HOLD_PACKAGE_SHA,
    FROZEN_OWNER_PACKAGE_SHA,
    FROZEN_RESOLUTION_SHA,
    RECEIPT_PATH,
    binding_sha,
    build_binding,
)

BINDING_SHA = "fc2537cb3ec72f204beda6a416f77ca7a3d1c5b55f976fe1bdfa93b6f87fcfa0"
GENERATOR = Path("tools/risk04/approve001_owner_approval_binding.py")


def test_frozen_snapshot_hashes_unchanged():
    owner = load_tsv(OWNER_PACKAGE_PATH)
    hold = load_tsv(HOLD_PACKAGE_PATH)
    assert owner_package_sha(owner) == FROZEN_OWNER_PACKAGE_SHA
    assert hold_package_sha(hold) == FROZEN_HOLD_PACKAGE_SHA
    assert final_manifest_sha(load_tsv(FINAL_MANIFEST_PATH)) == FROZEN_FINAL_MANIFEST_SHA
    assert resolution_sha(load_tsv(RESOLUTION_PATH)) == FROZEN_RESOLUTION_SHA
    assert len(owner) == 1110
    assert len(hold) == 1
    assert hold[0]["review_concept_key"] == L02_KEY
    assert hold[0]["canonical_label_candidate"] == "EMPTY"
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in owner)
    assert all(row["owner_approval_state"] == APPROVAL_STATE for row in hold)
    assert L02_KEY not in {row["review_concept_key"] for row in owner}


def test_binding_exact():
    rows = load_tsv(BINDING_PATH)
    rebuilt = build_binding()
    assert list(rows[0].keys()) == list(BINDING_FIELDS)
    assert len(rows) == 1
    row = rows[0]
    assert row["approval_id"] == "RISK-04-APPROVE-001"
    assert row["approval_decision"] == "APPROVED"
    assert row["binding_target"] == "PACKAGE_SHA_NOT_HEAD"
    assert row["approval_state"] == "OWNER_APPROVED"
    assert row["owner_package_sha256"] == FROZEN_OWNER_PACKAGE_SHA
    assert row["owner_package_rows"] == "1110"
    assert row["hold_package_sha256"] == FROZEN_HOLD_PACKAGE_SHA
    assert row["hold_package_rows"] == "1"
    assert row["hold_policy"] == "EXCLUDED_FROM_APPROVAL"
    assert row["repository_head_at_execution"] == EXECUTION_HEAD
    assert row["final_manifest_sha256"] == FROZEN_FINAL_MANIFEST_SHA
    assert row["final_resolution_sha256"] == FROZEN_RESOLUTION_SHA
    assert binding_sha(rows) == binding_sha(rebuilt) == BINDING_SHA


def test_no_materialization_or_snapshot_rewrite():
    src = GENERATOR.read_text(encoding="utf-8")
    lowered = src.lower()
    assert "uuid4" not in src
    assert "canonical_uuid" not in lowered
    assert "risk_canonical_nodes" not in lowered
    assert "psycopg" not in lowered
    assert "supabase" not in lowered
    assert "kiwipiepy" not in lowered
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "This is an explicit evidence pack, not a classifier." in src
    assert not list(Path("supabase/migrations").glob("*approve001*"))
    receipt = RECEIPT_PATH.read_text(encoding="utf-8")
    assert "OWNER APPROVAL = EXECUTED" in receipt
    assert "APPROVAL TARGET =" in receipt
    assert "EXACT PACKAGE SNAPSHOT" in receipt
    assert "OWNER PACKAGE ROWS = 1110" in receipt
    assert FROZEN_OWNER_PACKAGE_SHA in receipt
    assert "HOLD ROWS = 1" in receipt
    assert FROZEN_HOLD_PACKAGE_SHA in receipt
    assert "L-02 = NOT APPROVED / HOLD" in receipt
    assert "APPROVAL BINDING = PACKAGE SHA, NOT HEAD" in receipt
    assert "CANONICAL UUID CREATED = 0" in receipt
    assert "OWNER APPROVAL ≠ CANONICAL MATERIALIZATION" in receipt


def test_determinism_two_runs():
    first = build_binding()
    second = build_binding()
    assert binding_sha(first) == binding_sha(second) == BINDING_SHA
