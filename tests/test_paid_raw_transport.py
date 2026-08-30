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


# ── CORRECTION-01: empty structured value lossless (production path via fake supabase) ──
from services import diagnosis_integrated_svc as _svc


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, name, store):
        self._name = name
        self._store = store

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def update(self, *a, **k):
        return self

    def insert(self, row):
        self._store.setdefault("inserts", {}).setdefault(self._name, []).append(row)
        self._pending = row
        return self

    def execute(self):
        if self._name == "diagnosis_auth_log":
            return _FakeResult([{
                "id": "auth1", "ci_hash": "ci", "name": "n", "phone": "p",
                "free_count": 0, "free_limit": 3, "status": "ACTIVE", "linked_user_id": None,
            }])
        if self._name == "diagnosis_disclaimer_log":
            return _FakeResult([{"id": "disc1", "ci_hash": "ci", "agreed": True}])
        if self._name == "anonymous_diagnosis_results":
            row = getattr(self, "_pending", None)
            if row is not None:
                return _FakeResult([{**row, "id": "res1"}])
            return _FakeResult([{"id": "res1", "public_token": "tok"}])
        return _FakeResult([])


class _FakeSupabase:
    def __init__(self):
        self.store = {}

    def table(self, name):
        return _FakeTable(name, self.store)


def _run_capture(body):
    sup = _FakeSupabase()
    _svc.run_diagnosis(
        sup, body,
        run_step1_func=lambda supabase, step1_body: {"status": "success", "data": {"applicable_count": 0, "rules_table": []}},
        auto_tier_func=lambda sector, floor_area, contract_amount_eok, user_tier: "INDUSTRY_FREE",
        build_partial_func=lambda full: {},
        now_func=lambda: "2026-01-01T00:00:00Z",
        paid_tier_prices={},
        free_tier_codes={"INDUSTRY_FREE"},
        engine_version="test",
        current_user=None,
    )
    inserts = sup.store.get("inserts", {}).get("anonymous_diagnosis_results", [])
    assert inserts, "no result row inserted"
    return inserts[-1]["input_data"]


def _paid_free_body(**over):
    kw = dict(auth_token="t", sector="INDUSTRIAL", disclaimer_log_id="disc1")
    kw.update(over)
    return DiagnosisRunBody(**kw)


def test_corr01_empty_dict_input_preserved():
    idata = _run_capture(_paid_free_body(input={}))
    assert idata["raw_structured_input"]["input"] == {}


def test_corr01_empty_process_list_preserved():
    idata = _run_capture(_paid_free_body(process_list=[]))
    assert idata["raw_structured_input"]["process_list"] == []


def test_corr01_empty_equipment_list_preserved():
    idata = _run_capture(_paid_free_body(equipment_list=[]))
    assert idata["raw_structured_input"]["equipment_list"] == []


def test_corr01_empty_ksic_list_preserved():
    idata = _run_capture(_paid_free_body(ksic_list=[]))
    assert idata["raw_structured_input"]["ksic_list"] == []


def test_corr01_all_none_no_container():
    idata = _run_capture(_paid_free_body())
    assert "raw_structured_input" not in idata


def test_corr01_populated_roundtrip_production_path():
    body = _paid_free_body(
        input={"material_profile": [{"material_category": "위험물", "handling_modes": ["저장"]}]},
        process_list=[{"process_name": "용접", "activity_type": ["개조·수리·청소"]}],
        equipment_list=[{"equipment_type": "프레스", "usage_type": ["구내운반차 사용"], "relation_type": ["가스집합장치의 가스용기"]}],
        ksic_list=["C", "H"],
    )
    raw = _run_capture(body)["raw_structured_input"]
    assert raw["input"] == body.input
    assert raw["process_list"] == body.process_list
    assert raw["equipment_list"] == body.equipment_list
    assert raw["ksic_list"] == ["C", "H"]
