"""OBJ-01 KNOT-3B COMMIT B — worker submission service tests.

순수 서비스 계약 검증: 결정적 정체성/해시, 정규화, RPC 정확히 1회, typed 에러.
DB/네트워크 없이 fake supabase 로 RPC 호출을 관찰한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.worker_inspection_submission import (  # noqa: E402
    WorkerSubmissionError,
    compute_request_hash,
    compute_submission_id,
    normalize_phone,
    normalize_submitted_at,
    submit_worker_inspection,
)

TS = "2026-08-27T09:00:00Z"
ITEMS = [
    {"inspection_set_item_id": "11111111-1111-1111-1111-111111111111",
     "name": "소화기", "result_code": "NORMAL", "note": "", "photo_urls": []},
    {"inspection_set_item_id": "22222222-2222-2222-2222-222222222222",
     "name": "비상구", "result_code": "ABNORMAL", "note": "막힘", "photo_urls": ["u1"]},
]


class _Exec:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        class _R:
            data = self._payload
        return _R()


class FakeSupabase:
    """rpc(name, params).execute() 를 관찰하고 미리 정한 payload 를 돌려준다."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = []
        self.insert_calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return _Exec(self._payload)

    # 직접 테이블 접근이 일어나면 즉시 실패시키기 위한 트랩
    def table(self, *a, **k):
        self.insert_calls.append(("table", a, k))
        raise AssertionError("service must not touch tables directly")

    def from_(self, *a, **k):
        self.insert_calls.append(("from_", a, k))
        raise AssertionError("service must not touch tables directly")


def _ok_payload(overall="ABNORMAL", replayed=False):
    return {
        "ok": True,
        "replayed": replayed,
        "data": {
            "inspection_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "revision": 0,
            "inspection_status": "COMPLETED",
            "overall_result": overall,
            "normal_count": 1, "abnormal_count": 1, "hold_count": 0, "total_count": 2,
            "issue_items": [], "inspector_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
        },
    }


def _call(sb, items=None, submitted_at=TS, phone="010-1234-5678", schedule_ref="SCHED-1"):
    return submit_worker_inspection(
        sb,
        schedule_ref=schedule_ref,
        schedule_id="99999999-9999-9999-9999-999999999999",
        factory_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
        inspector_id="ffffffff-ffff-ffff-ffff-ffffffffffff",
        phone=phone,
        submitted_at=submitted_at,
        inspection_type="ROUTINE",
        items=items if items is not None else ITEMS,
    )


# ── determinism ─────────────────────────────────────────────────────────────

def test_submission_id_is_deterministic():
    dt = normalize_submitted_at(TS)
    a = compute_submission_id("SCHED-1", "010-1234-5678", dt)
    b = compute_submission_id("SCHED-1", "010-1234-5678", dt)
    assert a == b


def test_phone_normalization_stable_identity():
    dt = normalize_submitted_at(TS)
    a = compute_submission_id("SCHED-1", "010-1234-5678", dt)
    b = compute_submission_id("SCHED-1", "01012345678", dt)
    c = compute_submission_id("SCHED-1", "(010) 1234 5678", dt)
    assert a == b == c
    assert normalize_phone("010-1234-5678") == "01012345678"


def test_request_hash_is_deterministic():
    dt = normalize_submitted_at(TS)
    h1 = compute_request_hash(schedule_ref="SCHED-1", phone="010-1234-5678",
                              submitted_at=dt, inspection_type="ROUTINE", items=ITEMS)
    h2 = compute_request_hash(schedule_ref="SCHED-1", phone="01012345678",
                              submitted_at=dt, inspection_type="ROUTINE", items=list(ITEMS))
    assert h1 == h2 and len(h1) == 64


def test_same_identity_changed_item_same_id_different_hash():
    dt = normalize_submitted_at(TS)
    sid1 = compute_submission_id("SCHED-1", "010-1234-5678", dt)
    h1 = compute_request_hash(schedule_ref="SCHED-1", phone="010-1234-5678",
                              submitted_at=dt, inspection_type="ROUTINE", items=ITEMS)
    changed = [dict(ITEMS[0]), dict(ITEMS[1], result_code="HOLD")]
    sid2 = compute_submission_id("SCHED-1", "010-1234-5678", dt)
    h2 = compute_request_hash(schedule_ref="SCHED-1", phone="010-1234-5678",
                              submitted_at=dt, inspection_type="ROUTINE", items=changed)
    assert sid1 == sid2          # 정체성 동일 → 같은 submission_id
    assert h1 != h2              # 내용 변경 → 다른 hash


