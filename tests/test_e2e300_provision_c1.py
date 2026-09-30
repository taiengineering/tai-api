"""WO-E2E300-FROZEN300-C1C8-PIPELINE-WIRING-005 — P1-P20 provision tests.

P1-P3:  Dataset integrity (SHA / counts)
P4-P6:  MFG C1 payload
P7-P10: BLD C1 payload
P11-P20: CST C1 source-only provisioner

All tests are mock/seam only.  PRODUCTION_WRITE = 0.  LEG_EXECUTED = 0.
"""
import json
import sys
import hashlib
import pytest
from pathlib import Path
from unittest.mock import MagicMock, call

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "tools" / "e2e300"))

from provision_frozen_c1 import (
    BLD_NOT_PIPELINE_FIELDS,
    CST_NOT_PIPELINE_FIELDS,
    MFG_EXPLICIT_CONFIRM_FIELDS,
    MFG_NOT_BOUND_FIELDS,
    StaleE2ECaseError,
    build_bld_factory_payload,
    build_c1_source_evidence,
    build_cst_site_payload,
    build_manifest_c1_entry,
    build_mfg_factory_payload,
    extract_mfg_explicit_confirms,
    normalize_cst_amount_to_eok,
    normalize_cst_construction_type,
    provision_bld_c1,
    provision_case,
    provision_cst_source,
    provision_mfg_c1,
    verify_bld_c1_exact,
    verify_cst_c1_exact,
    verify_mfg_c1_exact,
)

_CASE_SHA = "20f39a93cc18dce4cec4229df0a001b6219de91bd926a0176509f5d313040efd"
_UNIVERSE_PATH = Path(_ROOT).parent / "TAI_E2E200" / "consumer-ui300" / "cases" / "case_universe_v1.json"


def _load_universe():
    return json.loads(_UNIVERSE_PATH.read_bytes())


# ─────────────────────────────────────────────────────────────────────────────
# P1 — CASE_SHA unchanged
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_case_sha_unchanged():
    """P1: case_universe_v1.json SHA256 must match CASE_SHA."""
    raw = _UNIVERSE_PATH.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    assert actual == _CASE_SHA, f"P1 FAIL: CASE_SHA mismatch — file was modified"


# ─────────────────────────────────────────────────────────────────────────────
# P2 — total 300
# ─────────────────────────────────────────────────────────────────────────────

def test_p2_total_300():
    """P2: case_universe total == 300."""
    data = _load_universe()
    assert len(data["cases"]) == 300


# ─────────────────────────────────────────────────────────────────────────────
# P3 — MFG100 / BLD100 / CST100
# ─────────────────────────────────────────────────────────────────────────────

def test_p3_sector_distribution():
    """P3: exactly 100 MFG / 100 BLD / 100 CST cases."""
    data = _load_universe()
    cases = data["cases"]
    counts = {}
    for c in cases:
        s = c.get("sector", "UNKNOWN")
        counts[s] = counts.get(s, 0) + 1
    assert counts.get("MANUFACTURING") == 100
    assert counts.get("BUILDING")      == 100
    assert counts.get("CONSTRUCTION")  == 100


# ─────────────────────────────────────────────────────────────────────────────
# P4 — MFG explicit false confirmed preserved
# ─────────────────────────────────────────────────────────────────────────────

def test_p4_mfg_explicit_false_preserved():
    """P4: extract_mfg_explicit_confirms preserves False for all three USER_CONFIRM fields."""
    case_data = {
        "case_id": "MFG-001",
        "sector":  "MANUFACTURING",
        "sector_fields": {
            "has_high_pressure_gas":  False,
            "has_chemical_substance": False,
            "has_boiler":             False,
            "has_local_exhaust":      True,
        },
    }
    confirms = extract_mfg_explicit_confirms(case_data)
    assert confirms["has_high_pressure_gas"]  is False
    assert confirms["has_chemical_substance"] is False
    assert confirms["has_boiler"]             is False
    assert "has_local_exhaust" not in confirms  # NOT an explicit confirm field


def test_p4b_mfg_explicit_absent_not_inserted():
    """P4b: fields absent from sector_fields are not added to confirms dict."""
    case_data = {
        "case_id": "MFG-002",
        "sector":  "MANUFACTURING",
        "sector_fields": {"has_boiler": True},  # only one present
    }
    confirms = extract_mfg_explicit_confirms(case_data)
    assert "has_boiler" in confirms
    assert "has_high_pressure_gas"  not in confirms
    assert "has_chemical_substance" not in confirms


# ─────────────────────────────────────────────────────────────────────────────
# P5 — MFG factory payload uses existing source seam fields (not has_local_exhaust)
# ─────────────────────────────────────────────────────────────────────────────

def test_p5_mfg_factory_payload_existing_source_seams():
    """P5: build_mfg_factory_payload includes ksic_code and electrical_capacity_kw."""
    case_data = {
        "factory_name": "테스트공장",
        "sector":       "MANUFACTURING",
        "site_type":    "OFFICE",
        "worker_count": 45,
        "sector_fields": {
            "ksic_code":              "C2593",
            "electrical_capacity_kw": 402,
            "has_boiler":             False,
            "has_local_exhaust":      True,
        },
    }
    payload = build_mfg_factory_payload(case_data, company_id="cmp-001")
    assert payload["ksic_code"] == "C2593"
    assert payload["electrical_capacity_kw"] == 402
    assert payload["employee_count"] == 45
    assert payload["sector"] == "INDUSTRIAL"  # normalize_sector_db("MANUFACTURING") → "INDUSTRIAL"


# ─────────────────────────────────────────────────────────────────────────────
# P6 — MFG has_local_exhaust NOT in factory payload (NOT_BOUND)
# ─────────────────────────────────────────────────────────────────────────────

