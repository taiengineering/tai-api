"""WO-E2E-OBJ-SEM-001-REV1-PATCH2 — integration test.

실제 run_diagnosis 경로 재현: form_data → canonical_applicability(drop work_types) →
_build_unified_step1_body(seed work_types) → build_unified_leg_input(expansion) → 2 domain bool.
canonical filter 후에도 SOURCE 값이 domain boolean 으로 도달함을 검증 (PATCH2 BLOCKER 해소).
"""
from services.diagnosis_integrated_svc import _build_unified_step1_body
from services.canonical.leg_input_contract import build_unified_leg_input


class _Body:
    """DiagnosisRunBody stub: form_data + 접근 속성."""
    def __init__(self, form_data):
        self.form_data = form_data
    def __getattr__(self, name):
        return None  # 없는 속성은 None (getattr(body, key, None) 호환)


def _run(form_data, inp):
    """실제 경로 재현: inp = canonical 필터 결과(work_types 없음), body.form_data = 원본."""
    return _build_unified_step1_body(
        engine_sector="CONSTRUCTION",
        inp=inp,                    # canonical_applicability 통과분 (work_types drop됨)
        workers=10,
        body=_Body(form_data),      # 원본 form_data (work_types 존재)
        factory_id=None,
        construction_type_fallback=None,
        unified_factory=build_unified_leg_input,
    )


def test_integration_fire_reaches_domain_bool():
    """form_data work_types=[FIRE] → canonical drop → seed → expansion → has_fire=true, has_ict=false."""
    form_data = {"has_subcontractor": True, "subcontractor_work_types": ["FIRE_FACILITY"]}
    inp = {"has_subcontractor": True}   # canonical 필터 후 (work_types 없음)
    body = _run(form_data, inp)
    assert body.input.get("has_fire_facility_subcontract") is True
    assert body.input.get("has_ict_subcontract") is False
    # work_types 자체는 LEG input 에 없음 (vocabulary 아님)
    assert "subcontractor_work_types" not in body.input


def test_integration_ict():
    form_data = {"has_subcontractor": True, "subcontractor_work_types": ["ICT"]}
    body = _run(form_data, {"has_subcontractor": True})
    assert body.input.get("has_fire_facility_subcontract") is False
    assert body.input.get("has_ict_subcontract") is True


def test_integration_both():
    form_data = {"has_subcontractor": True, "subcontractor_work_types": ["FIRE_FACILITY", "ICT"]}
    body = _run(form_data, {"has_subcontractor": True})
    assert body.input.get("has_fire_facility_subcontract") is True
    assert body.input.get("has_ict_subcontract") is True


def test_integration_empty_absent():
    """empty array → 두 domain bool ABSENT (canonical drop 후 seed 돼도 expansion 검증 실패)."""
    form_data = {"has_subcontractor": True, "subcontractor_work_types": []}
    body = _run(form_data, {"has_subcontractor": True})
    assert "has_fire_facility_subcontract" not in body.input
    assert "has_ict_subcontract" not in body.input


def test_integration_unknown_absent():
    """unknown token → 둘 다 ABSENT."""
    form_data = {"has_subcontractor": True, "subcontractor_work_types": ["INVALID_X"]}
    body = _run(form_data, {"has_subcontractor": True})
    assert "has_fire_facility_subcontract" not in body.input
    assert "has_ict_subcontract" not in body.input


def test_integration_key_absent():
    """work_types 미제공 → 둘 다 ABSENT."""
    form_data = {"has_subcontractor": True}
    body = _run(form_data, {"has_subcontractor": True})
    assert "has_fire_facility_subcontract" not in body.input
    assert "has_ict_subcontract" not in body.input
