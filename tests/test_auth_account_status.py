"""WP-A · ACTIVE ACCOUNT GATE — auth 단위테스트 (WO-SAFE-COMPANY-ACCESS-001).

_require_active_account 헬퍼 + login/get_current_user 게이트 + worker OTP 회귀.
운영 DB/네트워크 불사용, 순수 유닛(FakeSupabase 없이 헬퍼 위주).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from fastapi import HTTPException
import routers.auth as auth


# ────────────────────────────────────────────────────────────────────
# A01~A05 : _require_active_account 헬퍼 계약
# ────────────────────────────────────────────────────────────────────
def test_A01_active_and_is_active_passes():
    """ACTIVE + is_active=True → 통과 (예외 없음)."""
    auth._require_active_account({"status_code": "ACTIVE", "is_active": True})


def test_A02_pending_raises_403_with_code():
    with pytest.raises(HTTPException) as e:
        auth._require_active_account({"status_code": "PENDING", "is_active": False})
    assert e.value.status_code == 403
    d = e.value.detail
    assert isinstance(d, dict) and d.get("code") == "ACCOUNT_PENDING_APPROVAL"


def test_A03_inactive_raises_403_with_code():
    with pytest.raises(HTTPException) as e:
        auth._require_active_account({"status_code": "INACTIVE", "is_active": False})
    assert e.value.status_code == 403
    assert e.value.detail["code"] == "ACCOUNT_INACTIVE"


def test_A04_active_but_is_active_false_still_blocked():
    """DB drift 방어 : status=ACTIVE 인데 is_active=false 면 여전히 차단."""
    with pytest.raises(HTTPException) as e:
        auth._require_active_account({"status_code": "ACTIVE", "is_active": False})
    assert e.value.status_code == 403
    assert e.value.detail["code"] == "ACCOUNT_INACTIVE"


def test_A05_suspended_deleted_raises_403():
    for st in ("SUSPENDED", "DELETED"):
        with pytest.raises(HTTPException) as e:
            auth._require_active_account({"status_code": st, "is_active": False})
        assert e.value.status_code == 403
        assert e.value.detail["code"] == f"ACCOUNT_{st}"


# ────────────────────────────────────────────────────────────────────
# A06~A07 : login 로직 소스 계약 — PENDING 도 차단, is_active 조건 포함
# ────────────────────────────────────────────────────────────────────
def test_A06_login_source_includes_is_active_column_and_pending_block():
    """login 이 select 에 is_active 를 포함하고, PENDING 도 차단하도록 갱신되었음을 소스 grep."""
    import inspect
    src = inspect.getsource(auth.login)
    assert "is_active" in src, "login select 에 is_active 컬럼이 없다"
    assert '"PENDING"' in src or "'PENDING'" in src, \
        "login 이 PENDING 상태를 게이트 하지 않는다"
    assert "ACCOUNT_PENDING_APPROVAL" in src, \
        "login 에서 PENDING 응답 코드 문자열이 없다"


# ────────────────────────────────────────────────────────────────────
# A08 : get_current_user 도 ACTIVE gate 를 실행
# ────────────────────────────────────────────────────────────────────
def test_A07_get_current_user_source_calls_require_active_account():
    """get_current_user 가 users row 취득 직후 _require_active_account 를 호출."""
    import inspect
    src = inspect.getsource(auth.get_current_user)
    assert "_require_active_account" in src, \
        "get_current_user 가 _require_active_account 를 호출하지 않는다"


# ────────────────────────────────────────────────────────────────────
# A08 : worker OTP 회귀 — verify-otp 자동생성 user 는 ACTIVE / is_active=True 로 저장
# ────────────────────────────────────────────────────────────────────
def test_A08_verify_otp_creates_user_active_and_is_active_true():
    """auth 소스에서 worker OTP 자동생성 user insert 시 status_code='ACTIVE' + is_active=True.
    ACTIVE 게이트가 도입되어도 worker 는 로그인 가능 (regression)."""
    import inspect
    src = inspect.getsource(auth)
    # verify-otp 경로에서 status_code=ACTIVE 지정 (grep · 문자열 리터럴)
    assert '"status_code": "ACTIVE"' in src or "'status_code': 'ACTIVE'" in src, \
        "auth 소스에 worker OTP 자동생성 status_code=ACTIVE 지정이 없다 (worker OTP 회귀 위험)"
    # is_active True 지정 (verify-otp 자동생성 결과)
    assert '"is_active": True' in src or "'is_active': True" in src, \
        "auth 소스에 is_active=True 지정이 없다 (worker OTP 회귀 위험)"
