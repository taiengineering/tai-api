"""R13: WIRING-013 router — company_id 전달 + ChemicalSourceLoadError 503.

대상: routers/legal_engine.py (diagnose_industrial_leg / construction_leg / building_leg).
목표: SAFE 라우터 3개에서 인증된 company_id 가 run_safe_*_leg() 에 전달되는지 검증.
     ChemicalSourceLoadError → HTTP 503. CONSTRUCTION factory 회사 불일치 → 403.
     기존 에러 경로(LegDiagnosisError→502, ConstructionSiteBridgeError→409) 회귀 없음.

제약: 실제 외부 API 호출 0 / LEG C4 0 / DB Write 0.
"""
from __future__ import annotations
import asyncio
import pytest
from unittest.mock import MagicMock

from fastapi import HTTPException

from clients.chem_internal_client import ChemicalSourceLoadError
from services.safe_construction_leg_runtime import ConstructionSiteBridgeError
from services.leg_diagnosis_svc import LegDiagnosisError
from schemas.legal_engine import (
    SafeIndustrialLegBody, SafeConstructionLegBody, SafeBuildingLegBody,
    SafeIndustrialConsumerInput, SafeConstructionConsumerInput, SafeBuildingConsumerInput,
)

_COMPANY_ID = "cid-wiring013"
_FACTORY_ID = "fac-wiring013"
_SITE_ID = "site-wiring013"
_LEG_OUT = {"full_result": {}, "contract_version": "V1", "unresolved_fields": []}
_CST_OUT = {**_LEG_OUT, "factory_id": _FACTORY_ID}


class _FakeSupa:
    """라우터 레벨 supabase stub. construction_sites/factories/scope 3개 테이블 커버."""

    def __init__(self, factory_company_id: str = _COMPANY_ID):
        self._last_table: str | None = None
        self._factory_company_id = factory_company_id

    def table(self, name: str):
        self._last_table = name
        return self

    def select(self, *a, **kw):
        return self

    def eq(self, col, val):
        return self

    def limit(self, n):
        return self

    def execute(self):
        r = MagicMock()
        if self._last_table == "construction_sites":
            r.data = [{"company_id": _COMPANY_ID, "factory_id": _FACTORY_ID}]
        elif self._last_table == "factories":
            r.data = [{"company_id": self._factory_company_id}]
        elif self._last_table == "saas_contract_site_scopes":
            r.data = [{"entity_id": _SITE_ID}]
        else:
            r.data = []
        return r


def _patch_chain(monkeypatch, supa: _FakeSupa | None = None):
    """인증·소유권·Entitlement·Scope 체인 전체 stub."""
    if supa is None:
        supa = _FakeSupa()
    monkeypatch.setattr("routers.legal_engine.get_supabase", lambda: supa)
    monkeypatch.setattr("routers.legal_engine.get_current_user",
                        lambda auth: {"company_id": _COMPANY_ID})
    monkeypatch.setattr("routers.legal_engine._ensure_factory_own", lambda *a, **kw: None)
    monkeypatch.setattr("routers.legal_engine._ensure_own_company", lambda *a, **kw: None)
    monkeypatch.setattr("routers.legal_engine.require_active_company_saas", lambda *a, **kw: None)
    _res = MagicMock()
    _res.commercial_version_id = "cv-001"
    monkeypatch.setattr("routers.legal_engine._assert_leg_compliance_core_http",
                        lambda *a, **kw: _res)
    monkeypatch.setattr("routers.legal_engine._assert_leg_site_scope_http",
                        lambda *a, **kw: None)
    monkeypatch.setattr("routers.legal_engine.leg_runtime_client.is_enabled", lambda: True)
    monkeypatch.setattr("routers.legal_engine.check_saas_appendix3_contract",
                        lambda *a, **kw: None)
    monkeypatch.setattr("routers.legal_engine._finalize_saas_leg_http",
                        lambda *a, **kw: {"ok": True})


def _run(coro):
    return asyncio.run(coro)


# ─── R13-01 INDUSTRIAL company_id 전달 ──────────────────────────────────────

