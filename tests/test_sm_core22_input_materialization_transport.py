"""WO-SM-CORE22-PRODUCTION-INPUT-MATERIALIZATION-REPAIR-001

Official LEG request values already exist on DiagnosisRunBody.
This file proves FIRST LOSS POINT repair: contract_amount_eok exact-name
passthrough through canonical_applicability → unified input → build_facility.

No AP06/AP07/AP08 branches. No synthetic 0/1.0. No unit reconversion.
direct_workers / subcon_workers are not in RTM condition vocabulary — not appended.
"""
from __future__ import annotations

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from schemas.diagnosis_integrated import DiagnosisRunBody
from services.canonical.leg_input_contract import build_unified_leg_input
from services.canonical.materialization import canonical_applicability
from services.diagnosis_integrated_svc import _build_unified_step1_body


# Official Clean Run1 Construction request values (verbatim).
CONSTRUCTION_27 = (
    ("PF-0028", 18.0, 300, 150, "건축"),
    ("PF-0029", 6.0, 50, 25, "건축"),
    ("PF-0030", 18.0, 300, 150, "토목"),
    ("PF-0031", 18.0, 300, 150, "토목"),
    ("PF-0032", 18.0, 300, 150, "공통"),
    ("PF-0033", 6.0, 50, 25, "건축"),
    ("PF-0034", 1.0, 15, 7, "공통"),
    ("PF-0035", 6.0, 50, 25, "공통"),
    ("PF-0036", 18.0, 300, 150, "토목"),
    ("PF-0052", 49.0, 50, 0, "건축"),
    ("PF-0053", 50.0, 50, 0, "건축"),
    ("PF-0054", 51.0, 50, 0, "건축"),
    ("PF-0055", 119.0, 50, 0, "건축"),
    ("PF-0056", 120.0, 50, 0, "건축"),
    ("PF-0057", 121.0, 50, 0, "건축"),
    ("PF-0094", 30.0, 300, 150, "건축"),
    ("PF-0095", 6.0, 50, 25, "토목"),
    ("PF-0096", 30.0, 300, 150, "토목"),
    ("PF-0097", 50.0, 300, 150, "공통"),
    ("PF-0098", 1.0, 15, 7, "건축"),
    ("PF-0099", 6.0, 50, 25, "공통"),
    ("PF-0100", 1.0, 15, 7, "공통"),
    ("PF-0101", 50.0, 300, 150, "토목"),
    ("PF-0102", 18.0, 50, 25, "건축"),
    ("PF-0103", 50.0, 300, 150, "토목"),
    ("PF-0104", 18.0, 50, 25, "공통"),
    ("PF-0105", 6.0, 50, 25, "건축"),
)

PF0052_57 = tuple(row for row in CONSTRUCTION_27 if row[0] in {
    "PF-0052", "PF-0053", "PF-0054", "PF-0055", "PF-0056", "PF-0057",
})


def _body(eok, direct, subcon, ctype, workers):
    return DiagnosisRunBody(
        sector="CONSTRUCTION",
        contract_amount_eok=eok,
        direct_workers=direct,
        subcon_workers=subcon,
        construction_type=ctype,
        worker_count=workers,
        form_data={"construction_type": ctype, "worker_count": workers},
    )


def _official_facility(body: DiagnosisRunBody):
    available = {f: getattr(body, f, None) for f in type(body).model_fields}
    available.update(body.form_data or {})
    inp = {"region": body.region or "", "anonymous_flow": True, "tier_code": "CONSTRUCTION"}
    for code, val in canonical_applicability(available).items():
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


def test_diagnosis_run_body_fields_present_optional():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        contract_amount_eok=50.0,
        direct_workers=50,
        subcon_workers=0,
        construction_type="건축",
    )
    dumped = body.model_dump()
    assert dumped["contract_amount_eok"] == 50.0
    assert dumped["direct_workers"] == 50
    assert dumped["subcon_workers"] == 0
    assert dumped["construction_type"] == "건축"
    empty = DiagnosisRunBody(sector="CONSTRUCTION")
    assert empty.contract_amount_eok is None
    assert empty.direct_workers is None
    assert empty.subcon_workers is None
    assert empty.construction_type is None
    for name in ("contract_amount_eok", "direct_workers", "subcon_workers", "construction_type"):
        assert DiagnosisRunBody.model_fields[name].alias in (None, name)


def test_rtm_allowlist_has_eok_not_worker_split():
    assert "contract_amount_eok" in _LEG_INPUT_FIELDS
    assert "construction_type" in _LEG_INPUT_FIELDS
    assert "direct_workers" not in _LEG_INPUT_FIELDS
    assert "subcon_workers" not in _LEG_INPUT_FIELDS


def test_first_loss_point_was_allowlist_eok_now_present():
    body = _body(50.0, 50, 0, "건축", 50)
    available = {f: getattr(body, f, None) for f in type(body).model_fields}
    available.update(body.form_data or {})
    out = canonical_applicability(available)
    assert out["contract_amount_eok"] == 50.0
    assert out["construction_type"] == "건축"
    assert "direct_workers" not in out
    assert "subcon_workers" not in out


def test_construction_27_eok_and_type_reach_facility():
    assert len(CONSTRUCTION_27) == 27
    for pid, eok, direct, subcon, ctype in CONSTRUCTION_27:
        workers = direct + subcon
        body = _body(eok, direct, subcon, ctype, workers)
        step1, fac = _official_facility(body)
        assert step1.input.get("contract_amount_eok") == eok, pid
        assert fac.get("contract_amount_eok") == eok, pid
        assert fac.get("construction_type") == ctype, pid
        assert fac["contract_amount_eok"] != eok / 10_000
        assert fac["contract_amount_eok"] != eok * 100_000_000
        assert "direct_workers" not in fac
        assert "subcon_workers" not in fac
        if eok != 1.0:
            assert fac["contract_amount_eok"] != 1.0


def test_pf0052_57_values_lossless():
    expected = {
        "PF-0052": 49.0,
        "PF-0053": 50.0,
        "PF-0054": 51.0,
        "PF-0055": 119.0,
        "PF-0056": 120.0,
        "PF-0057": 121.0,
    }
    assert len(PF0052_57) == 6
    for pid, eok, direct, subcon, ctype in PF0052_57:
        body = _body(eok, direct, subcon, ctype, 50)
        _step1, fac = _official_facility(body)
        assert fac["contract_amount_eok"] == expected[pid]
        assert fac["contract_amount_eok"] is not True
        assert type(fac["contract_amount_eok"]) is float


def test_missing_eok_not_synthesized():
    body = DiagnosisRunBody(sector="CONSTRUCTION", construction_type="건축", worker_count=50)
    _step1, fac = _official_facility(body)
    assert "contract_amount_eok" not in fac
    assert fac.get("contract_amount_eok") not in (0, 0.0, 1, 1.0)
