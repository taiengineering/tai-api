"""WO-CHEM-05 materialize adapter unit tests (Phase A).

Small synthetic fixtures only. No real KOSHA API. No real DB. No large
corpus scan. Tests verify §33 contract items 1-15.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from services.kosha_msds import materialize as m
from tools.chem05 import build_materialize_plan as planner
from tools.chem05 import materialize_official_v12 as cli


# ---------------------------------------------------------------------------
# Fixture helpers: synthesize hydration-runner-shaped response records.
# ---------------------------------------------------------------------------


def _make_record(
    chem_id: str,
    section_no: int,
    *,
    source: str = "KOSHA_OFFICIAL",
    source_contract_version: str = "KOSHA_MSDS_OPENAPI_V1_2",
    official_spec_version: str = "1.2",
    official_spec_date: str = "2026-09-16",
    authoritative_verified: bool = True,
    result_code: str = "00",
    items: list | None = None,
    fetched_at: str = "2026-09-18T00:00:00Z",
    result_msg: str = "NORMAL SERVICE.",
) -> dict:
    return {
        "chemId": chem_id,
        "sectionNo": section_no,
        "operation": f"getChemDetail{section_no:02d}1",
        "source": source,
        "source_contract_version": source_contract_version,
        "official_spec_version": official_spec_version,
        "official_spec_date": official_spec_date,
        "result_code": result_code,
        "result_msg": result_msg,
        "status": "OK",
        "items": items if items is not None else [
            {"msdsItemCode": f"S{section_no:02d}I1",
             "msdsItemNameKor": f"항목{section_no}",
             "itemDetail": "내용", "ordrIdx": "1", "lev": "1"},
        ],
        "fetched_at": fetched_at,
        "authoritative_verified": authoritative_verified,
    }


def _sixteen_full(chem_id: str) -> list[dict]:
    return [_make_record(chem_id, n) for n in range(1, 17)]


# ---------------------------------------------------------------------------
# WO §33 items 1..15
# ---------------------------------------------------------------------------


def test_01_chem_id_leading_zero_preserved():
    """Leading zeros on chemId must survive plan generation."""
    recs = _sixteen_full("001008")
    plan = m.build_plan(artifact_records=recs)
    assert len(plan.chemicals) == 1
    assert plan.chemicals[0].chem_id == "001008"
    assert plan.chemicals[0].source_key == "001008"


def test_02_invalid_source_contract_blocks():
    """A record whose source ≠ KOSHA_OFFICIAL is rejected; plan lists the failure."""
    good = _sixteen_full("001008")
    bad = _make_record("001008", 1, source="KOSHA_UNOFFICIAL")
    plan = m.build_plan(artifact_records=[bad] + good[1:])  # first record poisoned
    assert plan.counts["source_contract_failures"] >= 1
    assert m.BLOCK_SOURCE_CONTRACT_FAIL in plan.execute_block_reasons
    assert plan.execute_eligible is False


def test_03_authoritative_verified_false_blocks():
    """A record with authoritative_verified=false is rejected."""
    rec = _make_record("001008", 1, authoritative_verified=False)
    plan = m.build_plan(artifact_records=[rec])
    assert plan.counts["source_contract_failures"] == 1
    codes = {f.code for f in plan.contract_failures}
    assert "AUTHORITATIVE_VERIFIED_MISMATCH" in codes
    assert m.BLOCK_SOURCE_CONTRACT_FAIL in plan.execute_block_reasons


def test_04_duplicate_pair_blocks():
    """(chem_id, section_no) may only appear once in the corpus."""
    recs = _sixteen_full("001008") + [_make_record("001008", 5)]
    plan = m.build_plan(artifact_records=recs)
    assert plan.counts["duplicate_pairs"] == 1
    assert ("001008", 5) in plan.duplicate_pairs
    assert m.BLOCK_DUPLICATE_PAIRS in plan.execute_block_reasons


def test_05_missing_section_marks_incomplete():
    """A chemical missing any of the 16 sections is INCOMPLETE."""
    recs = [_make_record("001008", n) for n in range(1, 16)]  # 1..15 only
    plan = m.build_plan(artifact_records=recs)
    assert len(plan.chemicals) == 1
    assert plan.chemicals[0].detail_status == "INCOMPLETE"
    assert plan.counts["incomplete_chemicals"] == 1


def test_06_all_16_sections_marks_complete():
    """A chemical with all 16 authoritative sections is COMPLETE."""
    plan = m.build_plan(artifact_records=_sixteen_full("001008"))
    assert len(plan.chemicals) == 1
    assert plan.chemicals[0].detail_status == "COMPLETE"


def test_07_section_hash_deterministic():
    """Same section items -> same section_hash."""
    plan_a = m.build_plan(artifact_records=_sixteen_full("001008"))
    plan_b = m.build_plan(artifact_records=_sixteen_full("001008"))
    ha = {s.section_no: s.section_hash for s in plan_a.chemicals[0].sections}
    hb = {s.section_no: s.section_hash for s in plan_b.chemicals[0].sections}
    assert ha == hb


def test_08_source_content_hash_deterministic():
    """source_content_hash matches when input is identical, differs when items differ."""
    plan_a = m.build_plan(artifact_records=_sixteen_full("001008"))
    plan_b = m.build_plan(artifact_records=_sixteen_full("001008"))
    assert plan_a.chemicals[0].source_content_hash == plan_b.chemicals[0].source_content_hash

    # Different items -> different source_content_hash
    varied = _sixteen_full("001008")
    varied[0] = _make_record("001008", 1, items=[{
        "msdsItemCode": "S01I2", "msdsItemNameKor": "다른", "itemDetail": "차이",
        "ordrIdx": "1", "lev": "1",
    }])
    plan_c = m.build_plan(artifact_records=varied)
    assert plan_c.chemicals[0].source_content_hash != plan_a.chemicals[0].source_content_hash


def test_09_same_input_same_plan_sha():
    """Same records (any order) -> same plan_sha256."""
    recs_a = _sixteen_full("001008") + _sixteen_full("097377")
    # Reverse order shouldn't matter (build_plan sorts internally).
    recs_b = list(reversed(recs_a))
    plan_a = m.build_plan(artifact_records=recs_a)
    plan_b = m.build_plan(artifact_records=recs_b)
    assert plan_a.plan_sha256 == plan_b.plan_sha256


def test_10_partial_corpus_execute_ineligible():
    """Partial corpus (well below 20,568 chemicals) is NOT execute-eligible."""
    plan = m.build_plan(artifact_records=_sixteen_full("001008"))
    assert plan.execute_eligible is False
    assert m.BLOCK_FULL_OFFICIAL_CORPUS_INCOMPLETE in plan.execute_block_reasons


def test_11_execute_gate_blocks_before_db_mutation(tmp_path):
    """--execute exits non-zero and never opens any DB connection.

    We drive the CLI directly with a tiny synthetic responses.jsonl to
    prove that no DB code path is reached: even the --execute mode
    prints a JSON block and returns non-zero.
    """
    responses = tmp_path / "responses.jsonl"
    responses.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in _sixteen_full("001008")) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "chem05_out"
    rc = cli.main([
        "--execute",
        "--responses", str(responses),
        "--out-dir", str(out_dir),
        "--i-understand-full-corpus",
    ])
    assert rc == 2  # blocked, never touched DB
    # Manifest and plan artifacts must still exist (execute rebuilds the plan first).
    assert (out_dir / "materialize_plan.jsonl").exists()
    assert (out_dir / "materialize_manifest.json").exists()


def test_12_identical_input_marks_content_hash_stable():
    """When the same content is fed twice, source_content_hash is byte-stable.

    This is the "UNCHANGED" precondition: a DB-side row whose stored
    source_content_hash equals the plan's is a candidate for UNCHANGED
    classification. (The DB comparison itself is out of scope for this
    unit test, but the deterministic hash is prerequisite.)
    """
    plan_a = m.build_plan(artifact_records=_sixteen_full("001008"))
    plan_b = m.build_plan(artifact_records=_sixteen_full("001008"))
    assert plan_a.chemicals[0].source_content_hash \
        == plan_b.chemicals[0].source_content_hash


def test_13_identity_conflict_missing_chem_id_blocks():
    """A record with missing chemId is rejected by admission."""
    rec = _make_record("", 1)
    rec["chemId"] = None  # simulate a genuinely missing identity
    plan = m.build_plan(artifact_records=[rec])
    codes = {f.code for f in plan.contract_failures}
    assert "MISSING_CHEM_ID" in codes
    assert m.BLOCK_SOURCE_CONTRACT_FAIL in plan.execute_block_reasons


def test_14_publish_full_never_emitted():
    """Adapter's snapshot candidate is always NOT_PUBLISHED; PUBLISHED_FULL is guarded."""
    plan = m.build_plan(artifact_records=_sixteen_full("001008"))
    assert plan.snapshot.publish_state == "NOT_PUBLISHED"
    # Assert the fail-closed guard rejects any manual override.
    plan.snapshot.publish_state = "PUBLISHED_FULL"
    with pytest.raises(ValueError):
        m.assert_no_publish_full(plan.snapshot)


