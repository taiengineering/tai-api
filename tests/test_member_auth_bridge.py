# WO-CST-PAID-MEMBER-RUNTIME-BRIDGE-006 (CORRECTION-02): verified member → diagnosis_auth_log 복원.
# production 저장 규약: users.identity_ci = SHA256(원문 CI), diagnosis_auth_log.ci_hash = SHA256(원문 CI).
# → resolver 는 identity_ci 를 재해시하지 않고 그대로 ci_hash 와 비교(double-hash 금지).
# mock 이 eq(col,val) 를 실제 필터하여 계약을 진짜 검증한다.
import hashlib
import pytest
from fastapi import HTTPException
from services import diagnosis_integrated_svc as _svc

CI_HASH = "a3f5" + "0" * 60  # users.identity_ci 와 diagnosis_auth_log.ci_hash 는 동일한 SHA256(원문 CI)
MEMBER = {"id": "u1", "identity_verified": True, "identity_ci": CI_HASH}  # 이미 hashed


def _sup(rows):
    class _T:
        def __init__(s, n): s.n = n; s._f = {}
        def select(s, *a, **k): return s
        def eq(s, col, val): s._f[col] = val; return s
        def limit(s, *a, **k): return s
        def execute(s):
            r = rows
            for c, v in s._f.items():
                r = [x for x in r if str(x.get(c)) == str(v)]
            return type("R", (), {"data": r})()
    class _S:
        def table(s, n): return _T(n)
    return _S()


def _row(ci_hash=CI_HASH, linked="u1", status="ACTIVE", rid="a1"):
    return {"id": rid, "ci_hash": ci_hash, "status": status, "linked_user_id": linked,
            "name": "n", "phone": "p", "free_count": 0, "free_limit": 3}


def test_member_exact_one_direct_hash_match_pass():
    row = _svc.resolve_member_auth_log(_sup([_row()]), MEMBER)
    assert row["id"] == "a1"


def test_member_double_hash_regression():
    rehashed = hashlib.sha256(CI_HASH.encode("utf-8")).hexdigest()
    row = _svc.resolve_member_auth_log(_sup([_row(ci_hash=CI_HASH)]), MEMBER)
    assert row["ci_hash"] == CI_HASH and row["ci_hash"] != rehashed


def test_member_zero_prior_authlog_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([]), MEMBER)
    assert e.value.status_code == 401


def test_member_multi_match_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row(rid="a1"), _row(rid="a2")]), MEMBER)
    assert e.value.status_code == 401


def test_member_wrong_linked_user_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row(linked="u2")]), MEMBER)
    assert e.value.status_code == 401


def test_member_wrong_ci_hash_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row(ci_hash="different")]), MEMBER)
    assert e.value.status_code == 401


def test_member_inactive_status_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row(status="EXPIRED")]), MEMBER)
    assert e.value.status_code == 401


def test_member_not_verified_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row()]), {"id": "u1", "identity_verified": False, "identity_ci": CI_HASH})
    assert e.value.status_code == 403


def test_member_no_ci_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row()]), {"id": "u1", "identity_verified": True, "identity_ci": ""})
    assert e.value.status_code == 403


def test_member_none_user_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row()]), None)
    assert e.value.status_code == 401


# ── CORRECTION-02 BREAK-1: member fallback paid-only gate (run_diagnosis 레벨) ──
class _RunSup:
    def __init__(s, authrows): s._a = authrows
    def table(s, n):
        rows = s._a if n == "diagnosis_auth_log" else []
        class _T:
            def __init__(t): t._f = {}
            def select(t, *a, **k): return t
            def eq(t, c, v): t._f[c] = v; return t
            def limit(t, *a, **k): return t
            def insert(t, r): t._p = r; return t
            def update(t, *a, **k): return t
            def execute(t):
                r = rows
                for c, v in t._f.items():
                    r = [x for x in r if str(x.get(c)) == str(v)]
                return type("R", (), {"data": r})()
        return _T()


def test_break1_member_free_intent_blocked():
    # 로그인 verified member + auth_token 없음 + payment_ref 없음 → member resolver 미진입 → 401
    from schemas.diagnosis_integrated import DiagnosisRunBody
    b = DiagnosisRunBody(sector="CONSTRUCTION")  # auth_token None, payment_ref None
    sup = _RunSup([_row()])
    with pytest.raises(HTTPException) as e:
        _svc.run_diagnosis(sup, b, run_step1_func=lambda *a, **k: {"status": "success", "data": {}},
            auto_tier_func=lambda *a, **k: "CONSTRUCTION_X", build_partial_func=lambda f: {},
            now_func=lambda: "t", paid_tier_prices={}, free_tier_codes={"CONSTRUCTION_FREE"},
            engine_version="t", current_user=MEMBER)
    assert e.value.status_code == 401  # paid context 없으면 member fallback 차단
