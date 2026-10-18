"""CHEM-WO-LEG-INPUT-A1-ADMIN-FACTORY-BOUNDARY-015 — A15 테스트

Goal: G-mvea8195-8ef927

커버리지:
  A15-01~04  services.company_scope._ensure_factory_company_match (unit)
  A15-05~07  routers.legal_engine.diagnose_industrial_leg admin 경계
  A15-08~10  routers.legal_engine.diagnose_building_leg admin 경계
  A15-11~13  routers.legal_engine.diagnose_construction_leg 회귀 (A15 미호출 확인)
  A15-14~16  정적: no _is_admin bypass / INDUSTRIAL·BUILDING 호출 확인
  A15-17     R13-08 행동 변화 확인 (빈 company_id → 403)

원칙:
  - _ensure_factory_company_match 에 _is_admin 우회 없음
  - INDUSTRIAL·BUILDING: 다른 회사 factory → 403 차단
  - CONSTRUCTION: 기존 factory-company 검증 유지, A15 guard 미삽입
  - empty company_id → 403 (라우터 레벨 차단)
  - DB Write 0 / 외부 API 0 / LEG C4 0
"""
from __future__ import annotations

import asyncio
import inspect
import pytest
from unittest.mock import MagicMock

from fastapi import HTTPException

from schemas.legal_engine import (
    SafeIndustrialLegBody, SafeBuildingLegBody, SafeConstructionLegBody,
    SafeIndustrialConsumerInput, SafeBuildingConsumerInput, SafeConstructionConsumerInput,
)

_COMPANY_A = "cid-company-A"
_COMPANY_B = "cid-company-B"
_FACTORY_A = "fac-belongs-to-A"
_FACTORY_B = "fac-belongs-to-B"
_SITE_ID = "site-015"

_LEG_OUT = {"full_result": {}, "contract_version": "V1", "unresolved_fields": []}
_CST_OUT = {**_LEG_OUT, "factory_id": _FACTORY_A}


# ─────────────────────────────────────────────────────────────────────────────
# Supabase stub
# ─────────────────────────────────────────────────────────────────────────────

class _FakeSupa:
    """factories / construction_sites 쿼리 stub.

    factory_company_map: factory_id → company_id 매핑.
    site_company_id: construction_sites 쿼리용 회사 ID.
    site_factory_id: construction_sites 쿼리용 factory_id.
    """

    def __init__(
        self,
        factory_company_map: dict | None = None,
        site_company_id: str = _COMPANY_A,
        site_factory_id: str = _FACTORY_A,
    ):
        self._last_table: str | None = None
        self._last_factory_id: str | None = None
        self._factory_company_map = (
            {_FACTORY_A: _COMPANY_A, _FACTORY_B: _COMPANY_B}
            if factory_company_map is None
            else factory_company_map
        )
        self._site_company_id = site_company_id
        self._site_factory_id = site_factory_id

    def table(self, name: str):
        self._last_table = name
        return self

    def select(self, *a, **kw):
        return self

    def eq(self, col, val):
        if col == "id" and self._last_table == "factories":
            self._last_factory_id = val
        return self

    def limit(self, n):
        return self

    def execute(self):
        r = MagicMock()
        if self._last_table == "factories":
            fid = self._last_factory_id
            cid = self._factory_company_map.get(fid)
            r.data = [{"company_id": cid}] if cid else []
        elif self._last_table == "construction_sites":
            r.data = [{"company_id": self._site_company_id, "factory_id": self._site_factory_id}]
        else:
            r.data = []
        return r


def _patch_chain(monkeypatch, supa=None, company_id=_COMPANY_A):
    """인증·소유권·Entitlement·Scope 체인 stub. _ensure_factory_company_match 는 real."""
    if supa is None:
        supa = _FakeSupa()
    monkeypatch.setattr("routers.legal_engine.get_supabase", lambda: supa)
    monkeypatch.setattr("routers.legal_engine.get_current_user",
                        lambda auth: {"company_id": company_id})
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


