"""WO-SAAS-INDUSTRIAL-C10-CANONICAL-WIRING-001 STEP 4B-4C — persist + guard + orchestration + route.

helper 단위(T2~T21) + route wiring(legal_engine.py INDUSTRIAL) / public guard(diagnosis_result_web.py) /
T22~T30. DB/network 불필요.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import logging

import pytest
from fastapi import HTTPException

from services.saas_diagnosis_result_persistence import (
    SaasPersistError,
    persist_saas_full_result,
    materialize_saas_inspection,
    run_saas_c10_and_materialize,
)


def _fit_gate(*a, **k):
    return {"status": "FIT", "sector": "INDUSTRY",
            "current_plan": {"tier_code": "TEST_CURRENT"},
            "required_plan": {"tier_code": "TEST_REQUIRED"}, "metric": {}}


def _full(**over):
    f = {
        "sector": "INDUSTRIAL",
        "engine_version": "leg-runtime-v3",
        "obligations_raw": [
            {"atom_id": "a0", "law_name": "산안법", "law_article": "38",
             "obligation_detail": {"what": "점검하여야 한다", "who": "사업주"},
             "enrichment": {"obligation_type": "INSPECT"}},
            {"atom_id": "a1", "obligation_detail": {"what": "게시"},
             "enrichment": {"obligation_type": "ACTION"}},
        ],
    }
    f.update(over)
    return f


# ── supabase mock ──
class _Q:
    def __init__(self, sb, name):
        self.sb = sb; self.name = name; self._op = "select"; self._eq = {}; self._payload = None; self._isnull = None

    def select(self, *a, **k): self._op = "select"; return self
    def eq(self, c, v): self._eq[c] = v; return self
    def is_(self, c, v): self._isnull = (c, v); return self
    def limit(self, n): return self
    def insert(self, row): self._op = "insert"; self._payload = row; return self

    def execute(self):
        class R: pass
        r = R()
        if self.name == "anonymous_diagnosis_results" and self._op == "insert":
            self.sb.c10_inserts.append(self._payload)
            r.data = [] if self.sb.c10_fail else [{"id": "diag-1", **self._payload}]
        else:
            r.data = []
        return r


class _WriterQ:
    """canonical_writer 의 inspection_sets select/insert/update + legacy guard select 흡수."""
    def __init__(self, sb): self.sb = sb; self._op = "select"; self._eq = {}; self._isnull = None; self._payload = None
    def select(self, *a, **k): self._op = "select"; return self
    def eq(self, c, v): self._eq[c] = v; return self
    def is_(self, c, v): self._isnull = (c, v); return self
    def in_(self, c, v): self._eq[c] = list(v); return self
    def limit(self, n): return self
    def insert(self, rows): self._op = "insert"; self._payload = rows; self.sb.writer_inserts.append(rows); return self
    def update(self, patch): self._op = "update"; self._payload = patch; self.sb.writer_updates.append(patch); return self
    def execute(self):
        class R: pass
        r = R()
        if self._op == "select" and self._isnull == ("legal_obligation_atom_id", "null"):
            r.data = list(self.sb.legacy_rows)          # legacy guard
        elif self._op == "select":
            r.data = []                                  # writer existing-atom lookup
        else:
            r.data = self._payload if isinstance(self._payload, list) else [self._payload]
        return r


class _SB:
    def __init__(self, legacy_rows=None, c10_fail=False):
        self.legacy_rows = legacy_rows or []; self.c10_fail = c10_fail
        self.c10_inserts = []; self.writer_inserts = []; self.writer_updates = []
    def table(self, name):
        if name == "inspection_sets":
            return _WriterQ(self)
        return _Q(self, name)


# ── persist ──
def test_T2_T4_T5_T7_T8_persist_row():
    sb = _SB()
    f = _full()
    out = persist_saas_full_result(sb, factory_id="f1", company_id="c1", full_result=f)
    row = sb.c10_inserts[0]
    assert row["full_result"] == f                      # T2 EXACT
    assert row["source_type"] == "saas"                 # T4
    assert out["public_token"] and len(out["public_token"]) >= 32  # T5 generated
    assert row["input_data"]["factory_id"] == "f1"      # T7
    assert row["input_data"]["company_id"] == "c1"      # T8
    assert row["input_data"]["sector"] == "INDUSTRIAL"
    assert out["diagnosis_id"] == "diag-1"
    # PATCH-0B: 최소 row 만(created_at 수동 생성 0)
    assert "created_at" not in row
    assert set(row.keys()) == {"public_token", "input_data", "full_result",
                               "status", "source_type", "engine_version"}


def test_T3_full_result_mutation_zero():
    sb = _SB(); f = _full(); before = copy.deepcopy(f)
    persist_saas_full_result(sb, factory_id="f1", company_id="c1", full_result=f)
    assert f == before


def test_T9_T10_T11_T12_no_consumer_fields():
    sb = _SB()
    persist_saas_full_result(sb, factory_id="f1", company_id="c1", full_result=_full())
    row = sb.c10_inserts[0]
    for k in ("ci_hash", "auth_log_id", "disclaimer_log_id", "payment_ref",
              "free_count", "tier_code", "paid_amount", "partial_result"):
        assert k not in row


def test_T13_obligations_raw_malformed_fail_close():
    sb = _SB()
    for bad in (None, {}, {"obligations_raw": None}, {"obligations_raw": "x"}, {"obligations_raw": {}}):
        with pytest.raises(SaasPersistError):
            persist_saas_full_result(sb, factory_id="f1", company_id="c1", full_result=bad)
    assert sb.c10_inserts == []
    persist_saas_full_result(_SB(), factory_id="f1", company_id="c1", full_result={"obligations_raw": []})


def test_factory_company_required_fail_close():
    for fid, cid in (("", "c1"), ("  ", "c1"), ("f1", ""), (None, "c1"), ("f1", None)):
        with pytest.raises(SaasPersistError):
            persist_saas_full_result(_SB(), factory_id=fid, company_id=cid, full_result=_full())


def test_T14_c10_insert_failure_raises():
    with pytest.raises(SaasPersistError):
        persist_saas_full_result(_SB(c10_fail=True), factory_id="f1", company_id="c1", full_result=_full())


# ── guard + materialize ──
def test_T15_legacy_present_blocks_writer():
    sb = _SB(legacy_rows=[{"id": "legacy-1"}])
    out = materialize_saas_inspection(sb, "f1", "c1", _full())
    assert out == {"status": "BLOCKED_LEGACY_ROWS"}
    assert sb.writer_inserts == [] and sb.writer_updates == []


def test_T16_T17_legacy_absent_writer_runs():
    sb = _SB(legacy_rows=[])
    out = materialize_saas_inspection(sb, "f1", "c1", _full())
    assert out["status"] == "MATERIALIZED"
    assert out["candidates"] == 1        # INSPECT atom a0 만 (a1=ACTION skip)
    assert out["inserted"] == 1
    assert sb.writer_inserts and sb.writer_inserts[0][0]["legal_obligation_atom_id"] == "a0"


# ── orchestration ──
def test_orchestration_blocked_legacy():
    sb = _SB(legacy_rows=[{"id": "L"}])
    out = run_saas_c10_and_materialize(sb, "f1", "c1", _full())
    assert out["diagnosis_id"] == "diag-1"
    assert out["inspection_materialization"] == {"status": "BLOCKED_LEGACY_ROWS"}
    assert len(sb.c10_inserts) == 1
    assert "public_token" not in out


def test_orchestration_materialized():
    sb = _SB(legacy_rows=[])
    out = run_saas_c10_and_materialize(sb, "f1", "c1", _full())
    assert out["inspection_materialization"]["status"] == "MATERIALIZED"
    assert out["inspection_materialization"]["inserted"] == 1


def test_T14_orch_c10_fail_no_writer():
    sb = _SB(c10_fail=True)
    with pytest.raises(SaasPersistError):
        run_saas_c10_and_materialize(sb, "f1", "c1", _full())
    assert sb.writer_inserts == []


def test_T21_writer_failure_preserves_c10_failed_status_and_logs(monkeypatch, caplog):
    import services.saas_diagnosis_result_persistence as M

    def _boom(supabase, factory_id, company_id, full_result):
        raise RuntimeError("writer boom")

    monkeypatch.setattr(M, "materialize_saas_inspection", _boom)
    sb = _SB(legacy_rows=[])
    with caplog.at_level(logging.ERROR, logger=M.log.name):
        out = M.run_saas_c10_and_materialize(sb, "f1", "c1", _full())
    assert out["inspection_materialization"] == {"status": "FAILED"}   # silent swallow 0
    assert out["diagnosis_id"] == "diag-1"
    assert len(sb.c10_inserts) == 1                                    # C-10 보존
    # PATCH-0A: exception log 1회 발생
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR and "[SAAS_C10]" in r.getMessage()]
    assert len(errors) == 1
    assert errors[0].exc_info is not None                             # log.exception (traceback 포함)


def test_canonical_writer_untouched():
    import inspect
    import services.saas_diagnosis_result_persistence as M
    src = inspect.getsource(M)
    assert "materialize_canonical_inspection_sets" in src
    assert "def materialize_canonical_inspection_sets" not in src


# ── T22~T30: public saas 404 + FREE/PAID 회귀 + INDUSTRIAL seam / other-sector delta 0 ──

_NOT_FOUND = "진단 결과를 찾을 수 없습니다."


def _web_rec(*, source_type=None, tier="BUILDING_FREE"):
    rec = {
        "id": "row-1",
        "public_token": "tok-1",
        "tier_code": tier,
        "status": "ACTIVE",
        "expires_at": None,
        "created_at": "2026-09-08T00:00:00+00:00",
        "input_data": {"company_name": "샘플", "sector": "BUILDING"},
        "full_result": {
            "sector": "BUILDING",
            "contract": {"missing_fields": ["a"], "unknown_fields": [], "invalid_fields": []},
            "obligations_raw": [
                {"enrichment": {"missing_fields": ["f1"], "usable_for_evaluation": True}},
            ],
        },
    }
    if source_type is not None:
        rec["source_type"] = source_type
    return rec


class _WebQ:
    def __init__(self, sb, rec):
        self.sb = sb
        self._rec = rec

    def select(self, cols, *a, **k):
        self.sb.last_select = cols
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        class R:
            data = [self._rec]
        return R()


class _WebSB:
    def __init__(self, rec):
        self._rec = rec
        self.last_select = None

    def table(self, *a, **k):
        return _WebQ(self, self._rec)


def _install_web(monkeypatch, rec):
    import routers.diagnosis_result_web as rw
    sb = _WebSB(rec)
    monkeypatch.setattr(rw, "get_supabase", lambda: sb)
    monkeypatch.setattr(rw, "build_paid_result_product_v1", lambda row: {
        "contract_version": 1,
        "diagnosis": {},
        "diagnosis_profile": {},
        "paid_result_materials_v1": {},
        "paid_result_evidence_v1": {},
        rw.SOURCE_TEXT_KEY: {"version": 1, "source_mode": "LIVE_LEG_SOURCE", "items": [], "unresolved": []},
    })
    return rw, sb


def test_T22_saas_token_result_404(monkeypatch):
    rw, sb = _install_web(monkeypatch, _web_rec(source_type="saas"))
    with pytest.raises(HTTPException) as ei:
        rw.get_diagnosis_result_web("tok-1")
    assert ei.value.status_code == 404
    assert ei.value.detail == _NOT_FOUND
    assert "source_type" in sb.last_select


def test_T23_saas_token_paid_result_404(monkeypatch):
    rw, _sb = _install_web(monkeypatch, _web_rec(source_type="saas", tier="BUILDING_V2"))
    with pytest.raises(HTTPException) as ei:
        rw.get_paid_result_web("tok-1")
    assert ei.value.status_code == 404
    assert ei.value.detail == _NOT_FOUND


def test_T24_saas_token_excel_404(monkeypatch):
    rw, _sb = _install_web(monkeypatch, _web_rec(source_type="saas", tier="BUILDING_V2"))
    with pytest.raises(HTTPException) as ei:
        rw.get_paid_result_excel("tok-1")
    assert ei.value.status_code == 404
    assert ei.value.detail == _NOT_FOUND


def test_T25_free_result_regression(monkeypatch):
    rw, _sb = _install_web(monkeypatch, _web_rec(tier="BUILDING_FREE"))
    data = rw.get_diagnosis_result_web("tok-1")["data"]
    assert data["is_free"] is True
    assert "additional_information" in data


def test_T26_paid_result_regression(monkeypatch):
    rw, _sb = _install_web(monkeypatch, _web_rec(tier="BUILDING_V2"))
    data = rw.get_paid_result_web("tok-1")["data"]
    assert data["is_free"] is False
    assert "additional_information" not in data


def test_T27_legacy_writer_auto_create_call_zero():
    import routers.legal_engine as LE
    src = inspect.getsource(LE.diagnose_industrial_leg)
    assert "auto_create_inspection_sets_from_diagnosis" not in src
    assert "inspection_set_auto" not in src
    assert "_finalize_saas_leg_http" in src
    assert "run_saas_c10_and_materialize" not in src


def test_T28_cycle_anchor_write_zero():
    import routers.legal_engine as LE
    src = inspect.getsource(LE.diagnose_industrial_leg)
    for banned in ("cycle_unit", "cycle_value", "anchor_confirmed",
                   "next_planned_date", "schedule_anchor"):
        assert banned not in src


def test_T29_schedule_write_zero():
    import routers.legal_engine as LE
    src = inspect.getsource(LE.diagnose_industrial_leg)
    assert "work_schedules" not in src
    assert "generate_schedules" not in src


def test_T30_building_construction_share_common_finalizer():
    import routers.legal_engine as LE
    for fn in (LE.diagnose_industrial_leg, LE.diagnose_building_leg, LE.diagnose_construction_leg):
        src = inspect.getsource(fn)
        assert "_finalize_saas_leg_http" in src
        assert "run_saas_c10_and_materialize" not in src
    helper = inspect.getsource(LE._finalize_saas_leg_http)
    assert "finalize_saas_leg_result" in helper


def test_industrial_leg_explicit_return_additive_company_id_from_factory(monkeypatch):
    """explicit return 2필드 additive · public_token 미반환 · company_id 서버 read."""
    import routers.legal_engine as LE
    from schemas.legal_engine import SafeIndustrialConsumerInput, SafeIndustrialLegBody

    captured = {}
    full = {"sector": "INDUSTRIAL", "obligations_raw": []}

    class _FacQ:
        def __init__(self, sb):
            self.sb = sb

        def select(self, cols, *a, **k):
            self.sb.factory_select = cols
            return self

        def eq(self, c, v):
            self.sb.factory_eq = (c, v)
            return self

        def limit(self, n):
            return self

        def execute(self):
            class R:
                data = [{"company_id": "c-server"}]
            return R()

    class _FacSB:
        def __init__(self):
            self.factory_select = None
            self.factory_eq = None

        def table(self, name):
            assert name == "factories"
            return _FacQ(self)

    sb = _FacSB()
    monkeypatch.setattr(LE, "get_supabase", lambda: sb)
    monkeypatch.setattr(LE, "get_current_user", lambda authorization=None: {"id": "u"})
    monkeypatch.setattr(LE, "_ensure_factory_own", lambda *a, **k: None)
    monkeypatch.setattr(LE, "evaluate_saas_tier_gate", _fit_gate)
    monkeypatch.setattr(LE.leg_runtime_client, "is_enabled", lambda: True)
    monkeypatch.setattr(LE, "run_safe_industrial_leg", lambda *a, **k: {
        "full_result": full,
        "contract_version": "v-test",
        "unresolved_fields": [],
    })

    def _fake_wiring(supabase, factory_id, company_id, full_result):
        captured["args"] = (factory_id, company_id, full_result)
        return {
            "diagnosis_id": "diag-x",
            "inspection_materialization": {"status": "MATERIALIZED"},
            "public_token": "must-not-leak",
        }

    monkeypatch.setattr(
        "services.saas_diagnosis_result_persistence.run_saas_c10_and_materialize",
        _fake_wiring,
    )
    body = SafeIndustrialLegBody(factory_id="f1", input=SafeIndustrialConsumerInput())
    out = asyncio.run(LE.diagnose_industrial_leg(body, authorization="Bearer x"))
    assert captured["args"] == ("f1", "c-server", full)
    assert sb.factory_select == "company_id"
    assert sb.factory_eq == ("id", "f1")
    assert out["status"] == "success"
    assert out["data"] is full
    assert out["contract_version"] == "v-test"
    assert out["unresolved_fields"] == []
    assert out["diagnosis_id"] == "diag-x"
    assert out["inspection_materialization"] == {"status": "MATERIALIZED"}
    assert "public_token" not in out
