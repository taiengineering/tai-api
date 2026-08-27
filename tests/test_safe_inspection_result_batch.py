"""OBJ-01 DEBT-W3-02 — SAFE result batch service tests.

RPC 정확히 1회, result→canonical result_code 정규화, 직접 테이블 write 0,
typed 에러, mode/count 반환. DB 없이 fake supabase 로 관찰.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.safe_inspection_result_batch import (  # noqa: E402
    RPC_NAME,
    SafeResultBatchError,
    record_safe_result_batch,
)

INSP = "3f9cf36f-5bbc-4dad-9ba6-e71643020e9a"


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
        self.table_calls.append(a)
        raise AssertionError("service must not touch tables directly")


def _ok(mode="CREATED", count=3):
    return {"ok": True, "mode": mode, "count": count,
            "data": {"inspection_id": INSP, "created": count}}


def _results():
    return [
        {"inspection_set_item_id": "11111111-1111-1111-1111-111111111111", "result": "ok", "note": "", "photo_url": None},
        {"inspection_set_item_id": None, "result": "fail", "note": "x"},
        {"result": "NA"},
    ]


# RPC called exactly once, with normalized canonical result_code
def test_rpc_once_normalized():
    sb = FakeSupabase(_ok())
    out = record_safe_result_batch(sb, inspection_id=INSP, results=_results())
    assert len(sb.calls) == 1
    name, params = sb.calls[0]
    assert name == RPC_NAME
    assert params["p_inspection_id"] == INSP
    codes = [r["result_code"] for r in params["p_results"]]
    assert codes == ["NORMAL", "ABNORMAL", "ABNORMAL"]   # ok→NORMAL, fail→ABNORMAL, NA→ABNORMAL
    # note default "" and photo_url passthrough
    assert params["p_results"][0]["note"] == ""
    assert params["p_results"][2]["note"] == ""
    assert out["mode"] == "CREATED" and out["count"] == 3


# no direct table write
def test_no_direct_table_write():
    sb = FakeSupabase(_ok())
    record_safe_result_batch(sb, inspection_id=INSP, results=_results())
    assert sb.table_calls == []


# replay passthrough + list unwrap
def test_replay_and_unwrap():
    assert record_safe_result_batch(FakeSupabase(_ok(mode="REPLAY")), inspection_id=INSP, results=_results())["mode"] == "REPLAY"
    assert record_safe_result_batch(FakeSupabase([_ok()]), inspection_id=INSP, results=_results())["count"] == 3


# typed errors: not-found / conflict / empty / generic / malformed / input guard
def test_typed_errors():
    try:
        record_safe_result_batch(FakeSupabase({"ok": False, "error": "INSPECTION_NOT_FOUND"}), inspection_id=INSP, results=_results()); assert False
    except SafeResultBatchError as e:
        assert e.is_not_found and not e.is_conflict

    try:
        record_safe_result_batch(FakeSupabase({"ok": False, "error": "RESULT_INITIAL_BATCH_CONFLICT"}), inspection_id=INSP, results=_results()); assert False
    except SafeResultBatchError as e:
        assert e.is_conflict and not e.is_not_found

    try:
        record_safe_result_batch(FakeSupabase({"ok": False, "error": "RESULT_CODE_UNRESOLVED"}), inspection_id=INSP, results=_results()); assert False
    except SafeResultBatchError as e:
        assert not e.is_not_found and not e.is_conflict

    try:
        record_safe_result_batch(FakeSupabase("garbage"), inspection_id=INSP, results=_results()); assert False
    except SafeResultBatchError as e:
        assert e.code == "RPC_RESULT_MALFORMED"

    # input guards raise before any RPC call
    sb = FakeSupabase(_ok())
    try:
        record_safe_result_batch(sb, inspection_id="", results=_results()); assert False
    except SafeResultBatchError as e:
        assert e.code == "INVALID_RESULT_INPUT"
    assert sb.calls == []

    sb = FakeSupabase(_ok())
    try:
        record_safe_result_batch(sb, inspection_id=INSP, results=[]); assert False
    except SafeResultBatchError as e:
        assert e.is_empty
    assert sb.calls == []


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
