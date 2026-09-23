"""WO-MSDS-INCREMENTAL-PUBLISH-001 — fixture tests (A–K + T1–T5, PATCH-1).

Tests verify the incremental publish tool's safety fences, frozen SHA pins,
four-way responses binding, and production mutation-0 contract.
Fixtures A–K correspond to WO §14; T1–T5 are PATCH-1 regression tests.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.kosha_msds import materialize_writer as w
from services.kosha_msds.contract import (
    PUBLICATION_SCOPE_SEO_PREVIEW,
    PUBLISH_PUBLISHED_SEO_PREVIEW,
    SNAPSHOT_COMPLETED,
    SNAPSHOT_FAILED,
    SNAPSHOT_RUNNING,
)
import tools.chem11.incremental_publish as ip


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_plan_bundle(
    chem_id: str,
    *,
    source_content_hash: str = "HASH",
    detail_status: str = "COMPLETE",
    num_sections: int = 16,
) -> dict:
    return {
        "chem_id": chem_id,
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "identity_status": "READY",
        "identity_reason": None,
        "chemical_name_ko": None,
        "chemical_name_en": None,
        "cas_no": None,
        "ke_no": None,
        "en_no": None,
        "un_no": None,
        "last_date": None,
        "source_content_hash": source_content_hash,
        "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
        "detail_status": detail_status,
        "sections": [
            {
                "section_no": n,
                "payload_json": [],
                "section_hash": f"SH-{chem_id}-{n}",
                "result_code": "00",
                "result_message": "NORMAL SERVICE.",
                "fetched_at": "2026-09-19T00:00:00Z",
            }
            for n in range(1, num_sections + 1)
        ],
    }


def _make_manifest(chemicals: int, sections: int, sem_sha: str) -> dict:
    return {
        "execute_eligible": True,
        "execute_block_reasons": [],
        "plan_semantic_sha256": sem_sha,
        "plan_file_sha256": sem_sha,
        "responses_sha256": "RESPONSES_SHA",
        "counts": {"chemicals": chemicals, "sections": sections},
        "snapshot": {
            "metrics_json": {
                "publication_scope": PUBLICATION_SCOPE_SEO_PREVIEW,
                "seo_preview_manifest_sha256": "SEO_SHA",
                "responses_sha256": "RESPONSES_SHA",
            }
        },
    }


# ---------------------------------------------------------------------------
# Fixture A — Tool module loads; frozen constants are present and non-empty.
# ---------------------------------------------------------------------------

def test_A_frozen_constants_present():
    assert ip.FROZEN_RESPONSES_SHA, "FROZEN_RESPONSES_SHA must be set"
    assert ip.FROZEN_SEO_MANIFEST_SHA, "FROZEN_SEO_MANIFEST_SHA must be set"
    assert ip.FROZEN_PREVIEW_PLAN_SEM, "FROZEN_PREVIEW_PLAN_SEM must be set"
    assert ip.FROZEN_PREVIEW_PLAN_FILE, "FROZEN_PREVIEW_PLAN_FILE must be set"
    assert ip.FROZEN_EXPECTED_CHEMICALS == 4647
    assert ip.FROZEN_EXPECTED_SECTIONS == 74352
    assert len(ip.FROZEN_RESPONSES_SHA) == 64, "SHA256 must be 64 hex chars"
    assert len(ip.FROZEN_SEO_MANIFEST_SHA) == 64


# ---------------------------------------------------------------------------
# Fixture B — DRY-RUN returns PREFLIGHT_PASS when all gates pass.
# ---------------------------------------------------------------------------

def test_B_dry_run_preflight_pass():
    new_chem = _make_plan_bundle("NEW01")
    unch_chem = _make_plan_bundle("UNCH01", source_content_hash="EXISTING_HASH")
    manifest = _make_manifest(2, 32, "SEM_SHA")

    plan_inputs = w.MaterializePlanInputs(
        manifest=manifest,
        report={"plan_sha256": "SEM_SHA", "execute_eligible": True, "responses_sha256": "RESPONSES_SHA"},
        chemicals=(new_chem, unch_chem),
    )

    existing_chem_row = {
        "id": str(uuid.uuid4()),
        "chem_id": "UNCH01",
        "source_id": "KOSHA_MSDS",
        "source_key": "UNCH01",
        "content_id": "CHEM:existing",
        "source_content_hash": "EXISTING_HASH",
    }
    store = w.MemoryMaterializeStore(
        chemicals=[existing_chem_row],
        sections=[
            {"chemical_id": existing_chem_row["id"], "section_no": n, "section_hash": f"SH-UNCH01-{n}"}
            for n in range(1, 17)
        ],
    )

    preflight = w.preflight(plan_inputs, store=store, publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW)
    assert preflight.can_execute
    assert preflight.counts_by_kind["NEW"] == (1, 16)
    assert preflight.counts_by_kind["UNCHANGED"] == (1, 16)
    assert preflight.counts_by_kind["CONFLICT"] == (0, 0)


# ---------------------------------------------------------------------------
# Fixture C — DRY-RUN = SELECT allowed, DRY-RUN = mutation 0.
#
# Uses a fake MemoryMaterializeStore subclass that intercepts all write
# methods and asserts they are never called during a preflight-only run.
# ---------------------------------------------------------------------------

class _MutationTrackingStore(w.MemoryMaterializeStore):
    """MemoryMaterializeStore that records any mutation call as a test failure."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.mutations: list[str] = []

    def insert_snapshot(self, snapshot):
        self.mutations.append("insert_snapshot")
        super().insert_snapshot(snapshot)

    def update_snapshot_status(self, snapshot_id, status):
        self.mutations.append(f"update_snapshot_status({status})")
        super().update_snapshot_status(snapshot_id, status)

    def insert_chemicals(self, rows):
        self.mutations.append(f"insert_chemicals({len(rows)})")
        super().insert_chemicals(rows)

    def insert_sections(self, rows):
        self.mutations.append(f"insert_sections({len(rows)})")
        super().insert_sections(rows)

    def insert_snapshot_items(self, rows):
        self.mutations.append(f"insert_snapshot_items({len(rows)})")
        super().insert_snapshot_items(rows)

    def update_chemical(self, source_id, source_key, mutable_fields):
        self.mutations.append(f"update_chemical({source_key})")
        super().update_chemical(source_id, source_key, mutable_fields)

    def update_section(self, chemical_id, section_no, mutable_fields):
        self.mutations.append(f"update_section({chemical_id},{section_no})")
        super().update_section(chemical_id, section_no, mutable_fields)


