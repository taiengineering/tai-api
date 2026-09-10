"""WO-SAAS-LEG-COMMON-FINALIZER-001 — common finalizer + 3-sector router wiring.

T1~T10 unit/wiring + S1~S4 static. DB/network/LEG 불필요.
self-fixture (이 파일) 과 repo pytest 묶음은 구분한다.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path

import pytest
from fastapi import HTTPException

from services.saas_diagnosis_result_persistence import (
    SaasPersistError,
    finalize_saas_leg_result,
)
from tests.test_saas_industrial_c10_canonical_wiring_v1 import _SB, _full


_ROOT = Path(__file__).resolve().parents[1]
_COMMON_KEYS = {
    "status", "data", "contract_version", "unresolved_fields",
    "diagnosis_id", "inspection_materialization",
}


def _fit_gate(*a, **k):
    return {"status": "FIT", "sector": "INDUSTRY",
            "current_plan": {"tier_code": "TEST_CURRENT"},
            "required_plan": {"tier_code": "TEST_REQUIRED"}, "metric": {}}


class _FacQ:
    def __init__(self, sb):
        self.sb = sb
        self._eq = None

    def select(self, cols, *a, **k):
        self.sb.factory_select = cols
        return self

    def eq(self, c, v):
        self._eq = (c, v)
        self.sb.factory_eq = (c, v)
        self.sb.factory_lookups.append((c, v))
        return self

    def limit(self, n):
        return self

    def execute(self):
        class R:
            pass
        r = R()
        if self.sb.factory_missing:
            r.data = []
        else:
            r.data = [dict(self.sb.factory_row)]
        return r


class _FacSB(_SB):
    def __init__(self, factory_row=None, factory_missing=False, **kw):
        super().__init__(**kw)
        self.factory_row = factory_row if factory_row is not None else {"company_id": "c1"}
        self.factory_missing = factory_missing
        self.factory_select = None
        self.factory_eq = None
        self.factory_lookups = []
        self.table_names = []

    def table(self, name):
        self.table_names.append(name)
        if name == "factories":
            return _FacQ(self)
        return super().table(name)


def _leg_out(full=None, **over):
    d = {
        "full_result": full if full is not None else _full(),
        "contract_version": "MKT_IND_PAID_CONTRACT_V1",
        "unresolved_fields": ["f1"],
    }
    d.update(over)
    return d


# ── T1 common success ──
def test_T1_common_success():
    sb = _FacSB()
    full = _full()
    out = finalize_saas_leg_result(sb, factory_id="f1", leg_out=_leg_out(full))
    assert set(out.keys()) == _COMMON_KEYS
    assert out["status"] == "success"
    assert out["data"] is full                          # STEP A transform 0
    assert out["contract_version"] == "MKT_IND_PAID_CONTRACT_V1"
    assert out["unresolved_fields"] == ["f1"]
    assert out["diagnosis_id"] == "diag-1"
    assert out["inspection_materialization"]["status"] == "MATERIALIZED"
    assert sb.factory_select == "company_id"
    assert sb.factory_eq == ("id", "f1")
    assert sb.c10_inserts[0]["full_result"] is full


# ── T2 factory missing ──
def test_T2_factory_missing_lookup_error():
    sb = _FacSB(factory_missing=True)
    with pytest.raises(LookupError, match="사업장을 찾을 수 없습니다."):
        finalize_saas_leg_result(sb, factory_id="missing", leg_out=_leg_out())
    assert sb.c10_inserts == []


# ── T3 company_id null/blank ──
@pytest.mark.parametrize("row", [{"company_id": None}, {"company_id": ""}, {"company_id": "  "}, {}])
def test_T3_company_null_value_error(row):
    sb = _FacSB(factory_row=row)
    with pytest.raises(ValueError, match="company_id required"):
        finalize_saas_leg_result(sb, factory_id="f1", leg_out=_leg_out())
    assert sb.c10_inserts == []


# ── T4 persist error propagate ──
def test_T4_persist_error_propagate():
    sb = _FacSB(c10_fail=True)
    with pytest.raises(SaasPersistError):
        finalize_saas_leg_result(sb, factory_id="f1", leg_out=_leg_out())
    assert sb.writer_inserts == []


# ── T5 public_token absent ──
def test_T5_public_token_absent():
    out = finalize_saas_leg_result(_FacSB(), factory_id="f1", leg_out=_leg_out())
    assert "public_token" not in out
    assert "public_token" not in (out.get("inspection_materialization") or {})


# ── T6 industrial regression EXACT ──
def test_T6_industrial_response_exact(monkeypatch):
    import routers.legal_engine as LE
    from schemas.legal_engine import SafeIndustrialConsumerInput, SafeIndustrialLegBody

    full = {"sector": "INDUSTRIAL", "obligations_raw": []}
    sb = _FacSB()
    monkeypatch.setattr(LE, "get_supabase", lambda: sb)
    monkeypatch.setattr(LE, "get_current_user", lambda authorization=None: {"id": "u"})
    monkeypatch.setattr(LE, "_ensure_factory_own", lambda *a, **k: None)
    monkeypatch.setattr(LE, "evaluate_saas_tier_gate", _fit_gate)
    monkeypatch.setattr(LE.leg_runtime_client, "is_enabled", lambda: True)
    monkeypatch.setattr(LE, "run_safe_industrial_leg", lambda *a, **k: _leg_out(full, contract_version="v-test", unresolved_fields=[]))
    body = SafeIndustrialLegBody(factory_id="f1", input=SafeIndustrialConsumerInput())
    out = asyncio.run(LE.diagnose_industrial_leg(body, authorization="Bearer x"))
    assert set(out.keys()) == _COMMON_KEYS
    assert out["status"] == "success"
    assert out["data"] is full
    assert out["contract_version"] == "v-test"
    assert out["unresolved_fields"] == []
    assert out["diagnosis_id"] == "diag-1"
    assert out["inspection_materialization"]["status"] == "MATERIALIZED"
    assert "public_token" not in out
    assert sb.factory_eq == ("id", "f1")


# ── T7 building wiring ──
def test_T7_building_finalize_uses_body_factory_id(monkeypatch):
    import routers.legal_engine as LE
    from schemas.legal_engine import SafeBuildingConsumerInput, SafeBuildingLegBody

    captured = {}
    full = {"sector": "BUILDING", "obligations_raw": []}

    def _fin(supabase, *, factory_id, leg_out):
        captured["factory_id"] = factory_id
        captured["leg_out"] = leg_out
        return {
            "status": "success", "data": leg_out["full_result"],
            "contract_version": leg_out["contract_version"],
            "unresolved_fields": leg_out["unresolved_fields"],
            "diagnosis_id": "diag-b",
            "inspection_materialization": {"status": "MATERIALIZED"},
        }

    monkeypatch.setattr(LE, "get_supabase", lambda: object())
    monkeypatch.setattr(LE, "get_current_user", lambda authorization=None: {"id": "u"})
    monkeypatch.setattr(LE, "_ensure_factory_own", lambda *a, **k: None)
    monkeypatch.setattr(LE, "evaluate_saas_tier_gate", _fit_gate)
    monkeypatch.setattr(LE.leg_runtime_client, "is_enabled", lambda: True)
    monkeypatch.setattr(LE, "run_safe_building_leg", lambda *a, **k: _leg_out(full, contract_version="bld-v", unresolved_fields=["u1"]))
    monkeypatch.setattr(LE, "finalize_saas_leg_result", _fin)
    body = SafeBuildingLegBody(factory_id="f-bld", input=SafeBuildingConsumerInput())
    out = asyncio.run(LE.diagnose_building_leg(body, authorization="Bearer x"))
    assert captured["factory_id"] == "f-bld"
    assert set(out.keys()) == _COMMON_KEYS
    assert out["diagnosis_id"] == "diag-b"
    assert "public_token" not in out


# ── T8 construction: assembler factory_id EXACT, router 재조회 0, site_id 오사용 0 ──
def test_T8_construction_factory_id_from_runtime_not_site_id(monkeypatch):
    import routers.legal_engine as LE
    from schemas.legal_engine import SafeConstructionConsumerInput, SafeConstructionLegBody

    captured = {}
    tables = []
    full = {"sector": "CONSTRUCTION", "obligations_raw": []}

    class _SiteQ:
        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, n):
            return self

        def execute(self):
            class R:
                data = [{"company_id": "c-site"}]
            return R()

    class _SiteSB:
        def table(self, name):
            tables.append(name)
            assert name == "construction_sites"
            return _SiteQ()

    def _fin(supabase, *, factory_id, leg_out):
        captured["factory_id"] = factory_id
        captured["leg_out"] = leg_out
        return {
            "status": "success", "data": leg_out["full_result"],
            "contract_version": leg_out["contract_version"],
            "unresolved_fields": leg_out["unresolved_fields"],
            "diagnosis_id": "diag-c",
            "inspection_materialization": {"status": "MATERIALIZED"},
        }

    monkeypatch.setattr(LE, "get_supabase", lambda: _SiteSB())
    monkeypatch.setattr(LE, "get_current_user", lambda authorization=None: {"id": "u"})
    monkeypatch.setattr(LE, "_ensure_own_company", lambda *a, **k: None)
    monkeypatch.setattr(LE, "evaluate_saas_tier_gate", _fit_gate)
    monkeypatch.setattr(LE.leg_runtime_client, "is_enabled", lambda: True)
    monkeypatch.setattr(LE, "run_safe_construction_leg", lambda *a, **k: {
        "full_result": full,
        "contract_version": "cst-v",
        "unresolved_fields": ["x"],
        "factory_id": "F-assembler-77",
    })
    monkeypatch.setattr(LE, "finalize_saas_leg_result", _fin)
    body = SafeConstructionLegBody(site_id="SITE-9", input=SafeConstructionConsumerInput())
    out = asyncio.run(LE.diagnose_construction_leg(body, authorization="Bearer x"))
    assert captured["factory_id"] == "F-assembler-77"
    assert captured["factory_id"] != body.site_id
    assert "SITE-9" != captured["factory_id"]
    assert tables == ["construction_sites"]               # factory 재조회 0
    assert set(out.keys()) == _COMMON_KEYS


# ── T9 same full_result → identical materialization across 3 factory_ids ──
def test_T9_same_full_result_identical_materialization():
    full = _full()
    mats = []
    for fid in ("f-ind", "f-bld", "f-cst"):
        sb = _FacSB()
        out = finalize_saas_leg_result(sb, factory_id=fid, leg_out=_leg_out(full))
        mats.append(out["inspection_materialization"])
        assert out["data"] is full
    assert mats[0] == mats[1] == mats[2]


# ── T10 legacy BLOCKED + schedule side-effect 0 ──
def test_T10_legacy_blocked_and_schedule_side_effect_zero():
    sb = _FacSB(legacy_rows=[{"id": "L"}])
    out = finalize_saas_leg_result(sb, factory_id="f1", leg_out=_leg_out())
    assert out["inspection_materialization"] == {"status": "BLOCKED_LEGACY_ROWS"}
    assert sb.writer_inserts == [] and sb.writer_updates == []
    assert "work_schedules" not in sb.table_names
    assert len(sb.c10_inserts) == 1


def test_http_mapping_lookup_value_persist():
    import routers.legal_engine as LE

    with pytest.raises(HTTPException) as e404:
        LE._finalize_saas_leg_http(_FacSB(factory_missing=True), factory_id="x", leg_out=_leg_out())
    assert e404.value.status_code == 404
    assert e404.value.detail == "사업장을 찾을 수 없습니다."

    with pytest.raises(HTTPException) as e422:
        LE._finalize_saas_leg_http(_FacSB(factory_row={"company_id": None}), factory_id="x", leg_out=_leg_out())
    assert e422.value.status_code == 422
    assert e422.value.detail == "company_id required"

    with pytest.raises(HTTPException) as e500:
        LE._finalize_saas_leg_http(_FacSB(c10_fail=True), factory_id="x", leg_out=_leg_out())
    assert e500.value.status_code == 500


# ── S1~S4 static ──
def _call_func_names(path: Path):
    tree = ast.parse(path.read_text())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                names.append(fn.id)
            elif isinstance(fn, ast.Attribute):
                names.append(fn.attr)
    return names


def test_S1_run_saas_c10_production_direct_call_only_finalizer():
    persist = _ROOT / "services" / "saas_diagnosis_result_persistence.py"
    router = _ROOT / "routers" / "legal_engine.py"
    persist_calls = [n for n in _call_func_names(persist) if n == "run_saas_c10_and_materialize"]
    router_calls = [n for n in _call_func_names(router) if n == "run_saas_c10_and_materialize"]
    assert persist_calls == ["run_saas_c10_and_materialize"]   # finalize 내부 1곳
    assert router_calls == []                                  # router 0


def test_S2_materialize_canonical_inspection_sets_persistence_one():
    persist = _ROOT / "services" / "saas_diagnosis_result_persistence.py"
    router = _ROOT / "routers" / "legal_engine.py"
    persist_calls = [n for n in _call_func_names(persist) if n == "materialize_canonical_inspection_sets"]
    router_calls = [n for n in _call_func_names(router) if n == "materialize_canonical_inspection_sets"]
    assert persist_calls == ["materialize_canonical_inspection_sets"]
    assert router_calls == []


def test_S3_finalize_called_from_three_routers():
    import routers.legal_engine as LE
    helper = inspect.getsource(LE._finalize_saas_leg_http)
    assert "finalize_saas_leg_result" in helper
    for fn in (LE.diagnose_industrial_leg, LE.diagnose_building_leg, LE.diagnose_construction_leg):
        src = inspect.getsource(fn)
        assert "_finalize_saas_leg_http" in src
        assert "run_saas_c10_and_materialize" not in src
    cst = inspect.getsource(LE.diagnose_construction_leg)
    assert 'out["factory_id"]' in cst
    assert "body.site_id" in cst                              # ownership 조회용
    # finalize factory_id 는 site_id 가 아님
    assert "factory_id=body.site_id" not in cst
    assert 'factory_id=out["factory_id"]' in cst


def test_S4_finalizer_no_sector_branch_no_http_no_fastapi():
    import services.saas_diagnosis_result_persistence as P
    src = inspect.getsource(P.finalize_saas_leg_result)
    assert "HTTPException" not in src
    assert "fastapi" not in src.lower()
    for word in ("INDUSTRIAL", "CONSTRUCTION", "BUILDING", "sector"):
        assert word not in src
    mod = inspect.getsource(P)
    assert "from fastapi" not in mod
    assert "import fastapi" not in mod
    assert "HTTPException" not in mod
    assert "finalize_saas_leg_result" in P.__all__
