"""WO-MEMTAI-00S — register 가입 보안 경계 테스트.

T01: role_code=001/031/032/033 주입 → 고권한 저장 0건; 서버가 role 결정
T02: 기존 회사 사업자번호 → 409, auth.sign_up 호출 0건, company_id 자동부여 0건
T03: 신규 회사 생성 성공 → server_role=_ROLE_COMPANY_ADMIN("002"), company_id 부여
T04: 신규 회사 생성 실패 → server_role=_ROLE_NO_COMPANY("014"), company_id=None;
     users INSERT 실패 시 auth 보상 삭제
T05: 중복 phone/email/CI → 기존 차단 로직 유지 (회귀 없음)
T06: company_name 없음 → server_role=_ROLE_NO_COMPANY("014"), company_id=None
T07: _PRIVILEGED_ROLES 상수 검사

Production DB/네트워크 불사용 — mock 전용.
"""
from __future__ import annotations

import hashlib
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from routers.auth import register, RegisterRequest, _ROLE_COMPANY_ADMIN, _ROLE_NO_COMPANY, _PRIVILEGED_ROLES


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_CI = "FAKE_CI_MEMTAI_XYZ"
_DEFAULT_CI_HASH = hashlib.sha256(_DEFAULT_CI.encode()).hexdigest()


def _req(**kwargs) -> RegisterRequest:
    defaults = dict(
        name="홍길동", email="new@example.com", phone="01011112222",
        password="Password123!", mtx_id="MTX_TEST_MEMTAI",
        role_code="002",
        company_name=None, company_type_code=None,
        business_number=None, representative_name=None, ksic_code=None,
        contact_phone=None,
    )
    defaults.update(kwargs)
    return RegisterRequest(**defaults)


def _ia_row(ci=_DEFAULT_CI):
    return {
        "status": "SUCCESS", "user_ci": ci,
        "user_name": "홍길동", "user_phone": "01011112222", "user_birthday": "19900101",
    }


def _empty():
    return MagicMock(data=[])


def _make_supabase(
    *,
    phone_dup: bool = False,
    email_dup: bool = False,
    ci_dup: bool = False,
    company_dup: bool = False,
    company_insert_ok: bool = True,
    user_insert_raises: bool = False,
    captured_user_insert: dict | None = None,
    auth_id: str = "auth-new-001",
):
    """
    register() 경로를 위한 최소 mock Supabase 클라이언트.

    각 테이블은 단일 MagicMock 오브젝트로 캐싱되어,
    sb.table("users") 호출이 반복되어도 동일 오브젝트를 반환한다.
    그 덕분에 select().execute() 호출 순서 카운터가 올바르게 작동한다.
    """
    sb = MagicMock()

    # auth.sign_up mock
    _auth_user = MagicMock()
    _auth_user.id = auth_id
    sb.auth.sign_up.return_value = MagicMock(user=_auth_user)
    sb.auth.admin = MagicMock()

    # ── users 테이블 ─────────────────────────────────────
    users_t = MagicMock()
    users_t.select.return_value = users_t
    users_t.eq.return_value = users_t
    users_t.neq.return_value = users_t
    users_t.limit.return_value = users_t
    users_t.update.return_value = MagicMock(
        eq=MagicMock(return_value=MagicMock(execute=MagicMock(return_value=_empty())))
    )

    # select execute 순서: 1=phone, 2=email, 3=CI
    _select_seq = [
        MagicMock(data=[{"id": "x"}] if phone_dup else []),
        MagicMock(data=[{"id": "x"}] if email_dup else []),
        MagicMock(data=[{"id": "x"}] if ci_dup else []),
    ]
    _select_idx = [0]

    def _users_execute():
        idx = _select_idx[0]
        _select_idx[0] += 1
        if idx < len(_select_seq):
            return _select_seq[idx]
        return _empty()

    users_t.execute.side_effect = _users_execute

    # users insert
    _inserted_user = {
        "id": "user-new-001", "auth_id": auth_id,
        "email": "new@example.com", "phone": "01011112222",
        "name": "홍길동", "status_code": "ACTIVE", "is_active": True,
    }

    def _users_insert(data):
        if captured_user_insert is not None:
            captured_user_insert.update(data)
        if user_insert_raises:
            raise Exception("DB_INSERT_FAIL")
        m = MagicMock()
        m.execute.return_value = MagicMock(data=[{"id": "user-new-001", **data}])
        return m

    users_t.insert.side_effect = _users_insert

    # ── inicis_auth_requests 테이블 ───────────────────────
    ia_t = MagicMock()
    ia_t.select.return_value = ia_t
    ia_t.eq.return_value = ia_t
    ia_t.limit.return_value = ia_t
    ia_t.execute.return_value = MagicMock(data=[_ia_row()])
    ia_t.update.return_value = MagicMock(
        eq=MagicMock(return_value=MagicMock(execute=MagicMock(return_value=_empty())))
    )

    # ── companies 테이블 ─────────────────────────────────
    companies_t = MagicMock()
    companies_t.select.return_value = companies_t
    companies_t.eq.return_value = companies_t
    companies_t.limit.return_value = companies_t
    # select(bn dup check)
    companies_t.execute.return_value = MagicMock(
        data=[{"id": "co-existing-001"}] if company_dup else []
    )
    # insert(신규 회사)
    if company_insert_ok:
        companies_t.insert.return_value = MagicMock(
            execute=MagicMock(return_value=MagicMock(data=[{"id": "co-new-001"}]))
        )
    else:
        companies_t.insert.return_value = MagicMock(
            execute=MagicMock(return_value=MagicMock(data=[]))  # 빈 응답 = 실패
        )

    # ── diagnosis_auth_log 테이블 ────────────────────────
    diag_t = MagicMock()
    diag_t.update.return_value = MagicMock(
        eq=MagicMock(return_value=MagicMock(execute=MagicMock(return_value=_empty())))
    )

    _table_cache = {
        "users": users_t,
        "inicis_auth_requests": ia_t,
        "companies": companies_t,
        "diagnosis_auth_log": diag_t,
    }

    sb.table.side_effect = lambda name: _table_cache.get(name, MagicMock())
    return sb


