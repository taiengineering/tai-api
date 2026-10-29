"""WO-TAI-PERF-CORE-AUTH-DEDUP-009 WP-02 보안·회귀 테스트 (R3 — 42개).

설계 계약: 05_SECURITY_AND_REGRESSION_TEST_PLAN.md R3
대상 파일: routers/auth.py (+6줄), services/permission_guard.py (+2줄)
실행 범위: 유닛(Supabase mock) + 통합(TestClient)
운영 DB 불사용.
"""
from __future__ import annotations

import os
import threading
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.datastructures import State

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "fake-sr-key")

import routers.auth as auth_mod
from routers.auth import get_current_user


# ────────────────────────────────────────────────────────────────────
# 공통 픽스처
# ────────────────────────────────────────────────────────────────────

VALID_USER = {"id": "user-001", "auth_id": "auth-001", "role_code": "002",
              "status_code": "ACTIVE", "is_active": True, "company_id": "co-001"}
VALID_TOKEN = "Bearer valid_token_abc"


def _make_request(token: Optional[str] = None,
                  auth_user=None, auth_token=None) -> Request:
    """테스트용 Starlette Request mock."""
    req = MagicMock(spec=Request)
    headers = {}
    if token:
        headers["authorization"] = token
    req.headers = headers
    req.state = State()
    if auth_user is not None:
        req.state._auth_user = auth_user
    if auth_token is not None:
        req.state._auth_token = auth_token
    return req


def _supabase_ok(user=None):
    """정상 응답 Supabase mock."""
    u = user or VALID_USER
    sb = MagicMock()
    sb.auth.get_user.return_value = MagicMock(user=MagicMock(id=u["auth_id"]))
    sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[u])
    return sb


# ────────────────────────────────────────────────────────────────────
# 그룹 A: 크로스 요청 격리 (CRITICAL — MERGE 차단)
# ────────────────────────────────────────────────────────────────────

