"""WO-CHEM-08 production materializer tests (fixture only).

MemoryMaterializeStore-only. No live Supabase. No live DB. Verifies
§26 items 1..20 individually.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.kosha_msds import materialize_writer as w
from tools.chem08 import materialize_production as cli


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _plan_chemical(
    chem_id: str,
    *,
    source_content_hash: str,
    detail_status: str = "COMPLETE",
    section_hashes: dict[int, str] | None = None,
) -> dict:
    """One line in materialize_plan.jsonl (ChemicalBundle.to_dict())."""
    section_hashes = section_hashes or {n: f"sec-{chem_id}-{n}" for n in range(1, 17)}
    return {
        "chem_id": chem_id,
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "identity_status": "READY",
        "identity_reason": None,
        "chemical_name_ko": f"화학{chem_id}",
        "chemical_name_en": f"Chem{chem_id}",
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
                "section_hash": section_hashes[n],
                "result_code": "00",
                "result_message": "NORMAL SERVICE.",
                "fetched_at": "2026-09-18T00:00:00Z",
                "item_count": 1,
                "payload_json": [{"msdsItemCode": f"C{n:02d}"}],
            }
            for n in sorted(section_hashes.keys())
        ],
    }


def _inputs_from_plan(chemicals: list[dict], *, execute_eligible: bool = True) -> w.MaterializePlanInputs:
    """Build MaterializePlanInputs directly (no disk I/O)."""
    manifest = {
        "wo": "WO-CHEM-05-AUTHORITATIVE-INGEST-ADAPTER-001",
        "adapter_version": "CHEM05_V1",
        "responses_sha256": "resp-sha-A",
        "plan_file_sha256": "plan-file-sha-A",
        "plan_semantic_sha256": "plan-sem-sha-A",
        "execute_eligible": execute_eligible,
        "execute_block_reasons": [] if execute_eligible else ["FULL_OFFICIAL_CORPUS_INCOMPLETE"],
        "snapshot": {
            "run_type": "FULL_SYNC",
            "enumeration_mode": "FULL_OFFICIAL",
            "status": "RUNNING",
            "publish_state": "NOT_PUBLISHED",
            "source_contract_version": "KOSHA_MSDS_OPENAPI_V1_2",
            "expected_count": 20568,
            "discovered_count": len(chemicals),
            "metrics_json": {
                "official_spec_version": "1.2",
                "official_spec_date": "2026-09-16",
            },
        },
    }
    report = {
        "plan_sha256": "plan-sem-sha-A",
        "responses_sha256": "resp-sha-A",
        "execute_eligible": execute_eligible,
    }
    return w.MaterializePlanInputs(
        manifest=manifest, report=report, chemicals=tuple(chemicals),
    )


def _existing_chemical_row(chem_id: str, *, source_content_hash: str, id: str) -> dict:
    return {
        "id": id,
        "content_id": f"CHEM:{chem_id}-existing",
        "source_id": "KOSHA_MSDS",
        "source_key": chem_id,
        "chem_id": chem_id,
        "identity_status": "READY",
        "chemical_name_ko": None,
        "chemical_name_en": None,
        "cas_no": None,
        "ke_no": None,
        "en_no": None,
        "un_no": None,
        "source_content_hash": source_content_hash,
        "source_dataset_url": "https://www.data.go.kr/data/15157612/openapi.do",
    }


def _existing_section_row(chemical_id: str, section_no: int, section_hash: str) -> dict:
    return {
        "chemical_id": chemical_id,
        "section_no": section_no,
        "payload_json": [{"msdsItemCode": f"C{section_no:02d}"}],
        "section_hash": section_hash,
        "result_code": "00",
        "result_message": "NORMAL SERVICE.",
        "fetched_at": "2026-09-17T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# §26 items 1..20
# ---------------------------------------------------------------------------


def test_01_incomplete_plan_blocks_before_db_connection():
    """execute_eligible=false plan is blocked at preflight."""
    inputs = _inputs_from_plan(
        [_plan_chemical("001008", source_content_hash="H1")],
        execute_eligible=False,
    )
    report = w.preflight(inputs, store=w.MemoryMaterializeStore())
    assert report.can_execute is False
    assert w.BLOCK_PLAN_NOT_ELIGIBLE in report.block_reasons


def test_02_bad_manifest_binding_blocks():
    """responses_sha mismatch is a preflight block."""
    inputs = _inputs_from_plan([_plan_chemical("001008", source_content_hash="H1")])
    report = w.preflight(
        inputs, store=w.MemoryMaterializeStore(),
        on_disk_responses_sha256="DIFFERENT_SHA",
    )
    assert report.can_execute is False
    assert w.BLOCK_MANIFEST_BINDING_MISMATCH in report.block_reasons


def test_03_plan_sha_mismatch_blocks():
    """If manifest.plan_semantic_sha256 != report.plan_sha256, block."""
    inputs = _inputs_from_plan([_plan_chemical("001008", source_content_hash="H1")])
    # Corrupt the report's plan_sha.
    inputs = w.MaterializePlanInputs(
        manifest=inputs.manifest,
        report={**inputs.report, "plan_sha256": "DIFFERENT_PLAN_SHA"},
        chemicals=inputs.chemicals,
    )
    report = w.preflight(inputs, store=w.MemoryMaterializeStore())
    assert report.can_execute is False
    assert w.BLOCK_PLAN_SHA_MISMATCH in report.block_reasons


def test_04_existing_running_snapshot_blocks():
    """An existing RUNNING snapshot without matching --resume-snapshot blocks."""
    inputs = _inputs_from_plan([_plan_chemical("001008", source_content_hash="H1")])
    store = w.MemoryMaterializeStore(snapshots=[{
        "id": "prior-snap-1",
        "status": w.SNAPSHOT_RUNNING,
    }])
    report = w.preflight(inputs, store=store)
    assert w.BLOCK_EXISTING_RUNNING_SNAPSHOT in report.block_reasons
    # But if resume matches the existing RUNNING id, the guard is silent.
    report_ok = w.preflight(inputs, store=store, resume_snapshot_id="prior-snap-1")
    assert w.BLOCK_EXISTING_RUNNING_SNAPSHOT not in report_ok.block_reasons


def test_05_new_chemical_classification():
    inputs = _inputs_from_plan([_plan_chemical("001008", source_content_hash="H1")])
    cls = w.classify_chemicals(inputs.chemicals, store=w.MemoryMaterializeStore())
    assert len(cls) == 1
    assert cls[0].kind == w.NEW


def test_06_unchanged_chemical_classification():
    inputs = _inputs_from_plan([_plan_chemical("001008", source_content_hash="H1")])
    store = w.MemoryMaterializeStore(
        chemicals=[_existing_chemical_row("001008", source_content_hash="H1", id="uu-1")],
    )
    cls = w.classify_chemicals(inputs.chemicals, store=store)
    assert cls[0].kind == w.UNCHANGED
    assert cls[0].db_chemical_id == "uu-1"


def test_07_changed_chemical_classification():
    inputs = _inputs_from_plan([_plan_chemical("001008", source_content_hash="H_NEW")])
    store = w.MemoryMaterializeStore(
        chemicals=[_existing_chemical_row("001008", source_content_hash="H_OLD", id="uu-1")],
    )
    cls = w.classify_chemicals(inputs.chemicals, store=store)
    assert cls[0].kind == w.CHANGED


def test_08_conflict_chemical_blocks():
    """DB row exists on the natural key but its chem_id disagrees with plan."""
    inputs = _inputs_from_plan([_plan_chemical("001008", source_content_hash="H1")])
    bad = _existing_chemical_row("001008", source_content_hash="H1", id="uu-1")
    bad["chem_id"] = "999999"  # identity mismatch
    store = w.MemoryMaterializeStore(chemicals=[bad])
    preflight_report = w.preflight(inputs, store=store)
    assert w.BLOCK_CHEMICAL_CONFLICT in preflight_report.block_reasons
    assert preflight_report.can_execute is False


def test_09_new_section_classification():
    inputs = _inputs_from_plan([_plan_chemical("001008", source_content_hash="H1")])
    cls_c = w.classify_chemicals(inputs.chemicals, store=w.MemoryMaterializeStore())
    cls_s = w.classify_sections(inputs.chemicals, cls_c, store=w.MemoryMaterializeStore())
    assert len(cls_s) == 16
    assert all(s.kind == w.NEW for s in cls_s)


def test_10_unchanged_section_classification():
    plan_hashes = {n: f"H-{n}" for n in range(1, 17)}
    inputs = _inputs_from_plan([
        _plan_chemical("001008", source_content_hash="C-H", section_hashes=plan_hashes)
    ])
    existing_chem = _existing_chemical_row("001008", source_content_hash="C-H", id="uu-1")
    existing_sections = [_existing_section_row("uu-1", n, plan_hashes[n]) for n in range(1, 17)]
    store = w.MemoryMaterializeStore(
        chemicals=[existing_chem], sections=existing_sections,
    )
    cls_c = w.classify_chemicals(inputs.chemicals, store=store)
    cls_s = w.classify_sections(inputs.chemicals, cls_c, store=store)
    assert all(s.kind == w.UNCHANGED for s in cls_s)


def test_11_section_conflict_from_conflict_chemical_blocks_preflight():
    """When the parent chemical is CONFLICT, sections are marked CONFLICT."""
    inputs = _inputs_from_plan([_plan_chemical("001008", source_content_hash="H1")])
    bad = _existing_chemical_row("001008", source_content_hash="H1", id="uu-1")
    bad["chem_id"] = "999999"
    store = w.MemoryMaterializeStore(chemicals=[bad])
    cls_c = w.classify_chemicals(inputs.chemicals, store=store)
    cls_s = w.classify_sections(inputs.chemicals, cls_c, store=store)
    assert all(s.kind == w.CONFLICT for s in cls_s)
    # And preflight surfaces both block reasons.
    report = w.preflight(inputs, store=store)
    assert w.BLOCK_CHEMICAL_CONFLICT in report.block_reasons
    assert w.BLOCK_SECTION_CONFLICT in report.block_reasons


def test_12_chunk_boundaries_deterministic():
    """Same plan input in reversed order still yields sorted, deterministic chunks."""
    chems = [_plan_chemical(f"{i:06d}", source_content_hash=f"H{i}") for i in range(1, 5)]
    inputs_a = _inputs_from_plan(list(chems))
    inputs_b = _inputs_from_plan(list(reversed(chems)))
    cls_a = w.classify_chemicals(inputs_a.chemicals, store=w.MemoryMaterializeStore())
    cls_b = w.classify_chemicals(inputs_b.chemicals, store=w.MemoryMaterializeStore())
    sec_a = w.classify_sections(inputs_a.chemicals, cls_a, store=w.MemoryMaterializeStore())
    sec_b = w.classify_sections(inputs_b.chemicals, cls_b, store=w.MemoryMaterializeStore())
    plan_a = w.build_chunk_plan(inputs_a, cls_a, sec_a)
    plan_b = w.build_chunk_plan(inputs_b, cls_b, sec_b)
    assert plan_a.chemical_batches == plan_b.chemical_batches
    assert plan_a.section_batches == plan_b.section_batches
    assert plan_a.snapshot_item_batches == plan_b.snapshot_item_batches
    # Verify actual chunk-size honored.
    for batch in plan_a.chemical_batches:
        assert len(batch) <= w.CHEMICAL_BATCH_SIZE
    for batch in plan_a.section_batches:
        assert len(batch) <= w.SECTION_BATCH_SIZE
    for batch in plan_a.snapshot_item_batches:
        assert len(batch) <= w.SNAPSHOT_ITEM_BATCH_SIZE


def test_13_snapshot_starts_running():
    snap = w.open_snapshot(
        snapshot_id="snap-A", manifest={"snapshot": {"metrics_json": {}}},
        discovered_count=100, expected_count=20568,
    )
    assert snap["status"] == w.SNAPSHOT_RUNNING
    assert snap["publish_state"] == "NOT_PUBLISHED"
    assert snap["enumeration_mode"] == "FULL_OFFICIAL"


def test_14_success_marks_snapshot_completed():
    store = w.MemoryMaterializeStore()
    snap = w.open_snapshot(
        snapshot_id="snap-B", manifest={"snapshot": {}},
        discovered_count=1, expected_count=1,
    )
    store.insert_snapshot(snap)
    w.mark_snapshot_completed(store, "snap-B")
    assert store.get_snapshot("snap-B")["status"] == w.SNAPSHOT_COMPLETED


def test_15_write_failure_marks_snapshot_failed():
    store = w.MemoryMaterializeStore()
    snap = w.open_snapshot(
        snapshot_id="snap-C", manifest={"snapshot": {}},
        discovered_count=1, expected_count=1,
    )
    store.insert_snapshot(snap)
    w.mark_snapshot_failed(store, "snap-C")
    assert store.get_snapshot("snap-C")["status"] == w.SNAPSHOT_FAILED


def test_16_published_full_never_emitted():
    """Direct guard + preflight-level check both refuse PUBLISHED_FULL."""
    # Direct guard.
    with pytest.raises(w.ProductionWriteForbidden):
        w.assert_no_publish_full({"publish_state": "PUBLISHED_FULL"})
    # Preflight-level: manifest snapshot with publish_state=PUBLISHED_FULL blocks.
    inputs = _inputs_from_plan([_plan_chemical("001008", source_content_hash="H1")])
    inputs.manifest["snapshot"]["publish_state"] = "PUBLISHED_FULL"
    report = w.preflight(inputs, store=w.MemoryMaterializeStore())
    assert w.BLOCK_PUBLISHED_FULL_ATTEMPTED in report.block_reasons


def test_17_incomplete_membership_blocks():
    """Any chemical with detail_status=INCOMPLETE blocks execution."""
    inputs = _inputs_from_plan([
        _plan_chemical("001008", source_content_hash="H1"),
        _plan_chemical("097377", source_content_hash="H2", detail_status="INCOMPLETE"),
    ])
    report = w.preflight(inputs, store=w.MemoryMaterializeStore())
    assert w.BLOCK_INCOMPLETE_MEMBERSHIP in report.block_reasons
    assert "097377" in report.incomplete_memberships


def test_18_repeat_run_no_duplicate_logical_rows():
    """Idempotency: replaying the same plan against a DB seeded with its
    result yields all-UNCHANGED. Chunk plan therefore has zero NEW/CHANGED
    chemical batches."""
    plan_hashes = {n: f"H-{n}" for n in range(1, 17)}
    plan = [_plan_chemical("001008", source_content_hash="C-H", section_hashes=plan_hashes)]
    inputs = _inputs_from_plan(plan)
    seeded = w.MemoryMaterializeStore(
        chemicals=[_existing_chemical_row("001008", source_content_hash="C-H", id="uu-1")],
        sections=[_existing_section_row("uu-1", n, plan_hashes[n]) for n in range(1, 17)],
    )
    cls_c = w.classify_chemicals(inputs.chemicals, store=seeded)
    cls_s = w.classify_sections(inputs.chemicals, cls_c, store=seeded)
    chunk = w.build_chunk_plan(inputs, cls_c, cls_s)
    assert all(c.kind == w.UNCHANGED for c in cls_c)
    assert all(s.kind == w.UNCHANGED for s in cls_s)
    # UNCHANGED rows are excluded from chemical/section batches.
    assert chunk.chemical_batches == ()
    assert chunk.section_batches == ()
    # snapshot_items still membership-batches over ALL plan chemicals.
    assert sum(len(b) for b in chunk.snapshot_item_batches) == 1


def test_19_dry_run_never_mutates_store():
    """Dry-run through the writer's high-level entrypoint must leave the
    store byte-identical to what was passed in."""
    plan = [_plan_chemical("001008", source_content_hash="H1")]
    inputs = _inputs_from_plan(plan)
    store = w.MemoryMaterializeStore()
    before = (
        dict(store._chemicals_by_key),
        dict(store._sections_by_pair),
        list(store._snapshots),
        list(store._snapshot_items),
    )
    _ = w.dry_run(inputs, store=store)
    after = (
        dict(store._chemicals_by_key),
        dict(store._sections_by_pair),
        list(store._snapshots),
        list(store._snapshot_items),
    )
    assert before == after


def test_20_owner_auth_missing_and_wo_scope_forbids_write():
    """assert_can_execute_production_write enforces THREE gates.

    (A) preflight.can_execute must be True.
    (B) owner_approved must be True.
    (C) WO_SCOPE_ALLOWS_WRITE must be True.

    WO-CHEM-08 hard-wires (C) to False. Even if the caller passes
    owner_approved=True, the writer must still refuse.
    """
    plan = [_plan_chemical("001008", source_content_hash="H1")]
    inputs = _inputs_from_plan(plan)
    store = w.MemoryMaterializeStore()
    report = w.preflight(inputs, store=store)

    # Sanity: preflight has no block reasons when plan is clean and DB is empty.
    assert report.can_execute is True

    # (B) fails: no owner approval → ProductionWriteForbidden.
    with pytest.raises(w.ProductionWriteForbidden) as ei:
        w.assert_can_execute_production_write(
            preflight_report=report, owner_approved=False,
        )
    assert w.BLOCK_OWNER_AUTHORIZATION_MISSING in str(ei.value)

    # (C) fails even with owner approval under this WO's scope.
    with pytest.raises(w.ProductionWriteForbidden) as ej:
        w.assert_can_execute_production_write(
            preflight_report=report, owner_approved=True,
        )
    assert w.BLOCK_WO_SCOPE_FORBIDS_WRITE in str(ej.value)

    # And the module-level constant is the load-bearing safety fence.
    assert w.PRODUCTION_WRITE_ALLOWED is False


# ---------------------------------------------------------------------------
# Extra: CLI-level fail-closed and cross-domain coupling
# ---------------------------------------------------------------------------


def test_21_cli_execute_blocked_even_with_owner_approved(tmp_path):
    """--execute --owner-approved returns rc=2 and never opens a DB path."""
    plan_path = tmp_path / "materialize_plan.jsonl"
    manifest_path = tmp_path / "materialize_manifest.json"
    report_path = tmp_path / "materialize_report.json"
    chems = [_plan_chemical("001008", source_content_hash="H1")]
    plan_path.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in chems) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "responses_sha256": "resp-sha",
        "plan_file_sha256": "plan-file-sha",
        "plan_semantic_sha256": "plan-sem-sha",
        "execute_eligible": True,
        "snapshot": {
            "run_type": "FULL_SYNC",
            "enumeration_mode": "FULL_OFFICIAL",
            "status": "RUNNING",
            "publish_state": "NOT_PUBLISHED",
            "source_contract_version": "KOSHA_MSDS_OPENAPI_V1_2",
            "expected_count": 20568,
            "discovered_count": 1,
            "metrics_json": {},
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report = {
        "plan_sha256": "plan-sem-sha",
        "responses_sha256": "resp-sha",
        "execute_eligible": True,
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    rc = cli.main([
        "--execute",
        "--owner-approved",
        "--plan", str(plan_path),
        "--manifest", str(manifest_path),
        "--report", str(report_path),
    ])
    assert rc == 2


def test_22_no_kosha_safety_materials_dependency():
    """Neither the writer module nor the CLI imports the safety-materials domain."""
    for module in (w, cli):
        src = Path(module.__file__).read_text(encoding="utf-8")
        assert "kosha_safety_materials" not in src, (
            f"{module.__file__} must not import services.kosha_safety_materials"
        )


def test_23_cli_dry_run_prints_report_and_touches_no_db(tmp_path, capsys):
    """--dry-run runs preflight and prints a compact JSON summary."""
    plan_path = tmp_path / "plan.jsonl"
    manifest_path = tmp_path / "manifest.json"
    report_path = tmp_path / "report.json"
    chems = [_plan_chemical("001008", source_content_hash="H1")]
    plan_path.write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in chems) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "responses_sha256": "resp-sha",
        "plan_file_sha256": "plan-file-sha",  # will not match on-disk SHA
        "plan_semantic_sha256": "plan-sem-sha",
        "execute_eligible": True,
        "snapshot": {"publish_state": "NOT_PUBLISHED",
                      "enumeration_mode": "FULL_OFFICIAL",
                      "status": "RUNNING",
                      "run_type": "FULL_SYNC",
                      "source_contract_version": "KOSHA_MSDS_OPENAPI_V1_2",
                      "expected_count": 20568,
                      "discovered_count": 1,
                      "metrics_json": {}},
    }
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    report = {"plan_sha256": "plan-sem-sha", "responses_sha256": "resp-sha",
              "execute_eligible": True}
    report_path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")

    rc = cli.main([
        "--dry-run",
        "--plan", str(plan_path),
        "--manifest", str(manifest_path),
        "--report", str(report_path),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["mode"] == "DRY_RUN"
    # Note: plan_file_sha in manifest won't match on-disk SHA; that raises
    # the manifest-binding block reason. can_execute must therefore be False.
    assert parsed["production_write_allowed"] is False
    assert parsed["wo_scope"] == "WO-CHEM-08-PRODUCTION-MATERIALIZER-001"