# ─────────────────────────────────────────────────────────────────────────────
# T01: 고권한 role_code 주입 차단
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("injected_role", list(_PRIVILEGED_ROLES) + ["002"])
def test_T01_role_injection_blocked(injected_role):
    """role_code를 어떤 값으로 보내도 서버 결정 역할만 저장된다. 고권한 코드가 users에 저장되면 안 된다."""
    captured = {}

    with patch("routers.auth.get_supabase") as mock_sb:
        mock_sb.return_value = _make_supabase(
            company_insert_ok=True,
            captured_user_insert=captured,
        )
        result = register(_req(
            role_code=injected_role,
            company_name="신규회사",
            business_number="1234567890",
        ))

    assert result["status"] == "success"
    stored = captured.get("role_code")
    assert stored not in _PRIVILEGED_ROLES, \
        f"고권한 {stored!r}가 저장됨 — 차단되어야 함"
    assert stored in (_ROLE_COMPANY_ADMIN, _ROLE_NO_COMPANY), \
        f"서버 결정 역할이 아님: {stored!r}"


# ─────────────────────────────────────────────────────────────────────────────
# T02: 기존 회사 사업자번호 → 409, auth.sign_up 호출 0건
# ─────────────────────────────────────────────────────────────────────────────

def test_T02a_existing_company_returns_409():
    """사업자번호가 기존 회사와 일치하면 409를 반환한다."""
    with patch("routers.auth.get_supabase") as mock_sb:
        sb = _make_supabase(company_dup=True)
        mock_sb.return_value = sb

        with pytest.raises(HTTPException) as exc:
            register(_req(company_name="기존회사", business_number="1234567890"))

    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == "COMPANY_ALREADY_EXISTS"


def test_T02b_existing_company_no_auth_signup_called():
    """409 경로에서 auth.sign_up이 호출되지 않는다."""
    with patch("routers.auth.get_supabase") as mock_sb:
        sb = _make_supabase(company_dup=True)
        mock_sb.return_value = sb

        with pytest.raises(HTTPException):
            register(_req(company_name="기존회사", business_number="1234567890"))

    sb.auth.sign_up.assert_not_called()


def test_T02c_existing_company_no_user_insert():
    """409 경로에서 users INSERT가 호출되지 않는다."""
    users_inserted = []

    with patch("routers.auth.get_supabase") as mock_sb:
        sb = _make_supabase(company_dup=True)
        # users INSERT를 가로채 캡처
        users_t = sb.table.side_effect("users")

        def capture(data):
            users_inserted.append(data)
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[{"id": "u", **data}])
            return m

        users_t.insert.side_effect = capture
        mock_sb.return_value = sb

        with pytest.raises(HTTPException):
            register(_req(company_name="기존회사", business_number="1234567890"))

    assert len(users_inserted) == 0, "409 경로에서 users INSERT가 호출됨"


# ─────────────────────────────────────────────────────────────────────────────
# T03: 신규 회사 생성 성공 → _ROLE_COMPANY_ADMIN, company_id 부여
# ─────────────────────────────────────────────────────────────────────────────

def test_T03_new_company_success_assigns_company_admin():
    """신규 회사 생성 성공 시 role_code=_ROLE_COMPANY_ADMIN("002"), company_id가 부여된다."""
    captured = {}

    with patch("routers.auth.get_supabase") as mock_sb:
        mock_sb.return_value = _make_supabase(
            company_dup=False,
            company_insert_ok=True,
            captured_user_insert=captured,
        )
        result = register(_req(company_name="신규회사", business_number="9876543210"))

    assert result["status"] == "success"
    assert captured.get("role_code") == _ROLE_COMPANY_ADMIN, \
        f"신규 회사 성공 시 role={_ROLE_COMPANY_ADMIN!r} 기대, got {captured.get('role_code')!r}"
    assert captured.get("company_id") == "co-new-001", \
        f"company_id 미부여: {captured.get('company_id')!r}"


