"""OBJ-01 KNOT-3B COMMIT C — worker_check /submit one-shot cutover tests.

submit_check 이 직접 base/results INSERT 대신 원자적 생성 서비스
(submit_worker_inspection)를 1회 호출하고, 응답은 legacy shape(status alias)로
보존됨을 검증한다. get_supabase 는 직접 테이블 INSERT 를 트랩하는 FakeSupabase 로,
submit_worker_inspection 은 호출 인자를 포착하는 스텁으로 monkeypatch 한다.

read 경로(/recent · /history)는 KNOT-2 그대로여야 한다.
"""
from __future__ import annotations

import pytest

from fastapi import HTTPException

from routers import worker_check as wc
from routers.worker_check import CheckItem, CheckSubmitBody
from services.worker_inspection_submission import WorkerSubmissionError


class _Q:
    def __init__(self, tbl, store, forbidden):
        self.tbl = tbl
        self.store = store
        self.forbidden = forbidden
        self._f = {}

    def select(self, *a, **k):
        return self

    def eq(self, k, v):
        self._f[k] = v
        return self

    def limit(self, n):
        return self

    def insert(self, payload):
        # 직접 base/results INSERT 는 금지 — 발생하면 기록해 테스트에서 실패시킨다.
        self.forbidden.append((self.tbl, payload))
        return self

    def execute(self):
        class R:
            pass
        r = R()
        key = self._f.get("phone") or self._f.get("id")
        r.data = self.store.get(self.tbl, {}).get(key, self.store.get(self.tbl, {}).get("*", []))
        return r


class FakeSupabase:
    def __init__(self, store, forbidden):
        self.store = store
        self.forbidden = forbidden

    def table(self, name):
        return _Q(name, self.store, self.forbidden)


def _store():
    return {
        "users": {"01012345678": [{"id": "INSP-1", "name": "홍길동"}]},
        "work_schedules": {"SCH-1": [{"id": "SCH-1", "factory_id": "FCT-1"}]},
    }


def _snap(overall, iid="INS-9", replayed=False):
    return {
        "data": {
            "inspection_id": iid, "revision": 0, "inspection_status": "COMPLETED",
            "overall_result": overall, "normal_count": 1, "abnormal_count": 0,
            "hold_count": 0, "total_count": 1, "issue_items": [], "inspector_id": "INSP-1",
        },
        "replayed": replayed,
    }


@pytest.fixture
def wired(monkeypatch):
    """get_supabase / submit_worker_inspection / _iss 를 스텁으로 교체하고 포착 상태를 돌려준다."""
    state = {"forbidden": [], "calls": [], "next": _snap("NORMAL"), "raise": None, "store": None}

    def fake_get_supabase():
        return FakeSupabase(state["store"] or _store(), state["forbidden"])

    def fake_submit(sb, **kw):
        state["calls"].append(kw)
        if state["raise"] is not None:
            raise state["raise"]
        return state["next"]

    monkeypatch.setattr(wc, "get_supabase", fake_get_supabase)
    monkeypatch.setattr(wc, "submit_worker_inspection", fake_submit)
    monkeypatch.setattr(wc._iss, "resolve_set_id_for_assignment", lambda a: None)
    return state


def _body(items, **kw):
    base = dict(phone="010-1234-5678", schedule_id="SCH-1",
                inspection_type="ROUTINE", submitted_at="2026-08-27T09:00:00Z")
    base.update(kw)
    return CheckSubmitBody(items=[CheckItem(**it) for it in items], **base)


def test_normal_maps_to_legacy_completed_no_direct_insert(wired):
    wired["next"] = _snap("NORMAL")
    r = wc.submit_check(_body([{"name": "소화기", "result": "ok"}]), current_user=None)
    assert r["data"]["status"] == "COMPLETED"
    assert r["data"]["has_issue"] is False
    assert r["data"]["inspection_id"] == "INS-9"
    assert wired["forbidden"] == []          # 직접 base/results INSERT 0
    assert len(wired["calls"]) == 1          # 서비스 정확히 1회


