"""WO-E2E300-PERSISTENCE-FREE-LEG-HARNESS-004 — H1-H20 contract tests.

Tests cover:
  H1-H3:   Sector dispatch (MFG/BLD/CST each calls correct seam)
  H4-H7:   Manifest/SHA/source_exact gates
  H8-H10:  None/false/zero field preservation in consumer_input
  H11-H13: Seam result passthrough / exception wrapping / empty obligations
  H14-H15: Finalize not imported / DB write fence
  H16-H17: diagnosis_id and inspection_sets absent from mainline engine_result
  H18-H19: CST site_id gate / ConstructionSiteBridgeError wrapping
  H20:     Summary deterministic
"""
import json
import sys
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# ── project root on path ─────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tools" / "e2e300"))

from run_leg_engine_matrix import (
    CASE_SHA,
    WriteBlockedSupabase,
    WriteBlockedTable,
    build_consumer_input,
    dispatch,
    load_manifest,
    run_case,
    write_case_result,
    write_summary,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_FULL_RESULT = {"obligations": [{"norm_id": "OSH-001", "level": "MANDATORY"}]}
_MOCK_LEG_RETURN = {
    "full_result":        _MOCK_FULL_RESULT,
    "contract_version":   "SAFE_INDUSTRIAL_LEG_V1",
    "unresolved_fields":  [],
}

def _mock_sb():
    sb = MagicMock()
    sb.table.return_value = MagicMock()
    return sb

def _mc(sector, factory_id="fid-test", site_id=None, source_exact=True):
    return {
        "case_id":      f"{sector[:3]}-001",
        "sector":       sector,
        "factory_id":   factory_id,
        "site_id":      site_id,
        "source_exact": source_exact,
    }

def _manifest(cases=None):
    return {
        "run_id":   "run-001",
        "case_sha": CASE_SHA,
        "cases":    cases or [_mc("MANUFACTURING")],
    }


# ─────────────────────────────────────────────────────────────────────────────
# H1 — MANUFACTURING dispatch calls run_safe_industrial_leg
# ─────────────────────────────────────────────────────────────────────────────

def test_h1_manufacturing_dispatch():
    """H1: sector=MANUFACTURING → _industrial_seam called with (sb, factory_id, consumer_input)."""
    called = {}
    def mock_industrial(sb, factory_id, consumer_input):
        called["factory_id"] = factory_id
        return dict(_MOCK_LEG_RETURN)

    from schemas.legal_engine import SafeIndustrialConsumerInput
    ci = SafeIndustrialConsumerInput()
    mc = _mc("MANUFACTURING", factory_id="fid-mfg")
    result = dispatch(_mock_sb(), mc, ci, _industrial_seam=mock_industrial)

    assert result["status"] == "OK"
    assert called["factory_id"] == "fid-mfg"
    assert "full_result" in result


# ─────────────────────────────────────────────────────────────────────────────
# H2 — BUILDING dispatch calls run_safe_building_leg
# ─────────────────────────────────────────────────────────────────────────────

def test_h2_building_dispatch():
    """H2: sector=BUILDING → _building_seam called with (sb, factory_id, consumer_input)."""
    called = {}
    def mock_building(sb, factory_id, consumer_input):
        called["factory_id"] = factory_id
        return {"full_result": {}, "contract_version": "SAFE_BUILDING_LEG_V1", "unresolved_fields": []}

    from schemas.legal_engine import SafeBuildingConsumerInput
    ci = SafeBuildingConsumerInput()
    mc = _mc("BUILDING", factory_id="fid-bld")
    result = dispatch(_mock_sb(), mc, ci, _building_seam=mock_building)

    assert result["status"] == "OK"
    assert called["factory_id"] == "fid-bld"


# ─────────────────────────────────────────────────────────────────────────────
# H3 — CONSTRUCTION dispatch calls run_safe_construction_leg
# ─────────────────────────────────────────────────────────────────────────────

def test_h3_construction_dispatch_with_site_id():
    """H3: sector=CONSTRUCTION with site_id → _construction_seam called with (sb, site_id, consumer_input)."""
    called = {}
    def mock_construction(sb, site_id, consumer_input):
        called["site_id"] = site_id
        return {"full_result": {}, "contract_version": "SAFE_CST_V1", "unresolved_fields": [], "factory_id": "fid-x"}

    from schemas.legal_engine import SafeConstructionConsumerInput
    ci = SafeConstructionConsumerInput()
    mc = _mc("CONSTRUCTION", factory_id="fid-cst", site_id="sid-cst")
    result = dispatch(_mock_sb(), mc, ci, _construction_seam=mock_construction)

    assert result["status"] == "OK"
    assert called["site_id"] == "sid-cst"


# ─────────────────────────────────────────────────────────────────────────────
# H4 — Manifest case_sha mismatch raises ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_h4_manifest_sha_mismatch(tmp_path):
    """H4: manifest with wrong case_sha → load_manifest raises ValueError."""
    bad = {"run_id": "r1", "case_sha": "deadbeef", "cases": []}
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="MANIFEST_CASE_SHA_MISMATCH"):
        load_manifest(str(p))


