"""WO-E2E200-CERT1-REVISE-001 KD-001

CONSTRUCTION resolved _contract_eok (body.contract_amount_eok →
form_data.project_amount → form_data.contract_amount_eok) must reach
unified source_facts / build_facility as exact-name contract_amount_eok.

No /10000, no *1e8, no 1.0 synthetic, no sector→amount derivation.
LEG / CORE22 published rows are not invoked or changed.
"""
from __future__ import annotations

from clients.leg_runtime_client import build_facility
from schemas.diagnosis_integrated import DiagnosisRunBody
from services.canonical.leg_input_contract import build_unified_leg_input
from services.canonical.materialization import canonical_applicability
from services import diagnosis_integrated_svc as _svc
from services.diagnosis_integrated_svc import _build_unified_step1_body

# Published CORE22 identities — constants only, not evaluated here.
AP06 = "7ba9bdde-b3b7-52da-9970-b0a52da6e1e7"
AP07 = "fa46b294-d497-58db-ac63-49c859cc4a1b"
AP08 = "12329b54-027f-59aa-bd93-ec7caa53fbd0"

T1_EOK = (3, 49, 50, 99, 100, 119, 120, 149, 150, 799, 800, 858)

# Published SM amount boundaries used by AP06/AP07/AP08 (LEG tests, unchanged).
AP06_LOWER = 50.0
AP06_UPPER_NONCIVIL = 120.0
RELATIONSHIP_LOWER = 100.0
CIVIL_AP06_UPPER = 150.0
AP08_LOWER = 800.0


class _R:
    def __init__(self, data):
        self.data = data


class _T:
    def __init__(self, n):
        self._n = n

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def update(self, *a, **k):
        return self

    def insert(self, row):
        self._p = row
        return self

    def execute(self):
        if self._n == "diagnosis_auth_log":
            return _R([{
                "id": "a1", "ci_hash": "ci", "name": "n", "phone": "p",
                "free_count": 0, "free_limit": 3, "status": "ACTIVE",
                "linked_user_id": None,
            }])
        if self._n == "diagnosis_disclaimer_log":
            return _R([{"id": "disc1", "ci_hash": "ci", "agreed": True}])
        if self._n == "anonymous_diagnosis_results":
            return _R([{**(getattr(self, "_p", None) or {}), "id": "r1"}])
        return _R([])


class _S:
    def table(self, n):
        return _T(n)


def _available(body: DiagnosisRunBody) -> dict:
    available = {f: getattr(body, f, None) for f in type(body).model_fields}
    available.update(body.form_data or {})
    return available


def _unified_step1(body: DiagnosisRunBody, *, contract_amount_eok=None, engine_sector=None):
    sector = engine_sector or (
        "MANUFACTURING" if body.sector == "INDUSTRIAL" else body.sector
    )
    inp = {"region": body.region or "", "anonymous_flow": True, "tier_code": sector}
    for code, val in canonical_applicability(_available(body)).items():
        inp.setdefault(code, val)
    return _build_unified_step1_body(
        engine_sector=sector,
        inp=inp,
        workers=body.worker_count if body.worker_count is not None else 0,
        body=body,
        factory_id=None,
        construction_type_fallback=body.construction_type,
        unified_factory=build_unified_leg_input,
        contract_amount_eok=contract_amount_eok,
    )


def _cap(body: DiagnosisRunBody, *, auto_tier="CONSTRUCTION_FREE"):
    cap = {}

    def r1(_sb, s1):
        cap["s1"] = s1
        return {"status": "success", "data": {"applicable_count": 0, "rules_table": []}}

    _svc.run_diagnosis(
        _S(),
        body,
        run_step1_func=r1,
        auto_tier_func=lambda *a, **k: auto_tier,
        build_partial_func=lambda f: {},
        now_func=lambda: "2026-01-01T00:00:00Z",
        paid_tier_prices={},
        free_tier_codes={"CONSTRUCTION_FREE", "INDUSTRY_FREE", "BUILDING_FREE"},
        engine_version="t",
        current_user=None,
        unified_step1_factory_func=build_unified_leg_input,
    )
    return cap["s1"], build_facility(cap["s1"])