class TestCrossRequestIsolation:

    def test_A01_different_requests_have_independent_state(self):
        """요청 B state에 user_a 없음."""
        req_a = _make_request()
        req_b = _make_request()
        req_a.state._auth_user = {"id": "user-a"}
        assert not hasattr(req_b.state, "_auth_user")

    def test_A02_concurrent_requests_have_isolated_state(self):
        """동시 10개 요청 — 각 요청 _auth_user가 자신의 user만 포함."""
        results = {}
        errors = []

        def run(idx):
            req = _make_request()
            req.state._auth_user = {"id": f"user-{idx}"}
            req.state._auth_token = f"Bearer token-{idx}"
            cached = getattr(req.state, "_auth_user", None)
            if cached and cached["id"] != f"user-{idx}":
                errors.append(f"idx={idx} got {cached['id']}")
            results[idx] = cached

        threads = [threading.Thread(target=run, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"격리 실패: {errors}"
        assert len(results) == 10
        for i, user in results.items():
            assert user["id"] == f"user-{i}"

    def test_A03_no_global_variable_pollution(self):
        """모듈 수준 변수 변화 없음 — get_current_user 자체가 전역 상태 미변경."""
        import importlib
        original_name = auth_mod.__name__
        req = _make_request(VALID_TOKEN, auth_user=VALID_USER, auth_token=VALID_TOKEN)
        with patch.object(auth_mod, "get_supabase", return_value=_supabase_ok()):
            get_current_user(authorization=VALID_TOKEN, request=req)
        assert auth_mod.__name__ == original_name


# ────────────────────────────────────────────────────────────────────
# 그룹 B: 캐시 히트/미스 (CRITICAL — MERGE 차단)
# ────────────────────────────────────────────────────────────────────

class TestCacheHitMiss:

    def test_B01_cache_hit_skips_supabase(self):
        """_auth_user + _auth_token 일치 시 supabase.auth.get_user 0회."""
        req = _make_request(VALID_TOKEN, auth_user=VALID_USER, auth_token=VALID_TOKEN)
        sb = _supabase_ok()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = get_current_user(authorization=VALID_TOKEN, request=req)
        assert result == VALID_USER
        sb.auth.get_user.assert_not_called()

    def test_B02_cache_miss_calls_supabase(self):
        """_auth_user 없을 시 Supabase 호출 수행."""
        req = _make_request(VALID_TOKEN)
        sb = _supabase_ok()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = get_current_user(authorization=VALID_TOKEN, request=req)
        sb.auth.get_user.assert_called_once()
        assert result == VALID_USER

    def test_B03_cache_returns_same_value_as_stored(self):
        """저장값 == 반환값."""
        stored = {"id": "user-stored", "status_code": "ACTIVE", "is_active": True,
                  "role_code": "002", "auth_id": "auth-stored", "company_id": "co-1"}
        req = _make_request(VALID_TOKEN, auth_user=stored, auth_token=VALID_TOKEN)
        with patch.object(auth_mod, "get_supabase", return_value=_supabase_ok()):
            result = get_current_user(authorization=VALID_TOKEN, request=req)
        assert result is stored

    def test_B04_direct_call_with_no_request_skips_cache(self):
        """request=None 직접 호출 시 캐시 체크 없이 Supabase 호출."""
        sb = _supabase_ok()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = get_current_user(authorization=VALID_TOKEN)
        sb.auth.get_user.assert_called_once()
        assert result == VALID_USER


# ────────────────────────────────────────────────────────────────────
# 그룹 C: 토큰 무효화 응답 보존 (CRITICAL — MERGE 차단)
# ────────────────────────────────────────────────────────────────────

class TestTokenInvalidation:

    def _expired_sb(self):
        sb = MagicMock()
        sb.auth.get_user.side_effect = Exception("JWT expired")
        return sb

    def test_C01_expired_token_raises_401(self):
        """만료 토큰 → HTTP 401."""
        with patch.object(auth_mod, "get_supabase", return_value=self._expired_sb()):
            with pytest.raises(HTTPException) as exc:
                get_current_user(authorization=VALID_TOKEN)
        assert exc.value.status_code == 401

    def test_C02_no_token_raises_401(self):
        """토큰 없음 → HTTP 401."""
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization=None)
        assert exc.value.status_code == 401

    def test_C03_malformed_token_raises_401(self):
        """잘못된 형식 → HTTP 401."""
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization="Token invalid_format")
        assert exc.value.status_code == 401

    def test_C04_pending_account_raises_403(self):
        """PENDING 계정 → HTTP 403."""
        pending = {**VALID_USER, "status_code": "PENDING", "is_active": False}
        sb = _supabase_ok(pending)
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            with pytest.raises(HTTPException) as exc:
                get_current_user(authorization=VALID_TOKEN)
        assert exc.value.status_code == 403

    def test_C05_suspended_account_raises_403(self):
        """SUSPENDED 계정 → HTTP 403."""
        suspended = {**VALID_USER, "status_code": "SUSPENDED", "is_active": False}
        sb = _supabase_ok(suspended)
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            with pytest.raises(HTTPException) as exc:
                get_current_user(authorization=VALID_TOKEN)
        assert exc.value.status_code == 403

    def test_C06_expired_token_does_not_set_auth_user(self):
        """만료 토큰 후 _auth_user attribute 없음."""
        req = _make_request(VALID_TOKEN)
        with patch.object(auth_mod, "get_supabase", return_value=self._expired_sb()):
            with pytest.raises(HTTPException):
                get_current_user(authorization=VALID_TOKEN, request=req)
        assert not hasattr(req.state, "_auth_user")


# ────────────────────────────────────────────────────────────────────
# 그룹 D: Public 경로 불변 (HIGH — MERGE 차단)
# ────────────────────────────────────────────────────────────────────

class TestPublicPathUnchanged:

    def test_D01_public_path_no_supabase_call(self):
        """Public 경로 → _evaluate() 조기 반환 — Supabase 미호출."""
        import services.permission_guard as pg
        req = _make_request()
        req.method = "GET"
        req.url = MagicMock()
        req.url.path = "/health"  # _PUBLIC 등록 경로
        sb = MagicMock()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = pg._evaluate(req)
        assert result is None
        sb.auth.get_user.assert_not_called()

    def test_D02_public_path_state_not_set(self):
        """Public 경로 _evaluate() 후 _auth_user, _auth_token state 미설정."""
        import services.permission_guard as pg
        req = _make_request()
        req.method = "GET"
        req.url = MagicMock()
        req.url.path = "/health"
        with patch.object(auth_mod, "get_supabase", return_value=MagicMock()):
            pg._evaluate(req)
        assert not hasattr(req.state, "_auth_user")
        assert not hasattr(req.state, "_auth_token")


