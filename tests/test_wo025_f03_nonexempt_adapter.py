"""WO025-F03 — fc001_permit_manufacture_or_use_nonexempt canonical_adapter tests.

P:  H8(콜타르피치) MANUFACTURE_OR_USE → True (APPLICABLE)
N1: 석면(미등재 key) → 생략(UNKNOWN)
N2: 베릴륨(H4)만 → 생략(UNKNOWN) — exempt 처리
M:  H4 + H8 MOU → True (H8에 의한 것)
U:  허가대상 물질 handling_mode_codes=None → 생략(UNKNOWN)
X1: H8 STORAGE_TRANSPORT only (MOU 없음) → 생략(UNKNOWN)
R:  기존 fc001_permit_manufacture_or_use 회귀 0
F:  _MATERIAL_ONLY_FIELDS — form_data 직접 주입 차단
"""
import pytest
from services.material_source.canonical_adapter import project_material_fc001_facts
from services.canonical.materialization import canonical_applicability, _MATERIAL_ONLY_FIELDS
from clients.leg_runtime_client import _LEG_INPUT_FIELDS

KEY_H4 = "ISHL-ENF-ART88-0088001-P-H4"   # 베릴륨 — exempt
KEY_H8 = "ISHL-ENF-ART88-0088001-P-H8"   # 콜타르피치 휘발물 — non-exempt
KEY_ASBESTOS_FAKE = "ASBESTOS-NOT-IN-CATALOG"  # 카탈로그 미등재


def _row(key, modes):
    return {"is_active": True, "material_master_key": key, "handling_mode_codes": modes}


# ---------------------------------------------------------------------------
# P: non-exempt permit + MANUFACTURE_OR_USE → True
# ---------------------------------------------------------------------------

def test_p_nonexempt_mou_true():
    rows = [_row(KEY_H8, ["MANUFACTURE_OR_USE"])]
    result = project_material_fc001_facts(rows)
    assert result.get("fc001_permit_manufacture_or_use_nonexempt") is True


# ---------------------------------------------------------------------------
# N1: 석면만 (카탈로그 미등재) → UNKNOWN (생략)
# ---------------------------------------------------------------------------

def test_n1_asbestos_only_unknown():
    rows = [_row(KEY_ASBESTOS_FAKE, ["MANUFACTURE_OR_USE"])]
    result = project_material_fc001_facts(rows)
    assert "fc001_permit_manufacture_or_use_nonexempt" not in result


# ---------------------------------------------------------------------------
# N2: 베릴륨(H4)만 → UNKNOWN (생략) — exempt key
# ---------------------------------------------------------------------------

def test_n2_beryllium_only_unknown():
    rows = [_row(KEY_H4, ["MANUFACTURE_OR_USE"])]
    result = project_material_fc001_facts(rows)
    assert "fc001_permit_manufacture_or_use_nonexempt" not in result


# ---------------------------------------------------------------------------
# M: 베릴륨 + H8 MOU → True (H8에 의한 것)
# ---------------------------------------------------------------------------

def test_m_beryllium_plus_nonexempt_true():
    rows = [
        _row(KEY_H4, ["MANUFACTURE_OR_USE"]),
        _row(KEY_H8, ["MANUFACTURE_OR_USE"]),
    ]
    result = project_material_fc001_facts(rows)
    assert result.get("fc001_permit_manufacture_or_use_nonexempt") is True


# ---------------------------------------------------------------------------
# U: 허가대상 물질 handling_mode_codes=None → UNKNOWN (생략)
# ---------------------------------------------------------------------------

def test_u_null_mode_unknown():
    rows = [_row(KEY_H8, None)]
    result = project_material_fc001_facts(rows)
    assert "fc001_permit_manufacture_or_use_nonexempt" not in result


# ---------------------------------------------------------------------------
# X1: H8 STORAGE_TRANSPORT만 (MANUFACTURE_OR_USE 없음) → UNKNOWN (생략)
# ---------------------------------------------------------------------------

def test_x1_storage_only_unknown():
    rows = [_row(KEY_H8, ["STORAGE_TRANSPORT"])]
    result = project_material_fc001_facts(rows)
    assert "fc001_permit_manufacture_or_use_nonexempt" not in result


# ---------------------------------------------------------------------------
# R: 기존 fc001_permit_manufacture_or_use 회귀 — H8 MOU에서 True 유지
# ---------------------------------------------------------------------------

def test_r_regression_existing_permit_field():
    rows = [_row(KEY_H8, ["MANUFACTURE_OR_USE"])]
    result = project_material_fc001_facts(rows)
    assert result.get("fc001_permit_manufacture_or_use") is True


# ---------------------------------------------------------------------------
# F: _MATERIAL_ONLY_FIELDS — form_data 직접 주입 차단
# ---------------------------------------------------------------------------

def test_f_material_only_field_in_constant():
    assert "fc001_permit_manufacture_or_use_nonexempt" in _MATERIAL_ONLY_FIELDS


def test_f_form_data_injection_blocked():
    source = {
        "fc001_permit_manufacture_or_use_nonexempt": True,
    }
    result = canonical_applicability(source)
    assert "fc001_permit_manufacture_or_use_nonexempt" not in result


def test_f_leg_input_fields_contains_nonexempt():
    assert "fc001_permit_manufacture_or_use_nonexempt" in _LEG_INPUT_FIELDS


# ---------------------------------------------------------------------------
# Additional: empty rows → UNKNOWN
# ---------------------------------------------------------------------------

def test_empty_rows_unknown():
    result = project_material_fc001_facts([])
    assert "fc001_permit_manufacture_or_use_nonexempt" not in result


def test_inactive_row_ignored():
    rows = [{"is_active": False, "material_master_key": KEY_H8,
             "handling_mode_codes": ["MANUFACTURE_OR_USE"]}]
    result = project_material_fc001_facts(rows)
    assert "fc001_permit_manufacture_or_use_nonexempt" not in result