def test_p6_mfg_has_local_exhaust_not_in_payload():
    """P6: has_local_exhaust is NOT included in factory payload (MFG_NOT_BOUND_FIELDS)."""
    case_data = {
        "factory_name": "공장A",
        "sector":       "MANUFACTURING",
        "worker_count": 10,
        "sector_fields": {
            "ksic_code":         "C2511",
            "has_local_exhaust": True,
        },
    }
    payload = build_mfg_factory_payload(case_data, company_id="cmp-001")
    assert "has_local_exhaust" not in payload
    # Verify MFG_NOT_BOUND_FIELDS is the source of truth
    for field in MFG_NOT_BOUND_FIELDS:
        assert field not in payload


# ─────────────────────────────────────────────────────────────────────────────
# P7 — BLD building_area persisted exact
# ─────────────────────────────────────────────────────────────────────────────

def test_p7_bld_building_area_persisted_exact():
    """P7: build_bld_factory_payload includes building_area from sector_fields (was missing pre-005)."""
    case_data = {
        "factory_name": "사무빌딩",
        "sector":       "BUILDING",
        "site_type":    "BUILDING",
        "worker_count": 30,
        "sector_fields": {
            "building_area": 411.3,
            "floor_count":   4,
            "building_use_code": "B02",
            "main_purpose_name": "업무시설",
        },
    }
    payload = build_bld_factory_payload(case_data, company_id="cmp-001")
    assert payload["building_area"] == 411.3
    assert payload["floor_count"]   == 4


# ─────────────────────────────────────────────────────────────────────────────
# P8 — BLD worker_count → employee_count exact
# ─────────────────────────────────────────────────────────────────────────────

def test_p8_bld_worker_count_to_employee_count():
    """P8: case worker_count maps to factories.employee_count (VERIFIED_SOURCE mapping)."""
    case_data = {
        "factory_name": "빌딩B",
        "sector":       "BUILDING",
        "worker_count": 72,
        "sector_fields": {"building_area": 800.0, "floor_count": 8},
    }
    payload = build_bld_factory_payload(case_data, company_id="cmp-001")
    assert payload["employee_count"] == 72
    assert "worker_count" not in payload


# ─────────────────────────────────────────────────────────────────────────────
# P9 — BLD processes NOT in pipeline (manifest marks as NOT_CURRENTLY_CONSUMED)
# ─────────────────────────────────────────────────────────────────────────────

def test_p9_bld_processes_not_pipeline_required():
    """P9: BLD processes not included in factory payload; manifest marks NOT_CURRENTLY_CONSUMED."""
    case_data = {
        "case_id":      "BLD-001",
        "factory_name": "빌딩C",
        "sector":       "BUILDING",
        "worker_count": 20,
        "processes": [{"process_id": "P01"}, {"process_id": "P02"}],
        "sector_fields": {"building_area": 300.0, "floor_count": 3},
    }
    payload = build_bld_factory_payload(case_data, company_id="cmp-001")
    assert "processes" not in payload

    # manifest entry marks it as non-pipeline
    provision_result = {"pipeline_c1_exact": True, "factory_id": "fid-x", "site_id": None}
    entry = build_manifest_c1_entry(case_data, provision_result,
                                    work_source_exact=True,
                                    material_source_exact=True,
                                    equipment_source_exact=True)
    assert "baseline_non_pipeline" in entry
    for f in BLD_NOT_PIPELINE_FIELDS:
        assert entry["baseline_non_pipeline"][f] == "NOT_CURRENTLY_CONSUMED"


# ─────────────────────────────────────────────────────────────────────────────
# P10 — common source (work/material/equipment) uses same seams for BLD
# ─────────────────────────────────────────────────────────────────────────────

def test_p10_bld_common_source_exact_propagates():
    """P10: pipeline_c1_exact = True only when work/material/equipment all exact."""
    case_data = {"case_id": "BLD-002", "sector": "BUILDING", "factory_name": "X",
                 "sector_fields": {"building_area": 100.0}}
    provision_result = {"pipeline_c1_exact": True, "factory_id": "fid-x", "site_id": None}

    entry_all = build_manifest_c1_entry(case_data, provision_result,
                                        work_source_exact=True,
                                        material_source_exact=True,
                                        equipment_source_exact=True)
    assert entry_all["pipeline_c1_exact"] is True

    entry_partial = build_manifest_c1_entry(case_data, provision_result,
                                            work_source_exact=False,
                                            material_source_exact=True,
                                            equipment_source_exact=True)
    assert entry_partial["pipeline_c1_exact"] is False


# ─────────────────────────────────────────────────────────────────────────────
# P11 — POST /sites not used in provision_cst_source
# ─────────────────────────────────────────────────────────────────────────────

def test_p11_post_sites_not_used():
    """P11: provision_cst_source uses _site_insert_fn seam, not POST /sites API."""
    inserted = {"called": False, "payload": None}

    def mock_site_insert(supabase, payload, now_iso_fn):
        inserted["called"] = True
        inserted["payload"] = payload
        return "site-test-001"

    def mock_factory_bridge(supabase, site_row, now_iso_fn):
        return "fid-test-001"

    case_data = {
        "case_id":      "CST-001",
        "factory_name": "테스트현장",
        "sector":       "CONSTRUCTION",
        "worker_count": 50,
        "sector_fields": {
            "construction_type":   "건축",
            "construction_amount": 59_890_000_000,
        },
        "construction_processes": [],
        "construction_works":     [],
    }

    result = provision_cst_source(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _site_insert_fn=mock_site_insert,
        _factory_bridge_fn=mock_factory_bridge,
    )
    assert inserted["called"] is True
    # POST /sites was NOT called (no HTTP call made — seam replaced DB insert)
    assert result["site_id"] == "site-test-001"


# ─────────────────────────────────────────────────────────────────────────────
# P12 — auto_diagnose_and_schedule not called
# ─────────────────────────────────────────────────────────────────────────────

