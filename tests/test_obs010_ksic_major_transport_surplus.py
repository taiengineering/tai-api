"""WO-E2E-OBS010-KSIC-MAJOR-MINIMUM-MODIFY-001: LEG transport surplus removal.

ksic_major stays on consumer/Official schema. It is not a LEG Runtime input.
"""
from types import SimpleNamespace

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from schemas.diagnosis_integrated import DiagnosisRunBody
from schemas.legal_engine import DiagnoseStep1Body


def test_ksic_major_removed_from_leg_transport_allowlist():
    assert "ksic_major" not in _LEG_INPUT_FIELDS
    assert len(_LEG_INPUT_FIELDS) == 186
    assert len(set(_LEG_INPUT_FIELDS)) == 186


def test_build_facility_omits_ksic_major_keeps_worker_count():
    body = SimpleNamespace(
        sector="MANUFACTURING",
        ksic_major="30",
        input={"ksic_major": "30", "worker_count": 100},
    )
    fac = build_facility(body)
    assert fac.get("worker_count") == 100
    assert "ksic_major" not in fac


def test_consumer_schema_still_accepts_ksic_major():
    assert "ksic_major" in DiagnosisRunBody.model_fields
    assert "ksic_major" in DiagnoseStep1Body.model_fields
    run = DiagnosisRunBody(sector="MANUFACTURING", ksic_major="30")
    assert run.ksic_major == "30"
    step1 = DiagnoseStep1Body(sector="MANUFACTURING", ksic_major="30")
    assert step1.ksic_major == "30"