# ─────────────────────────────────────────────────────────────────────────────
# H5 — Missing provision_manifest.json raises FileNotFoundError
# ─────────────────────────────────────────────────────────────────────────────

def test_h5_manifest_file_not_found(tmp_path):
    """H5: provision_manifest.json absent → load_manifest raises FileNotFoundError."""
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        load_manifest(str(missing))


# ─────────────────────────────────────────────────────────────────────────────
# H6 — source_exact=False → SKIPPED
# ─────────────────────────────────────────────────────────────────────────────

def test_h6_source_not_exact_skipped():
    """H6: source_exact=False → run_case returns SKIPPED."""
    mc = _mc("MANUFACTURING", source_exact=False)
    result = run_case(_mock_sb(), mc, {})
    assert result["status"] == "SKIPPED"
    assert result["reason"] == "SOURCE_NOT_EXACT"


# ─────────────────────────────────────────────────────────────────────────────
# H7 — source_exact=True proceeds to dispatch
# ─────────────────────────────────────────────────────────────────────────────

def test_h7_source_exact_true_proceeds():
    """H7: source_exact=True → run_case calls seam and returns OK."""
    def mock_industrial(sb, factory_id, consumer_input):
        return dict(_MOCK_LEG_RETURN)

    mc = _mc("MANUFACTURING", source_exact=True)
    result = run_case(_mock_sb(), mc, {}, _industrial_seam=mock_industrial)
    assert result["status"] == "OK"


# ─────────────────────────────────────────────────────────────────────────────
# H8 — None field in consumer_input → excluded from override dict
# ─────────────────────────────────────────────────────────────────────────────

def test_h8_none_field_excluded_from_override():
    """H8: SafeIndustrialConsumerInput(worker_count=None) → exclude_none=True omits worker_count."""
    from schemas.legal_engine import SafeIndustrialConsumerInput
    ci = SafeIndustrialConsumerInput(worker_count=None)
    overrides = ci.model_dump(exclude_none=True)
    assert "worker_count" not in overrides


# ─────────────────────────────────────────────────────────────────────────────
# H9 — false field in consumer_input → NOT excluded (explicit override)
# ─────────────────────────────────────────────────────────────────────────────

def test_h9_false_field_preserved_as_override():
    """H9: SafeIndustrialConsumerInput(has_boiler=False) → override dict includes has_boiler=False."""
    from schemas.legal_engine import SafeIndustrialConsumerInput
    ci = SafeIndustrialConsumerInput(has_boiler=False)
    overrides = ci.model_dump(exclude_none=True)
    assert "has_boiler" in overrides
    assert overrides["has_boiler"] is False


# ─────────────────────────────────────────────────────────────────────────────
# H10 — 0 numeric field → NOT excluded (explicit override, distinct from None)
# ─────────────────────────────────────────────────────────────────────────────

