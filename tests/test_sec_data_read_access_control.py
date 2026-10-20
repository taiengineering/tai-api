"""WO-TAI-API-SEC-DATA-READ-001 — GET /users, GET /work-permits 접근통제 테스트.

검증 항목:
  SEC-READ-01  GET /users: 토큰 없음 → 401
  SEC-READ-02  GET /users: 유효하지 않은 토큰 → 401
  SEC-READ-03  GET /work-permits: 토큰 없음 + phone 없음 → 401
  SEC-READ-04  GET /work-permits: 유효하지 않은 토큰 → 401
  SEC-READ-05  GET /users: JWT company_id 있으면 company_id 파라미터 덮어씀 (정적 로직)
  SEC-READ-06  GET /work-permits: 미인증 + phone → requester_phone 필터 적용 (정적 로직)
  SEC-READ-07  GET /work-permits: 인증 있음 + JWT company_id → company_id 필터 적용 (정적 로직)
  SEC-READ-08  GET /users: get_current_user Depends 등록 확인 (소스 정적 분석)
  SEC-READ-09  GET /work-permits: _optional_auth Depends 등록 확인 (소스 정적 분석)
  SEC-READ-10  GET /work-permits: FAIL-CLOSE 분기 존재 (소스 정적 분석)
  SEC-READ-11  GET /users/{user_id}: 인증 의무화 (소스 정적 분석)
  SEC-READ-12  POST /users: 인증 의무화 (소스 정적 분석)
  SEC-READ-13  DELETE /users/{user_id}: 인증 의무화 (소스 정적 분석)
  SEC-READ-14  GET /users: JWT company_id 강제 코드 존재 (소스 정적 분석)
  SEC-READ-15  GET /work-permits: 인증 있을 때 JWT company_id 강제 코드 존재 (소스 정적 분석)
"""
from __future__ import annotations

import importlib
import inspect
import os
import pathlib
import sys
import re
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_USERS_SRC = (_ROOT / "routers" / "users.py").read_text(encoding="utf-8")
_PERMITS_SRC = (_ROOT / "routers" / "worker_permits.py").read_text(encoding="utf-8")


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
    # Supabase client call chains
    table_mock = MagicMock()
    mock_sb.table.return_value = table_mock
    execute_result = MagicMock()
    execute_result.data = []
    execute_result.count = 0
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.neq.return_value = table_mock
    table_mock.order.return_value = table_mock
    table_mock.range.return_value = table_mock
    table_mock.limit.return_value = table_mock
    table_mock.in_.return_value = table_mock
    table_mock.or_.return_value = table_mock
    table_mock.single.return_value = table_mock
    table_mock.execute.return_value = execute_result
    # auth.get_user always fails for invalid tokens
    mock_sb.auth.get_user.side_effect = Exception("invalid token")

    with patch("db.supabase_client.get_supabase", return_value=mock_sb):
        for mod in list(sys.modules.keys()):
            if mod in ("main",) or mod.startswith(("routers.", "services.")):
                del sys.modules[mod]
        from main import app
        yield TestClient(app, raise_server_exceptions=False)


def _valid_token_headers(company_id: Optional[str] = "cid-test") -> dict:
    """get_current_user 를 패치하여 유효한 토큰처럼 동작시킨다."""
    return {"Authorization": "Bearer valid-token"}


def _user_payload(company_id: Optional[str] = "cid-test") -> dict:
    return {"id": "uid-test", "company_id": company_id, "role_code": "001"}


# ════════════════════════════════════════════════════════════════
# SEC-READ-01: GET /users — 토큰 없음 → 401
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_01_get_users_no_token(app_client):
    resp = app_client.get("/users")
    assert resp.status_code == 401, f"토큰 없이 /users 접근이 {resp.status_code} 반환"


# ════════════════════════════════════════════════════════════════
# SEC-READ-02: GET /users — 유효하지 않은 토큰 → 401
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_02_get_users_invalid_token(app_client):
    resp = app_client.get("/users", headers={"Authorization": "Bearer invalid-token"})
    assert resp.status_code == 401, f"유효하지 않은 토큰으로 /users 접근이 {resp.status_code} 반환"


