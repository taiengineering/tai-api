"""WO-OBS009-MATERIAL-CANONICAL-RUNTIME-WIRING-PATCH-001.

Proves the Chemical canonical adapter is wired into the production SAFE→LEG
path across all three sectors.

Layers under test:
  T1–T5   common SaaS adapter passthrough (build_saas_leg_step1)
  T6–T8   _LEG_INPUT_FIELDS allowlist lock
  T9–T11  three sector runtimes (Industrial / Construction / Building)
  T12     fail-closed integration (material read failure → LEG call = 0)
  T13     unrelated fields not added to allowlist
  T14     conflict policy — explicit false + projected true
"""
from __future__ import annotations

import pytest

from clients.leg_runtime_client import _LEG_INPUT_FIELDS
from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.material_source.canonical_adapter import (
    MaterialCanonicalMergeConflict,
)
from services.material_source.store import MaterialSourceLoadError


MANAGED_CANON = "is_managed_hazardous_substance"
PERMIT_CANON = "is_permit_required_hazardous_substance"
SPECIAL_CANON = "is_special_management_substance"

# Real classification-carrying keys from Material Source authority catalog.
BENZENE_KEY = "ISHL-RULE-APP12-G1-I046"     # MANAGED + SPECIAL
VINYL_KEY = "ISHL-ENF-ART88-0088001-P-H7"   # PERMIT
STODDARD_KEY = "ISHL-RULE-APP12-G1-I060"    # MANAGED only


def _mat_row(**kwargs):
    base = {
        "material_name": "x",
        "material_category_code": None,
        "handling_mode_codes": None,
        "material_master_key": None,
        "is_active": True,
    }
    base.update(kwargs)
    return base


# ─────────────────────────────────────────────────────────────────────────
# T1–T5  common SaaS adapter passthrough
# ─────────────────────────────────────────────────────────────────────────

def test_T1_material_MANAGED_reaches_step1_input():
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        material_rows=[_mat_row(material_master_key=STODDARD_KEY)],
    )
    assert step1.input.get(MANAGED_CANON) is True
    assert PERMIT_CANON not in step1.input
    assert SPECIAL_CANON not in step1.input


def test_T2_material_PERMIT_reaches_step1_input():
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        material_rows=[_mat_row(material_master_key=VINYL_KEY)],
    )
    assert step1.input.get(PERMIT_CANON) is True
    assert MANAGED_CANON not in step1.input
    assert SPECIAL_CANON not in step1.input


def test_T3_material_SPECIAL_reaches_step1_input():
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        material_rows=[_mat_row(material_master_key=BENZENE_KEY)],
    )
    # BENZENE carries {MANAGED, SPECIAL} per legal catalog.
    assert step1.input.get(SPECIAL_CANON) is True
    assert step1.input.get(MANAGED_CANON) is True
    assert PERMIT_CANON not in step1.input


def test_T4_no_material_all_three_absent():
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        material_rows=[],
    )
    assert MANAGED_CANON not in step1.input
    assert PERMIT_CANON not in step1.input
    assert SPECIAL_CANON not in step1.input


def test_T4_material_rows_None_all_three_absent():
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        material_rows=None,
    )
    assert MANAGED_CANON not in step1.input
    assert PERMIT_CANON not in step1.input
    assert SPECIAL_CANON not in step1.input


def test_T4_free_text_only_all_three_absent():
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        material_rows=[_mat_row(material_name="unknown-solvent", material_master_key=None)],
    )
    assert MANAGED_CANON not in step1.input
    assert PERMIT_CANON not in step1.input
    assert SPECIAL_CANON not in step1.input


def test_T5_explicit_false_plus_projected_true_conflicts():
    """Explicit input MUST win; the merge must raise so LEG is never called
    with a silently-overwritten fact."""
    with pytest.raises(MaterialCanonicalMergeConflict) as exc_info:
        build_saas_leg_step1(
            sector="INDUSTRIAL",
            source_facts={MANAGED_CANON: False},
            material_rows=[_mat_row(material_master_key=STODDARD_KEY)],
        )
    conflict = exc_info.value.conflicts[0]
    assert conflict["field"] == MANAGED_CANON
    assert conflict["explicit"] is False
    assert conflict["projected"] is True


