"""OBJ-01 KNOT-3A COMMIT A — writer bridge tests.

bridge 모듈의 resolve_inspection_record / change_status 를 monkeypatch 해
전표화 흐름 + 멱등성 + concurrency 수렴을 검증한다. DB / RPC 실호출 없음.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import services.inspection_record_writer_bridge as B  # noqa: E402
from services.inspection_record_resolver import InspectionRecordError  # noqa: E402


class _SB:
    """sentinel supabase (bridge 는 이 값을 resolver/command 에 그대로 넘겨야 한다)."""


def _rec(status="IN_PROGRESS", revision=0, is_active=True, inspection_id="insp-1"):
    return {
        "inspection_id": inspection_id,
        "revision": revision,
        "is_active": is_active,
        "inspection_status": status,
    }


class _Patch:
    """resolve 는 순차 반환(리스트), change_status 는 콜 기록 + 선택적 raise."""

    def __init__(self, resolve_seq, change_raise=None, change_return=None):
        self._resolve_seq = list(resolve_seq)
        self._change_raise = change_raise
        self._change_return = change_return if change_return is not None else {"revision": 1}
        self.resolve_calls = []
        self.change_calls = []
        self._orig = {}

    def _resolve(self, inspection_id, supabase=None):
        self.resolve_calls.append((inspection_id, supabase))
        nxt = self._resolve_seq.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def _change(self, supabase, inspection_id, *, expected_revision, command_id, to_status, actor_id, reason=None):
        self.change_calls.append({
            "supabase": supabase, "inspection_id": inspection_id,
            "expected_revision": expected_revision, "command_id": command_id,
            "to_status": to_status, "actor_id": actor_id, "reason": reason,
        })
        if self._change_raise is not None:
            raise self._change_raise
        return self._change_return

    def __enter__(self):
        self._orig = {"r": B.resolve_inspection_record, "c": B.change_status}
        B.resolve_inspection_record = self._resolve
        B.change_status = self._change
        return self

    def __exit__(self, *a):
        B.resolve_inspection_record = self._orig["r"]
        B.change_status = self._orig["c"]
        return False


def test_in_progress_rev0_appends_status_change():
    p = _Patch(resolve_seq=[_rec("IN_PROGRESS", 0)], change_return={"revision": 1})
    with p:
        out = B.complete_inspection_status(_SB(), "insp-1", actor_id="u-1", reason="SAFE_COMPLETE")
    assert out["status"] == "COMPLETED" and out["changed"] is True and out["noop"] is False
    assert len(p.change_calls) == 1
    c = p.change_calls[0]
    assert c["expected_revision"] == 0          # resolver revision 그대로
    assert c["to_status"] == "COMPLETED"
    assert c["actor_id"] == "u-1"
    assert c["reason"] == "SAFE_COMPLETE"
    assert isinstance(c["command_id"], str) and len(c["command_id"]) == 36  # server-generated uuid
    assert out["command_id"] == c["command_id"]


def test_already_completed_noop_zero_rpc():
    p = _Patch(resolve_seq=[_rec("COMPLETED", 3)])
    with p:
        out = B.complete_inspection_status(_SB(), "insp-1", actor_id="u-1", reason="SAFE_COMPLETE")
    assert out["changed"] is False and out["noop"] is True and out["status"] == "COMPLETED"
    assert len(p.change_calls) == 0             # command RPC 0
    assert out["revision"] == 3


def test_revision_conflict_reresolve_completed_success():
    # first resolve IN_PROGRESS rev0 -> change_status raises REVISION_CONFLICT
    # -> re-resolve -> COMPLETED -> success no-op
    p = _Patch(
        resolve_seq=[_rec("IN_PROGRESS", 0), _rec("COMPLETED", 1)],
        change_raise=InspectionRecordError("REVISION_CONFLICT", "stale"),
    )
    with p:
        out = B.complete_inspection_status(_SB(), "insp-1", actor_id="u-1", reason="SAFE_COMPLETE")
    assert out["changed"] is False and out["noop"] is True and out["status"] == "COMPLETED"
    assert len(p.change_calls) == 1             # 최초 1회만, retry loop 없음
    assert len(p.resolve_calls) == 2            # 최초 + re-resolve 1회


def test_revision_conflict_reresolve_still_in_progress_error():
    p = _Patch(
        resolve_seq=[_rec("IN_PROGRESS", 0), _rec("IN_PROGRESS", 0)],
        change_raise=InspectionRecordError("REVISION_CONFLICT", "stale"),
    )
    with p:
        try:
            B.complete_inspection_status(_SB(), "insp-1", actor_id="u-1", reason="SAFE_COMPLETE")
            raise AssertionError("expected REVISION_CONFLICT to propagate")
        except B.InspectionStatusWriteError as e:
            assert e.code == "REVISION_CONFLICT"
    assert len(p.change_calls) == 1             # single change attempt
    assert len(p.resolve_calls) == 2            # single re-resolve only


def test_inactive_rejected_zero_rpc():
    p = _Patch(resolve_seq=[_rec("IN_PROGRESS", 0, is_active=False)])
    with p:
        try:
            B.complete_inspection_status(_SB(), "insp-1", actor_id="u-1", reason="SAFE_COMPLETE")
            raise AssertionError("expected INSPECTION_INACTIVE")
        except B.InspectionStatusWriteError as e:
            assert e.code == "INSPECTION_INACTIVE"
    assert len(p.change_calls) == 0


def test_unknown_lifecycle_invalid_transition():
    p = _Patch(resolve_seq=[_rec("CANCELLED", 0)])
    with p:
        try:
            B.complete_inspection_status(_SB(), "insp-1", actor_id="u-1", reason="SAFE_COMPLETE")
            raise AssertionError("expected INVALID_STATUS_TRANSITION")
        except B.InspectionStatusWriteError as e:
            assert e.code == "INVALID_STATUS_TRANSITION"
    assert len(p.change_calls) == 0


def test_resolver_error_becomes_write_error():
    p = _Patch(resolve_seq=[InspectionRecordError("LEGACY_STATUS_UNRESOLVED", "x")])
    with p:
        try:
            B.complete_inspection_status(_SB(), "insp-1", actor_id="u-1", reason="SAFE_COMPLETE")
            raise AssertionError("expected LEGACY_STATUS_UNRESOLVED")
        except B.InspectionStatusWriteError as e:
            assert e.code == "LEGACY_STATUS_UNRESOLVED"
    assert len(p.change_calls) == 0


def test_supabase_passed_through():
    sb = _SB()
    p = _Patch(resolve_seq=[_rec("IN_PROGRESS", 0)])
    with p:
        B.complete_inspection_status(sb, "insp-1", actor_id="u-1", reason="SAFE_COMPLETE")
    assert p.resolve_calls[0][1] is sb           # resolver 에 동일 client
    assert p.change_calls[0]["supabase"] is sb   # command 에 동일 client


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
