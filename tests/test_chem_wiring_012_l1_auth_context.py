"""CHEM-WO-LEG-INPUT-L1-AUTH-CONTEXT-012 — L1 인증 company_id collect_* 연결 검증

Goal: G-mvcuqz1f-8ef927

커버리지:
  LA-01~06  collect_industrial_leg_input company_id → load_chemical_facts 연결
  LA-07~09  CONSTRUCTION site→factory bridge 후 company_id 전달
  LA-10~12  BUILDING collect company_id + allow_h01_db_write=False DB Write 0
  LA-13~14  run_safe_* company_id 스레드
  SD-02     run_safe_* 함수에 load_chemical_facts 직접 호출 없음(collect_* 경유만)

원칙:
  - C4(run_leg_diagnosis) 호출 0
  - DB Write 0
  - fail-closed: ChemicalSourceLoadError 재발생(False 생성 금지)
  - company_id=None → CHEM 미호출(backward-compat)
"""
from __future__ import annotations

import inspect
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch, call

import pytest

from schemas.legal_engine import (
    SafeIndustrialConsumerInput,
    SafeConstructionConsumerInput,
    SafeBuildingConsumerInput,
)


# ─────────────────────────────────────────────────────────────────────────────
# 공통 픽스처 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _fake_industrial_assembler(supabase, factory_id):
    from services.safe_industrial_canonical_assembler import TARGET_FIELDS, CONTRACT_VERSION
    values = {f: None for f in TARGET_FIELDS}
    values["ksic_major"] = "C10"
    values["worker_count"] = 10
    return {
        "contract_version": CONTRACT_VERSION,
        "sector": "INDUSTRIAL",
        "factory_id": factory_id,
        "values": {f: values[f] for f in TARGET_FIELDS},
        "unresolved_fields": [f for f in TARGET_FIELDS if values[f] is None],
        "provenance": {},
    }


def _fake_construction_assembler(supabase, site_id):
    from services.safe_construction_canonical_assembler import TARGET_FIELDS, CONTRACT_VERSION
    values = {f: None for f in TARGET_FIELDS}
    values["worker_count"] = 5
    return {
        "contract_version": CONTRACT_VERSION,
        "sector": "CONSTRUCTION",
        "factory_id": "F-CST",
        "values": {f: values[f] for f in TARGET_FIELDS},
        "unresolved_fields": [f for f in TARGET_FIELDS if values[f] is None],
        "provenance": {},
    }


def _stub_sources(monkeypatch):
    monkeypatch.setattr("services.work_source.store.load_work_rows_optional", lambda sb, fid: [])
    monkeypatch.setattr("services.material_source.store.load_factory_material_rows_optional", lambda sb, fid: [])
    monkeypatch.setattr("services.equipment_source.store.load_equipment_rows_optional", lambda sb, fid: [])