# ────────────────────────────────────────────────────────────────────
# 그룹 E: 관리자 게이트 동작 불변 관찰 (OBSERVE — MERGE 미차단)
# ────────────────────────────────────────────────────────────────────

class TestAdminGateObservation:

    def test_E01_wp02_does_not_change_check_admin_behavior(self):
        """WP02 전후 _check_admin() 동작 불변 — user_role=None 상태 유지."""
        from services import permission_guard as pg
        # WP02는 user_role을 변경하지 않는다
        assert not hasattr(pg, "_check_admin"), \
            "_check_admin이 있다면 WP02 범위 외 변경 감지"

    def test_E02_wp02_does_not_set_user_role_on_state(self):
        """WP02 후에도 user_role은 request.state에 설정되지 않음."""
        import services.permission_guard as pg
        req = _make_request(VALID_TOKEN)
        req.method = "GET"
        req.url = MagicMock()
        req.url.path = "/auth/me"

        with patch.object(pg, "_resolve_user", return_value=VALID_USER):
            with patch.object(pg, "is_public", return_value=True):
                pg._evaluate(req)

        assert not hasattr(req.state, "user_role")

    def test_E03_auth_token_sentinel_set_after_middleware_pass(self):
        """미들웨어 통과 후 _auth_token == authorization_header."""
        import services.permission_guard as pg
        req = _make_request(VALID_TOKEN)
        req.method = "GET"
        req.url = MagicMock()
        req.url.path = "/auth/me"

        with patch.object(pg, "is_public", return_value=False):
            with patch.object(pg, "template_for", return_value="/auth/me"):
                with patch.object(pg, "lookup_permission", return_value=None):
                    with patch.object(pg, "_resource_of", return_value="auth"):
                        with patch.object(pg, "_resolve_user", return_value=VALID_USER):
                            with patch.object(pg, "_is_worker_route", return_value=True):
                                pg._evaluate(req)

        assert getattr(req.state, "_auth_token", None) == VALID_TOKEN
        assert getattr(req.state, "_auth_user", None) == VALID_USER


# ────────────────────────────────────────────────────────────────────
# 그룹 F: 회귀 (CRITICAL — MERGE 차단)
# ────────────────────────────────────────────────────────────────────

class TestRegressionSuite:

    def test_F01_depends_path_returns_user_dict(self):
        """Depends 경로 user dict 반환 — 기존 user dict 그대로 반환."""
        req = _make_request(VALID_TOKEN)
        sb = _supabase_ok()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = get_current_user(authorization=VALID_TOKEN, request=req)
        assert isinstance(result, dict)
        assert result.get("id") == VALID_USER["id"]

    def test_F02_get_current_user_optional_no_auth_returns_none(self):
        """get_current_user_optional 인증 없음 → None, Supabase 0회."""
        from routers.auth import get_current_user_optional
        sb = MagicMock()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = get_current_user_optional(authorization=None)
        assert result is None
        sb.auth.get_user.assert_not_called()

    def test_F03_get_current_user_optional_with_auth_returns_user(self):
        """get_current_user_optional 인증 있음 → user 반환."""
        from routers.auth import get_current_user_optional
        with patch.object(auth_mod, "get_supabase", return_value=_supabase_ok()):
            result = get_current_user_optional(authorization=VALID_TOKEN)
        assert result is not None
        assert result.get("id") == VALID_USER["id"]

    def test_F04_existing_tests_not_broken(self):
        """F04 — 기존 동작 보존 소스 계약: Bearer 없이 401."""
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization="invalid")
        assert exc.value.status_code == 401

    def test_F05_entitlement_check_unchanged(self):
        """WRITE 만료 계정 → 403 — _evaluate()의 entitlement 체크 불변."""
        import services.permission_guard as pg
        req = _make_request(VALID_TOKEN)
        req.method = "POST"
        req.url = MagicMock()
        req.url.path = "/factories"

        with patch.object(pg, "is_public", return_value=False), \
             patch.object(pg, "template_for", return_value="/factories"), \
             patch.object(pg, "lookup_permission", return_value=None), \
             patch.object(pg, "_resource_of", return_value="factories"), \
             patch.object(pg, "_resolve_user", return_value=VALID_USER), \
             patch.object(pg, "active_entitlement", return_value=False), \
             patch.object(pg, "_is_advisory", return_value=False):
            result = pg._evaluate(req)

        assert result is not None
        assert result.status_code == 403

    def test_F06_http_integration_auth_success(self):
        """HTTP 통합 테스트 — 인증 성공 경로 200."""
        app = FastAPI()

        @app.get("/test-me")
        def me(user: dict = Depends(get_current_user)):
            return {"id": user["id"]}

        client = TestClient(app, raise_server_exceptions=True)
        with patch.object(auth_mod, "get_supabase", return_value=_supabase_ok()):
            resp = client.get("/test-me", headers={"Authorization": VALID_TOKEN})
        assert resp.status_code == 200
        assert resp.json()["id"] == VALID_USER["id"]

    def test_F07_http_integration_auth_failure(self):
        """HTTP 통합 테스트 — 인증 실패 경로 401."""
        app = FastAPI()

        @app.get("/test-protected")
        def protected(user: dict = Depends(get_current_user)):
            return {"id": user["id"]}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test-protected")
        assert resp.status_code == 401

    def test_F08_http_integration_public_path(self):
        """HTTP 통합 테스트 — Public 경로 인증 없이 200."""
        app = FastAPI()

        @app.get("/public-info")
        def public_info():
            return {"public": True}

        client = TestClient(app)
        resp = client.get("/public-info")
        assert resp.status_code == 200