# ─────────────────────────────────────────────────────────────────────────────
# A15-01~04 — _ensure_factory_company_match 유닛
# ─────────────────────────────────────────────────────────────────────────────

class TestEnsureFactoryCompanyMatch:

    def _make_supa(self, factory_company_id: str | None, factory_exists: bool = True):
        sb = MagicMock()
        row = MagicMock()
        row.data = [{"company_id": factory_company_id}] if factory_exists else []
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = row
        return sb

    def test_A15_01_matching_company_id_no_exception(self):
        """A15-01: factory.company_id == company_id → 예외 없음."""
        from services.company_scope import _ensure_factory_company_match
        sb = self._make_supa(_COMPANY_A)
        _ensure_factory_company_match(sb, _FACTORY_A, _COMPANY_A)  # should not raise

    def test_A15_02_mismatching_company_id_403(self):
        """A15-02: factory.company_id != company_id → HTTPException 403."""
        from services.company_scope import _ensure_factory_company_match
        sb = self._make_supa(_COMPANY_B)
        with pytest.raises(HTTPException) as exc_info:
            _ensure_factory_company_match(sb, _FACTORY_B, _COMPANY_A)
        assert exc_info.value.status_code == 403

    def test_A15_03_factory_not_found_404(self):
        """A15-03: factories 조회 결과 없음 → HTTPException 404."""
        from services.company_scope import _ensure_factory_company_match
        sb = self._make_supa(None, factory_exists=False)
        with pytest.raises(HTTPException) as exc_info:
            _ensure_factory_company_match(sb, "nonexistent-factory", _COMPANY_A)
        assert exc_info.value.status_code == 404

    def test_A15_04_empty_company_id_403(self):
        """A15-04: company_id="" → DB 미조회 즉시 HTTPException 403."""
        from services.company_scope import _ensure_factory_company_match
        sb = MagicMock()  # DB 호출되면 안 됨
        with pytest.raises(HTTPException) as exc_info:
            _ensure_factory_company_match(sb, _FACTORY_A, "")
        assert exc_info.value.status_code == 403
        sb.table.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# A15-05~07 — INDUSTRIAL 라우터 admin 경계
# ─────────────────────────────────────────────────────────────────────────────

def test_A15_05_industrial_admin_own_company_factory_passes(monkeypatch):
    """A15-05: ALL admin, 자사 factory → _ensure_factory_company_match 통과 → leg 호출."""
    supa = _FakeSupa()  # FACTORY_A → COMPANY_A
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_A)
    called = {"n": 0}

    def fake_run(*a, **kw):
        called["n"] += 1
        return _LEG_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_industrial_leg", fake_run)

    body = SafeIndustrialLegBody(factory_id=_FACTORY_A, input=SafeIndustrialConsumerInput())
    from routers.legal_engine import diagnose_industrial_leg
    _run(diagnose_industrial_leg(body, authorization="Bearer tok"))

    assert called["n"] == 1, "자사 factory → run_safe_industrial_leg 호출됨"


def test_A15_06_industrial_admin_other_company_factory_403(monkeypatch):
    """A15-06: ALL admin(company A), 타사(company B) factory → HTTP 403 차단."""
    supa = _FakeSupa()  # FACTORY_B → COMPANY_B
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_A)
    called = {"n": 0}

    def fake_run(*a, **kw):
        called["n"] += 1
        return _LEG_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_industrial_leg", fake_run)

    body = SafeIndustrialLegBody(factory_id=_FACTORY_B, input=SafeIndustrialConsumerInput())
    from routers.legal_engine import diagnose_industrial_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_industrial_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 403
    assert called["n"] == 0, "타사 factory 시 run_safe_industrial_leg 호출 금지"


def test_A15_07_industrial_admin_nonexistent_factory_404(monkeypatch):
    """A15-07: ALL admin, 존재하지 않는 factory_id → HTTP 404."""
    supa = _FakeSupa(factory_company_map={})  # 빈 맵 → 404
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_A)

    body = SafeIndustrialLegBody(factory_id="no-such-factory", input=SafeIndustrialConsumerInput())
    from routers.legal_engine import diagnose_industrial_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_industrial_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# A15-08~10 — BUILDING 라우터 admin 경계
