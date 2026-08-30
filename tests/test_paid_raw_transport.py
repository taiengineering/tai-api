# WO-FE-IND-GAP-051-TRANSPORT-001 — paid structured RAW INPUT transport contract test
# RAW ENVELOPE(input/process_list/equipment_list/ksic_list) 은 backend 가 lossless 수신·보존만 하고
# CANONICAL LEG applicability(CURRENT _LEG_INPUT_FIELDS exact-name allowlist) 로는 유입되지 않는다.
from schemas.diagnosis_integrated import DiagnosisRunBody
from services.canonical.materialization import canonical_applicability


def _paid_body():
    return DiagnosisRunBody(
        auth_token="t", sector="INDUSTRIAL", tier="PAID", ksic_list=["C", "H"],
        input={"material_profile": [{"material_category": "위험물", "handling_modes": ["저장", "취급"]}],
               "has_chemical_substance": True},
        process_list=[{"process_name": "용접", "hazard_codes": ["H1"], "worker_count": 3,
                       "is_primary": True, "activity_type": ["개조·수리·청소"]}],
        equipment_list=[{"equipment_type": "프레스", "asset_name": "150t", "quantity": 2,
                         "capacity_value": 150, "capacity_unit": "ton", "is_legal_target": True,
                         "usage_type": ["구내운반차 사용"], "relation_type": ["가스집합장치의 가스용기"]}],
    )


def _canon(body):
    avail = {f: getattr(body, f, None) for f in type(body).model_fields}
    avail.update(getattr(body, "form_data", None) or {})
    return canonical_applicability(avail)


def test_current_paid_payload_accepted():
    b = _paid_body()
    assert b.sector == "INDUSTRIAL"
    assert b.ksic_list == ["C", "H"]


def test_nested_roundtrip_verbatim():
    b = _paid_body()
    assert b.input["material_profile"] == [{"material_category": "위험물", "handling_modes": ["저장", "취급"]}]
    assert b.process_list[0]["activity_type"] == ["개조·수리·청소"]
    assert b.equipment_list[0]["usage_type"] == ["구내운반차 사용"]
    assert b.equipment_list[0]["relation_type"] == ["가스집합장치의 가스용기"]


def test_row_columns_preserved():
    b = _paid_body()
    assert b.process_list[0]["process_name"] == "용접" and b.process_list[0]["is_primary"] is True
    assert b.equipment_list[0]["equipment_type"] == "프레스" and b.equipment_list[0]["is_legal_target"] is True


def test_canonical_isolation_no_raw_leak():
    canon = _canon(_paid_body())
    for k in ("input", "process_list", "equipment_list", "ksic_list",
              "material_profile", "activity_type", "usage_type", "relation_type"):
        assert k not in canon
    # raw input dict 내부(has_chemical_substance)도 flatten 되어 canonical 로 새지 않는다
    assert "has_chemical_substance" not in canon


def test_unknown_raw_nested_preserved_not_in_canonical():
    b = DiagnosisRunBody(auth_token="t", sector="INDUSTRIAL", input={"future_attribute": "x"})
    assert b.input["future_attribute"] == "x"
    assert "future_attribute" not in _canon(b)


def test_legacy_form_data_canonical_unchanged():
    b = DiagnosisRunBody(auth_token="t", sector="BUILDING",
                         form_data={"has_confined_space": True, "worker_count": 5})
    canon = _canon(b)
    assert canon.get("has_confined_space") is True
    assert canon.get("worker_count") == 5


def test_repair27_process_equipment_raw_received():
    b = _paid_body()
    assert b.process_list[0]["process_name"] == "용접"
    assert b.equipment_list[0]["equipment_type"] == "프레스"


def _build_raw(body):
    return (
        {k: v for k, v in {
            "input": body.input, "process_list": body.process_list,
            "equipment_list": body.equipment_list, "ksic_list": body.ksic_list,
        }.items() if v is not None}
        if any([body.input, body.process_list, body.equipment_list, body.ksic_list]) else {}
    )


def test_raw_structured_input_persistence_container():
    b = _paid_body()
    raw = _build_raw(b)
    assert raw["input"] == b.input and raw["process_list"] == b.process_list
    assert raw["equipment_list"] == b.equipment_list and raw["ksic_list"] == ["C", "H"]


def test_legacy_no_raw_empty_container():
    b = DiagnosisRunBody(auth_token="t", sector="BUILDING",
                         form_data={"has_confined_space": True})
    assert _build_raw(b) == {}