# ─────────────────────────────────────────────────────────────────────────
# T6–T8  _LEG_INPUT_FIELDS allowlist lock
# ─────────────────────────────────────────────────────────────────────────

def test_T6_is_managed_hazardous_substance_in_allowlist():
    assert MANAGED_CANON in _LEG_INPUT_FIELDS


def test_T7_is_permit_required_hazardous_substance_in_allowlist():
    assert PERMIT_CANON in _LEG_INPUT_FIELDS


def test_T8_is_special_management_substance_in_allowlist():
    assert SPECIAL_CANON in _LEG_INPUT_FIELDS


def test_T13_unrelated_new_fields_not_added():
    """Only the 3 canonical booleans were added by this WO. Guard against drift."""
    added_by_this_wo = {MANAGED_CANON, PERMIT_CANON, SPECIAL_CANON}
    # Fields with an is_ prefix that could confuse with the 3.
    forbidden = {
        "is_hazardous_substance",
        "is_managed",
        "is_permit_required",
        "is_special_management",
        "has_managed_hazardous_substance",
        "has_permit_required_hazardous_substance",
        "has_special_management_substance",
        "material_classifications",
        "material_master_key",
    }
    for f in forbidden:
        assert f not in _LEG_INPUT_FIELDS, (
            f"{f} must NOT be added — only {added_by_this_wo} are approved"
        )


# ─────────────────────────────────────────────────────────────────────────
# T9–T11  three sector production runtimes
# ─────────────────────────────────────────────────────────────────────────

def _stub_material_rows(monkeypatch, rows):
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional",
        lambda supabase, factory_id: list(rows),
    )


def _stub_work_rows_empty(monkeypatch):
    monkeypatch.setattr(
        "services.work_source.store.load_work_rows_optional",
        lambda supabase, factory_id: [],
    )


def test_T9_industrial_runtime_receives_chemical_canonical(monkeypatch):
    import services.safe_industrial_leg_runtime as R
    from services.safe_industrial_canonical_assembler import (
        TARGET_FIELDS, CONTRACT_VERSION,
    )
    from schemas.legal_engine import SafeIndustrialConsumerInput

    captured = {}

    def fake_assemble(supabase, factory_id):
        values = {f: None for f in TARGET_FIELDS}
        values["worker_count"] = 10
        return {
            "contract_version": CONTRACT_VERSION,
            "sector": "INDUSTRIAL",
            "factory_id": factory_id,
            "values": {f: values[f] for f in TARGET_FIELDS},
            "unresolved_fields": [],
            "provenance": {},
        }

    def fake_run_leg(step1):
        captured["step1"] = step1
        return {"engine_family": "LEG", "sector": step1.sector}

    monkeypatch.setattr(R, "assemble_industrial_marketing_contract", fake_assemble)
    monkeypatch.setattr(R, "run_leg_diagnosis", fake_run_leg)
    _stub_work_rows_empty(monkeypatch)
    _stub_material_rows(monkeypatch, [_mat_row(material_master_key=BENZENE_KEY)])

    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    inp = captured["step1"].input
    assert inp.get(MANAGED_CANON) is True
    assert inp.get(SPECIAL_CANON) is True
    assert PERMIT_CANON not in inp


