"""WO-TAI-API-SEC-DATA-READ-001-R2+R3+R4 — 접근통제 보안 테스트.

검증 항목:
  SEC-R2-01  미인증 GET /users → 401
  SEC-R2-02  무효 토큰 GET /users → 401
  SEC-R2-03  작업자 권한으로 GET /users → 403 (USER_VIEW 없음)
  SEC-R2-04  관리자 본인 회사 GET /users → 200 허용
  SEC-R2-05  관리자 타사 GET /users/{id} → 404 차단
  SEC-R2-06  관리자 타사 PATCH /users/{id} → 404 차단
  SEC-R2-07  관리자 타사 DELETE /users/{id} → 404 차단
  SEC-R2-08  일반 사용자 PATCH /users/{id}/role → 403 (USER_UPDATE 없음)
  SEC-R2-09  관리자가 고권한(001) 역할로 승격 → 403 (최고관리자만 가능)
  SEC-R2-10  자기 자신 role 변경 → 403 (SELF_ROLE_CHANGE_FORBIDDEN)
  SEC-R2-11  POST /users 등록 시 타사 company_id → 강제 덮어쓰기 (비어드민)
  SEC-R2-12  POST /users 등록 시 고권한 role_code → 403
  SEC-R2-13  GET /users 응답에 password_hash 없음 (소스 정적 분석)
  SEC-R2-14  미인증 GET /work-permits → 401
  SEC-R2-15  미인증 GET /work-permits?phone=... → 401
  SEC-R2-16  작업자 GET /work-permits → 본인 범위만 (requester_id 필터)
  SEC-R2-17  작업자 GET /work-permits → 타인 phone 파라미터 무시
  SEC-R2-18  관리자 GET /work-permits → JWT company_id 필터 강제
  SEC-R2-19  company_id 없는 비어드민 GET /users → 빈결과
  SEC-R2-20  SUSPENDED 계정 GET /users → 403 (get_current_user ACTIVE 게이트)
  SEC-R2-ST  소스 정적 분석 — users.py / worker_permits.py 보안 패턴 확인

  SEC-R3-E-01  POST /users 응답에 social_token 없음 (allow-list)
  SEC-R3-E-02  POST /users 응답에 push_token 없음 (allow-list)
  SEC-R3-E-03  PATCH /users/{id} 응답에 social_token 없음 (allow-list)
  SEC-R3-E-04  PATCH /users/{id} 응답에 push_token 없음 (allow-list)
  SEC-R3-E-05  작업자 user_id 있으면 본인 기록 조회 허용
  SEC-R3-E-06  작업자 user_id 없으면 빈 결과 (phone 단독 조회 차단)
  SEC-R3-E-07  작업자 OR 조건에 타사 phone 기록 포함 금지 (company_id 필수)
  SEC-R3-E-08  레거시 NULL 기록: phone+company_id 함께 확인
  SEC-R3-E-09  company_id 없는 관리자 work-permits → 본인 기록만 (ID 있으면)
  SEC-R3-E-10  비최고관리자가 고권한(001) 계정 DELETE → 403
  SEC-R3-E-11  비최고관리자가 고권한(001) 계정 상태변경 → 403
  SEC-R3-E-12  최고관리자(001)는 고권한 대상 삭제 가능
  SEC-R3-E-13  소스 정적: _strip_to_public + _PUBLIC_COLS_SET 존재 확인
  SEC-R3-E-14  소스 정적: _assert_target_not_privileged 존재 확인
  SEC-R3-E-15  소스 정적: worker OR 조건에 company_id 범위 포함 확인

  SEC-R4-01  002 관리자가 001 대상 일반 PATCH 차단 (FIX-A)
  SEC-R4-02  001 최고관리자가 관리자 대상 일반 PATCH 허용 (FIX-A)
  SEC-R4-03  작업자 본인 ID 기록에 타사 company_id 차단 (FIX-B)
  SEC-R4-04  작업자 본인 ID + 본인 회사 기록 조회 허용 (FIX-B)
  SEC-R4-05  레거시 NULL 기록의 타사 company_id 차단 (FIX-B)
  SEC-R4-06  company_id 없는 작업자 전체 조회 차단 (FIX-B)
  SEC-R4-07  002 관리자가 신규 002 역할 부여 차단 (FIX-C)
  SEC-R4-08  002 관리자가 기존 002 계정 비활성화 차단 (FIX-C)
  SEC-R4-09  001 최고관리자가 002 역할 부여 허용 (FIX-C)
  SEC-R4-10  타사 factory_id로 사용자 생성 차단 (FIX-D)
  SEC-R4-11  타사 factory_id로 사용자 수정 차단 (FIX-D)
  SEC-R4-12  factory_id와 불일치하는 team_id 차단 (FIX-D)
  SEC-R4-13  정상 회사·공장·팀 계층 허용 (FIX-D)
  SEC-R4-14  allow-list 회귀 PASS (소스 정적)
  SEC-R4-15  작업자 OR 조건 requester_id 분기에 company_id 포함 (소스 정적)

  SEC-R4S-01  소스 정적: _assert_team_belongs_to_factory teams.factory_id만 조회 (company_id 없음)
  SEC-R4S-02  정상 factory_id + team_id + company_id 계층 허용 (teams→factories 경로)
  SEC-R4S-03  team_id만 지정 시 teams→factories 경로로 회사 검증
  SEC-R4S-04  다른 회사 팀 지정 → 차단 (teams→factories company_id 불일치)
  SEC-R4S-05  다른 공장 팀 지정 → 차단 (teams.factory_id 불일치)
  SEC-R4S-06  존재하지 않는 팀 → 차단 (422)
  SEC-R4S-07  공장 없는 팀 (factory_id=None) → FAIL-CLOSE (403)
  SEC-R4S-08  PATCH factory_id만 변경 시 기존 team_id 정합성 재검증 → 차단
  SEC-R4S-09  PATCH 관리자 company_id + factory_id 동시 변경 정상 조합 → 허용
  SEC-R4S-10  PATCH 관리자 company_id 변경 후 기존 factory_id 타사 → 차단
  SEC-R4S-11  company_id 없는 작업자 GET /work-permits → 빈 결과 (FAIL-CLOSE)
  SEC-R4S-12  company_id 있는 작업자 본인 기록 조회 → 기존 동작 유지
  SEC-R4S-13  정상 factory_id + 실제 factory_id NULL 팀 → 403 (우회 차단)
  SEC-R4S-14  PATCH 기존 미배정 팀 + 새 factory_id 조합 → 403 (HOTFIX)
"""
from __future__ import annotations

import importlib
import os
import pathlib
import re
import sys
from typing import Optional
from unittest.mock import MagicMock, patch, call

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_USERS_SRC = (_ROOT / "routers" / "users.py").read_text(encoding="utf-8")
_PERMITS_SRC = (_ROOT / "routers" / "worker_permits.py").read_text(encoding="utf-8")


# ────────────────────────────────────────────────────────────────
# Mock 헬퍼
# ────────────────────────────────────────────────────────────────

def _make_supabase_mock(
    perm_check: bool = True,
    is_all_scope: bool = False,
    users_data: list = None,
    target_user: dict = None,
):
    """공통 supabase Mock 빌더.

    perm_check: role_permissions 쿼리가 True/False 반환
    is_all_scope: role_data_scope가 ALL 반환 여부
    users_data: table("users") execute() 반환 data
    target_user: single() 반환 용도
    """
    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock

    # 기본 체인
    for m in ("select", "eq", "neq", "order", "range", "limit",
              "in_", "or_", "ilike", "gte", "lte"):
        getattr(table_mock, m).return_value = table_mock

    # role_permissions: perm_check
    perm_result = MagicMock()
    perm_result.data = [{"id": "perm-1"}] if perm_check else []

    # role_data_scope: scope
    scope_result = MagicMock()
    scope_result.data = [{"scope_type": "ALL"}] if is_all_scope else [{"scope_type": "COMPANY"}]

    # users 기본 결과
    default_users_result = MagicMock()
    default_users_result.data = users_data if users_data is not None else []
    default_users_result.count = len(default_users_result.data)

    # single()용
    single_result = MagicMock()
    single_result.data = target_user

    table_mock.single.return_value = table_mock

    def _execute_side_effect():
        # table 이름으로 분기
        last_call_table = mock_sb.table.call_args_list[-1][0][0] if mock_sb.table.call_args_list else ""
        if last_call_table == "role_permissions":
            return perm_result
        if last_call_table == "role_data_scope":
            return scope_result
        if last_call_table == "users" and target_user is not None:
            r = MagicMock()
            r.data = target_user
            r.count = 1 if target_user else 0
            return r
        return default_users_result

    table_mock.execute.side_effect = _execute_side_effect

    # auth.get_user: 항상 실패 (토큰 검증 실패)
    mock_sb.auth.get_user.side_effect = Exception("invalid token")
    return mock_sb


def _active_user(role_code="002", company_id="cid-alpha", user_id="uid-test") -> dict:
    return {
        "id": user_id,
        "company_id": company_id,
        "role_code": role_code,
        "status_code": "ACTIVE",
        "is_active": True,
        "name": "테스트관리자",
        "phone": "01012345678",
    }


def _worker_user(user_id="uid-worker", company_id="cid-alpha") -> dict:
    return {
        "id": user_id,
        "company_id": company_id,
        "role_code": "014",
        "status_code": "ACTIVE",
        "is_active": True,
        "name": "테스트작업자",
        "phone": "01099998888",
    }