def _stub_cst_sources(monkeypatch):
    _stub_sources(monkeypatch)
    monkeypatch.setattr(
        "services.safe_construction_leg_runtime._load_site_process_work_type_codes",
        lambda sb, sid: [],
    )
    monkeypatch.setattr(
        "services.safe_construction_leg_runtime._load_site_work_type_codes",
        lambda sb, sid: [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# LA-01~06 — INDUSTRIAL collect_industrial_leg_input
# ─────────────────────────────────────────────────────────────────────────────

class TestIndustrialCollectChemContext:

    def test_LA01_company_id_given_load_chemical_facts_called(self, monkeypatch):
        """LA-01: company_id 제공 → load_chemical_facts(factory_id, company_id) 호출."""
        import services.safe_industrial_leg_runtime as R
        monkeypatch.setattr(R, "assemble_industrial_marketing_contract", _fake_industrial_assembler)
        _stub_sources(monkeypatch)

        calls = []
        def fake_load(fid, cid, **kw):
            calls.append((fid, cid))
            return {"has_chemical": True}

        monkeypatch.setattr("clients.chem_internal_client.load_chemical_facts", fake_load)

        step1, _ = R.collect_industrial_leg_input(
            object(), "F1", SafeIndustrialConsumerInput(), company_id="C1"
        )

        assert calls == [("F1", "C1")], f"load_chemical_facts not called correctly: {calls}"

    def test_LA02_company_id_none_no_chem_call(self, monkeypatch):
        """LA-02: company_id=None → load_chemical_facts 미호출(backward-compat)."""
        import services.safe_industrial_leg_runtime as R
        monkeypatch.setattr(R, "assemble_industrial_marketing_contract", _fake_industrial_assembler)
        _stub_sources(monkeypatch)

        calls = []
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda *a, **k: calls.append(a) or {},
        )

        R.collect_industrial_leg_input(object(), "F1", SafeIndustrialConsumerInput(), company_id=None)
        assert calls == [], "load_chemical_facts must not be called when company_id=None"

    def test_LA03_company_id_empty_string_no_chem_call(self, monkeypatch):
        """LA-03: company_id='' → load_chemical_facts 미호출."""
        import services.safe_industrial_leg_runtime as R
        monkeypatch.setattr(R, "assemble_industrial_marketing_contract", _fake_industrial_assembler)
        _stub_sources(monkeypatch)

        calls = []
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda *a, **k: calls.append(a) or {},
        )

        R.collect_industrial_leg_input(object(), "F1", SafeIndustrialConsumerInput(), company_id="")
        assert calls == [], "load_chemical_facts must not be called when company_id=''"

    def test_LA04_chemical_source_load_error_reraises(self, monkeypatch):
        """LA-04: ChemicalSourceLoadError → fail-closed 재발생(False 생성 금지)."""
        import services.safe_industrial_leg_runtime as R
        from clients.chem_internal_client import ChemicalSourceLoadError
        monkeypatch.setattr(R, "assemble_industrial_marketing_contract", _fake_industrial_assembler)
        _stub_sources(monkeypatch)
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda fid, cid, **kw: (_ for _ in ()).throw(ChemicalSourceLoadError("timeout: timed out")),
        )

        with pytest.raises(ChemicalSourceLoadError, match="timeout"):
            R.collect_industrial_leg_input(
                object(), "F1", SafeIndustrialConsumerInput(), company_id="C1"
            )

    def test_LA05_chem_fact_reaches_step1_input(self, monkeypatch):
        """LA-05: CHEM has_chemical=True → step1.input['has_chemical']=True."""
        import services.safe_industrial_leg_runtime as R
        monkeypatch.setattr(R, "assemble_industrial_marketing_contract", _fake_industrial_assembler)
        _stub_sources(monkeypatch)
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda fid, cid, **kw: {"has_chemical": True},
        )

        step1, _ = R.collect_industrial_leg_input(
            object(), "F1", SafeIndustrialConsumerInput(), company_id="C1"
        )
        assert step1.input.get("has_chemical") is True, (
            f"has_chemical must reach step1.input; got {step1.input.get('has_chemical')!r}"
        )

    def test_LA06_source_facts_explicit_wins_over_chem(self, monkeypatch):
        """LA-06: source_facts 명시 False > CHEM True (충돌 정책 유지).
        app3_projection 경로로 has_chemical=False 를 source_facts 에 주입한다.
        SafeIndustrialConsumerInput 은 has_chemical 필드를 허용하지 않으므로(extra_forbidden).
        """
        import services.safe_industrial_leg_runtime as R
        monkeypatch.setattr(R, "assemble_industrial_marketing_contract", _fake_industrial_assembler)
        _stub_sources(monkeypatch)
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda fid, cid, **kw: {"has_chemical": True},
        )

        step1, _ = R.collect_industrial_leg_input(
            object(), "F1",
            SafeIndustrialConsumerInput(),
            app3_projection={"has_chemical": False},  # source_facts 에 False 명시
            company_id="C1",
        )
        assert step1.input.get("has_chemical") is False, (
            f"Explicit False in source_facts must win over CHEM True; got {step1.input.get('has_chemical')!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# LA-07~09 — CONSTRUCTION site→factory bridge + company_id 전달
# ─────────────────────────────────────────────────────────────────────────────

class TestConstructionCollectChemContext:

    def test_LA07_construction_company_id_passed_to_chem(self, monkeypatch):
        """LA-07: CONSTRUCTION collect — company_id 가 load_chemical_facts 에 전달됨."""
        import services.safe_construction_leg_runtime as R
        monkeypatch.setattr(R, "assemble_construction_marketing_contract", _fake_construction_assembler)
        _stub_cst_sources(monkeypatch)

        calls = []
        def fake_load(fid, cid, **kw):
            calls.append((fid, cid))
            return {"has_chemical": True}

        monkeypatch.setattr("clients.chem_internal_client.load_chemical_facts", fake_load)

        step1, _, factory_id = R.collect_construction_leg_input(
            object(), "S1", SafeConstructionConsumerInput(), company_id="C-CST"
        )

        assert calls == [("F-CST", "C-CST")], (
            f"CONSTRUCTION: load_chemical_facts must use bridge factory_id; got {calls}"
        )
        assert factory_id == "F-CST"

    def test_LA08_construction_site_bridge_factory_id_used_for_chem(self, monkeypatch):
        """LA-08: CONSTRUCTION bridge 가 해소한 factory_id 로 CHEM 호출 — 요청 body factory 아님."""
        import services.safe_construction_leg_runtime as R

        def fake_assembler(supabase, site_id):
            from services.safe_construction_canonical_assembler import TARGET_FIELDS, CONTRACT_VERSION
            values = {f: None for f in TARGET_FIELDS}
            return {
                "contract_version": CONTRACT_VERSION,
                "sector": "CONSTRUCTION",
                "factory_id": "BRIDGE-FAC",  # bridge-resolved, not from caller
                "values": {f: values[f] for f in TARGET_FIELDS},
                "unresolved_fields": list(TARGET_FIELDS),
                "provenance": {},
            }

        monkeypatch.setattr(R, "assemble_construction_marketing_contract", fake_assembler)
        _stub_cst_sources(monkeypatch)

        captured = {}
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda fid, cid, **kw: captured.update({"fid": fid, "cid": cid}) or {"has_chemical": False},
        )

        R.collect_construction_leg_input(object(), "SITE-X", {}, company_id="CO-X")
        assert captured.get("fid") == "BRIDGE-FAC", "must use bridge factory_id, not any caller-supplied id"
        assert captured.get("cid") == "CO-X"

    def test_LA09_construction_company_id_none_no_chem(self, monkeypatch):
        """LA-09: CONSTRUCTION company_id=None → CHEM 미호출."""
        import services.safe_construction_leg_runtime as R
        monkeypatch.setattr(R, "assemble_construction_marketing_contract", _fake_construction_assembler)
        _stub_cst_sources(monkeypatch)

        calls = []
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda *a, **k: calls.append(a) or {},
        )

        R.collect_construction_leg_input(object(), "S1", SafeConstructionConsumerInput(), company_id=None)
        assert calls == [], "CONSTRUCTION: load_chemical_facts must not be called when company_id=None"