def test_T10_construction_runtime_receives_chemical_canonical(monkeypatch):
    import services.safe_construction_leg_runtime as R
    from services.safe_construction_canonical_assembler import (
        TARGET_FIELDS, CONTRACT_VERSION,
    )
    from schemas.legal_engine import SafeConstructionConsumerInput

    captured = {}

    def fake_assemble(supabase, site_id):
        values = {f: None for f in TARGET_FIELDS}
        return {
            "contract_version": CONTRACT_VERSION,
            "sector": "CONSTRUCTION",
            "factory_id": "F1",
            "values": {f: values[f] for f in TARGET_FIELDS},
            "unresolved_fields": [],
            "provenance": {},
        }

    def fake_run_leg(step1):
        captured["step1"] = step1
        return {"engine_family": "LEG", "sector": step1.sector}

    monkeypatch.setattr(R, "assemble_construction_marketing_contract", fake_assemble)
    monkeypatch.setattr(R, "run_leg_diagnosis", fake_run_leg)
    _stub_work_rows_empty(monkeypatch)
    _stub_material_rows(monkeypatch, [_mat_row(material_master_key=VINYL_KEY)])

    R.run_safe_construction_leg(object(), "S1", SafeConstructionConsumerInput())
    inp = captured["step1"].input
    assert inp.get(PERMIT_CANON) is True
    assert MANAGED_CANON not in inp
    assert SPECIAL_CANON not in inp


def test_T11_building_runtime_receives_chemical_canonical(monkeypatch):
    import services.safe_building_leg_runtime as R
    from schemas.legal_engine import SafeBuildingConsumerInput

    class _Res:
        def __init__(self, d): self.data = d
    class _Q:
        def __init__(self, rows): self._rows = rows
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def order(self, *a, **k): return self
        def execute(self): return _Res(self._rows)
    class _FakeSB:
        def __init__(self, fac): self._fac = fac
        def table(self, n):
            return _Q([self._fac] if (n == "factories" and self._fac) else [])

    captured = {}

    def fake_run_leg(step1):
        captured["step1"] = step1
        return {"engine_family": "LEG"}

    monkeypatch.setattr(R, "run_leg_diagnosis", fake_run_leg)
    _stub_work_rows_empty(monkeypatch)
    _stub_material_rows(monkeypatch, [_mat_row(material_master_key=STODDARD_KEY)])

    R.run_safe_building_leg(_FakeSB({"floor_count": 5}), "F1", SafeBuildingConsumerInput())
    inp = captured["step1"].input
    assert inp.get(MANAGED_CANON) is True
    assert PERMIT_CANON not in inp
    assert SPECIAL_CANON not in inp
    # BUILDING has_chemical_substance patch-A path is separate and unaffected.


def test_T11b_building_has_chemical_substance_patchA_still_works(monkeypatch):
    """Regression — the 3 new canonical booleans MUST NOT collapse with
    the existing BUILDING has_chemical_substance exact-key patch-A path."""
    import services.safe_building_leg_runtime as R
    from schemas.legal_engine import SafeBuildingConsumerInput

    class _Res:
        def __init__(self, d): self.data = d
    class _Q:
        def __init__(self, rows): self._rows = rows
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def order(self, *a, **k): return self
        def execute(self): return _Res(self._rows)
    class _FakeSB:
        def __init__(self, fac): self._fac = fac
        def table(self, n):
            return _Q([self._fac] if (n == "factories" and self._fac) else [])

    captured = {}
    monkeypatch.setattr(R, "run_leg_diagnosis",
                        lambda step1: captured.setdefault("step1", step1) or {})
    _stub_work_rows_empty(monkeypatch)
    _stub_material_rows(monkeypatch, [_mat_row(material_master_key=BENZENE_KEY)])

    ci = SafeBuildingConsumerInput(has_chemical_substance=True)
    R.run_safe_building_leg(_FakeSB({"floor_count": 5}), "F1", ci)
    inp = captured["step1"].input
    # Legacy narrow field still present via patch-A.
    assert inp.get("has_chemical_substance") is True
    # New canonical booleans coexist as separate keys — no collapse.
    assert inp.get(MANAGED_CANON) is True
    assert inp.get(SPECIAL_CANON) is True


# ─────────────────────────────────────────────────────────────────────────
# T12  fail-closed integration
# ─────────────────────────────────────────────────────────────────────────