# ─────────────────────────────────────────────────────────────────────────────

def test_A15_08_building_admin_own_company_factory_passes(monkeypatch):
    """A15-08: ALL admin, 자사 factory → _ensure_factory_company_match 통과 → leg 호출."""
    supa = _FakeSupa()
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_A)
    called = {"n": 0}

    def fake_run(*a, **kw):
        called["n"] += 1
        return _LEG_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_building_leg", fake_run)

    body = SafeBuildingLegBody(factory_id=_FACTORY_A, input=SafeBuildingConsumerInput())
    from routers.legal_engine import diagnose_building_leg
    _run(diagnose_building_leg(body, authorization="Bearer tok"))

    assert called["n"] == 1, "자사 factory → run_safe_building_leg 호출됨"


def test_A15_09_building_admin_other_company_factory_403(monkeypatch):
    """A15-09: ALL admin(company A), 타사(company B) factory → HTTP 403 차단."""
    supa = _FakeSupa()
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_A)
    called = {"n": 0}

    def fake_run(*a, **kw):
        called["n"] += 1
        return _LEG_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_building_leg", fake_run)

    body = SafeBuildingLegBody(factory_id=_FACTORY_B, input=SafeBuildingConsumerInput())
    from routers.legal_engine import diagnose_building_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_building_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 403
    assert called["n"] == 0, "타사 factory 시 run_safe_building_leg 호출 금지"


def test_A15_10_building_regular_user_own_factory_passes(monkeypatch):
    """A15-10: 일반 사용자(비-ALL), 자사 factory → 기존 동작 유지 (회귀 없음)."""
    supa = _FakeSupa()
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_A)
    called = {"n": 0}

    def fake_run(*a, **kw):
        called["n"] += 1
        return _LEG_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_building_leg", fake_run)

    body = SafeBuildingLegBody(factory_id=_FACTORY_A, input=SafeBuildingConsumerInput())
    from routers.legal_engine import diagnose_building_leg
    _run(diagnose_building_leg(body, authorization="Bearer tok"))

    assert called["n"] == 1, "자사 factory 일반 사용자 → run_safe_building_leg 호출됨"


# ─────────────────────────────────────────────────────────────────────────────
# A15-11~13 — CONSTRUCTION 회귀 (A15 guard 미삽입 확인)
# ─────────────────────────────────────────────────────────────────────────────

def test_A15_11_construction_factory_company_match_still_403(monkeypatch):
    """A15-11: CONSTRUCTION 기존 factory-company 불일치 → 403 (기존 동작 유지)."""
    supa = _FakeSupa(factory_company_map={_FACTORY_A: _COMPANY_B}, site_factory_id=_FACTORY_A)
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_A)
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
    assert called["n"] == 0, "CONSTRUCTION factory 회사 불일치 → runtime 미호출"


def test_A15_12_construction_company_id_from_site_db_not_token(monkeypatch):
    """A15-12: CONSTRUCTION company_id 는 site DB에서 파생 — token.company_id 미사용."""
    supa = _FakeSupa(
        factory_company_map={_FACTORY_A: _COMPANY_A},
        site_company_id=_COMPANY_A,
        site_factory_id=_FACTORY_A,
    )
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_B)  # token은 B지만 site는 A
    captured = {}

    def fake_run(*a, company_id=None, **kw):
        captured["company_id"] = company_id
        return _CST_OUT

    monkeypatch.setattr("routers.legal_engine.run_safe_construction_leg", fake_run)

    body = SafeConstructionLegBody(site_id=_SITE_ID, input=SafeConstructionConsumerInput())
    from routers.legal_engine import diagnose_construction_leg
    _run(diagnose_construction_leg(body, authorization="Bearer tok"))

    assert captured["company_id"] == _COMPANY_A, (
        f"CONSTRUCTION company_id 는 site DB에서 파생: expected {_COMPANY_A!r}, got {captured.get('company_id')!r}"
    )