# ── submitted_at required ────────────────────────────────────────────────────

def test_missing_submitted_at_raises():
    for bad in (None, ""):
        try:
            normalize_submitted_at(bad)
            assert False, "expected error"
        except WorkerSubmissionError as e:
            assert e.code == "WORKER_SUBMISSION_TIMESTAMP_INVALID"


def test_invalid_submitted_at_raises():
    try:
        normalize_submitted_at("not-a-date")
        assert False, "expected error"
    except WorkerSubmissionError as e:
        assert e.code == "WORKER_SUBMISSION_TIMESTAMP_INVALID"


def test_z_suffix_and_naive_are_utc():
    a = normalize_submitted_at("2026-08-27T09:00:00Z")
    b = normalize_submitted_at("2026-08-27T09:00:00")
    assert a == b
    assert a.tzinfo is not None


# ── RPC exactly once + no direct table access ────────────────────────────────

def test_rpc_called_exactly_once():
    sb = FakeSupabase(_ok_payload())
    out = _call(sb)
    assert len(sb.calls) == 1
    name, params = sb.calls[0]
    assert name == "fn_create_worker_inspection_record"
    assert sb.insert_calls == []
    assert out["replayed"] is False
    assert out["data"]["overall_result"] == "ABNORMAL"


def test_rpc_params_shape():
    sb = FakeSupabase(_ok_payload())
    _call(sb)
    _, params = sb.calls[0]
    for k in ("p_submission_id", "p_request_hash", "p_source", "p_schedule_id",
              "p_factory_id", "p_inspector_id", "p_submitted_at", "p_results",
              "p_request_payload"):
        assert k in params, k
    assert isinstance(params["p_results"], list) and len(params["p_results"]) == 2
    # canonical result_code passed through untouched
    assert {r["result_code"] for r in params["p_results"]} == {"NORMAL", "ABNORMAL"}


def test_scalar_jsonb_and_list_jsonb_both_unwrap():
    # scalar
    sb1 = FakeSupabase(_ok_payload())
    assert _call(sb1)["data"]["inspection_status"] == "COMPLETED"
    # list-wrapped
    sb2 = FakeSupabase([_ok_payload()])
    assert _call(sb2)["data"]["inspection_status"] == "COMPLETED"


def test_replay_flag_passthrough():
    sb = FakeSupabase(_ok_payload(replayed=True))
    assert _call(sb)["replayed"] is True


# ── typed error mapping ──────────────────────────────────────────────────────

def test_rpc_error_becomes_typed_error():
    sb = FakeSupabase({"ok": False, "error": "WORK_SCHEDULE_NOT_FOUND", "detail": "x"})
    try:
        _call(sb)
        assert False, "expected error"
    except WorkerSubmissionError as e:
        assert e.code == "WORK_SCHEDULE_NOT_FOUND"
        assert e.is_conflict is False


def test_conflict_codes_flag_is_conflict():
    for code in ("SUBMISSION_ID_REUSE_CONFLICT", "INSPECTION_ALREADY_EXISTS_FOR_SCHEDULE",
                 "FACTORY_MISMATCH"):
        sb = FakeSupabase({"ok": False, "error": code, "detail": ""})
        try:
            _call(sb)
            assert False, "expected error"
        except WorkerSubmissionError as e:
            assert e.code == code and e.is_conflict is True


def test_malformed_rpc_result_raises():
    sb = FakeSupabase("garbage")
    try:
        _call(sb)
        assert False, "expected error"
    except WorkerSubmissionError as e:
        assert e.code == "RPC_RESULT_MALFORMED"


if __name__ == "__main__":
    g = dict(globals())
    tests = sorted((n, f) for n, f in g.items() if n.startswith("test_") and callable(f))
    passed = failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS {name}"); passed += 1
        except Exception as e:  # noqa: BLE001
            import traceback
            print(f"FAIL {name}: {type(e).__name__}: {e}"); traceback.print_exc(); failed += 1
    print(f"\n== {passed} passed, {failed} failed / {passed + failed} total ==")
    sys.exit(1 if failed else 0)
