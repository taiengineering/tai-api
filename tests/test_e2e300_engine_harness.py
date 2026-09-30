"""WO-E2E300-LEG-HARNESS-CONTRACT-PATCH-004B — H1-H31 contract tests.

Tests cover:
  H1-H3:   Sector dispatch (MFG/BLD/CST each calls correct seam)
  H4-H7:   Manifest/SHA/source_exact/identity gates
  H8-H10:  None/false/zero field preservation in consumer_input
  H11:     fallback_used=True → run_case FAIL
  H12:     Seam exception wrapping; H12b INTERNAL_ERROR leg_status → FAIL
  H13a/b:  obligations_raw non-list → FAIL; empty list + count=0 → OK
  H14:     Finalize not imported / DB write fence (WriteBlockedBuilder)
  H15/b/c: WriteBlockedBuilder insert/update blocked, select allowed
  H16-H17: diagnosis_id and inspection_sets absent from engine_result.json
  H18-H19: CST site_id gate / ConstructionSiteBridgeError wrapping
  H20:     Summary deterministic (execution_pass / all_pass fields)
  H21:     Case file SHA from actual bytes mismatch → ValueError
  H22:     Case not in frozen universe → BLOCKED
  H23a/b/c: MFG false/false/false binding; BLD/CST empty overrides
  H24-H28: validate_engine_result contract (valid, fallback, system-error, list, count)
  H29:     WriteBlockedBuilder chain: select().update() blocked
  H30:     WriteBlockedSupabase.rpc() blocked
  H31:     Read chain .select().eq().execute() passes through
"""
import hashlib
import json
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# ── project root on path ─────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tools" / "e2e300"))

