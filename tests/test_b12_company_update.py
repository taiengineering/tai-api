"""
B12-SAAS-SET-FNC-002: PATCH /companies/{id} — 회사정보 수정 계약 검증

검증 목표:
  V1: 인증 없음 → 401
  V2: 타사 company_id 경로 → 404 (_ensure_own_company 존재 숨김)
  V3: 정상 수정 → 200, 수정 메시지 반환

구조:
  _ensure_own_company: tier=COMPANY 비-ALL 사용자는 token.company_id ≠ 경로 company_id → 404
  _tier: role_data_scope.scope_type 조회 (role_data_scope 테이블 SELECT)
  update_company: companies.single() 존재 확인 → companies.update()

운영 안전:
  monkeypatch + FastAPI TestClient 전용 — 운영 DB/API 미접촉
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.companies as co_mod
from routers.auth import get_current_user

_CO_A_ID = "co-aaaa-0000-0000-0000-000000000001"
_CO_B_ID = "co-bbbb-0000-0000-0000-000000000002"

_CALLER = {
    "id":          "usr-b12-0001",
    "company_id":  _CO_A_ID,
    "role_code":   "010",
    "is_active":   True,
    "status_code": "ACTIVE",
}


def _make_sb_for_update() -> MagicMock:
    """
    update_company 경로 Supabase 체인 모의.
    - role_data_scope → scope_type=COMPANY (_tier 조회)
    - companies SELECT single → {id: _CO_A_ID}  (기존 존재 확인)
    - companies UPDATE → [{id: _CO_A_ID, name: "보정된 회사명"}]
    """
    sb = MagicMock()

    # _tier 조회: .table().select().eq().limit().execute()
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[{"scope_type": "COMPANY"}])

    # 기존 회사 존재 확인: .table().select().eq().single().execute()
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = \
        MagicMock(data={"id": _CO_A_ID})

    # 수정 결과: .table().update().eq().execute()
    sb.table.return_value.update.return_value.eq.return_value.execute.return_value = \
        MagicMock(data=[{"id": _CO_A_ID, "name": "보정된 회사명", "updated_at": "2026-11-08T00:00:00"}])

    return sb


def _make_app_with_user(sb: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(co_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _CALLER
    with patch.object(co_mod, "get_supabase", return_value=sb):
        return TestClient(app, raise_server_exceptions=False)


# ── V1: 인증 없음 → 401 ──────────────────────────────────────────────────

def test_V1_no_auth_401():
    """V1: Authorization 헤더 없음 → get_current_user가 401 발생."""
    sb = MagicMock()
    with patch.object(co_mod, "get_supabase", return_value=sb):
        app = FastAPI()
        app.include_router(co_mod.router)
        # dependency_overrides 없음 → 실제 get_current_user 실행 → 401
        client = TestClient(app, raise_server_exceptions=False)
        r = client.patch(f"/companies/{_CO_A_ID}", json={"company_name": "테스트 회사"})
    assert r.status_code == 401, f"예상 401, 실제 {r.status_code}: {r.text}"


# ── V2: 타사 company_id → 404 ───────────────────────────────────────────

def test_V2_cross_company_404():
    """V2: 토큰 company_id(_CO_A_ID)와 경로 company_id(_CO_B_ID) 불일치 → 404.

    _ensure_own_company: 비-ALL 사용자는 타사 자원을 404로 숨김.
    """
    sb = _make_sb_for_update()
    client = _make_app_with_user(sb)
    with patch.object(co_mod, "get_supabase", return_value=sb):
        # 경로에 타사 company_id 사용
        r = client.patch(f"/companies/{_CO_B_ID}", json={"company_name": "타사 회사명"})
    assert r.status_code == 404, f"예상 404 (존재 숨김), 실제 {r.status_code}: {r.text}"


# ── V3: 정상 수정 → 200 ──────────────────────────────────────────────────

def test_V3_success_200():
    """V3: 자사 company_id + 유효 토큰 → 200, 수정 성공 메시지."""
    sb = _make_sb_for_update()
    client = _make_app_with_user(sb)
    with patch.object(co_mod, "get_supabase", return_value=sb):
        r = client.patch(
            f"/companies/{_CO_A_ID}",
            json={"company_name": "보정된 회사명"},
        )
    assert r.status_code == 200, f"예상 200, 실제 {r.status_code}: {r.text}"
    body = r.json()
    assert body["status"] == "success"
    assert "수정됐습니다" in body.get("message", ""), (
        f"성공 메시지 없음. body: {body}"
    )
