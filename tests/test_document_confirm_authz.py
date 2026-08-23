"""WP-DOCUMENT-ARCH-05B-B0A — confirm authorization policy tests.

repository root 기준 실행(pytest). 순수 함수 테스트이며 DB/네트워크 접근 없음.
CASE MATRIX 전 분기를 fail-closed 로 고정한다.
"""

from services import document_confirm_authz as az
from services.document_confirm_authz import authorize_confirm, APPROVE_ROLE_CODES

USER_ID = "11111111-1111-1111-1111-111111111111"
COMPANY_A = "aaaaaaaa-0001-0001-0001-000000000001"
COMPANY_B = "bbbbbbbb-0002-0002-0002-000000000002"
FACTORY_1 = "ffffffff-0001-0001-0001-000000000001"
FACTORY_2 = "ffffffff-0002-0002-0002-000000000002"
DOC_ID = "dddddddd-0001-0001-0001-000000000001"


def user(role_code="011", company_id=COMPANY_A, factory_id=None, uid=USER_ID):
    return {"id": uid, "role_code": role_code,
            "company_id": company_id, "factory_id": factory_id}


def doc(company_id=COMPANY_A, factory_id=None, did=DOC_ID):
    return {"id": did, "company_id": company_id, "factory_id": factory_id,
            "status": "REVIEW_PENDING"}


# ── 인증 ────────────────────────────────────────────────────────────────
def test_01_no_auth_denied_401():
    r = authorize_confirm(current_user=None, document=doc(), role_scope="COMPANY")
    assert not r.allowed and r.http_status == 401


def test_02_user_without_id_denied_401():
    r = authorize_confirm(current_user={"role_code": "011"}, document=doc(),
                          role_scope="COMPANY")
    assert not r.allowed and r.http_status == 401


# ── actor_id 사칭 ────────────────────────────────────────────────────────
def test_03_actor_id_mismatch_denied_403():
    r = authorize_confirm(current_user=user(), document=doc(), role_scope="COMPANY",
                          actor_id="99999999-9999-9999-9999-999999999999")
    assert not r.allowed and r.http_status == 403
    assert "actor_id" in r.reason


def test_04_actor_id_match_allowed():
    r = authorize_confirm(current_user=user(), document=doc(), role_scope="COMPANY",
                          actor_id=USER_ID)
    assert r.allowed and r.confirmed_by == USER_ID


def test_05_actor_id_absent_uses_authenticated():
    r = authorize_confirm(current_user=user(), document=doc(), role_scope="COMPANY",
                          actor_id=None)
    assert r.allowed and r.confirmed_by == USER_ID


# ── 문서 존재 ────────────────────────────────────────────────────────────
def test_06_missing_document_404():
    r = authorize_confirm(current_user=user(), document=None, role_scope="COMPANY")
    assert not r.allowed and r.http_status == 404


# ── 권한(role) ───────────────────────────────────────────────────────────
def test_07_role_not_in_allowlist_denied_403():
    for bad_role in ("012", "013", "014", "008", "031", "002", None, ""):
        r = authorize_confirm(current_user=user(role_code=bad_role), document=doc(),
                              role_scope="COMPANY")
        assert not r.allowed and r.http_status == 403, "role %r must be denied" % bad_role


def test_08_allowlisted_roles_pass_role_gate():
    # allowlist 의 role 은 role gate 를 통과한다(scope 는 별도).
    assert APPROVE_ROLE_CODES == {"001", "011"}
    for ok_role in APPROVE_ROLE_CODES:
        scope = "ALL" if ok_role == "001" else "COMPANY"
        r = authorize_confirm(current_user=user(role_code=ok_role), document=doc(),
                              role_scope=scope)
        assert r.allowed, "role %s should pass" % ok_role


# ── data scope ───────────────────────────────────────────────────────────
def test_09_scope_all_crosses_company():
    r = authorize_confirm(current_user=user(role_code="001", company_id=COMPANY_A),
                          document=doc(company_id=COMPANY_B), role_scope="ALL")
    assert r.allowed  # ALL 은 회사 경계를 넘는다


