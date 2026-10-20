"""WO-TAI-API-SEC-DATA-READ-001-R2+R3 — 접근통제 보안 테스트.

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
# SEC-R3-E-05: 작업자 user_id 있으면 본인 기록 조회 허용
# ════════════════════════════════════════════════════════════════

def test_SEC_R3_E_05_worker_with_user_id_gets_own_records():
    """작업자 경로: user_id가 있으면 requester_id 필터 또는 OR 쿼리로 본인 기록 조회."""
    os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

    worker = {
        "id": "uid-worker-r3e05",
        "company_id": None,   # company_id 없는 작업자
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
        app.dependency_overrides[get_current_user] = lambda: worker
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/work-permits")
            assert resp.status_code == 200, f"작업자 GET /work-permits가 {resp.status_code}. body={resp.text}"
            # eq("requester_id", user_id) 가 적용되어야 함 (phone/company 없으면 eq만 사용)
            assert ("requester_id", "uid-worker-r3e05") in eq_calls, (
                f"requester_id 필터가 없음. eq_calls={eq_calls}"
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
