"""WO-AUTH-DIAG-BE-001 백엔드 검증 테스트 스위트.

BE-AUTH-01~07: 회원가입·로그인·OAuth·보상삭제 계약
BE-SEC-01~08:  users 보안·company scope·admin 게이트
BE-FD-01~06:   무료진단 공식 진입점·C10 영속성

운영 DB/네트워크 불사용 — 소스 계약(inspect.getsource) + 단위 로직 검증.
"""
from __future__ import annotations

import inspect
import os

import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

from fastapi import HTTPException


# ═══════════════════════════════════════════════════════════════════
# BE-AUTH: 회원가입·로그인·OAuth·보상삭제
# ═══════════════════════════════════════════════════════════════════

def test_BE_AUTH_01_register_creates_active_user():
    """FIX-D: register 시 status_code='ACTIVE' + is_active=True 로 생성."""
    import routers.auth as auth
    src = inspect.getsource(auth.register)
    assert '"status_code": "ACTIVE"' in src or "'status_code': 'ACTIVE'" in src, \
        "register 가 ACTIVE 상태로 생성하지 않는다"
    assert '"is_active": True' in src or "'is_active': True" in src, \
        "register 가 is_active=True 로 생성하지 않는다"


def test_BE_AUTH_02_register_compensation_delete_on_insert_fail():
    """FIX-B: public.users INSERT 실패 시 auth user 를 delete_user 로 보상삭제."""
    import routers.auth as auth
    src = inspect.getsource(auth.register)
    assert "delete_user" in src, \
        "register 보상삭제(auth.admin.delete_user)가 소스에 없다"
    assert "auth_id" in src, \
        "register 보상삭제에 auth_id 변수가 없다"


def test_BE_AUTH_03_login_active_user_passes_status_gate():
    """login 이 ACTIVE + is_active=True 를 성공 경로로 처리."""
    import routers.auth as auth
    src = inspect.getsource(auth.login)
    assert "is_active" in src, "login select 에 is_active 컬럼이 없다"
    assert "ACTIVE" in src, "login 에 ACTIVE 상태 검증이 없다"


def test_BE_AUTH_04_login_pending_user_raises_403():
    """PENDING 계정 login 시도 → 403 (ACCOUNT_PENDING_APPROVAL)."""
    import routers.auth as auth
    src = inspect.getsource(auth.login)
    assert "PENDING" in src, "login 이 PENDING 상태를 차단하지 않는다"
    assert "ACCOUNT_PENDING_APPROVAL" in src, \
        "login 에 ACCOUNT_PENDING_APPROVAL 에러 코드가 없다"


def test_BE_AUTH_05_get_current_user_requires_active_gate():
    """get_current_user 가 _require_active_account 를 호출해 ACTIVE/is_active 를 강제."""
    import routers.auth as auth
    src = inspect.getsource(auth.get_current_user)
    assert "_require_active_account" in src, \
        "get_current_user 가 _require_active_account 를 호출하지 않는다"


def test_BE_AUTH_06_require_active_account_blocks_pending():
    """_require_active_account: PENDING → 403 ACCOUNT_PENDING_APPROVAL."""
    import routers.auth as auth
    with pytest.raises(HTTPException) as exc:
        auth._require_active_account({"status_code": "PENDING", "is_active": False})
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "ACCOUNT_PENDING_APPROVAL"


def test_BE_AUTH_07_ensure_user_new_row_created_active():
    """FIX-D: ensure_user 가 신규 행 생성 시 status_code='ACTIVE' + is_active=True."""
    import routers.auth as auth
    src = inspect.getsource(auth.ensure_user)
    assert '"status_code": "ACTIVE"' in src or "'status_code': 'ACTIVE'" in src, \
        "ensure_user 신규 행 생성에 ACTIVE 가 없다"
    assert '"is_active": True' in src or "'is_active': True" in src, \
        "ensure_user 신규 행 생성에 is_active=True 가 없다"


# ═══════════════════════════════════════════════════════════════════
# BE-SEC: users 보안·company scope·admin 게이트
# ═══════════════════════════════════════════════════════════════════

def test_BE_SEC_01_users_router_has_require_admin():
    """SECURITY-BLOCKER-01: users.py 에 _require_admin 함수가 정의되어 있다."""
    import routers.users as users
    assert hasattr(users, "_require_admin"), \
        "users.py 에 _require_admin 이 없다"


def test_BE_SEC_02_users_require_admin_checks_role_001():
    """_require_admin 이 role_code != '001' 이면 403 을 발생시킨다."""
    import routers.users as users
    from unittest.mock import MagicMock
    with pytest.raises(HTTPException) as exc:
        users._require_admin({"role_code": "002"})
    assert exc.value.status_code == 403


def test_BE_SEC_03_users_require_admin_passes_for_role_001():
    """_require_admin 이 role_code='001' 이면 예외 없이 통과."""
    import routers.users as users
    result = users._require_admin({"role_code": "001"})
    assert result["role_code"] == "001"


def test_BE_SEC_04_all_users_endpoints_use_require_admin():
    """users.py 의 모든 라우트 핸들러가 _require_admin Depends 를 사용한다."""
    import routers.users as users
    src = inspect.getsource(users)
    handler_sigs = [
        "def get_users(", "def create_user(", "def get_user(",
        "def update_user(", "def delete_user(", "def update_user_status(",
        "def update_user_role(", "def get_user_factories(",
    ]
    for sig in handler_sigs:
        assert "_require_admin" in src, \
            f"users.py 가 _require_admin 을 전혀 사용하지 않는다 (sig={sig})"
    count = src.count("Depends(_require_admin)")
    assert count >= 8, \
        f"users.py 엔드포인트 8개 모두 Depends(_require_admin) 필요, 현재 {count}개"


