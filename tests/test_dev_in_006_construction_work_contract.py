"""DEV-IN-006: construction-work trigger contract restoration tests.

EXCAVATION / WELDING / DEMOLITION 3종의 전 구간 계약을 검증한다.
- Emitter: factories has_*_work=True -> WORK:* 코드 emit
- UNKNOWN 보존: null/absent/False -> emit 안 함
- Consumer 계약: field_code -> factories 컬럼 매핑 존재
- Detector: TRIGGER_SPECS(_get_spec)에 3종 존재
(Binder/_TRIGGER_TO_SCOPE_SLOTS 존재는 감사에서 확인; adapter import 회피로 여기선 미포함)
"""
from services.trigger_generator import generate_trigger_codes_from_row
from services.trigger_obligation_generator import _get_spec
from constants.exists_mvp_fields import FIELD_CODE_TO_FACTORY_COLUMN

_TARGETS = {
    "has_excavation_work": "WORK:EXCAVATION",
    "has_welding_work": "WORK:WELDING",
    "has_demolition_work": "WORK:DEMOLITION",
}


def test_emit_when_true():
    for col, code in _TARGETS.items():
        codes = generate_trigger_codes_from_row({col: True}, [])
        assert code in codes, f"{col}=True should emit {code}"


def test_no_emit_when_unknown_or_false():
    # 미입력(UNKNOWN) → emit 안 함
    codes = generate_trigger_codes_from_row({}, [])
    for code in _TARGETS.values():
        assert code not in codes
    # 명시적 False → emit 안 함
    for col, code in _TARGETS.items():
        c2 = generate_trigger_codes_from_row({col: False}, [])
        assert code not in c2


def test_consumer_field_code_maps_to_column():
    assert FIELD_CODE_TO_FACTORY_COLUMN["has_excavation"] == "has_excavation_work"
    assert FIELD_CODE_TO_FACTORY_COLUMN["has_welding"] == "has_welding_work"
    assert FIELD_CODE_TO_FACTORY_COLUMN["has_demolition"] == "has_demolition_work"


def test_detector_specs_present():
    for code in _TARGETS.values():
        assert _get_spec(code) is not None, f"detector missing spec for {code}"