def test_10_scope_company_same_company_allowed():
    r = authorize_confirm(current_user=user(company_id=COMPANY_A),
                          document=doc(company_id=COMPANY_A), role_scope="COMPANY")
    assert r.allowed


def test_11_scope_company_cross_company_hidden_404():
    r = authorize_confirm(current_user=user(company_id=COMPANY_A),
                          document=doc(company_id=COMPANY_B), role_scope="COMPANY")
    assert not r.allowed and r.http_status == 404  # 존재 은닉


def test_12_scope_company_unresolvable_owner_404():
    r = authorize_confirm(current_user=user(company_id=COMPANY_A),
                          document=doc(company_id=None, factory_id=None),
                          role_scope="COMPANY", factory_company_id=None)
    assert not r.allowed and r.http_status == 404  # 판정 불능 = fail-closed


def test_13_scope_company_resolved_via_factory_company():
    # doc.company_id 는 없지만 factory→company 로 소유 회사가 도출되면 판정 가능
    r = authorize_confirm(current_user=user(company_id=COMPANY_A),
                          document=doc(company_id=None, factory_id=FACTORY_1),
                          role_scope="COMPANY", factory_company_id=COMPANY_A)
    assert r.allowed
    r2 = authorize_confirm(current_user=user(company_id=COMPANY_A),
                           document=doc(company_id=None, factory_id=FACTORY_1),
                           role_scope="COMPANY", factory_company_id=COMPANY_B)
    assert not r2.allowed and r2.http_status == 404


def test_14_scope_company_user_without_company_403():
    r = authorize_confirm(current_user=user(company_id=None),
                          document=doc(company_id=COMPANY_A), role_scope="COMPANY")
    assert not r.allowed and r.http_status == 403


# ── FACTORY scope (allowlist 밖이지만 정책 자체는 검증) ───────────────────
def test_15_scope_factory_same_factory_allowed():
    # role gate 를 통과시키기 위해 allowlist 를 임시 확장하지 않고 정책 함수를
    # 직접 확인: FACTORY scope 로직은 role gate 이후에 도달하므로,
    # 여기서는 scope 로직만 보려고 allowlist 통과 role(001↔ALL 아님)이 필요.
    # 대신 정책의 FACTORY 분기를 직접 노출하기 위해 011+FACTORY 조합으로 검증한다.
    r = authorize_confirm(
        current_user=user(role_code="011", company_id=COMPANY_A, factory_id=FACTORY_1),
        document=doc(company_id=COMPANY_A, factory_id=FACTORY_1),
        role_scope="FACTORY", factory_company_id=COMPANY_A)
    assert r.allowed


def test_16_scope_factory_other_factory_same_company_404():
    r = authorize_confirm(
        current_user=user(role_code="011", company_id=COMPANY_A, factory_id=FACTORY_1),
        document=doc(company_id=COMPANY_A, factory_id=FACTORY_2),
        role_scope="FACTORY", factory_company_id=COMPANY_A)
    assert not r.allowed and r.http_status == 404  # company_scope 관례: 존재 은닉


def test_17_scope_factory_cross_company_hidden_404():
    r = authorize_confirm(
        current_user=user(role_code="011", company_id=COMPANY_A, factory_id=FACTORY_1),
        document=doc(company_id=COMPANY_B, factory_id=FACTORY_1),
        role_scope="FACTORY", factory_company_id=COMPANY_B)
    assert not r.allowed and r.http_status == 404


def test_18_scope_factory_unresolvable_factory_404():
    r = authorize_confirm(
        current_user=user(role_code="011", company_id=COMPANY_A, factory_id=FACTORY_1),
        document=doc(company_id=COMPANY_A, factory_id=None),
        role_scope="FACTORY")
    assert not r.allowed and r.http_status == 404


def test_19_scope_factory_user_without_factory_403():
    r = authorize_confirm(
        current_user=user(role_code="011", company_id=COMPANY_A, factory_id=None),
        document=doc(company_id=COMPANY_A, factory_id=FACTORY_1),
        role_scope="FACTORY", factory_company_id=COMPANY_A)
    assert not r.allowed and r.http_status == 403


