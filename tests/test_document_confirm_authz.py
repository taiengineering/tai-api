"""WP-DOCUMENT-ARCH-05B-B1-CORR-01 — authorize_confirm tests (submitter-as-confirmer).

정책 정본: Confirm 권한 = 제출자 identity(submitted_by == current_user.id).
role_code 는 판정 기준이 아니다. ownership consistency 는 유지.
"""

from services.document_confirm_authz import authorize_confirm, ConfirmAuthResult


USER = "11111111-1111-1111-1111-111111111111"
OTHER = "99999999-9999-9999-9999-999999999999"
COMPANY_A = "aaaaaaaa-0001-0001-0001-000000000001"
COMPANY_B = "bbbbbbbb-0002-0002-0002-000000000002"
FACTORY_1 = "ffffffff-0001-0001-0001-000000000001"
FACTORY_2 = "ffffffff-0002-0002-0002-000000000002"
DOC = "dddddddd-0001-0001-0001-000000000001"


def user(role_code="014", company_id=COMPANY_A, factory_id=None, uid=USER):
    return {"id": uid, "role_code": role_code, "company_id": company_id, "factory_id": factory_id}


def doc(submitted_by=USER, company_id=COMPANY_A, factory_id=None):
    return {"id": DOC, "submitted_by": submitted_by,
            "company_id": company_id, "factory_id": factory_id}


def _allow(r):
    assert isinstance(r, ConfirmAuthResult) and r.allowed, repr(r)
    assert r.confirmed_by == USER


def _deny(r, status):
    assert isinstance(r, ConfirmAuthResult) and not r.allowed, repr(r)
    assert r.http_status == status, "expected %s got %s (%s)" % (status, r.http_status, r.reason)


# ── A1~A5: 다양한 role, 본인이 제출 → 모두 ALLOW (role 무관) ────────────────
def test_A1_worker_014_self_allow():
    _allow(authorize_confirm(current_user=user(role_code="014"), document=doc()))

def test_A2_safety_012_self_allow():
    _allow(authorize_confirm(current_user=user(role_code="012"), document=doc()))

def test_A3_supervisor_013_self_allow():
    _allow(authorize_confirm(current_user=user(role_code="013"), document=doc()))

def test_A4_manager_011_self_allow():
    _allow(authorize_confirm(current_user=user(role_code="011"), document=doc()))

def test_A5_admin_001_self_allow():
    _allow(authorize_confirm(current_user=user(role_code="001"), document=doc()))


# ── A6~A8: 다른 사람이 제출 → 403 (role 무관) ────────────────────────
def test_A6_admin_001_other_submitter_403():
    _deny(authorize_confirm(current_user=user(role_code="001"), document=doc(submitted_by=OTHER)), 403)

def test_A7_manager_011_other_submitter_403():
    _deny(authorize_confirm(current_user=user(role_code="011"), document=doc(submitted_by=OTHER)), 403)

def test_A8_worker_014_other_submitter_403():
    _deny(authorize_confirm(current_user=user(role_code="014"), document=doc(submitted_by=OTHER)), 403)


# ── A9: submitted_by NULL → 409 ────────────────────────────────────
def test_A9_submitted_by_null_409():
    _deny(authorize_confirm(current_user=user(), document=doc(submitted_by=None)), 409)


# ── A10: actor spoof → 403 ─────────────────────────────────────
def test_A10_actor_spoof_403():
    _deny(authorize_confirm(current_user=user(), document=doc(), actor_id=OTHER), 403)


# ── A11: cross-company → 404 ─────────────────────────────────
def test_A11_cross_company_404():
    # 제출자 본인이지만 사용자 회사(A)와 문서 회사(B)가 다름 → 존재 은닉 404
    _deny(authorize_confirm(current_user=user(company_id=COMPANY_A),
                            document=doc(company_id=COMPANY_B)), 404)


# ── A12: factory mismatch → 404 ───────────────────────────────
def test_A12_factory_mismatch_404():
    _deny(authorize_confirm(current_user=user(company_id=COMPANY_A, factory_id=FACTORY_1),
                            document=doc(company_id=COMPANY_A, factory_id=FACTORY_2),
                            factory_company_id=COMPANY_A), 404)


# ── A13: company/factory metadata conflict → 404 ────────────────────
def test_A13_ownership_conflict_404():
    # 문서 company_id(A)와 factory의 소유회사(B)가 충돌 → 404
    _deny(authorize_confirm(current_user=user(company_id=COMPANY_A, factory_id=FACTORY_1),
                            document=doc(company_id=COMPANY_A, factory_id=FACTORY_1),
                            factory_company_id=COMPANY_B), 404)


# ── A14: ownership unresolved → 404 ─────────────────────────────
def test_A14_ownership_unresolved_404():
    # 문서에 company_id 없음 + factory_id도 없음 → 소유 판정 불능 404
    _deny(authorize_confirm(current_user=user(company_id=COMPANY_A),
                            document=doc(company_id=None, factory_id=None)), 404)


# ── A15: role_code None/임의값이라도 identity+ownership 정상이면 ALLOW ──────
def test_A15_role_code_none_allow():
    _allow(authorize_confirm(current_user=user(role_code=None), document=doc()))

def test_A15b_role_code_arbitrary_allow():
    _allow(authorize_confirm(current_user=user(role_code="ZZ9"), document=doc()))


# ── 보강: 인증 없음 → 401 ─────────────────────────────────────
def test_auth_missing_401():
    _deny(authorize_confirm(current_user=None, document=doc()), 401)

def test_auth_no_id_401():
    _deny(authorize_confirm(current_user={"role_code": "014"}, document=doc()), 401)


# ── 보강: 문서 없음 → 404 ──────────────────────────────────
def test_document_missing_404():
    _deny(authorize_confirm(current_user=user(), document=None), 404)


# ── 보강: user company 없음 → 403 (fail-closed) ─────────────────────
def test_user_no_company_403():
    _deny(authorize_confirm(current_user=user(company_id=None), document=doc()), 403)


# ── 보강: factory-level 문서 + user factory 없음 → 403 (fail-closed) ────────
def test_user_no_factory_factory_doc_403():
    _deny(authorize_confirm(current_user=user(company_id=COMPANY_A, factory_id=None),
                            document=doc(company_id=COMPANY_A, factory_id=FACTORY_1),
                            factory_company_id=COMPANY_A), 403)


# ── 보강: company-level 문서(factory None) + factory 일치 불요 → ALLOW ──────
def test_company_level_doc_allow():
    _allow(authorize_confirm(current_user=user(company_id=COMPANY_A, factory_id=FACTORY_1),
                             document=doc(company_id=COMPANY_A, factory_id=None)))


# ── 보강: actor_id == current_user.id → 허용 ────────────────────────
def test_actor_matches_allow():
    _allow(authorize_confirm(current_user=user(), document=doc(), actor_id=USER))