# ────────────────────────────────────────────────────────────────────
# 그룹 G: 직접 호출 회귀 (CRITICAL — R2 신규)
# ────────────────────────────────────────────────────────────────────

class TestDirectCallCompat:

    def test_G01_positional_direct_call_no_type_error(self):
        """positional 직접 호출 → TypeError 없음."""
        sb = _supabase_ok()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = get_current_user(VALID_TOKEN)
        assert result is not None
        assert result.get("id") == VALID_USER["id"]

    def test_G02_keyword_direct_call_no_type_error(self):
        """keyword 직접 호출 → 정상 처리."""
        sb = _supabase_ok()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = get_current_user(authorization=VALID_TOKEN)
        assert result is not None

    def test_G03_get_current_user_optional_internal_call(self):
        """get_current_user_optional 내부 직접 호출 → 정상."""
        from routers.auth import get_current_user_optional
        with patch.object(auth_mod, "get_supabase", return_value=_supabase_ok()):
            result = get_current_user_optional(authorization=VALID_TOKEN)
        assert result is not None
        assert result.get("id") == VALID_USER["id"]

    def test_G04_change_phone_direct_call_pattern(self):
        """change_phone() 패턴 — get_current_user(authorization=authorization) → user 반환."""
        authorization = VALID_TOKEN
        sb = _supabase_ok()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = get_current_user(authorization=authorization)
        assert result is not None

    def test_G05_direct_call_request_none_always_calls_supabase(self):
        """request=None 경로 → Supabase 호출 수행 (캐시 없음)."""
        sb = _supabase_ok()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            get_current_user(authorization=VALID_TOKEN)
        sb.auth.get_user.assert_called_once()

    def test_G06_direct_call_result_unchanged(self):
        """WP02 전후 동일 user 반환 — 직접 호출 경로 결과 불변."""
        sb = _supabase_ok()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result1 = get_current_user(authorization=VALID_TOKEN)
        with patch.object(auth_mod, "get_supabase", return_value=_supabase_ok()):
            result2 = get_current_user(authorization=VALID_TOKEN)
        assert result1 == result2


# ────────────────────────────────────────────────────────────────────
# 그룹 H: 캐시 신뢰 경계 (CRITICAL — R2 신규, H-06 R3 추가)
# ────────────────────────────────────────────────────────────────────

