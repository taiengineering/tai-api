"""
B10-WF-001: worker_registry PATCH/DELETE cross-tenant isolation verification

검증 목표:
  1. worker_registry PATCH/DELETE 엔드포인트에 per-route 인증 미선언 확인
  2. permission_guard 미들웨어 없이 타사 작업자 수정 성공 여부 확인
  3. permission_guard ADVISORY 모드 동작 — fail-open (통과) 여부 확인
  4. ENFORCE 모드에서도 company_id 소유권 검증이 없어 타사 수정 허용 여부 확인

판정:
  CT-01 ~ CT-04 모두 통과 → CROSS_TENANT_MUTATION_CONFIRMED_IN_ISOLATION
  보상 제어 확인 시 → COMPENSATING_CONTROL_VERIFIED

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
"""

from __future__ import annotations

import os
import inspect
import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

import routers.worker_registry as wr


# ── 모의 작업자 데이터 ────────────────────────────────────────────────────────

_WORKER_B_ID   = "wkr-b-0001-0000-0000-000000000001"
_COMPANY_A_ID  = "co-aaaa-0000-0000-0000-000000000001"
_COMPANY_B_ID  = "co-bbbb-0000-0000-0000-000000000002"

# Company B 소속 작업자 (수정 대상)
_WORKER_B_ROW = {
    "id":         _WORKER_B_ID,
    "name":       "홍길동",
    "phone":      "01011112222",
    "factory_id": "fac-b-0001",
    "company_id": _COMPANY_B_ID,
    "is_active":  True,
    "status_code": "ACTIVE",
}

_WORKER_B_UPDATED = {**_WORKER_B_ROW, "memo": "수정됨"}
_WORKER_B_DEACTIVATED = {**_WORKER_B_ROW, "is_active": False, "status_code": "INACTIVE"}


def _make_sb_find(worker_row: dict):
    """작업자 조회 성공 → 수정 성공을 반환하는 mock supabase."""
    sb = MagicMock()
    # select: worker exists
    sel = MagicMock()
    sel.execute.return_value = MagicMock(data=[{"id": worker_row["id"]}])
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value = sel
    # update: returns updated row
    upd = MagicMock()
    upd.execute.return_value = MagicMock(data=[worker_row])
    sb.table.return_value.update.return_value.eq.return_value = upd
    return sb


def _make_app_no_guard() -> TestClient:
    """permission_guard 없이 worker_registry 라우터만 탑재한 격리 앱."""
    app = FastAPI()
    app.include_router(wr.router)
    return TestClient(app, raise_server_exceptions=False)


# ── CT-01: per-route 인증 미선언 소스 확인 ──────────────────────────────────

def test_CT01_patch_has_no_depends_get_current_user():
    """CT-01: update_worker 함수 시그니처에 Depends(get_current_user) 미선언."""
    src = inspect.getsource(wr.update_worker)
    assert "get_current_user" not in src, (
        "update_worker에 get_current_user Depends가 존재합니다 "
        "— per-route 인증이 추가됐을 수 있음. B10-WF-001 재검토 필요."
    )


def test_CT01b_delete_has_no_depends_get_current_user():
    """CT-01b: delete_worker 함수 시그니처에 Depends(get_current_user) 미선언."""
    src = inspect.getsource(wr.delete_worker)
    assert "get_current_user" not in src, (
        "delete_worker에 get_current_user Depends가 존재합니다 "
        "— per-route 인증이 추가됐을 수 있음. B10-WF-001 재검토 필요."
    )


# ── CT-02: 인증 없이 타사 작업자 수정 성공 확인 ──────────────────────────────

def test_CT02_unauthenticated_patch_succeeds_cross_tenant():
    """CT-02: 인증 헤더 없이 Company B 작업자 수정 → 200 성공.

    worker_registry는 Depends(get_current_user) 미선언이므로
    permission_guard 없는 격리 환경에서 인증 없이도 수정 가능.
    """
    client = _make_app_no_guard()
    with patch.object(wr, "get_supabase", return_value=_make_sb_find(_WORKER_B_UPDATED)):
        resp = client.patch(
            f"/worker-registry/{_WORKER_B_ID}",
            json={"memo": "수정됨"},
            # Authorization 헤더 없음 — 타사 사용자 시뮬레이션
        )
    assert resp.status_code == 200, (
        f"예상: 200 (회사 격리 없음). 실제: {resp.status_code}. "
        "보상 제어가 추가됐다면 COMPENSATING_CONTROL_VERIFIED로 재분류."
    )
    assert resp.json()["status"] == "success"


