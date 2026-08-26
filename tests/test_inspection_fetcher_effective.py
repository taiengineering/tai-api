"""OBJ-01 KNOT-2 COMMIT 10 — inspection_fetcher effective read cutover tests.

fetch() 를 fake supabase + monkeypatched resolver 로 호출한다. base ledger
(safety_inspections / safety_inspection_results) 직독이 없고, 비활성 점검은
발행 실패이며, is_active=true 결과만 소비하고, 집계가 canonical ABNORMAL 로
계산됨(legacy result_code=="ISSUE" 비교 제거)을 증명한다.
"""
from __future__ import annotations

import asyncio
import inspect as _inspect
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import services.document_engine.fetchers.inspection_fetcher as F  # noqa: E402
from services.inspection_record_resolver import InspectionRecordError  # noqa: E402


class _FakeSB:
    """asset_id/inspector_id 가 None 이면 어떤 table 도 호출되지 않는다.
    base ledger 직독이 발생하면 즉시 실패시킨다."""

    def table(self, name):
        if name in ("safety_inspections", "safety_inspection_results"):
            raise AssertionError(f"DIRECT BASE READ FORBIDDEN in fetcher: table({name!r})")
        raise AssertionError(f"unexpected table {name!r} (fixture uses null asset/inspector)")


def _record(**over):
    rec = {
        "inspection_id": "insp-1",
        "revision": 0,
        "is_active": True,
        "inspection_status": "COMPLETED",
        "legacy_raw_status_code": "completed",
        "assignment_id": None,
        "asset_id": None,        # asset/factory/company/inspector 조회 skip
        "inspector_id": None,
        "inspection_date": "2026-05-14T00:00:00",
        "submitted_by": None,
        "factory_id": None,
        "results": [],
        "overall_result": None,
    }
    rec.update(over)
    return rec


def _result(rid, code, is_active=True, **over):
    r = {
        "result_id": rid,
        "is_active": is_active,
        "inspection_set_item_id": None,
        "item_name": f"항목 {rid}",
        "result_code": code,
        "value_text": None,
        "value_number": None,
        "note": f"메모 {rid}",
        "checked_at": "2026-05-14T07:49:43+00:00",
        "photo_url": None,
        "photo_urls": [],
        "created_at": "2026-05-14T07:49:44",
    }
    r.update(over)
    return r


class _Patch:
    def __init__(self, record=None, raiser=None):
        self.record = record
        self.raiser = raiser
        self._orig = {}

    def __enter__(self):
        self._orig = {"g": F.get_supabase, "r": F.resolve_inspection_record}
        F.get_supabase = lambda: _FakeSB()
        if self.raiser is not None:
            def _boom(iid, sb=None):
                raise self.raiser
            F.resolve_inspection_record = _boom
        else:
            F.resolve_inspection_record = lambda iid, sb=None: self.record
        return self

    def __exit__(self, *a):
        F.get_supabase = self._orig["g"]
        F.resolve_inspection_record = self._orig["r"]
        return False


def _fetch(record=None, raiser=None, inspection_id="insp-1"):
    fetcher = F.InspectionFetcher.__new__(F.InspectionFetcher)  # BaseFetcher.__init__ 우회
    with _Patch(record=record, raiser=raiser):
        return asyncio.run(fetcher.fetch({"inspection_id": inspection_id}))


def test_missing_inspection_id_raises():
    fetcher = F.InspectionFetcher.__new__(F.InspectionFetcher)
    try:
        asyncio.run(fetcher.fetch({}))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_fetch_consumes_resolver_no_base_read():
    out = _fetch(_record(results=[_result("r1", "NORMAL")]))
    assert out["total_count"] == 1
    # _FakeSB 가 safety_inspections/results 직독 시 AssertionError 를 던지므로,
    # 여기까지 도달했다는 것 자체가 base 직독 부재의 증거다.


def test_inactive_inspection_raises():
    try:
        _fetch(_record(is_active=False, results=[_result("r1", "NORMAL")]))
        raise AssertionError("inactive inspection must raise")
    except ValueError as e:
        assert "비활성" in str(e)


def test_only_active_results_consumed():
    rec = _record(results=[
        _result("r1", "NORMAL", is_active=True),
        _result("r2", "ABNORMAL", is_active=True),
        _result("r3", "HOLD", is_active=True),
        _result("r4", "ABNORMAL", is_active=False),  # inactive → 제외
    ])
    out = _fetch(rec)
    assert out["total_count"] == 3  # inactive 제외
    ids = [i["id"] for i in out["items"]]
    assert "r4" not in ids


def test_issue_count_uses_abnormal_not_issue():
    rec = _record(results=[
        _result("r1", "NORMAL"),
        _result("r2", "ABNORMAL"),
        _result("r3", "HOLD"),
    ])
    out = _fetch(rec)
    assert out["normal_count"] == 1
    assert out["issue_count"] == 1      # ABNORMAL 1건
    assert out["hold_count"] == 1
    assert out["abnormal_count"] == out["issue_count"]  # canonical alias
    assert out["has_issue"] is True
    assert len(out["issue_items"]) == 1
    assert out["issue_items"][0]["item_name"] == "항목 r2"


def test_legacy_issue_string_not_counted():
    # canonical 은 ABNORMAL 이다. 혹시 남은 "ISSUE" 문자열이 있어도 issue_count 로 세지 않는다.
    rec = _record(results=[_result("r1", "ISSUE"), _result("r2", "ABNORMAL")])
    out = _fetch(rec)
    assert out["issue_count"] == 1  # ABNORMAL 만, "ISSUE" 는 세지 않음


def test_item_template_shape_exact():
    out = _fetch(_record(results=[_result("r1", "NORMAL")]))
    assert set(out["items"][0].keys()) == {
        "id", "item_name", "result_code", "note", "photo_urls", "value_text", "value_number",
    }


def test_status_code_alias_and_summary_abnormal():
    out = _fetch(_record(overall_result="ABNORMAL", inspection_status="COMPLETED",
                         results=[_result("r1", "ABNORMAL")]))
    assert out["result_summary"] == "ABNORMAL"
    assert out["inspection_status"] == "COMPLETED"
    assert out["status_code"] == "ISSUE"  # ABNORMAL → ISSUE (legacy alias)


def test_status_code_null_summary_is_inspection_status():
    out = _fetch(_record(overall_result=None, inspection_status="IN_PROGRESS", results=[]))
    assert out["result_summary"] is None
    assert out["status_code"] == "IN_PROGRESS"  # summary None → inspection_status


def test_resolver_error_becomes_valueerror():
    try:
        _fetch(raiser=InspectionRecordError("INSPECTION_NOT_FOUND", "insp-1"))
        raise AssertionError("resolver error must become ValueError")
    except ValueError as e:
        assert "찾을 수 없습니다" in str(e)


def test_no_result_code_issue_comparison_static():
    src = _inspect.getsource(F)
    assert '== "ISSUE"' not in src  # result_code 를 "ISSUE" 로 비교하지 않는다
    assert '"ABNORMAL"' in src      # 집계는 canonical ABNORMAL 로 한다


def test_no_direct_base_read_static():
    src = _inspect.getsource(F)
    assert '.table("safety_inspections")' not in src
    assert '.table("safety_inspection_results")' not in src
    assert "resolve_inspection_record" in src


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
