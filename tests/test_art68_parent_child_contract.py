"""ART68 부모-자식 입력 계약 검증 테스트.

WO-LEGAL-ADDITIONAL-INPUT-GAPA-FINAL-GATE-PATCH-003 D항 필수 테스트 (서버 경계).

검증 범위:
  - ART68 필드 없음: 기존 요청 호환 통과
  - 부모 비boolean 차단
  - 부모=false + 자식 없음: 통과
  - 부모=false + 자식 있음: 422 차단
  - 자식 단독 제출 차단
  - 부모=true + 자식 누락: 422
  - 부모=true + 자식 문자열: 422
  - 부모=true + 자식 모두 valid + 건수=0: 통과
  - 부모=true + 자식 모두 valid + 건수=2: 통과
  - 부모=true + 건수 미입력: 422
  - 부모=true + 건수 소수: 422
  - 부모=true + 건수 boolean: 422
"""
import pytest
from fastapi import HTTPException
from services.diagnosis_integrated_svc import _validate_art68_parent_child_contract

P = "contracts_construction_work_at_site"
L = "leads_and_manages_construction_execution"
R = "recontracts_received_construction_work"
C = "same_site_contracted_construction_work_count"

VALID_CHILDREN = {L: True, R: False, C: 0}


# ── 기존 요청 호환 ──────────────────────────────────────────────────
def test_no_art68_fields_passes():
    _validate_art68_parent_child_contract({})
    _validate_art68_parent_child_contract({"worker_count": 10, "contract_amount_eok": 30.0})


# ── 부모 타입 오류 ──────────────────────────────────────────────────
def test_parent_string_false_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: "false"})
    assert exc.value.status_code == 422


def test_parent_string_true_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: "true"})
    assert exc.value.status_code == 422


def test_parent_integer_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: 0})
    assert exc.value.status_code == 422


# ── 부모=false 케이스 ────────────────────────────────────────────────
def test_parent_false_no_children_passes():
    _validate_art68_parent_child_contract({P: False})


def test_parent_false_with_child_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: False, L: True})
    assert exc.value.status_code == 422


def test_parent_false_with_count_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: False, C: 0})
    assert exc.value.status_code == 422


# ── 자식 단독 제출 ───────────────────────────────────────────────────
def test_child_only_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({L: True})
    assert exc.value.status_code == 422


def test_count_only_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({C: 1})
    assert exc.value.status_code == 422


# ── 부모=true + 자식 누락/오류 ─────────────────────────────────────
def test_parent_true_missing_leads_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: True, R: False, C: 0})
    assert exc.value.status_code == 422


def test_parent_true_missing_recon_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: True, L: True, C: 0})
    assert exc.value.status_code == 422


def test_parent_true_child_string_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: True, L: "yes", R: False, C: 0})
    assert exc.value.status_code == 422


def test_parent_true_missing_count_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: True, L: True, R: False})
    assert exc.value.status_code == 422


def test_parent_true_count_float_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: True, L: True, R: False, C: 1.5})
    assert exc.value.status_code == 422


def test_parent_true_count_negative_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: True, L: True, R: False, C: -1})
    assert exc.value.status_code == 422


def test_parent_true_count_boolean_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_parent_child_contract({P: True, L: True, R: False, C: True})
    assert exc.value.status_code == 422


# ── 부모=true + 완전한 유효 입력 ────────────────────────────────────
def test_parent_true_count_zero_passes():
    _validate_art68_parent_child_contract({P: True, **VALID_CHILDREN})


def test_parent_true_count_two_passes():
    _validate_art68_parent_child_contract({P: True, L: False, R: True, C: 2})


def test_parent_true_all_false_with_zero_passes():
    _validate_art68_parent_child_contract({P: True, L: False, R: False, C: 0})
