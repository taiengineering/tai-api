"""WO-AUTH-REGISTER-FIX-001 — register / ensure-user ACTIVE 상태 계약 테스트.

T1: 일반 register → public.users status_code=ACTIVE, is_active=True, identity_verified=True
T2: 일반 register 후 login gate → ACTIVE+is_active=True 이면 토큰 발급 경로 통과
T3: public.users INSERT 실패 → 신규 auth.users 보상 삭제 실행 (정확히 auth_id만)
T4: social ensure-user 신규 생성 → ACTIVE, is_active=True
T5: social ensure-user 기존 사용자 → 기존 row 반환, 상태 변경 없음

Production DB/네트워크 불사용 — mock 전용.
"""
from __future__ import annotations

import hashlib
import os
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

import routers.auth as auth_mod
from routers.auth import register, ensure_user, RegisterRequest


# ──────────────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

def _make_supabase(*, phone_exists=False, email_exists=False, ci_exists=False,
                   ia_status="SUCCESS", user_ci="FAKE_CI_VALUE",
                   insert_ok=True, auth_id="auth-uuid-001"):
    """register 경로 mock supabase 생성."""
    sb = MagicMock()

    def _table_chain(table_name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.limit.return_value = t
        t.update.return_value = t
        t.insert.return_value = t

        if table_name == "users":
            def _execute_users():
                r = MagicMock()
                # select 호출 여부에 따라 분기 — insert vs select 는 insert() 체인에서 판단
                r.data = []
                return r
            t.execute.return_value = MagicMock(data=[])

        elif table_name == "inicis_auth_requests":
            ia_row = {"status": ia_status, "user_ci": user_ci,
                      "user_name": "홍길동", "user_phone": "01012345678", "user_birthday": "19900101"}
            t.execute.return_value = MagicMock(data=[ia_row] if ia_status == "SUCCESS" else [])

        elif table_name == "diagnosis_auth_log":
            t.execute.return_value = MagicMock(data=[])

        else:
            t.execute.return_value = MagicMock(data=[])

        return t

    sb.table.side_effect = _table_chain

    # phone/email/ci 중복 체크를 순서대로 처리하기 위해 side_effect 재구성
    call_results = []
    # call 순서: phone check, email check, ci check(ia), ci_dup check, users insert
    phone_res  = MagicMock(data=[{"id": "x"}] if phone_exists  else [])
    email_res  = MagicMock(data=[{"id": "x"}] if email_exists  else [])
    ia_res     = MagicMock(data=[{
        "status": ia_status, "user_ci": user_ci,
        "user_name": "홍길동", "user_phone": "01012345678", "user_birthday": "19900101",
    }] if ia_status == "SUCCESS" else [])
    ci_dup_res = MagicMock(data=[{"id": "x"}] if ci_exists else [])

    # inserted user row
    inserted_user = {
        "id": "user-uuid-001", "auth_id": auth_id, "email": "test@example.com",
        "phone": "01012345678", "name": "홍길동", "status_code": "ACTIVE", "is_active": True,
        "identity_verified": True,
    }
    insert_res = MagicMock(data=[inserted_user] if insert_ok else [])
    if not insert_ok:
        insert_res = None  # INSERT 실패를 예외로 시뮬레이션

    sb._call_seq = [phone_res, email_res, ia_res, ci_dup_res]
    sb._insert_ok = insert_ok
    sb._inserted_user = inserted_user
    sb._auth_id = auth_id

    # auth.sign_up mock
    auth_user = MagicMock()
    auth_user.id = auth_id
    sb.auth.sign_up.return_value = MagicMock(user=auth_user, session=MagicMock(access_token="tok"))
    sb.auth.admin = MagicMock()

    return sb


def _make_register_req(**kwargs):
    defaults = dict(
        name="홍길동", email="test@example.com", phone="01012345678",
        password="Password123!", mtx_id="MTX_TEST_001",
        role_code="002", company_name=None, company_type_code=None,
        business_number=None, representative_name=None, ksic_code=None,
        contact_phone=None,
    )
    defaults.update(kwargs)
    return RegisterRequest(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# T1: register → ACTIVE, is_active=True, identity_verified=True
# ──────────────────────────────────────────────────────────────────────────────
def test_T1_register_creates_active_user():
    """register 성공 시 public.users row가 ACTIVE·is_active=True·identity_verified=True로 생성된다."""
    inserted = {}

    with patch("routers.auth.get_supabase") as mock_sb_fn:
        sb = MagicMock()
        mock_sb_fn.return_value = sb

        # 중복 없음
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        # inicis_auth_requests: SUCCESS 반환
        ia_table = MagicMock()
        ia_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{
            "status": "SUCCESS", "user_ci": "CI_VALUE_ABCD",
            "user_name": "홍길동", "user_phone": "01012345678", "user_birthday": "19900101",
        }])

        user_insert_table = MagicMock()
        def capture_insert(data):
            inserted.update(data)
            user_insert_table._last_insert = data
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[{"id": "user-001", **data}])
            return m
        user_insert_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        user_insert_table.insert.side_effect = capture_insert
        user_insert_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        def table_dispatch(name):
            if name == "inicis_auth_requests":
                return ia_table
            return user_insert_table

        sb.table.side_effect = table_dispatch

        auth_user = MagicMock(); auth_user.id = "auth-001"
        sb.auth.sign_up.return_value = MagicMock(user=auth_user)

        result = register(_make_register_req())

    assert result["status"] == "success"
    assert inserted.get("status_code") == "ACTIVE", f"expected ACTIVE, got {inserted.get('status_code')}"
    assert inserted.get("is_active") is True,       f"expected True, got {inserted.get('is_active')}"
    assert inserted.get("identity_verified") is True, "identity_verified must be True"


