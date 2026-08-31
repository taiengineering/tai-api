# WO-CST-PAID-MEMBER-RUNTIME-BRIDGE-006 (CORRECTION-02): verified member → diagnosis_auth_log 복원.
# mock 이 eq(col,val) 필터를 실제 적용하여 sha256 ci_hash 규약 + deterministic exact-1 을 진짜 검증한다.
import hashlib
import pytest
from fastapi import HTTPException
from services import diagnosis_integrated_svc as _svc

CI_RAW = "800101-XXXXXXX-realci"
CI_HASH = hashlib.sha256(CI_RAW.encode("utf-8")).hexdigest()
MEMBER = {"id": "u1", "identity_verified": True, "identity_ci": CI_RAW}


def _sup(rows):
    # eq(col,val) 를 실제 필터로 적용 → ci_hash/linked_user_id/status 매칭을 검증한다.
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


def test_member_exact_one_sha256_match_pass():
    # auth_log.ci_hash = sha256(identity_ci) → 매칭 1건
    row = _svc.resolve_member_auth_log(_sup([_row()]), MEMBER)
    assert row["id"] == "a1"


def test_member_raw_ci_stored_would_fail_regression():
    # BREAK-B 재현 방지: auth_log 가 원문 CI 로 저장돼 있으면 sha256 비교로 0건(fail-closed) 이어야 한다.
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row(ci_hash=CI_RAW)]), MEMBER)  # 원문 저장 → 매칭 실패
    assert e.value.status_code == 401


def test_member_zero_prior_authlog_fail_closed():
    # 회원이나 연결된 본인인증 세션(diagnosis_auth_log) 없음 → 401
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([]), MEMBER)
    assert e.value.status_code == 401


def test_member_multi_match_fail_closed():
    rows = [_row(rid="a1"), _row(rid="a2")]  # 동일 회원 sha256 매칭 2건
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup(rows), MEMBER)
    assert e.value.status_code == 401  # latest/first 금지 → 복수 fail-closed


def test_member_wrong_linked_user_fail_closed():
    # ci_hash 는 맞아도 linked_user_id 가 다른 회원 → 필터로 제외 → 0건 401
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row(linked="u2")]), MEMBER)
    assert e.value.status_code == 401


def test_member_inactive_status_fail_closed():
    # status != ACTIVE → 필터 제외 → 0건 401
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row(status="EXPIRED")]), MEMBER)
    assert e.value.status_code == 401


def test_member_not_verified_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row()]), {"id": "u1", "identity_verified": False, "identity_ci": CI_RAW})
    assert e.value.status_code == 403


def test_member_no_ci_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row()]), {"id": "u1", "identity_verified": True, "identity_ci": ""})
    assert e.value.status_code == 403


def test_member_none_user_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([_row()]), None)
    assert e.value.status_code == 401