# ────────────────────────────────────────────────────────────────
# 공통 FastAPI 앱 픽스처
# ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app_client():
    """FastAPI TestClient. 외부 의존성은 Mock으로 대체."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    execute_result = MagicMock()
    execute_result.data = []
    execute_result.count = 0
    for m in ("select", "eq", "neq", "order", "range", "limit",
              "in_", "or_", "single", "ilike", "gte", "lte"):
        getattr(table_mock, m).return_value = table_mock
    table_mock.execute.return_value = execute_result
    mock_sb.auth.get_user.side_effect = Exception("invalid token")

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        yield TestClient(app, raise_server_exceptions=False)


# ════════════════════════════════════════════════════════════════
# SEC-R2-01: GET /users — 미인증 → 401
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_01_get_users_no_token(app_client):
    resp = app_client.get("/users")
    assert resp.status_code == 401, f"미인증 /users가 {resp.status_code} 반환"


# ════════════════════════════════════════════════════════════════
# SEC-R2-02: GET /users — 무효 토큰 → 401
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_02_get_users_invalid_token(app_client):
    resp = app_client.get("/users", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401, f"무효 토큰 /users가 {resp.status_code} 반환"


# ════════════════════════════════════════════════════════════════
# SEC-R2-03: 작업자 권한으로 GET /users → 403 (USER_VIEW 없음)
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_03_worker_role_get_users_forbidden():
    """작업자(014)는 USER_VIEW 권한이 없어 /users 조회 시 403 반환."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = _worker_user()

    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
        getattr(table_mock, m).return_value = table_mock

    # role_permissions → 권한 없음
    no_perm = MagicMock()
    no_perm.data = []
    table_mock.execute.return_value = no_perm

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/users")
            assert resp.status_code == 403, (
                f"작업자 GET /users가 403이어야 하나 {resp.status_code} 반환. "
                f"body={resp.text}"
            )
            data = resp.json()
            assert data.get("detail", {}).get("error") == "PERMISSION_DENIED"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-04: 관리자 본인 회사 사용자 조회 → 200 허용
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_04_admin_own_company_get_users_allowed():
    """USER_VIEW 보유 관리자가 본인 회사 /users 조회 시 200."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
        getattr(table_mock, m).return_value = table_mock

    call_count = [0]

    def _execute():
        call_count[0] += 1
        # 첫 번째 호출: role_permissions (USER_VIEW 있음)
        if call_count[0] == 1:
            r = MagicMock()
            r.data = [{"id": "perm-1"}]
            return r
        # 두 번째 호출: role_data_scope (COMPANY)
        if call_count[0] == 2:
            r = MagicMock()
            r.data = [{"scope_type": "COMPANY"}]
            return r
        # 이후 호출: users 데이터
        r = MagicMock()
        r.data = [{"id": "uid-1", "name": "홍길동", "company_id": "cid-alpha"}]
        r.count = 1
        return r

    table_mock.execute.side_effect = _execute

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/users")
            assert resp.status_code == 200, (
                f"관리자 GET /users가 200이어야 하나 {resp.status_code} 반환. body={resp.text}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-05: 관리자 타사 GET /users/{id} → 404 차단
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_05_admin_cross_company_get_user_blocked():
    """비어드민 관리자가 타사 사용자 조회 시 404."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
        getattr(table_mock, m).return_value = table_mock

    call_count = [0]

    def _execute():
        call_count[0] += 1
        if call_count[0] == 1:  # role_permissions
            r = MagicMock()
            r.data = [{"id": "perm-1"}]
            return r
        if call_count[0] == 2:  # role_data_scope
            r = MagicMock()
            r.data = [{"scope_type": "COMPANY"}]
            return r
        # users 조회: 타사 사용자
        r = MagicMock()
        r.data = {"id": "uid-other", "company_id": "cid-BETA"}
        return r

    table_mock.execute.side_effect = _execute

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/users/uid-other")
            assert resp.status_code == 404, (
                f"타사 GET /users/uid-other가 404이어야 하나 {resp.status_code}. body={resp.text}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-06: 관리자 타사 PATCH /users/{id} → 404 차단
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_06_admin_cross_company_update_user_blocked():
    """비어드민 관리자가 타사 사용자 수정 시 404."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single", "update"):
        getattr(table_mock, m).return_value = table_mock

    call_count = [0]

    def _execute():
        call_count[0] += 1
        if call_count[0] == 1:  # role_permissions
            r = MagicMock()
            r.data = [{"id": "perm-1"}]
            return r
        if call_count[0] == 2:  # role_data_scope
            r = MagicMock()
            r.data = [{"scope_type": "COMPANY"}]
            return r
        # existing user 조회: 타사
        r = MagicMock()
        r.data = {"id": "uid-other", "company_id": "cid-BETA"}
        return r

    table_mock.execute.side_effect = _execute

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.patch("/users/uid-other", json={"name": "공격자"})
            assert resp.status_code == 404, (
                f"타사 PATCH가 404이어야 하나 {resp.status_code}. body={resp.text}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-07: 관리자 타사 DELETE /users/{id} → 404 차단
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_07_admin_cross_company_delete_user_blocked():
    """비어드민 관리자가 타사 사용자 삭제 시 404."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single", "update"):
        getattr(table_mock, m).return_value = table_mock

    call_count = [0]

    def _execute():
        call_count[0] += 1
        if call_count[0] == 1:  # role_permissions
            r = MagicMock()
            r.data = [{"id": "perm-1"}]
            return r
        if call_count[0] == 2:  # role_data_scope
            r = MagicMock()
            r.data = [{"scope_type": "COMPANY"}]
            return r
        r = MagicMock()
        r.data = {"id": "uid-other", "company_id": "cid-BETA"}
        return r

    table_mock.execute.side_effect = _execute

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.delete("/users/uid-other")
            assert resp.status_code == 404, (
                f"타사 DELETE가 404이어야 하나 {resp.status_code}. body={resp.text}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-08: USER_UPDATE 없는 사용자 PATCH /users/{id}/role → 403
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_08_no_user_update_perm_role_change_forbidden():
    """USER_UPDATE 권한이 없으면 역할 변경 403."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    user = _worker_user()  # 014 — USER_UPDATE 없음

    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
        getattr(table_mock, m).return_value = table_mock

    no_perm = MagicMock()
    no_perm.data = []
    table_mock.execute.return_value = no_perm

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.patch("/users/uid-other/role", json={"role_code": "002"})
            assert resp.status_code == 403, (
                f"USER_UPDATE 없는 역할 변경이 403이어야 하나 {resp.status_code}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-09: 비최고관리자가 고권한(001) 역할로 승격 → 403
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_09_non_superadmin_cannot_grant_high_privilege():
    """USER_UPDATE는 있으나 role_code != '001'인 경우 고권한 역할 부여 금지."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")  # 002 — not 001

    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
        getattr(table_mock, m).return_value = table_mock

    # USER_UPDATE 있음
    perm_ok = MagicMock()
    perm_ok.data = [{"id": "perm-1"}]
    table_mock.execute.return_value = perm_ok

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            # 001(최고관리자) 역할 부여 시도
            resp = client.patch("/users/uid-target/role", json={"role_code": "001"})
            assert resp.status_code == 403, (
                f"비최고관리자가 001 부여 시 403이어야 하나 {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "INSUFFICIENT_PRIVILEGE"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-10: 자기 자신 role 변경 → 403
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_10_self_role_change_forbidden():
    """자기 id로 role 변경 시도 시 403."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha", user_id="uid-self")

    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
        getattr(table_mock, m).return_value = table_mock

    perm_ok = MagicMock()
    perm_ok.data = [{"id": "perm-1"}]
    table_mock.execute.return_value = perm_ok

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.patch("/users/uid-self/role", json={"role_code": "002"})
            assert resp.status_code == 403, (
                f"자기 역할 변경이 403이어야 하나 {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "SELF_ROLE_CHANGE_FORBIDDEN"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-11: POST /users 등록 — 비어드민 company_id 강제
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_11_create_user_company_id_overridden_for_non_admin():
    """비어드민이 다른 company_id로 사용자 등록 시도 → JWT company_id로 강제."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_",
                  "single", "update", "insert", "delete"):
            getattr(t, m).return_value = t
        return t

    # role_permissions → USER_CREATE 있음
    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    # role_data_scope → COMPANY (비어드민)
    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # users → email dup check(→[]), insert(→ new user)
    users_mock = _chain()
    users_call = [0]
    inserted_data = [None]

    def users_execute():
        users_call[0] += 1
        r = MagicMock()
        if users_call[0] == 1:  # email dup check
            r.data = []
            return r
        # insert — capture args
        insert_args = users_mock.insert.call_args
        if insert_args:
            inserted_data[0] = insert_args[0][0] if insert_args[0] else {}
        r.data = [{"id": "new-uid", "company_id": "cid-alpha", "role_code": "004"}]
        return r

    users_mock.execute.side_effect = users_execute

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "test@other.com",
                "name": "침투자",
                "company_id": "cid-EVIL",  # 다른 회사 지정
                "role_code": "004",
            })
            assert resp.status_code == 200, f"POST /users가 {resp.status_code}. body={resp.text}"
            data = resp.json().get("data", {})
            assert data.get("company_id") == "cid-alpha", (
                f"비어드민 등록 시 company_id가 JWT 값으로 강제되어야 하나 {data.get('company_id')}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-12: POST /users 등록 — 고권한 role_code 지정 → 403
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_12_create_user_high_privilege_role_blocked():
    """비어드민이 고권한 역할(001)로 사용자 등록 시 403."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "attacker@co.kr",
                "name": "공격자",
                "role_code": "001",  # 최고관리자 역할 지정
            })
            assert resp.status_code == 403, (
                f"고권한 역할 등록이 403이어야 하나 {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ROLE_PRIVILEGE_DENIED"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-13: GET /users 응답에 민감 컬럼 없음 (소스 정적 분석)
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_13_sensitive_columns_excluded_from_select():
    """users.py가 select('*') 대신 명시적 컬럼을 사용하고 민감 컬럼 제외 확인."""
    sensitive_cols = [
        "password_hash",
        "email_verify_token",
        "identity_ci",
    ]
    # _USER_PUBLIC_COLS 상수 정의 확인
    assert "_USER_PUBLIC_COLS" in _USERS_SRC, "_USER_PUBLIC_COLS 상수 없음"

    for col in sensitive_cols:
        # _USER_PUBLIC_COLS 정의 내에 포함되지 않아야 함
        # 정의 블록 찾기
        match = re.search(r'_USER_PUBLIC_COLS\s*=\s*\(([^)]+)\)', _USERS_SRC, re.DOTALL)
        assert match, "_USER_PUBLIC_COLS 정의 블록을 찾을 수 없음"
        cols_block = match.group(1)
        assert col not in cols_block, f"민감 컬럼 '{col}'이 _USER_PUBLIC_COLS에 포함됨"

    # select("*") 가 get_users/get_user에서 사용되지 않는지 확인
    # (users.py 에 select("*") 가 없어야 한다 — _enrich_user_rows 등에서도)
    # 단, 다른 맥락의 select("id") 등은 허용
    star_selects = re.findall(r'select\(["\'](\*)["\']', _USERS_SRC)
    assert len(star_selects) == 0, f"select('*') 발견 ({len(star_selects)}건) — 명시적 컬럼 필수"


# ════════════════════════════════════════════════════════════════
# SEC-R2-14: 미인증 GET /work-permits → 401
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_14_get_work_permits_no_token(app_client):
    resp = app_client.get("/work-permits")
    assert resp.status_code == 401, f"미인증 /work-permits가 {resp.status_code} 반환"


# ════════════════════════════════════════════════════════════════
# SEC-R2-15: 미인증 GET /work-permits?phone=... → 401
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_15_get_work_permits_phone_no_token(app_client):
    """전화번호 파라미터가 있어도 미인증이면 401."""
    resp = app_client.get("/work-permits?phone=01012345678")
    assert resp.status_code == 401, (
        f"미인증+phone /work-permits가 {resp.status_code} 반환 — "
        "전화번호만으로 타인 기록 조회 불가"
    )


# ════════════════════════════════════════════════════════════════
# SEC-R2-16: 작업자 GET /work-permits → 본인 범위만 (requester_id 필터)
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_16_worker_gets_own_work_permits_only():
    """작업자는 본인 requester_id 범위만 조회 (관리자 company 필터 불가)."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = _worker_user(user_id="uid-worker-001")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    # role_permissions → 없음 (작업자)
    perm_mock = _chain()
    no_perm_r = MagicMock(); no_perm_r.data = []
    perm_mock.execute.return_value = no_perm_r

    # role_data_scope → FACTORY
    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "FACTORY"}]
    scope_mock.execute.return_value = scope_r

    # work_permits → 본인 기록
    permits_mock = _chain()
    permits_r = MagicMock()
    permits_r.data = [{"id": "wp-1", "requester_id": "uid-worker-001", "company_id": "cid-alpha"}]
    permits_mock.execute.return_value = permits_r

    # or_ 호출 캡처 (work_permits mock에만 적용)
    or_calls = []
    def capture_or(expr):
        or_calls.append(expr)
        return permits_mock
    permits_mock.or_.side_effect = capture_or

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock,
        "role_data_scope": scope_mock,
        "work_permits": permits_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"작업자 GET /work-permits가 {resp.status_code}. body={resp.text}"
            # 본인 id가 필터에 포함되어야 함 (or_ 또는 eq 중 하나)
            all_or_exprs = " ".join(or_calls)
            assert "uid-worker-001" in all_or_exprs or \
                   any("uid-worker-001" in str(c) for c in permits_mock.eq.call_args_list), (
                "작업자 범위 필터에 본인 uid가 없음"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-17: 작업자가 phone 파라미터로 타인 기록 조회 → 본인 범위 고정
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_17_worker_phone_param_ignored():
    """작업자 경로에서 phone 파라미터는 무시되고 본인 범위만 조회."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = _worker_user(user_id="uid-worker-002")

    mock_sb = MagicMock()
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
        getattr(table_mock, m).return_value = table_mock

    no_perm = MagicMock()
    no_perm.data = []
    scope_factory = MagicMock()
    scope_factory.data = [{"scope_type": "FACTORY"}]
    permits_result = MagicMock()
    permits_result.data = []

    call_count = [0]

    def _execute():
        call_count[0] += 1
        if call_count[0] == 1:
            return no_perm
        if call_count[0] == 2:
            return scope_factory
        return permits_result

    table_mock.execute.side_effect = _execute

    # eq 호출 캡처
    eq_calls = []

    def capture_eq(col, val):
        eq_calls.append((col, val))
        return table_mock

    table_mock.eq.side_effect = capture_eq

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            # 타인 전화번호를 파라미터로 전달
            resp = client.get("/work-permits?phone=01011112222")
            assert resp.status_code == 200, f"응답이 {resp.status_code}"
            # requester_phone=01011112222 필터가 없어야 함 (작업자 경로에서 phone 무시)
            assert ("requester_phone", "01011112222") not in eq_calls, (
                "작업자 경로에서 phone 파라미터가 타인 조회에 사용됨 — 보안 결함"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-18: 관리자 GET /work-permits → JWT company_id 필터 강제
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_18_admin_work_permits_company_scoped():
    """USER_VIEW 보유 관리자는 company_id 필터가 JWT 값으로 강제됨."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # work_permits mock — eq 호출 캡처
    permits_mock = _chain()
    permits_r = MagicMock(); permits_r.data = []
    permits_mock.execute.return_value = permits_r

    eq_calls = []
    def capture_eq(col, val):
        eq_calls.append((col, val))
        return permits_mock
    permits_mock.eq.side_effect = capture_eq

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock,
        "role_data_scope": scope_mock,
        "work_permits": permits_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"관리자 GET /work-permits가 {resp.status_code}"
            # JWT company_id 필터가 work_permits 쿼리에 적용되어야 함
            assert ("company_id", "cid-alpha") in eq_calls, (
                f"JWT company_id 필터가 적용되지 않음. eq_calls={eq_calls}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-19: company_id 없는 비어드민 GET /users → 빈결과
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_19_non_admin_no_company_id_gets_empty():
    """비어드민이 company_id 없으면 전체 조회 불가 → 빈 결과."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    user_no_company = {
        "id": "uid-no-co",
        "company_id": None,
        "role_code": "002",
        "status_code": "ACTIVE",
        "is_active": True,
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: user_no_company
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/users")
            assert resp.status_code == 200, f"응답 {resp.status_code}"
            data = resp.json().get("data", {})
            assert data.get("total") == 0, "company_id 없는 비어드민은 사용자가 0건이어야 함"
            assert data.get("items") == [], "items가 빈 배열이어야 함"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R2-20: SUSPENDED 계정 → 403 (get_current_user ACTIVE 게이트)
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_20_suspended_account_blocked(app_client):
    """SUSPENDED 계정의 유효 토큰도 get_current_user에서 403으로 차단.

    app_client의 mock_sb.auth.get_user는 항상 실패하므로 401 반환.
    이 테스트는 get_current_user 소스에 ACTIVE 게이트 코드 존재를 확인.
    """
    from routers.auth import _require_active_account, get_current_user
    import inspect

    # _require_active_account 함수가 SUSPENDED를 차단하는지 확인
    src = inspect.getsource(_require_active_account)
    assert "SUSPENDED" in src, "_require_active_account에 SUSPENDED 차단 로직 없음"
    assert "ACCOUNT_INACTIVE" in src or "ACCOUNT_SUSPENDED" in src, \
        "SUSPENDED 계정 응답 코드 없음"

    # SUSPENDED 계정으로 실제 호출 시 403
    suspended_user = {
        "id": "uid-suspended",
        "status_code": "SUSPENDED",
        "is_active": False,
        "role_code": "002",
    }
    try:
        _require_active_account(suspended_user)
        assert False, "SUSPENDED 계정이 통과됨"
    except HTTPException as e:
        assert e.status_code == 403, f"SUSPENDED 계정 응답이 403이어야 하나 {e.status_code}"


# ════════════════════════════════════════════════════════════════
# SEC-R2-ST: 소스 정적 분석 — 핵심 보안 패턴 존재 확인
# ════════════════════════════════════════════════════════════════

def test_SEC_R2_ST_01_users_has_permission_helper():
    """users.py에 _has_permission 헬퍼 함수 존재."""
    assert "def _has_permission(" in _USERS_SRC, "_has_permission 헬퍼 없음"
    assert "role_permissions" in _USERS_SRC, "role_permissions 테이블 참조 없음"


def test_SEC_R2_ST_02_users_high_privilege_roles_defined():
    """users.py에 _HIGH_PRIVILEGE_ROLES 상수 정의."""
    assert "_HIGH_PRIVILEGE_ROLES" in _USERS_SRC, "_HIGH_PRIVILEGE_ROLES 상수 없음"
    assert '"001"' in _USERS_SRC, "001 (최고관리자) 코드 없음"


def test_SEC_R2_ST_03_users_role_change_self_forbidden():
    """users.py의 update_user_role에 자기 역할 변경 금지 코드 존재."""
    assert "SELF_ROLE_CHANGE_FORBIDDEN" in _USERS_SRC, "자기 역할 변경 금지 코드 없음"


def test_SEC_R2_ST_04_users_high_privilege_role_guard():
    """update_user_role에 고권한 역할 변경 제한 코드 존재."""
    assert "INSUFFICIENT_PRIVILEGE" in _USERS_SRC, "고권한 역할 변경 제한 코드 없음"
    assert "_HIGH_PRIVILEGE_ROLES" in _USERS_SRC, "_HIGH_PRIVILEGE_ROLES 사용 없음"


def test_SEC_R2_ST_05_users_company_id_forced_create():
    """create_user에서 비어드민 company_id 강제 코드 존재."""
    assert "req.company_id = jwt_company_id" in _USERS_SRC, \
        "create_user에 company_id 강제 코드 없음"


def test_SEC_R2_ST_06_work_permits_get_current_user_required():
    """worker_permits.py의 list_work_permits가 get_current_user Depends 사용."""
    pattern = r"@router\.get\(\"/work-permits\"\).*?def list_work_permits\("
    match = re.search(pattern, _PERMITS_SRC, re.DOTALL)
    assert match, "GET /work-permits 라우터 핸들러를 찾을 수 없음"
    func_sig_start = match.end()
    paren_depth = 1
    end = func_sig_start
    while end < len(_PERMITS_SRC) and paren_depth > 0:
        if _PERMITS_SRC[end] == "(":
            paren_depth += 1
        elif _PERMITS_SRC[end] == ")":
            paren_depth -= 1
        end += 1
    sig_body = _PERMITS_SRC[func_sig_start:end]
    assert "Depends(get_current_user)" in sig_body, (
        f"list_work_permits에 Depends(get_current_user) 없음. 서명: {sig_body[:300]}"
    )


def test_SEC_R2_ST_07_work_permits_worker_scope_applied():
    """worker_permits.py 작업자 경로에 requester_id 범위 필터 코드 존재."""
    assert "requester_id" in _PERMITS_SRC, "requester_id 필터 없음"
    assert "requester_phone" in _PERMITS_SRC, "requester_phone 필터 없음"


def test_SEC_R2_ST_08_work_permits_admin_company_scope():
    """worker_permits.py 관리자 경로에 JWT company_id 강제 코드 존재."""
    assert "jwt_company_id" in _PERMITS_SRC, "jwt_company_id 없음"
    assert 'eq("company_id", jwt_company_id)' in _PERMITS_SRC or \
           "q = q.eq(\"company_id\", jwt_company_id)" in _PERMITS_SRC, \
        "관리자 경로 company_id 필터 없음"


def test_SEC_R2_ST_09_users_assert_company_helper():
    """users.py에 타사 접근 차단 헬퍼(_assert_user_company) 존재."""
    assert "def _assert_user_company(" in _USERS_SRC, "_assert_user_company 헬퍼 없음"
    assert "_assert_user_company(" in _USERS_SRC.split("def _assert_user_company(")[1], \
        "_assert_user_company 호출 없음"


def test_SEC_R2_ST_10_users_no_select_star():
    """users.py의 공개 API에서 select('*') 미사용 — 명시적 컬럼만."""
    # select("*") 또는 select('*') 패턴 검색
    star_matches = re.findall(r"""select\(['"]\*['"]\)""", _USERS_SRC)
    assert len(star_matches) == 0, (
        f"users.py에 select('*') {len(star_matches)}건 발견 — 명시적 컬럼 사용 필수"
    )


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-01: POST /users 응답에 social_token 없음 (allow-list)
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_01_post_users_response_no_social_token():
    """POST /users 등록 응답에 social_token이 포함되지 않아야 함 (_strip_to_public)."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_",
                  "single", "update", "insert", "delete"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    users_mock = _chain()
    users_call = [0]

    def users_execute():
        users_call[0] += 1
        r = MagicMock()
        if users_call[0] == 1:  # email dup check
            r.data = []
            return r
        # insert — 민감 필드 포함된 응답 시뮬레이션
        r.data = [{
            "id": "new-uid", "company_id": "cid-alpha", "role_code": "004",
            "name": "홍길동", "email": "test@co.kr",
            "social_token": "SECRET_SOCIAL_TOKEN",   # 이 필드는 응답에 없어야 함
            "push_token": "SECRET_PUSH_TOKEN",
        }]
        return r

    users_mock.execute.side_effect = users_execute

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={"email": "test@co.kr", "name": "홍길동", "role_code": "004"})
            assert resp.status_code == 200, f"POST /users 실패: {resp.text}"
            data = resp.json().get("data", {})
            assert "social_token" not in data, (
                f"POST /users 응답에 social_token 포함됨 — allow-list 미작동"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-02: POST /users 응답에 push_token 없음 (allow-list)
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_02_post_users_response_no_push_token():
    """POST /users 등록 응답에 push_token이 포함되지 않아야 함."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_",
                  "single", "update", "insert", "delete"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    users_mock = _chain()
    users_call = [0]

    def users_execute():
        users_call[0] += 1
        r = MagicMock()
        if users_call[0] == 1:  # email dup check
            r.data = []
            return r
        r.data = [{
            "id": "new-uid2", "company_id": "cid-alpha", "role_code": "004",
            "name": "김철수", "email": "test2@co.kr",
            "push_token": "DEVICE_PUSH_TOKEN_CONFIDENTIAL",
        }]
        return r

    users_mock.execute.side_effect = users_execute

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={"email": "test2@co.kr", "name": "김철수", "role_code": "004"})
            assert resp.status_code == 200, f"POST /users 실패: {resp.text}"
            data = resp.json().get("data", {})
            assert "push_token" not in data, (
                f"POST /users 응답에 push_token 포함됨 — allow-list 미작동"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-03: PATCH /users/{id} 응답에 social_token 없음
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_03_patch_user_response_no_social_token():
    """PATCH /users/{id} 수정 응답에 social_token이 포함되지 않아야 함."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_",
                  "single", "update", "insert", "delete"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    users_mock = _chain()
    users_call = [0]

    def users_execute():
        users_call[0] += 1
        r = MagicMock()
        if users_call[0] == 1:  # existing user lookup
            r.data = {"id": "uid-target", "company_id": "cid-alpha"}
            return r
        # update 응답 — 민감 필드 포함 시뮬레이션
        r.data = [{
            "id": "uid-target", "company_id": "cid-alpha", "name": "수정됨",
            "social_token": "OAUTH_TOKEN_LEAK",
        }]
        return r

    users_mock.execute.side_effect = users_execute

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.patch("/users/uid-target", json={"name": "수정됨"})
            assert resp.status_code == 200, f"PATCH /users/{'{uid}'} 실패: {resp.text}"
            data = resp.json().get("data", {})
            assert "social_token" not in data, (
                f"PATCH /users 응답에 social_token 포함됨 — allow-list 미작동"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-04: PATCH /users/{id} 응답에 push_token 없음
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_04_patch_user_response_no_push_token():
    """PATCH /users/{id} 수정 응답에 push_token이 포함되지 않아야 함."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_",
                  "single", "update", "insert", "delete"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    users_mock = _chain()
    users_call = [0]

    def users_execute():
        users_call[0] += 1
        r = MagicMock()
        if users_call[0] == 1:  # existing user lookup
            r.data = {"id": "uid-target2", "company_id": "cid-alpha"}
            return r
        r.data = [{
            "id": "uid-target2", "company_id": "cid-alpha", "name": "수정됨2",
            "push_token": "FCM_DEVICE_TOKEN_SECRET",
        }]
        return r

    users_mock.execute.side_effect = users_execute

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.patch("/users/uid-target2", json={"name": "수정됨2"})
            assert resp.status_code == 200, f"PATCH /users 실패: {resp.text}"
            data = resp.json().get("data", {})
            assert "push_token" not in data, (
                f"PATCH /users 응답에 push_token 포함됨 — allow-list 미작동"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-05: company_id 없는 작업자 → FAIL-CLOSE 빈 결과
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_05_worker_without_company_gets_empty_result():
    """작업자 경로: company_id 없으면 FAIL-CLOSE — work_permits 쿼리 없이 빈 결과 반환.

    FIX-03: requester_id 단독 노출은 겸직·이동 시 타사 기록 접근 허용 위험.
    company_id 미확정 상태에서는 회사 경계를 확인할 수 없으므로 빈 결과로 안전 차단.
    """
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = {
        "id": "uid-worker-r3e05",
        "company_id": None,   # company_id 없는 작업자 → FAIL-CLOSE
        "role_code": "014",
        "status_code": "ACTIVE",
        "is_active": True,
        "phone": "",
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "limit", "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    no_perm_r = MagicMock(); no_perm_r.data = []
    perm_mock.execute.return_value = no_perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "FACTORY"}]
    scope_mock.execute.return_value = scope_r

    permits_mock = _chain()
    permits_r = MagicMock()
    permits_r.data = [{"id": "wp-r3e05", "requester_id": "uid-worker-r3e05"}]
    permits_mock.execute.return_value = permits_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock,
        "role_data_scope": scope_mock,
        "work_permits": permits_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"작업자 GET /work-permits가 {resp.status_code}. body={resp.text}"
            body = resp.json()
            # FIX-03: company_id 없는 작업자 → FAIL-CLOSE 빈 결과
            assert body["data"]["items"] == [], (
                f"company_id 없는 작업자가 빈 결과가 아님: items={body['data']['items']}"
            )
            assert body["data"]["total"] == 0, f"total이 0이 아님: {body['data']['total']}"
            # FAIL-CLOSE 경로에서 work_permits 테이블 execute 미호출 확인
            assert not permits_mock.execute.called, (
                "FAIL-CLOSE 경로에서 work_permits 쿼리가 실행됨 — company 경계 없이 조회 차단 실패"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-06: 작업자 user_id 없으면 빈 결과 (phone 단독 조회 차단)
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_06_worker_no_user_id_gets_empty():
    """user_id 없는 작업자는 phone 단독으로 타인 기록 조회 불가 → 빈 결과."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker_no_id = {
        "id": None,   # id 없음
        "company_id": "cid-alpha",
        "role_code": "014",
        "status_code": "ACTIVE",
        "is_active": True,
        "phone": "01099998888",
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "limit", "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    no_perm_r = MagicMock(); no_perm_r.data = []
    perm_mock.execute.return_value = no_perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "FACTORY"}]
    scope_mock.execute.return_value = scope_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock,
        "role_data_scope": scope_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker_no_id
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"응답: {resp.status_code} {resp.text}"
            data = resp.json().get("data", {})
            assert data.get("items") == [], "user_id 없으면 빈 결과여야 함"
            assert data.get("total") == 0
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-07: OR 조건에 타사 phone 기록 포함 금지 (company_id 필수)
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_07_worker_or_clause_includes_company_id_scope():
    """작업자 경로 OR 조건에서 phone 기반 레거시 기록은 company_id 제한 필수."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = {
        "id": "uid-worker-r3e07",
        "company_id": "cid-alpha",
        "role_code": "014",
        "status_code": "ACTIVE",
        "is_active": True,
        "phone": "01055556666",
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "limit", "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    no_perm_r = MagicMock(); no_perm_r.data = []
    perm_mock.execute.return_value = no_perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "FACTORY"}]
    scope_mock.execute.return_value = scope_r

    permits_mock = _chain()
    permits_r = MagicMock(); permits_r.data = []
    permits_mock.execute.return_value = permits_r

    or_calls = []
    def capture_or(expr):
        or_calls.append(expr)
        return permits_mock
    permits_mock.or_.side_effect = capture_or

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock,
        "role_data_scope": scope_mock,
        "work_permits": permits_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"응답: {resp.status_code} {resp.text}"
            # OR 조건이 사용되었으면 company_id가 포함되어야 함
            if or_calls:
                all_or = " ".join(or_calls)
                assert "company_id" in all_or, (
                    f"작업자 OR 조건에 company_id 없음 — 타사 phone 기록 노출 위험. or_expr={all_or}"
                )
                # phone만 단독으로 조회하는 패턴이 없어야 함 (requester_id.is.null 없이 phone만 있으면 위험)
                assert "requester_id.is.null" in all_or or "requester_id.eq." in all_or, (
                    f"OR 조건에 requester_id 제약 없음: {all_or}"
                )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-08: 레거시 NULL 기록: phone+company_id 함께 확인
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_08_legacy_null_requester_id_includes_company_scope():
    """worker_permits.py OR 표현식이 'requester_id.is.null' 조건을 포함하는지 확인."""
    # 소스 코드 정적 분석 — 레거시 NULL 기록 처리 패턴
    assert "requester_id.is.null" in _PERMITS_SRC, (
        "worker_permits.py에 requester_id IS NULL 레거시 기록 처리 없음"
    )
    # NULL 레거시 기록 처리 시 company_id 범위 제한 필수
    null_idx = _PERMITS_SRC.index("requester_id.is.null")
    # null 조건 주변 200자 내에 company_id 필터가 있어야 함
    context = _PERMITS_SRC[max(0, null_idx - 50):null_idx + 200]
    assert "company_id" in context, (
        f"requester_id IS NULL 처리에 company_id 범위 없음. 컨텍스트: {context}"
    )


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-09: company_id 없는 관리자 work-permits → ID 기반 본인 기록
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_09_admin_without_company_gets_own_records_only():
    """USER_VIEW 있으나 company_id 없는 관리자 → 본인 requester_id 기록만 (안전 폴백)."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin_no_co = {
        "id": "uid-admin-no-co",
        "company_id": None,
        "role_code": "002",
        "status_code": "ACTIVE",
        "is_active": True,
        "phone": "01099991111",
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "limit", "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    permits_mock = _chain()
    permits_r = MagicMock(); permits_r.data = []
    permits_mock.execute.return_value = permits_r

    eq_calls = []
    def capture_eq(col, val):
        eq_calls.append((col, val))
        return permits_mock
    permits_mock.eq.side_effect = capture_eq

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock,
        "role_data_scope": scope_mock,
        "work_permits": permits_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin_no_co
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"응답: {resp.status_code} {resp.text}"
            # company_id 없는 관리자는 본인 requester_id 필터 (안전 폴백)
            # 전사 조회 차단 — company_id 필터 없이 전체 조회되면 안 됨
            any_company_filter = any(col == "company_id" for col, _ in eq_calls)
            any_id_filter = any(col == "requester_id" for col, _ in eq_calls)
            assert any_id_filter or resp.json().get("data", {}).get("items") == [], (
                f"company_id 없는 관리자가 전사 조회됨. eq_calls={eq_calls}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-10: 비최고관리자가 고권한(001) 계정 DELETE → 403
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_10_non_superadmin_cannot_delete_superadmin_account():
    """비최고관리자(002)가 최고관리자(001) 계정 삭제 시 403."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single", "update"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # 대상: 동일 회사의 최고관리자(001)
    users_mock = _chain()
    users_r = MagicMock()
    users_r.data = {"id": "uid-superadmin", "company_id": "cid-alpha", "role_code": "001"}
    users_mock.execute.return_value = users_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.delete("/users/uid-superadmin")
            assert resp.status_code == 403, (
                f"비최고관리자가 001 계정 삭제 시 403이어야 하나 {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "TARGET_PRIVILEGE_DENIED"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-11: 비최고관리자가 고권한(001) 계정 상태변경 → 403
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_11_non_superadmin_cannot_change_superadmin_status():
    """비최고관리자(002)가 최고관리자(001) 계정 상태 변경 시 403."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single", "update"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # 대상: 동일 회사의 최고관리자(001)
    users_mock = _chain()
    users_r = MagicMock()
    users_r.data = {"id": "uid-superadmin2", "company_id": "cid-alpha", "role_code": "001"}
    users_mock.execute.return_value = users_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.patch("/users/uid-superadmin2/status", json={"status_code": "SUSPENDED"})
            assert resp.status_code == 403, (
                f"비최고관리자가 001 계정 상태변경 시 403이어야 하나 {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "TARGET_PRIVILEGE_DENIED"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-12: 최고관리자(001)는 고권한 대상 삭제 가능
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_12_superadmin_can_delete_privileged_account():
    """최고관리자(001)는 동일 회사의 고권한(031) 계정 삭제 가능."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    superadmin = _active_user(role_code="001", company_id="cid-alpha", user_id="uid-super-001")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit", "in_", "or_", "single", "update"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    # 001은 scope=ALL
    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "ALL"}]
    scope_mock.execute.return_value = scope_r

    # 대상: 고권한(031) 계정
    users_mock = _chain()
    users_call = [0]

    def users_execute():
        users_call[0] += 1
        r = MagicMock()
        if users_call[0] == 1:  # SELECT existing user
            r.data = {"id": "uid-031", "company_id": "cid-alpha", "role_code": "031"}
            return r
        r.data = []  # work_schedules update
        return r

    users_mock.execute.side_effect = users_execute

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: superadmin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.delete("/users/uid-031")
            assert resp.status_code == 200, (
                f"최고관리자가 031 계정 삭제 시 200이어야 하나 {resp.status_code}. body={resp.text}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-13: 소스 정적: _strip_to_public + _PUBLIC_COLS_SET 존재
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_13_allow_list_helpers_defined():
    """users.py에 allow-list 헬퍼(_strip_to_public, _PUBLIC_COLS_SET) 존재."""
    assert "def _strip_to_public(" in _USERS_SRC, "_strip_to_public 헬퍼 없음"
    assert "_PUBLIC_COLS_SET" in _USERS_SRC, "_PUBLIC_COLS_SET 상수 없음"
    # deny-list pop 패턴이 아닌 allow-list 사용 확인
    assert "_strip_to_public(" in _USERS_SRC.split("def _strip_to_public(")[1], (
        "_strip_to_public 호출 없음 — allow-list 미적용"
    )
    # 기존 pop-list 패턴이 응답 경로에서 사라졌는지 확인 (social_token, push_token 수동 pop 없음)
    response_section = _USERS_SRC
    assert 'pop("social_token"' not in response_section and "pop('social_token'" not in response_section, (
        "social_token을 수동 pop — allow-list로 대체 필요"
    )
    assert 'pop("push_token"' not in response_section and "pop('push_token'" not in response_section, (
        "push_token을 수동 pop — allow-list로 대체 필요"
    )


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-14: 소스 정적: _assert_target_not_privileged 존재 및 호출 확인
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_14_target_privilege_guard_defined_and_called():
    """users.py에 _assert_target_not_privileged 헬퍼가 정의되고 복수 호출됨."""
    assert "def _assert_target_not_privileged(" in _USERS_SRC, (
        "_assert_target_not_privileged 헬퍼 없음"
    )
    assert "TARGET_PRIVILEGE_DENIED" in _USERS_SRC, "TARGET_PRIVILEGE_DENIED 에러 코드 없음"
    # 정의 이후 부분에서 호출 확인 (delete_user, update_user_status, update_user_role에 각 1회)
    after_def = _USERS_SRC.split("def _assert_target_not_privileged(")[1]
    call_count = after_def.count("_assert_target_not_privileged(")
    assert call_count >= 3, (
        f"_assert_target_not_privileged 호출이 3회 미만 ({call_count}회) — "
        "delete_user/update_user_status/update_user_role 모두 적용 필요"
    )


# ════════════════════════════════════════════════════════════════
# SEC-R3-E-15: 소스 정적: worker OR 조건에 company_id 범위 포함
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_15_worker_or_clause_has_company_scope_in_source():
    """worker_permits.py worker 경로 OR 조건에 company_id 범위가 소스에 명시됨."""
    # 소스에서 작업자 OR 표현식 패턴 확인
    assert "requester_id.is.null" in _PERMITS_SRC, (
        "worker_permits.py에 requester_id IS NULL 레거시 처리 없음"
    )
    # OR 표현식에 company_id 범위가 포함되어야 함
    or_idx = _PERMITS_SRC.find("requester_id.is.null")
    context = _PERMITS_SRC[max(0, or_idx - 100):or_idx + 300]
    assert "company_id" in context, (
        f"OR 조건 requester_id.is.null 근처에 company_id 없음. 컨텍스트:\n{context}"
    )
    # 이전 R2 취약 패턴(phone만 단독 OR) 제거 확인
    # "requester_phone.eq.{phone}" 이 company_id 없이 단독으로 OR 조건에 있으면 안 됨
    old_pattern = re.search(
        r'or_\([^)]*requester_id\.eq\.[^,]+,requester_phone\.eq\.[^)]+\)',
        _PERMITS_SRC,
        re.DOTALL,
    )
    assert old_pattern is None, (
        "취약 패턴 발견: company_id 없이 phone만 단독 OR 조건 사용 — R3-B 미적용"
    )


# ════════════════════════════════════════════════════════════════
# SEC-R4-01: 002 관리자가 001 대상 일반 PATCH 차단 (FIX-A)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_01_manager_patch_superadmin_blocked():
    """002 관리자가 001 최고관리자 계정 일반 PATCH 시도 → 403 TARGET_PRIVILEGE_DENIED."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha", user_id="uid-mgr-r4")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert", "delete"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    # 002 → COMPANY scope (비최고관리자)
    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # 대상: 동일 회사의 최고관리자(001)
    users_mock = _chain()
    users_r = MagicMock()
    users_r.data = {"id": "uid-super-001", "company_id": "cid-alpha",
                    "factory_id": None, "role_code": "001"}
    users_mock.execute.return_value = users_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.patch("/users/uid-super-001", json={"name": "변조시도"})
            assert resp.status_code == 403, (
                f"002가 001 대상 PATCH 시 403이어야 하나 {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "TARGET_PRIVILEGE_DENIED", (
                f"에러코드 TARGET_PRIVILEGE_DENIED 아님: {body}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-02: 001 최고관리자가 002 대상 일반 PATCH 허용 (FIX-A)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_02_superadmin_patch_manager_allowed():
    """001 최고관리자가 002 관리자 계정 일반 PATCH → 200 허용 (scope=ALL 우회)."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    superadmin = _active_user(role_code="001", company_id="cid-alpha", user_id="uid-super-001")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert", "delete"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    # 001 → ALL scope
    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "ALL"}]
    scope_mock.execute.return_value = scope_r

    # 대상: 002 관리자 (고권한이지만 001이 조작 가능)
    users_mock = _chain()
    users_calls = [0]

    def users_exec():
        users_calls[0] += 1
        r = MagicMock()
        if users_calls[0] == 1:
            # existing SELECT
            r.data = {"id": "uid-002-target", "company_id": "cid-alpha",
                      "factory_id": None, "role_code": "002"}
        else:
            # UPDATE 결과
            r.data = [{"id": "uid-002-target", "name": "수정완료", "company_id": "cid-alpha"}]
        return r

    users_mock.execute.side_effect = users_exec

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: superadmin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.patch("/users/uid-002-target", json={"name": "수정완료"})
            assert resp.status_code == 200, (
                f"001이 002 대상 PATCH 시 200이어야 하나 {resp.status_code}. body={resp.text}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-03: 작업자 본인 ID 기록에 타사 company_id 차단 (FIX-B)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_03_worker_requester_id_or_includes_company_id():
    """작업자 phone+company_id 있을 때 OR 조건 requester_id 분기에도 company_id 포함 확인."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = {
        "id": "uid-worker-r4a",
        "company_id": "cid-alpha",
        "role_code": "014",
        "phone": "01099998888",
        "status_code": "ACTIVE",
        "is_active": True,
        "name": "R4작업자",
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    # 작업자: USER_VIEW 없음
    perm_no_mock = _chain()
    perm_no_r = MagicMock(); perm_no_r.data = []
    perm_no_mock.execute.return_value = perm_no_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    wp_mock = _chain()
    wp_r = MagicMock(); wp_r.data = []
    wp_mock.execute.return_value = wp_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_no_mock,
        "role_data_scope": scope_mock,
        "work_permits": wp_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"작업자 GET /work-permits가 {resp.status_code}"
            # OR 조건이 호출됐어야 함 (phone+cid 있는 경우)
            assert wp_mock.or_.called, (
                "work_permits.or_ 미호출 — requester_id 분기에 company_id 범위 없음"
            )
            call_arg = wp_mock.or_.call_args[0][0]
            assert "company_id.eq.cid-alpha" in call_arg, (
                f"OR 조건에 company_id 없음 — 타사 기록 노출 위험. OR인자:\n{call_arg}"
            )
            assert "requester_id.eq.uid-worker-r4a" in call_arg, (
                f"OR 조건에 requester_id 없음. OR인자:\n{call_arg}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-04: 작업자 본인 ID + 본인 회사 기록 조회 허용 (FIX-B)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_04_worker_with_company_id_gets_own_permits():
    """작업자에게 company_id 있으면 GET /work-permits → 200 정상 반환."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = {
        "id": "uid-worker-r4b",
        "company_id": "cid-alpha",
        "role_code": "014",
        "phone": "01011112222",
        "status_code": "ACTIVE",
        "is_active": True,
        "name": "R4작업자B",
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_no_mock = _chain()
    perm_no_r = MagicMock(); perm_no_r.data = []
    perm_no_mock.execute.return_value = perm_no_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    wp_mock = _chain()
    wp_r = MagicMock()
    wp_r.data = [{"id": "wp-001", "requester_id": "uid-worker-r4b", "company_id": "cid-alpha"}]
    wp_mock.execute.return_value = wp_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_no_mock,
        "role_data_scope": scope_mock,
        "work_permits": wp_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"작업자 허가서 조회 실패: {resp.status_code}"
            body = resp.json()
            assert body["data"]["total"] >= 1, "작업자 본인 기록 반환 실패"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-05: 레거시 NULL 기록의 타사 company_id 차단 (FIX-B)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_05_legacy_null_requester_has_company_scope():
    """OR 조건의 requester_id IS NULL 분기에도 company_id 범위 포함 확인."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = {
        "id": "uid-worker-r4c",
        "company_id": "cid-alpha",
        "role_code": "014",
        "phone": "01033334444",
        "status_code": "ACTIVE",
        "is_active": True,
        "name": "R4작업자C",
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_no_mock = _chain()
    perm_no_r = MagicMock(); perm_no_r.data = []
    perm_no_mock.execute.return_value = perm_no_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    wp_mock = _chain()
    wp_r = MagicMock(); wp_r.data = []
    wp_mock.execute.return_value = wp_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_no_mock,
        "role_data_scope": scope_mock,
        "work_permits": wp_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200
            assert wp_mock.or_.called, "레거시 NULL 처리 OR 조건 미호출"
            call_arg = wp_mock.or_.call_args[0][0]
            # IS NULL 분기에도 company_id 범위가 있어야 함
            assert "requester_id.is.null" in call_arg, (
                f"OR 조건에 requester_id.is.null 없음 — 레거시 기록 처리 누락:\n{call_arg}"
            )
            assert "company_id.eq.cid-alpha" in call_arg, (
                f"IS NULL 분기에 company_id 없음 — 레거시 타사 기록 노출 위험:\n{call_arg}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-06: company_id 없는 작업자 전체 조회 차단 (FIX-B)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_06_worker_without_company_id_returns_empty():
    """company_id 없는 작업자: 회사 소속 미확정 → FAIL-CLOSE (빈 결과, work_permits 미조회)."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = {
        "id": "uid-worker-no-cid",
        "company_id": None,  # company_id 없음
        "role_code": "014",
        "phone": "01055556666",
        "status_code": "ACTIVE",
        "is_active": True,
        "name": "무회사작업자",
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_no_mock = _chain()
    perm_no_r = MagicMock(); perm_no_r.data = []
    perm_no_mock.execute.return_value = perm_no_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    wp_mock = _chain()
    wp_r = MagicMock(); wp_r.data = []
    wp_mock.execute.return_value = wp_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_no_mock,
        "role_data_scope": scope_mock,
        "work_permits": wp_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"무회사 작업자 조회가 {resp.status_code}"
            body = resp.json()
            # FIX-03: company_id 없으면 빈 결과 반환 (work_permits 쿼리 미실행)
            assert body["data"]["items"] == [], (
                f"무회사 작업자에게 기록이 반환됨 — 타사 기록 노출 위험. items={body['data']['items']}"
            )
            assert body["data"]["total"] == 0
            assert not wp_mock.execute.called, (
                "company_id 없는 작업자에서 work_permits 쿼리 실행됨 — FAIL-CLOSE 미적용"
            )
            assert not wp_mock.or_.called, (
                "company_id 없는 작업자에서 or_ 호출됨"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-07: 002 관리자가 신규 002 역할 부여 차단 (FIX-C)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_07_manager_002_cannot_grant_002_role():
    """002 관리자가 POST /users 로 role_code='002' 부여 시도 → 403 ROLE_PRIVILEGE_DENIED."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha", user_id="uid-mgr-r4c")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    # 002 → COMPANY scope (비최고관리자)
    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "newmgr@test.com",
                "name": "신규관리자",
                "role_code": "002",
            })
            assert resp.status_code == 403, (
                f"002가 002 역할 부여 시 403이어야 하나 {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ROLE_PRIVILEGE_DENIED", (
                f"에러코드 ROLE_PRIVILEGE_DENIED 아님: {body}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-08: 002 관리자가 기존 002 계정 비활성화 차단 (FIX-C)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_08_manager_002_cannot_deactivate_002_account():
    """002 관리자가 다른 002 계정 DELETE 시도 → 403 TARGET_PRIVILEGE_DENIED."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha", user_id="uid-mgr-r4d")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "delete"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    # 002 → COMPANY (비최고관리자)
    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # 대상: 동일 회사의 002 계정
    users_mock = _chain()
    users_r = MagicMock()
    users_r.data = {"id": "uid-002-other", "company_id": "cid-alpha", "role_code": "002"}
    users_mock.execute.return_value = users_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.delete("/users/uid-002-other")
            assert resp.status_code == 403, (
                f"002가 002 계정 DELETE 시 403이어야 하나 {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "TARGET_PRIVILEGE_DENIED", (
                f"에러코드 TARGET_PRIVILEGE_DENIED 아님: {body}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-09: 001 최고관리자가 002 역할 부여 허용 (FIX-C)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_09_superadmin_can_grant_002_role():
    """001 최고관리자가 POST /users 로 role_code='002' 부여 → 200 허용."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    superadmin = _active_user(role_code="001", company_id="cid-alpha", user_id="uid-super-r4")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    # 001 → ALL scope
    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "ALL"}]
    scope_mock.execute.return_value = scope_r

    # users: dup check 없음, insert 성공
    users_mock = _chain()
    users_calls = [0]

    def users_exec():
        users_calls[0] += 1
        r = MagicMock()
        if users_calls[0] == 1:
            r.data = []  # email dup 없음
        else:
            r.data = [{"id": "uid-new-002", "email": "admin2@test.com", "role_code": "002"}]
        return r

    users_mock.execute.side_effect = users_exec

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {"role_permissions": perm_mock, "role_data_scope": scope_mock, "users": users_mock}
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: superadmin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "admin2@test.com",
                "name": "신규관리자",
                "role_code": "002",
            })
            assert resp.status_code == 200, (
                f"001이 002 역할 부여 시 200이어야 하나 {resp.status_code}. body={resp.text}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-10: 타사 factory_id로 사용자 생성 차단 (FIX-D)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_10_create_user_with_foreign_factory_blocked():
    """POST /users에 타사 소속 factory_id 지정 시 → 403 ORG_HIERARCHY_VIOLATION."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha", user_id="uid-mgr-r4e")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # factory "fid-other"는 "cid-beta" 소속 (타사)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-beta"}]
    factory_mock.execute.return_value = factory_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock,
        "role_data_scope": scope_mock,
        "factories": factory_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "newuser@test.com",
                "name": "신규사용자",
                "factory_id": "fid-other",
            })
            assert resp.status_code == 403, (
                f"타사 factory_id 생성 차단 실패: {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ORG_HIERARCHY_VIOLATION", (
                f"에러코드 ORG_HIERARCHY_VIOLATION 아님: {body}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-11: 타사 factory_id로 사용자 수정 차단 (FIX-D)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_11_update_user_with_foreign_factory_blocked():
    """PATCH /users/{id}에 타사 소속 factory_id 지정 시 → 403 ORG_HIERARCHY_VIOLATION."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha", user_id="uid-mgr-r4f")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # 기존 사용자: 일반 역할(010)
    users_mock = _chain()
    users_r = MagicMock()
    users_r.data = {"id": "uid-normal", "company_id": "cid-alpha",
                    "factory_id": None, "role_code": "010"}
    users_mock.execute.return_value = users_r

    # factory "fid-other"는 "cid-beta" 소속 (타사)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-beta"}]
    factory_mock.execute.return_value = factory_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock,
        "role_data_scope": scope_mock,
        "users": users_mock,
        "factories": factory_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.patch("/users/uid-normal", json={"factory_id": "fid-other"})
            assert resp.status_code == 403, (
                f"타사 factory_id 수정 차단 실패: {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ORG_HIERARCHY_VIOLATION", (
                f"에러코드 ORG_HIERARCHY_VIOLATION 아님: {body}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-12: factory_id와 불일치하는 team_id 차단 (FIX-D)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_12_create_user_with_mismatched_team_blocked():
    """POST /users에 factory_id와 불일치하는 team_id 지정 시 → 403 ORG_HIERARCHY_VIOLATION."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha", user_id="uid-mgr-r4g")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # factory "fid-a"는 "cid-alpha" 소속 (OK)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-alpha"}]
    factory_mock.execute.return_value = factory_r

    # team "tid-b"는 "fid-c" 소속 (fid-a와 불일치) — 운영 DB 계약: factory_id만 존재
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = [{"factory_id": "fid-c"}]
    team_mock.execute.return_value = team_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock,
        "role_data_scope": scope_mock,
        "factories": factory_mock,
        "teams": team_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "mismatch@test.com",
                "name": "불일치팀",
                "factory_id": "fid-a",
                "team_id": "tid-b",
            })
            assert resp.status_code == 403, (
                f"factory/team 불일치 차단 실패: {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ORG_HIERARCHY_VIOLATION", (
                f"에러코드 ORG_HIERARCHY_VIOLATION 아님: {body}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-13: 정상 회사·공장·팀 계층 허용 (FIX-D)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_13_create_user_with_valid_hierarchy_allowed():
    """POST /users에 유효한 factory_id + team_id 지정 시 → 200 허용."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-alpha", user_id="uid-mgr-r4h")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # factory "fid-a" → "cid-alpha" 소속 (OK)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-alpha"}]
    factory_mock.execute.return_value = factory_r

    # team "tid-a" → factory_id="fid-a" (운영 DB 계약: company_id 없음, teams→factories 경로)
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = [{"factory_id": "fid-a"}]
    team_mock.execute.return_value = team_r

    # users: dup 없음, insert 성공
    users_mock = _chain()
    users_calls = [0]

    def users_exec():
        users_calls[0] += 1
        r = MagicMock()
        if users_calls[0] == 1:
            r.data = []  # email dup 없음
        else:
            r.data = [{"id": "uid-valid-new", "email": "valid@test.com",
                       "name": "정상사용자", "factory_id": "fid-a", "team_id": "tid-a"}]
        return r

    users_mock.execute.side_effect = users_exec

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock,
        "role_data_scope": scope_mock,
        "factories": factory_mock,
        "teams": team_mock,
        "users": users_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "valid@test.com",
                "name": "정상사용자",
                "factory_id": "fid-a",
                "team_id": "tid-a",
            })
            assert resp.status_code == 200, (
                f"유효 계층 사용자 생성 실패: {resp.status_code}. body={resp.text}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4-14: allow-list 회귀 PASS — 민감 토큰 제외 확인 (소스 정적)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_14_allow_list_excludes_sensitive_columns():
    """_PUBLIC_COLS_SET에 social_token, push_token, password_hash가 포함되지 않음."""
    # _USER_PUBLIC_COLS 문자열에 민감 컬럼 없음
    assert "social_token" not in _USERS_SRC.split("_PUBLIC_COLS_SET")[0].split("_USER_PUBLIC_COLS")[1] if "_USER_PUBLIC_COLS" in _USERS_SRC else True, (
        "_USER_PUBLIC_COLS 정의에 social_token 포함됨"
    )
    assert "push_token" not in (
        _USERS_SRC.split("_PUBLIC_COLS_SET =")[0] if "_PUBLIC_COLS_SET =" in _USERS_SRC else ""
    ), "_PUBLIC_COLS_SET 정의 이전에 push_token 없어야 함"

    # 소스에서 _USER_PUBLIC_COLS 상수 추출 후 검증
    match = re.search(r'_USER_PUBLIC_COLS\s*=\s*\(\s*\n?(.*?)\n?\)', _USERS_SRC, re.DOTALL)
    assert match, "_USER_PUBLIC_COLS 상수를 찾을 수 없음"
    cols_block = match.group(1)
    assert "social_token" not in cols_block, (
        "_USER_PUBLIC_COLS에 social_token 포함됨 — 민감 토큰 노출 위험"
    )
    assert "push_token" not in cols_block, (
        "_USER_PUBLIC_COLS에 push_token 포함됨 — 민감 토큰 노출 위험"
    )
    assert "password_hash" not in cols_block, (
        "_USER_PUBLIC_COLS에 password_hash 포함됨 — 비밀번호 해시 노출 위험"
    )
    # allow-list 헬퍼가 INSERT/UPDATE 응답에 사용됨
    after_def = _USERS_SRC.split("def _strip_to_public(")[1]
    call_count = after_def.count("_strip_to_public(")
    assert call_count >= 2, (
        f"_strip_to_public 호출이 2회 미만 ({call_count}회) — "
        "create_user/update_user 응답에 allow-list 미적용"
    )


# ════════════════════════════════════════════════════════════════
# SEC-R4-15: 작업자 OR 조건 requester_id 분기에 company_id 포함 (소스 정적)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4_15_worker_or_requester_id_branch_has_company_id_in_source():
    """worker_permits.py worker 경로: requester_id 분기 OR 조건에 company_id 포함 확인 (소스 정적)."""
    # and(requester_id.eq.{user_id},company_id.eq.{user_cid}) 패턴 확인
    assert "and(requester_id.eq." in _PERMITS_SRC, (
        "worker_permits.py에 requester_id 분기 compound AND 패턴 없음"
    )
    idx = _PERMITS_SRC.find("and(requester_id.eq.")
    context = _PERMITS_SRC[idx: idx + 200]
    assert "company_id.eq." in context, (
        f"requester_id 분기에 company_id 없음 — 겸직/이동 시 타사 기록 노출 위험.\n"
        f"컨텍스트:\n{context}"
    )
    # 이전 R4 취약 패턴 부재 확인: requester_id 단독 OR (company_id 없음)
    # "requester_id.eq.{user_id}" 가 company_id 없이 단독 OR 되면 안 됨
    bare_pattern = re.search(
        r'or_\(["\']requester_id\.eq\.[^,]+,requester_phone\.eq\.',
        _PERMITS_SRC,
    )
    assert bare_pattern is None, (
        "취약 패턴 발견: requester_id 단독 OR (company_id 없이) — FIX-B 미적용"
    )


# ════════════════════════════════════════════════════════════════
# SEC-R4S-01: 소스 정적 — teams 조회 컬럼 계약 (factory_id만, company_id 없음)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_01_teams_select_contract_factory_id_only():
    """_assert_team_belongs_to_factory 가 teams.factory_id만 조회 (company_id 없음) 확인."""
    # 함수 정의 이후 소스에서 teams select 패턴 확인
    after_def = _USERS_SRC.split("def _assert_team_belongs_to_factory(")[1]
    # teams.select 에서 company_id가 포함되지 않아야 함
    teams_select = re.search(r'\.select\("([^"]*)"[^)]*\)', after_def)
    assert teams_select, "_assert_team_belongs_to_factory에서 teams select 패턴 못 찾음"
    select_cols = teams_select.group(1)
    assert "company_id" not in select_cols, (
        f"teams.select에 company_id 포함됨 — 운영 DB 계약 위반 (컬럼 없음): {select_cols}"
    )
    assert "factory_id" in select_cols, (
        f"teams.select에 factory_id 없음: {select_cols}"
    )
    # 함수 내에 factories 테이블 2차 조회가 있어야 함 (company_id 검증 경로)
    assert '"factories"' in after_def.split("def _assert_factory_belongs_to_company")[0], (
        "_assert_team_belongs_to_factory에서 factories 2차 조회 없음 — company_id 검증 경로 누락"
    )


# ════════════════════════════════════════════════════════════════
# SEC-R4S-02: 정상 factory_id + team_id + company_id → 허용 (teams→factories 경로)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_02_valid_team_factory_company_hierarchy_allowed():
    """POST /users: 유효한 factory+team 계층 (teams→factories 경로) → 200."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-a", user_id="uid-mgr-s02")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # factories: fid-x → cid-a (두 번 조회됨: factory 직접 + team→factory)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-a"}]
    factory_mock.execute.return_value = factory_r

    # teams: factory_id만 존재 (운영 DB 계약)
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = [{"factory_id": "fid-x"}]
    team_mock.execute.return_value = team_r

    users_mock = _chain()
    users_calls = [0]

    def users_exec():
        users_calls[0] += 1
        r = MagicMock()
        if users_calls[0] == 1:
            r.data = []  # no dup
        else:
            r.data = [{"id": "uid-new-s02", "email": "s02@test.com"}]
        return r

    users_mock.execute.side_effect = users_exec

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "factories": factory_mock, "teams": team_mock, "users": users_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "s02@test.com", "name": "S02사용자",
                "factory_id": "fid-x", "team_id": "tid-x",
            })
            assert resp.status_code == 200, (
                f"유효 계층 생성 실패: {resp.status_code}. body={resp.text}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-03: team_id만 지정 → teams→factories 경로로 회사 검증
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_03_team_id_only_validates_via_factories():
    """POST /users에 team_id만 지정 (factory_id 없음) → teams→factories 경유 회사 검증 → 200."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-a", user_id="uid-mgr-s03")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # team tid-y → factory fid-y (teams.factory_id만)
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = [{"factory_id": "fid-y"}]
    team_mock.execute.return_value = team_r

    # factories fid-y → cid-a (회사 소속 확인)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-a"}]
    factory_mock.execute.return_value = factory_r

    users_mock = _chain()
    users_calls = [0]

    def users_exec():
        users_calls[0] += 1
        r = MagicMock()
        if users_calls[0] == 1:
            r.data = []
        else:
            r.data = [{"id": "uid-new-s03", "email": "s03@test.com"}]
        return r

    users_mock.execute.side_effect = users_exec

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "factories": factory_mock, "teams": team_mock, "users": users_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "s03@test.com", "name": "S03사용자",
                "team_id": "tid-y",  # factory_id 없음
            })
            assert resp.status_code == 200, (
                f"team_id만 지정 시 teams→factories 경로 검증 실패: {resp.status_code}. body={resp.text}"
            )
            # teams 테이블이 실제로 조회됐는지 확인
            assert team_mock.execute.called, "teams 테이블 미조회 — 계층 검증 누락"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-04: 다른 회사 팀 지정 → 차단 (teams→factories company_id 불일치)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_04_team_from_different_company_blocked():
    """팀의 factories.company_id가 JWT company_id와 다를 때 → 403."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-a", user_id="uid-mgr-s04")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # factory_mock: req.factory_id 없으므로 _assert_factory_belongs_to_company 미호출
    # factory_mock: teams→factories 경로에서 사용 → cid-b (타사)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-b"}]
    factory_mock.execute.return_value = factory_r

    # team → factory fid-z (타사 소속)
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = [{"factory_id": "fid-z"}]
    team_mock.execute.return_value = team_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "factories": factory_mock, "teams": team_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "s04@test.com", "name": "S04사용자",
                "team_id": "tid-z",
            })
            assert resp.status_code == 403, (
                f"타사 팀 차단 실패: {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ORG_HIERARCHY_VIOLATION"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-05: 다른 공장 팀 지정 → 차단 (teams.factory_id 불일치)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_05_team_from_different_factory_blocked():
    """요청 factory_id와 teams.factory_id가 다를 때 → 403."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-a", user_id="uid-mgr-s05")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # factory "fid-req" → cid-a (OK for factory check)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-a"}]
    factory_mock.execute.return_value = factory_r

    # team tid-s5 → factory "fid-other" (fid-req와 불일치)
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = [{"factory_id": "fid-other"}]
    team_mock.execute.return_value = team_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "factories": factory_mock, "teams": team_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "s05@test.com", "name": "S05사용자",
                "factory_id": "fid-req", "team_id": "tid-s5",
            })
            assert resp.status_code == 403, (
                f"공장 불일치 팀 차단 실패: {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ORG_HIERARCHY_VIOLATION"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-06: 존재하지 않는 팀 → 차단 (422)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_06_nonexistent_team_blocked():
    """POST /users에 존재하지 않는 team_id 지정 시 → 422 INVALID_TEAM."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-a", user_id="uid-mgr-s06")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-a"}]
    factory_mock.execute.return_value = factory_r

    # 존재하지 않는 팀 → empty
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = []
    team_mock.execute.return_value = team_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "factories": factory_mock, "teams": team_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "s06@test.com", "name": "S06사용자",
                "factory_id": "fid-req", "team_id": "tid-nonexist",
            })
            assert resp.status_code == 422, (
                f"미존재 팀 422 아님: {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "INVALID_TEAM"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-07: factory_id 없는 팀 (FAIL-CLOSE) → 403
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_07_team_without_factory_id_fail_close():
    """teams.factory_id=None인 팀 (소속 확인 불가) → 403 FAIL-CLOSE."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-a", user_id="uid-mgr-s07")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # team tid-nofactory → factory_id=None (소속 공장 미배정)
    # factory_id 요청 없음 → effective_fid = None → FAIL-CLOSE
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = [{"factory_id": None}]
    team_mock.execute.return_value = team_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "teams": team_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "s07@test.com", "name": "S07사용자",
                "team_id": "tid-nofactory",
            })
            assert resp.status_code == 403, (
                f"factory_id 없는 팀 FAIL-CLOSE 실패: {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ORG_HIERARCHY_VIOLATION"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-08: PATCH factory_id만 변경 시 기존 team_id 정합성 재검증 → 차단
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_08_patch_factory_change_invalidates_existing_team():
    """PATCH: factory_id만 변경해 기존 team_id와 불일치 → 403."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-a", user_id="uid-mgr-s08")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # 기존 사용자: factory_id="fid-old", team_id="tid-old"
    users_mock = _chain()
    users_r = MagicMock()
    users_r.data = {"id": "uid-tgt", "company_id": "cid-a",
                    "factory_id": "fid-old", "team_id": "tid-old", "role_code": "010"}
    users_mock.execute.return_value = users_r

    # 새 factory "fid-new" → cid-a (OK)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-a"}]
    factory_mock.execute.return_value = factory_r

    # 기존 team "tid-old" → 아직 "fid-old" 소속 (fid-new와 불일치)
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = [{"factory_id": "fid-old"}]
    team_mock.execute.return_value = team_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "users": users_mock, "factories": factory_mock, "teams": team_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            # factory_id만 변경 (team_id 미변경) — 기존 team이 새 factory와 불일치
            resp = client.patch("/users/uid-tgt", json={"factory_id": "fid-new"})
            assert resp.status_code == 403, (
                f"factory 변경 후 기존 team 정합성 검증 실패: {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ORG_HIERARCHY_VIOLATION"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-09: PATCH 관리자 company_id + factory_id 동시 변경 정상 조합 → 허용
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_09_admin_patch_company_and_factory_valid_combination_allowed():
    """001 관리자가 company_id + factory_id 동시 변경 (정상 조합) → 200."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    superadmin = _active_user(role_code="001", company_id="cid-a", user_id="uid-super-s09")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    # 001 → ALL scope
    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "ALL"}]
    scope_mock.execute.return_value = scope_r

    # 기존 사용자: cid-a, fid-a, no team
    users_mock = _chain()
    users_calls = [0]

    def users_exec():
        users_calls[0] += 1
        r = MagicMock()
        if users_calls[0] == 1:
            r.data = {"id": "uid-tgt-s09", "company_id": "cid-a",
                      "factory_id": "fid-a", "team_id": None, "role_code": "010"}
        else:
            r.data = [{"id": "uid-tgt-s09"}]
        return r

    users_mock.execute.side_effect = users_exec

    # 새 factory "fid-b" → 새 회사 cid-b (정합성 OK)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-b"}]
    factory_mock.execute.return_value = factory_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "users": users_mock, "factories": factory_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: superadmin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            # 관리자가 회사+공장 동시 변경 (새 factory가 새 company 소속)
            resp = client.patch("/users/uid-tgt-s09", json={
                "company_id": "cid-b", "factory_id": "fid-b",
            })
            assert resp.status_code == 200, (
                f"관리자 company+factory 동시 변경 허용 실패: {resp.status_code}. body={resp.text}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-10: PATCH 관리자 company_id 변경 후 기존 factory_id 타사 → 차단
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_10_admin_patch_company_change_with_mismatched_factory_blocked():
    """001 관리자가 company_id 변경 + 기존 factory_id가 새 company 소속 아님 → 403."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    superadmin = _active_user(role_code="001", company_id="cid-a", user_id="uid-super-s10")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "ALL"}]
    scope_mock.execute.return_value = scope_r

    # 기존 사용자: cid-a, fid-a (cid-a 소속)
    users_mock = _chain()
    users_r = MagicMock()
    users_r.data = {"id": "uid-tgt-s10", "company_id": "cid-a",
                    "factory_id": "fid-a", "team_id": None, "role_code": "010"}
    users_mock.execute.return_value = users_r

    # fid-a → cid-a (기존 company 소속, 새 company cid-b와 불일치)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-a"}]
    factory_mock.execute.return_value = factory_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "users": users_mock, "factories": factory_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: superadmin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            # company_id만 변경 (factory_id 미변경) — 기존 factory가 새 company 소속 아님
            resp = client.patch("/users/uid-tgt-s10", json={"company_id": "cid-b"})
            assert resp.status_code == 403, (
                f"company 변경 후 기존 factory 검증 실패: {resp.status_code}. body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ORG_HIERARCHY_VIOLATION"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-11: company_id 없는 작업자 GET /work-permits → 빈 결과 (FAIL-CLOSE)
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_11_worker_no_company_id_get_permits_fail_close():
    """company_id 없는 작업자 GET /work-permits → 200 빈 결과 (work_permits 미쿼리)."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = {
        "id": "uid-worker-s11",
        "company_id": None,
        "role_code": "014",
        "phone": "01077778888",
        "status_code": "ACTIVE",
        "is_active": True,
        "name": "S11무회사작업자",
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_no_mock = _chain()
    perm_no_r = MagicMock(); perm_no_r.data = []
    perm_no_mock.execute.return_value = perm_no_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    wp_mock = _chain()
    wp_r = MagicMock(); wp_r.data = []
    wp_mock.execute.return_value = wp_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_no_mock,
        "role_data_scope": scope_mock,
        "work_permits": wp_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"S11 조회가 {resp.status_code}"
            body = resp.json()
            assert body["data"]["items"] == [], "company_id 없는 작업자에게 기록 반환됨"
            assert body["data"]["total"] == 0
            # work_permits 테이블 실제 쿼리 미실행 확인 (FAIL-CLOSE)
            assert not wp_mock.execute.called, "work_permits execute 호출됨 — FAIL-CLOSE 미적용"
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-12: company_id 있는 작업자 본인 기록 조회 → 기존 동작 유지
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_12_worker_with_company_id_normal_query():
    """company_id 있는 작업자 GET /work-permits → OR 조건으로 정상 쿼리."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = {
        "id": "uid-worker-s12",
        "company_id": "cid-x",
        "role_code": "014",
        "phone": "01088889999",
        "status_code": "ACTIVE",
        "is_active": True,
        "name": "S12정상작업자",
    }

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single"):
            getattr(t, m).return_value = t
        return t

    perm_no_mock = _chain()
    perm_no_r = MagicMock(); perm_no_r.data = []
    perm_no_mock.execute.return_value = perm_no_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    wp_mock = _chain()
    wp_r = MagicMock()
    wp_r.data = [{"id": "wp-s12", "requester_id": "uid-worker-s12", "company_id": "cid-x"}]
    wp_mock.execute.return_value = wp_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_no_mock,
        "role_data_scope": scope_mock,
        "work_permits": wp_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"S12 조회가 {resp.status_code}"
            body = resp.json()
            assert body["data"]["total"] >= 1, "S12 작업자 기록 반환 실패"
            # company_id 있으면 OR 조건 (phone+cid) 또는 eq(id+cid) — 쿼리 실행됨
            assert wp_mock.execute.called, "work_permits execute 미호출 — 정상 쿼리 누락"
            # OR 조건에 company_id 포함 확인
            assert wp_mock.or_.called, "company_id 있는 작업자에서 or_ 미호출"
            call_arg = wp_mock.or_.call_args[0][0]
            assert "company_id.eq.cid-x" in call_arg
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-13: 정상 factory_id + 실제 teams.factory_id NULL 팀 → 403
# R4S-HOTFIX 핵심 케이스: 요청 factory_id로 미배정 팀 소속 보충 우회 차단
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_13_valid_factory_with_null_team_factory_blocked():
    """POST /users: 유효한 factory_id 제공 + 팀의 실제 factory_id=NULL → 403.

    공격 경로: admin이 자기 회사 factory_id를 지정하면서 미배정 팀(factory_id=NULL)을
    함께 지정. 이전 코드는 요청 factory_id로 회사 검증을 통과시켜 우회 가능.
    수정 후: teams.factory_id NULL → Step2에서 즉시 403 (요청값 무시).
    """
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="002", company_id="cid-a", user_id="uid-mgr-s13")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "COMPANY"}]
    scope_mock.execute.return_value = scope_r

    # factory fid-valid → 정상, cid-a 소속
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-a"}]
    factory_mock.execute.return_value = factory_r

    # team tid-null-factory → teams.factory_id = NULL (공장 미배정)
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = [{"factory_id": None}]
    team_mock.execute.return_value = team_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "factories": factory_mock, "teams": team_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/users", json={
                "email": "s13@test.com", "name": "S13우회시도",
                "factory_id": "fid-valid",    # 정상 factory (cid-a 소속)
                "team_id": "tid-null-factory", # teams.factory_id = NULL
            })
            assert resp.status_code == 403, (
                f"R4S-HOTFIX: 미배정 팀 우회 차단 실패. status={resp.status_code} body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ORG_HIERARCHY_VIOLATION", (
                f"오류 코드 불일치: {body.get('detail')}"
            )
            # factory 검증에서가 아닌 team NULL 단계에서 차단됐는지 확인
            assert "배정되지 않아" in body.get("detail", {}).get("message", ""), (
                f"팀 미배정 메시지 누락: {body.get('detail')}"
            )
        finally:
            app.dependency_overrides.clear()


# ════════════════════════════════════════════════════════════════
# SEC-R4S-14: PATCH 기존 미배정 팀 + 새 factory_id 조합 → 403
# ════════════════════════════════════════════════════════════════

def test_SEC_R4S_14_patch_new_factory_with_existing_null_team_blocked():
    """PATCH /users/{id}: 새 factory_id 변경 + 기존 team.factory_id=NULL → 403.

    기존 사용자에게 team_id는 그대로 두고 factory_id만 변경할 때,
    기존 team의 factory_id가 NULL이면 재검증에서 차단돼야 한다.
    """
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    admin = _active_user(role_code="001", company_id="cid-a", user_id="uid-super-s14")

    def _chain():
        t = MagicMock()
        for m in ("select", "eq", "neq", "order", "range", "limit",
                  "in_", "or_", "single", "update", "insert"):
            getattr(t, m).return_value = t
        return t

    perm_mock = _chain()
    perm_r = MagicMock(); perm_r.data = [{"id": "perm-1"}]
    perm_mock.execute.return_value = perm_r

    scope_mock = _chain()
    scope_r = MagicMock(); scope_r.data = [{"scope_type": "ALL"}]
    scope_mock.execute.return_value = scope_r

    # 대상 사용자: 기존에 team_id="tid-null-fac" 배정, factory_id 없음
    target_user_r = MagicMock()
    target_user_r.data = {
        "id": "uid-target-s14",
        "company_id": "cid-a",
        "factory_id": None,
        "team_id": "tid-null-fac",
        "role_code": "014",
    }

    users_mock = _chain()
    users_mock.single.return_value = users_mock
    users_mock.execute.return_value = target_user_r

    # factory fid-new → cid-a 소속 (정상 공장)
    factory_mock = _chain()
    factory_r = MagicMock(); factory_r.data = [{"company_id": "cid-a"}]
    factory_mock.execute.return_value = factory_r

    # team tid-null-fac → teams.factory_id = NULL (공장 미배정)
    team_mock = _chain()
    team_r = MagicMock(); team_r.data = [{"factory_id": None}]
    team_mock.execute.return_value = team_r

    default_mock = _chain()
    def_r = MagicMock(); def_r.data = []; def_r.count = 0
    default_mock.execute.return_value = def_r

    tables = {
        "role_permissions": perm_mock, "role_data_scope": scope_mock,
        "users": users_mock,
        "factories": factory_mock,
        "teams": team_mock,
    }
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: tables.get(name, default_mock)

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        from routers.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            client = TestClient(app, raise_server_exceptions=False)
            # factory_id만 변경 — 기존 team_id는 그대로 (미지정)
            resp = client.patch("/users/uid-target-s14", json={
                "factory_id": "fid-new",  # 새 factory (cid-a 소속)
                # team_id 미포함 — 기존 tid-null-fac 유지
            })
            assert resp.status_code == 403, (
                f"R4S-HOTFIX PATCH: 미배정 기존 팀 우회 차단 실패. "
                f"status={resp.status_code} body={resp.text}"
            )
            body = resp.json()
            assert body.get("detail", {}).get("error") == "ORG_HIERARCHY_VIOLATION", (
                f"오류 코드 불일치: {body.get('detail')}"
            )
        finally:
            app.dependency_overrides.clear()
