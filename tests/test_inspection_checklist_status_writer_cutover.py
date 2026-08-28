"""OBJ-01 KNOT-3A COMMIT B — inspection_checklist status writer cutover tests.

record_inspection_results() / complete_inspection() 가 직접 safety_inspections
status UPDATE 대신 writer bridge(complete_inspection_status) 를 통해 전표화하는지,
그리고 schedule/result side effect 및 cardinality fail-closed 를 검증한다.

fake supabase 는 safety_inspections.update 를 금지(직접 base UPDATE 제거 증명)하고
모든 호출을 log 에 기록한다. bridge 와 ownership guard 는 monkeypatch.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import routers.inspection_checklist as R  # noqa: E402
from services.inspection_record_writer_bridge import InspectionStatusWriteError  # noqa: E402

try:  # HTTPException (real fastapi in repo, stub in isolated run)
    from fastapi import HTTPException
except Exception:  # pragma: no cover
    HTTPException = R.HTTPException  # type: ignore


class _Resp:
    def __init__(self, data=None, count=None):
        self.data = data
        self.count = count


class _Tbl:
    def __init__(self, name, log, resp):
        self.name = name
        self.log = log
        self.resp = resp
        self.action = None

    def select(self, *a, **k):
        self.action = "select"; return self

    def insert(self, rows, *a, **k):
        self.action = "insert"; self._rows = rows; return self

    def update(self, payload, *a, **k):
        if self.name == "safety_inspections":
            raise AssertionError("DIRECT safety_inspections UPDATE FORBIDDEN (writer cutover)")
        self.action = "update"; self._payload = payload; return self

    def delete(self, *a, **k):
        self.action = "delete"; return self

    # chainable filters / modifiers (all no-op, return self)
    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self
    def lt(self, *a, **k): return self
    def not_(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self
    def range(self, *a, **k): return self

    def execute(self):
        self.log.append((self.name, self.action))
        data = self.resp.get((self.name, self.action))
        if self.action == "insert" and data is None:
            data = [{"id": i} for i in range(len(self._rows))]
        return _Resp(data=data if data is not None else [])


class _FakeSB:
    def __init__(self, resp):
        self.resp = resp
        self.log = []

    def table(self, name):
        return _Tbl(name, self.log, self.resp)


class _BridgeSpy:
    def __init__(self, raise_exc=None):
        self.calls = []
        self.raise_exc = raise_exc

    def __call__(self, supabase, inspection_id, *, actor_id, reason):
        self.calls.append({"inspection_id": inspection_id, "actor_id": actor_id, "reason": reason})
        if self.raise_exc is not None:
            raise self.raise_exc
        return {"status": "COMPLETED", "changed": True, "noop": False, "revision": 1, "command_id": "cmd"}


class _Patch:
    def __init__(self, fake, spy, guard_attr):
        self.fake = fake
        self.spy = spy
        self.guard_attr = guard_attr
        self._orig = {}

    def __enter__(self):
        self._orig = {
            "g": R.get_supabase,
            "b": R.complete_inspection_status,
            "rb": getattr(R, "record_safe_result_batch", None),
            "guard": getattr(R, self.guard_attr),
        }
        R.get_supabase = lambda: self.fake
        R.complete_inspection_status = self.spy
        R.record_safe_result_batch = (
            lambda sb, *, inspection_id, results: {
                "mode": "CREATED",
                "count": len(results),
                "data": {"inspection_id": inspection_id, "created": len(results)},
            }
        )
        setattr(R, self.guard_attr, lambda *a, **k: None)
        return self

    def __exit__(self, *a):
        R.get_supabase = self._orig["g"]
        R.complete_inspection_status = self._orig["b"]
        if self._orig["rb"] is not None:
            R.record_safe_result_batch = self._orig["rb"]
        setattr(R, self.guard_attr, self._orig["guard"])
        return False


CUR = {"id": "user-1", "company_id": "c1", "role_code": "SAFETY_MANAGER"}


# ── record_inspection_results ──────────────────────────────────────────────

def test_record_normal_only_uses_bridge_once_no_direct_update():
    resp = {
        ("safety_inspection_results", "insert"): [{"id": 1}, {"id": 2}],
        ("safety_inspections", "select"): [{"assignment_id": "ws-1"}],
        ("work_schedules", "update"): [{"id": "ws-1"}],
    }
    fake = _FakeSB(resp); spy = _BridgeSpy()
    with _Patch(fake, spy, "_ensure_inspection_own"):
        body = {"results": [{"result": "PASS", "inspection_set_item_id": "i1"},
                            {"result": "PASS", "inspection_set_item_id": "i2"}]}
        out = asyncio.run(R.record_inspection_results("insp-1", body, current=CUR))
    # DEBT-W3-02: 직접 results INSERT 없음 (RPC 서비스 1회)
    assert ("safety_inspection_results", "insert") not in fake.log
    # schedule completed side effect 유지
    assert ("work_schedules", "update") in fake.log
    # writer bridge exactly 1 (direct safety_inspections UPDATE 은 fake 가 raise 하므로 도달 자체가 증거)
    assert len(spy.calls) == 1
    assert spy.calls[0]["inspection_id"] == "insp-1"
    assert spy.calls[0]["actor_id"] == "user-1"
    assert spy.calls[0]["reason"] == "SAFE_RESULT_AUTO_COMPLETE"
    # response contract unchanged
    assert out == {"status": "success", "message": "2개 결과가 기록됐습니다.",
                   "data": {"inspection_id": "insp-1", "created": 2}}


def test_record_with_fail_present_no_bridge():
    resp = {
        ("safety_inspection_results", "insert"): [{"id": 1}],
        ("safety_inspections", "select"): [{"assignment_id": "ws-1"}],
    }
    fake = _FakeSB(resp); spy = _BridgeSpy()
    with _Patch(fake, spy, "_ensure_inspection_own"):
        body = {"results": [{"result": "PASS"}, {"result": "FAIL"}]}
        out = asyncio.run(R.record_inspection_results("insp-1", body, current=CUR))
    assert len(spy.calls) == 0                       # FAIL 있으면 완료 처리 안 함
    assert ("work_schedules", "update") not in fake.log
    assert out["status"] == "success" and out["data"]["created"] == 2


def test_record_with_na_present_no_bridge():
    resp = {
        ("safety_inspection_results", "insert"): [{"id": 1}],
        ("safety_inspections", "select"): [{"assignment_id": "ws-1"}],
    }
    fake = _FakeSB(resp); spy = _BridgeSpy()
    with _Patch(fake, spy, "_ensure_inspection_own"):
        body = {"results": [{"result": "NA"}]}
        asyncio.run(R.record_inspection_results("insp-1", body, current=CUR))
    assert len(spy.calls) == 0


def test_record_bridge_error_maps_409():
    resp = {
        ("safety_inspection_results", "insert"): [{"id": 1}],
        ("safety_inspections", "select"): [{"assignment_id": "ws-1"}],
        ("work_schedules", "update"): [{"id": "ws-1"}],
    }
    fake = _FakeSB(resp)
    spy = _BridgeSpy(raise_exc=InspectionStatusWriteError("REVISION_CONFLICT", "x"))
    with _Patch(fake, spy, "_ensure_inspection_own"):
        body = {"results": [{"result": "PASS"}]}
        try:
            asyncio.run(R.record_inspection_results("insp-1", body, current=CUR))
            raise AssertionError("expected HTTPException 409")
        except HTTPException as e:
            assert e.status_code == 409
            assert e.detail["code"] == "REVISION_CONFLICT"


# ── complete_inspection ────────────────────────────────────────────────────

def test_complete_zero_linked_schedule_only_no_bridge():
    resp = {
        ("safety_inspections", "select"): [],                       # cardinality 0
        ("work_schedules", "select"): [{"id": "ws-1", "completed_at": None,
                                        "status_code": "in_progress", "inspection_set_id": None}],
        ("work_schedules", "update"): [{"id": "ws-1", "factory_id": "f1", "inspection_set_id": None}],
    }
    fake = _FakeSB(resp); spy = _BridgeSpy()
    with _Patch(fake, spy, "_ensure_ws_own"):
        out = asyncio.run(R.complete_inspection("ws-1", body={}, current=CUR))
    assert ("work_schedules", "update") in fake.log              # schedule orchestration 진행
    assert len(spy.calls) == 0                                   # inspection command 없음
    assert out["status"] == "success"


def test_complete_one_linked_schedule_and_bridge_once():
    resp = {
        ("safety_inspections", "select"): [{"id": "insp-9"}],       # cardinality 1
        ("work_schedules", "select"): [{"id": "ws-1", "completed_at": None,
                                        "status_code": "in_progress", "inspection_set_id": None}],
        ("work_schedules", "update"): [{"id": "ws-1", "factory_id": "f1", "inspection_set_id": None}],
    }
    fake = _FakeSB(resp); spy = _BridgeSpy()
    with _Patch(fake, spy, "_ensure_ws_own"):
        out = asyncio.run(R.complete_inspection("ws-1", body={}, current=CUR))
    assert ("work_schedules", "update") in fake.log             # schedule orchestration 그대로
    assert len(spy.calls) == 1
    assert spy.calls[0]["inspection_id"] == "insp-9"
    assert spy.calls[0]["reason"] == "SAFE_COMPLETE"
    assert spy.calls[0]["actor_id"] == "user-1"
    assert out["status"] == "success"


def test_complete_two_linked_409_before_schedule_update():
    resp = {
        ("safety_inspections", "select"): [{"id": "a"}, {"id": "b"}],   # cardinality 2 -> hard fail
        ("work_schedules", "update"): [{"id": "ws-1", "factory_id": "f1", "inspection_set_id": None}],
    }
    fake = _FakeSB(resp); spy = _BridgeSpy()
    with _Patch(fake, spy, "_ensure_ws_own"):
        try:
            asyncio.run(R.complete_inspection("ws-1", body={}, current=CUR))
            raise AssertionError("expected 409 INSPECTION_CARDINALITY_VIOLATION")
        except HTTPException as e:
            assert e.status_code == 409
            assert e.detail["code"] == "INSPECTION_CARDINALITY_VIOLATION"
    # 409 는 schedule mutation 이전에 발생해야 한다
    assert ("work_schedules", "update") not in fake.log
    assert len(spy.calls) == 0


def test_complete_bridge_error_maps_409():
    resp = {
        ("safety_inspections", "select"): [{"id": "insp-9"}],
        ("work_schedules", "select"): [{"id": "ws-1", "completed_at": None,
                                        "status_code": "in_progress", "inspection_set_id": None}],
        ("work_schedules", "update"): [{"id": "ws-1", "factory_id": "f1", "inspection_set_id": None}],
    }
    fake = _FakeSB(resp)
    spy = _BridgeSpy(raise_exc=InspectionStatusWriteError("INVALID_STATUS_TRANSITION", "x"))
    with _Patch(fake, spy, "_ensure_ws_own"):
        try:
            asyncio.run(R.complete_inspection("ws-1", body={}, current=CUR))
            raise AssertionError("expected HTTPException 409")
        except HTTPException as e:
            assert e.status_code == 409
            assert e.detail["code"] == "INVALID_STATUS_TRANSITION"


if __name__ == "__main__":
    g = dict(globals())
    tests = sorted((n, f) for n, f in g.items() if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS {name}"); passed += 1
        except Exception as e:  # noqa: BLE001
            import traceback
            print(f"FAIL {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n== {passed} passed, {failed} failed / {passed + failed} total ==")
    sys.exit(1 if failed else 0)
