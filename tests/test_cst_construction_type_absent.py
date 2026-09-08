"""WO-CST-SYNTHETIC-CONSTRUCTION-TYPE-HOTFIX-001 회귀.

_build_unified_step1_body 의 CST construction_type synthetic default("건축") 제거 검증.
transport 계약만 검증 — LEG runtime 미호출. unified_factory 를 캡처 fake 로 주입해
전달되는 source_facts(runtime_facts) 를 확인한다.
"""
from services.diagnosis_integrated_svc import _build_unified_step1_body


class _Body:
    """DiagnoseStep1Body 대역 — helper 가 참조하는 속성만."""
    def __init__(self, form_data=None):
        self.form_data = form_data or {}
        self.input = {}
        self.elevator_count = None


def _capture_factory():
    """unified_factory 캡처: 전달된 source_facts 를 보관하고 sentinel 반환."""
    captured = {}
    def factory(*, sector, source_facts, factory_id):
        captured["sector"] = sector
        captured["source_facts"] = dict(source_facts)
        captured["factory_id"] = factory_id
        class _S:  # step1_body 대역 (BUILDING 분기 model_copy 미사용 경로)
            pass
        return _S()
    return factory, captured


def _run(engine_sector, inp, construction_type_fallback, form_data=None):
    factory, captured = _capture_factory()
    _build_unified_step1_body(
        engine_sector=engine_sector,
        inp=dict(inp),
        workers=30,
        body=_Body(form_data=form_data),
        factory_id=None,
        construction_type_fallback=construction_type_fallback,
        unified_factory=factory,
    )
    return captured["source_facts"]


def test_T1_cst_missing_construction_type_absent():
    # CST + construction_type 미입력 → source_facts 에 construction_type 키 없음(ABSENT)
    sf = _run("CONSTRUCTION", inp={"region": ""}, construction_type_fallback=None)
    assert "construction_type" not in sf, f"missing 인데 생성됨: {sf.get('construction_type')!r}"


def test_T2_cst_explicit_construction_type_preserved():
    # CST + construction_type 명시(inp=canonical 결과에 존재) → 그대로 보존
    sf = _run("CONSTRUCTION", inp={"construction_type": "건축", "region": ""},
              construction_type_fallback="건축")
    assert sf.get("construction_type") == "건축", f"명시값 유실: {sf!r}"


def test_T2b_cst_fallback_no_longer_injects():
    # patch 계약: fallback 파라미터로는 더 이상 주입 안 함(미입력이면 fallback 있어도 ABSENT)
    sf = _run("CONSTRUCTION", inp={"region": ""}, construction_type_fallback="건축")
    assert "construction_type" not in sf, f"fallback 이 주입함(계약 위반): {sf.get('construction_type')!r}"


def test_T3_industrial_regression_no_construction_type():
    # IND(MANUFACTURING) → construction_type 무관, 생성 안 됨
    sf = _run("MANUFACTURING", inp={"worker_count": 45, "region": ""},
              construction_type_fallback=None)
    assert "construction_type" not in sf
    assert sf.get("worker_count") == 45


def test_T4_building_regression_no_construction_type():
    # BLD(BUILDING) → construction_type 무관, 생성 안 됨
    sf = _run("BUILDING", inp={"total_floor_area": 12000, "region": ""},
              construction_type_fallback=None)
    assert "construction_type" not in sf
