"""WO-SM-CORE22-AP01-05-EXPLICIT-APPENDIX3-INPUT-CONTRACT-001

Explicit appendix3_item_no → Published AP01~05 Runtime Leaf projection.
Strict JSON integer 1..49. Item 37 subtype bool only. No KSIC/sector derivation.
Client projected-leaf spoof is stripped. is_construction contract unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from schemas.diagnosis_integrated import DiagnosisRunBody
from services.canonical.explicit_appendix3_classification import (
    APPENDIX3_INTERNAL_LEAVES,
    APPENDIX3_LAW_VERSION_ID,
    APPENDIX3_RUNTIME_LEAVES,
    Appendix3SourceError,
    collect_explicit_appendix3_source,
    merge_projection_after_canonical,
    persist_explicit_appendix3_source,
    prepare_available_and_projection,
    project_explicit_appendix3_classification,
    sanitize_form_data_for_persist,
)
from services.canonical.explicit_construction_predicates import (
    EXPLICIT_CONSTRUCTION_PREDICATES,
    collect_explicit_construction_predicates,
)
from services.canonical.leg_input_contract import build_unified_leg_input
from services.canonical.materialization import canonical_applicability
from services.diagnosis_integrated_svc import _build_unified_step1_body

SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "docs/canonical/legal-input/appendix3_items_v1.json"
)

SNAPSHOT_SHA256 = "b106956b54036508576774a48c98e9198facfd6a0d34d52d9e70ab55e07aad69"


def _available(body: DiagnosisRunBody) -> dict:
    available = {f: getattr(body, f, None) for f in type(body).model_fields}
    available.update(body.form_data or {})
    return available


def _official_facility(body: DiagnosisRunBody, *, sector: str = "INDUSTRIAL"):
    inp = {"region": body.region or "", "anonymous_flow": True, "tier_code": sector}
    available = _available(body)
    source, proj = prepare_available_and_projection(body, available)
    merge_projection_after_canonical(inp, canonical_applicability(available), proj)
    engine_sector = "MANUFACTURING" if sector == "INDUSTRIAL" else sector
    step1 = _build_unified_step1_body(
        engine_sector=engine_sector,
        inp=inp,
        workers=body.worker_count,
        body=body,
        factory_id=None,
        construction_type_fallback=body.construction_type,
        unified_factory=build_unified_leg_input,
    )
    return source, step1, build_facility(step1)


def test_snapshot_version_bound_1_to_49_exact():
    raw = SNAPSHOT.read_text(encoding="utf-8")
    assert hashlib.sha256(raw.encode("utf-8")).hexdigest() == SNAPSHOT_SHA256
    doc = json.loads(raw)
    assert doc["law_version_id"] == APPENDIX3_LAW_VERSION_ID
    assert doc["appendix_no"] == "별표 3"
    assert doc["item_count"] == 49
    assert doc["not_a_new_law_sot"] is True
    nos = [it["item_no"] for it in doc["items"]]
    assert nos == list(range(1, 50))
    assert len(set(nos)) == 49
    by = {it["item_no"]: it["label"] for it in doc["items"]}
    assert by[37] == "부동산업"
    assert by[40] == "사진처리업"
    assert by[49] == "건설업"


def test_schema_strict_item_accepts_int_rejects_coercion():
    ok = DiagnosisRunBody(sector="INDUSTRIAL", appendix3_item_no=37)
    assert ok.appendix3_item_no == 37
    DiagnosisRunBody.model_validate({"sector": "INDUSTRIAL", "appendix3_item_no": 1})
    DiagnosisRunBody.model_validate({"sector": "INDUSTRIAL", "appendix3_item_no": 49})
    for bad in (0, 50, -1, "37", 37.0, True, False):
        with pytest.raises(ValidationError):
            DiagnosisRunBody.model_validate(
                {"sector": "INDUSTRIAL", "appendix3_item_no": bad}
            )


def test_schema_strict_subtype_accepts_bool_rejects_coercion():
    yes = DiagnosisRunBody(sector="INDUSTRIAL", is_real_estate_management=True)
    no = DiagnosisRunBody(sector="INDUSTRIAL", is_real_estate_management=False)
    assert yes.is_real_estate_management is True
    assert no.is_real_estate_management is False
    for bad in ("true", "false", 1, 0, "True"):
        with pytest.raises(ValidationError):
            DiagnosisRunBody.model_validate(
                {"sector": "INDUSTRIAL", "is_real_estate_management": bad}
            )


def test_internal_leaves_are_not_diagnosis_run_body_fields():
    for name in APPENDIX3_INTERNAL_LEAVES:
        assert name not in DiagnosisRunBody.model_fields


def test_allowlist_contains_published_leaves_not_source_item():
    for name in APPENDIX3_RUNTIME_LEAVES:
        assert name in _LEG_INPUT_FIELDS
    assert "appendix3_item_no" not in _LEG_INPUT_FIELDS
    assert len(_LEG_INPUT_FIELDS) == len(set(_LEG_INPUT_FIELDS))
    assert len(_LEG_INPUT_FIELDS) == 114


def _proj_keys(item, subtype=None):
    return project_explicit_appendix3_classification(item, subtype)


def test_projection_truth_table():
    item1 = _proj_keys(1)
    assert item1 == {
        "is_appendix3_1_27": True,
        "is_appendix3_28_48": False,
        "is_appendix3_item_37": False,
        "is_appendix3_item_40": False,
    }
    assert "is_real_estate_management" not in item1
    assert _proj_keys(27) == item1

    item28 = _proj_keys(28)
    assert item28 == {
        "is_appendix3_1_27": False,
        "is_appendix3_28_48": True,
        "is_appendix3_item_37": False,
        "is_appendix3_item_40": False,
    }
    assert "is_real_estate_management" not in item28
    assert "is_construction" not in item28

    item37_false = _proj_keys(37, False)
    assert item37_false == {
        "is_appendix3_1_27": False,
        "is_appendix3_28_48": True,
        "is_appendix3_item_37": True,
        "is_appendix3_item_40": False,
        "is_real_estate_management": False,
    }
    item37_true = _proj_keys(37, True)
    assert item37_true["is_real_estate_management"] is True
    item37_missing = _proj_keys(37, None)
    assert item37_missing["is_appendix3_item_37"] is True
    assert "is_real_estate_management" not in item37_missing

    item40 = _proj_keys(40)
    assert item40["is_appendix3_item_40"] is True
    assert item40["is_appendix3_28_48"] is True
    assert "is_real_estate_management" not in item40
    assert _proj_keys(48)["is_appendix3_28_48"] is True

    item49 = _proj_keys(49)
    assert item49 == {
        "is_appendix3_1_27": False,
        "is_appendix3_28_48": False,
        "is_appendix3_item_37": False,
        "is_appendix3_item_40": False,
    }
    assert "is_real_estate_management" not in item49
    assert "is_construction" not in item49


def test_projection_does_not_use_ksic_or_sector():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        ksic_major="C",
        building_use_type="공장",
        form_data={"industry_type": "제조업", "ksic_code": "10"},
    )
    assert collect_explicit_appendix3_source(body) == {}
    assert project_explicit_appendix3_classification(None) == {}
    _source, _step1, fac = _official_facility(body)
    for name in APPENDIX3_RUNTIME_LEAVES:
        assert name not in fac


def test_item37_missing_subtype_does_not_invent_false():
    body = DiagnosisRunBody(sector="INDUSTRIAL", appendix3_item_no=37, worker_count=100)
    source = collect_explicit_appendix3_source(body)
    assert source == {"appendix3_item_no": 37}
    assert "is_real_estate_management" not in source
    _src, step1, fac = _official_facility(body)
    assert fac["is_appendix3_item_37"] is True
    assert "is_real_estate_management" not in fac
    assert "is_real_estate_management" not in step1.input


def test_source_conflict_fails():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        appendix3_item_no=28,
        form_data={"appendix3_item_no": 37},
    )
    with pytest.raises(Appendix3SourceError) as ei:
        collect_explicit_appendix3_source(body)
    assert ei.value.code == "APPENDIX3_ITEM_NO_CONFLICT"


def test_form_data_string_item_rejected():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        form_data={"appendix3_item_no": "37"},
    )
    with pytest.raises(Appendix3SourceError) as ei:
        collect_explicit_appendix3_source(body)
    assert ei.value.code == "APPENDIX3_ITEM_NO_TYPE"


def test_spoofed_internal_leaves_do_not_become_runtime_authority():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        appendix3_item_no=28,
        worker_count=50,
        form_data={
            "is_appendix3_1_27": True,
            "is_appendix3_item_37": True,
            "is_appendix3_28_48": False,
            "is_real_estate_management": True,
        },
    )
    _src, step1, fac = _official_facility(body)
    assert fac["is_appendix3_1_27"] is False
    assert fac["is_appendix3_28_48"] is True
    assert fac["is_appendix3_item_37"] is False
    assert "is_real_estate_management" not in fac
    assert step1.input["is_appendix3_1_27"] is False
    persist = persist_explicit_appendix3_source(_src)
    assert persist["appendix3_item_no"] == 28
    assert persist["appendix3_law_version_id"] == APPENDIX3_LAW_VERSION_ID
    assert "is_appendix3_1_27" not in persist
    fd = sanitize_form_data_for_persist(body.form_data, _src)
    for name in APPENDIX3_INTERNAL_LEAVES:
        assert name not in fd
    assert "is_real_estate_management" not in fd


def test_spoof_only_without_item_yields_zero_projected_leaves():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        worker_count=50,
        form_data={
            "is_appendix3_1_27": True,
            "is_appendix3_28_48": True,
            "is_appendix3_item_37": True,
            "is_appendix3_item_40": True,
            "is_real_estate_management": True,
        },
    )
    _src, _step1, fac = _official_facility(body)
    for name in APPENDIX3_RUNTIME_LEAVES:
        assert name not in fac
    assert _src == {}


def test_item49_does_not_inject_is_construction():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        appendix3_item_no=49,
        worker_count=50,
    )
    _src, _step1, fac = _official_facility(body)
    assert fac["is_appendix3_1_27"] is False
    assert fac["is_appendix3_28_48"] is False
    assert "is_construction" not in fac


def test_item28_does_not_synthesize_is_construction_false():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        appendix3_item_no=28,
        worker_count=50,
    )
    source, step1, fac = _official_facility(body)
    assert "is_construction" not in source
    assert "is_construction" not in step1.input
    assert "is_construction" not in fac
    assert collect_explicit_construction_predicates(body) == {}


def test_construction_predicates_unchanged_when_appendix3_present():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        is_construction=True,
        is_relationship_contractor=False,
        is_civil_construction=False,
        appendix3_item_no=28,
        contract_amount_eok=50.0,
    )
    collected = collect_explicit_construction_predicates(body)
    assert collected == {
        "is_construction": True,
        "is_relationship_contractor": False,
        "is_civil_construction": False,
    }
    _src, step1, fac = _official_facility(body, sector="CONSTRUCTION")
    assert fac["is_construction"] is True
    assert fac["is_relationship_contractor"] is False
    assert fac["is_civil_construction"] is False
    assert fac["is_appendix3_28_48"] is True
    for name in EXPLICIT_CONSTRUCTION_PREDICATES:
        assert name in _LEG_INPUT_FIELDS


def test_persist_does_not_store_projected_leaves_as_user_answers():
    source = {"appendix3_item_no": 37, "is_real_estate_management": False}
    stored = persist_explicit_appendix3_source(source)
    assert stored == {
        "appendix3_item_no": 37,
        "is_real_estate_management": False,
        "appendix3_law_version_id": APPENDIX3_LAW_VERSION_ID,
    }
    for name in APPENDIX3_INTERNAL_LEAVES:
        assert name not in stored
    stored49 = persist_explicit_appendix3_source({"appendix3_item_no": 49})
    assert "is_real_estate_management" not in stored49
    assert "is_construction" not in stored49