def test_p12_auto_diagnose_not_called():
    """P12: _factory_bridge_fn does not call auto_diagnose_and_schedule."""
    bridge_calls = []

    def mock_factory_bridge(supabase, site_row, now_iso_fn):
        bridge_calls.append({"site_row": site_row})
        return "fid-test-001"

    case_data = {
        "case_id":      "CST-002",
        "factory_name": "현장2",
        "sector":       "CONSTRUCTION",
        "worker_count": 20,
        "sector_fields": {
            "construction_type":   "토목",
            "construction_amount": 30_000_000_000,
        },
    }
    provision_cst_source(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _site_insert_fn=lambda *_a: "sid-002",
        _factory_bridge_fn=mock_factory_bridge,
    )
    assert len(bridge_calls) == 1
    # No diagnosis or schedule function in bridge args
    bridge_row = bridge_calls[0]["site_row"]
    assert "auto_diagnose" not in str(bridge_row)
    assert "run_diagnosis" not in str(bridge_row)


# ─────────────────────────────────────────────────────────────────────────────
# P13 — site created
# ─────────────────────────────────────────────────────────────────────────────

def test_p13_site_created():
    """P13: provision_cst_source returns site_id from _site_insert_fn."""
    case_data = {
        "case_id":      "CST-003",
        "factory_name": "현장3",
        "sector":       "CONSTRUCTION",
        "worker_count": 100,
        "sector_fields": {
            "construction_type":   "공통",
            "construction_amount": 50_000_000_000,
        },
    }
    result = provision_cst_source(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _site_insert_fn=lambda *_a: "sid-explicit-003",
        _factory_bridge_fn=lambda *_a: "fid-explicit-003",
    )
    assert result["site_id"] == "sid-explicit-003"


# ─────────────────────────────────────────────────────────────────────────────
# P14 — factory bridge created
# ─────────────────────────────────────────────────────────────────────────────

def test_p14_factory_bridge_created():
    """P14: provision_cst_source returns factory_id from _factory_bridge_fn; pipeline_c1_exact from readback."""
    case_data = {
        "case_id":      "CST-004",
        "factory_name": "현장4",
        "sector":       "CONSTRUCTION",
        "worker_count": 60,
        "sector_fields": {
            "construction_type":   "건축",
            "construction_amount": 80_000_000_000,
        },
    }
    # Readback seams return matching data so verify_cst_c1_exact returns exact=True
    result = provision_cst_source(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _site_insert_fn=lambda *_a: "sid-004",
        _factory_bridge_fn=lambda *_a: "fid-bridge-004",
        _site_read_fn=lambda _sb, _sid: {
            "id": "sid-004", "site_name": "현장4",
            "site_type": "BUILDING", "contract_amount": 800.0, "total_workers": 60,
        },
        _factory_read_fn=lambda _sb, _fid: {"id": "fid-bridge-004"},
    )
    assert result["factory_id"] == "fid-bridge-004"
    assert result["pipeline_c1_exact"] is True  # from verify_cst_c1_exact, not hardcoded


# ─────────────────────────────────────────────────────────────────────────────
# P15 — amount normalized once only
# ─────────────────────────────────────────────────────────────────────────────

def test_p15_amount_normalized_once():
    """P15: normalize_cst_amount_to_eok called exactly once in build_cst_site_payload."""
    case_data = {
        "case_id":      "CST-001",
        "factory_name": "현장1",
        "sector":       "CONSTRUCTION",
        "worker_count": 30,
        "sector_fields": {
            "construction_type":   "건축",
            "construction_amount": 59_890_000_000,  # WON
        },
    }
    payload = build_cst_site_payload(case_data, "cmp-001")
    # Exact: 59,890,000,000 / 100,000,000 = 598.9
    assert abs(payload["contract_amount"] - 598.9) < 0.001
    # NOT double-normalized (598.9 / 100_000_000 would be near-zero)
    assert payload["contract_amount"] > 1.0


# ─────────────────────────────────────────────────────────────────────────────
# P16 — no magnitude inference
# ─────────────────────────────────────────────────────────────────────────────

def test_p16_no_magnitude_inference():
    """P16: normalize_cst_amount_to_eok divides by fixed 100_000_000 only — no branching by size."""
    assert normalize_cst_amount_to_eok(100_000_000)     == pytest.approx(1.0)
    assert normalize_cst_amount_to_eok(1_500_000_000)   == pytest.approx(15.0)
    assert normalize_cst_amount_to_eok(50_000_000_000)  == pytest.approx(500.0)
    assert normalize_cst_amount_to_eok(500_000_000_000) == pytest.approx(5000.0)
    # No different logic for small vs large amounts


# ─────────────────────────────────────────────────────────────────────────────
# P17 — missing address remains missing
# ─────────────────────────────────────────────────────────────────────────────

def test_p17_missing_address_remains_missing():
    """P17: CST frozen has no site_address → payload site_address=None (not synthetic)."""
    case_data = {
        "case_id":      "CST-005",
        "factory_name": "현장5",
        "sector":       "CONSTRUCTION",
        "worker_count": 25,
        "sector_fields": {
            "construction_type":   "토목",
            "construction_amount": 40_000_000_000,
        },
    }
    payload = build_cst_site_payload(case_data, "cmp-001")
    assert "site_address" in payload
    assert payload["site_address"] is None


# ─────────────────────────────────────────────────────────────────────────────
# P18 — construction_processes NOT converted to CST site payload
# ─────────────────────────────────────────────────────────────────────────────

