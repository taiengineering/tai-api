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
    build_bld_factory_payload,
    build_c1_source_evidence,
    build_cst_site_payload,
    build_manifest_c1_entry,
    build_mfg_factory_payload,
    extract_mfg_explicit_confirms,
    normalize_cst_amount_to_eok,
    normalize_cst_construction_type,
    provision_cst_source,
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
    assert payload["sector"] == "MANUFACTURING"


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
        _site_insert_fn=lambda *_a: "sid-explicit-003",
        _factory_bridge_fn=lambda *_a: "fid-explicit-003",
    )
    assert result["site_id"] == "sid-explicit-003"


# ─────────────────────────────────────────────────────────────────────────────
# P14 — factory bridge created
# ─────────────────────────────────────────────────────────────────────────────

def test_p14_factory_bridge_created():
    """P14: provision_cst_source returns factory_id from _factory_bridge_fn."""
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
    result = provision_cst_source(
        MagicMock(), case_data, "cmp-001",
        _site_insert_fn=lambda *_a: "sid-004",
        _factory_bridge_fn=lambda *_a: "fid-bridge-004",
    )
    assert result["factory_id"] == "fid-bridge-004"
    assert result["pipeline_c1_exact"] is True


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
        _site_insert_fn=capture_site_insert,
        _factory_bridge_fn=lambda *_a: "fid-008",
    )
    for p in site_payloads_seen:
        assert "work_date" not in p