from run_leg_engine_matrix import (
    CASE_SHA,
    WriteBlockedBuilder,
    WriteBlockedSupabase,
    _check_cases_selected,
    build_consumer_input,
    build_frozen_consumer_overrides,
    dispatch,
    load_case_universe,
    load_manifest,
    run_case,
    validate_engine_result,
    write_case_result,
    write_execution_verdict,
    write_summary,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

# Valid full_result satisfying the full LEG contract
_VALID_FULL_RESULT = {
    "engine_family":    "LEG",
    "fallback_used":    False,
    "leg_status":       "LEG_COMPLETE",
    "leg_trace_id":     "trace-test-001",
    "obligations_raw":  [],
    "applicable_count": 0,
}
_VALID_LEG_RETURN = {
    "full_result":       _VALID_FULL_RESULT,
    "contract_version":  "SAFE_INDUSTRIAL_LEG_V1",
    "unresolved_fields": [],
}

# Legacy dispatch-only mock (not validated by run_case contract)
_MOCK_FULL_RESULT = {"obligations": [{"norm_id": "OSH-001", "level": "MANDATORY"}]}
_MOCK_LEG_RETURN = {
    "full_result":       _MOCK_FULL_RESULT,
    "contract_version":  "SAFE_INDUSTRIAL_LEG_V1",
    "unresolved_fields": [],
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


def _case_universe(mc, sector_fields=None):
    """Minimal frozen case_universe dict keyed by case_id."""
    return {
        mc["case_id"]: {
            "case_id":       mc["case_id"],
            "sector":        mc["sector"],
            "sector_fields": sector_fields or {},
        }
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
# H6 — source_exact=False → SKIPPED (before identity gate)
# ─────────────────────────────────────────────────────────────────────────────

def test_h6_source_not_exact_skipped():
    """H6: source_exact=False → run_case returns SKIPPED before identity gate."""
    mc = _mc("MANUFACTURING", source_exact=False)
    result = run_case(_mock_sb(), mc, {})
    assert result["status"] == "SKIPPED"
    assert result["reason"] == "SOURCE_NOT_EXACT"


# ─────────────────────────────────────────────────────────────────────────────
# H7 — source_exact=True proceeds to dispatch and passes validation
# ─────────────────────────────────────────────────────────────────────────────

def test_h7_source_exact_true_proceeds():
    """H7: source_exact=True with valid full_result → run_case status=OK."""
    def mock_industrial(sb, factory_id, consumer_input):
        return dict(_VALID_LEG_RETURN)

    mc = _mc("MANUFACTURING", source_exact=True)
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
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
# H11 — fallback_used=True in full_result → run_case FAIL
# ─────────────────────────────────────────────────────────────────────────────

def test_h11_fallback_used_true_fails():
    """H11: seam returns fallback_used=True → run_case status=FAIL with FALLBACK_USED_NOT_FALSE."""
    def mock_industrial(sb, factory_id, consumer_input):
        return {
            "full_result": {
                "engine_family":    "LEG",
                "fallback_used":    True,
                "leg_status":       "LEG_COMPLETE",
                "leg_trace_id":     "trace-001",
                "obligations_raw":  [],
                "applicable_count": 0,
            },
            "contract_version":  "SAFE_INDUSTRIAL_LEG_V1",
            "unresolved_fields": [],
        }

    mc = _mc("MANUFACTURING")
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
    assert result["status"] == "FAIL"
    assert any("FALLBACK_USED_NOT_FALSE" in str(e) for e in result.get("validation_errors", []))


# ─────────────────────────────────────────────────────────────────────────────
# H12 — seam raises unexpected exception → ERROR; H12b INTERNAL_ERROR → FAIL
# ─────────────────────────────────────────────────────────────────────────────

def test_h12_seam_exception_wrapped_as_error():
    """H12: seam raises RuntimeError → run_case returns status=ERROR."""
    def mock_industrial(sb, factory_id, consumer_input):
        raise RuntimeError("network timeout")

    mc = _mc("MANUFACTURING")
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
    assert result["status"] == "ERROR"
    assert "SEAM_ERROR" in result["reason"]
    assert "RuntimeError" in result["reason"]


def test_h12b_leg_status_internal_error_fails():
    """H12b: full_result.leg_status=INTERNAL_ERROR → run_case status=FAIL."""
    def mock_industrial(sb, factory_id, consumer_input):
        return {
            "full_result": {
                "engine_family":    "LEG",
                "fallback_used":    False,
                "leg_status":       "INTERNAL_ERROR",
                "leg_trace_id":     "trace-001",
                "obligations_raw":  [],
                "applicable_count": 0,
            },
            "contract_version":  "SAFE_INDUSTRIAL_LEG_V1",
            "unresolved_fields": [],
        }

    mc = _mc("MANUFACTURING")
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
    assert result["status"] == "FAIL"
    assert any("LEG_STATUS_SYSTEM_ERROR" in str(e) for e in result.get("validation_errors", []))


# ─────────────────────────────────────────────────────────────────────────────
# H13a/b — obligations_raw contract: non-list → FAIL; [] + count=0 → OK
# ─────────────────────────────────────────────────────────────────────────────

def test_h13a_obligations_raw_non_list_fails():
    """H13a: obligations_raw=None → run_case status=FAIL with OBLIGATIONS_RAW_NOT_LIST."""
    def mock_industrial(sb, factory_id, consumer_input):
        return {
            "full_result": {
                "engine_family":    "LEG",
                "fallback_used":    False,
                "leg_status":       "LEG_COMPLETE",
                "leg_trace_id":     "trace-001",
                "obligations_raw":  None,
                "applicable_count": 0,
            },
            "contract_version":  "SAFE_INDUSTRIAL_LEG_V1",
            "unresolved_fields": [],
        }

    mc = _mc("MANUFACTURING")
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
    assert result["status"] == "FAIL"
    assert any("OBLIGATIONS_RAW_NOT_LIST" in str(e) for e in result.get("validation_errors", []))


def test_h13b_empty_obligations_zero_count_passes():
    """H13b: obligations_raw=[], applicable_count=0 → shape OK → run_case status=OK."""
    def mock_industrial(sb, factory_id, consumer_input):
        return dict(_VALID_LEG_RETURN)

    mc = _mc("MANUFACTURING")
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
    assert result["status"] == "OK"
    ev = result.get("execution_validation", {})
    assert ev.get("obligations_raw_list") is True
    assert ev.get("applicable_count_exact") is True


# ─────────────────────────────────────────────────────────────────────────────
# H14 — finalize/persist functions NOT imported in run_leg_engine_matrix
# ─────────────────────────────────────────────────────────────────────────────

def test_h14_finalize_not_imported():
    """H14: run_leg_engine_matrix must not import finalize/persist/materialize functions."""
    import run_leg_engine_matrix as harness_mod
    forbidden = [
        "_finalize_saas_leg_http",
        "_persist_saas_leg",
        "_materialize_inspection_sets",
        "SaasLegCommonFinalizer",
        "apply_saas_v2_initial_payment_runtime",
    ]
    for name in forbidden:
        assert name not in dir(harness_mod), (
            f"H14 FAIL: forbidden symbol {name!r} found in run_leg_engine_matrix namespace"
        )


# ─────────────────────────────────────────────────────────────────────────────
# H15 — DB write fence: WriteBlockedBuilder blocks writes
# ─────────────────────────────────────────────────────────────────────────────

def test_h15_db_write_fence_blocks_insert():
    """H15: WriteBlockedSupabase.table().insert() raises AssertionError."""
    inner = MagicMock()
    inner.table.return_value = MagicMock()
    wrapped = WriteBlockedSupabase(inner)

    table_proxy = wrapped.table("payments")
    assert isinstance(table_proxy, WriteBlockedBuilder)

    with pytest.raises(AssertionError, match="E2E300_ENGINE_MATRIX_DB_WRITE_BLOCKED"):
        table_proxy.insert({"id": "x"})


def test_h15b_db_write_fence_blocks_update():
    """H15b: WriteBlockedBuilder.update() raises AssertionError."""
    inner = MagicMock()
    wrapped = WriteBlockedBuilder(inner)
    with pytest.raises(AssertionError, match="E2E300_ENGINE_MATRIX_DB_WRITE_BLOCKED"):
        wrapped.update({"status": "ACTIVE"})


def test_h15c_db_write_fence_allows_select():
    """H15c: WriteBlockedBuilder.select() proxies through to inner (read allowed)."""
    inner = MagicMock()
    inner.select.return_value = "NOT_A_BUILDER"
    wrapped = WriteBlockedBuilder(inner)
    wrapped.select("id, name")
    inner.select.assert_called_once_with("id, name")


# ─────────────────────────────────────────────────────────────────────────────
# H16 — diagnosis_id absent from mainline engine_result.json
# ─────────────────────────────────────────────────────────────────────────────

def test_h16_diagnosis_id_absent_from_engine_result(tmp_path):
    """H16: engine_result.json written by harness must NOT contain diagnosis_id."""
    def mock_industrial(sb, factory_id, consumer_input):
        return dict(_VALID_LEG_RETURN)

    mc = _mc("MANUFACTURING")
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
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
        return dict(_VALID_LEG_RETURN)

    mc = _mc("MANUFACTURING")
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
    write_case_result(str(tmp_path), mc["case_id"], result)

    saved = json.loads((tmp_path / "cases" / mc["case_id"] / "engine_result.json").read_text())
    assert "inspection_sets" not in saved, (
        "H17 FAIL: inspection_sets must not appear in engine_result.json (no inspection write in mainline)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# H18 — CONSTRUCTION with site_id=None → BLOCKED: SITE_ID_REQUIRED_FOR_CONSTRUCTION
# ─────────────────────────────────────────────────────────────────────────────

def test_h18_construction_no_site_id_blocked():
    """H18: CONSTRUCTION with site_id=null in manifest → BLOCKED (not a crash)."""
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
# H20 — Summary output is deterministic; correct field names
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

    assert s1["total"]          == 3
    assert s1["execution_pass"] == 2
    assert s1["blocked"]        == 1
    assert s1["all_pass"]       is False  # BLOCKED > 0 → all_pass=False


# ─────────────────────────────────────────────────────────────────────────────
# H21 — Case file SHA from actual bytes: mismatch → ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_h21_case_file_sha_actual_bytes_mismatch(tmp_path):
    """H21: load_case_universe with tampered file → CASE_FILE_SHA_MISMATCH from actual bytes."""
    tampered = {"cases": [{"case_id": "X-001", "sector": "MANUFACTURING"}]}
    p = tmp_path / "case_universe.json"
    p.write_bytes(json.dumps(tampered).encode("utf-8"))
    with pytest.raises(ValueError, match="CASE_FILE_SHA_MISMATCH"):
        load_case_universe(str(p))


# ─────────────────────────────────────────────────────────────────────────────
# H22 — Case not in frozen universe → BLOCKED:CASE_NOT_FOUND_IN_FROZEN_UNIVERSE
# ─────────────────────────────────────────────────────────────────────────────

def test_h22_case_not_in_frozen_universe_blocked():
    """H22: manifest references case_id absent from case_universe → BLOCKED."""
    mc = _mc("MANUFACTURING")
    wrong_universe = {
        "OTHER-001": {"case_id": "OTHER-001", "sector": "MANUFACTURING", "sector_fields": {}}
    }
    result = run_case(_mock_sb(), mc, wrong_universe)
    assert result["status"] == "BLOCKED"
    assert result["reason"] == "CASE_NOT_FOUND_IN_FROZEN_UNIVERSE"


# ─────────────────────────────────────────────────────────────────────────────
# H23a/b/c — MFG false binding; BLD/CST empty overrides (no invented aliases)
# ─────────────────────────────────────────────────────────────────────────────

def test_h23a_mfg_false_sector_fields_bound_explicitly():
    """H23a: sector_fields has_*=False → overrides include all three as False."""
    case_data = {
        "case_id": "MFG-001",
        "sector":  "MANUFACTURING",
        "sector_fields": {
            "has_high_pressure_gas":  False,
            "has_chemical_substance": False,
            "has_boiler":             False,
        },
    }
    overrides = build_frozen_consumer_overrides(case_data, "MANUFACTURING")
    assert overrides["has_high_pressure_gas"]  is False
    assert overrides["has_chemical_substance"] is False
    assert overrides["has_boiler"]             is False


def test_h23b_bld_sector_fields_empty_overrides():
    """H23b: BUILDING → build_frozen_consumer_overrides returns {} (no invented aliases)."""
    case_data = {
        "case_id": "BLD-001",
        "sector":  "BUILDING",
        "sector_fields": {"building_use_code": "OFFICE", "floor_area": 500},
    }
    overrides = build_frozen_consumer_overrides(case_data, "BUILDING")
    assert overrides == {}


def test_h23c_cst_sector_fields_empty_overrides():
    """H23c: CONSTRUCTION → build_frozen_consumer_overrides returns {}."""
    case_data = {
        "case_id": "CST-001",
        "sector":  "CONSTRUCTION",
        "sector_fields": {"construction_amount": 100_000_000},
    }
    overrides = build_frozen_consumer_overrides(case_data, "CONSTRUCTION")
    assert overrides == {}


# ─────────────────────────────────────────────────────────────────────────────
# H24 — validate_engine_result: fully-compliant result → valid=True
# ─────────────────────────────────────────────────────────────────────────────

def test_h24_validate_engine_result_valid():
    """H24: validate_engine_result with full LEG contract → valid=True, all fields set."""
    result = {
        "status": "OK",
        "full_result": {
            "engine_family":    "LEG",
            "fallback_used":    False,
            "leg_status":       "LEG_COMPLETE",
            "leg_trace_id":     "trace-001",
            "obligations_raw":  [{"norm_id": "N01"}],
            "applicable_count": 1,
        },
    }
    v = validate_engine_result(result, "MANUFACTURING")
    assert v["valid"] is True
    assert v["errors"] == []
    assert v["engine_family"]         == "LEG"
    assert v["fallback_used"]         is False
    assert v["leg_trace_id_present"]  is True
    assert v["obligations_raw_list"]  is True
    assert v["applicable_count_exact"] is True


# ─────────────────────────────────────────────────────────────────────────────
# H25 — validate_engine_result: fallback_used=True → invalid
# ─────────────────────────────────────────────────────────────────────────────

def test_h25_validate_fallback_used_true_invalid():
    """H25: validate_engine_result with fallback_used=True → valid=False, FALLBACK_USED_NOT_FALSE."""
    result = {
        "full_result": {
            "engine_family":    "LEG",
            "fallback_used":    True,
            "leg_status":       "LEG_COMPLETE",
            "leg_trace_id":     "trace-001",
            "obligations_raw":  [],
            "applicable_count": 0,
        },
    }
    v = validate_engine_result(result, "MANUFACTURING")
    assert v["valid"] is False
    assert any("FALLBACK_USED_NOT_FALSE" in e for e in v["errors"])


# ─────────────────────────────────────────────────────────────────────────────
# H26 — validate_engine_result: INTERNAL_ERROR leg_status → invalid
# ─────────────────────────────────────────────────────────────────────────────

def test_h26_validate_internal_error_leg_status_invalid():
    """H26: validate_engine_result with leg_status=INTERNAL_ERROR → valid=False."""
    result = {
        "full_result": {
            "engine_family":    "LEG",
            "fallback_used":    False,
            "leg_status":       "INTERNAL_ERROR",
            "leg_trace_id":     "trace-001",
            "obligations_raw":  [],
            "applicable_count": 0,
        },
    }
    v = validate_engine_result(result, "MANUFACTURING")
    assert v["valid"] is False
    assert any("LEG_STATUS_SYSTEM_ERROR" in e for e in v["errors"])


# ─────────────────────────────────────────────────────────────────────────────
# H27 — validate_engine_result: obligations_raw not a list → invalid
# ─────────────────────────────────────────────────────────────────────────────

def test_h27_validate_obligations_raw_not_list_invalid():
    """H27: validate_engine_result with obligations_raw=dict → valid=False, OBLIGATIONS_RAW_NOT_LIST."""
    result = {
        "full_result": {
            "engine_family":    "LEG",
            "fallback_used":    False,
            "leg_status":       "LEG_COMPLETE",
            "leg_trace_id":     "trace-001",
            "obligations_raw":  {"items": []},
            "applicable_count": 0,
        },
    }
    v = validate_engine_result(result, "MANUFACTURING")
    assert v["valid"] is False
    assert any("OBLIGATIONS_RAW_NOT_LIST" in e for e in v["errors"])


# ─────────────────────────────────────────────────────────────────────────────
# H28 — validate_engine_result: applicable_count mismatch → invalid
# ─────────────────────────────────────────────────────────────────────────────

def test_h28_validate_applicable_count_mismatch_invalid():
    """H28: applicable_count=5 but obligations_raw has 2 items → APPLICABLE_COUNT_MISMATCH."""
    result = {
        "full_result": {
            "engine_family":    "LEG",
            "fallback_used":    False,
            "leg_status":       "LEG_COMPLETE",
            "leg_trace_id":     "trace-001",
            "obligations_raw":  [{"norm_id": "A"}, {"norm_id": "B"}],
            "applicable_count": 5,
        },
    }
    v = validate_engine_result(result, "MANUFACTURING")
    assert v["valid"] is False
    assert any("APPLICABLE_COUNT_MISMATCH" in e for e in v["errors"])


# ─────────────────────────────────────────────────────────────────────────────
# H29 — WriteBlockedBuilder chain: .select().update() blocked at update
# ─────────────────────────────────────────────────────────────────────────────

def test_h29_write_blocked_builder_chain_select_update():
    """H29: WriteBlockedBuilder.select().update() is blocked at update (chain preserved)."""
    select_result = MagicMock(spec=["execute", "eq", "update", "limit"])
    inner_builder = MagicMock()
    inner_builder.select.return_value = select_result

    proxy = WriteBlockedBuilder(inner_builder)
    chained = proxy.select("*")
    assert isinstance(chained, WriteBlockedBuilder)

    with pytest.raises(AssertionError, match="E2E300_ENGINE_MATRIX_DB_WRITE_BLOCKED"):
        chained.update({"field": "value"})


# ─────────────────────────────────────────────────────────────────────────────
# H30 — WriteBlockedSupabase.rpc() → AssertionError
# ─────────────────────────────────────────────────────────────────────────────

def test_h30_rpc_blocked():
    """H30: WriteBlockedSupabase.rpc() raises AssertionError with RPC_BLOCKED message."""
    inner = MagicMock()
    wrapped = WriteBlockedSupabase(inner)
    with pytest.raises(AssertionError, match="E2E300_ENGINE_MATRIX_RPC_BLOCKED"):
        wrapped.rpc("some_function", {"arg": 1})


# ─────────────────────────────────────────────────────────────────────────────
# H31 — Read chain .select().eq().execute() passes through (not blocked)
# ─────────────────────────────────────────────────────────────────────────────

def test_h31_read_chain_passes():
    """H31: .table().select().eq().execute() read chain returns data without blocking."""
    execute_response = {"data": [{"id": "x"}], "error": None}

    eq_obj = MagicMock()
    eq_obj.execute.return_value = execute_response

    select_obj = MagicMock()
    select_obj.eq.return_value = eq_obj

    table_obj = MagicMock()
    table_obj.select.return_value = select_obj

    inner_sb = MagicMock()
    inner_sb.table.return_value = table_obj

    wrapped_sb = WriteBlockedSupabase(inner_sb)
    tbl = wrapped_sb.table("factories")
    sel = tbl.select("*")
    assert isinstance(sel, WriteBlockedBuilder)
    eq = sel.eq("id", "x")
    assert isinstance(eq, WriteBlockedBuilder)
    result = eq.execute()
    assert result == execute_response


# ─────────────────────────────────────────────────────────────────────────────
# G1 — blocked=1 → all_pass=False
# ─────────────────────────────────────────────────────────────────────────────

def test_g1_blocked_cases_not_all_pass(tmp_path):
    """G1: BLOCKED > 0 → all_pass=False even if no FAIL/ERROR."""
    results = [{"case_id": "MFG-001", "sector": "MANUFACTURING", "status": "BLOCKED", "reason": "SITE_ID_REQUIRED"}]
    s = write_summary(str(tmp_path), results)
    assert s["all_pass"] is False
    assert s["blocked"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# G2 — skipped=1 → all_pass=False
# ─────────────────────────────────────────────────────────────────────────────

def test_g2_skipped_cases_not_all_pass(tmp_path):
    """G2: SKIPPED > 0 → all_pass=False (source_exact=False cannot silently pass)."""
    results = [{"case_id": "MFG-001", "sector": "MANUFACTURING", "status": "SKIPPED", "reason": "SOURCE_NOT_EXACT"}]
    s = write_summary(str(tmp_path), results)
    assert s["all_pass"] is False
    assert s["skipped"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# G3 — total=0 → all_pass=False
# ─────────────────────────────────────────────────────────────────────────────

def test_g3_zero_total_not_all_pass(tmp_path):
    """G3: write_summary with empty results → all_pass=False (total=0 is not success)."""
    s = write_summary(str(tmp_path), [])
    assert s["all_pass"] is False
    assert s["total"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# G4 — OK 1/1 → all_pass=True
# ─────────────────────────────────────────────────────────────────────────────

def test_g4_all_ok_all_pass(tmp_path):
    """G4: single OK result with no FAIL/BLOCKED/SKIPPED/ERROR → all_pass=True."""
    results = [{"case_id": "MFG-001", "sector": "MANUFACTURING", "status": "OK", "reason": None}]
    s = write_summary(str(tmp_path), results)
    assert s["all_pass"] is True
    assert s["execution_pass"] == 1
    assert s["total"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# G5 — manifest sector != frozen sector → ERROR, LEG seam not called
# ─────────────────────────────────────────────────────────────────────────────

def test_g5_manifest_sector_mismatch_no_seam_call():
    """G5: manifest says BUILDING but frozen universe says MANUFACTURING → ERROR, seam=0 calls."""
    seam_called = {"count": 0}
    def mock_industrial(sb, factory_id, consumer_input):
        seam_called["count"] += 1
        return dict(_VALID_LEG_RETURN)

    mc = _mc("BUILDING", factory_id="fid-x")
    mc["case_id"] = "BLD-001"
    # Frozen universe says MANUFACTURING for this case_id
    universe = {"BLD-001": {"case_id": "BLD-001", "sector": "MANUFACTURING", "sector_fields": {}}}

    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
    assert result["status"] == "ERROR"
    assert "CASE_SECTOR_MISMATCH" in result["reason"]
    assert seam_called["count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# G6 — duplicate manifest case_id → load_manifest raises ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_g6_manifest_duplicate_case_id(tmp_path):
    """G6: provision_manifest.json with duplicate case_id → MANIFEST_DUPLICATE_CASE_ID."""
    manifest = {
        "run_id":   "run-001",
        "case_sha": CASE_SHA,
        "cases": [
            {"case_id": "MFG-001", "sector": "MANUFACTURING", "factory_id": "f1", "source_exact": True},
            {"case_id": "MFG-001", "sector": "MANUFACTURING", "factory_id": "f2", "source_exact": True},
        ],
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="MANIFEST_DUPLICATE_CASE_ID"):
        load_manifest(str(p))


# ─────────────────────────────────────────────────────────────────────────────
# G7 — zero cases selected → _check_cases_selected raises ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_g7_zero_cases_selected_raises():
    """G7: _check_cases_selected([]) raises ValueError with NO_CASES_SELECTED."""
    with pytest.raises(ValueError, match="NO_CASES_SELECTED"):
        _check_cases_selected([])


def test_g7b_nonzero_cases_selected_ok():
    """G7b: _check_cases_selected with 1 item does not raise."""
    _check_cases_selected([{"case_id": "MFG-001"}])


# ─────────────────────────────────────────────────────────────────────────────
# P21 — pipeline_c1_exact=false → SKIPPED (PIPELINE_C1_NOT_EXACT), LEG not called
# ─────────────────────────────────────────────────────────────────────────────

def test_p21_pipeline_c1_exact_false_skipped():
    """P21: manifest_case with pipeline_c1_exact=False → SKIPPED, seam not called."""
    seam_calls = {"n": 0}
    def mock_industrial(sb, fid, ci):
        seam_calls["n"] += 1
        return dict(_VALID_LEG_RETURN)

    mc = _mc("MANUFACTURING")
    mc["pipeline_c1_exact"] = False
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
    assert result["status"] == "SKIPPED"
    assert result["reason"] == "PIPELINE_C1_NOT_EXACT"
    assert seam_calls["n"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# P22 — pipeline_c1_exact=true → correct sector seam called
# ─────────────────────────────────────────────────────────────────────────────

def test_p22_pipeline_c1_exact_true_calls_correct_seam():
    """P22: pipeline_c1_exact=True → correct sector seam called and status=OK."""
    called = {}
    def mock_building(sb, factory_id, consumer_input):
        called["factory_id"] = factory_id
        return dict({
            "full_result": {
                "engine_family": "LEG", "fallback_used": False, "leg_status": "LEG_COMPLETE",
                "leg_trace_id": "trace-p22", "obligations_raw": [], "applicable_count": 0,
            },
            "contract_version": "SAFE_BUILDING_LEG_V1", "unresolved_fields": [],
        })

    mc = _mc("BUILDING", factory_id="fid-bld-p22")
    mc["pipeline_c1_exact"] = True
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _building_seam=mock_building)
    assert result["status"] == "OK"
    assert called["factory_id"] == "fid-bld-p22"


# ─────────────────────────────────────────────────────────────────────────────
# P23 — MFG C1→C8 mock pipeline (pipeline_c1_exact=true → LEG result valid → OK)
# ─────────────────────────────────────────────────────────────────────────────

def test_p23_mfg_c1_c8_mock_pipeline():
    """P23: MFG with pipeline_c1_exact=True + valid LEG result → status=OK, engine_family=LEG."""
    def mock_industrial(sb, factory_id, consumer_input):
        return dict(_VALID_LEG_RETURN)

    mc = _mc("MANUFACTURING")
    mc["pipeline_c1_exact"] = True
    universe = _case_universe(mc, sector_fields={
        "has_high_pressure_gas": False,
        "has_chemical_substance": False,
        "has_boiler": False,
    })
    result = run_case(_mock_sb(), mc, universe, _industrial_seam=mock_industrial)
    assert result["status"] == "OK"
    ev = result.get("execution_validation", {})
    assert ev.get("engine_family") == "LEG"
    assert ev.get("fallback_used") is False
    assert ev.get("valid") is True


# ─────────────────────────────────────────────────────────────────────────────
# P24 — BLD C1→C8 mock pipeline
# ─────────────────────────────────────────────────────────────────────────────

def test_p24_bld_c1_c8_mock_pipeline():
    """P24: BLD with pipeline_c1_exact=True + valid LEG result → status=OK."""
    def mock_building(sb, factory_id, consumer_input):
        return {
            "full_result": {
                "engine_family": "LEG", "fallback_used": False, "leg_status": "LEG_COMPLETE",
                "leg_trace_id": "trace-p24", "obligations_raw": [{"norm_id": "B01"}], "applicable_count": 1,
            },
            "contract_version": "SAFE_BUILDING_LEG_V1", "unresolved_fields": [],
        }

    mc = _mc("BUILDING")
    mc["pipeline_c1_exact"] = True
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _building_seam=mock_building)
    assert result["status"] == "OK"
    ev = result.get("execution_validation", {})
    assert ev.get("valid") is True
    assert ev.get("applicable_count_exact") is True


# ─────────────────────────────────────────────────────────────────────────────
# P25 — CST C1→C8 mock pipeline
# ─────────────────────────────────────────────────────────────────────────────

def test_p25_cst_c1_c8_mock_pipeline():
    """P25: CST with pipeline_c1_exact=True + site_id + valid LEG result → status=OK."""
    def mock_construction(sb, site_id, consumer_input):
        return {
            "full_result": {
                "engine_family": "LEG", "fallback_used": False, "leg_status": "LEG_COMPLETE",
                "leg_trace_id": "trace-p25", "obligations_raw": [], "applicable_count": 0,
            },
            "contract_version": "MKT_CST_PAID_CONTRACT_V1", "unresolved_fields": [],
            "factory_id": "fid-cst-p25",
        }

    mc = _mc("CONSTRUCTION", factory_id="fid-cst-p25", site_id="sid-cst-p25")
    mc["pipeline_c1_exact"] = True
    universe = _case_universe(mc)
    result = run_case(_mock_sb(), mc, universe, _construction_seam=mock_construction)
    assert result["status"] == "OK"
    ev = result.get("execution_validation", {})
    assert ev.get("valid") is True