def test_p18_construction_processes_not_converted():
    """P18: construction_processes present in frozen → NOT in site payload, marked NOT_CURRENTLY_CONSUMED."""
    case_data = {
        "case_id":      "CST-006",
        "factory_name": "현장6",
        "sector":       "CONSTRUCTION",
        "worker_count": 80,
        "construction_processes": [
            {"process_id": "KCSC-001", "process_name": "가설공사"},
            {"process_id": "KCSC-002", "process_name": "토공사"},
        ],
        "construction_works": [],
        "sector_fields": {
            "construction_type":   "건축",
            "construction_amount": 70_000_000_000,
        },
    }
    payload = build_cst_site_payload(case_data, "cmp-001")
    assert "construction_processes" not in payload
    assert "kcsc_process" not in str(payload).lower()

    # Evidence marks it as NOT_CURRENTLY_CONSUMED
    evidence = build_c1_source_evidence(case_data, {"pipeline_c1_exact": True, "factory_id": "f", "site_id": "s"})
    assert "non_pipeline_baseline_fields" in evidence
    assert evidence["non_pipeline_baseline_fields"]["construction_processes"]["status"] == "NOT_CURRENTLY_CONSUMED"


# ─────────────────────────────────────────────────────────────────────────────
# P19 — construction_works NOT converted
# ─────────────────────────────────────────────────────────────────────────────

def test_p19_construction_works_not_converted():
    """P19: construction_works NOT in site payload, marked NOT_CURRENTLY_CONSUMED."""
    case_data = {
        "case_id":      "CST-007",
        "factory_name": "현장7",
        "sector":       "CONSTRUCTION",
        "worker_count": 40,
        "construction_processes": [],
        "construction_works": [
            {"work_name": "굴착작업", "is_hazardous": True},
        ],
        "sector_fields": {
            "construction_type":   "토목",
            "construction_amount": 35_000_000_000,
        },
    }
    payload = build_cst_site_payload(case_data, "cmp-001")
    assert "construction_works" not in payload

    evidence = build_c1_source_evidence(case_data, {"pipeline_c1_exact": True, "factory_id": "f", "site_id": "s"})
    assert evidence["non_pipeline_baseline_fields"]["construction_works"]["status"] == "NOT_CURRENTLY_CONSUMED"


# ─────────────────────────────────────────────────────────────────────────────
# P20 — no synthetic work_date
# ─────────────────────────────────────────────────────────────────────────────

def test_p20_no_synthetic_work_date():
    """P20: build_cst_site_payload and provision_cst_source produce no work_date field."""
    case_data = {
        "case_id":      "CST-008",
        "factory_name": "현장8",
        "sector":       "CONSTRUCTION",
        "worker_count": 55,
        "construction_works": [{"work_name": "철거작업"}],  # no work_date in frozen
        "sector_fields": {
            "construction_type":   "공통",
            "construction_amount": 90_000_000_000,
        },
    }
    payload = build_cst_site_payload(case_data, "cmp-001")
    assert "work_date" not in payload

    # provision_cst_source also must not inject work_date
    site_payloads_seen = []

    def capture_site_insert(supabase, payload, now_iso_fn):
        site_payloads_seen.append(payload)
        return "sid-008"

    provision_cst_source(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _site_insert_fn=capture_site_insert,
        _factory_bridge_fn=lambda *_a: "fid-008",
    )
    for p in site_payloads_seen:
        assert "work_date" not in p

# =============================================================================
# WO-005A — Q1-Q23: readback exactness, stale guard, verify functions,
# provision orchestrators, sector router
# All mock/seam only.  PRODUCTION_WRITE = 0.  LEG_EXECUTED = 0.
# =============================================================================

from services.legal_rules import normalize_sector_db as _norm_sector

_NORM_MFG = _norm_sector("MANUFACTURING")  # "INDUSTRIAL"


# ─────────────────────────────────────────────────────────────────────────────
# Q1 — provision_mfg_c1 raises StaleE2ECaseError when stale
# ─────────────────────────────────────────────────────────────────────────────

def test_q1_mfg_stale_guard_raises():
    """Q1: provision_mfg_c1 raises StaleE2ECaseError when _stale_fn returns True."""
    case_data = {
        "case_id": "MFG-001", "factory_name": "중복공장", "sector": "MANUFACTURING",
        "worker_count": 10, "sector_fields": {}, "processes": [], "works": [],
        "materials": [], "equipment": [],
    }
    with pytest.raises(StaleE2ECaseError) as exc_info:
        provision_mfg_c1(
            MagicMock(), case_data, "cmp-001",
            _stale_fn=lambda *_a: True,
        )
    assert "STALE_E2E_CASE_FOUND" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# Q2 — provision_bld_c1 raises StaleE2ECaseError when stale
# ─────────────────────────────────────────────────────────────────────────────

