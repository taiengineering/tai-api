"""WO-QA-OPS-ADMIN-SLACK-001 WP-1R — register_cron_run 계약 테스트.

커버리지:
  CR-01  신규 SCHEDULE run 생성 + targets
  CR-02  동일 (github_run_id, github_run_attempt) → idempotent=True, 기존 run_id 반환
  CR-03  scenario_ids 빈 리스트 → 422
  CR-04  scenario_ids 101건 초과 → 422
  CR-05  scenario_ids 중복 → 422
  CR-06  존재하지 않는 scenario_id → 422
  CR-07  disabled scenario → 422
  CR-08  신규 run: trigger_type=SCHEDULE, requested_by=github-cron, run_status=RUNNING, started_at 설정 (R2)
  CR-09  idempotent 반환 시 기존 scenario_ids 복원
  CR-10  신규 run: RUNNING 상태로 생성 (R2: QUEUED→COMPLETED 불가, RUNNING→COMPLETED 허용)
  CR-11  target insert 실패 시 run 롤백 시도 (R5)
  CR-12  rollback 실패도 원래 예외로 re-raise (R5: 불완전 run 잔존 0 시도)
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

import services.qa_control_svc as svc


# ─────────────────────────────────────────────────────────────────────────────
# Mock helpers
# ─────────────────────────────────────────────────────────────────────────────

class _Q:
    def __init__(self, rows=None, count=None):
        self._rows = rows or []
        self._count = count if count is not None else len(self._rows)
        self.last_insert = None
        self.last_delete = None

    def select(self, *a, **k): return self
    def eq(self, *a, **k):     return self
    def in_(self, *a, **k):    return self
    def limit(self, *a, **k):  return self

    def insert(self, rows, **k):
        self.last_insert = rows
        return self

    def delete(self, **k):
        self.last_delete = True
        return self

    def execute(self):
        return type("R", (), {"data": self._rows, "count": self._count})()


class _Supabase:
    def __init__(self, table_map):
        self._map = table_map

    def table(self, name):
        return self._map.get(name, _Q())


def _items_q(scenario_ids=("P0-SAAS-001", "P0-WWW-003"), enabled=True):
    return _Q(rows=[
        {"id": f"item-{i}", "scenario_id": sid, "enabled": enabled}
        for i, sid in enumerate(scenario_ids)
    ])


def _call(sb, github_run_id=12345, github_run_attempt=1, scenario_ids=None):
    if scenario_ids is None:
        scenario_ids = ["P0-SAAS-001", "P0-WWW-003"]
    return svc.register_cron_run(
        sb,
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        scenario_ids=scenario_ids,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CR-01: 신규 SCHEDULE run 생성
# ─────────────────────────────────────────────────────────────────────────────

def test_CR01_new_run_created():
    class _InsertableQ(_Q):
        def eq(self, *a, **k): return _Q(rows=[])   # idempotency check: no existing run
        def insert(self, rows, **k):
            self.last_insert = rows
            return _Q(rows=[{"id": "new-run-1"}])
        def execute(self):
            return type("R", (), {"data": self._rows, "count": 0})()

    sb = _Supabase({
        "qa_runs":        _InsertableQ(rows=[]),
        "qa_items":       _items_q(),
        "qa_run_targets": _Q(),
    })
    data = _call(sb)
    assert data["run_id"] == "new-run-1"
    assert data["idempotent"] is False
    assert set(data["scenario_ids"]) == {"P0-SAAS-001", "P0-WWW-003"}


# ─────────────────────────────────────────────────────────────────────────────
# CR-08 + CR-10: trigger_type/requested_by 고정값 + RUNNING 상태 (R2)
# ─────────────────────────────────────────────────────────────────────────────

def test_CR08_CR10_run_row_fields():
    inserted_row = {}

    class _TrackQ(_Q):
        def eq(self, *a, **k): return _Q(rows=[])
        def insert(self, rows, **k):
            data = rows if isinstance(rows, dict) else (rows[0] if rows else {})
            inserted_row.update(data)
            return _Q(rows=[{"id": "run-track"}])
        def execute(self):
            return type("R", (), {"data": self._rows, "count": 0})()

    sb = _Supabase({
        "qa_runs":        _TrackQ(rows=[]),
        "qa_items":       _items_q(),
        "qa_run_targets": _Q(),
    })
    _call(sb)
    # R2: RUNNING at creation — QUEUED→COMPLETED is invalid (RUNNING→COMPLETED is valid)
    assert inserted_row.get("trigger_type") == "SCHEDULE"
    assert inserted_row.get("requested_by") == "github-cron"
    assert inserted_row.get("run_status") == "RUNNING"
    assert inserted_row.get("started_at") is not None
    assert inserted_row.get("github_run_id") == 12345
    assert inserted_row.get("github_run_attempt") == 1


# ─────────────────────────────────────────────────────────────────────────────
# CR-02: 동일 (github_run_id, github_run_attempt) → idempotent
# ─────────────────────────────────────────────────────────────────────────────

def test_CR02_idempotent_existing_run():
    sb = _Supabase({
        "qa_runs": _Q(rows=[{"id": "existing-run"}]),
        "qa_run_targets": _Q(rows=[{"qa_item_id": "item-0"}, {"qa_item_id": "item-1"}]),
        "qa_items": _Q(rows=[
            {"id": "item-0", "scenario_id": "P0-SAAS-001"},
            {"id": "item-1", "scenario_id": "P0-WWW-003"},
        ]),
    })
    data = _call(sb)
    assert data["run_id"] == "existing-run"
    assert data["idempotent"] is True
    assert set(data["scenario_ids"]) == {"P0-SAAS-001", "P0-WWW-003"}


# ─────────────────────────────────────────────────────────────────────────────
# CR-09: idempotent 경로에서 기존 targets → scenario_ids 복원
# ─────────────────────────────────────────────────────────────────────────────

def test_CR09_idempotent_scenario_ids_restored():
    """CR-09: idempotent 경로에서 DB에 저장된 scenario_ids를 반환한다.

    incoming과 stored가 동일한 집합이어야 통과 (R5 divergence check).
    stored → ["P0-MYP-001"], incoming → ["P0-MYP-001"] (identical set).
    """
    sb = _Supabase({
        "qa_runs": _Q(rows=[{"id": "run-dup"}]),
        "qa_run_targets": _Q(rows=[{"qa_item_id": "item-x"}]),
        "qa_items": _Q(rows=[{"id": "item-x", "scenario_id": "P0-MYP-001"}]),
    })
    data = _call(sb, scenario_ids=["P0-MYP-001"])  # identical to stored — no divergence
    assert data["idempotent"] is True
    assert data["scenario_ids"] == ["P0-MYP-001"]


# ─────────────────────────────────────────────────────────────────────────────
# CR-03: scenario_ids 빈 리스트 → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_CR03_empty_scenario_ids_422():
    with pytest.raises(HTTPException) as exc:
        _call(_Supabase({}), scenario_ids=[])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# CR-04: scenario_ids > 100 → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_CR04_too_many_scenario_ids_422():
    with pytest.raises(HTTPException) as exc:
        _call(_Supabase({}), scenario_ids=[f"P0-ID-{i:03d}" for i in range(101)])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# CR-05: scenario_ids 중복 → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_CR05_duplicate_scenario_ids_422():
    with pytest.raises(HTTPException) as exc:
        _call(_Supabase({}), scenario_ids=["P0-SAAS-001", "P0-SAAS-001"])
    assert exc.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# CR-06: 존재하지 않는 scenario_id → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_CR06_unknown_scenario_id_422():
    sb = _Supabase({
        "qa_runs":  _Q(rows=[]),   # no existing run
        "qa_items": _Q(rows=[]),   # empty — all missing
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, scenario_ids=["P0-SAAS-001"])
    assert exc.value.status_code == 422
    assert "P0-SAAS-001" in str(exc.value.detail)


# ─────────────────────────────────────────────────────────────────────────────
# CR-07: disabled scenario → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_CR07_disabled_scenario_422():
    sb = _Supabase({
        "qa_runs":  _Q(rows=[]),
        "qa_items": _items_q(scenario_ids=("P0-SAAS-001",), enabled=False),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, scenario_ids=["P0-SAAS-001"])
    assert exc.value.status_code == 422
    assert "disabled" in str(exc.value.detail).lower()


# ─────────────────────────────────────────────────────────────────────────────
# CR-11: target insert 실패 → run 롤백 시도 후 500 (R5)
# ─────────────────────────────────────────────────────────────────────────────

def test_CR11_target_insert_failure_triggers_rollback():
    deleted_run_ids = []

    class _RunQ(_Q):
        def eq(self, col, val):
            self._eq_val = val
            return self
        def insert(self, rows, **k):
            return _Q(rows=[{"id": "run-fail"}])
        def delete(self, **k):
            deleted_run_ids.append(getattr(self, "_eq_val", None))
            return self
        def execute(self):
            return type("R", (), {"data": self._rows, "count": 0})()

    class _FailTargetQ(_Q):
        def insert(self, rows, **k):
            raise RuntimeError("DB insert failed")

    sb = _Supabase({
        "qa_runs":        _RunQ(rows=[]),   # eq for idempotency → empty; insert → run-fail
        "qa_items":       _items_q(),
        "qa_run_targets": _FailTargetQ(),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb)
    assert exc.value.status_code == 500
    assert "롤백" in str(exc.value.detail)


# ─────────────────────────────────────────────────────────────────────────────
# CR-12: rollback 자체 실패해도 원래 HTTPException re-raise (R5)
# ─────────────────────────────────────────────────────────────────────────────

def test_CR12_rollback_failure_still_raises_500():
    class _RunQ(_Q):
        def eq(self, *a, **k): return self
        def insert(self, rows, **k):
            return _Q(rows=[{"id": "run-rbfail"}])
        def delete(self, **k):
            raise RuntimeError("delete also failed")
        def execute(self):
            return type("R", (), {"data": self._rows, "count": 0})()

    class _FailTargetQ(_Q):
        def insert(self, rows, **k):
            raise RuntimeError("DB insert failed")

    sb = _Supabase({
        "qa_runs":        _RunQ(rows=[]),
        "qa_items":       _items_q(),
        "qa_run_targets": _FailTargetQ(),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb)
    # Must still get 500, not the rollback RuntimeError
    assert exc.value.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# CR-13: 동일 GitHub identity + 다른 scenario_ids → 409 (R5 divergence)
# ─────────────────────────────────────────────────────────────────────────────

def test_CR13_diverging_scenario_ids_409():
    """동일 (github_run_id, github_run_attempt)로 다른 scenario 집합 재등록 → 409."""
    # Existing run registered with P0-MYP-001 only
    sb = _Supabase({
        "qa_runs":        _Q(rows=[{"id": "run-exist"}]),
        "qa_run_targets": _Q(rows=[{"qa_item_id": "item-x"}]),
        "qa_items":       _Q(rows=[{"id": "item-x", "scenario_id": "P0-MYP-001"}]),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb, scenario_ids=["P0-SAAS-001"])  # different from stored P0-MYP-001
    assert exc.value.status_code == 409
    assert "CRON_RUN_SCENARIO_DIVERGENCE" in str(exc.value.detail)


# ─────────────────────────────────────────────────────────────────────────────
# CR-14: rollback 실패 시 ERROR 상태 갱신 시도 (R5 orphan RUNNING 방지)
# ─────────────────────────────────────────────────────────────────────────────

def test_CR14_rollback_failure_attempts_error_status():
    """Target insert + rollback 모두 실패 → ERROR 상태 갱신 시도 후 500 re-raise."""
    error_updates = []

    class _RunQ(_Q):
        def eq(self, col, val):
            self._eq_col, self._eq_val = col, val
            return self

        def insert(self, rows, **k):
            return _Q(rows=[{"id": "run-orphan"}])

        def update(self, patch, **k):
            error_updates.append(patch)
            return self

        def delete(self, **k):
            raise RuntimeError("delete failed")

        def execute(self):
            return type("R", (), {"data": self._rows, "count": 0})()

    class _FailTargetQ(_Q):
        def insert(self, rows, **k):
            raise RuntimeError("DB insert failed")

    sb = _Supabase({
        "qa_runs":        _RunQ(rows=[]),
        "qa_items":       _items_q(),
        "qa_run_targets": _FailTargetQ(),
    })
    with pytest.raises(HTTPException) as exc:
        _call(sb)
    assert exc.value.status_code == 500
    # ERROR status update must have been attempted
    assert any(u.get("run_status") == "ERROR" for u in error_updates), (
        f"expected ERROR status update, got: {error_updates}"
    )