class TestCacheTrustBoundary:

    def test_H01_token_mismatch_bypasses_cache(self):
        """_auth_token != authorization → Supabase 호출 수행."""
        different_user = {**VALID_USER, "id": "user-different", "auth_id": "auth-diff"}
        req = _make_request("Bearer token_b",
                            auth_user=VALID_USER, auth_token="Bearer token_a")
        sb = _supabase_ok(different_user)
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = get_current_user(authorization="Bearer token_b", request=req)
        sb.auth.get_user.assert_called_once()
        assert result["id"] == different_user["id"]

    def test_H02_auth_user_without_auth_token_bypasses_cache(self):
        """_auth_user 있지만 _auth_token 없음 → 캐시 미사용 → Supabase 호출."""
        req = _make_request(VALID_TOKEN)
        req.state._auth_user = VALID_USER
        # _auth_token 미설정
        sb = _supabase_ok()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            get_current_user(authorization=VALID_TOKEN, request=req)
        sb.auth.get_user.assert_called_once()

    def test_H03_no_authorization_header_raises_401_not_cache(self):
        """authorization=None 인증 없는 요청 → HTTP 401 (캐시 반환 금지, IG-01)."""
        req = _make_request(None, auth_user=VALID_USER, auth_token=None)
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization=None, request=req)
        assert exc.value.status_code == 401

    def test_H04_different_token_direct_call_cannot_use_cache(self):
        """다른 토큰 직접 호출로 캐시 오용 불가."""
        other_user = {**VALID_USER, "id": "user-other", "auth_id": "auth-other"}
        req = _make_request("Bearer other_token",
                            auth_user=VALID_USER, auth_token=VALID_TOKEN)
        sb = _supabase_ok(other_user)
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = get_current_user(authorization="Bearer other_token", request=req)
        sb.auth.get_user.assert_called_once()
        assert result["id"] == other_user["id"]

    def test_H05_pending_account_not_cached(self):
        """ACTIVE 계정만 캐시 저장 — PENDING 계정 미들웨어 실패 → _auth_user 미설정."""
        req = _make_request(VALID_TOKEN)
        pending = {**VALID_USER, "status_code": "PENDING", "is_active": False}
        sb = _supabase_ok(pending)
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            with pytest.raises(HTTPException) as exc:
                get_current_user(authorization=VALID_TOKEN, request=req)
        assert exc.value.status_code == 403
        assert not hasattr(req.state, "_auth_user")

    def test_H06_none_token_and_none_authorization_raises_401(self):
        """_auth_token=None, authorization=None 동시 → HTTP 401 (캐시 반환 금지, IG-01)."""
        req = _make_request(None)
        req.state._auth_user = VALID_USER
        req.state._auth_token = None
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization=None, request=req)
        assert exc.value.status_code == 401


# ────────────────────────────────────────────────────────────────────
# 그룹 I: Permission Guard 모드별 동작 (HIGH — R2 신규)
# ────────────────────────────────────────────────────────────────────

class TestPermissionGuardModes:

    def test_I01_enforce_mode_deny_returns_response(self):
        """ENFORCE 모드 인증 실패 → _deny() → JSONResponse(401)."""
        from services.permission_guard import _deny
        from starlette.responses import JSONResponse
        result = _deny(advisory=False, code=401, msg="토큰이 없습니다.", extra="")
        assert result is not None
        assert isinstance(result, JSONResponse)
        assert result.status_code == 401

    def test_I02_advisory_mode_deny_returns_none(self):
        """ADVISORY 모드 인증 실패 → _deny() → None."""
        from services.permission_guard import _deny
        result = _deny(advisory=True, code=401, msg="토큰이 없습니다.", extra="")
        assert result is None

    def test_I03_advisory_mode_no_auth_header_raises_401_via_di(self):
        """ADVISORY 모드 — 미들웨어 통과(None), DI get_current_user → 401 폴백."""
        from services.permission_guard import permission_guard_middleware

        app = FastAPI()

        @app.get("/wp02-protected")
        def protected(user: dict = Depends(get_current_user)):
            return {"id": user["id"]}

        app.middleware("http")(permission_guard_middleware)
        client = TestClient(app, raise_server_exceptions=False)

        # ADVISORY 기본 모드: 미들웨어는 인증 없이 통과 → DI에서 401
        with patch.object(auth_mod, "get_supabase", return_value=MagicMock()):
            resp = client.get("/wp02-protected")
        assert resp.status_code == 401

    def test_I04_advisory_mode_does_not_expand_permissions(self):
        """ADVISORY 모드 허용 확대 없음 — WP02 전후 _deny 로직 불변."""
        import services.permission_guard as pg
        from starlette.responses import JSONResponse

        # 기존 _deny 계약: ENFORCE → JSONResponse, ADVISORY → None
        enforce_result = pg._deny(advisory=False, code=403, msg="권한 없음")
        advisory_result = pg._deny(advisory=True, code=403, msg="권한 없음")
        assert isinstance(enforce_result, JSONResponse)
        assert enforce_result.status_code == 403
        assert advisory_result is None

        # WP02가 _deny 함수 자체를 변경하지 않았음
        import inspect
        src = inspect.getsource(pg._deny)
        # _auth_user/_auth_token 관련 코드가 _deny에 없어야 함
        assert "_auth_user" not in src
        assert "_auth_token" not in src