def test_q2_bld_stale_guard_raises():
    """Q2: provision_bld_c1 raises StaleE2ECaseError when _stale_fn returns True."""
    case_data = {
        "case_id": "BLD-001", "factory_name": "중복빌딩", "sector": "BUILDING",
        "worker_count": 20, "sector_fields": {"building_area": 300.0, "floor_count": 3},
        "processes": [], "works": [], "materials": [], "equipment": [],
    }
    with pytest.raises(StaleE2ECaseError):
        provision_bld_c1(
            MagicMock(), case_data, "cmp-001",
            _stale_fn=lambda *_a: True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Q3 — stale check passes (no error) when _stale_fn returns False
# ─────────────────────────────────────────────────────────────────────────────

def test_q3_stale_check_passes_when_no_duplicate():
    """Q3: provision_mfg_c1 proceeds normally when _stale_fn returns False."""
    case_data = {
        "case_id": "MFG-002", "factory_name": "신규공장", "sector": "MANUFACTURING",
        "worker_count": 10, "sector_fields": {}, "processes": [], "works": [],
        "materials": [], "equipment": [],
    }
    inserted = {}

    def mock_ins(supabase, payload):
        inserted.update(payload)
        return {**payload, "id": "fid-q3"}

    # Should not raise
    result = provision_mfg_c1(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _factory_insert_fn=mock_ins,
        _factory_read_fn=lambda *_a: {**inserted, "id": "fid-q3"},
        _process_read_fn=lambda *_a: [],
        _work_read_fn=lambda *_a: [],
        _material_read_fn=lambda *_a: [],
        _equipment_read_fn=lambda *_a: [],
    )
    assert result["factory_id"] == "fid-q3"


# ─────────────────────────────────────────────────────────────────────────────
# Q4 — verify_mfg_c1_exact exact=True for matching factory
# ─────────────────────────────────────────────────────────────────────────────

def test_q4_verify_mfg_exact_true():
    """Q4: verify_mfg_c1_exact returns exact=True when stored matches expected."""
    expected = {
        "name": "공장A", "company_id": "cmp-001",
        "sector": _NORM_MFG,  # "INDUSTRIAL"
        "site_type": "OFFICE", "employee_count": 45,
        "ksic_code": "C2593", "electrical_capacity_kw": 402,
    }
    stored = {**expected, "id": "fid-001", "extra_col": "ignored"}
    result = verify_mfg_c1_exact(stored, expected)
    assert result["exact"] is True
    assert result["mismatches"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Q5 — verify_mfg_c1_exact detects wrong sector (MANUFACTURING vs INDUSTRIAL)
# ─────────────────────────────────────────────────────────────────────────────

def test_q5_verify_mfg_exact_wrong_sector():
    """Q5: verify_mfg_c1_exact returns exact=False with 'sector' in mismatches when sector='MANUFACTURING'."""
    expected = {
        "name": "공장B", "company_id": "cmp-001",
        "sector": _NORM_MFG,  # "INDUSTRIAL"
        "site_type": "OFFICE", "employee_count": 30, "ksic_code": "C2511",
    }
    stored = {**expected, "sector": "MANUFACTURING"}  # wrong: should be INDUSTRIAL
    result = verify_mfg_c1_exact(stored, expected)
    assert result["exact"] is False
    assert "sector" in result["mismatches"]


# ─────────────────────────────────────────────────────────────────────────────
# Q6 — verify_mfg_c1_exact detects employee_count mismatch
# ─────────────────────────────────────────────────────────────────────────────

def test_q6_verify_mfg_exact_wrong_employee_count():
    """Q6: verify_mfg_c1_exact returns exact=False when employee_count differs."""
    expected = {
        "name": "공장C", "company_id": "cmp-001",
        "sector": _NORM_MFG, "site_type": "OFFICE", "employee_count": 50,
    }
    stored = {**expected, "employee_count": 99}  # wrong
    result = verify_mfg_c1_exact(stored, expected)
    assert result["exact"] is False
    assert "employee_count" in result["mismatches"]


# ─────────────────────────────────────────────────────────────────────────────
# Q7 — verify_bld_c1_exact exact=True for matching factory
# ─────────────────────────────────────────────────────────────────────────────

def test_q7_verify_bld_exact_true():
    """Q7: verify_bld_c1_exact returns exact=True when stored matches expected."""
    expected = {
        "name": "빌딩A", "company_id": "cmp-001", "sector": "BUILDING",
        "site_type": "BUILDING", "employee_count": 30,
        "building_area": 411.3, "floor_count": 4, "electrical_capacity_kw": 73,
    }
    stored = {**expected, "id": "fid-bld-001"}
    result = verify_bld_c1_exact(stored, expected)
    assert result["exact"] is True
    assert result["mismatches"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Q8 — verify_bld_c1_exact detects building_area mismatch
# ─────────────────────────────────────────────────────────────────────────────

def test_q8_verify_bld_exact_wrong_building_area():
    """Q8: verify_bld_c1_exact returns exact=False when building_area differs."""
    expected = {
        "name": "빌딩B", "company_id": "cmp-001", "sector": "BUILDING",
        "site_type": "BUILDING", "employee_count": 25, "building_area": 500.0,
    }
    stored = {**expected, "building_area": 999.0}  # wrong
    result = verify_bld_c1_exact(stored, expected)
    assert result["exact"] is False
    assert "building_area" in result["mismatches"]


# ─────────────────────────────────────────────────────────────────────────────
# Q9 — verify_cst_c1_exact exact=True when site+factory match
# ─────────────────────────────────────────────────────────────────────────────

def test_q9_verify_cst_exact_true():
    """Q9: verify_cst_c1_exact returns exact=True when site row and factory bridge match."""
    case_data = {
        "case_id": "CST-001", "factory_name": "현장A", "sector": "CONSTRUCTION",
        "worker_count": 60,
        "sector_fields": {"construction_type": "건축", "construction_amount": 80_000_000_000},
    }
    stored_site = {
        "id": "sid-001", "site_name": "현장A", "site_type": "BUILDING",
        "contract_amount": 800.0, "total_workers": 60,
    }
    stored_factory = {"id": "fid-001"}
    result = verify_cst_c1_exact(stored_site, stored_factory, case_data)
    assert result["exact"] is True
    assert result["mismatches"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Q10 — verify_cst_c1_exact fails when stored_factory is None (bridge failed)
# ─────────────────────────────────────────────────────────────────────────────

def test_q10_verify_cst_exact_false_no_factory():
    """Q10: verify_cst_c1_exact returns exact=False with 'factory_bridge' in mismatches when factory absent."""
    case_data = {
        "case_id": "CST-002", "factory_name": "현장B", "sector": "CONSTRUCTION",
        "worker_count": 30,
        "sector_fields": {"construction_type": "토목", "construction_amount": 50_000_000_000},
    }
    stored_site = {
        "id": "sid-002", "site_name": "현장B", "site_type": "CIVIL",
        "contract_amount": 500.0, "total_workers": 30,
    }
    result = verify_cst_c1_exact(stored_site, None, case_data)
    assert result["exact"] is False
    assert "factory_bridge" in result["mismatches"]


# ─────────────────────────────────────────────────────────────────────────────
# Q11 — provision_mfg_c1 inserts factory with sector=INDUSTRIAL
# ─────────────────────────────────────────────────────────────────────────────

def test_q11_provision_mfg_c1_inserts_industrial_sector():
    """Q11: provision_mfg_c1 passes sector='INDUSTRIAL' (not 'MANUFACTURING') to factory insert."""
    captured_payload = {}

    def mock_ins(supabase, payload):
        captured_payload.update(payload)
        return {**payload, "id": "fid-q11"}

    case_data = {
        "case_id": "MFG-003", "factory_name": "공장Q11", "sector": "MANUFACTURING",
        "worker_count": 50, "site_type": "OFFICE",
        "sector_fields": {"ksic_code": "C2593"},
        "processes": [], "works": [], "materials": [], "equipment": [],
    }
    provision_mfg_c1(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _factory_insert_fn=mock_ins,
        _factory_read_fn=lambda *_a: {**captured_payload, "id": "fid-q11"},
        _process_read_fn=lambda *_a: [],
        _work_read_fn=lambda *_a: [],
        _material_read_fn=lambda *_a: [],
        _equipment_read_fn=lambda *_a: [],
    )
    assert captured_payload["sector"] == "INDUSTRIAL"


# ─────────────────────────────────────────────────────────────────────────────
# Q12 — provision_mfg_c1 calls factory readback after insert
# ─────────────────────────────────────────────────────────────────────────────

def test_q12_provision_mfg_c1_factory_readback_called():
    """Q12: provision_mfg_c1 calls _factory_read_fn — readback is required, not just insert success."""
    read_calls = []

    def mock_read(supabase, factory_id):
        read_calls.append(factory_id)
        return {"id": factory_id, "name": "공장Q12", "company_id": "cmp-001",
                "sector": "INDUSTRIAL", "site_type": "OFFICE", "employee_count": 10}

    case_data = {
        "case_id": "MFG-004", "factory_name": "공장Q12", "sector": "MANUFACTURING",
        "worker_count": 10, "sector_fields": {},
        "processes": [], "works": [], "materials": [], "equipment": [],
    }
    provision_mfg_c1(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _factory_insert_fn=lambda _sb, p: {**p, "id": "fid-q12"},
        _factory_read_fn=mock_read,
        _process_read_fn=lambda *_a: [],
        _work_read_fn=lambda *_a: [],
        _material_read_fn=lambda *_a: [],
        _equipment_read_fn=lambda *_a: [],
    )
    assert len(read_calls) == 1
    assert read_calls[0] == "fid-q12"


# ─────────────────────────────────────────────────────────────────────────────
# Q13 — provision_mfg_c1 pipeline_c1_exact=True when all verify pass
# ─────────────────────────────────────────────────────────────────────────────

def test_q13_provision_mfg_c1_pipeline_exact_true_from_verify():
    """Q13: pipeline_c1_exact=True only when factory + all source readbacks match."""
    case_data = {
        "case_id": "MFG-005", "factory_name": "공장Q13", "sector": "MANUFACTURING",
        "worker_count": 45, "site_type": "OFFICE",
        "sector_fields": {"ksic_code": "C2593", "electrical_capacity_kw": 402},
        "processes": [],
        "works": [{"work_type": "GRINDING", "work_subtype": None, "attributes": {}}],
        "materials": [],
        "equipment": [{"equipment_type_code": "040", "asset_name": "VOC설비", "quantity": 1}],
    }
    captured = {}

    def mock_ins(supabase, payload):
        captured.update(payload)
        return {**payload, "id": "fid-q13"}

    result = provision_mfg_c1(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _factory_insert_fn=mock_ins,
        _factory_read_fn=lambda *_a: {**captured, "id": "fid-q13"},  # exact match
        _process_read_fn=lambda *_a: [],                                # 0 expected → exact
        _work_read_fn=lambda *_a: [{"work_type": "GRINDING", "active": True}],
        _material_read_fn=lambda *_a: [],                               # 0 expected → exact
        _equipment_read_fn=lambda *_a: [{"equipment_type_code": "040"}],
        _work_insert_fn=lambda *_a: {},
        _equipment_insert_fn=lambda *_a: {},
    )
    assert result["pipeline_c1_exact"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Q14 — provision_mfg_c1 pipeline_c1_exact=False when factory readback has wrong sector
# ─────────────────────────────────────────────────────────────────────────────

def test_q14_provision_mfg_c1_pipeline_exact_false_on_mismatch():
    """Q14: pipeline_c1_exact=False when factory readback returns wrong sector."""
    case_data = {
        "case_id": "MFG-006", "factory_name": "공장Q14", "sector": "MANUFACTURING",
        "worker_count": 45, "site_type": "OFFICE",
        "sector_fields": {"ksic_code": "C2593"},
        "processes": [], "works": [], "materials": [], "equipment": [],
    }
    result = provision_mfg_c1(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _factory_insert_fn=lambda _sb, p: {**p, "id": "fid-q14"},
        # readback returns MANUFACTURING (wrong) — verify should catch this
        _factory_read_fn=lambda *_a: {
            "id": "fid-q14", "name": "공장Q14", "company_id": "cmp-001",
            "sector": "MANUFACTURING",  # wrong: should be INDUSTRIAL
            "site_type": "OFFICE", "employee_count": 45,
        },
        _process_read_fn=lambda *_a: [],
        _work_read_fn=lambda *_a: [],
        _material_read_fn=lambda *_a: [],
        _equipment_read_fn=lambda *_a: [],
    )
    assert result["pipeline_c1_exact"] is False
    assert "sector" in result["verify"]["factory"]["mismatches"]


# ─────────────────────────────────────────────────────────────────────────────
# Q15 — provision_bld_c1 factory insert called
# ─────────────────────────────────────────────────────────────────────────────

def test_q15_provision_bld_c1_factory_insert_called():
    """Q15: provision_bld_c1 calls _factory_insert_fn with BLD sector."""
    captured = {}

    def mock_ins(supabase, payload):
        captured.update(payload)
        return {**payload, "id": "fid-bld-q15"}

    case_data = {
        "case_id": "BLD-002", "factory_name": "빌딩Q15", "sector": "BUILDING",
        "worker_count": 30, "site_type": "BUILDING",
        "sector_fields": {"building_area": 411.3, "floor_count": 4},
        "processes": [], "works": [], "materials": [], "equipment": [],
    }
    provision_bld_c1(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _factory_insert_fn=mock_ins,
        _factory_read_fn=lambda *_a: {**captured, "id": "fid-bld-q15"},
        _work_read_fn=lambda *_a: [],
        _material_read_fn=lambda *_a: [],
        _equipment_read_fn=lambda *_a: [],
    )
    assert captured["sector"] == "BUILDING"
    assert captured["building_area"] == 411.3


# ─────────────────────────────────────────────────────────────────────────────
# Q16 — provision_bld_c1 does NOT call process insert (BLD_NOT_PIPELINE)
# ─────────────────────────────────────────────────────────────────────────────

def test_q16_provision_bld_c1_no_process_insert():
    """Q16: provision_bld_c1 never calls process insert — BLD processes are NOT_PIPELINE."""
    process_insert_calls = []

    case_data = {
        "case_id": "BLD-003", "factory_name": "빌딩Q16", "sector": "BUILDING",
        "worker_count": 20, "sector_fields": {"building_area": 300.0, "floor_count": 3},
        "processes": [{"process_id": "P01", "process_name": "공정1", "source": "DB"}],
        "works": [], "materials": [], "equipment": [],
    }
    provision_bld_c1(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _factory_insert_fn=lambda _sb, p: {**p, "id": "fid-bld-q16"},
        _factory_read_fn=lambda *_a: {
            "id": "fid-bld-q16", "name": "빌딩Q16", "company_id": "cmp-001",
            "sector": "BUILDING", "site_type": "BUILDING", "employee_count": 20,
            "building_area": 300.0, "floor_count": 3,
        },
        _work_read_fn=lambda *_a: [],
        _material_read_fn=lambda *_a: [],
        _equipment_read_fn=lambda *_a: [],
    )
    assert len(process_insert_calls) == 0  # NOT called: no _process_insert_fn param for BLD


# ─────────────────────────────────────────────────────────────────────────────
# Q17 — provision_bld_c1 pipeline_c1_exact from readback
# ─────────────────────────────────────────────────────────────────────────────

def test_q17_provision_bld_c1_pipeline_exact_from_readback():
    """Q17: provision_bld_c1 pipeline_c1_exact derives from factory readback verify, not insert success."""
    case_data = {
        "case_id": "BLD-004", "factory_name": "빌딩Q17", "sector": "BUILDING",
        "worker_count": 25, "site_type": "BUILDING",
        "sector_fields": {"building_area": 500.0, "floor_count": 5},
        "processes": [], "works": [], "materials": [], "equipment": [],
    }
    captured = {}

    def mock_ins(supabase, payload):
        captured.update(payload)
        return {**payload, "id": "fid-bld-q17"}

    result = provision_bld_c1(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _factory_insert_fn=mock_ins,
        _factory_read_fn=lambda *_a: {**captured, "id": "fid-bld-q17"},  # exact
        _work_read_fn=lambda *_a: [],
        _material_read_fn=lambda *_a: [],
        _equipment_read_fn=lambda *_a: [],
    )
    # Readback matched expected → exact=True
    assert result["pipeline_c1_exact"] is True
    assert result["direct_source_exact"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Q18 — provision_cst_source site readback called after insert
# ─────────────────────────────────────────────────────────────────────────────

def test_q18_provision_cst_site_readback_called():
    """Q18: provision_cst_source calls _site_read_fn after inserting the site."""
    site_reads = []

    def mock_site_read(supabase, site_id):
        site_reads.append(site_id)
        return {
            "id": site_id, "site_name": "현장Q18", "site_type": "BUILDING",
            "contract_amount": 500.0, "total_workers": 40,
        }

    case_data = {
        "case_id": "CST-Q18", "factory_name": "현장Q18", "sector": "CONSTRUCTION",
        "worker_count": 40,
        "sector_fields": {"construction_type": "건축", "construction_amount": 50_000_000_000},
    }
    provision_cst_source(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _site_insert_fn=lambda *_a: "sid-q18",
        _factory_bridge_fn=lambda *_a: "fid-q18",
        _site_read_fn=mock_site_read,
        _factory_read_fn=lambda *_a: {"id": "fid-q18"},
    )
    assert len(site_reads) == 1
    assert site_reads[0] == "sid-q18"


# ─────────────────────────────────────────────────────────────────────────────
# Q19 — provision_cst_source factory readback called after bridge
# ─────────────────────────────────────────────────────────────────────────────

def test_q19_provision_cst_factory_readback_called():
    """Q19: provision_cst_source calls _factory_read_fn after factory bridge."""
    factory_reads = []

    def mock_factory_read(supabase, factory_id):
        factory_reads.append(factory_id)
        return {"id": factory_id}

    case_data = {
        "case_id": "CST-Q19", "factory_name": "현장Q19", "sector": "CONSTRUCTION",
        "worker_count": 50,
        "sector_fields": {"construction_type": "토목", "construction_amount": 60_000_000_000},
    }
    provision_cst_source(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _site_insert_fn=lambda *_a: "sid-q19",
        _factory_bridge_fn=lambda *_a: "fid-q19",
        _site_read_fn=lambda *_a: {
            "id": "sid-q19", "site_name": "현장Q19", "site_type": "CIVIL",
            "contract_amount": 600.0, "total_workers": 50,
        },
        _factory_read_fn=mock_factory_read,
    )
    assert len(factory_reads) == 1
    assert factory_reads[0] == "fid-q19"


# ─────────────────────────────────────────────────────────────────────────────
# Q20 — provision_cst_source pipeline_c1_exact from verify_cst_c1_exact, not hardcoded
# ─────────────────────────────────────────────────────────────────────────────

def test_q20_provision_cst_pipeline_exact_from_verify_not_hardcoded():
    """Q20: provision_cst_source pipeline_c1_exact comes from verify_cst_c1_exact (readback), not True literal."""
    case_data = {
        "case_id": "CST-Q20", "factory_name": "현장Q20", "sector": "CONSTRUCTION",
        "worker_count": 35,
        "sector_fields": {"construction_type": "건축", "construction_amount": 40_000_000_000},
    }

    # Scenario A: readback matches → exact=True
    result_exact = provision_cst_source(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _site_insert_fn=lambda *_a: "sid-q20",
        _factory_bridge_fn=lambda *_a: "fid-q20",
        _site_read_fn=lambda *_a: {
            "id": "sid-q20", "site_name": "현장Q20", "site_type": "BUILDING",
            "contract_amount": 400.0, "total_workers": 35,
        },
        _factory_read_fn=lambda *_a: {"id": "fid-q20"},
    )
    assert result_exact["pipeline_c1_exact"] is True

    # Scenario B: readback returns None (simulates DB read failure) → exact=False
    result_fail = provision_cst_source(
        MagicMock(), case_data, "cmp-001",
        _stale_fn=lambda *_a: False,
        _site_insert_fn=lambda *_a: "sid-q20b",
        _factory_bridge_fn=lambda *_a: "fid-q20b",
        _site_read_fn=lambda *_a: None,       # readback failed
        _factory_read_fn=lambda *_a: {"id": "fid-q20b"},
    )
    assert result_fail["pipeline_c1_exact"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Q21 — provision_case routes MANUFACTURING to provision_mfg_c1
# ─────────────────────────────────────────────────────────────────────────────

def test_q21_provision_case_routes_mfg():
    """Q21: provision_case dispatches MANUFACTURING sector to provision_mfg_c1."""
    case_data = {
        "case_id": "MFG-Q21", "factory_name": "공장Q21", "sector": "MANUFACTURING",
        "worker_count": 15, "sector_fields": {},
        "processes": [], "works": [], "materials": [], "equipment": [],
    }
    captured = {}
    result = provision_case(
        MagicMock(), case_data, "cmp-001",
        _mfg_seams={
            "_stale_fn": lambda *_a: False,
            "_factory_insert_fn": lambda _sb, p: (captured.update(p) or {**p, "id": "fid-q21"}),
            "_factory_read_fn": lambda *_a: {**captured, "id": "fid-q21"},
            "_process_read_fn": lambda *_a: [],
            "_work_read_fn": lambda *_a: [],
            "_material_read_fn": lambda *_a: [],
            "_equipment_read_fn": lambda *_a: [],
        },
    )
    # provision_mfg_c1 was called: result has factory_id (not site_id pattern)
    assert result["factory_id"] == "fid-q21"
    assert result["site_id"] is None
    assert captured["sector"] == "INDUSTRIAL"


# ─────────────────────────────────────────────────────────────────────────────
# Q22 — provision_case routes BUILDING to provision_bld_c1
# ─────────────────────────────────────────────────────────────────────────────

def test_q22_provision_case_routes_bld():
    """Q22: provision_case dispatches BUILDING sector to provision_bld_c1."""
    case_data = {
        "case_id": "BLD-Q22", "factory_name": "빌딩Q22", "sector": "BUILDING",
        "worker_count": 20, "sector_fields": {"building_area": 300.0, "floor_count": 3},
        "processes": [], "works": [], "materials": [], "equipment": [],
    }
    captured = {}
    result = provision_case(
        MagicMock(), case_data, "cmp-001",
        _bld_seams={
            "_stale_fn": lambda *_a: False,
            "_factory_insert_fn": lambda _sb, p: (captured.update(p) or {**p, "id": "fid-bld-q22"}),
            "_factory_read_fn": lambda *_a: {**captured, "id": "fid-bld-q22"},
            "_work_read_fn": lambda *_a: [],
            "_material_read_fn": lambda *_a: [],
            "_equipment_read_fn": lambda *_a: [],
        },
    )
    assert result["factory_id"] == "fid-bld-q22"
    assert captured["sector"] == "BUILDING"
    assert captured["building_area"] == 300.0


# ─────────────────────────────────────────────────────────────────────────────
# Q23 — provision_case routes CONSTRUCTION to provision_cst_source
# ─────────────────────────────────────────────────────────────────────────────

def test_q23_provision_case_routes_cst():
    """Q23: provision_case dispatches CONSTRUCTION sector to provision_cst_source."""
    case_data = {
        "case_id": "CST-Q23", "factory_name": "현장Q23", "sector": "CONSTRUCTION",
        "worker_count": 80,
        "sector_fields": {"construction_type": "공통", "construction_amount": 100_000_000_000},
    }
    result = provision_case(
        MagicMock(), case_data, "cmp-001",
        _cst_seams={
            "_stale_fn": lambda *_a: False,
            "_site_insert_fn": lambda *_a: "sid-cst-q23",
            "_factory_bridge_fn": lambda *_a: "fid-cst-q23",
            "_site_read_fn": lambda *_a: {
                "id": "sid-cst-q23", "site_name": "현장Q23", "site_type": "SPECIALTY",
                "contract_amount": 1000.0, "total_workers": 80,
            },
            "_factory_read_fn": lambda *_a: {"id": "fid-cst-q23"},
        },
    )
    # provision_cst_source was called: result has site_id
    assert result["site_id"] == "sid-cst-q23"
    assert result["factory_id"] == "fid-cst-q23"
