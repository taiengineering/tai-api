"""WO-E2E2000-C02-D-ETA-B-IMPLEMENT-001 — D-η B안 채석작업 독립 입력 국소 테스트.

Owner 결정: D-η = B안 (has_quarrying_work 신규 입력 분리).
PSR mapped_field 변경은 별도 Owner 승인 — 운영 원자 연결 미변경.
LEG 서버 호출 없음. DB 호출 없음. 운영 데이터 변경 없음.

T01: has_excavation=True만 → has_quarrying_work 자동 생성 없음
T02: has_quarrying_work=True → C2(step1.input)+C3(build_facility) 정확히 전달
T03: has_quarrying_work=False → 명시값 보존(누락 아님)
T04: has_quarrying_work=None → 미전달(UNKNOWN 보존)
T05: 기존 EXCAVATION→has_excavation 매핑 불변
T06: 기존 BLASTING→has_blasting 매핑 불변
T07: has_quarrying_work=True → has_excavation 자동 확산 없음
T08: 제374조① 후보 원자 조건 의미 검증 (True/False/None/미제공)
T09: has_excavation 기존 전달 경로 회귀 없음 (323행 보호)
T10: 신규 필드 미포함 기존 C1 요청 호환성 유지
"""
from __future__ import annotations
import copy
import pytest

import services.safe_construction_leg_runtime as cst_rt
from services.safe_construction_leg_runtime import (
    run_safe_construction_leg,
    SAFE_CST_OVERRIDE_FIELDS,
    _C02_QUARRYING_OVERRIDE_FIELDS,
)
from services.cst_process_projector import (
    _APPROVED_PROCESS_MAPPINGS_V1,
    project_cst_process_codes,
    project_cst_work_codes,
)
from schemas.legal_engine import SafeConstructionConsumerInput
from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility


# ── shared fixtures ────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, d): self.data = d

class _Q:
    def __init__(self, store, c): self.store = store; self.c = c; self._f = {}
    def select(self, *a, **k): return self
    def eq(self, col, val): self._f[col] = val; return self
    def in_(self, col, vals): return self
    def limit(self, n): return self
    def order(self, *a, **k): return self
    def insert(self, *a, **k): self.c["writes"] += 1; return self
    def update(self, *a, **k): self.c["writes"] += 1; return self
    def upsert(self, *a, **k): self.c["writes"] += 1; return self
    def delete(self, *a, **k): self.c["writes"] += 1; return self
    def execute(self):
        self.c["reads"] += 1
        rows = [r for r in self.store if all(r.get(k) == v for k, v in self._f.items())]
        return _Res(copy.deepcopy(rows))

class _T:
    def __init__(self, name, store, c): self.name = name; self.store = store; self.c = c
    def select(self, *a, **k): return _Q(self.store, self.c)
    def insert(self, *a, **k): self.c["writes"] += 1; return _Q(self.store, self.c)
    def update(self, *a, **k): self.c["writes"] += 1; return _Q(self.store, self.c)
    def upsert(self, *a, **k): self.c["writes"] += 1; return _Q(self.store, self.c)
    def delete(self, *a, **k): self.c["writes"] += 1; return _Q(self.store, self.c)

class FakeSB:
    def __init__(self, **stores):
        self.stores = {"construction_sites": []}
        self.stores.update(stores)
        self.counters = {"writes": 0, "reads": 0}
    def table(self, n): self.stores.setdefault(n, []); return _T(n, self.stores[n], self.counters)


def _site(**kw):
    base = {"id": "S1", "factory_id": "F1", "total_workers": 30, "direct_workers": 10,
            "subcon_workers": 20, "site_type": "BUILDING", "site_address": "서울",
            "contract_amount": 50}
    base.update(kw)
    return base

def _sb(**kw):
    return FakeSB(construction_sites=[_site()], **kw)


def _patch_leg(monkeypatch, capture):
    def fake_run(step1):
        capture["called"] += 1
        capture["step1"] = step1
        return {"engine_family": "LEG", "sector": "CONSTRUCTION", "status_ok": True}
    monkeypatch.setattr(cst_rt, "run_leg_diagnosis", fake_run)


# ── Registry 사전 확인 ─────────────────────────────────────────────────────────

def test_has_quarrying_work_in_leg_input_fields():
    """has_quarrying_work 는 _LEG_INPUT_FIELDS 에 등록돼야 한다."""
    assert "has_quarrying_work" in _LEG_INPUT_FIELDS


def test_has_quarrying_work_in_c02_override_group():
    """has_quarrying_work 는 _C02_QUARRYING_OVERRIDE_FIELDS 에 포함돼야 한다."""
    assert "has_quarrying_work" in _C02_QUARRYING_OVERRIDE_FIELDS