def test_service_receives_parent_factory_and_canonical_items(wired):
    wc.submit_check(_body([{"name": "소화기", "result": "ok"}]), current_user=None)
    c = wired["calls"][0]
    assert c["schedule_id"] == "SCH-1"
    assert c["factory_id"] == "FCT-1"        # parent work_schedules companion (body.factory_id 미신뢰)
    assert c["inspector_id"] == "INSP-1"
    assert c["submitted_at"] == "2026-08-27T09:00:00Z"
    assert c["items"][0]["result_code"] == "NORMAL"   # canonical passthrough


def test_abnormal_maps_to_legacy_issue(wired):
    wired["next"] = _snap("ABNORMAL")
    r = wc.submit_check(_body([{"name": "비상구", "result": "bad"}]), current_user=None)
    assert r["data"]["status"] == "ISSUE"
    assert r["data"]["has_issue"] is True
    assert r["data"]["issue_items"] == ["비상구"]
    assert wired["forbidden"] == []


def test_hold_maps_to_legacy_hold(wired):
    wired["next"] = _snap("HOLD")
    r = wc.submit_check(_body([{"name": "밸브", "result": "hold"}]), current_user=None)
    assert r["data"]["status"] == "HOLD"
    assert r["data"]["has_issue"] is False


def test_retry_same_body_same_inspection_id_no_direct_insert(wired):
    wired["next"] = _snap("NORMAL", iid="INS-SAME")
    r1 = wc.submit_check(_body([{"name": "소화기", "result": "ok"}]), current_user=None)
    wired["next"] = _snap("NORMAL", iid="INS-SAME", replayed=True)
    r2 = wc.submit_check(_body([{"name": "소화기", "result": "ok"}]), current_user=None)
    assert r1["data"]["inspection_id"] == r2["data"]["inspection_id"] == "INS-SAME"
    assert wired["forbidden"] == []


def test_conflict_code_becomes_409(wired):
    wired["raise"] = WorkerSubmissionError("INSPECTION_ALREADY_EXISTS_FOR_SCHEDULE")
    with pytest.raises(HTTPException) as ei:
        wc.submit_check(_body([{"name": "소화기", "result": "ok"}]), current_user=None)
    assert ei.value.status_code == 409
    assert ei.value.detail == {"error": "INSPECTION_ALREADY_EXISTS_FOR_SCHEDULE"}


def test_non_conflict_error_becomes_500(wired):
    wired["raise"] = WorkerSubmissionError("WORK_SCHEDULE_NOT_FOUND")
    with pytest.raises(HTTPException) as ei:
        wc.submit_check(_body([{"name": "소화기", "result": "ok"}]), current_user=None)
    assert ei.value.status_code == 500
    assert ei.value.detail == {"error": "WORK_SCHEDULE_NOT_FOUND"}


def test_missing_schedule_ref_fail_closed_409(wired):
    with pytest.raises(HTTPException) as ei:
        wc.submit_check(_body([{"name": "소화기", "result": "ok"}], schedule_id=None, assignment_id=None),
                        current_user=None)
    assert ei.value.status_code == 409
    assert wired["calls"] == []              # 서비스 호출 자체가 없어야 함


def test_missing_submitted_at_returns_422_no_service_call(wired):
    # BLOCKER A: 누락 submitted_at 은 서버 시각으로 대체하지 않고 fail-closed 422.
    with pytest.raises(HTTPException) as ei:
        wc.submit_check(_body([{"name": "소화기", "result": "ok"}], submitted_at=None), current_user=None)
    assert ei.value.status_code == 422
    assert ei.value.detail == {"error": "WORKER_SUBMISSION_TIMESTAMP_INVALID"}
    assert wired["calls"] == []              # 서비스 호출 0


def test_empty_submitted_at_returns_422_no_service_call(wired):
    with pytest.raises(HTTPException) as ei:
        wc.submit_check(_body([{"name": "소화기", "result": "ok"}], submitted_at=""), current_user=None)
    assert ei.value.status_code == 422
    assert wired["calls"] == []