def test_15_kosha_safety_materials_domain_not_referenced():
    """The adapter must not import from services.kosha_safety_materials.

    That is a different KOSHA domain (safety documents / educational
    assets), not MSDS chemicals. Cross-domain coupling would defeat
    WO §32.
    """
    for module in (m, planner, cli):
        # imports check: no attribute named kosha_safety_materials in the module dict
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "kosha_safety_materials" not in source, \
            f"{module.__file__} imports the kosha_safety_materials domain"


# ---------------------------------------------------------------------------
# Extra: end-to-end dry-run against a tiny synthetic responses.jsonl
# ---------------------------------------------------------------------------


def test_e2e_dry_run_writes_plan_manifest_report(tmp_path):
    responses = tmp_path / "responses.jsonl"
    recs = _sixteen_full("001008") + _sixteen_full("097377")
    responses.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "chem05_out"
    rc = cli.main([
        "--dry-run",
        "--responses", str(responses),
        "--out-dir", str(out_dir),
    ])
    assert rc == 0

    plan_lines = (out_dir / "materialize_plan.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(plan_lines) == 2

    manifest = json.loads((out_dir / "materialize_manifest.json").read_text(encoding="utf-8"))
    report = json.loads((out_dir / "materialize_report.json").read_text(encoding="utf-8"))
    assert manifest["snapshot"]["expected_count"] == m.FULL_OFFICIAL_CHEMICAL_COUNT
    assert manifest["snapshot"]["discovered_count"] == 2
    assert manifest["execute_eligible"] is False
    assert m.BLOCK_FULL_OFFICIAL_CORPUS_INCOMPLETE in manifest["execute_block_reasons"]
    # Report matches manifest on the shared fields.
    assert report["plan_sha256"] == manifest["plan_semantic_sha256"]
    assert report["responses_sha256"] == manifest["responses_sha256"]
    # metrics_json carries the provenance the DB has no columns for.
    metrics = manifest["snapshot"]["metrics_json"]
    assert metrics["official_spec_version"] == "1.2"
    assert metrics["official_spec_date"] == "2026-09-16"
    assert metrics["adapter_version"] == "CHEM05_V1"
    assert metrics["artifact_responses_sha256"] == manifest["responses_sha256"]


def test_e2e_census_supplements_identity(tmp_path):
    responses = tmp_path / "responses.jsonl"
    recs = _sixteen_full("001008")
    responses.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
        encoding="utf-8",
    )
    census = tmp_path / "census.jsonl"
    census.write_text(
        json.dumps({
            "chem_id": "001008",
            "chemical_name_ko": "벤젠",
            "chemical_name_en": "Benzene",
            "cas_no": "71-43-2",
            "last_date": "2024-01-15",
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "chem05_out"
    rc = cli.main([
        "--dry-run",
        "--responses", str(responses),
        "--census", str(census),
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    plan_json = json.loads(
        (out_dir / "materialize_plan.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert plan_json["chemical_name_ko"] == "벤젠"
    assert plan_json["chemical_name_en"] == "Benzene"
    assert plan_json["cas_no"] == "71-43-2"
    assert plan_json["last_date"] == "2024-01-15"