def test_h10_zero_numeric_preserved_as_override():
    """H10: SafeIndustrialConsumerInput(worker_count=0) → override dict includes worker_count=0."""
    from schemas.legal_engine import SafeIndustrialConsumerInput
    ci = SafeIndustrialConsumerInput(worker_count=0)
    overrides = ci.model_dump(exclude_none=True)
    assert "worker_count" in overrides
    assert overrides["worker_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# H11 — LEG fallback in full_result → status still OK (harness doesn't inspect content)
# ─────────────────────────────────────────────────────────────────────────────

def test_h11_leg_fallback_still_ok():
    """H11: seam returns full_result with fallback marker → dispatch status=OK."""
    def mock_industrial(sb, factory_id, consumer_input):
        return {
            "full_result":       {"obligations": [], "_fallback": "OBLIGATIONS_FALLBACK"},
            "contract_version":  "V1",
            "unresolved_fields": [],
        }

    from schemas.legal_engine import SafeIndustrialConsumerInput
    ci = SafeIndustrialConsumerInput()
    mc = _mc("MANUFACTURING")
    result = dispatch(_mock_sb(), mc, ci, _industrial_seam=mock_industrial)
    assert result["status"] == "OK"
    assert "_fallback" in result["full_result"]


# ─────────────────────────────────────────────────────────────────────────────
# H12 — seam raises unexpected exception → ERROR result (not crash)
# ─────────────────────────────────────────────────────────────────────────────

def test_h12_seam_exception_wrapped_as_error():
    """H12: seam raises RuntimeError → run_case returns status=ERROR."""
    def mock_industrial(sb, factory_id, consumer_input):
        raise RuntimeError("network timeout")

    mc = _mc("MANUFACTURING")
    result = run_case(_mock_sb(), mc, {}, _industrial_seam=mock_industrial)
    assert result["status"] == "ERROR"
    assert "SEAM_ERROR" in result["reason"]
    assert "RuntimeError" in result["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# H13 — full_result with empty obligations → status=OK
# ─────────────────────────────────────────────────────────────────────────────

def test_h13_empty_obligations_ok():
    """H13: full_result with obligations=[] → status=OK (harness doesn't validate LEG quality)."""
    def mock_industrial(sb, factory_id, consumer_input):
        return {"full_result": {"obligations": []}, "contract_version": "V1", "unresolved_fields": []}

    from schemas.legal_engine import SafeIndustrialConsumerInput
    ci = SafeIndustrialConsumerInput()
    mc = _mc("MANUFACTURING")
    result = dispatch(_mock_sb(), mc, ci, _industrial_seam=mock_industrial)
    assert result["status"] == "OK"
    assert result["full_result"]["obligations"] == []


# ─────────────────────────────────────────────────────────────────────────────
# H14 — finalize/persist functions NOT imported in run_leg_engine_matrix
# ─────────────────────────────────────────────────────────────────────────────

def test_h14_finalize_not_imported():
    """H14: run_leg_engine_matrix must not import finalize/persist/materialize functions."""
    import run_leg_engine_matrix as harness_mod
    module_attrs = dir(harness_mod)
    forbidden = [
        "_finalize_saas_leg_http",
        "_persist_saas_leg",
        "_materialize_inspection_sets",
        "SaasLegCommonFinalizer",
        "apply_saas_v2_initial_payment_runtime",
    ]
    for name in forbidden:
        assert name not in module_attrs, (
            f"H14 FAIL: forbidden symbol {name!r} found in run_leg_engine_matrix namespace"
        )


# ─────────────────────────────────────────────────────────────────────────────
# H15 — DB write fence blocks .insert() on WriteBlockedSupabase
# ─────────────────────────────────────────────────────────────────────────────

def test_h15_db_write_fence_blocks_insert():
    """H15: WriteBlockedSupabase.table().insert() raises AssertionError."""
    inner = MagicMock()
    inner.table.return_value = MagicMock()
    wrapped = WriteBlockedSupabase(inner)

    table_proxy = wrapped.table("payments")
    assert isinstance(table_proxy, WriteBlockedTable)

    with pytest.raises(AssertionError, match="E2E300_ENGINE_MATRIX_DB_WRITE_BLOCKED"):
        table_proxy.insert({"id": "x"})


def test_h15b_db_write_fence_blocks_update():
    """H15b: WriteBlockedTable.update() also raises AssertionError."""
    inner = MagicMock()
    wrapped = WriteBlockedTable(inner)
    with pytest.raises(AssertionError, match="E2E300_ENGINE_MATRIX_DB_WRITE_BLOCKED"):
        wrapped.update({"status": "ACTIVE"})


def test_h15c_db_write_fence_allows_select():
    """H15c: WriteBlockedTable.select() proxies through (read allowed)."""
    inner = MagicMock()
    inner.select.return_value = MagicMock()
    wrapped = WriteBlockedTable(inner)
    result = wrapped.select("id, name")
    inner.select.assert_called_once_with("id, name")


# ─────────────────────────────────────────────────────────────────────────────
# H16 — diagnosis_id absent from mainline engine_result.json
# ─────────────────────────────────────────────────────────────────────────────

def test_h16_diagnosis_id_absent_from_engine_result(tmp_path):
    """H16: engine_result.json written by harness must NOT contain diagnosis_id."""
    def mock_industrial(sb, factory_id, consumer_input):
        return {"full_result": {}, "contract_version": "V1", "unresolved_fields": []}

    mc = _mc("MANUFACTURING")
    result = run_case(_mock_sb(), mc, {}, _industrial_seam=mock_industrial)
    write_case_result(str(tmp_path), mc["case_id"], result)

    saved = json.loads((tmp_path / "cases" / mc["case_id"] / "engine_result.json").read_text())
    assert "diagnosis_id" not in saved, (
        "H16 FAIL: diagnosis_id must not appear in engine_result.json (no C10 call in mainline)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# H17 — inspection_sets absent from mainline engine_result.json
# ─────────────────────────────────────────────────────────────────────────────

def test_h17_inspection_sets_absent_from_engine_result(tmp_path):
    """H17: engine_result.json must NOT contain inspection_sets key."""
    def mock_industrial(sb, factory_id, consumer_input):
        return {"full_result": {}, "contract_version": "V1", "unresolved_fields": []}

    mc = _mc("MANUFACTURING")
    result = run_case(_mock_sb(), mc, {}, _industrial_seam=mock_industrial)
    write_case_result(str(tmp_path), mc["case_id"], result)

    saved = json.loads((tmp_path / "cases" / mc["case_id"] / "engine_result.json").read_text())
    assert "inspection_sets" not in saved, (
        "H17 FAIL: inspection_sets must not appear in engine_result.json (no inspection write in mainline)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# H18 — CONSTRUCTION with site_id=None → BLOCKED: SITE_ID_REQUIRED_FOR_CONSTRUCTION
# ─────────────────────────────────────────────────────────────────────────────

def test_h18_construction_no_site_id_blocked():
    """H18: CONSTRUCTION with site_id=null in manifest → BLOCKED (not an error crash)."""
    from schemas.legal_engine import SafeConstructionConsumerInput
    ci = SafeConstructionConsumerInput()
    mc = _mc("CONSTRUCTION", factory_id="fid-x", site_id=None)
    result = dispatch(_mock_sb(), mc, ci)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "SITE_ID_REQUIRED_FOR_CONSTRUCTION"


# ─────────────────────────────────────────────────────────────────────────────
# H19 — CONSTRUCTION ConstructionSiteBridgeError → BLOCKED: CONSTRUCTION_SITE_BRIDGE_ERROR
# ─────────────────────────────────────────────────────────────────────────────

def test_h19_construction_bridge_error_blocked():
    """H19: run_safe_construction_leg raises ConstructionSiteBridgeError → BLOCKED."""
    from services.safe_construction_leg_runtime import ConstructionSiteBridgeError

    def mock_construction(sb, site_id, consumer_input):
        raise ConstructionSiteBridgeError("현장과 시설 연결이 완료되지 않았습니다.")

    from schemas.legal_engine import SafeConstructionConsumerInput
    ci = SafeConstructionConsumerInput()
    mc = _mc("CONSTRUCTION", factory_id="fid-x", site_id="sid-no-factory")
    result = dispatch(_mock_sb(), mc, ci, _construction_seam=mock_construction)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "CONSTRUCTION_SITE_BRIDGE_ERROR"
    assert "현장과 시설" in result.get("detail", "")


# ─────────────────────────────────────────────────────────────────────────────
# H20 — Summary output is deterministic for same input
# ─────────────────────────────────────────────────────────────────────────────

def test_h20_summary_deterministic(tmp_path):
    """H20: write_summary with same results list always produces identical JSON."""
    results = [
        {"case_id": "MFG-001", "sector": "MANUFACTURING", "status": "OK",      "reason": None},
        {"case_id": "BLD-001", "sector": "BUILDING",      "status": "OK",      "reason": None},
        {"case_id": "CST-001", "sector": "CONSTRUCTION",  "status": "BLOCKED", "reason": "SITE_ID_REQUIRED_FOR_CONSTRUCTION"},
    ]

    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    s1 = write_summary(str(out1), results)
    s2 = write_summary(str(out2), results)

    j1 = (out1 / "engine_matrix_summary.json").read_text()
    j2 = (out2 / "engine_matrix_summary.json").read_text()
    assert j1 == j2, "H20 FAIL: summary not deterministic"

    assert s1["total"]   == 3
    assert s1["ok"]      == 2
    assert s1["blocked"] == 1
    assert s1["all_ok"]  is False
