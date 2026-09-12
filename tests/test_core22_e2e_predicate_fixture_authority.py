"""WO-SM-E2E-CANONICAL-PREDICATE-FIXTURE-AUTHORITY-001 — T1~T15.

No POST /diagnosis/run-leg. No Frozen112 mutation. No quota. No Clean112.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from schemas.diagnosis_integrated import DiagnosisRunBody
from tools.test_universe.explicit_predicate_authority import (
    AUTHORITY_MISSING,
    DEFAULT_AUTHORITY_PATH,
    PREDICATE_NAMES,
    FixtureAuthorityError,
    build_authority_index,
    load_approved_authority_index,
    require_construction_facts,
)
from tools.test_universe.leg_bridge import (
    BridgeContractError,
    load_profile_universe,
    profile_to_leg_request,
    project_universe,
)

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = Path.home() / "45cm-test/profile_universe_v1.json"
AUTHORITY = DEFAULT_AUTHORITY_PATH
BRIDGE = ROOT / "tools/test_universe/leg_bridge.py"
AUTHORITY_PY = ROOT / "tools/test_universe/explicit_predicate_authority.py"
FROZEN_SHA = "4818a63ab261c5a36c1432647b6b17e7636641071801d36fd1b85d1361af751b"
CONSTRUCTION_IDS = [
    "PF-0028", "PF-0029", "PF-0030", "PF-0031", "PF-0032", "PF-0033",
    "PF-0034", "PF-0035", "PF-0036",
    "PF-0052", "PF-0053", "PF-0054", "PF-0055", "PF-0056", "PF-0057",
    "PF-0094", "PF-0095", "PF-0096", "PF-0097", "PF-0098", "PF-0099",
    "PF-0100", "PF-0101", "PF-0102", "PF-0103", "PF-0104", "PF-0105",
]
REL_TRUE = {"PF-0033"}
CIVIL_TRUE = {
    "PF-0030", "PF-0031", "PF-0036", "PF-0095", "PF-0096", "PF-0101", "PF-0103",
}
EOK = {
    "PF-0052": 49,
    "PF-0053": 50,
    "PF-0054": 51,
    "PF-0055": 119,
    "PF-0056": 120,
    "PF-0057": 121,
}

needs_universe = pytest.mark.skipif(not UNIVERSE.is_file(), reason="frozen universe missing")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _profiles():
    return load_profile_universe(UNIVERSE)["profiles"]


def _construction_profile(pid: str) -> dict:
    return copy.deepcopy(next(p for p in _profiles() if p["profile_id"] == pid))


@needs_universe
def test_T1_frozen112_unchanged():
    assert _sha256(UNIVERSE) == FROZEN_SHA
    before = _sha256(UNIVERSE)
    project_universe(_profiles())
    assert _sha256(UNIVERSE) == before == FROZEN_SHA


@needs_universe
def test_T2_construction_exact_27():
    ids = [p["profile_id"] for p in _profiles() if p.get("sector") == "CONSTRUCTION"]
    assert ids == CONSTRUCTION_IDS
    assert len(ids) == 27


def test_T3_approved_authority_exact_27():
    data = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    assert data["status"] == "APPROVED"
    assert data["authority_type"] == "OWNER_APPROVED_E2E_FIXTURE_FACT"
    assert data["construction_profile_count"] == 27
    ids = [r["profile_id"] for r in data["profiles"]]
    assert ids == CONSTRUCTION_IDS
    index = load_approved_authority_index()
    assert set(index) == set(CONSTRUCTION_IDS)
    assert len(index) == 27


def test_T4_no_duplicate_ids():
    data = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    ids = [r["profile_id"] for r in data["profiles"]]
    assert len(ids) == len(set(ids)) == 27


def test_T5_no_extra_ids():
    data = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    ids = [r["profile_id"] for r in data["profiles"]]
    assert set(ids) == set(CONSTRUCTION_IDS)
    extra = set(ids) - set(CONSTRUCTION_IDS)
    assert extra == set()


def test_T6_all_81_values_bool():
    data = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    n = 0
    for row in data["profiles"]:
        for name in PREDICATE_NAMES:
            assert type(row[name]) is bool
            n += 1
    assert n == 81


def test_T7_null_zero():
    blob = AUTHORITY.read_text(encoding="utf-8")
    data = json.loads(blob)
    for row in data["profiles"]:
        for name in PREDICATE_NAMES:
            assert row[name] is not None
    assert ": null" not in blob
    assert blob.count("true") + blob.count("false") >= 81


@needs_universe
def test_T8_missing_row_fail_closed():
    p = _construction_profile("PF-0028")
    index = load_approved_authority_index()
    del index["PF-0028"]
    with pytest.raises(BridgeContractError) as ei:
        profile_to_leg_request(p, authority_index=index)
    assert AUTHORITY_MISSING in str(ei.value)


@needs_universe
def test_T9_invalid_string_true_fail_closed():
    p = _construction_profile("PF-0028")
    index = load_approved_authority_index()
    index["PF-0028"] = {
        "is_construction": "true",  # type: ignore[dict-item]
        "is_relationship_contractor": False,
        "is_civil_construction": False,
    }
    with pytest.raises(BridgeContractError) as ei:
        profile_to_leg_request(p, authority_index=index)
    assert AUTHORITY_MISSING in str(ei.value)
    with pytest.raises(FixtureAuthorityError) as e2:
        require_construction_facts("PF-0028", index)
    assert AUTHORITY_MISSING in str(e2.value)


@needs_universe
def test_T10_non_construction_injection_zero():
    built, summary = project_universe(_profiles())
    injected = 0
    for item in built:
        if item["sector"] == "CONSTRUCTION":
            continue
        req = item["request"]
        form = req.get("form_data") or {}
        for name in PREDICATE_NAMES:
            if name in req or name in form:
                injected += 1
    assert injected == 0
    assert summary["non_construction_predicate_injection"] == 0


@needs_universe
def test_T11_raw_fields_alone_cannot_generate_predicates():
    p = _construction_profile("PF-0033")
    assert p["layers"]["construction"]["order_type"] == "하도급"
    p_civil = _construction_profile("PF-0030")
    assert p_civil["layers"]["construction"]["construction_type_code"] == "CIVIL"
    with pytest.raises(BridgeContractError) as ei:
        profile_to_leg_request(p, authority_index={})
    assert AUTHORITY_MISSING in str(ei.value)
    src_auth = AUTHORITY_PY.read_text(encoding="utf-8")
    src_bridge = BRIDGE.read_text(encoding="utf-8")
    assert "layers" not in src_auth
    assert '.get("order_type")' not in src_auth
    assert '.get("construction_type_code")' not in src_auth
    assert "require_construction_facts" in src_bridge
    assert 'construction["order_type"]' not in src_bridge
    assert 'is_relationship_contractor"] =' not in src_bridge
    assert 'is_civil_construction"] =' not in src_bridge
    assert 'is_construction"] = True' not in src_bridge


@needs_universe
def test_T12_approved_false_preserved():
    req = profile_to_leg_request(_construction_profile("PF-0028"))["request"]
    assert req["is_relationship_contractor"] is False
    assert req["is_civil_construction"] is False
    assert req["is_construction"] is True
    boundary = profile_to_leg_request(_construction_profile("PF-0052"))["request"]
    assert boundary["is_construction"] is True
    assert boundary["is_relationship_contractor"] is False
    assert boundary["is_civil_construction"] is False


@needs_universe
def test_T13_approved_true_preserved():
    rel = profile_to_leg_request(_construction_profile("PF-0033"))["request"]
    assert rel["is_relationship_contractor"] is True
    civil = profile_to_leg_request(_construction_profile("PF-0030"))["request"]
    assert civil["is_civil_construction"] is True
    assert civil["is_construction"] is True


@needs_universe
def test_T14_request_top_level_exact_bool():
    built, summary = project_universe(_profiles())
    assert summary["request_build"] == 112
    assert summary["construction_predicates_complete"] == 27
    for item in built:
        if item["sector"] != "CONSTRUCTION":
            continue
        req = item["request"]
        form = req.get("form_data") or {}
        expected_rel = item["profile_id"] in REL_TRUE
        expected_civil = item["profile_id"] in CIVIL_TRUE
        for name in PREDICATE_NAMES:
            assert type(req[name]) is bool
            assert type(form[name]) is bool
            assert req[name] == form[name]
        assert req["is_construction"] is True
        assert req["is_relationship_contractor"] is expected_rel
        assert req["is_civil_construction"] is expected_civil
        DiagnosisRunBody(**req)


@needs_universe
def test_T15_pf0052_57_eok_unchanged():
    pmap = {p["profile_id"]: p for p in _profiles()}
    for pid, eok in EOK.items():
        src = pmap[pid]["layers"]["construction"]["contract_amount_eok"]
        assert src == eok
        req = profile_to_leg_request(pmap[pid])["request"]
        assert req["contract_amount_eok"] == eok
        assert req["is_construction"] is True
        assert req["is_relationship_contractor"] is False
        assert req["is_civil_construction"] is False


def test_candidate_status_rejected():
    with pytest.raises(FixtureAuthorityError) as ei:
        build_authority_index({"status": "CANDIDATE", "authority_type": "OWNER_APPROVED_E2E_FIXTURE_FACT", "profiles": []})
    assert AUTHORITY_MISSING in str(ei.value)