# ── 미정의/위험 scope = fail-closed ──────────────────────────────────────
def test_20_undefined_or_platform_scope_denied():
    for scope in (None, "", "TEAM", "ASSIGNED", "PLATFORM", "WHATEVER"):
        r = authorize_confirm(current_user=user(role_code="011"), document=doc(),
                              role_scope=scope)
        assert not r.allowed and r.http_status == 403, "scope %r must be denied" % scope


def test_21_platform_scope_not_auto_widened_to_all():
    # PLATFORM 을 ALL 로 자동 해석하면 cross-company 승인이 뚫린다. 반드시 deny.
    r = authorize_confirm(current_user=user(role_code="001", company_id=COMPANY_A),
                          document=doc(company_id=COMPANY_B), role_scope="PLATFORM")
    assert not r.allowed and r.http_status == 403


# ── confirmed_by 는 항상 인증 사용자 ─────────────────────────────────────
def test_22_confirmed_by_is_always_authenticated_user():
    r = authorize_confirm(current_user=user(uid=USER_ID), document=doc(),
                          role_scope="COMPANY", actor_id=USER_ID)
    assert r.confirmed_by == USER_ID
    # 거부 시에는 confirmed_by 가 채워지지 않는다
    r2 = authorize_confirm(current_user=user(role_code="014"), document=doc(),
                           role_scope="COMPANY")
    assert r2.confirmed_by is None


# ── 순수성 — DB/clock/network 미접촉 ─────────────────────────────────────
def test_23_module_is_pure():
    src = open("services/document_confirm_authz.py", encoding="utf-8").read()
    for banned in ("get_supabase", "supabase", "requests", "httpx",
                   "datetime.now", "utcnow", "os.environ", "create_client"):
        assert banned not in src, "authz policy must be pure: %s" % banned


# ── ownership consistency (BLOCKER 1/2 회귀 고정) ────────────────────────
def test_24_company_and_factory_company_conflict_denied():
    # doc.company_id 와 factory→company 가 충돌하면 봉인 불가(FAIL-CLOSED)
    r = authorize_confirm(
        current_user=user(company_id=COMPANY_A),
        document=doc(company_id=COMPANY_A, factory_id=FACTORY_1),
        role_scope="COMPANY",
        factory_company_id=COMPANY_B,
    )
    assert not r.allowed and r.http_status == 404


def test_25_all_scope_cannot_seal_inconsistent_ownership():
    # 001(ALL)이라도 어긋난 ownership metadata 는 봉인 불가
    r = authorize_confirm(
        current_user=user(role_code="001"),
        document=doc(company_id=COMPANY_A, factory_id=FACTORY_1),
        role_scope="ALL",
        factory_company_id=COMPANY_B,
    )
    assert not r.allowed


def test_26_factory_scope_requires_user_company():
    r = authorize_confirm(
        current_user=user(role_code="011", company_id=None, factory_id=FACTORY_1),
        document=doc(company_id=COMPANY_A, factory_id=FACTORY_1),
        role_scope="FACTORY",
        factory_company_id=COMPANY_A,
    )
    assert not r.allowed and r.http_status == 403


def test_27_factory_scope_requires_resolved_factory_owner():
    r = authorize_confirm(
        current_user=user(role_code="011", company_id=COMPANY_A, factory_id=FACTORY_1),
        document=doc(company_id=None, factory_id=FACTORY_1),
        role_scope="FACTORY",
        factory_company_id=None,
    )
    assert not r.allowed and r.http_status == 404


def test_28_all_scope_requires_resolvable_ownership():
    # ALL 은 다른 회사 문서까지 승인 가능하지만, 소유주 자체가 없는 문서는 봉인 불가
    r = authorize_confirm(
        current_user=user(role_code="001", company_id=None, factory_id=None),
        document=doc(company_id=None, factory_id=None),
        role_scope="ALL",
    )
    assert not r.allowed
    assert r.http_status == 404
