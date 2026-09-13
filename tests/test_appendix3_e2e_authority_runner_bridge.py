"""WO-E2E-APPENDIX3-AUTHORITY-RUNNER-BRIDGE-001 — dry projection tests.

No POST /diagnosis/run-leg. No Frozen112 mutation. No Authority mutation.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from schemas.diagnosis_integrated import DiagnosisRunBody
from tools.test_universe.explicit_predicate_authority import (
    DEFAULT_AUTHORITY_PATH,
    PREDICATE_NAMES,
    load_approved_authority_index,
)
from tools.test_universe.leg_bridge import (
    EXPECTED_APPENDIX3_AUTHORITY_SHA256,
    EXPECTED_FROZEN_PROFILE_SHA256,
    EXPECTED_PROFILE_COUNT,
    APPENDIX3_INTERNAL_LEAVES,
    APPENDIX3_SOURCE_KEYS,
    DEFAULT_APPENDIX3_AUTHORITY_PATH,
    BridgeContractError,
    load_approved_appendix3_authority_index,
    load_profile_universe,
    profile_to_leg_request,
    project_universe,
)

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = Path.home() / "45cm-test/profile_universe_v1.json"
BRIDGE = ROOT / "tools/test_universe/leg_bridge.py"
CORE22_AUTHORITY = DEFAULT_AUTHORITY_PATH
APPENDIX3_AUTHORITY = DEFAULT_APPENDIX3_AUTHORITY_PATH
ITEM37_IDS = ("PF-0022", "PF-0082", "PF-0089")
ITEM41_IDS = (
    "PF-0025",
    "PF-0049",
    "PF-0050",
    "PF-0051",
    "PF-0062",
    "PF-0063",
    "PF-0064",
    "PF-0085",
    "PF-0093",
)

needs_universe = pytest.mark.skipif(not UNIVERSE.is_file(), reason="frozen universe missing")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profiles():
    return load_profile_universe(UNIVERSE)["profiles"]


def _pmap():
    return {p["profile_id"]: p for p in _profiles()}


@needs_universe
def test_anchors_unmutated():
    assert _sha256(UNIVERSE) == EXPECTED_FROZEN_PROFILE_SHA256
    assert _sha256(APPENDIX3_AUTHORITY) == EXPECTED_APPENDIX3_AUTHORITY_SHA256
    before_u = _sha256(UNIVERSE)
    before_a = _sha256(APPENDIX3_AUTHORITY)
    project_universe(_profiles())
    assert _sha256(UNIVERSE) == before_u == EXPECTED_FROZEN_PROFILE_SHA256
    assert _sha256(APPENDIX3_AUTHORITY) == before_a == EXPECTED_APPENDIX3_AUTHORITY_SHA256


def test_authority_load_fail_closed():
    index = load_approved_appendix3_authority_index()
    assert len(index) == 75
    assert len(index) == len(set(index))


@needs_universe
def test_dry_112_gated_ungated_counts():
    built, summary = project_universe(_profiles())
    assert summary["request_build"] == EXPECTED_PROFILE_COUNT
    assert summary["fail"] == 0
    assert summary["appendix3_injected"] == 75
    assert summary["ungated_appendix3_injected"] == 0
    assert summary["item37"] == 3
    assert summary["item37_true"] == 3
    assert summary["item41"] == 9
    assert summary["non37_subtype"] == 0
    assert summary["internal_runtime_leaf_injected"] == 0
    assert summary["http_executed"] == 0
    gated = [x for x in built if x["sector"] in {"MANUFACTURING", "BUILDING"}]
    ungated = [x for x in built if x["sector"] not in {"MANUFACTURING", "BUILDING"}]
    assert len(gated) == 75
    assert len(ungated) == 37
    for item in gated:
        req = item["request"]
        form = req.get("form_data") or {}
        assert "appendix3_item_no" in req
        assert all(k not in form for k in APPENDIX3_SOURCE_KEYS)
        assert all(k not in req and k not in form for k in APPENDIX3_INTERNAL_LEAVES)
        DiagnosisRunBody(**req)
    for item in ungated:
        req = item["request"]
        form = req.get("form_data") or {}
        assert all(k not in req and k not in form for k in APPENDIX3_SOURCE_KEYS)
        assert all(k not in req and k not in form for k in APPENDIX3_INTERNAL_LEAVES)


@needs_universe
def test_spot_pf0001_manufacturing_item17():
    req = profile_to_leg_request(_pmap()["PF-0001"])["request"]
    form = req.get("form_data") or {}
    assert req["sector"] == "MANUFACTURING"
    assert req["appendix3_item_no"] == 17
    assert "is_real_estate_management" not in req
    assert "is_real_estate_management" not in form
    assert "appendix3_item_no" not in form


@needs_universe
def test_spot_pf0022_item37_true_top_level():
    req = profile_to_leg_request(_pmap()["PF-0022"])["request"]
    form = req.get("form_data") or {}
    assert req["appendix3_item_no"] == 37
    assert req["is_real_estate_management"] is True
    assert "is_real_estate_management" not in form
    for pid in ITEM37_IDS:
        row = profile_to_leg_request(_pmap()[pid])["request"]
        assert row["appendix3_item_no"] == 37
        assert row["is_real_estate_management"] is True


@needs_universe
def test_spot_pf0025_item41_no_subtype():
    req = profile_to_leg_request(_pmap()["PF-0025"])["request"]
    assert req["appendix3_item_no"] == 41
    assert "is_real_estate_management" not in req
    for pid in ITEM41_IDS:
        row = profile_to_leg_request(_pmap()[pid])["request"]
        assert row["appendix3_item_no"] == 41
        assert "is_real_estate_management" not in row


@needs_universe
def test_spot_pf0028_ungated_core22_unchanged():
    req = profile_to_leg_request(_pmap()["PF-0028"])["request"]
    form = req.get("form_data") or {}
    assert all(k not in req and k not in form for k in APPENDIX3_SOURCE_KEYS)
    index = load_approved_authority_index()
    facts = index["PF-0028"]
    for name in PREDICATE_NAMES:
        assert req[name] is facts[name]
        assert form[name] is facts[name]


@needs_universe
def test_core22_authority_regression_zero():
    index = load_approved_authority_index()
    built, _ = project_universe(_profiles())
    construction = [x for x in built if x["sector"] == "CONSTRUCTION"]
    assert len(construction) == 27
    for item in construction:
        facts = index[item["profile_id"]]
        req = item["request"]
        form = req.get("form_data") or {}
        for name in PREDICATE_NAMES:
            assert req[name] is facts[name]
            assert form[name] is facts[name]


@needs_universe
def test_gated_authority_missing_fail_closed():
    p = copy.deepcopy(_pmap()["PF-0001"])
    index = load_approved_appendix3_authority_index()
    index.pop("PF-0001")
    with pytest.raises(BridgeContractError) as ei:
        profile_to_leg_request(p, appendix3_authority_index=index)
    assert "E2E_FIXTURE_AUTHORITY_MISSING" in str(ei.value)
    assert "PF-0001" in str(ei.value)


@needs_universe
def test_preexisting_appendix3_conflict_fail_closed():
    p = copy.deepcopy(_pmap()["PF-0001"])
    p.setdefault("layers", {}).setdefault("company", {})
    req_first = profile_to_leg_request(p)["request"]
    assert req_first["appendix3_item_no"] == 17
    from tools.test_universe import leg_bridge as lb

    original = lb._put_body

    def _put_with_conflict(body, key, value):
        original(body, key, value)
        if key == "sector" and "appendix3_item_no" not in body:
            body["appendix3_item_no"] = 17

    monkey = pytest.MonkeyPatch()
    monkey.setattr(lb, "_put_body", _put_with_conflict)
    try:
        with pytest.raises(BridgeContractError) as ei:
            profile_to_leg_request(p)
        assert "E2E_FIXTURE_AUTHORITY_CONFLICT" in str(ei.value)
    finally:
        monkey.undo()


def test_bridge_does_not_invent_mapping_or_http():
    src = BRIDGE.read_text(encoding="utf-8")
    assert "urllib" not in src
    assert "requests." not in src
    assert "ksic_name →" not in src
    assert "building_use_type →" not in src
    assert CORE22_AUTHORITY.is_file()
    assert APPENDIX3_AUTHORITY.is_file()
    data = json.loads(APPENDIX3_AUTHORITY.read_text(encoding="utf-8"))
    assert data["production_derivation_rule"] == "NONE"
    assert data["authority_type"] == "OWNER_APPROVED_E2E_FIXTURE_FACT"
