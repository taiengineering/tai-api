"""
B16-ADMIN-OPS-FNC-002: PATCH /admin/qa/items/{qa_item_id} — QA 항목 enabled 토글 API 경계 검증

검증 목표:
  T1: 토큰 없음 → 401 (get_current_user 미통과)
  T2: 비어드민 토큰 → 403 (실제 _require_admin 실행; role_data_scope=COMPANY → 차단)
      svc.update_item 미호출 확인
  T3: 어드민 토큰 + enabled=False → 200, data.enabled=False
      실제 _require_admin(role_data_scope=ALL) + 실제 svc.update_item(mock qa_items) 실행
      DB에 enabled=False 전달 확인
  T4: enabled=None → 422 (사전: AQ09가 svc 내 실제 로직 검증 완료;
                           본 테스트는 HTTP 경계에서 예외 전달만 확인)
  T5: item 미존재 → 404 (사전: AQ10이 svc 내 실제 로직 검증 완료;
                          본 테스트는 HTTP 경계에서 예외 전달만 확인)

배경:
  AQ08~AQ10: svc.update_item() 직접 호출 (서비스 계층 — API 경계 미검증)
  AQ31~AQ34: GET /admin/qa/summary 대상 (PATCH /items/{id} 미검증)
  → T1~T5로 PATCH /admin/qa/items/{id} API 경계 최초 보완 검증

프론트엔드 연결:
  tai-admin/vue3/src/pages/qa/items/index.vue → useQaApi().updateItemEnabled()
  → PATCH /admin/qa/items/${id}  (useQaApi.ts 155행)
  qa-console.spec.ts A03: updateItemEnabled 소스 계약 기존 검증

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

from fastapi import FastAPI, HTTPException as FHTTPEx
from fastapi.testclient import TestClient

import routers.admin_qa as aq_mod
from routers.auth import get_current_user

_ITEM_ID = "qa-item-b16-0000-0000-000000000001"

_ADMIN_USER   = {"id": "admin-b16", "role_code": "000", "is_active": True}
_NONAMIN_USER = {"id": "user-b16",  "role_code": "099", "is_active": True}

_UPDATED_ITEM = {
    "id": _ITEM_ID,
    "enabled": False,
    "name": "테스트 항목",
}


# ── Mock DB 헬퍼 ──────────────────────────────────────────────────────────────

def _rds_m(scope_type: str) -> MagicMock:
    """role_data_scope 테이블 mock — scope_type 반환."""
    m = MagicMock()
    m.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"scope_type": scope_type}]
    )
    return m


def _qa_items_m_success() -> MagicMock:
    """qa_items 테이블 mock — update 성공, _UPDATED_ITEM 반환."""
    m = MagicMock()
    m.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[_UPDATED_ITEM]
    )
    return m


def _make_sb(scope_type: str, qa_m: MagicMock | None = None) -> MagicMock:
    """실제 _require_admin 경로에 필요한 role_data_scope + (선택) qa_items mock."""
    rds = _rds_m(scope_type)
    sb = MagicMock()

    def _dispatch(name: str):
        if name == "role_data_scope":
            return rds
        if name == "qa_items" and qa_m is not None:
            return qa_m
        return MagicMock()

    sb.table.side_effect = _dispatch
    return sb


# ── T1: 토큰 없음 → 401 ──────────────────────────────────────────────────────

def test_T1_no_token_401():
    """T1: Authorization 헤더 없음 → get_current_user 미통과 → 401."""
    app = FastAPI()
    app.include_router(aq_mod.router)
    client = TestClient(app, raise_server_exceptions=False)

    r = client.patch(f"/admin/qa/items/{_ITEM_ID}", json={"enabled": False})
    assert r.status_code == 401, f"예상 401, 실제 {r.status_code}: {r.text}"


# ── T2: 비어드민 → 실제 _require_admin 차단 → 403 ────────────────────────────

def test_T2_non_admin_403():
    """T2: role_data_scope=COMPANY → 실제 _require_admin 403 차단.
    svc.update_item 미호출 확인.
    """
    sb = _make_sb(scope_type="COMPANY")
    app = FastAPI()
    app.include_router(aq_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _NONAMIN_USER

    with patch.object(aq_mod, "get_supabase", return_value=sb), \
         patch.object(aq_mod.svc, "update_item") as spy_update:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(
            f"/admin/qa/items/{_ITEM_ID}",
            json={"enabled": False},
            headers={"Authorization": "Bearer fake"},
        )

    assert r.status_code == 403, f"예상 403, 실제 {r.status_code}: {r.text}"
    spy_update.assert_not_called()
    app.dependency_overrides.clear()


# ── T3: 어드민 + 실제 _require_admin 통과 + 실제 svc.update_item → 200 ───────

def test_T3_admin_enabled_false_200():
    """T3: role_data_scope=ALL → 실제 _require_admin 통과.
    실제 svc.update_item(mock qa_items) → 200, data.enabled=False.
    qa_items.update 에 enabled=False 전달 확인.
    """
    qa_m = _qa_items_m_success()
    sb = _make_sb(scope_type="ALL", qa_m=qa_m)

    app = FastAPI()
    app.include_router(aq_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER

    with patch.object(aq_mod, "get_supabase", return_value=sb):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(
            f"/admin/qa/items/{_ITEM_ID}",
            json={"enabled": False},
            headers={"Authorization": "Bearer valid"},
        )

    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["enabled"] is False

    # qa_items.update 호출 확인 — enabled=False 전달
    call_args = qa_m.update.call_args
    assert call_args is not None, "qa_items.update 미호출"
    update_data = call_args[0][0]
    assert update_data.get("enabled") is False, f"enabled=False 전달 안됨: {update_data}"

    app.dependency_overrides.clear()


# ── T4: enabled=None → 422 ───────────────────────────────────────────────────

def test_T4_enabled_none_422():
    """T4: HTTP 경계에서 422 예외 전달 확인.
    실제 서비스 로직(enabled=None → HTTPException(422))은 AQ09 에서 검증 완료.
    본 테스트는 router 경유 시 422가 클라이언트에 전달되는지만 확인.
    """
    app = FastAPI()
    app.include_router(aq_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER

    def _svc_422(*a, **k):
        raise FHTTPEx(status_code=422, detail="enabled 값이 필요합니다")

    with patch.object(aq_mod, "_require_admin", lambda *a, **k: None), \
         patch.object(aq_mod, "get_supabase", return_value=MagicMock()), \
         patch.object(aq_mod.svc, "update_item", _svc_422):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(
            f"/admin/qa/items/{_ITEM_ID}",
            json={},
            headers={"Authorization": "Bearer valid"},
        )

    assert r.status_code == 422, f"예상 422, 실제 {r.status_code}: {r.text}"
    app.dependency_overrides.clear()


# ── T5: 존재하지 않는 item → 404 ─────────────────────────────────────────────

def test_T5_item_not_found_404():
    """T5: HTTP 경계에서 404 예외 전달 확인.
    실제 서비스 로직(update 결과 없음 → HTTPException(404))은 AQ10 에서 검증 완료.
    본 테스트는 router 경유 시 404가 클라이언트에 전달되는지만 확인.
    """
    app = FastAPI()
    app.include_router(aq_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER

    def _svc_404(*a, **k):
        raise FHTTPEx(status_code=404, detail="QA 항목을 찾을 수 없습니다")

    with patch.object(aq_mod, "_require_admin", lambda *a, **k: None), \
         patch.object(aq_mod, "get_supabase", return_value=MagicMock()), \
         patch.object(aq_mod.svc, "update_item", _svc_404):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(
            "/admin/qa/items/nonexistent-id",
            json={"enabled": True},
            headers={"Authorization": "Bearer valid"},
        )

    assert r.status_code == 404, f"예상 404, 실제 {r.status_code}: {r.text}"
    app.dependency_overrides.clear()