def test_R13_01_industrial_company_id_forwarded(monkeypatch):
    """run_safe_industrial_leg 호출 시 company_id=_COMPANY_ID 가 kwargs에 포함된다."""
    _patch_chain(monkeypatch)
    captured = {}

    def fake_run(supa, factory_id, consumer_input, *, app3_projection=None, company_id=None):
        captured["company_id"] = company_id
        return _LEG_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_industrial_leg", fake_run)

    body = SafeIndustrialLegBody(factory_id=_FACTORY_ID, input=SafeIndustrialConsumerInput())
    from routers.legal_engine import diagnose_industrial_leg
    _run(diagnose_industrial_leg(body, authorization="Bearer tok"))

    assert captured["company_id"] == _COMPANY_ID, f"company_id 전달 실패: {captured}"


# ─── R13-02 CONSTRUCTION company_id 전달 ────────────────────────────────────

def test_R13_02_construction_company_id_forwarded(monkeypatch):
    """run_safe_construction_leg 호출 시 company_id=_COMPANY_ID 가 kwargs에 포함된다."""
    _patch_chain(monkeypatch)
    captured = {}

    def fake_run(supa, site_id, consumer_input, *, subcontract_legal_event_id=None,
                 subcontractor_id=None, app3_projection=None, company_id=None):
        captured["company_id"] = company_id
        return _CST_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_construction_leg", fake_run)

    body = SafeConstructionLegBody(site_id=_SITE_ID, input=SafeConstructionConsumerInput())
    from routers.legal_engine import diagnose_construction_leg
    _run(diagnose_construction_leg(body, authorization="Bearer tok"))

    assert captured["company_id"] == _COMPANY_ID, f"company_id 전달 실패: {captured}"


# ─── R13-03 BUILDING company_id 전달 ────────────────────────────────────────

def test_R13_03_building_company_id_forwarded(monkeypatch):
    """run_safe_building_leg 호출 시 company_id=_COMPANY_ID 가 kwargs에 포함된다."""
    _patch_chain(monkeypatch)
    captured = {}

    def fake_run(supa, factory_id, consumer_input, *, material_inout_event_id=None,
                 occupancy_assessment_id=None, app3_projection=None, company_id=None):
        captured["company_id"] = company_id
        return _LEG_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_building_leg", fake_run)

    body = SafeBuildingLegBody(factory_id=_FACTORY_ID, input=SafeBuildingConsumerInput())
    from routers.legal_engine import diagnose_building_leg
    _run(diagnose_building_leg(body, authorization="Bearer tok"))

    assert captured["company_id"] == _COMPANY_ID, f"company_id 전달 실패: {captured}"


# ─── R13-04 INDUSTRIAL ChemicalSourceLoadError → 503 ───────────────────────

def test_R13_04_industrial_chem_error_503(monkeypatch):
    """run_safe_industrial_leg 에서 ChemicalSourceLoadError 발생 시 HTTP 503 반환."""
    _patch_chain(monkeypatch)

    def fake_run(*a, **kw):
        raise ChemicalSourceLoadError("timeout")

    monkeypatch.setattr("routers.legal_engine.run_safe_industrial_leg", fake_run)

    body = SafeIndustrialLegBody(factory_id=_FACTORY_ID, input=SafeIndustrialConsumerInput())
    from routers.legal_engine import diagnose_industrial_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_industrial_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "CHEM_SOURCE_UNAVAILABLE"
    assert "timeout" not in str(exc_info.value.detail)  # 내부 정보 미노출


# ─── R13-05 CONSTRUCTION ChemicalSourceLoadError → 503 ──────────────────────

def test_R13_05_construction_chem_error_503(monkeypatch):
    """run_safe_construction_leg 에서 ChemicalSourceLoadError 발생 시 HTTP 503 반환."""
    _patch_chain(monkeypatch)

    def fake_run(*a, **kw):
        raise ChemicalSourceLoadError("network error")

    monkeypatch.setattr("routers.legal_engine.run_safe_construction_leg", fake_run)

    body = SafeConstructionLegBody(site_id=_SITE_ID, input=SafeConstructionConsumerInput())
    from routers.legal_engine import diagnose_construction_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_construction_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "CHEM_SOURCE_UNAVAILABLE"
    assert "network" not in str(exc_info.value.detail)  # 내부 정보 미노출


# ─── R13-06 BUILDING ChemicalSourceLoadError → 503 ──────────────────────────