# ──────────────────────────────────────────────────────────────────────────────
# T2: ACTIVE+is_active=True 사용자는 _require_active_account 통과
# ──────────────────────────────────────────────────────────────────────────────
def test_T2_active_user_passes_login_gate():
    """status_code=ACTIVE, is_active=True 이면 _require_active_account 예외 없음."""
    # register가 생성하는 row 그대로 gate에 전달
    user_row = {"status_code": "ACTIVE", "is_active": True}
    # 예외 없이 통과해야 함
    auth_mod._require_active_account(user_row)  # raises on failure


# ──────────────────────────────────────────────────────────────────────────────
# T3: public.users INSERT 실패 → 신규 auth.users 보상 삭제
# ──────────────────────────────────────────────────────────────────────────────
def test_T3_public_users_insert_fail_triggers_compensation():
    """public.users INSERT 예외 → supabase.auth.admin.delete_user(auth_id) 정확히 1회 호출."""
    target_auth_id = "auth-to-delete-999"
    deleted_ids = []

    with patch("routers.auth.get_supabase") as mock_sb_fn:
        sb = MagicMock()
        mock_sb_fn.return_value = sb

        # 중복 없음 (phone/email/ci 체크 모두 empty)
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        ia_table = MagicMock()
        ia_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{
            "status": "SUCCESS", "user_ci": "CI_XYZ",
            "user_name": "홍길동", "user_phone": "01012345678", "user_birthday": "19900101",
        }])

        user_table = MagicMock()
        user_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        user_table.insert.return_value.execute.side_effect = Exception("DB_ERROR")
        user_table.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        def table_dispatch(name):
            if name == "inicis_auth_requests":
                return ia_table
            return user_table

        sb.table.side_effect = table_dispatch

        auth_user = MagicMock(); auth_user.id = target_auth_id
        sb.auth.sign_up.return_value = MagicMock(user=auth_user)

        def capture_delete(uid):
            deleted_ids.append(uid)
        sb.auth.admin.delete_user.side_effect = capture_delete

        with pytest.raises(HTTPException) as exc:
            register(_make_register_req())

    assert exc.value.status_code == 500
    assert target_auth_id in deleted_ids, \
        f"compensation delete_user not called with {target_auth_id}; called with {deleted_ids}"
    assert len(deleted_ids) == 1, f"delete_user must be called exactly once, got {len(deleted_ids)}"


# ──────────────────────────────────────────────────────────────────────────────
# T4: social ensure-user 신규 생성 → ACTIVE, is_active=True
# ──────────────────────────────────────────────────────────────────────────────
def test_T4_social_ensure_user_new_creates_active():
    """소셜 신규 유저 ensure-user → ACTIVE·is_active=True 로 INSERT."""
    inserted = {}

    with patch("routers.auth._auth_user_from_token") as mock_tok, \
         patch("routers.auth.get_supabase") as mock_sb_fn:

        # auth token mock
        auth_user = MagicMock()
        auth_user.id = "social-auth-001"
        auth_user.email = "social@example.com"
        auth_user.user_metadata = {"name": "소셜유저"}
        auth_user.app_metadata = {"provider": "google"}
        sb = MagicMock()
        mock_tok.return_value = (sb, auth_user)
        mock_sb_fn.return_value = sb

        # auth_id 로 기존 row 없음, email 로도 없음
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        def capture_insert(data):
            inserted.update(data)
            m = MagicMock()
            m.execute.return_value = MagicMock(data=[{"id": "user-social-001", **data}])
            return m

        sb.table.return_value.insert.side_effect = capture_insert

        result = ensure_user(authorization="Bearer fake-token")

    assert result["status"] == "success"
    assert result["created"] is True
    assert inserted.get("status_code") == "ACTIVE",  f"expected ACTIVE, got {inserted.get('status_code')}"
    assert inserted.get("is_active") is True,         f"expected True, got {inserted.get('is_active')}"


# ──────────────────────────────────────────────────────────────────────────────
# T5: social ensure-user 기존 사용자 → 기존 row 반환, 상태 변경 없음
# ──────────────────────────────────────────────────────────────────────────────
def test_T5_social_ensure_user_existing_returns_unchanged():
    """auth_id 로 기존 row가 있으면 INSERT 없이 기존 row를 그대로 반환한다."""
    existing_row = {
        "id": "user-existing-001", "auth_id": "social-auth-002",
        "email": "existing@example.com", "status_code": "ACTIVE", "is_active": True,
    }

    with patch("routers.auth._auth_user_from_token") as mock_tok, \
         patch("routers.auth.get_supabase") as mock_sb_fn:

        auth_user = MagicMock()
        auth_user.id = "social-auth-002"
        auth_user.email = "existing@example.com"
        auth_user.user_metadata = {}
        auth_user.app_metadata = {"provider": "kakao"}
        sb = MagicMock()
        mock_tok.return_value = (sb, auth_user)
        mock_sb_fn.return_value = sb

        # auth_id 로 기존 row 반환
        sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[existing_row])

        result = ensure_user(authorization="Bearer existing-token")

    assert result["status"] == "success"
    assert result["created"] is False
    assert result["data"]["id"] == "user-existing-001"
    # INSERT가 호출되지 않았는지 확인
    sb.table.return_value.insert.assert_not_called()