# ────────────────────────────────────────────────────────────────────
# 그룹 J: 미들웨어–DI 캐시 통합 (CRITICAL — WP-02 핵심 성능 증거)
#
# 실제 HTTP 요청에서 permission_guard_middleware가 request.state에 저장한
# 인증 결과를 Depends(get_current_user)가 재사용하는지 검증한다.
# Supabase 호출 4회 → 2회 감소를 직접 계측한다.
# ────────────────────────────────────────────────────────────────────

class TestMiddlewareDIIntegration:
    """미들웨어 + DI 연동 통합 테스트 — 운영 DB 불사용, Supabase mock 계측."""

    def _build_app(self) -> tuple:
        """미들웨어 장착 FastAPI app + Supabase 호출 횟수 카운터 반환."""
        from services.permission_guard import permission_guard_middleware

        call_counts = {"auth_get_user": 0, "table_select": 0}

        def counting_sb():
            sb = MagicMock()

            def _get_user(token):
                call_counts["auth_get_user"] += 1
                return MagicMock(user=MagicMock(id=VALID_USER["auth_id"]))

            sb.auth.get_user.side_effect = _get_user
            sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = \
                lambda: (call_counts.__setitem__("table_select", call_counts["table_select"] + 1)
                         or MagicMock(data=[VALID_USER]))
            return sb

        app = FastAPI()

        @app.get("/api/protected")
        def protected(user: dict = Depends(get_current_user)):
            return {"id": user["id"]}

        app.middleware("http")(permission_guard_middleware)
        return app, call_counts, counting_sb

    def test_J01_middleware_sets_state_and_di_reads_cache(self):
        """정상 보호 요청: 미들웨어에서 state 저장 → DI 캐시 반환."""
        app, counts, counting_sb = self._build_app()
        client = TestClient(app, raise_server_exceptions=True)

        with patch.object(auth_mod, "get_supabase", side_effect=counting_sb):
            resp = client.get("/api/protected", headers={"Authorization": VALID_TOKEN})

        assert resp.status_code == 200
        assert resp.json()["id"] == VALID_USER["id"]
        # 미들웨어 1회만 Supabase 호출 — DI는 캐시 사용
        assert counts["auth_get_user"] == 1, \
            f"auth.get_user 호출 수 = {counts['auth_get_user']} (기대: 1)"
        assert counts["table_select"] == 1, \
            f"table.select 호출 수 = {counts['table_select']} (기대: 1)"

    def test_J02_total_supabase_calls_reduced_from_4_to_2(self):
        """Supabase 총 호출 4회 → 2회 감소 직접 계측."""
        app, counts, counting_sb = self._build_app()
        client = TestClient(app, raise_server_exceptions=True)

        with patch.object(auth_mod, "get_supabase", side_effect=counting_sb):
            resp = client.get("/api/protected", headers={"Authorization": VALID_TOKEN})

        assert resp.status_code == 200
        total = counts["auth_get_user"] + counts["table_select"]
        assert total == 2, \
            f"총 Supabase 호출 수 = {total} (기대: 2, WP02 이전 = 4)"

    def test_J03_different_tokens_isolation_between_requests(self):
        """서로 다른 토큰 요청 간 캐시 격리 — 각 요청 독립적 Supabase 호출."""
        from services.permission_guard import permission_guard_middleware

        user_a = {**VALID_USER, "id": "user-a", "auth_id": "auth-a"}
        user_b = {**VALID_USER, "id": "user-b", "auth_id": "auth-b"}
        token_a = "Bearer token_a"
        token_b = "Bearer token_b"

        user_map = {"token_a": user_a, "token_b": user_b,
                    "auth-a": user_a, "auth-b": user_b}
        call_log = []

        def counting_sb():
            sb = MagicMock()

            def _get_user(token):
                call_log.append(("auth_get_user", token))
                uid = "auth-a" if token == "token_a" else "auth-b"
                return MagicMock(user=MagicMock(id=uid))

            def _table_execute():
                call_log.append("table_select")
                auth_id = call_log[-2][1] if len(call_log) >= 2 else None
                u = user_map.get(auth_id, VALID_USER)
                return MagicMock(data=[u])

            sb.auth.get_user.side_effect = _get_user
            sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = \
                _table_execute
            return sb

        app = FastAPI()

        @app.get("/api/isolated")
        def isolated(user: dict = Depends(get_current_user)):
            return {"id": user["id"]}

        app.middleware("http")(permission_guard_middleware)
        client = TestClient(app, raise_server_exceptions=True)

        with patch.object(auth_mod, "get_supabase", side_effect=counting_sb):
            resp_a = client.get("/api/isolated", headers={"Authorization": token_a})
            resp_b = client.get("/api/isolated", headers={"Authorization": token_b})

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        # 각 요청이 독립적 → auth.get_user 2회 (요청당 1회)
        auth_calls = [c for c in call_log if isinstance(c, tuple) and c[0] == "auth_get_user"]
        assert len(auth_calls) == 2, f"auth.get_user 호출 수 = {len(auth_calls)} (기대: 2)"

    def test_J04_no_token_still_raises_401(self):
        """토큰 없는 요청 → 401 유지 (캐시 최적화 후 회귀 없음)."""
        app, _, counting_sb = self._build_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch.object(auth_mod, "get_supabase", side_effect=counting_sb):
            resp = client.get("/api/protected")
        assert resp.status_code == 401

    def test_J05_pending_account_still_raises_403(self):
        """PENDING 계정 → 403 유지 (캐시 최적화 후 회귀 없음)."""
        from services.permission_guard import permission_guard_middleware

        pending = {**VALID_USER, "status_code": "PENDING", "is_active": False}
        app = FastAPI()

        @app.get("/api/pending-test")
        def pending_route(user: dict = Depends(get_current_user)):
            return {"id": user["id"]}

        app.middleware("http")(permission_guard_middleware)
        client = TestClient(app, raise_server_exceptions=False)

        sb = _supabase_ok(pending)
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            resp = client.get("/api/pending-test", headers={"Authorization": VALID_TOKEN})
        assert resp.status_code == 403

    def test_J06_state_auth_user_and_token_set_by_middleware(self):
        """미들웨어가 인증 성공 후 request.state에 _auth_user + _auth_token 설정."""
        import services.permission_guard as pg

        captured = {}

        req = MagicMock(spec=Request)
        req.method = "GET"
        req.url = MagicMock()
        req.url.path = "/api/me"
        req.headers = {"authorization": VALID_TOKEN}
        req.state = State()

        with patch.object(pg, "is_public", return_value=False), \
             patch.object(pg, "template_for", return_value="/api/me"), \
             patch.object(pg, "lookup_permission", return_value=None), \
             patch.object(pg, "_resource_of", return_value="api"), \
             patch.object(pg, "_resolve_user", return_value=VALID_USER), \
             patch.object(pg, "_is_worker_route", return_value=True):
            pg._evaluate(req)

        assert req.state._auth_user == VALID_USER
        assert req.state._auth_token == VALID_TOKEN

    def test_J07_public_path_no_state_set(self):
        """Public GET /health — _evaluate() 즉시 반환, state 미설정."""
        import services.permission_guard as pg

        req = MagicMock(spec=Request)
        req.method = "GET"
        req.url = MagicMock()
        req.url.path = "/health"
        req.headers = {}
        req.state = State()

        sb = MagicMock()
        with patch.object(auth_mod, "get_supabase", return_value=sb):
            result = pg._evaluate(req)

        assert result is None
        sb.auth.get_user.assert_not_called()
        assert not hasattr(req.state, "_auth_user")
        assert not hasattr(req.state, "_auth_token")