def test_CT02b_unauthenticated_delete_succeeds_cross_tenant():
    """CT-02b: 인증 헤더 없이 Company B 작업자 비활성화 → 200 성공."""
    client = _make_app_no_guard()
    with patch.object(wr, "get_supabase", return_value=_make_sb_find(_WORKER_B_DEACTIVATED)):
        resp = client.delete(
            f"/worker-registry/{_WORKER_B_ID}",
            # Authorization 헤더 없음
        )
    assert resp.status_code == 200, (
        f"예상: 200 (회사 격리 없음). 실제: {resp.status_code}."
    )
    assert resp.json()["status"] == "success"


# ── CT-03: 엔드포인트 내 company_id 소유권 검증 미존재 확인 ──────────────────

def test_CT03_patch_no_company_id_check_in_source():
    """CT-03: update_worker 소스에 company_id 소유권 검증 없음."""
    src = inspect.getsource(wr.update_worker)
    # 소유권 검증 함수 미존재
    assert "_assert_worker_company" not in src
    assert "_ensure_worker_own" not in src
    # caller의 company_id와 target의 company_id를 비교하는 로직 없음
    # (factory lookup은 POST/bulk-import 전용)
    assert 'current_user.get("company_id")' not in src


def test_CT03b_delete_no_company_id_check_in_source():
    """CT-03b: delete_worker 소스에 company_id 소유권 검증 없음."""
    src = inspect.getsource(wr.delete_worker)
    assert "_assert_worker_company" not in src
    assert "_ensure_worker_own" not in src
    assert 'current_user.get("company_id")' not in src


# ── CT-04: permission_guard ADVISORY 모드 — fail-open 동작 확인 ──────────────

def test_CT04_permission_guard_default_is_advisory():
    """CT-04: permission_guard 기본 모드 = ADVISORY (fail-open).

    PERMISSION_GUARD_MODE 환경변수 미설정 시 ADVISORY — 로그만 기록, 차단 없음.
    """
    from services import permission_guard as pg
    # 현재 테스트 환경의 모드 확인
    # 운영에서 PERMISSION_GUARD_MODE=ENFORCE로 설정 가능하나, 기본값 = ADVISORY
    guard_src = inspect.getsource(pg)
    assert '_MODE = os.getenv("PERMISSION_GUARD_MODE", "ADVISORY")' in guard_src or \
           "ADVISORY" in guard_src, \
        "permission_guard ADVISORY 기본값 확인 불가 — 소스 변경 여부 확인 필요."

    # _deny 함수: advisory=True → returns None (통과)
    deny_src = inspect.getsource(pg._deny)
    assert "return None" in deny_src, \
        "_deny advisory 분기에서 None 반환(통과) 패턴 없음 — 소스 변경됐을 수 있음."


def test_CT04b_permission_guard_advisory_passthrough_on_no_auth():
    """CT-04b: ADVISORY 모드에서 미인증 요청도 _deny가 None 반환 → 통과.

    _is_advisory('auth', resource)가 True이면 _deny는 None을 반환한다.
    즉, Authorization 헤더 없는 요청도 ADVISORY 모드에서는 통과한다.
    """
    from services.permission_guard import _deny, _is_advisory
    # ADVISORY 모드에서 auth 타입 거부는 None 반환 (fail-open)
    with patch.dict(os.environ, {"PERMISSION_GUARD_MODE": "ADVISORY"}):
        import importlib
        import services.permission_guard as pg_mod
        importlib.reload(pg_mod)
        result = pg_mod._deny(True, 401, "토큰이 없습니다.", "PATCH /worker-registry/x")
        assert result is None, \
            "ADVISORY 모드 _deny가 None을 반환하지 않음 — fail-open 패턴 변경됨."