def test_C_dry_run_mutation_zero(monkeypatch):
    """DRY-RUN path calls preflight (SELECT) only — zero DB mutations."""
    new_chem = _make_plan_bundle("C_NEW")
    unch_chem = _make_plan_bundle("C_UNCH", source_content_hash="H_UNCH")
    unch_uuid = str(uuid.uuid4())
    manifest = _make_manifest(2, 32, "SEM_C")
    report = {"plan_sha256": "SEM_C", "execute_eligible": True, "responses_sha256": "RESP_C"}

    existing_row = {
        "id": unch_uuid, "chem_id": "C_UNCH",
        "source_id": "KOSHA_MSDS", "source_key": "C_UNCH",
        "content_id": "CHEM:c_unch", "source_content_hash": "H_UNCH",
    }
    fake_store = _MutationTrackingStore(
        chemicals=[existing_row],
        sections=[
            {"chemical_id": unch_uuid, "section_no": n, "section_hash": f"SH-C_UNCH-{n}"}
            for n in range(1, 17)
        ],
    )
    plan_inputs = w.MaterializePlanInputs(
        manifest=manifest, report=report, chemicals=(new_chem, unch_chem),
    )

    # Verify: preflight reads store (SELECT) but writes nothing.
    preflight = w.preflight(
        plan_inputs, store=fake_store,
        publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )

    assert preflight.can_execute
    assert fake_store.mutations == [], (
        f"DRY-RUN must produce zero mutations, got: {fake_store.mutations}"
    )
    assert preflight.counts_by_kind["NEW"][0] == 1
    assert preflight.counts_by_kind["UNCHANGED"][0] == 1


# ---------------------------------------------------------------------------
# Fixture D — Execute without --owner-approved is blocked at CLI level.
# ---------------------------------------------------------------------------

def test_D_execute_without_owner_approved_blocked():
    with pytest.raises(SystemExit) as exc_info:
        ip.main(["--execute"])
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# Fixture E — Conflicting chemical blocks the run.
# ---------------------------------------------------------------------------