def _cst_body(form_data, **extra):
    fd = dict(form_data or {})
    fd.setdefault("is_construction", True)
    fd.setdefault("is_relationship_contractor", False)
    fd.setdefault("is_civil_construction", False)
    return DiagnosisRunBody(
        auth_token="t",
        sector="CONSTRUCTION",
        disclaimer_log_id="disc1",
        form_data=fd,
        **extra,
    )


def _assert_verbatim_eok(fac, eok):
    assert fac.get("contract_amount_eok") == float(eok)
    assert fac["contract_amount_eok"] != float(eok) / 10_000
    assert fac["contract_amount_eok"] != float(eok) * 100_000_000
    if float(eok) != 1.0:
        assert fac["contract_amount_eok"] != 1.0


# --- T1 exact passthrough ---

def test_t1_project_amount_reaches_unified_and_facility():
    for eok in T1_EOK:
        body = DiagnosisRunBody(
            sector="CONSTRUCTION",
            form_data={"project_amount": eok, "worker_count": 50},
        )
        step1 = _unified_step1(body, contract_amount_eok=float(eok))
        fac = build_facility(step1)
        assert step1.input.get("contract_amount_eok") == float(eok)
        _assert_verbatim_eok(fac, eok)
        assert "project_amount" not in step1.input
        assert "project_amount" not in fac


def test_t1_run_diagnosis_form_data_project_amount():
    for eok in T1_EOK:
        step1, fac = _cap(_cst_body({"project_amount": eok, "worker_count": 50}))
        assert step1.input.get("contract_amount_eok") == float(eok)
        _assert_verbatim_eok(fac, eok)
        assert "project_amount" not in fac


# --- T2 absent stays absent ---

def test_t2_absent_stays_absent_no_synthetic_one():
    body = DiagnosisRunBody(sector="CONSTRUCTION", worker_count=10)
    step1 = _unified_step1(body, contract_amount_eok=None)
    fac = build_facility(step1)
    assert "contract_amount_eok" not in step1.input
    assert "contract_amount_eok" not in fac
    assert fac.get("contract_amount_eok") != 1.0


def test_t2_run_diagnosis_absent_no_synthetic_one():
    step1, fac = _cap(_cst_body({"worker_count": 10}))
    assert "contract_amount_eok" not in step1.input
    assert "contract_amount_eok" not in fac
    assert fac.get("contract_amount_eok") != 1.0


# --- T3 existing canonical eok is not overwritten ---

def test_t3_existing_canonical_eok_not_overwritten():
    body = DiagnosisRunBody(
        sector="CONSTRUCTION",
        contract_amount_eok=50.0,
        form_data={"project_amount": 999.0},
    )
    step1 = _unified_step1(body, contract_amount_eok=999.0)
    fac = build_facility(step1)
    assert step1.input["contract_amount_eok"] == 50.0
    assert fac["contract_amount_eok"] == 50.0


def test_t3_run_diagnosis_body_eok_precedes_project_amount():
    step1, fac = _cap(_cst_body(
        {"project_amount": 999.0, "worker_count": 50},
        contract_amount_eok=50.0,
    ))
    assert step1.input["contract_amount_eok"] == 50.0
    assert fac["contract_amount_eok"] == 50.0


# --- T4 non-construction no delta ---

def test_t4_industrial_project_amount_does_not_create_eok():
    body = DiagnosisRunBody(
        sector="INDUSTRIAL",
        appendix3_item_no=28,
        form_data={"project_amount": 50.0, "worker_count": 10},
    )
    step1 = _unified_step1(body, contract_amount_eok=50.0, engine_sector="MANUFACTURING")
    fac = build_facility(step1)
    assert "contract_amount_eok" not in step1.input
    assert "contract_amount_eok" not in fac


