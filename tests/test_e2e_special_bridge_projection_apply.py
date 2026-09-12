"""WO-SM-E2E-SPECIAL-BRIDGE-PROJECTION-APPLY-001 — SPECIAL consumer projection.

No live POST /diagnosis/run-leg. No Frozen Profile rewrite. No tier injection.
"""
from __future__ import annotations

import hashlib
import inspect
from collections import Counter
from pathlib import Path

import pytest
from pydantic.fields import PydanticUndefined

from routers.diagnosis_integrated import FREE_TIER_CODES
from schemas.diagnosis_integrated import DiagnosisRunBody
from services.diagnosis_helpers import _auto_tier
from services.legal_rules import normalize_sector_db
from tools.test_universe.leg_bridge import (
    EXPECTED_PROFILE_COUNT,
    consumer_entry_sector,
    load_profile_universe,
    profile_to_leg_request,
    project_universe,
)

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = Path.home() / "45cm-test/profile_universe_v1.json"
RUNNER = ROOT / "tools/test_universe/e2e_runner_all.py"
BRIDGE = ROOT / "tools/test_universe/leg_bridge.py"

needs_universe = pytest.mark.skipif(not UNIVERSE.is_file(), reason="frozen universe missing")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profiles():
    return load_profile_universe(UNIVERSE)["profiles"]


def _dry_is_free(request_sector: str, floor_area: float | None) -> tuple[str, bool]:
    """Production run_diagnosis tier remap. Bridge does not inject this."""
    sector = normalize_sector_db(request_sector)
    tier = _auto_tier(sector, floor_area=floor_area or 0.0, contract_amount_eok=0.0, user_tier=None)
    if tier not in FREE_TIER_CODES:
        root = "INDUSTRY" if sector in ("INDUSTRIAL", "INDUSTRY") else sector
        cand = "{}_FREE".format(root)
        if cand in FREE_TIER_CODES:
            tier = cand
    return tier, tier in FREE_TIER_CODES


@needs_universe
def test_T1_frozen_112_load():
    assert len(_profiles()) == EXPECTED_PROFILE_COUNT


@needs_universe
def test_T2_special_count_10():
    assert sum(1 for p in _profiles() if p.get("sector") == "SPECIAL_FACILITY") == 10


@needs_universe
def test_T3_special_source_sector_unchanged():
    built, _ = project_universe(_profiles())
    special = [x for x in built if x["sector"] == "SPECIAL_FACILITY"]
    assert len(special) == 10
    for item in special:
        assert item["sector"] == "SPECIAL_FACILITY"


@needs_universe
def test_T4_special_request_sector_building_10_of_10():
    built, _ = project_universe(_profiles())
    special = [x for x in built if x["sector"] == "SPECIAL_FACILITY"]
    assert len(special) == 10
    for item in special:
        assert item["request_sector"] == "BUILDING"
        assert item["request"]["sector"] == "BUILDING"


@needs_universe
def test_T5_non_special_sector_projection_unchanged():
    expected = {
        "MANUFACTURING": "MANUFACTURING",
        "BUILDING": "BUILDING",
        "CONSTRUCTION": "CONSTRUCTION",
    }
    counts = Counter()
    for p in _profiles():
        src = p["sector"]
        if src == "SPECIAL_FACILITY":
            continue
        item = profile_to_leg_request(p)
        assert item["sector"] == src
        assert item["request"]["sector"] == expected[src]
        counts[src] += 1
    assert counts["MANUFACTURING"] == 46
    assert counts["BUILDING"] == 29
    assert counts["CONSTRUCTION"] == 27


@needs_universe
def test_T6_synthetic_building_use_type_zero():
    special = [p for p in _profiles() if p.get("sector") == "SPECIAL_FACILITY"]
    present = 0
    for p in special:
        req = profile_to_leg_request(p)["request"]
        form = req.get("form_data") or {}
        if req.get("building_use_type") or form.get("building_use_type"):
            present += 1
    assert present == 0


def test_T7_no_facility_type_to_building_use_type_inference():
    src = BRIDGE.read_text(encoding="utf-8")
    assert "facility_type" in src  # UNSUPPORTED inventory only
    assert "facility_type →" not in src
    assert 'building_use_type"] = ' not in src
    sample = {
        "profile_id": "PF-TEST-SP",
        "sector": "SPECIAL_FACILITY",
        "layers": {
            "company": {"region": "서울", "worker_count": 10, "workers": 10},
            "building": {
                "facility_type": "특수연구시설",
                "total_floor_area": 15000.0,
                "floor_area": 15000.0,
            },
            "process": [],
            "facility": [{"code": "has_boiler", "value": True}],
            "work": ["전기작업"],
            "construction": None,
        },
    }
    req = profile_to_leg_request(sample)["request"]
    assert req["sector"] == "BUILDING"
    assert "building_use_type" not in req
    assert (req.get("form_data") or {}).get("building_use_type") is None
    assert req["total_floor_area"] == 15000.0
    assert (req.get("form_data") or {}).get("has_boiler") is True


@needs_universe
def test_T8_request_build_112():
    built, summary = project_universe(_profiles())
    assert summary["request_build"] == 112
    assert summary["fail"] == 0
    assert len(built) == 112
    for item in built:
        DiagnosisRunBody(**item["request"])


@needs_universe
def test_T9_special_dry_free_path_10_of_10():
    for p in _profiles():
        if p.get("sector") != "SPECIAL_FACILITY":
            continue
        item = profile_to_leg_request(p)
        area = item["request"].get("total_floor_area") or item["request"].get("floor_area")
        tier, is_free = _dry_is_free(item["request"]["sector"], area)
        assert item["request"].get("tier") is None
        assert item["request"].get("user_tier") is None
        assert is_free is True
        assert tier == "BUILDING_FREE"


def test_T10_historical_runner_unmutated():
    src = RUNNER.read_text(encoding="utf-8")
    assert "/anonymous-diagnosis" in src
    assert "/diagnosis/run-leg" not in src
    assert "consumer_entry_sector" not in src


@needs_universe
def test_T11_frozen_universe_unmutated():
    before = _sha256(UNIVERSE)
    project_universe(_profiles())
    assert _sha256(UNIVERSE) == before
    assert sum(1 for p in _profiles() if p.get("sector") == "SPECIAL_FACILITY") == 10


def test_T12_live_http_zero_in_bridge():
    src = BRIDGE.read_text(encoding="utf-8")
    assert "urllib" not in src
    assert "requests." not in src
    assert "/diagnosis/run-leg" in src  # documented entrypoint string only


def test_building_use_type_is_optional_on_production_request_model():
    field = DiagnosisRunBody.model_fields["building_use_type"]
    assert field.is_required() is False
    assert field.default is None or field.default is PydanticUndefined or field.default is None
    DiagnosisRunBody(sector="BUILDING")  # missing building_use_type accepted


def test_bridge_does_not_inject_tier():
    src = inspect.getsource(profile_to_leg_request) + inspect.getsource(consumer_entry_sector)
    assert "BUILDING_FREE" not in src
    assert "BUILDING_LARGE_V2" not in src
    assert "BUILDING_V2" not in src
    assert consumer_entry_sector("SPECIAL_FACILITY") == "BUILDING"
    assert consumer_entry_sector("BUILDING") == "BUILDING"
    assert consumer_entry_sector("CONSTRUCTION") == "CONSTRUCTION"
    assert consumer_entry_sector("MANUFACTURING") == "MANUFACTURING"
