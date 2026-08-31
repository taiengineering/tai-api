# WO-CST-PAID-MEMBER-RUNTIME-BRIDGE-006: verified member → diagnosis_auth_log 복원 (auth_token 없는 유료).
# deterministic: linked_user_id=current_user.id AND ci_hash=identity_ci AND status=ACTIVE, 정확히 1건.
# 0/복수/미verified/무CI/무user 전부 fail-closed. latest/first 선택 금지.
import pytest
from fastapi import HTTPException
from services import diagnosis_integrated_svc as _svc


def _sup(rows):
    class _T:
        def __init__(s, n): s.n = n
        def select(s, *a, **k): return s
        def eq(s, *a, **k): return s
        def execute(s): return type("R", (), {"data": rows})()
    class _S:
        def table(s, n): return _T(n)
    return _S()


MEMBER = {"id": "u1", "identity_verified": True, "identity_ci": "cihash1"}


def test_member_exact_one_pass():
    sup = _sup([{"id": "a1", "ci_hash": "cihash1", "status": "ACTIVE", "linked_user_id": "u1", "free_count": 0, "free_limit": 3}])
    row = _svc.resolve_member_auth_log(sup, MEMBER)
    assert row["id"] == "a1"


def test_member_zero_match_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([]), MEMBER)
    assert e.value.status_code == 401


def test_member_multi_match_fail_closed():
    rows = [{"id": "a1", "ci_hash": "cihash1", "status": "ACTIVE", "linked_user_id": "u1"},
            {"id": "a2", "ci_hash": "cihash1", "status": "ACTIVE", "linked_user_id": "u1"}]
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup(rows), MEMBER)
    assert e.value.status_code == 401  # latest/first 금지 → 복수는 fail-closed


def test_member_not_verified_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([{"id": "a1"}]), {"id": "u1", "identity_verified": False, "identity_ci": "c"})
    assert e.value.status_code == 403


def test_member_no_ci_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([{"id": "a1"}]), {"id": "u1", "identity_verified": True, "identity_ci": ""})
    assert e.value.status_code == 403


def test_member_none_user_fail_closed():
    with pytest.raises(HTTPException) as e:
        _svc.resolve_member_auth_log(_sup([{"id": "a1"}]), None)
    assert e.value.status_code == 401