# ─────────────────────────────────────────────────────────────────────────────
# LA-10~12 — BUILDING collect company_id + allow_h01_db_write=False
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildingCollectChemContext:

    def _make_sb(self, fac_data: dict = None):
        """Factory DB stub."""
        sb = MagicMock()
        row = fac_data or {}
        (
            sb.table.return_value
            .select.return_value
            .eq.return_value
            .limit.return_value
            .execute.return_value
            .data
        ) = [row]
        return sb

    def test_LA10_building_company_id_load_chemical_facts_called(self, monkeypatch):
        """LA-10: BUILDING collect + company_id → load_chemical_facts(factory_id, company_id)."""
        from services.safe_building_leg_runtime import collect_building_leg_input
        _stub_sources(monkeypatch)

        calls = []
        def fake_load(fid, cid, **kw):
            calls.append((fid, cid))
            return {"has_chemical": True}

        monkeypatch.setattr("clients.chem_internal_client.load_chemical_facts", fake_load)

        collect_building_leg_input(
            self._make_sb(), "F-BLD", SafeBuildingConsumerInput(),
            allow_h01_db_write=False, company_id="C-BLD",
        )
        assert calls == [("F-BLD", "C-BLD")], f"BUILDING: load_chemical_facts not called: {calls}"

    def test_LA11_building_chem_fact_reaches_step1(self, monkeypatch):
        """LA-11: BUILDING CHEM has_chemical=True → step1.input에 전달."""
        from services.safe_building_leg_runtime import collect_building_leg_input
        _stub_sources(monkeypatch)
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda fid, cid, **kw: {"has_chemical": True},
        )

        step1, _, _ = collect_building_leg_input(
            self._make_sb(), "F-BLD", SafeBuildingConsumerInput(),
            allow_h01_db_write=False, company_id="C-BLD",
        )
        assert step1.input.get("has_chemical") is True

    def test_LA12_building_company_id_none_no_chem(self, monkeypatch):
        """LA-12: BUILDING company_id=None → CHEM 미호출(backward-compat)."""
        from services.safe_building_leg_runtime import collect_building_leg_input
        _stub_sources(monkeypatch)

        calls = []
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda *a, **k: calls.append(a) or {},
        )

        collect_building_leg_input(
            self._make_sb(), "F-BLD", SafeBuildingConsumerInput(),
            allow_h01_db_write=False, company_id=None,
        )
        assert calls == [], "BUILDING: no CHEM call when company_id=None"


# ─────────────────────────────────────────────────────────────────────────────
# LA-13~14 — run_safe_* company_id 스레드
# ─────────────────────────────────────────────────────────────────────────────

