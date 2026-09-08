"""WO-SAAS-INDUSTRIAL-C10-CANONICAL-WIRING-001 STEP 4B-4C — persist + guard + orchestration.

helper 단위(T1~T21의 pure/mock 부분). route wiring(legal_engine.py) / public guard(diagnosis_result_web.py) /
T22~T30 route·security 회귀 = 별도 route 테스트(Cursor). DB/network 불필요.
"""
from __future__ import annotations

import copy

import pytest

from services.saas_diagnosis_result_persistence import (
    SaasPersistError,
    persist_saas_full_result,
    materialize_saas_inspection,
    run_saas_c10_and_materialize,
)


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
        elif self.name == "inspection_sets" and self._op == "select":
            r.data = list(self.sb.legacy_rows) if self._isnull == ("legal_obligation_atom_id", "null") else []
        elif self.name == "inspection_sets":  # writer select(existing atoms)
            r.data = []
        return r


class _SB:
    def __init__(self, legacy_rows=None, c10_fail=False):
        self.legacy_rows = legacy_rows or []; self.c10_fail = c10_fail
        self.c10_inserts = []; self.writer_inserts = []; self.writer_updates = []
    def table(self, name):
        # writer(materialize_canonical_inspection_sets)의 insert/update 캡처용 별도 경로
        if name == "inspection_sets":
            return _WriterQ(self)
        return _Q(self, name)


class _WriterQ:
    """canonical_writer 의 inspection_sets select/insert/update 를 흡수(legacy guard select 포함)."""
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


# ── persist (T2~T12) ──
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
    assert sb.c10_inserts == []            # writer 0 (persist 자체 미수행)
    # empty list 는 정상
    persist_saas_full_result(_SB(), factory_id="f1", company_id="c1", full_result={"obligations_raw": []})


def test_factory_company_required_fail_close():
    for fid, cid in (("", "c1"), ("  ", "c1"), ("f1", ""), (None, "c1"), ("f1", None)):
        with pytest.raises(SaasPersistError):
            persist_saas_full_result(_SB(), factory_id=fid, company_id=cid, full_result=_full())


def test_T14_c10_insert_failure_raises():
    with pytest.raises(SaasPersistError):
        persist_saas_full_result(_SB(c10_fail=True), factory_id="f1", company_id="c1", full_result=_full())


# ── guard + materialize (T15/T16/T17) ──
def test_T15_legacy_present_blocks_writer():
    sb = _SB(legacy_rows=[{"id": "legacy-1"}])
    out = materialize_saas_inspection(sb, "f1", "c1", _full())
    assert out == {"status": "BLOCKED_LEGACY_ROWS"}
    assert sb.writer_inserts == [] and sb.writer_updates == []   # writer 0, legacy 무수정


def test_T16_T17_legacy_absent_writer_runs():
    sb = _SB(legacy_rows=[])
    out = materialize_saas_inspection(sb, "f1", "c1", _full())
    assert out["status"] == "MATERIALIZED"
    assert out["candidates"] == 1        # INSPECT atom a0 만 (a1=ACTION skip)
    assert out["inserted"] == 1
    # T17 writer 가 obligations_raw INSPECT atom 을 EXACT 사용
    assert sb.writer_inserts and sb.writer_inserts[0][0]["legal_obligation_atom_id"] == "a0"


# ── orchestration (T21 등) ──
def test_orchestration_blocked_legacy():
    sb = _SB(legacy_rows=[{"id": "L"}])
    out = run_saas_c10_and_materialize(sb, "f1", "c1", _full())
    assert out["diagnosis_id"] == "diag-1"
    assert out["inspection_materialization"] == {"status": "BLOCKED_LEGACY_ROWS"}
    assert len(sb.c10_inserts) == 1      # C-10 저장은 됨
    assert "public_token" not in out     # 노출 0


def test_orchestration_materialized():
    sb = _SB(legacy_rows=[])
    out = run_saas_c10_and_materialize(sb, "f1", "c1", _full())
    assert out["inspection_materialization"]["status"] == "MATERIALIZED"
    assert out["inspection_materialization"]["inserted"] == 1


def test_T14_orch_c10_fail_no_writer():
    sb = _SB(c10_fail=True)
    with pytest.raises(SaasPersistError):
        run_saas_c10_and_materialize(sb, "f1", "c1", _full())
    assert sb.writer_inserts == []       # writer 0


def test_T21_writer_failure_preserves_c10_failed_status(monkeypatch):
    import services.saas_diagnosis_result_persistence as M

    def _boom(supabase, factory_id, company_id, full_result):
        raise RuntimeError("writer boom")

    monkeypatch.setattr(M, "materialize_saas_inspection", _boom)
    sb = _SB(legacy_rows=[])
    out = M.run_saas_c10_and_materialize(sb, "f1", "c1", _full())
    assert out["inspection_materialization"] == {"status": "FAILED"}   # silent swallow 0
    assert out["diagnosis_id"] == "diag-1"
    assert len(sb.c10_inserts) == 1                                    # C-10 보존


def test_canonical_writer_untouched():
    import inspect
    import services.saas_diagnosis_result_persistence as M
    src = inspect.getsource(M)
    # writer 는 import 재사용만, 수정 아님
    assert "materialize_canonical_inspection_sets" in src
    assert "def materialize_canonical_inspection_sets" not in src  # 재정의 0
