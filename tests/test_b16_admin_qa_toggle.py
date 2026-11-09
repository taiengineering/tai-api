"""
B16-ADMIN-OPS-FNC-002: PATCH /admin/qa/items/{qa_item_id} — QA 항목 enabled 토글 API 경계 검증

검증 목표:
  T1: 토큰 없음 → 401 (get_current_user 미통과)
  T2: 비어드민 토큰 → 403 (_require_admin 차단)
  T3: 어드민 토큰 + enabled=False → 200, data.enabled=False
  T4: enabled=None (ItemPatch default) → 422 (svc 내 ValidationError)
  T5: 존재하지 않는 qa_item_id → 404

배경:
  AQ08~AQ10: svc.update_item() 직접 호출 (서비스 계층)
  AQ31~AQ34: GET /admin/qa/summary 대상 (PATCH 엔드포인트 미검증)
  → PATCH /admin/qa/items/{id} API 경계 완전 미검증 → 본 파일로 보완

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

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


def _make_app(caller=None, require_admin_fn=None, svc_update_fn=None) -> TestClient:
    app = FastAPI()
    app.include_router(aq_mod.router)

    if caller is not None:
        app.dependency_overrides[get_current_user] = lambda: caller

    client_kwargs: dict = {}

    patches = []
    if require_admin_fn is not None:
        patches.append(patch.object(aq_mod, "_require_admin", require_admin_fn))
    if svc_update_fn is not None:
        patches.append(patch.object(aq_mod.svc, "update_item", svc_update_fn))
    patches.append(patch.object(aq_mod, "get_supabase", return_value=MagicMock()))

    for p in patches:
        p.start()

    tc = TestClient(app, raise_server_exceptions=False)
    tc._b16_patches = patches
    return tc


def _stop(client: TestClient):
    for p in getattr(client, "_b16_patches", []):
        try:
            p.stop()
        except RuntimeError:
            pass


# ── T1: 토큰 없음 → 401 ──────────────────────────────────────────────────────

def test_T1_no_token_401():
    """T1: Authorization 헤더 없음 → get_current_user 미통과 → 401."""
    app = FastAPI()
    app.include_router(aq_mod.router)
    client = TestClient(app, raise_server_exceptions=False)

    r = client.patch(f"/admin/qa/items/{_ITEM_ID}", json={"enabled": False})
    assert r.status_code == 401, f"예상 401, 실제 {r.status_code}: {r.text}"


# ── T2: 비어드민 → 403 ───────────────────────────────────────────────────────

def test_T2_non_admin_403():
    """T2: 유효 토큰이지만 _require_admin 차단 → 403."""
    app = FastAPI()
    app.include_router(aq_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _NONAMIN_USER

    def _deny(*a, **k):
        raise FHTTPEx(status_code=403, detail="권한이 없습니다")

    with patch.object(aq_mod, "_require_admin", _deny), \
         patch.object(aq_mod, "get_supabase", return_value=MagicMock()):
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(
            f"/admin/qa/items/{_ITEM_ID}",
            json={"enabled": False},
            headers={"Authorization": "Bearer fake"},
        )

    assert r.status_code == 403, f"예상 403, 실제 {r.status_code}: {r.text}"
    app.dependency_overrides.clear()


# ── T3: 어드민 + enabled=False → 200 ─────────────────────────────────────────

def test_T3_admin_enabled_false_200():
    """T3: 어드민 토큰 + enabled=False → 200, data.enabled=False."""
    app = FastAPI()
    app.include_router(aq_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER

    with patch.object(aq_mod, "_require_admin", lambda *a, **k: None), \
         patch.object(aq_mod, "get_supabase", return_value=MagicMock()), \
         patch.object(aq_mod.svc, "update_item", return_value=_UPDATED_ITEM):
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
    app.dependency_overrides.clear()


# ── T4: enabled=None → 422 ───────────────────────────────────────────────────

def test_T4_enabled_none_422():
    """T4: enabled 필드 없이 빈 JSON → svc 내 422 (enabled=None 검증)."""
    app = FastAPI()
    app.include_router(aq_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER

    def _svc_422(*a, **k):
        raise FHTTPEx(status_code=422, detail="enabled 값이 필요합니다.")

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
    """T5: 존재하지 않는 qa_item_id → svc 내 404 반환."""
    app = FastAPI()
    app.include_router(aq_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _ADMIN_USER

    def _svc_404(*a, **k):
        raise FHTTPEx(status_code=404, detail="QA 항목을 찾을 수 없습니다.")

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