def test_has_quarrying_work_in_safe_cst_override_fields():
    """has_quarrying_work 는 SAFE_CST_OVERRIDE_FIELDS 에 포함돼야 한다."""
    assert "has_quarrying_work" in SAFE_CST_OVERRIDE_FIELDS


def test_has_quarrying_work_in_schema():
    """SafeConstructionConsumerInput 에 has_quarrying_work 필드가 존재한다."""
    fields = SafeConstructionConsumerInput.model_fields
    assert "has_quarrying_work" in fields
    # 기본값 None (미제공=UNKNOWN)
    obj = SafeConstructionConsumerInput()
    assert obj.has_quarrying_work is None


# ── T01: 일반 굴착만 True → 채석작업 자동 생성 없음 ────────────────────────────

def test_T01_excavation_true_does_not_auto_create_quarrying(monkeypatch):
    """has_excavation=True 만 있을 때 has_quarrying_work 가 C2/C3 에 없어야 한다."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_excavation": True})
    inp = cap["step1"].input
    assert "has_quarrying_work" not in inp, (
        f"has_excavation=True 가 has_quarrying_work 를 자동 생성하면 안 됨: {inp.get('has_quarrying_work')!r}"
    )
    facility = build_facility(cap["step1"])
    assert "has_quarrying_work" not in facility


# ── T02: 채석 True → C2+C3 정확히 전달 ─────────────────────────────────────────

def test_T02_quarrying_true_transported_to_c2(monkeypatch):
    """has_quarrying_work=True → step1.input(C2) 에 True 로 전달된다."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": True})
    assert cap["step1"].input.get("has_quarrying_work") is True


def test_T02_quarrying_true_transported_to_c3(monkeypatch):
    """has_quarrying_work=True → build_facility(C3) 출력에 True 로 전달된다."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": True})
    facility = build_facility(cap["step1"])
    assert facility.get("has_quarrying_work") is True


# ── T03: 채석 False → 명시값 보존 ─────────────────────────────────────────────

def test_T03_quarrying_false_preserved_at_c2(monkeypatch):
    """has_quarrying_work=False 명시값 → C2 에서 False 로 보존(누락 아님)."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": False})
    assert cap["step1"].input.get("has_quarrying_work") is False


def test_T03_quarrying_false_preserved_at_c3(monkeypatch):
    """has_quarrying_work=False → build_facility(C3) 에서 False 로 보존."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": False})
    facility = build_facility(cap["step1"])
    assert facility.get("has_quarrying_work") is False


# ── T04: 채석 None → 미확인 상태 보존 (LEG 미전달) ──────────────────────────────

def test_T04_quarrying_none_absent_from_c2(monkeypatch):
    """has_quarrying_work=None → C2 에서 키 자체가 없어야 한다(UNKNOWN)."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": None})
    assert "has_quarrying_work" not in cap["step1"].input


def test_T04_quarrying_none_absent_from_c3(monkeypatch):
    """has_quarrying_work=None → build_facility(C3) 에서 키 없음(UNKNOWN)."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": None})
    facility = build_facility(cap["step1"])
    assert "has_quarrying_work" not in facility


# ── T05: 기존 EXCAVATION→has_excavation 매핑 불변 ─────────────────────────────

def test_T05_excavation_process_mapping_preserved():
    """cst_process_projector: EXCAVATION 코드 → has_excavation 매핑이 유지된다."""
    assert _APPROVED_PROCESS_MAPPINGS_V1[("kcsc_process_master", "EXCAVATION")] == "has_excavation"


def test_T05_excavation_project_cst_output():
    """project_cst_process_codes(['EXCAVATION']) → {'has_excavation': True}."""
    result = project_cst_process_codes(["EXCAVATION"])
    assert result == {"has_excavation": True}
    assert "has_quarrying_work" not in result


# ── T06: 기존 BLASTING→has_blasting 매핑 불변 ────────────────────────────────

def test_T06_blasting_work_mapping_preserved():
    """cst_process_projector: BLASTING 코드 → has_blasting 매핑이 유지된다."""
    assert _APPROVED_PROCESS_MAPPINGS_V1[("kcsc_work_master", "BLASTING")] == "has_blasting"


def test_T06_blasting_project_cst_output():
    """project_cst_work_codes(['BLASTING']) → {'has_blasting': True}."""
    result = project_cst_work_codes(["BLASTING"])
    assert result == {"has_blasting": True}
    assert "has_quarrying_work" not in result


# ── T07: has_quarrying_work 가 다른 필드에 자동 확산되지 않음 ──────────────────

def test_T07_quarrying_true_does_not_auto_set_excavation(monkeypatch):
    """has_quarrying_work=True 가 has_excavation 을 자동 생성하면 안 된다."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": True})
    inp = cap["step1"].input
    assert inp.get("has_excavation") is None or "has_excavation" not in inp, (
        f"has_quarrying_work=True 가 has_excavation={inp.get('has_excavation')!r} 로 자동 확산됨"
    )