class TestRunSafeCompanyIdThread:

    def test_LA13_run_safe_industrial_threads_company_id(self, monkeypatch):
        """LA-13: run_safe_industrial_leg company_id → collect_industrial_leg_input 에 전달."""
        import services.safe_industrial_leg_runtime as R
        monkeypatch.setattr(R, "assemble_industrial_marketing_contract", _fake_industrial_assembler)
        _stub_sources(monkeypatch)

        calls = []
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda fid, cid, **kw: calls.append((fid, cid)) or {"has_chemical": True},
        )

        _leg_step1 = {}
        def fake_run_leg(step1):
            _leg_step1["s"] = step1
            return {"sector": "INDUSTRIAL", "engine_family": "LEG", "key_obligations": [], "facility_used": {}}
        monkeypatch.setattr(R, "run_leg_diagnosis", fake_run_leg)

        R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput(), company_id="C1")
        assert calls == [("F1", "C1")], f"run_safe_industrial_leg must thread company_id: {calls}"

    def test_LA14_run_safe_construction_threads_company_id(self, monkeypatch):
        """LA-14: run_safe_construction_leg company_id → collect_construction_leg_input 에 전달."""
        import services.safe_construction_leg_runtime as R
        monkeypatch.setattr(R, "assemble_construction_marketing_contract", _fake_construction_assembler)
        _stub_cst_sources(monkeypatch)

        calls = []
        monkeypatch.setattr(
            "clients.chem_internal_client.load_chemical_facts",
            lambda fid, cid, **kw: calls.append((fid, cid)) or {"has_chemical": True},
        )

        def fake_run_leg(step1):
            return {"sector": "CONSTRUCTION", "engine_family": "LEG", "key_obligations": [], "facility_used": {}}
        monkeypatch.setattr(R, "run_leg_diagnosis", fake_run_leg)

        R.run_safe_construction_leg(object(), "S1", SafeConstructionConsumerInput(), company_id="C-CST")
        assert calls == [("F-CST", "C-CST")], f"run_safe_construction_leg must thread company_id: {calls}"


# ─────────────────────────────────────────────────────────────────────────────
# SD-02 — run_safe_* 직접 load_chemical_facts 호출 없음 (collect_* 경유만)
# ─────────────────────────────────────────────────────────────────────────────

def test_SD02_run_safe_functions_do_not_directly_call_load_chemical_facts():
    """SD-02 (Static): run_safe_* 함수 본체에 load_chemical_facts 직접 호출 없음.
    CHEM 호출은 collect_*_leg_input() 경유만 허용된다."""
    import services.safe_industrial_leg_runtime as IND
    import services.safe_construction_leg_runtime as CST
    import services.safe_building_leg_runtime as BLD

    for func, name in [
        (IND.run_safe_industrial_leg, "run_safe_industrial_leg"),
        (CST.run_safe_construction_leg, "run_safe_construction_leg"),
        (BLD.run_safe_building_leg, "run_safe_building_leg"),
    ]:
        src = inspect.getsource(func)
        assert "load_chemical_facts" not in src, (
            f"{name} must NOT call load_chemical_facts directly — only via collect_*"
        )


# ─────────────────────────────────────────────────────────────────────────────
# C4=0 / DB Write=0 확인
# ─────────────────────────────────────────────────────────────────────────────

def test_LA15_c4_call_zero_industrial(monkeypatch):
    """LA-15: collect_industrial_leg_input + CHEM 연결 → run_leg_diagnosis 0회."""
    import services.safe_industrial_leg_runtime as R
    monkeypatch.setattr(R, "assemble_industrial_marketing_contract", _fake_industrial_assembler)
    monkeypatch.setattr("services.work_source.store.load_work_rows_optional", lambda sb, fid: [])
    monkeypatch.setattr("services.material_source.store.load_factory_material_rows_optional", lambda sb, fid: [])
    monkeypatch.setattr("services.equipment_source.store.load_equipment_rows_optional", lambda sb, fid: [])
    monkeypatch.setattr(
        "clients.chem_internal_client.load_chemical_facts",
        lambda fid, cid, **kw: {"has_chemical": True},
    )

    leg_calls = {"n": 0}
    monkeypatch.setattr(R, "run_leg_diagnosis", lambda s: leg_calls.update({"n": leg_calls["n"] + 1}))

    R.collect_industrial_leg_input(object(), "F1", SafeIndustrialConsumerInput(), company_id="C1")
    assert leg_calls["n"] == 0, "collect_* must not call run_leg_diagnosis (C4 호출 0)"