def test_t4_building_project_amount_does_not_create_eok():
    body = DiagnosisRunBody(
        sector="BUILDING",
        appendix3_item_no=28,
        form_data={"project_amount": 50.0, "worker_count": 10},
    )
    step1 = _unified_step1(body, contract_amount_eok=50.0, engine_sector="BUILDING")
    fac = build_facility(step1)
    assert "contract_amount_eok" not in step1.input
    assert "contract_amount_eok" not in fac


def test_t4_run_diagnosis_industrial_project_amount_no_eok():
    body = DiagnosisRunBody(
        auth_token="t",
        sector="INDUSTRIAL",
        disclaimer_log_id="disc1",
        appendix3_item_no=28,
        form_data={"project_amount": 50.0, "worker_count": 10},
    )
    step1, fac = _cap(body, auto_tier="INDUSTRY_FREE")
    assert "contract_amount_eok" not in step1.input
    assert "contract_amount_eok" not in fac


def test_t4_run_diagnosis_building_project_amount_no_eok():
    body = DiagnosisRunBody(
        auth_token="t",
        sector="BUILDING",
        disclaimer_log_id="disc1",
        appendix3_item_no=28,
        form_data={"project_amount": 50.0, "worker_count": 10},
    )
    step1, fac = _cap(body, auto_tier="BUILDING_FREE")
    assert "contract_amount_eok" not in step1.input
    assert "contract_amount_eok" not in fac


# --- T5 SM boundary probes: runtime facts only, published ids recorded ---

def test_t5_published_identities_unchanged_constants():
    assert AP06 == "7ba9bdde-b3b7-52da-9970-b0a52da6e1e7"
    assert AP07 == "fa46b294-d497-58db-ac63-49c859cc4a1b"
    assert AP08 == "12329b54-027f-59aa-bd93-ec7caa53fbd0"


def test_t5_ap06_lower_upper_noncivil_via_project_amount():
    for eok in (AP06_LOWER, AP06_UPPER_NONCIVIL):
        step1, fac = _cap(_cst_body({
            "project_amount": eok,
            "worker_count": 50,
            "is_construction": True,
            "is_relationship_contractor": False,
            "is_civil_construction": False,
        }))
        _assert_verbatim_eok(fac, eok)
        assert fac["is_construction"] is True
        assert fac["is_relationship_contractor"] is False
        assert fac["is_civil_construction"] is False


def test_t5_relationship_lower_threshold_via_project_amount():
    step1, fac = _cap(_cst_body({
        "project_amount": RELATIONSHIP_LOWER,
        "worker_count": 50,
        "is_construction": True,
        "is_relationship_contractor": True,
        "is_civil_construction": False,
    }))
    _assert_verbatim_eok(fac, RELATIONSHIP_LOWER)
    assert fac["is_relationship_contractor"] is True
    assert fac["is_civil_construction"] is False


def test_t5_civil_ap06_ap07_boundary_via_project_amount():
    for eok in (149.0, CIVIL_AP06_UPPER):
        step1, fac = _cap(_cst_body({
            "project_amount": eok,
            "worker_count": 50,
            "is_construction": True,
            "is_relationship_contractor": False,
            "is_civil_construction": True,
        }))
        _assert_verbatim_eok(fac, eok)
        assert fac["is_civil_construction"] is True
        assert fac["is_relationship_contractor"] is False


def test_t5_ap07_ap08_800_boundary_via_project_amount():
    for eok in (799.0, AP08_LOWER):
        step1, fac = _cap(_cst_body({
            "project_amount": eok,
            "worker_count": 50,
            "is_construction": True,
            "is_relationship_contractor": False,
            "is_civil_construction": False,
        }))
        _assert_verbatim_eok(fac, eok)
        assert fac["is_construction"] is True
        assert fac["is_civil_construction"] is False
