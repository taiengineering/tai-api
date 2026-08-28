"""OBJ-01 DEBT-W3-02 — router cutover tests for record_inspection_results.

Cursor 가 routers/inspection_checklist.py 를 편집한 뒤 실행. 실제 라우터 함수를
import 하고, record_safe_result_batch / get_supabase / _ensure_inspection_own /
complete_inspection_status 를 모킹해 R14/R15/R16 + 매핑 + 응답 shape + B1 을 고정한다.

핵심 계약:
- 직접 safety_inspection_results INSERT = 0 (RPC 서비스만)
- CREATED 와 REPLAY 모두 auto-complete 후속 실행 (REPLAY early-return 금지)
- auto-complete 판단은 CANONICAL (NORMAL only) 기준 — raw 문자열 아님 (B1)
- conflict→409, not-found→404, empty→400, created=N, ownership guard 호출
"""
from __future__ import annotations

import asyncio

import pytest

import routers.inspection_checklist as ic
from services.safe_inspection_result_batch import SafeResultBatchError


class _Q:
    def __init__(self, tbl, forbidden):
        self.tbl = tbl
        self.forbidden = forbidden

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def update(self, p):
        self.forbidden.append((self.tbl, "update", p))
        return self

    def insert(self, p):
        self.forbidden.append((self.tbl, "insert", p))
        return self

    def execute(self):
        class R:
            pass
        r = R()
        r.data = [{"assignment_id": "WS-1"}] if self.tbl == "safety_inspections" else []
        return r


class FakeSupabase:
    def __init__(self, forbidden):
        self.forbidden = forbidden

    def table(self, name):
        return _Q(name, self.forbidden)


@pytest.fixture
def wired(monkeypatch):
    state = {"forbidden": [], "own": [], "rb_calls": [], "complete": [],
             "rb_next": None, "rb_raise": None}
    sb = FakeSupabase(state["forbidden"])

    def _get_supabase():
        return sb

    def _own(supabase, iid, cur):
        state["own"].append(iid)

    def _rb(supabase, *, inspection_id, results):
        state["rb_calls"].append((inspection_id, list(results)))
        if state["rb_raise"] is not None:
            raise state["rb_raise"]
        return state["rb_next"]

    def _complete(supabase, iid, *, actor_id, reason):
        state["complete"].append((iid, reason))

    monkeypatch.setattr(ic, "get_supabase", _get_supabase, raising=True)
    monkeypatch.setattr(ic, "_ensure_inspection_own", _own, raising=True)
    monkeypatch.setattr(ic, "record_safe_result_batch", _rb, raising=True)
    monkeypatch.setattr(ic, "complete_inspection_status", _complete, raising=True)
    return state


def _call(body):
    return asyncio.run(ic.record_inspection_results("INS", body, {"id": "U"}))


def _created(n=3):
    return {"mode": "CREATED", "count": n, "data": {"inspection_id": "INS", "created": n}}


def _replay(n=3):
    return {"mode": "REPLAY", "count": n, "data": {"inspection_id": "INS", "created": n}}


ALLPASS = [{"result": "ok"}, {"result": "ok"}, {"result": "ok"}]


def test_r16_no_direct_results_insert_and_created(wired):
    wired["rb_next"] = _created(3)
    out = _call({"results": ALLPASS})
    assert [f for f in wired["forbidden"] if f[0] == "safety_inspection_results"] == []
    assert len(wired["rb_calls"]) == 1
    assert out["data"]["created"] == 3 and out["status"] == "success"


def test_r14_created_autocomplete(wired):
    wired["rb_next"] = _created(3)
    _call({"results": ALLPASS})
    assert wired["complete"] == [("INS", "SAFE_RESULT_AUTO_COMPLETE")]


def test_r15_replay_autocomplete_no_early_return(wired):
    wired["rb_next"] = _replay(3)
    _call({"results": ALLPASS})
    assert wired["complete"] == [("INS", "SAFE_RESULT_AUTO_COMPLETE")]


def test_autocomplete_skipped_on_fail(wired):
    wired["rb_next"] = _created(2)
    _call({"results": [{"result": "ok"}, {"result": "FAIL"}]})
    assert wired["complete"] == []


# ── B1: auto-complete decided on CANONICAL result, not raw string ──

def test_b1_created_abnormal_no_autocomplete(wired):
    wired["rb_next"] = _created(1)
    _call({"results": [{"result": "FAIL"}]})          # FAIL -> ABNORMAL
    assert wired["complete"] == []


def test_b1_replay_abnormal_no_autocomplete(wired):
    wired["rb_next"] = _replay(1)
    _call({"results": [{"result": "ABNORMAL"}]})      # already canonical ABNORMAL
    assert wired["complete"] == []


def test_b1_hold_no_autocomplete(wired):
    wired["rb_next"] = _created(1)
    _call({"results": [{"result": "HOLD"}]})          # HOLD is not NORMAL
    assert wired["complete"] == []


def test_b1_alias_same_side_effect(wired):
    # FAIL and ABNORMAL both normalize to ABNORMAL => identical (no) auto-complete,
    # so a CREATED(FAIL) then REPLAY(ABNORMAL) retry cannot flip the side-effect.
    wired["rb_next"] = _created(1)
    _call({"results": [{"result": "FAIL"}]})
    first = list(wired["complete"])
    wired["complete"].clear()
    wired["rb_next"] = _replay(1)
    _call({"results": [{"result": "ABNORMAL"}]})
    assert wired["complete"] == first == []


def test_b1_normal_aliases_autocomplete(wired):
    wired["rb_next"] = _created(3)
    _call({"results": [{"result": "ok"}, {"result": "pass"}, {"result": "NORMAL"}]})
    assert wired["complete"] == [("INS", "SAFE_RESULT_AUTO_COMPLETE")]


def test_conflict_409(wired):
    wired["rb_raise"] = SafeResultBatchError("RESULT_INITIAL_BATCH_CONFLICT")
    with pytest.raises(ic.HTTPException) as ei:
        _call({"results": ALLPASS})
    assert ei.value.status_code == 409


def test_not_found_404(wired):
    wired["rb_raise"] = SafeResultBatchError("INSPECTION_NOT_FOUND")
    with pytest.raises(ic.HTTPException) as ei:
        _call({"results": ALLPASS})
    assert ei.value.status_code == 404


def test_empty_400_before_rpc(wired):
    wired["rb_next"] = _created()
    with pytest.raises(ic.HTTPException) as ei:
        _call({"results": []})
    assert ei.value.status_code == 400
    assert wired["rb_calls"] == []


def test_ownership_guard_called(wired):
    wired["rb_next"] = _created()
    _call({"results": ALLPASS})
    assert wired["own"] == ["INS"]