# ─────────────────────────────────────────────────────────────────────────────
# T04a: 신규 회사 생성 실패 → _ROLE_NO_COMPANY, company_id=None
# ─────────────────────────────────────────────────────────────────────────────

def test_T04a_company_creation_fail_assigns_no_company_role():
    """회사 생성 결과가 빈 응답이면 role_code=_ROLE_NO_COMPANY, company_id=None으로 가입된다."""
    captured = {}

    with patch("routers.auth.get_supabase") as mock_sb:
        mock_sb.return_value = _make_supabase(
            company_dup=False,
            company_insert_ok=False,
            captured_user_insert=captured,
        )
        result = register(_req(company_name="신규회사", business_number="1111111111"))

    assert result["status"] == "success"
    assert captured.get("role_code") == _ROLE_NO_COMPANY, \
        f"회사 생성 실패 시 role={_ROLE_NO_COMPANY!r} 기대, got {captured.get('role_code')!r}"
    assert captured.get("company_id") is None, \
        f"company_id=None 기대, got {captured.get('company_id')!r}"


# ─────────────────────────────────────────────────────────────────────────────
# T04b: users INSERT 실패 → auth 보상 삭제
# ─────────────────────────────────────────────────────────────────────────────

def test_T04b_users_insert_fail_triggers_compensation_delete():
    """public.users INSERT 실패 시 auth.users 보상 삭제가 1회 호출된다."""
    target_auth_id = "auth-to-delete-00s"
    deleted = []

    with patch("routers.auth.get_supabase") as mock_sb:
        sb = _make_supabase(
            user_insert_raises=True,
            auth_id=target_auth_id,
        )
        sb.auth.admin.delete_user.side_effect = lambda uid: deleted.append(uid)
        mock_sb.return_value = sb

        with pytest.raises(HTTPException) as exc:
            register(_req())

    assert exc.value.status_code == 500
    assert target_auth_id in deleted, f"보상 삭제 미실행; deleted={deleted}"
    assert len(deleted) == 1, f"delete_user 1회 기대, got {len(deleted)}"


# ─────────────────────────────────────────────────────────────────────────────
# T05: 중복 phone / email / CI → 기존 차단 유지
# ─────────────────────────────────────────────────────────────────────────────

def test_T05a_duplicate_phone_blocked():
    with patch("routers.auth.get_supabase") as mock_sb:
        mock_sb.return_value = _make_supabase(phone_dup=True)
        with pytest.raises(HTTPException) as exc:
            register(_req())
    assert exc.value.status_code == 400
    assert "휴대폰" in str(exc.value.detail)


def test_T05b_duplicate_email_blocked():
    with patch("routers.auth.get_supabase") as mock_sb:
        mock_sb.return_value = _make_supabase(email_dup=True)
        with pytest.raises(HTTPException) as exc:
            register(_req())
    assert exc.value.status_code == 400
    assert "이메일" in str(exc.value.detail)


def test_T05c_duplicate_ci_blocked():
    with patch("routers.auth.get_supabase") as mock_sb:
        mock_sb.return_value = _make_supabase(ci_dup=True)
        with pytest.raises(HTTPException) as exc:
            register(_req())
    assert exc.value.status_code == 400
    assert "본인인증 중복" in str(exc.value.detail)


# ─────────────────────────────────────────────────────────────────────────────
# T06: company_name 없음 → _ROLE_NO_COMPANY, company_id=None
# ─────────────────────────────────────────────────────────────────────────────

def test_T06_no_company_name_assigns_no_company_role():
    """company_name 없이 가입하면 role_code=_ROLE_NO_COMPANY("014"), company_id=None."""
    captured = {}

    with patch("routers.auth.get_supabase") as mock_sb:
        mock_sb.return_value = _make_supabase(captured_user_insert=captured)
        result = register(_req(company_name=None, business_number=None))

    assert result["status"] == "success"
    assert captured.get("role_code") == _ROLE_NO_COMPANY, \
        f"미소속 가입 role={_ROLE_NO_COMPANY!r} 기대, got {captured.get('role_code')!r}"
    assert captured.get("company_id") is None


# ─────────────────────────────────────────────────────────────────────────────
# T07: 상수 검사
# ─────────────────────────────────────────────────────────────────────────────

def test_T07_privileged_roles_constant():
    """_PRIVILEGED_ROLES에 최고관리자(001)가 포함되고, 가입 역할은 포함되지 않는다."""
    assert "001" in _PRIVILEGED_ROLES
    assert _ROLE_COMPANY_ADMIN not in _PRIVILEGED_ROLES, \
        f"{_ROLE_COMPANY_ADMIN!r}는 가입 가능 역할이므로 _PRIVILEGED_ROLES에 없어야 함"
    assert _ROLE_NO_COMPANY not in _PRIVILEGED_ROLES, \
        f"{_ROLE_NO_COMPANY!r}는 가입 가능 역할이므로 _PRIVILEGED_ROLES에 없어야 함"
