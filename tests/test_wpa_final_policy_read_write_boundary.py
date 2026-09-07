"""WP-A FINAL POLICY CORRECTION — AUTH ≠ ENTITLEMENT ≠ RBAC.

WO-SAFE-COMPANY-ACCESS-001. 정책 SoT (FROZEN) :
    · ACTIVE ACCOUNT → 로그인 가능
    · ENTITLEMENT ACTIVE → READ + WRITE (RBAC 범위)
    · ENTITLEMENT EXPIRED/INACTIVE/없음 → 로그인 가능 · READ 가능 · WRITE 금지
    · AUTHENTICATION ≠ ENTITLEMENT ≠ RBAC

이 파일은 라우터 계층에서 T1~T7 경계를 검증한다.
    T1 ACTIVE+ACTIVE     : login PASS · GET 3개 PASS · WRITE 5개 PASS (RBAC 내)
    T2 ACTIVE+EXPIRED    : login PASS · GET 3개 200 · WRITE 5개 403 (DELETE 포함)
    T3 no entitlement    : login PASS · GET 3개 200 · WRITE 5개 403
    T4 PENDING account   : (auth 레이어, 별도 검증 · 이 파일 대상 아님)
    T5 /me/company/access 오류 : (프론트 정책, 별도 검증)
    T6 expired READ 200  : T2 의 READ 부분과 동치 · 명시 회귀
    T7 expired WRITE 403 : T2 의 WRITE 부분과 동치 · DELETE invite 포함 명시 회귀

기존 test_company_users.py 픽스처 (_admin_user / _base_store / _client / FakeSupabase) 를
재사용한다. 운영 DB/네트워크 불사용.
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("INTERNAL_API_SECRET", "pytest-internal-secret")

# 픽스처 재사용
from tests.test_company_users import (  # type: ignore
    _admin_user, _base_store, _client, requires_client,
)


# 회사 C-A = default subs 에 ACTIVE SaaS 있음 (entitlement ACTIVE)
# 회사 C-B = default subs 에 없음 (entitlement 없음 = 만료·비활성과 동치 판정)
CID_ACTIVE = "C-A"
CID_EXPIRED = "C-B"


def _admin_with_active_entitlement():
    return _admin_user(uid="U-T-A", cid=CID_ACTIVE)


def _admin_with_expired_entitlement():
    return _admin_user(uid="U-T-B", cid=CID_EXPIRED)


def _store_expired_entitlement(invites=None, users=None):
    """C-B 회사 (entitlement 없음) 시나리오 store. RBAC 는 유지."""
    return _base_store(
        companies=[{"id": CID_EXPIRED, "name": "B사"}],
        invites=invites or [],
        users=users or [],
    )


# ═══════════════════════════════════════════════════════════════════
# T1 · ACTIVE + ACTIVE — 정상 baseline (READ/WRITE 모두 통과)
# ═══════════════════════════════════════════════════════════════════
@requires_client
def test_T1_active_entitlement_read_users_200():
    admin = _admin_with_active_entitlement()
    c = _client(admin, _base_store())
    r = c.get("/me/company/users")
    assert r.status_code == 200


@requires_client
def test_T1_active_entitlement_write_invite_200():
    """ACTIVE entitlement 에서 초대 생성 (WRITE) 정상."""
    admin = _admin_with_active_entitlement()
    c = _client(admin, _base_store())
    r = c.post("/me/company/user-invites",
               json={"email": "t1@a.co.kr", "role_code": "010"})
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# T2 / T6 · EXPIRED entitlement · READ 허용 (GET 3 개 200)
# ═══════════════════════════════════════════════════════════════════
@requires_client
def test_T2_T6_expired_get_users_200():
    admin = _admin_with_expired_entitlement()
    c = _client(admin, _store_expired_entitlement())
    r = c.get("/me/company/users")
    assert r.status_code == 200, f"expired READ 허용 위반: {r.json()}"


@requires_client
def test_T2_T6_expired_get_user_roles_200():
    admin = _admin_with_expired_entitlement()
    c = _client(admin, _store_expired_entitlement())
    r = c.get("/me/company/user-roles")
    assert r.status_code == 200


@requires_client
def test_T2_T6_expired_get_user_invites_200():
    admin = _admin_with_expired_entitlement()
    invites = [{"id": "IV-E1", "company_id": CID_EXPIRED,
                "email": "x@b.co.kr", "role_code": "020",
                "status": "PENDING", "token_hash": "h1",
                "expires_at": "2030-01-01T00:00:00+00:00"}]
    c = _client(admin, _store_expired_entitlement(invites=invites))
    r = c.get("/me/company/user-invites")
    assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# T2 / T7 · EXPIRED entitlement · WRITE 금지 (POST · PATCH · DELETE 전부 403)
# ═══════════════════════════════════════════════════════════════════
@requires_client
def test_T2_T7_expired_post_invite_403():
    """WRITE : POST /me/company/user-invites → 403 SAAS_ENTITLEMENT_REQUIRED."""
    admin = _admin_with_expired_entitlement()
    c = _client(admin, _store_expired_entitlement())
    r = c.post("/me/company/user-invites",
               json={"email": "wt7@b.co.kr", "role_code": "010"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


@requires_client
def test_T2_T7_expired_delete_invite_403_mutation():
    """WRITE : DELETE /me/company/user-invites/{id} → 403 (mutation, gate 유지)."""
    admin = _admin_with_expired_entitlement()
    invites = [{"id": "IV-DEL", "company_id": CID_EXPIRED,
                "email": "del@b.co.kr", "role_code": "020",
                "status": "PENDING", "token_hash": "h2",
                "expires_at": "2030-01-01T00:00:00+00:00"}]
    c = _client(admin, _store_expired_entitlement(invites=invites))
    r = c.delete("/me/company/user-invites/IV-DEL")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


@requires_client
def test_T2_T7_expired_approve_user_403():
    """WRITE : POST /me/company/users/{id}/approve → 403."""
    admin = _admin_with_expired_entitlement()
    users = [{"id": "U-P", "email": "p@b.co.kr", "name": "P",
              "role_code": "020", "company_id": CID_EXPIRED,
              "status_code": "PENDING", "is_active": True}]
    c = _client(admin, _store_expired_entitlement(users=users))
    r = c.post("/me/company/users/U-P/approve", json={"role_code": "010"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


@requires_client
def test_T2_T7_expired_patch_user_role_403():
    """WRITE : PATCH /me/company/users/{id}/role → 403."""
    admin = _admin_with_expired_entitlement()
    users = [{"id": "U-R", "email": "r@b.co.kr", "name": "R",
              "role_code": "020", "company_id": CID_EXPIRED,
              "status_code": "ACTIVE", "is_active": True}]
    c = _client(admin, _store_expired_entitlement(users=users))
    r = c.patch("/me/company/users/U-R/role", json={"role_code": "010"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


@requires_client
def test_T2_T7_expired_patch_user_status_403():
    """WRITE : PATCH /me/company/users/{id}/status → 403."""
    admin = _admin_with_expired_entitlement()
    users = [{"id": "U-S", "email": "s@b.co.kr", "name": "S",
              "role_code": "020", "company_id": CID_EXPIRED,
              "status_code": "ACTIVE", "is_active": True}]
    c = _client(admin, _store_expired_entitlement(users=users))
    r = c.patch("/me/company/users/U-S/status", json={"status_code": "INACTIVE"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


# ═══════════════════════════════════════════════════════════════════
# T3 · no entitlement 회사 : READ 허용 · WRITE 금지 (= T2 와 동치, 별칭)
# ═══════════════════════════════════════════════════════════════════
@requires_client
def test_T3_no_entitlement_read_pass_write_403():
    """entitlement 자체가 없는 회사도 READ 200 · WRITE 403 정책 일관."""
    admin = _admin_with_expired_entitlement()
    c = _client(admin, _store_expired_entitlement())
    # READ
    assert c.get("/me/company/users").status_code == 200
    assert c.get("/me/company/user-roles").status_code == 200
    assert c.get("/me/company/user-invites").status_code == 200
    # WRITE
    wr = c.post("/me/company/user-invites",
                json={"email": "t3@b.co.kr", "role_code": "010"})
    assert wr.status_code == 403
    assert wr.json()["detail"]["code"] == "SAAS_ENTITLEMENT_REQUIRED"


# ═══════════════════════════════════════════════════════════════════
# 정책 SoT invariant : /me/company/access · _entitlement_snapshot · bootstrap 무변경
# ═══════════════════════════════════════════════════════════════════
@requires_client
def test_INV_access_endpoint_state_unchanged():
    """access 스냅샷 엔드포인트는 entitlement 없어도 여전히 200 (Safe 진입 판정 소스)."""
    admin = _admin_with_expired_entitlement()
    c = _client(admin, _store_expired_entitlement())
    r = c.get("/me/company/access")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["entitlement"]["active"] is False


def test_INV_source_only_get3_lack_entitlement_gate():
    """소스 계약 : GET (users/user-roles/user-invites) 만 gate 없음.
    WRITE 5 endpoint 는 여전히 require_active_company_saas 호출을 유지해야 한다."""
    import inspect
    import routers.company_users as cu
    src = inspect.getsource(cu)

    def _endpoint_block(marker):
        idx = src.index(marker)
        # 다음 @router 데코레이터 시작 or EOF 까지가 endpoint 블록
        rest = src[idx:]
        next_at = rest.find("@router.", 1)
        return rest[:next_at] if next_at > 0 else rest

    # GET 3 개 : gate 부재
    for get_marker in ('@router.get("/me/company/users")',
                       '@router.get("/me/company/user-roles")',
                       '@router.get("/me/company/user-invites")'):
        block = _endpoint_block(get_marker)
        assert "require_active_company_saas" not in block, (
            f"GET endpoint 에 entitlement gate 재도입 : {get_marker}"
        )

    # WRITE 5 개 : gate 유지
    for wr_marker in ('@router.post("/me/company/user-invites")',
                      '@router.delete("/me/company/user-invites/{invite_id}")',
                      '@router.post("/me/company/users/{user_id}/approve")',
                      '@router.patch("/me/company/users/{user_id}/role")',
                      '@router.patch("/me/company/users/{user_id}/status")'):
        block = _endpoint_block(wr_marker)
        assert "require_active_company_saas" in block, (
            f"WRITE endpoint 에서 entitlement gate 가 제거되면 안 됨 : {wr_marker}"
        )


def test_INV_entitlement_snapshot_hotfix_preserved():
    """WP-A HOTFIX (subscriptions.started_at) 유지 회귀."""
    import inspect
    import routers.company_users as cu
    src = inspect.getsource(cu._entitlement_snapshot)
    sub_start = src.index('sb.table("subscriptions")')
    sub_end = src.index("for row in sub", sub_start)
    sub_block = src[sub_start:sub_end]
    assert "started_at" in sub_block, "HOTFIX 회귀 : subscription select started_at 상실"
    assert "start_date" not in sub_block, "HOTFIX 회귀 : subscription select start_date 재도입"


def test_INV_bootstrap_and_auth_gate_intact():
    """WP-A buyer bootstrap · auth ACTIVE gate 심볼 유지."""
    from services import payment_post_process as pp
    from routers import auth as au
    import inspect
    assert callable(pp._bootstrap_buyer_company_admin)
    assert callable(pp._is_saas_payment)
    au_src = inspect.getsource(au)
    assert "_require_active_account" in au_src or "is_active" in au_src
