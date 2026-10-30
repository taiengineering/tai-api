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
  CR-13  동일 GitHub identity + 다른 scenario_ids → 409 CRON_RUN_SCENARIO_DIVERGENCE
  CR-14  rollback 실패 → ERROR status 갱신 시도
  CR-15  skip_reason=BLOCKED_NO_QA_CREDENTIALS → ERROR run 생성, targets 없음, blocked=True
  CR-16  BLOCKED 동일 github identity 재호출 → idempotent=True, blocked=True
  CR-17  BLOCKED skip_reason + 비어있지 않은 scenario_ids → 422
  CR-18  라우터: blocked=True, idempotent=False 시 send_slack(QA_RUN_ERROR) 호출 확인 (Mock)
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


# ─────────────────────────────────────────────────────────────────────────────
# CR-15~18: BLOCKED_NO_QA_CREDENTIALS skip_reason
# ─────────────────────────────────────────────────────────────────────────────

def _call_blocked(sb, github_run_id=88888, github_run_attempt=1):
    return svc.register_cron_run(
        sb,
        github_run_id=github_run_id,
        github_run_attempt=github_run_attempt,
        scenario_ids=[],
        skip_reason="BLOCKED_NO_QA_CREDENTIALS",
    )


def test_CR15_blocked_creates_error_run_no_targets():
    """skip_reason=BLOCKED_NO_QA_CREDENTIALS → ERROR run 생성, targets 없음, blocked=True."""
    inserted_row: dict = {}

    class _BlockedQ(_Q):
        def eq(self, *a, **k): return _Q(rows=[])   # no existing run
        def insert(self, rows, **k):
            data = rows if isinstance(rows, dict) else (rows[0] if rows else {})
            inserted_row.update(data)
            return _Q(rows=[{"id": "blocked-run-1"}])
        def execute(self):
            return type("R", (), {"data": self._rows})()

    sb = _Supabase({"qa_runs": _BlockedQ(rows=[])})
    data = _call_blocked(sb)

    assert data["run_id"] == "blocked-run-1"
    assert data["idempotent"] is False
    assert data["blocked"] is True
    assert data["scenario_ids"] == []
    assert inserted_row["run_status"] == "ERROR"
    assert inserted_row["error_code"] == "BLOCKED_NO_QA_CREDENTIALS"
    assert inserted_row["trigger_type"] == "SCHEDULE"
    assert inserted_row["requested_by"] == "github-cron"
    assert "finished_at" in inserted_row, "ERROR run must have finished_at"


def test_CR16_blocked_idempotent_returns_existing():
    """동일 github identity로 재호출 시 기존 run_id 반환 (idempotent=True, blocked=True)."""
    sb = _Supabase({
        "qa_runs": _Q(rows=[{"id": "blocked-run-existing"}]),
    })
    data = _call_blocked(sb)
    assert data["run_id"] == "blocked-run-existing"
    assert data["idempotent"] is True
    assert data["blocked"] is True
    assert data["scenario_ids"] == []


def test_CR17_blocked_with_nonempty_scenario_ids_422():
    """BLOCKED_NO_QA_CREDENTIALS + 비어있지 않은 scenario_ids → 422."""
    sb = _Supabase({"qa_runs": _Q()})
    with pytest.raises(HTTPException) as exc:
        svc.register_cron_run(
            sb,
            github_run_id=88888,
            github_run_attempt=1,
            scenario_ids=["P0-SAAS-001"],
            skip_reason="BLOCKED_NO_QA_CREDENTIALS",
        )
    assert exc.value.status_code == 422


def test_CR18_router_sends_slack_for_blocked_not_idempotent():
    """라우터: blocked=True, idempotent=False → send_slack(QA_RUN_ERROR) 호출.
    idempotent=True 재호출에서는 발송하지 않음 (중복 알림 억제)."""
    import asyncio
    import os
    from unittest.mock import AsyncMock, patch, MagicMock

    os.environ.setdefault("INTERNAL_API_SECRET", "test-secret")

    blocked_data    = {"run_id": "blocked-run-slack", "scenario_ids": [], "idempotent": False, "blocked": True}
    idempotent_data = {"run_id": "blocked-run-slack", "scenario_ids": [], "idempotent": True,  "blocked": True}

    async def _test_new():
        import routers.internal_qa as router_mod
        from routers.internal_qa import RegisterCronRunRequest
        body = RegisterCronRunRequest(
            github_run_id=77777, github_run_attempt=1,
            scenario_ids=[], skip_reason="BLOCKED_NO_QA_CREDENTIALS",
        )
        mock_slack = AsyncMock()
        with patch.object(router_mod.svc, "register_cron_run", return_value=blocked_data), \
             patch.object(router_mod, "send_slack", mock_slack), \
             patch.object(router_mod, "get_supabase", return_value=MagicMock()):
            await router_mod.register_cron_run(body, x_internal_secret="test-secret")
        return mock_slack.call_count

    async def _test_idempotent():
        import routers.internal_qa as router_mod
        from routers.internal_qa import RegisterCronRunRequest
        body = RegisterCronRunRequest(
            github_run_id=77777, github_run_attempt=1,
            scenario_ids=[], skip_reason="BLOCKED_NO_QA_CREDENTIALS",
        )
        mock_slack = AsyncMock()
        with patch.object(router_mod.svc, "register_cron_run", return_value=idempotent_data), \
             patch.object(router_mod, "send_slack", mock_slack), \
             patch.object(router_mod, "get_supabase", return_value=MagicMock()):
            await router_mod.register_cron_run(body, x_internal_secret="test-secret")
        return mock_slack.call_count

    assert asyncio.run(_test_new()) == 1, "신규 BLOCKED run → send_slack 1회 호출"
    assert asyncio.run(_test_idempotent()) == 0, "idempotent BLOCKED run → send_slack 호출 없음"
