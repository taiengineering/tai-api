"""LEG-FREE-CONSUMER-CONTRACT-WIRING-IMPLEMENT-01 검증.

FREE 3-sector 계약: 소비자 원값이 form_data(flat) -> DiagnosisRunBody ->
step1_body -> build_facility(input) 까지 손실/상수덮어쓰기 없이 보존되는지
step1_body 구성 경계까지 순수 단위 검증. (Supabase/RTM 미접근 - run_step1_func 모킹)
"""
from __future__ import annotations

from typing import Any, Dict

from schemas.diagnosis_integrated import DiagnosisRunBody
from services.diagnosis_nexas_adapter import nexas_run_body_from_request
from services import diagnosis_integrated_svc as svc
from clients.leg_runtime_client import build_facility, _LEG_INPUT_FIELDS


class _StubTable:
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def insert(self, row): self._last = row; return self
    def update(self, *a, **k): return self
    def execute(self):
        class R: pass
        r = R(); r.data = self._rows if self._rows is not None else [{"id": "x"}]
        return r


class _StubSupabase:
    def __init__(self):
        self._auth = [{
            "id": "auth1", "ci_hash": "cihash", "name": "t", "phone": "",
            "free_count": 0, "free_limit": 3, "status": "ACTIVE",
        }]
        self._disc = [{"id": "disc1", "ci_hash": "cihash", "agreed": True}]
        self._ins = [{"id": "res1", "public_token": "tok"}]
    def table(self, name):
        if name == "diagnosis_auth_log": return _StubTable(self._auth)
        if name == "diagnosis_disclaimer_log": return _StubTable(self._disc)
        if name == "anonymous_diagnosis_results": return _StubTable(self._ins)
        return _StubTable([{"id": "x"}])


_CAPTURED: Dict[str, Any] = {}


def _fake_run_step1(supabase, step1_body):
    _CAPTURED["step1_body"] = step1_body
    _CAPTURED["facility"] = build_facility(step1_body)
    return {"status": "success", "data": {"rules_table": [], "applicable_count": 0}}


def _auto_tier(sector, floor_area=0.0, contract_amount_eok=0.0, user_tier=None):
    return {"BUILDING": "BUILDING_FREE", "INDUSTRIAL": "INDUSTRY_FREE",
            "CONSTRUCTION": "CONSTRUCTION_FREE"}.get(sector, "BUILDING_FREE")


def _build_partial(full): return {}
def _now(): return "2026-01-01T00:00:00Z"

_FREE_CODES = frozenset({"BUILDING_FREE", "INDUSTRY_FREE", "CONSTRUCTION_FREE"})
_PRICES: Dict[str, int] = {}


def _run(sector: str, form_data: Dict[str, Any]) -> None:
    _CAPTURED.clear()
    body = nexas_run_body_from_request({
        "auth_token": "tok", "disclaimer_log_id": "disc1",
        "sector": sector, "tier": "FREE", "form_data": form_data,
    })
    svc.run_diagnosis(
        supabase=_StubSupabase(), body=body,
        run_step1_func=_fake_run_step1, auto_tier_func=_auto_tier,
        build_partial_func=_build_partial, now_func=_now,
        paid_tier_prices=_PRICES, free_tier_codes=_FREE_CODES,
        engine_version="test",
    )


def test_construction_worker_count_preserved():
    _run("CONSTRUCTION", {
        "worker_count": 37, "project_address": "seoul",
        "facility": {"worker_count": 37}, "process": [], "equipment": [],
    })
    s1 = _CAPTURED["step1_body"]
    assert s1.worker_count == 37, "step1.worker_count=%r" % s1.worker_count
    assert s1.direct_workers == 37
    assert s1.subcon_workers == 0
    fac = _CAPTURED["facility"]
    if "worker_count" in _LEG_INPUT_FIELDS:
        assert fac.get("worker_count") == 37, "facility.worker_count=%r" % fac.get("worker_count")


def test_industrial_fields_preserved():
    _run("INDUSTRY", {
        "ksic_major": "C25", "worker_count": 88, "total_floor_area": 12345.0,
        "address": "busan",
        "facility": {"ksic_major": "C25", "worker_count": 88, "total_floor_area": 12345.0},
        "process": [], "equipment": [],
    })
    s1 = _CAPTURED["step1_body"]
    assert s1.ksic_major == "C25", "ksic_major=%r" % s1.ksic_major
    assert s1.worker_count == 88, "worker_count=%r" % s1.worker_count
    assert s1.total_floor_area == 12345.0, "total_floor_area=%r" % s1.total_floor_area
    assert s1.total_floor_area != 400.0
    fac = _CAPTURED["facility"]
    for code, val in (("ksic_major", "C25"), ("worker_count", 88), ("total_floor_area", 12345.0)):
        if code in _LEG_INPUT_FIELDS:
            assert fac.get(code) == val, "facility.%s=%r" % (code, fac.get(code))


def test_building_fields_preserved():
    _run("BUILDING", {
        "building_use_type": "factory", "worker_count": 21, "total_floor_area": 6600.0,
        "address": "incheon",
        "facility": {"building_use_type": "factory", "worker_count": 21, "total_floor_area": 6600.0},
        "process": [], "equipment": [],
    })
    s1 = _CAPTURED["step1_body"]
    assert s1.building_use_type == "factory", "building_use_type=%r" % s1.building_use_type
    assert s1.building_use_type != "\uc0ac\ubb34\uc2e4"
    assert s1.worker_count == 21, "worker_count=%r" % s1.worker_count
    assert s1.total_floor_area == 6600.0, "total_floor_area=%r" % s1.total_floor_area
    assert s1.total_floor_area != 400.0
    fac = _CAPTURED["facility"]
    for code, val in (("building_use_type", "factory"), ("worker_count", 21), ("total_floor_area", 6600.0)):
        if code in _LEG_INPUT_FIELDS:
            assert fac.get(code) == val, "facility.%s=%r" % (code, fac.get(code))