def test_invalid_submitted_at_maps_to_422(wired):
    # invalid ISO 는 service 가 typed 에러로 올리고 router 는 422 로 매핑(500 아님).
    wired["raise"] = WorkerSubmissionError("WORKER_SUBMISSION_TIMESTAMP_INVALID")
    with pytest.raises(HTTPException) as ei:
        wc.submit_check(_body([{"name": "소화기", "result": "ok"}], submitted_at="not-a-date"), current_user=None)
    assert ei.value.status_code == 422
    assert ei.value.detail == {"error": "WORKER_SUBMISSION_TIMESTAMP_INVALID"}


def test_submitted_at_not_defaulted_to_server_now_static():
    import inspect as _inspect
    src = _inspect.getsource(wc.submit_check)
    assert "body.submitted_at or now" not in src
    assert "submitted_at=body.submitted_at," in src


def test_recent_and_history_alias_unchanged(wired, monkeypatch):
    recs = [{"inspection_id": "R1", "inspection_date": "2026-08-27",
             "inspection_status": "COMPLETED", "overall_result": "ABNORMAL"}]
    monkeypatch.setattr(wc, "list_effective_inspection_records_by_inspector", lambda iid, lim, sb: recs)
    rec = wc.get_recent_checks(phone="010-1234-5678", limit=5)
    it = rec["data"]["items"][0]
    assert it["id"] == "R1" and it["status_code"] == "ISSUE"   # ABNORMAL→ISSUE alias
    hist = wc.get_check_history(phone="010-1234-5678", limit=50)
    assert hist["data"]["items"][0]["status_code"] == "ISSUE"


# ── REV-2: Worker ingress pair-identity fail-closed (W-A..W-D) ──
def _store_ws(rows):
    return {
        "users": {"01012345678": [{"id": "INSP-1", "name": "홍길동"}]},
        "work_schedules": {"SCH-1": rows},
    }


def test_ambiguous_schedule_id_rows2_returns_409_no_service(wired):
    # W-A: 동일 id 가 두 factory 에 → 409 AMBIGUOUS, 서비스 호출 0
    wired["store"] = _store_ws([{"id": "SCH-1", "factory_id": "FCT-1"},
                                {"id": "SCH-1", "factory_id": "FCT-2"}])
    with pytest.raises(HTTPException) as ei:
        wc.submit_check(_body([{"name": "소화기", "result": "ok"}]), current_user=None)
    assert ei.value.status_code == 409
    assert ei.value.detail == {"error": "WORK_SCHEDULE_ID_AMBIGUOUS"}
    assert wired["calls"] == []


def test_single_row_passes_that_rows_factory(wired):
    # W-B: rows=1 → 그 row 의 factory_id 를 service 로 전달(임의/기본값 아님)
    wired["store"] = _store_ws([{"id": "SCH-1", "factory_id": "FCT-ONLY"}])
    wc.submit_check(_body([{"name": "소화기", "result": "ok"}]), current_user=None)
    assert wired["calls"][0]["factory_id"] == "FCT-ONLY"


def test_zero_rows_not_found_409_no_service(wired):
    # W-C: rows=0 → 기존 not-found 409, 서비스 호출 0
    wired["store"] = {"users": {"01012345678": [{"id": "INSP-1", "name": "홍길동"}]},
                      "work_schedules": {}}
    with pytest.raises(HTTPException) as ei:
        wc.submit_check(_body([{"name": "소화기", "result": "ok"}]), current_user=None)
    assert ei.value.status_code == 409
    assert wired["calls"] == []


def test_parent_lookup_no_limit1_static():
    # W-D: worker start path 의 work_schedules parent 조회에 limit(1) 없음
    import inspect as _inspect
    src = _inspect.getsource(wc.submit_check)
    assert '.select("id, factory_id").eq("id", schedule_ref).limit(1)' not in src
    assert '.select("id, factory_id").eq("id", schedule_ref).execute()' in src
