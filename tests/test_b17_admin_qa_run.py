"""
B17-ADMIN-OPS-FNC-003: POST /admin/qa/runs — QA 수동 실행 dispatch API 경계 검증

검증 목표:
  T1: 토큰 없음 → 401 (get_current_user 미통과)
  T2: 비어드민 → 403 (실제 _require_admin; role_data_scope=COMPANY → 차단)
      svc.create_run 미호출 확인
  T3: 어드민 + 유효 항목 → 201; 실제 _require_admin(ALL) + 실제 svc.create_run(mock DB)
      dispatch OK → run_status=RUNNING, dispatch=OK
      qa_runs.insert trigger_type=MANUAL·requested_by 확인
  T4: 어드민 + dispatch 실패 → 201; dispatch=ERROR, run_status=ERROR 기록 확인

재사용 근거 (서비스 계층):
  AQ25: trigger_type=MANUAL, requested_by, ordinal 서버 고정 (svc.create_run 직접 검증 완료)
  AQ26~AQ29: 빈 ID, 초과, 중복, 비활성 항목 → 422 (svc 직접 검증 완료)
  AQ30: target 실패 보상 DELETE (svc 직접 검증 완료)
  → 본 파일은 AQ25~AQ30 미검증 API 경계에만 집중

프론트엔드 연결:
  tai-admin/vue3/src/pages/qa/useQaApi.ts 180행
  createRun(qaItemIds) → POST /admin/qa/runs { qa_item_ids }
  qa-console.spec.ts A05: fetchRuns /admin/qa/runs 소스 계약 보유

운영 안전:
  monkeypatch + FastAPI TestClient — 운영 DB/API/GitHub Actions 미접촉
  dispatch_qa_run 반드시 모의 처리 (실제 GitHub dispatch 차단)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.admin_qa as aq_mod
from routers.auth import get_current_user

_ITEM_ID  = "qa-item-b17-0000-0000-000000000001"
_RUN_ID   = "qa-run-b17-0000-0000-000000000001"
_SCEN_ID  = "scen-b17-0000-0000-000000000001"

_ADMIN_USER   = {"id": "admin-b17", "role_code": "000", "is_active": True}
_NONAMIN_USER = {"id": "user-b17",  "role_code": "099", "is_active": True}

_ENABLED_ITEM = {"id": _ITEM_ID, "enabled": True, "scenario_id": _SCEN_ID}
_RUN_ROW = {
    "id": _RUN_ID,
    "trigger_type": "MANUAL",
    "run_status": "QUEUED",
    "requested_by": "admin-b17",
    "requested_at": "2026-11-09T00:00:00+09:00",
    "started_at": None,
    "finished_at": None,
    "error_code": None,
    "error_summary": None,
    "created_at": "2026-11-09T00:00:00+09:00",
    "updated_at": "2026-11-09T00:00:00+09:00",
}


# ── Mock DB 헬퍼 ──────────────────────────────────────────────────────────────

def _rds_m(scope_type: str) -> MagicMock:
    """role_data_scope 테이블 — scope_type 반환."""
    m = MagicMock()
    m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"scope_type": scope_type}]
    )
    return m


def _make_sb_non_admin() -> MagicMock:
    """T2: role_data_scope=COMPANY — _require_admin 차단."""
    rds = _rds_m("COMPANY")
    sb = MagicMock()
    sb.table.side_effect = lambda name: rds if name == "role_data_scope" else MagicMock()
    return sb


def _make_sb_admin_run() -> tuple[MagicMock, MagicMock, MagicMock]:
    """T3·T4: role_data_scope=ALL + svc.create_run 경로 mock.
    Returns: (sb, qa_runs_mock, qa_run_targets_mock)
    """
    rds = _rds_m("ALL")

    # qa_items: svc.create_run → select("id, enabled").in_()
    #           router → select("id, scenario_id").in_()
    # 양쪽 모두 같은 mock 반환 — data에 enabled+scenario_id 포함
    qi_m = MagicMock()
    qi_m.select.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[_ENABLED_ITEM]
    )

    qruns_m = MagicMock()
    qruns_m.insert.return_value.execute.return_value = MagicMock(data=[dict(_RUN_ROW)])
    qruns_m.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    targets_m = MagicMock()
    targets_m.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "tgt-b17", "run_id": _RUN_ID, "qa_item_id": _ITEM_ID, "ordinal": 1}]
    )

    sb = MagicMock()

    def _dispatch(name: str):
        if name == "role_data_scope":   return rds
        if name == "qa_items":          return qi_m
        if name == "qa_runs":           return qruns_m
        if name == "qa_run_targets":    return targets_m
        return MagicMock()

    sb.table.side_effect = _dispatch
    return sb, qruns_m, targets_m


def _make_app(caller=None) -> FastAPI:
    app = FastAPI()
    app.include_router(aq_mod.router)
    if caller is not None:
        app.dependency_overrides[get_current_user] = lambda: caller
    return app


# ── T1: 토큰 없음 → 401 ──────────────────────────────────────────────────────

def test_T1_POST_no_token_401():
    """T1: Authorization 헤더 없음 → 401."""
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/admin/qa/runs", json={"qa_item_ids": [_ITEM_ID]})
    assert r.status_code == 401, f"예상 401, 실제 {r.status_code}: {r.text}"
    app.dependency_overrides.clear()


# ── T2: 비어드민 → 실제 _require_admin 차단 → 403 ────────────────────────────

def test_T2_POST_non_admin_403():
    """T2: role_data_scope=COMPANY → 실제 _require_admin 403 차단.
    svc.create_run 미호출 확인.
    """
    sb = _make_sb_non_admin()
    app = _make_app(caller=_NONAMIN_USER)

    with patch.object(aq_mod, "get_supabase", return_value=sb), \
         patch.object(aq_mod.svc, "create_run") as spy_create:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/admin/qa/runs",
            json={"qa_item_ids": [_ITEM_ID]},
            headers={"Authorization": "Bearer fake"},
        )

    assert r.status_code == 403, f"예상 403, 실제 {r.status_code}: {r.text}"
    spy_create.assert_not_called()
    app.dependency_overrides.clear()


# ── T3: 어드민 + dispatch OK → 201, run_status=RUNNING ───────────────────────

def test_T3_POST_admin_dispatch_ok_201():
    """T3: role_data_scope=ALL 실 _require_admin 통과.
    실제 svc.create_run(mock DB) → trigger_type=MANUAL, requested_by 확인.
    dispatch_qa_run 성공 → run_status=RUNNING, dispatch=OK.
    """
    sb, qruns_m, _ = _make_sb_admin_run()
    app = _make_app(caller=_ADMIN_USER)

    async def _ok_dispatch(run_id, scenario_ids, **kw):
        pass

    with patch.object(aq_mod, "get_supabase", return_value=sb), \
         patch("services.github_dispatch_svc.dispatch_qa_run", new=_ok_dispatch):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/admin/qa/runs",
            json={"qa_item_ids": [_ITEM_ID]},
            headers={"Authorization": "Bearer valid"},
        )

    assert r.status_code == 201, f"예상 201, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "success"
    assert body["dispatch"] == "OK"
    assert body["data"]["trigger_type"] == "MANUAL"
    assert body["data"]["run_status"] == "RUNNING"

    # qa_runs.insert에 trigger_type=MANUAL·requested_by=admin-b17 전달 확인
    insert_call = qruns_m.insert.call_args
    assert insert_call is not None, "qa_runs.insert 미호출"
    inserted = insert_call[0][0]
    assert inserted["trigger_type"] == "MANUAL", f"trigger_type 오류: {inserted}"
    assert inserted["requested_by"] == "admin-b17", f"requested_by 오류: {inserted}"

    app.dependency_overrides.clear()


# ── T4: dispatch 실패 → 201, run_status=ERROR, dispatch=ERROR ────────────────

def test_T4_POST_dispatch_fail_error_state():
    """T4: dispatch_qa_run 예외 발생 → 201 반환, dispatch=ERROR, run_status=ERROR.
    qa_runs.update에 run_status=ERROR 전달 확인.
    """
    sb, qruns_m, _ = _make_sb_admin_run()
    app = _make_app(caller=_ADMIN_USER)

    async def _fail_dispatch(run_id, scenario_ids, **kw):
        raise RuntimeError("GitHub API 접근 불가")

    with patch.object(aq_mod, "get_supabase", return_value=sb), \
         patch("services.github_dispatch_svc.dispatch_qa_run", new=_fail_dispatch):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/admin/qa/runs",
            json={"qa_item_ids": [_ITEM_ID]},
            headers={"Authorization": "Bearer valid"},
        )

    assert r.status_code == 201, f"예상 201, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["dispatch"] == "ERROR"
    assert body["data"]["run_status"] == "ERROR"
    assert body["data"].get("error_summary") is not None

    # qa_runs.update에 run_status=ERROR 전달 확인
    update_calls = qruns_m.update.call_args_list
    assert update_calls, "qa_runs.update 미호출"
    error_update_data = update_calls[0][0][0]
    assert error_update_data.get("run_status") == "ERROR", (
        f"ERROR 상태 미전달: {error_update_data}"
    )

    app.dependency_overrides.clear()
