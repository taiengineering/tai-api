"""WO-SM-CORE22-CONSTRUCTION-PREDICATE-EXPLICIT-INPUT-CONTRACT-001

Explicit canonical legal facts: is_construction / is_relationship_contractor /
is_civil_construction. Additive Optional[bool]. missing != false. False preserved.

No sector / construction_type / construction_type_code / order_type /
has_subcontractor derivation. No server fail-closed in this change.
"""
from __future__ import annotations

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from schemas.diagnosis_integrated import DiagnosisRunBody
from services.canonical.explicit_construction_predicates import (
    EXPLICIT_CONSTRUCTION_PREDICATES,
    collect_explicit_construction_predicates,
)
from services.canonical.leg_input_contract import build_unified_leg_input
from services.canonical.materialization import canonical_applicability
from services.diagnosis_integrated_svc import _build_unified_step1_body


def _available(body: DiagnosisRunBody) -> dict:
    available = {f: getattr(body, f, None) for f in type(body).model_fields}
    available.update(body.form_data or {})
    return available


def _official_facility(body: DiagnosisRunBody):
    inp = {"region": body.region or "", "anonymous_flow": True, "tier_code": "CONSTRUCTION"}
    for code, val in canonical_applicability(_available(body)).items():
        inp.setdefault(code, val)
    step1 = _build_unified_step1_body(
        engine_sector="CONSTRUCTION",
        inp=inp,
        workers=body.worker_count,
        body=body,
        factory_id=None,
        construction_type_fallback=body.construction_type,
        unified_factory=build_unified_leg_input,
    )
    return step1, build_facility(step1)


def test_schema_optional_no_alias():
    empty = DiagnosisRunBody(sector="CONSTRUCTION")
    for name in EXPLICIT_CONSTRUCTION_PREDICATES:
        assert getattr(empty, name) is None
        assert DiagnosisRunBody.model_fields[name].alias in (None, name)
    yes = DiagnosisRunBody(
        sector="CONSTRUCTION",
        is_construction=True,
        is_relationship_contractor=False,
        is_civil_construction=False,
    )
    dumped = yes.model_dump()
    assert dumped["is_construction"] is True
    assert dumped["is_relationship_contractor"] is False
    assert dumped["is_civil_construction"] is False


def test_allowlist_exact_names_no_alias():
    for name in EXPLICIT_CONSTRUCTION_PREDICATES:
        assert name in _LEG_INPUT_FIELDS
    assert len(_LEG_INPUT_FIELDS) == len(set(_LEG_INPUT_FIELDS))
    assert "is_construction" not in (
        "sector",
        "construction_type",
        "construction_type_code",
        "order_type",
    )


def test_no_derivation_from_sector_or_raw_construction_facts():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        construction_type="토목",
        form_data={
            "construction_type_code": "CIVIL",
            "order_type": "하도급",
            "has_subcontractor": True,
            "subcon_workers": 12,
        },
    )
    collected = collect_explicit_construction_predicates(body)
    assert collected == {}
    out = canonical_applicability(_available(body))
    for name in EXPLICIT_CONSTRUCTION_PREDICATES:
        assert name not in out
        assert name not in collected
    _step1, fac = _official_facility(body)
    for name in EXPLICIT_CONSTRUCTION_PREDICATES:
        assert name not in fac


def test_false_preserved_top_level_and_form_data():
    top = DiagnosisRunBody(
        sector="CONSTRUCTION",
        is_construction=True,
        is_relationship_contractor=False,
        is_civil_construction=False,
        contract_amount_eok=50.0,
    )
    assert collect_explicit_construction_predicates(top) == {
        "is_construction": True,
        "is_relationship_contractor": False,
        "is_civil_construction": False,
    }
    canon = canonical_applicability(_available(top))
    assert canon["is_construction"] is True
    assert canon["is_relationship_contractor"] is False
    assert canon["is_civil_construction"] is False
    step1, fac = _official_facility(top)
    assert step1.input["is_relationship_contractor"] is False
    assert step1.input["is_civil_construction"] is False
    assert fac["is_relationship_contractor"] is False
    assert fac["is_civil_construction"] is False
    assert fac["is_construction"] is True

    nested = DiagnosisRunBody(
        sector="CONSTRUCTION",
        form_data={
            "is_construction": True,
            "is_relationship_contractor": False,
            "is_civil_construction": False,
            "contract_amount_eok": 50.0,
        },
    )
    assert nested.is_construction is None
    assert collect_explicit_construction_predicates(nested)["is_relationship_contractor"] is False
    _step1, fac2 = _official_facility(nested)
    assert fac2["is_relationship_contractor"] is False
    assert fac2["is_civil_construction"] is False


def test_none_omitted_not_coerced_to_false():
    body = DiagnosisRunBody(sector="CONSTRUCTION", is_construction=True)
    collected = collect_explicit_construction_predicates(body)
    assert collected == {"is_construction": True}
    canon = canonical_applicability(_available(body))
    assert canon["is_construction"] is True
    assert "is_relationship_contractor" not in canon
    assert "is_civil_construction" not in canon
    _step1, fac = _official_facility(body)
    assert "is_relationship_contractor" not in fac
    assert "is_civil_construction" not in fac


def test_building_industrial_do_not_require_predicates():
    for sector in ("BUILDING", "INDUSTRIAL"):
        body = DiagnosisRunBody(sector=sector, worker_count=10)
        assert collect_explicit_construction_predicates(body) == {}
        canon = canonical_applicability(_available(body))
        for name in EXPLICIT_CONSTRUCTION_PREDICATES:
            assert name not in canon


def test_unified_input_false_not_dropped():
    facts = {
        "is_construction": True,
        "is_relationship_contractor": False,
        "is_civil_construction": False,
        "contract_amount_eok": 50.0,
    }
    body = build_unified_leg_input(sector="CONSTRUCTION", source_facts=facts)
    assert body.input["is_relationship_contractor"] is False
    assert body.input["is_civil_construction"] is False
    fac = build_facility(body)
    assert fac["is_relationship_contractor"] is False
    assert fac["is_civil_construction"] is False