def test_T07_quarrying_true_does_not_spread_to_blasting(monkeypatch):
    """has_quarrying_work=True 가 has_blasting 을 자동 생성하면 안 된다."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": True})
    inp = cap["step1"].input
    assert "has_blasting" not in inp


# ── T08: 제374조① 후보 원자 조건 의미 검증 ───────────────────────────────────
# PSR mapped_field 는 아직 has_excavation. 이 테스트는 has_quarrying_work 입력이
# 정확히 LEG transport 경계까지 전달됨을 확인해 향후 PSR 변경 후 연결 가능성을 보증한다.

def test_T08_quarrying_true_reaches_leg_transport_boundary(monkeypatch):
    """has_quarrying_work=True → LEG transport 경계(C3) 에 전달: 채석조건 충족 후보."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": True})
    facility = build_facility(cap["step1"])
    assert facility.get("has_quarrying_work") is True, "채석작업 조건 충족 후보: True 전달 필요"


def test_T08_quarrying_false_reaches_leg_transport_boundary(monkeypatch):
    """has_quarrying_work=False → LEG transport 경계(C3) 에 전달: 채석조건 불충족 후보."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": False})
    facility = build_facility(cap["step1"])
    assert facility.get("has_quarrying_work") is False, "채석작업 조건 불충족 후보: False 전달 필요"


def test_T08_quarrying_none_means_unknown(monkeypatch):
    """has_quarrying_work=None → C3 에 키 없음: 채석조건 미확인(UNKNOWN)."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_quarrying_work": None})
    facility = build_facility(cap["step1"])
    assert "has_quarrying_work" not in facility, "채석작업 미확인 후보: 키 없어야 함"


def test_T08_quarrying_not_provided_means_unknown(monkeypatch):
    """has_quarrying_work 미제공 → C3 에 키 없음: 채석조건 미확인(UNKNOWN)."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {})
    facility = build_facility(cap["step1"])
    assert "has_quarrying_work" not in facility, "has_quarrying_work 미제공 → 키 없어야 함"


# ── T09: has_excavation 기존 전달 경로 회귀 없음 (323행 보호) ───────────────────

def test_T09_excavation_true_still_transported(monkeypatch):
    """has_excavation=True 는 기존대로 C2+C3 에 전달된다 (PAT-09-01 323행 회귀 없음)."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_excavation": True})
    assert cap["step1"].input.get("has_excavation") is True
    facility = build_facility(cap["step1"])
    assert facility.get("has_excavation") is True


def test_T09_excavation_false_still_preserved(monkeypatch):
    """has_excavation=False 명시값 → 기존대로 C2+C3 에 보존."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {"has_excavation": False})
    assert cap["step1"].input.get("has_excavation") is False
    facility = build_facility(cap["step1"])
    assert facility.get("has_excavation") is False


def test_T09_excavation_and_quarrying_independent(monkeypatch):
    """has_excavation 과 has_quarrying_work 는 독립 — 함께 제공 시 각각 보존."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(
        _sb(), "S1",
        {"has_excavation": True, "has_quarrying_work": False},
    )
    inp = cap["step1"].input
    assert inp.get("has_excavation") is True
    assert inp.get("has_quarrying_work") is False
    facility = build_facility(cap["step1"])
    assert facility.get("has_excavation") is True
    assert facility.get("has_quarrying_work") is False


# ── T10: 기존 C1 요청에서 신규 필드 생략 시 호환성 ────────────────────────────

def test_T10_existing_request_without_quarrying_works(monkeypatch):
    """기존 C1 요청(has_quarrying_work 없음) → 정상 동작, has_quarrying_work 없음."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(
        _sb(), "S1",
        {"has_excavation": True, "has_blasting": False},
    )
    assert cap["called"] == 1
    assert cap["step1"].input.get("has_excavation") is True
    assert cap["step1"].input.get("has_blasting") is False
    assert "has_quarrying_work" not in cap["step1"].input


def test_T10_schema_allows_omitting_quarrying_field():
    """SafeConstructionConsumerInput 에서 has_quarrying_work 생략 가능 (default None)."""
    obj = SafeConstructionConsumerInput(has_excavation=True)
    assert obj.has_quarrying_work is None
    assert obj.has_excavation is True


def test_T10_schema_extra_forbid_still_active():
    """extra=forbid 는 그대로 — 미등록 필드 거부."""
    with pytest.raises(Exception):
        SafeConstructionConsumerInput(unknown_field_xyz=True)
