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
    # identity_ci(=SHA256) == diagnosis_auth_log.ci_hash → 재해시 없이 직접 매칭 1건
    row = _svc.resolve_member_auth_log(_sup([_row()]), MEMBER)
    assert row["id"] == "a1"


def test_member_double_hash_regression():
    # double-hash 방어: resolver 가 identity_ci 를 재해시하면 SHA256(SHA256(CI)) 가 되어 절대 매칭 안 됨.
    # auth_log 에는 정상 규약(ci_hash=CI_HASH)만 존재. resolver 가 재해시하면 0건이 되어 이 PASS 가 깨진다.
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
    assert e.value.status_code == 401  # latest/first 금지


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