def test_A15_13_construction_handler_does_not_call_ensure_factory_company_match(monkeypatch):
    """A15-13 (Static): diagnose_construction_leg 소스에 _ensure_factory_company_match 없음.

    CONSTRUCTION 은 이미 기존 코드(lines 242-248)에서 factory-company 검증하므로 A15 guard 미삽입.
    """
    from routers.legal_engine import diagnose_construction_leg
    src = inspect.getsource(diagnose_construction_leg)
    assert "_ensure_factory_company_match" not in src, (
        "CONSTRUCTION 핸들러에 _ensure_factory_company_match 미삽입 — 기존 검증으로 충분"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A15-14~16 — 정적 검증
# ─────────────────────────────────────────────────────────────────────────────

def test_A15_14_ensure_factory_company_match_has_no_admin_bypass():
    """A15-14 (Static): _ensure_factory_company_match 소스에 _is_admin 우회 없음."""
    from services.company_scope import _ensure_factory_company_match
    src = inspect.getsource(_ensure_factory_company_match)
    assert "_is_admin" not in src, (
        "_ensure_factory_company_match must not contain _is_admin bypass"
    )
    assert 'tier == "ALL"' not in src and "tier==" not in src, (
        "_ensure_factory_company_match must not check tier for bypass"
    )


def test_A15_15_industrial_handler_calls_ensure_factory_company_match():
    """A15-15 (Static): diagnose_industrial_leg 소스에 _ensure_factory_company_match 있음."""
    from routers.legal_engine import diagnose_industrial_leg
    src = inspect.getsource(diagnose_industrial_leg)
    assert "_ensure_factory_company_match" in src, (
        "diagnose_industrial_leg must call _ensure_factory_company_match"
    )


def test_A15_16_building_handler_calls_ensure_factory_company_match():
    """A15-16 (Static): diagnose_building_leg 소스에 _ensure_factory_company_match 있음."""
    from routers.legal_engine import diagnose_building_leg
    src = inspect.getsource(diagnose_building_leg)
    assert "_ensure_factory_company_match" in src, (
        "diagnose_building_leg must call _ensure_factory_company_match"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A15-17 — R13-08 행동 변화 (빈 company_id → 403)
# ─────────────────────────────────────────────────────────────────────────────

def test_A15_17_empty_company_id_blocked_at_router(monkeypatch):
    """A15-17: company_id=None → "" → A15 guard 403 차단 (WIRING-015 신규 동작).

    WIRING-015 이전: "" 이 runtime으로 전달되어 CHEM 클라이언트에서 차단.
    WIRING-015 이후: 라우터 레벨에서 403 — runtime 미호출.
    BUILDING 경로로도 동일 검증.
    """
    supa = _FakeSupa()
    _patch_chain(monkeypatch, supa=supa, company_id=None)  # type: ignore[arg-type]
    # get_current_user 재설정 (company_id=None 명시)
    monkeypatch.setattr("routers.legal_engine.get_current_user",
                        lambda auth: {"company_id": None})
    called_ind = {"n": 0}
    called_bld = {"n": 0}

    monkeypatch.setattr(
        "routers.legal_engine.run_safe_industrial_leg",
        lambda *a, **kw: called_ind.update({"n": called_ind["n"] + 1}) or _LEG_OUT,
    )
    monkeypatch.setattr(
        "routers.legal_engine.run_safe_building_leg",
        lambda *a, **kw: called_bld.update({"n": called_bld["n"] + 1}) or _LEG_OUT,
    )

    from routers.legal_engine import diagnose_industrial_leg, diagnose_building_leg

    body_ind = SafeIndustrialLegBody(factory_id=_FACTORY_A, input=SafeIndustrialConsumerInput())
    with pytest.raises(HTTPException) as exc_ind:
        _run(diagnose_industrial_leg(body_ind, authorization="Bearer tok"))
    assert exc_ind.value.status_code == 403
    assert called_ind["n"] == 0

    body_bld = SafeBuildingLegBody(factory_id=_FACTORY_A, input=SafeBuildingConsumerInput())
    with pytest.raises(HTTPException) as exc_bld:
        _run(diagnose_building_leg(body_bld, authorization="Bearer tok"))
    assert exc_bld.value.status_code == 403
    assert called_bld["n"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# A15-18~20 — PATCH-01: CONSTRUCTION App3 조회 순서 검증
# ─────────────────────────────────────────────────────────────────────────────

def test_A15_18_construction_mismatch_app3_not_called(monkeypatch):
    """A15-18 (PATCH-01): CONSTRUCTION 타사 factory → App3 호출 0, runtime 호출 0.

    factory-company 검증이 check_saas_appendix3_contract 보다 먼저 실행되어
    타사 factory 자료를 App3 조회 전에 차단해야 한다.
    """
    supa = _FakeSupa(factory_company_map={_FACTORY_A: _COMPANY_B}, site_factory_id=_FACTORY_A)
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_A)

    app3_called = {"n": 0}
    runtime_called = {"n": 0}

    def fake_app3(sb, fac_id, sector, inp):
        app3_called["n"] += 1
        return None

    def fake_run(*a, **kw):
        runtime_called["n"] += 1
        return _CST_OUT

    monkeypatch.setattr("routers.legal_engine.check_saas_appendix3_contract", fake_app3)
    monkeypatch.setattr("routers.legal_engine.run_safe_construction_leg", fake_run)

    body = SafeConstructionLegBody(site_id=_SITE_ID, input=SafeConstructionConsumerInput())
    from routers.legal_engine import diagnose_construction_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_construction_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 403
    assert app3_called["n"] == 0, "타사 factory 시 App3 조회 금지 (PATCH-01)"
    assert runtime_called["n"] == 0, "타사 factory 시 runtime 호출 금지"


def test_A15_19_construction_same_company_app3_still_called(monkeypatch):
    """A15-19 (PATCH-01): CONSTRUCTION 자사 factory → App3 호출 1 (기존 동작 유지)."""
    supa = _FakeSupa(factory_company_map={_FACTORY_A: _COMPANY_A}, site_factory_id=_FACTORY_A)
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_A)

    app3_called = {"n": 0}

    def fake_app3(sb, fac_id, sector, inp):
        app3_called["n"] += 1
        return None

    def fake_run(*a, **kw):
        return _CST_OUT

    monkeypatch.setattr("routers.legal_engine.check_saas_appendix3_contract", fake_app3)
    monkeypatch.setattr("routers.legal_engine.run_safe_construction_leg", fake_run)

    body = SafeConstructionLegBody(site_id=_SITE_ID, input=SafeConstructionConsumerInput())
    from routers.legal_engine import diagnose_construction_leg
    _run(diagnose_construction_leg(body, authorization="Bearer tok"))

    assert app3_called["n"] == 1, "자사 factory → App3 조회 정상 호출"


def test_A15_20_construction_factory_not_found_fail_closed(monkeypatch):
    """A15-20 (PATCH-01): CONSTRUCTION factory 미존재 → 403 fail-closed (App3·runtime 미호출)."""
    supa = _FakeSupa(factory_company_map={}, site_factory_id=_FACTORY_A)
    _patch_chain(monkeypatch, supa=supa, company_id=_COMPANY_A)

    app3_called = {"n": 0}
    runtime_called = {"n": 0}

    def fake_app3(*a, **kw):
        app3_called["n"] += 1
        return None

    def fake_run(*a, **kw):
        runtime_called["n"] += 1
        return _CST_OUT

    monkeypatch.setattr("routers.legal_engine.check_saas_appendix3_contract", fake_app3)
    monkeypatch.setattr("routers.legal_engine.run_safe_construction_leg", fake_run)

    body = SafeConstructionLegBody(site_id=_SITE_ID, input=SafeConstructionConsumerInput())
    from routers.legal_engine import diagnose_construction_leg
    with pytest.raises(HTTPException) as exc_info:
        _run(diagnose_construction_leg(body, authorization="Bearer tok"))

    assert exc_info.value.status_code == 403
    assert app3_called["n"] == 0, "factory 미존재 시 App3 조회 금지"
    assert runtime_called["n"] == 0, "factory 미존재 시 runtime 호출 금지"
