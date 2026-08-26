"""OBJ-01 KNOT-3C1 — SAFE start service tests (T11-T14).

순수 서비스 계약: RPC 정확히 1회, 직접 테이블 write 0, replay passthrough,
typed 에러. DB/네트워크 없이 fake supabase 로 RPC 호출을 관찰한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.inspection_record_start import (  # noqa: E402
    RPC_NAME,
    SafeStartError,
    start_safe_inspection,
)

TS = "2026-08-27T09:00:00Z"


class _Exec:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        class _R:
            data = self._payload
        return _R()


class FakeSupabase:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []
        self.table_calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return _Exec(self._payload)

    def table(self, *a, **k):
        self.table_calls.append(("table", a, k))
        raise AssertionError("service must not touch tables directly")

    def from_(self, *a, **k):
        self.table_calls.append(("from_", a, k))
        raise AssertionError("service must not touch tables directly")


def _ok(replayed=False, status="IN_PROGRESS"):
    return {
        "ok": True,
        "replayed": replayed,
        "data": {
            "inspection_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "work_schedule_id": "99999999-9999-9999-9999-999999999999",
            "factory_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            "inspection_status": status,
            "started_at": TS,
            "inspector_name": "홍길동",
        },
    }


def _call(sb, **over):
    kw = dict(schedule_id="99999999-9999-9999-9999-999999999999",
              factory_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
              started_at=TS, inspector_name="홍길동")
    kw.update(over)
    return start_safe_inspection(sb, **kw)


# T11 — RPC called exactly once, correct name + params
def test_rpc_called_exactly_once():
    sb = FakeSupabase(_ok())
    out = _call(sb)
    assert len(sb.calls) == 1
    name, params = sb.calls[0]
    assert name == RPC_NAME == "fn_start_safe_inspection_record"
    for k in ("p_schedule_id", "p_factory_id", "p_started_at", "p_inspector_name"):
        assert k in params, k
    assert out["data"]["inspection_status"] == "IN_PROGRESS"


# T12 — no direct table write
def test_no_direct_table_write():
    sb = FakeSupabase(_ok())
    _call(sb)
    assert sb.table_calls == []


# T13 — replay flag passthrough + scalar/list unwrap
def test_replay_passthrough_and_unwrap():
    assert _call(FakeSupabase(_ok(replayed=True)))["replayed"] is True
    # list-wrapped jsonb also unwraps
    assert _call(FakeSupabase([_ok()]))["data"]["inspection_status"] == "IN_PROGRESS"


# T14 — typed errors: not-found / cardinality flags + rpc error + malformed + input guard
def test_typed_errors():
    # WORK_SCHEDULE_NOT_FOUND → is_not_found
    try:
        _call(FakeSupabase({"ok": False, "error": "WORK_SCHEDULE_NOT_FOUND", "detail": "x"}))
        assert False
    except SafeStartError as e:
        assert e.is_not_found and not e.is_cardinality

    # INSPECTION_CARDINALITY_VIOLATION → is_cardinality
    try:
        _call(FakeSupabase({"ok": False, "error": "INSPECTION_CARDINALITY_VIOLATION", "detail": ""}))
        assert False
    except SafeStartError as e:
        assert e.is_cardinality and not e.is_not_found

    # generic rpc error → neither flag
    try:
        _call(FakeSupabase({"ok": False, "error": "SOME_OTHER", "detail": ""}))
        assert False
    except SafeStartError as e:
        assert not e.is_not_found and not e.is_cardinality

    # malformed result
    try:
        _call(FakeSupabase("garbage"))
        assert False
    except SafeStartError as e:
        assert e.code == "RPC_RESULT_MALFORMED"

    # input guards (no RPC call happens)
    for over, code in (
        ({"schedule_id": None}, "INVALID_START_INPUT"),
        ({"factory_id": None}, "INVALID_START_INPUT"),
        ({"started_at": None}, "START_TIMESTAMP_INVALID"),
    ):
        sb = FakeSupabase(_ok())
        try:
            _call(sb, **over)
            assert False
        except SafeStartError as e:
            assert e.code == code
        assert sb.calls == []   # RPC 호출 자체가 없어야 함


if __name__ == "__main__":
    g = dict(globals())
    tests = sorted((k, v) for k, v in g.items() if k.startswith("test_") and callable(v))
    p = f = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS {name}"); p += 1
        except Exception as e:
            import traceback
            print(f"FAIL {name}: {e}"); traceback.print_exc(); f += 1
    print(f"\n== {p} passed, {f} failed / {p + f} total ==")
    raise SystemExit(1 if f else 0)