def test_T12_material_read_failure_never_calls_LEG_industrial(monkeypatch):
    import services.safe_industrial_leg_runtime as R
    from services.safe_industrial_canonical_assembler import (
        TARGET_FIELDS, CONTRACT_VERSION,
    )
    from schemas.legal_engine import SafeIndustrialConsumerInput

    leg_calls = {"n": 0}

    def fake_assemble(supabase, factory_id):
        return {
            "contract_version": CONTRACT_VERSION,
            "sector": "INDUSTRIAL",
            "factory_id": factory_id,
            "values": {f: None for f in TARGET_FIELDS},
            "unresolved_fields": [],
            "provenance": {},
        }

    def fake_run_leg(step1):
        leg_calls["n"] += 1
        return {}

    def boom(supabase, factory_id):
        raise MaterialSourceLoadError(
            "factory_materials query failed", factory_id=factory_id
        )

    monkeypatch.setattr(R, "assemble_industrial_marketing_contract", fake_assemble)
    monkeypatch.setattr(R, "run_leg_diagnosis", fake_run_leg)
    _stub_work_rows_empty(monkeypatch)
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional",
        boom,
    )

    with pytest.raises(MaterialSourceLoadError):
        R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    assert leg_calls["n"] == 0, "LEG must NOT be called when Material Source read fails"


def test_T12_material_read_failure_never_calls_LEG_construction(monkeypatch):
    import services.safe_construction_leg_runtime as R
    from services.safe_construction_canonical_assembler import (
        TARGET_FIELDS, CONTRACT_VERSION,
    )
    from schemas.legal_engine import SafeConstructionConsumerInput

    leg_calls = {"n": 0}

    def fake_assemble(supabase, site_id):
        return {
            "contract_version": CONTRACT_VERSION,
            "sector": "CONSTRUCTION",
            "factory_id": "F1",
            "values": {f: None for f in TARGET_FIELDS},
            "unresolved_fields": [],
            "provenance": {},
        }

    def fake_run_leg(step1):
        leg_calls["n"] += 1
        return {}

    def boom(supabase, factory_id):
        raise MaterialSourceLoadError(
            "factory_materials query failed", factory_id=factory_id
        )

    monkeypatch.setattr(R, "assemble_construction_marketing_contract", fake_assemble)
    monkeypatch.setattr(R, "run_leg_diagnosis", fake_run_leg)
    _stub_work_rows_empty(monkeypatch)
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional",
        boom,
    )

    with pytest.raises(MaterialSourceLoadError):
        R.run_safe_construction_leg(object(), "S1", SafeConstructionConsumerInput())
    assert leg_calls["n"] == 0, "LEG must NOT be called when Material Source read fails"


def test_T12_material_read_failure_never_calls_LEG_building(monkeypatch):
    import services.safe_building_leg_runtime as R
    from schemas.legal_engine import SafeBuildingConsumerInput

    class _Res:
        def __init__(self, d): self.data = d
    class _Q:
        def __init__(self, rows): self._rows = rows
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def order(self, *a, **k): return self
        def execute(self): return _Res(self._rows)
    class _FakeSB:
        def __init__(self, fac): self._fac = fac
        def table(self, n):
            return _Q([self._fac] if (n == "factories" and self._fac) else [])

    leg_calls = {"n": 0}
    monkeypatch.setattr(R, "run_leg_diagnosis",
                        lambda s: leg_calls.__setitem__("n", leg_calls["n"] + 1) or {})
    _stub_work_rows_empty(monkeypatch)

    def boom(supabase, factory_id):
        raise MaterialSourceLoadError(
            "factory_materials query failed", factory_id=factory_id
        )

    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional",
        boom,
    )

    with pytest.raises(MaterialSourceLoadError):
        R.run_safe_building_leg(_FakeSB({"floor_count": 5}), "F1",
                                SafeBuildingConsumerInput())
    assert leg_calls["n"] == 0, "LEG must NOT be called when Material Source read fails"