# ════════════════════════════════════════════════════════════════
# SEC-READ-03: GET /work-permits — 토큰 없음 + phone 없음 → 401
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_03_get_work_permits_no_auth_no_phone(app_client):
    resp = app_client.get("/work-permits")
    assert resp.status_code == 401, f"미인증+phone없음 /work-permits 접근이 {resp.status_code} 반환"


# ════════════════════════════════════════════════════════════════
# SEC-READ-04: GET /work-permits — 유효하지 않은 토큰 → 401
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_04_get_work_permits_invalid_token(app_client):
    resp = app_client.get("/work-permits", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401, f"유효하지 않은 토큰으로 /work-permits 접근이 {resp.status_code} 반환"


# ════════════════════════════════════════════════════════════════
# SEC-READ-05: JWT company_id 강제 로직 — 정적 분석
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_05_get_users_jwt_company_override_logic():
    """get_users에서 jwt_company_id가 있으면 company_id를 덮어쓰는 코드 존재."""
    assert "jwt_company_id = current_user.get(\"company_id\")" in _USERS_SRC, \
        "jwt_company_id 추출 코드 없음"
    assert "if jwt_company_id:" in _USERS_SRC, \
        "jwt_company_id 조건 분기 없음"
    assert "company_id = jwt_company_id" in _USERS_SRC, \
        "JWT company_id로 파라미터 덮어쓰기 없음"


# ════════════════════════════════════════════════════════════════
# SEC-READ-06: 미인증+phone → requester_phone 필터 정적 분석
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_06_work_permits_phone_only_filter_logic():
    """미인증+phone 경로에서 requester_phone으로만 필터링."""
    assert "q = q.eq(\"requester_phone\", _clean_phone(phone))" in _PERMITS_SRC, \
        "미인증+phone 경로에 requester_phone 필터 없음"


# ════════════════════════════════════════════════════════════════
# SEC-READ-07: 인증+JWT company_id → company_id 필터 정적 분석
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_07_work_permits_auth_company_scope_logic():
    """인증된 사용자 경로에서 JWT company_id로 범위 강제."""
    assert "jwt_company_id = current_user.get(\"company_id\")" in _PERMITS_SRC, \
        "worker_permits에서 jwt_company_id 추출 없음"
    assert "q = q.eq(\"company_id\", jwt_company_id)" in _PERMITS_SRC, \
        "JWT company_id 필터 없음"


# ════════════════════════════════════════════════════════════════
# SEC-READ-08: GET /users — get_current_user Depends 소스 정적 분석
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_08_get_users_has_depends_get_current_user():
    pattern = r"@router\.get\(\"\"\).*?def get_users\("
    match = re.search(pattern, _USERS_SRC, re.DOTALL)
    assert match, "GET /users 라우트 handler를 찾을 수 없음"
    func_sig_start = match.end()
    paren_depth = 1
    end = func_sig_start
    while end < len(_USERS_SRC) and paren_depth > 0:
        if _USERS_SRC[end] == "(":
            paren_depth += 1
        elif _USERS_SRC[end] == ")":
            paren_depth -= 1
        end += 1
    sig_body = _USERS_SRC[func_sig_start:end]
    assert "Depends(get_current_user)" in sig_body, \
        f"get_users에 Depends(get_current_user) 없음. 시그니처: {sig_body[:200]}"


# ════════════════════════════════════════════════════════════════
# SEC-READ-09: GET /work-permits — _optional_auth Depends 소스 정적 분석
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_09_get_work_permits_has_depends_optional_auth():
    pattern = r"@router\.get\(\"/work-permits\"\).*?def list_work_permits\("
    match = re.search(pattern, _PERMITS_SRC, re.DOTALL)
    assert match, "GET /work-permits 라우트 handler를 찾을 수 없음"
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
    assert "Depends(_optional_auth)" in sig_body, \
        f"list_work_permits에 Depends(_optional_auth) 없음. 시그니처: {sig_body[:200]}"


# ════════════════════════════════════════════════════════════════
# SEC-READ-10: FAIL-CLOSE 분기 존재
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_10_work_permits_fail_close_branch():
    assert "if current_user is None and not phone:" in _PERMITS_SRC, \
        "FAIL-CLOSE 조건 분기 없음"
    assert "status_code=401" in _PERMITS_SRC, \
        "401 응답 코드 없음"
    assert "AUTH_REQUIRED" in _PERMITS_SRC, \
        "AUTH_REQUIRED 오류 코드 없음"


# ════════════════════════════════════════════════════════════════
# SEC-READ-11: GET /users/{user_id} 인증 의무화
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_11_get_user_by_id_has_auth():
    pattern = r"@router\.get\(\"\/{user_id}\"\).*?def get_user\("
    match = re.search(pattern, _USERS_SRC, re.DOTALL)
    assert match, "GET /{user_id} handler를 찾을 수 없음"
    sig_start = match.end()
    paren_depth = 1
    end = sig_start
    while end < len(_USERS_SRC) and paren_depth > 0:
        if _USERS_SRC[end] == "(":
            paren_depth += 1
        elif _USERS_SRC[end] == ")":
            paren_depth -= 1
        end += 1
    sig_body = _USERS_SRC[sig_start:end]
    assert "Depends(get_current_user)" in sig_body, \
        "GET /{user_id}에 Depends(get_current_user) 없음"


# ════════════════════════════════════════════════════════════════
# SEC-READ-12: POST /users 인증 의무화
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_12_post_users_has_auth():
    pattern = r"@router\.post\(\"\"\).*?def create_user\("
    match = re.search(pattern, _USERS_SRC, re.DOTALL)
    assert match, "POST /users handler를 찾을 수 없음"
    sig_start = match.end()
    paren_depth = 1
    end = sig_start
    while end < len(_USERS_SRC) and paren_depth > 0:
        if _USERS_SRC[end] == "(":
            paren_depth += 1
        elif _USERS_SRC[end] == ")":
            paren_depth -= 1
        end += 1
    sig_body = _USERS_SRC[sig_start:end]
    assert "Depends(get_current_user)" in sig_body, \
        "POST /users에 Depends(get_current_user) 없음"


# ════════════════════════════════════════════════════════════════
# SEC-READ-13: DELETE /users/{user_id} 인증 의무화
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_13_delete_user_has_auth():
    pattern = r"@router\.delete\(\"\/{user_id}\"\).*?def delete_user\("
    match = re.search(pattern, _USERS_SRC, re.DOTALL)
    assert match, "DELETE /{user_id} handler를 찾을 수 없음"
    sig_start = match.end()
    paren_depth = 1
    end = sig_start
    while end < len(_USERS_SRC) and paren_depth > 0:
        if _USERS_SRC[end] == "(":
            paren_depth += 1
        elif _USERS_SRC[end] == ")":
            paren_depth -= 1
        end += 1
    sig_body = _USERS_SRC[sig_start:end]
    assert "Depends(get_current_user)" in sig_body, \
        "DELETE /{user_id}에 Depends(get_current_user) 없음"


# ════════════════════════════════════════════════════════════════
# SEC-READ-14: JWT company_id 강제 코드 — get_users 내 위치 확인
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_14_company_scope_in_get_users_body():
    """JWT company_id 강제가 get_users 함수 바디에 위치."""
    func_match = re.search(r"def get_users\(", _USERS_SRC)
    assert func_match, "get_users 함수 없음"
    func_body = _USERS_SRC[func_match.start():]
    # 다음 @router 이전까지만
    next_router = re.search(r"\n@router\.", func_body[10:])
    if next_router:
        func_body = func_body[:next_router.start() + 10]
    assert "jwt_company_id" in func_body, \
        "get_users 함수 바디에 jwt_company_id 없음"


# ════════════════════════════════════════════════════════════════
# SEC-READ-15: JWT company_id 강제 코드 — list_work_permits 내 위치 확인
# ════════════════════════════════════════════════════════════════

def test_SEC_READ_15_company_scope_in_list_work_permits_body():
    """JWT company_id 강제가 list_work_permits 함수 바디에 위치."""
    func_match = re.search(r"def list_work_permits\(", _PERMITS_SRC)
    assert func_match, "list_work_permits 함수 없음"
    func_body = _PERMITS_SRC[func_match.start():]
    assert "jwt_company_id" in func_body, \
        "list_work_permits 함수 바디에 jwt_company_id 없음"
