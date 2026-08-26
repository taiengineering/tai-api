"""OBJ-01 KNOT-2 COMMIT 9 — worker /recent + /history effective read cutover tests.

라우터 함수를 fake supabase 로 직접 호출한다. effective record 어댑터
(fn_list_effective_inspection_records_by_inspector)만 소비하고, base ledger
(safety_inspections) 직독이 없으며, per-row resolver 호출(N+1)이 없음을 증명한다.
submit_check(writer) 는 read cutover 의 영향을 받지 않음을 정적으로 확인한다.
"""
from __future__ import annotations

import contextlib
import inspect as _inspect
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import routers.worker_check as W  # noqa: E402


class _RpcCall:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return type("R", (), {"data": self._data})()


class _UsersQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if r.get(col) == val]
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def execute(self):
        return type("R", (), {"data": list(self._rows)})()


class FakeSB:
    def __init__(self, users, records):
        self._users = users
        self._records = records
        self.rpc_calls = []  # [(name, params)]

    def table(self, name):
        if name == "safety_inspections":
            raise AssertionError("DIRECT BASE READ FORBIDDEN in worker GET routes")
        if name == "users":
            return _UsersQuery(self._users)
        if name == "worker_registry":
            return _UsersQuery([])
        raise AssertionError(f"unexpected table {name!r}")

    def rpc(self, name, params=None):
        self.rpc_calls.append((name, params))
        if name == "fn_list_effective_inspection_records_by_inspector":
            return _RpcCall(self._records)
        raise AssertionError(f"unexpected rpc {name!r}")


def _records():
    return [
        {"inspection_id": "i1", "inspection_date": "2026-05-14T00:00:00", "inspection_status": "COMPLETED", "overall_result": "NORMAL"},
        {"inspection_id": "i2", "inspection_date": "2026-05-13T00:00:00", "inspection_status": "COMPLETED", "overall_result": "ABNORMAL"},
        {"inspection_id": "i3", "inspection_date": "2026-05-12T00:00:00", "inspection_status": "COMPLETED", "overall_result": "HOLD"},
        {"inspection_id": "i4", "inspection_date": "2026-05-11T00:00:00", "inspection_status": "IN_PROGRESS", "overall_result": None},
    ]


USERS = [{"id": "u-1", "phone": "01012345678"}]


@contextlib.contextmanager
def _patch(fake):
    orig = W.get_supabase
    W.get_supabase = lambda: fake
    try:
        yield
    finally:
        W.get_supabase = orig


def test_recent_uses_effective_adapter_single_rpc():
    fake = FakeSB(USERS, _records())
    with _patch(fake):
        out = W.get_recent_checks(phone="010-1234-5678", limit=5)
    assert out["status"] == "success"
    assert len(out["data"]["items"]) == 4
    # single adapter RPC, no per-row resolver -> N+1 = 0
    assert fake.rpc_calls == [("fn_list_effective_inspection_records_by_inspector", {"p_inspector_id": "u-1", "p_limit": 5})]
    assert all(c[0] != "fn_resolve_inspection_record" for c in fake.rpc_calls)


def test_history_uses_effective_adapter_worker_id():
    fake = FakeSB(USERS, _records())
    with _patch(fake):
        out = W.get_check_history(worker_id="u-1", limit=50)
    assert len(out["data"]["items"]) == 4
    assert fake.rpc_calls == [("fn_list_effective_inspection_records_by_inspector", {"p_inspector_id": "u-1", "p_limit": 50})]
    assert all(c[0] != "fn_resolve_inspection_record" for c in fake.rpc_calls)


def test_item_contract_keys_exact():
    fake = FakeSB(USERS, _records())
    with _patch(fake):
        items = W.get_recent_checks(phone="01012345678")["data"]["items"]
    for it in items:
        assert set(it.keys()) == {"id", "inspection_date", "inspection_status", "result_summary", "status_code"}


def test_status_code_alias_mapping():
    fake = FakeSB(USERS, _records())
    with _patch(fake):
        items = W.get_recent_checks(phone="01012345678")["data"]["items"]
    by_id = {it["id"]: it for it in items}
    assert by_id["i1"]["status_code"] == "COMPLETED"   # NORMAL -> COMPLETED
    assert by_id["i2"]["status_code"] == "ISSUE"        # ABNORMAL -> ISSUE
    assert by_id["i3"]["status_code"] == "HOLD"         # HOLD -> HOLD


def test_null_summary_status_code_is_inspection_status():
    fake = FakeSB(USERS, _records())
    with _patch(fake):
        items = W.get_recent_checks(phone="01012345678")["data"]["items"]
    by_id = {it["id"]: it for it in items}
    assert by_id["i4"]["result_summary"] is None
    assert by_id["i4"]["status_code"] == "IN_PROGRESS"  # summary None -> inspection_status


def test_result_summary_passthrough_and_id_is_inspection_id():
    fake = FakeSB(USERS, _records())
    with _patch(fake):
        items = W.get_recent_checks(phone="01012345678")["data"]["items"]
    assert [it["id"] for it in items] == ["i1", "i2", "i3", "i4"]  # adapter order preserved
    by_id = {it["id"]: it for it in items}
    assert by_id["i1"]["result_summary"] == "NORMAL"
    assert by_id["i2"]["result_summary"] == "ABNORMAL"


def test_inspector_not_found_empty_no_rpc():
    fake = FakeSB([], _records())  # no matching user
    with _patch(fake):
        out = W.get_recent_checks(phone="01099999999")
    assert out["data"]["items"] == []
    assert fake.rpc_calls == []  # no adapter call when inspector unresolved


def test_router_maps_adapter_output_1to1_no_filter():
    # 라우터는 어댑터가 준 목록을 그대로 매핑한다(inactive 필터/inspector 소속 판정은 어댑터 책임).
    recs = _records() + [
        {"inspection_id": "i5", "inspection_date": "2026-05-10T00:00:00", "inspection_status": "COMPLETED", "overall_result": "NORMAL"},
    ]
    fake = FakeSB(USERS, recs)
    with _patch(fake):
        items = W.get_recent_checks(phone="01012345678")["data"]["items"]
    assert len(items) == len(recs)  # 1:1, no router-side filtering


def test_submit_check_writer_unchanged_static():
    # §18: submit_check 는 read cutover 의 영향을 받지 않는다 — effective 어댑터를 호출하지 않고
    # 여전히 base ledger 에 write 한다.
    src = _inspect.getsource(W.submit_check)
    assert "list_effective_inspection_records_by_inspector" not in src
    assert 'supabase.table("safety_inspections").insert(' in src
    assert 'supabase.table("safety_inspection_results").insert(' in src


if __name__ == "__main__":
    g = dict(globals())
    tests = sorted((n, f) for n, f in g.items() if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS {name}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {name}: {type(e).__name__}: {e}"); failed += 1
    print(f"\n== {passed} passed, {failed} failed / {passed + failed} total ==")
    sys.exit(1 if failed else 0)