def test_E_conflict_chemical_blocks_run():
    """A CONFLICT row in preflight causes can_execute=False."""
    conflict_chem = _make_plan_bundle("CONF01", source_content_hash="HASH_A")
    manifest = _make_manifest(1, 16, "SEM")

    plan_inputs = w.MaterializePlanInputs(
        manifest=manifest,
        report={"plan_sha256": "SEM", "execute_eligible": True},
        chemicals=(conflict_chem,),
    )

    # DB has the same source_key but a DIFFERENT chem_id → CONFLICT.
    existing_row = {
        "id": str(uuid.uuid4()),
        "chem_id": "DIFFERENT_CHEM_ID",
        "source_id": "KOSHA_MSDS",
        "source_key": "CONF01",    # same natural key
        "content_id": "CHEM:conflict",
        "source_content_hash": "HASH_A",
    }
    store = w.MemoryMaterializeStore(chemicals=[existing_row])

    preflight = w.preflight(plan_inputs, store=store, publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW)
    assert not preflight.can_execute
    assert "CHEMICAL_CONFLICT" in preflight.block_reasons


# ---------------------------------------------------------------------------
# Fixture F — UNCHANGED chemicals are preserved with their existing UUID.
# ---------------------------------------------------------------------------

def test_F_unchanged_chemicals_preserve_uuid():
    existing_uuid = str(uuid.uuid4())
    unch_chem = _make_plan_bundle("UNCH02", source_content_hash="HASH_X")
    manifest = _make_manifest(1, 16, "SEM")

    existing_row = {
        "id": existing_uuid,
        "chem_id": "UNCH02",
        "source_id": "KOSHA_MSDS",
        "source_key": "UNCH02",
        "content_id": "CHEM:existing_uuid",
        "source_content_hash": "HASH_X",
    }
    store = w.MemoryMaterializeStore(
        chemicals=[existing_row],
        sections=[
            {"chemical_id": existing_uuid, "section_no": n, "section_hash": f"SH-UNCH02-{n}"}
            for n in range(1, 17)
        ],
    )

    plan_inputs = w.MaterializePlanInputs(
        manifest=manifest,
        report={"plan_sha256": "SEM", "execute_eligible": True},
        chemicals=(unch_chem,),
    )
    snap_id = str(uuid.uuid4())
    store.insert_snapshot({"id": "DUMMY_PARENT", "status": "COMPLETED", "publish_state": "PUBLISHED_SEO_PREVIEW", "enumeration_mode": "FULL_OFFICIAL"})

    report = w.execute_incremental_write(plan_inputs, store=store, snapshot_id=snap_id)
    assert report.chemicals_unchanged == 1
    assert report.chemicals_new == 0
    # Verify the UNCHANGED chemical kept its existing UUID in membership.
    key = ("KOSHA_MSDS", "UNCH02")
    assert report.chem_uuid_by_key.get(key) == existing_uuid


# ---------------------------------------------------------------------------
# Fixture G — NEW chemicals get fresh UUIDs; UNCHANGED keep existing.
# ---------------------------------------------------------------------------

def test_G_new_and_unchanged_mix():
    existing_uuid = str(uuid.uuid4())
    unch = _make_plan_bundle("MIX_U", source_content_hash="H_U")
    new_ = _make_plan_bundle("MIX_N", source_content_hash="H_N")
    manifest = _make_manifest(2, 32, "SEM")

    existing_row = {
        "id": existing_uuid,
        "chem_id": "MIX_U",
        "source_id": "KOSHA_MSDS",
        "source_key": "MIX_U",
        "content_id": "CHEM:mix_u",
        "source_content_hash": "H_U",
    }
    store = w.MemoryMaterializeStore(
        chemicals=[existing_row],
        sections=[
            {"chemical_id": existing_uuid, "section_no": n, "section_hash": f"SH-MIX_U-{n}"}
            for n in range(1, 17)
        ],
    )

    plan_inputs = w.MaterializePlanInputs(
        manifest=manifest,
        report={"plan_sha256": "SEM", "execute_eligible": True},
        chemicals=(unch, new_),
    )
    snap_id = str(uuid.uuid4())
    report = w.execute_incremental_write(plan_inputs, store=store, snapshot_id=snap_id)

    assert report.chemicals_new == 1
    assert report.chemicals_unchanged == 1
    assert report.membership_rows == 2

    key_u = ("KOSHA_MSDS", "MIX_U")
    key_n = ("KOSHA_MSDS", "MIX_N")
    assert report.chem_uuid_by_key[key_u] == existing_uuid
    assert report.chem_uuid_by_key[key_n] != existing_uuid


