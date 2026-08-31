# WO-FE-CST-EQUIPMENT-CAPTURE-WIRING-001 (+CORRECTION-01): equipment_assets → 5 legal fact.
# CONSTRUCTION PAID + owned factory only; INDUSTRIAL/BUILDING/FREE firewall; tenant ownership; fail-closed.
import pytest
from fastapi import HTTPException
from schemas.diagnosis_integrated import DiagnosisRunBody
from clients.leg_runtime_client import build_facility
from services import diagnosis_integrated_svc as _svc

EQ = {"010": "has_emergency_gen", "014": "has_boiler", "023": "has_press",
      "024": "has_conveyor", "038": "has_pressure_vessel"}
USER = {"id": "u1", "company_id": "c1", "role_code": "MEMBER"}


class _R:
    def __init__(self, d): self.data = d
class _T:
    def __init__(self, n, eq, own=True, eqfail=False):
        self._n = n; self._eq = eq; self._own = own; self._eqfail = eqfail
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def update(self, *a, **k): return self
    def insert(self, row): self._p = row; return self
    def execute(self):
        if self._n == "diagnosis_auth_log": return _R([{"id": "a1", "ci_hash": "ci", "name": "n", "phone": "p", "free_count": 0, "free_limit": 3, "status": "ACTIVE", "linked_user_id": "u1"}])
        if self._n == "diagnosis_disclaimer_log": return _R([{"id": "disc1", "ci_hash": "ci", "agreed": True}])
        if self._n == "anonymous_diagnosis_results": return _R([{**(getattr(self, "_p", None) or {}), "id": "r1"}])
        if self._n == "diagnosis_purchases": return _R([{"id": "p1"}])
        if self._n == "factories":
            # _ensure_factory_own: factory→company_id. own=True 면 c1(=user company)
            return _R([{"id": "f1", "company_id": "c1" if self._own else "cX"}])
        if self._n == "equipment_assets":
            if self._eqfail: raise RuntimeError("db down")
            return _R([{"equipment_type_code": c} for c in self._eq])
        return _R([])
class _S:
    def __init__(self, eq, own=True, eqfail=False): self._eq = eq; self._own = own; self._eqfail = eqfail
    def table(self, n): return _T(n, self._eq, self._own, self._eqfail)


def _run(sector, codes, factory="f1", paid=True, own=True, eqfail=False):
    cap = {}
    def r1(sb, s1): cap["s1"] = s1; return {"status": "success", "data": {"applicable_count": 0, "rules_table": []}}
    kw = dict(auth_token="t", sector=sector, disclaimer_log_id="disc1")
    if factory: kw["factory_id"] = factory
    if paid: kw["payment_ref"] = "oid1"
    b = DiagnosisRunBody(**kw)
    _svc.run_diagnosis(_S(codes, own, eqfail), b, run_step1_func=r1,
        auto_tier_func=lambda *a, **k: ("CONSTRUCTION_X" if paid else "CONSTRUCTION_FREE"),
        build_partial_func=lambda f: {}, now_func=lambda: "2026-01-01T00:00:00Z",
        paid_tier_prices={"CONSTRUCTION_X": 100}, free_tier_codes={"CONSTRUCTION_FREE", "BUILDING_FREE", "INDUSTRY_FREE"},
        engine_version="t", current_user=(USER if paid else None))
    return cap["s1"]

def _fac(sector, codes, **kw): return build_facility(_run(sector, codes, **kw))


# ── CONSTRUCTION PAID owned: 5/5 ──
def test_equipment_materializer_construction_paid():
    fac = _fac("CONSTRUCTION", ["010", "014", "023", "024", "038"])
    assert all(fac.get(f) is True for f in EQ.values()), {f: fac.get(f) for f in EQ.values()}

def test_equipment_contract_010(): assert _fac("CONSTRUCTION", ["010"]).get("has_emergency_gen") is True
def test_equipment_contract_014(): assert _fac("CONSTRUCTION", ["014"]).get("has_boiler") is True
def test_equipment_contract_023(): assert _fac("CONSTRUCTION", ["023"]).get("has_press") is True
def test_equipment_contract_024(): assert _fac("CONSTRUCTION", ["024"]).get("has_conveyor") is True
def test_equipment_contract_038(): assert _fac("CONSTRUCTION", ["038"]).get("has_pressure_vessel") is True

# ── sector firewall ──
def test_equipment_materializer_industrial_firewall():
    fac = _fac("INDUSTRIAL", ["010", "014", "023", "024", "038"])
    assert all(fac.get(f) is None for f in EQ.values())

def test_equipment_materializer_building_firewall():
    fac = _fac("BUILDING", ["010", "014", "023", "024", "038"])
    assert all(fac.get(f) is None for f in EQ.values())

def test_equipment_materializer_construction_free_firewall():
    # free(payment_ref 없음) → materializer skip
    fac = _fac("CONSTRUCTION", ["010", "014", "023", "024", "038"], paid=False)
    assert all(fac.get(f) is None for f in EQ.values())

# ── tenant ownership ──
def test_equipment_materializer_foreign_factory_rejected():
    with pytest.raises(HTTPException):
        _run("CONSTRUCTION", ["010"], own=False)

# ── fail-closed ──
def test_equipment_materializer_db_failure_is_not_silent():
    with pytest.raises(HTTPException) as ei:
        _run("CONSTRUCTION", ["010"], eqfail=True)
    assert ei.value.status_code == 503

# ── absence / unknown / no-factory ──
def test_absence_does_not_generate_false():
    fac = _fac("CONSTRUCTION", [])
    for f in EQ.values(): assert fac.get(f) is None

def test_unknown_equipment_code_does_not_generate_fact():
    fac = _fac("CONSTRUCTION", ["999", "021"])
    for f in EQ.values(): assert fac.get(f) is None

def test_no_factory_no_equipment_fact():
    fac = _fac("CONSTRUCTION", ["010"], factory=None)
    assert fac.get("has_emergency_gen") is None