def test_R13_06_building_chem_error_503(monkeypatch):
    """run_safe_building_leg 에서 ChemicalSourceLoadError 발생 시 HTTP 503 반환."""
    _patch_chain(monkeypatch)

    def fake_run(*a, **kw):
        raise ChemicalSourceLoadError("HTTP 502: bad gateway")

    monkeypatch.setattr("routers.legal_engine.run_safe_building_leg", fake_run)

    body = SafeBuildingLegBody(factory_id=_FACTORY_ID, input=SafeBuildingConsumerInput())
    from routers.legal_engine import diagnose_building_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_building_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "CHEM_SOURCE_UNAVAILABLE"


# ─── R13-07 CONSTRUCTION factory 회사 불일치 → 403 ───────────────────────────

def test_R13_07_construction_factory_company_mismatch_403(monkeypatch):
    """CONSTRUCTION: site 소유권은 통과했으나 factory company_id 불일치 → HTTP 403."""
    supa = _FakeSupa(factory_company_id="cid-DIFFERENT-COMPANY")
    _patch_chain(monkeypatch, supa=supa)

    called = {"n": 0}

    def fake_run(*a, **kw):
        called["n"] += 1
        return _CST_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_construction_leg", fake_run)

    body = SafeConstructionLegBody(site_id=_SITE_ID, input=SafeConstructionConsumerInput())
    from routers.legal_engine import diagnose_construction_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_construction_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 403
    assert called["n"] == 0, "factory 회사 불일치 시 run_safe_construction_leg 호출 금지"


# ─── R13-08 INDUSTRIAL company_id 빈 문자열 → 403 (A15 CHEM guard) ───────────

def test_R13_08_industrial_empty_company_id_403(monkeypatch):
    """current에 company_id=None인 경우 A15 CHEM guard → HTTP 403 (CHEM 미호출, runtime 미호출).

    WIRING-015 이전: 빈 문자열이 그대로 전달되어 CHEM 클라이언트에서 차단됨.
    WIRING-015 이후: 라우터 레벨 _ensure_factory_company_match에서 403 차단.
    """
    _patch_chain(monkeypatch)
    monkeypatch.setattr("routers.legal_engine.get_current_user",
                        lambda auth: {"company_id": None})
    called = {"n": 0}

    def fake_run(supa, factory_id, consumer_input, *, app3_projection=None, company_id=None):
        called["n"] += 1
        return _LEG_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_industrial_leg", fake_run)

    body = SafeIndustrialLegBody(factory_id=_FACTORY_ID, input=SafeIndustrialConsumerInput())
    from routers.legal_engine import diagnose_industrial_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_industrial_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 403
    assert called["n"] == 0, "빈 company_id 시 run_safe_industrial_leg 호출 금지"


# ─── R13-09 INDUSTRIAL LegDiagnosisError → 502 (회귀 없음) ─────────────────

def test_R13_09_industrial_leg_diagnosis_error_502(monkeypatch):
    """기존 LegDiagnosisError → HTTP 502 경로가 WIRING-013 이후에도 유지된다."""
    _patch_chain(monkeypatch)

    def fake_run(*a, **kw):
        raise LegDiagnosisError("LEG 내부 오류")

    monkeypatch.setattr("routers.legal_engine.run_safe_industrial_leg", fake_run)

    body = SafeIndustrialLegBody(factory_id=_FACTORY_ID, input=SafeIndustrialConsumerInput())
    from routers.legal_engine import diagnose_industrial_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_industrial_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 502


# ─── R13-10 CONSTRUCTION ConstructionSiteBridgeError → 409 (회귀 없음) ──────

def test_R13_10_construction_bridge_error_409(monkeypatch):
    """기존 ConstructionSiteBridgeError → HTTP 409 경로가 WIRING-013 이후에도 유지된다."""
    _patch_chain(monkeypatch)

    def fake_run(*a, **kw):
        raise ConstructionSiteBridgeError("현장과 시설 연결 없음")

    monkeypatch.setattr("routers.legal_engine.run_safe_construction_leg", fake_run)

    body = SafeConstructionLegBody(site_id=_SITE_ID, input=SafeConstructionConsumerInput())
    from routers.legal_engine import diagnose_construction_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_construction_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 409
