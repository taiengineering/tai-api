"""WO-SM-CORE22-E2E-112-BRIDGE-CONTRACT-001 — T1~T13 contract tests.

Does not POST /diagnosis/run-leg. Does not mutate BEFORE_BASELINE_V1.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "test_universe"))

from leg_bridge import (  # noqa: E402
    EXPECTED_ID_RANGE,
    EXPECTED_PROFILE_COUNT,
    BridgeContractError,
    assert_universe_integrity,
    load_profile_universe,
    profile_to_leg_request,
    project_universe,
)

UNIVERSE = Path(os.environ.get(
    "PROFILE_UNIVERSE_PATH",
    str(Path.home() / "45cm-test" / "profile_universe_v1.json"),
)).expanduser()
RUNNER = ROOT / "tools" / "test_universe" / "e2e_runner_all.py"
BASELINE = Path.home() / "45cm-test" / "baseline_snapshot_set_v1.json"

needs_universe = pytest.mark.skipif(
    not UNIVERSE.is_file(),
    reason=f"frozen universe not present: {UNIVERSE}",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_profiles():
    return load_profile_universe(UNIVERSE)["profiles"]


@needs_universe
def test_T1_profile_universe_load_112():
    profiles = _load_profiles()
    assert len(profiles) == EXPECTED_PROFILE_COUNT


@needs_universe
def test_T2_profile_ids_exact():
    ids = [p["profile_id"] for p in _load_profiles()]
    assert sorted(ids) == sorted(EXPECTED_ID_RANGE)


@needs_universe
def test_T3_duplicate_profile_zero():
    ids = [p["profile_id"] for p in _load_profiles()]
    assert len(ids) == len(set(ids))


@needs_universe
def test_T4_112_request_build():
    built, summary = project_universe(_load_profiles())
    assert summary["request_build"] == EXPECTED_PROFILE_COUNT
    assert summary["fail"] == 0
    assert len(built) == EXPECTED_PROFILE_COUNT
    assert summary["type_counts"].get("GAP", 0) == 0
    for item in built:
        assert "factory_id" not in item["request"]
        assert "company_id" not in item["request"]
        assert "project_amount" not in item["request"]
        assert "auth_token" not in item["request"]
        assert item["mapping_gaps"] == []


@needs_universe
def test_T5_source_profile_mutation_zero():
    before = _sha256(UNIVERSE)
    project_universe(_load_profiles())
    assert _sha256(UNIVERSE) == before


@needs_universe
def test_T6_existing_baseline_artifact_mutation_zero():
    hashes = {}
    for path in (UNIVERSE, BASELINE, RUNNER):
        if path.is_file():
            hashes[str(path)] = _sha256(path)
    project_universe(_load_profiles())
    for path, digest in hashes.items():
        assert _sha256(Path(path)) == digest


def test_T7_existing_e2e_runner_all_behavior_unmutated():
    src = RUNNER.read_text(encoding="utf-8")
    assert "POST" in src or "ENDPOINT" in src
    assert "/anonymous-diagnosis" in src
    assert "/diagnosis/run-leg" not in src
    assert "site_kind" in src
    assert "contract_amount_eok" not in src
    # This test file and leg_bridge.py are the new consumer; runner stays historical.


@needs_universe
def test_T8_construction_profiles_27():
    profiles = _load_profiles()
    con = [p for p in profiles if p.get("sector") == "CONSTRUCTION"]
    assert len(con) == 27
    built, summary = project_universe(profiles)
    assert summary["construction_profiles"] == 27
    for item in built:
        if item["sector"] != "CONSTRUCTION":
            continue
        assert "contract_amount_eok" in item["request"]


@needs_universe
def test_T9_pf0052_0057_amount_lossless():
    expected = {
        "PF-0052": 49,
        "PF-0053": 50,
        "PF-0054": 51,
        "PF-0055": 119,
        "PF-0056": 120,
        "PF-0057": 121,
    }
    pmap = {p["profile_id"]: p for p in _load_profiles()}
    for pid, eok in expected.items():
        src = pmap[pid]["layers"]["construction"]["contract_amount_eok"]
        assert src == eok
        req = profile_to_leg_request(pmap[pid])["request"]
        assert req["contract_amount_eok"] == eok
        assert req["contract_amount_eok"] == src
        assert "project_amount" not in req


def test_T10_missing_required_official_input_fail_closed():
    with pytest.raises(BridgeContractError) as ei:
        profile_to_leg_request({"profile_id": "PF-XXXX", "layers": {}})
    assert "SECTOR" in str(ei.value)


@needs_universe
def test_T11_unsupported_not_silently_dropped():
    built, _ = project_universe(_load_profiles())
    any_unsupported = False
    for item in built:
        for rec in item["records"]:
            if rec["mapping_type"] == "UNSUPPORTED":
                any_unsupported = True
                names = {u["source_field"] for u in item["unsupported_fields"]}
                assert rec["source_field"] in names
                assert rec["source_field"] in item["omitted_source_fields"]
        for u in item["unsupported_fields"]:
            assert u.get("source_field")
            assert u.get("evidence")
    assert any_unsupported  # work/process/scale exist in universe


def test_T12_synthetic_default_zero():
    src = Path(ROOT / "tools" / "test_universe" / "leg_bridge.py").read_text(encoding="utf-8")
    assert "400.0" not in src
    assert "contract_amount_eok = 1" not in src
    assert 'construction_type"] = "건축"' not in src
    sample = {
        "profile_id": "PF-TEST",
        "sector": "BUILDING",
        "layers": {
            "company": {"region": "서울", "worker_count": 10, "ksic_major": "F"},
            "building": {"building_use_type": "사무실"},
            "process": [],
            "facility": [],
            "work": [],
            "construction": None,
        },
    }
    req = profile_to_leg_request(sample)["request"]
    assert "floor_area" not in req
    assert "total_floor_area" not in req
    assert "contract_amount_eok" not in req
    assert req.get("floor_count") is None or "floor_count" not in req


def test_T13_core22_ap_hardcode_zero():
    src = Path(ROOT / "tools" / "test_universe" / "leg_bridge.py").read_text(encoding="utf-8")
    cli = Path(ROOT / "tools" / "test_universe" / "leg_bridge_cli.py").read_text(encoding="utf-8")
    blob = src + cli
    for needle in (
        "AP-06", "AP-07", "AP-08", "AP-17",
        "7ba9bdde", "fa46b294", "12329b54", "336c5672",
        "Golden", "expected obligation",
    ):
        assert needle not in blob


@needs_universe
def test_workers_mismatch_fail_closed():
    p = copy.deepcopy(_load_profiles()[0])
    p["layers"]["company"]["workers"] = 999999
    p["layers"]["company"]["worker_count"] = 1
    with pytest.raises(BridgeContractError) as ei:
        profile_to_leg_request(p)
    assert "WORKERS_NE_WORKER_COUNT" in str(ei.value)