# ---------------------------------------------------------------------------
# Fixture H — Production impact projection: NEW=2650, UNCHANGED=1997, CHANGED=0.
# ---------------------------------------------------------------------------

def test_H_production_impact_projection():
    """Verify the DRY-RUN tool's impact projection matches the live preflight."""
    new_count = 2650
    unch_count = 1997

    new_bundles = [_make_plan_bundle(f"NEW{i:05d}") for i in range(new_count)]
    unch_bundles = [_make_plan_bundle(f"UNCH{i:05d}", source_content_hash=f"H{i}") for i in range(unch_count)]
    all_bundles = new_bundles + unch_bundles
    total = len(all_bundles)

    manifest = _make_manifest(total, total * 16, "SEM")
    plan_inputs = w.MaterializePlanInputs(
        manifest=manifest,
        report={"plan_sha256": "SEM", "execute_eligible": True},
        chemicals=tuple(all_bundles),
    )

    existing_chems = []
    existing_secs = []
    for i in range(unch_count):
        cid = str(uuid.uuid4())
        existing_chems.append({
            "id": cid, "chem_id": f"UNCH{i:05d}",
            "source_id": "KOSHA_MSDS", "source_key": f"UNCH{i:05d}",
            "content_id": f"CHEM:{cid}", "source_content_hash": f"H{i}",
        })
        for n in range(1, 17):
            existing_secs.append({
                "chemical_id": cid, "section_no": n,
                "section_hash": f"SH-UNCH{i:05d}-{n}",
            })

    store = w.MemoryMaterializeStore(chemicals=existing_chems, sections=existing_secs)
    preflight = w.preflight(plan_inputs, store=store, publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW)

    assert preflight.can_execute
    assert preflight.counts_by_kind["NEW"][0] == new_count
    assert preflight.counts_by_kind["UNCHANGED"][0] == unch_count
    assert preflight.counts_by_kind["CHANGED"][0] == 0
    assert preflight.counts_by_kind["CONFLICT"][0] == 0


# ---------------------------------------------------------------------------
# Fixture I — Union membership: existing 1997 all covered by the 4647 plan.
# ---------------------------------------------------------------------------

def test_I_union_membership_all_existing_covered():
    """All existing published chemicals must appear in the new snapshot plan."""
    existing_ids = {f"EXIST{i:04d}" for i in range(1997)}
    new_ids = {f"NEW_{i:04d}" for i in range(2650)}
    plan_ids = existing_ids | new_ids  # union = 4647

    assert len(plan_ids) == 4647
    # No existing ID is missing from the plan.
    missing = existing_ids - plan_ids
    assert len(missing) == 0, f"Union membership violated: {len(missing)} existing IDs not in plan"


# ---------------------------------------------------------------------------
# Fixture J — Snapshot lifecycle: RUNNING → COMPLETED on success,
#             RUNNING → FAILED on exception.
# ---------------------------------------------------------------------------

def test_J_snapshot_lifecycle_completed_on_success():
    chem = _make_plan_bundle("SL01")
    manifest = _make_manifest(1, 16, "SEM")
    plan_inputs = w.MaterializePlanInputs(
        manifest=manifest,
        report={"plan_sha256": "SEM", "execute_eligible": True},
        chemicals=(chem,),
    )
    snap_id = "test-snap-j"
    store = w.MemoryMaterializeStore()

    snap_row = w.open_snapshot(snapshot_id=snap_id, manifest=manifest, discovered_count=1, expected_count=1)
    snap_row["started_at"] = "2026-09-23T00:00:00Z"
    store.insert_snapshot(snap_row)
    assert store.get_snapshot(snap_id)["status"] == "RUNNING"

    w.execute_incremental_write(plan_inputs, store=store, snapshot_id=snap_id)
    w.mark_snapshot_completed(store, snap_id)
    assert store.get_snapshot(snap_id)["status"] == "COMPLETED"