def test_BE_SEC_05_company_users_list_accepts_factory_id_query():
    """company_users.py GET /me/company/users 가 factory_id 쿼리 파라미터를 받는다."""
    import routers.company_users as cu
    src = inspect.getsource(cu.list_users)
    assert "factory_id" in src, \
        "list_users 에 factory_id 파라미터가 없다"
    assert "Query" in src, \
        "list_users 에 Query import 가 없다"


def test_BE_SEC_06_company_users_list_validates_factory_ownership():
    """GET /me/company/users?factory_id=x 는 다른 회사 factory_id 를 거부한다."""
    import routers.company_users as cu
    src = inspect.getsource(cu.list_users)
    assert "FACTORY_OUT_OF_SCOPE" in src, \
        "list_users 에 FACTORY_OUT_OF_SCOPE 검증이 없다"
    assert "company_id" in src, \
        "list_users factory 검증에 company_id 비교가 없다"


def test_BE_SEC_07_anonymous_diagnosis_admin_has_require_admin():
    """SECURITY-BLOCKER: anonymous_diagnosis_admin.py 에 _require_admin 이 있다."""
    import routers.anonymous_diagnosis_admin as ada
    assert hasattr(ada, "_require_admin"), \
        "anonymous_diagnosis_admin.py 에 _require_admin 이 없다"


def test_BE_SEC_08_all_admin_anon_diag_endpoints_use_require_admin():
    """anonymous_diagnosis_admin.py 의 모든 admin 엔드포인트가 _require_admin 을 사용."""
    import routers.anonymous_diagnosis_admin as ada
    src = inspect.getsource(ada)
    count = src.count("Depends(_require_admin)")
    assert count >= 5, \
        f"anonymous_diagnosis_admin.py admin 엔드포인트 5개 모두 _require_admin 필요, 현재 {count}개"
    # expire-stale 도 포함 검증
    expire_src = inspect.getsource(ada.expire_stale_records)
    assert "_require_admin" in expire_src, \
        "expire_stale_records 에 _require_admin 이 없다 (unauthenticated 접근 가능)"


# ═══════════════════════════════════════════════════════════════════
# BE-FD: 무료진단 공식 진입점·C10 영속성
# ═══════════════════════════════════════════════════════════════════

def test_BE_FD_01_official_free_entry_is_run_leg():
    """OFFICIAL FREE ENTRY = POST /diagnosis/run-leg (diagnosis_integrated_leg.py)."""
    import routers.diagnosis_integrated_leg as dil
    src = inspect.getsource(dil)
    assert 'prefix="/diagnosis"' in src or "prefix = '/diagnosis'" in src, \
        "diagnosis_integrated_leg router prefix 가 /diagnosis 가 아니다"
    assert "run-leg" in src, \
        "POST /diagnosis/run-leg 경로가 소스에 없다"


def test_BE_FD_02_run_leg_uses_optional_auth():
    """POST /diagnosis/run-leg 는 비로그인 허용 (get_current_user_optional)."""
    import routers.diagnosis_integrated_leg as dil
    src = inspect.getsource(dil.run_diagnosis_leg)
    assert "get_current_user_optional" in src, \
        "run_diagnosis_leg 가 optional auth 를 사용하지 않는다"


def test_BE_FD_03_leg_pipeline_enabled_gate():
    """LEG_PIPELINE_ENABLED 가 False 이면 503 을 반환한다."""
    import routers.diagnosis_integrated_leg as dil
    src = inspect.getsource(dil._run_leg_impl)
    assert "LEG_PIPELINE_ENABLED" in src, \
        "_run_leg_impl 에 LEG_PIPELINE_ENABLED 게이트가 없다"
    assert "503" in src, \
        "_run_leg_impl 에 503 응답이 없다"


def test_BE_FD_04_leg_failure_returns_502_no_tai_fallback():
    """LEG 실패 시 TAI fallback 없이 502 반환."""
    import routers.diagnosis_integrated_leg as dil
    src = inspect.getsource(dil._run_step1_via_leg)
    assert "502" in src, "_run_step1_via_leg 에 502 응답이 없다"
    # TAI fallback 미존재 확인 (문서 + 소스)
    assert "fallback" not in src.lower() or "없음" in src or "no" in src.lower(), \
        "_run_step1_via_leg 에 TAI fallback 경로가 있다"


def test_BE_FD_05_result_saved_to_anonymous_diagnosis_results():
    """C10 영속성: run_diagnosis 가 anonymous_diagnosis_results 에 저장."""
    import services.diagnosis_integrated_svc as svc
    src = inspect.getsource(svc)
    assert "anonymous_diagnosis_results" in src, \
        "diagnosis_integrated_svc 가 anonymous_diagnosis_results 테이블을 사용하지 않는다"


def test_BE_FD_06_engine_version_is_leg_runtime_v3():
    """C10 영속성: engine_version='leg-runtime-v3' 로 저장."""
    import routers.diagnosis_integrated_leg as dil
    src = inspect.getsource(dil)
    assert "leg-runtime-v3" in src, \
        "diagnosis_integrated_leg 에 engine_version=leg-runtime-v3 가 없다"
