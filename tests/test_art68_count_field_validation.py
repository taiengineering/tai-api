"""ART68 same_site_contracted_construction_work_count 정수 검증 테스트.

WO-LEGAL-ADDITIONAL-INPUT-GAPA-FINAL-CORRECTION-002 D항 필수 테스트 (서버 경계).

검증 범위:
  - 비정수 차단 (건수=1.5 → 422)
  - 음수 차단 (건수=-1 → 422)
  - 잘못된 자료형 차단 (true/문자열 → 422)
  - 정수 0 이상 허용 (건수=0, 건수=2 → pass)
  - 필드 부재(None) 허용 (기존 요청 호환)
  - 비CONSTRUCTION 섹터 무영향
"""
import pytest
from fastapi import HTTPException
from services.diagnosis_integrated_svc import _validate_art68_count_field


# ── 차단 케이스 ──────────────────────────────────────────────────────
def test_float_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_count_field({"same_site_contracted_construction_work_count": 1.5})
    assert exc.value.status_code == 422


def test_negative_integer_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_count_field({"same_site_contracted_construction_work_count": -1})
    assert exc.value.status_code == 422


def test_boolean_true_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_count_field({"same_site_contracted_construction_work_count": True})
    assert exc.value.status_code == 422


def test_boolean_false_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_count_field({"same_site_contracted_construction_work_count": False})
    assert exc.value.status_code == 422


def test_string_digit_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_art68_count_field({"same_site_contracted_construction_work_count": "3"})
    assert exc.value.status_code == 422


def test_nan_via_float_is_rejected():
    import math
    with pytest.raises(HTTPException) as exc:
        _validate_art68_count_field({"same_site_contracted_construction_work_count": float("nan")})
    assert exc.value.status_code == 422


# ── 허용 케이스 ──────────────────────────────────────────────────────
def test_zero_is_allowed():
    _validate_art68_count_field({"same_site_contracted_construction_work_count": 0})


def test_positive_integer_is_allowed():
    _validate_art68_count_field({"same_site_contracted_construction_work_count": 2})
    _validate_art68_count_field({"same_site_contracted_construction_work_count": 100})


def test_field_absent_none_is_allowed():
    """None은 미입력(기존 요청 호환). 차단 없음."""
    _validate_art68_count_field({"same_site_contracted_construction_work_count": None})


def test_field_key_missing_is_allowed():
    """키 자체 없음 = 기존 요청. 차단 없음."""
    _validate_art68_count_field({})


def test_unrelated_fields_do_not_trigger():
    _validate_art68_count_field({"worker_count": 1.5, "contract_amount_eok": "bad"})