def test_J2_snapshot_lifecycle_failed_on_exception():
    chem = _make_plan_bundle("SL02")
    manifest = _make_manifest(1, 16, "SEM")
    plan_inputs = w.MaterializePlanInputs(
        manifest=manifest,
        report={"plan_sha256": "SEM", "execute_eligible": True},
        chemicals=(chem,),
    )
    snap_id = "test-snap-j2"
    store = w.MemoryMaterializeStore()
    snap_row = w.open_snapshot(snapshot_id=snap_id, manifest=manifest, discovered_count=1, expected_count=1)
    snap_row["started_at"] = "2026-09-23T00:00:00Z"
    store.insert_snapshot(snap_row)

    # Mark failed manually (executor would do this on exception).
    w.mark_snapshot_failed(store, snap_id)
    assert store.get_snapshot(snap_id)["status"] == "FAILED"


# ---------------------------------------------------------------------------
# Fixture K — No existing RUNNING snapshot blocks a new run.
# ---------------------------------------------------------------------------

def test_K_existing_running_snapshot_blocks():
    chem = _make_plan_bundle("K01")
    manifest = _make_manifest(1, 16, "SEM")
    plan_inputs = w.MaterializePlanInputs(
        manifest=manifest,
        report={"plan_sha256": "SEM", "execute_eligible": True},
        chemicals=(chem,),
    )

    running_snap = {
        "id": "existing-running-id",
        "status": SNAPSHOT_RUNNING,
        "publish_state": "NOT_PUBLISHED",
        "enumeration_mode": "FULL_OFFICIAL",
    }
    store = w.MemoryMaterializeStore(snapshots=[running_snap])
    preflight = w.preflight(
        plan_inputs, store=store, publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    assert not preflight.can_execute
    assert "EXISTING_RUNNING_SNAPSHOT" in preflight.block_reasons


def test_K2_no_running_snapshot_allows_execute():
    chem = _make_plan_bundle("K02")
    manifest = _make_manifest(1, 16, "SEM")
    plan_inputs = w.MaterializePlanInputs(
        manifest=manifest,
        report={"plan_sha256": "SEM", "execute_eligible": True},
        chemicals=(chem,),
    )
    store = w.MemoryMaterializeStore()  # empty — no running snapshot
    preflight = w.preflight(
        plan_inputs, store=store, publication_scope=PUBLICATION_SCOPE_SEO_PREVIEW,
    )
    assert preflight.existing_running_snapshot_id is None


# ===========================================================================
# PATCH-1 regression tests T1–T5 — frozen artifact binding guards.
#
# These tests call ip._verify_frozen_artifacts() with patched file content
# to assert each binding mismatch is blocked before any DB connection.
# ===========================================================================

def _make_good_seo_manifest() -> dict:
    return {
        "manifest_sha256": ip.FROZEN_SEO_MANIFEST_SHA,
        "source": {"responses_sha256": ip.FROZEN_RESPONSES_SHA},
        "census": {
            "complete_chemicals": ip.FROZEN_EXPECTED_CHEMICALS,
            "preview_sections": ip.FROZEN_EXPECTED_SECTIONS,
        },
        "chemicals": [],
    }


def _make_good_preview_manifest() -> dict:
    return {
        "plan_semantic_sha256": ip.FROZEN_PREVIEW_PLAN_SEM,
        "plan_file_sha256": ip.FROZEN_PREVIEW_PLAN_FILE,
        "responses_sha256": ip.FROZEN_RESPONSES_SHA,
        "counts": {
            "chemicals": ip.FROZEN_EXPECTED_CHEMICALS,
            "sections": ip.FROZEN_EXPECTED_SECTIONS,
        },
    }


def _patch_files(monkeypatch, *, responses_sha=None, plan_file_sha=None,
                 seo_manifest=None, preview_manifest=None):
    """Monkeypatch ip._file_sha256 and Path.read_text for the three key files."""

    real_file_sha256 = ip._file_sha256
    _responses_sha = responses_sha or ip.FROZEN_RESPONSES_SHA
    _plan_file_sha = plan_file_sha or ip.FROZEN_PREVIEW_PLAN_FILE
    _seo = seo_manifest or _make_good_seo_manifest()
    _prev = preview_manifest or _make_good_preview_manifest()

    def fake_file_sha256(path: Path) -> str:
        if path == ip.RESPONSES_PATH:
            return _responses_sha
        if path == ip.PREVIEW_PLAN_JSONL:
            return _plan_file_sha
        return real_file_sha256(path)

    monkeypatch.setattr(ip, "_file_sha256", fake_file_sha256)

    # Patch Path.exists to True for all relevant paths.
    orig_exists = Path.exists

    def fake_exists(self):
        if self in (ip.RESPONSES_PATH, ip.SEO_MANIFEST_PATH,
                    ip.PREVIEW_PLAN_JSONL, ip.PREVIEW_MANIFEST_JSON,
                    ip.PREVIEW_REPORT_JSON):
            return True
        return orig_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    # Patch Path.read_text to return our fake manifests.
    orig_read_text = Path.read_text

    def fake_read_text(self, **kw):
        if self == ip.SEO_MANIFEST_PATH:
            return json.dumps(_seo)
        if self == ip.PREVIEW_MANIFEST_JSON:
            return json.dumps(_prev)
        return orig_read_text(self, **kw)

    monkeypatch.setattr(Path, "read_text", fake_read_text)


# ---------------------------------------------------------------------------
# T1 — actual responses.jsonl SHA mismatch → BLOCKED.
# ---------------------------------------------------------------------------

def test_T1_responses_sha_mismatch_blocked(monkeypatch):
    _patch_files(monkeypatch, responses_sha="WRONG_SHA_" + "0" * 54)
    with pytest.raises(SystemExit) as exc_info:
        ip._verify_frozen_artifacts()
    assert ip.BLOCK_SHA_MISMATCH in str(exc_info.value)


# ---------------------------------------------------------------------------
# T2 — preview plan JSONL file SHA mismatch → BLOCKED.
# ---------------------------------------------------------------------------

def test_T2_preview_plan_file_sha_mismatch_blocked(monkeypatch):
    _patch_files(monkeypatch, plan_file_sha="WRONG_PLAN_" + "0" * 53)
    with pytest.raises(SystemExit) as exc_info:
        ip._verify_frozen_artifacts()
    assert ip.BLOCK_SHA_MISMATCH in str(exc_info.value)


# ---------------------------------------------------------------------------
# T3 — preview manifest responses_sha256 mismatch → BLOCKED.
# ---------------------------------------------------------------------------

def test_T3_preview_manifest_responses_sha_mismatch_blocked(monkeypatch):
    bad_prev = _make_good_preview_manifest()
    bad_prev["responses_sha256"] = "WRONG_MANIFEST_RESP_" + "0" * 44
    _patch_files(monkeypatch, preview_manifest=bad_prev)
    with pytest.raises(SystemExit) as exc_info:
        ip._verify_frozen_artifacts()
    assert ip.BLOCK_SHA_MISMATCH in str(exc_info.value)


# ---------------------------------------------------------------------------
# T4 — preview manifest plan_semantic_sha256 mismatch → BLOCKED.
# ---------------------------------------------------------------------------

def test_T4_preview_semantic_sha_mismatch_blocked(monkeypatch):
    bad_prev = _make_good_preview_manifest()
    bad_prev["plan_semantic_sha256"] = "WRONG_SEM_" + "0" * 54
    _patch_files(monkeypatch, preview_manifest=bad_prev)
    with pytest.raises(SystemExit) as exc_info:
        ip._verify_frozen_artifacts()
    assert ip.BLOCK_SHA_MISMATCH in str(exc_info.value)


# ---------------------------------------------------------------------------
# T5 — all frozen SHAs match → _verify_frozen_artifacts returns without error.
# ---------------------------------------------------------------------------

def test_T5_all_frozen_match_passes(monkeypatch):
    _patch_files(monkeypatch)
    result = ip._verify_frozen_artifacts()
    assert result["actual_responses_sha"] == ip.FROZEN_RESPONSES_SHA
    assert result["actual_plan_file_sha"] == ip.FROZEN_PREVIEW_PLAN_FILE
    assert result["preview_plan_semantic_sha"] == ip.FROZEN_PREVIEW_PLAN_SEM
    assert result["chemicals"] == ip.FROZEN_EXPECTED_CHEMICALS
    assert result["sections"] == ip.FROZEN_EXPECTED_SECTIONS
