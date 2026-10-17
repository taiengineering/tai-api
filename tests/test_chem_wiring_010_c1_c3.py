"""CHEM-WO-LEG-INPUT-TAI-C1C3-WIRING-010 — C1→C3 연결 검증

Goal: G-mvcs98l9-8ef927

커버리지:
  CC-01~07  clients.chem_internal_client.load_chemical_facts (M2M 클라이언트)
  CW-01~09  services.canonical.saas_leg_source_adapter.build_saas_leg_step1 chemical_facts 파라미터
  C3-01~03  clients.leg_runtime_client.build_facility C2/C3 전달 검증

원칙:
  - C4(evaluate_rtm/evaluate) 호출 0
  - DB Write 0
  - run_diagnosis() 코드 미수정 검증 포함
  - BUILDING has_chemical_substance 명시값 경계 유지
  - CONSTRUCTION has_chemical → has_chemical_substance alias 유지
  - False/0 보존 (truthy filter 금지)
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# CC — CHEM M2M 클라이언트 테스트
# ─────────────────────────────────────────────────────────────────────────────

class TestChemInternalClient:

    def _make_resp(self, status_code: int, json_body: dict) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_body
        resp.text = str(json_body)
        return resp

    def test_CC01_success_has_chemical_true(self, monkeypatch):
        """CC-01: 200 응답 has_chemical=True → {"has_chemical": True} 반환."""
        monkeypatch.setenv("CHEM_INTERNAL_BASE_URL", "http://chem-internal")
        monkeypatch.setenv("CHEM_INTERNAL_API_SECRET", "test-secret")
        from clients.chem_internal_client import load_chemical_facts
        resp = self._make_resp(200, {"factory_id": "f1", "facts": {"has_chemical": True}, "contract_gaps": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp) as mock_get:
            result = load_chemical_facts("f1", "c1")
        assert result == {"has_chemical": True}
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs["params"]["company_id"] == "c1"
        assert call_kwargs.kwargs["headers"]["X-Internal-Secret"] == "test-secret"

    def test_CC02_has_chemical_false_preserved(self, monkeypatch):
        """CC-02: has_chemical=False 는 보존 — truthy filter 금지."""
        monkeypatch.setenv("CHEM_INTERNAL_BASE_URL", "http://chem-internal")
        monkeypatch.setenv("CHEM_INTERNAL_API_SECRET", "test-secret")
        from clients.chem_internal_client import load_chemical_facts
        resp = self._make_resp(200, {"factory_id": "f1", "facts": {"has_chemical": False}, "contract_gaps": []})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_chemical_facts("f1", "c1")
        assert result == {"has_chemical": False}, f"False must be preserved; got {result!r}"

    def test_CC03_timeout_raises(self, monkeypatch):
        """CC-03: httpx.TimeoutException → ChemicalSourceLoadError."""
        monkeypatch.setenv("CHEM_INTERNAL_BASE_URL", "http://chem-internal")
        monkeypatch.setenv("CHEM_INTERNAL_API_SECRET", "test-secret")
        from clients.chem_internal_client import load_chemical_facts, ChemicalSourceLoadError
        import httpx
        with patch("clients.chem_internal_client.httpx.get", side_effect=httpx.TimeoutException("timed out")):
            with pytest.raises(ChemicalSourceLoadError, match="timeout"):
                load_chemical_facts("f1", "c1")

    def test_CC04_http_403_raises(self, monkeypatch):
        """CC-04: HTTP 403 → ChemicalSourceLoadError (fail-closed)."""
        monkeypatch.setenv("CHEM_INTERNAL_BASE_URL", "http://chem-internal")
        monkeypatch.setenv("CHEM_INTERNAL_API_SECRET", "wrong-secret")
        from clients.chem_internal_client import load_chemical_facts, ChemicalSourceLoadError
        resp = self._make_resp(403, {"detail": "INVALID_INTERNAL_SECRET"})
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            with pytest.raises(ChemicalSourceLoadError, match="HTTP 403"):
                load_chemical_facts("f1", "c1")

    def test_CC05_contract_gaps_stripped(self, monkeypatch):
        """CC-05: contract_gaps 는 결과에서 제거 — LEG 사실 아님."""
        monkeypatch.setenv("CHEM_INTERNAL_BASE_URL", "http://chem-internal")
        monkeypatch.setenv("CHEM_INTERNAL_API_SECRET", "test-secret")
        from clients.chem_internal_client import load_chemical_facts
        resp = self._make_resp(200, {
            "factory_id": "f1",
            "facts": {"has_chemical": True},
            "contract_gaps": ["L4_CONVERT_BLOCKED", "L4_AGGREGATE_BLOCKED"],
        })
        with patch("clients.chem_internal_client.httpx.get", return_value=resp):
            result = load_chemical_facts("f1", "c1")
        assert "contract_gaps" not in result
        assert list(result.keys()) == ["has_chemical"]

    def test_CC06_missing_base_url_raises(self, monkeypatch):
        """CC-06: CHEM_INTERNAL_BASE_URL 미설정 → ChemicalSourceLoadError."""
        monkeypatch.delenv("CHEM_INTERNAL_BASE_URL", raising=False)
        monkeypatch.setenv("CHEM_INTERNAL_API_SECRET", "test-secret")
        from clients.chem_internal_client import load_chemical_facts, ChemicalSourceLoadError
        with pytest.raises(ChemicalSourceLoadError, match="CHEM_INTERNAL_BASE_URL"):
            load_chemical_facts("f1", "c1")

    def test_CC07_missing_secret_raises(self, monkeypatch):
        """CC-07: CHEM_INTERNAL_API_SECRET 미설정 → ChemicalSourceLoadError."""
        monkeypatch.setenv("CHEM_INTERNAL_BASE_URL", "http://chem-internal")
        monkeypatch.delenv("CHEM_INTERNAL_API_SECRET", raising=False)
        from clients.chem_internal_client import load_chemical_facts, ChemicalSourceLoadError
        with pytest.raises(ChemicalSourceLoadError, match="CHEM_INTERNAL_API_SECRET"):
            load_chemical_facts("f1", "c1")


# ─────────────────────────────────────────────────────────────────────────────
# CW — build_saas_leg_step1 chemical_facts 파라미터 계약
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildSaasLegStep1Chemical:

    def test_CW01_industrial_chemical_true_passes_through(self):
        """CW-01: INDUSTRIAL + chemical_facts has_chemical=True → step1.input["has_chemical"]=True."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        step1 = build_saas_leg_step1(
            sector="INDUSTRIAL",
            source_facts={"worker_count": 5},
            chemical_facts={"has_chemical": True},
        )
        assert step1.input.get("has_chemical") is True

    def test_CW02_source_facts_explicit_wins_over_chemical(self):
        """CW-02: source_facts 명시값(False)이 chemical_facts(True)보다 우선."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        step1 = build_saas_leg_step1(
            sector="INDUSTRIAL",
            source_facts={"has_chemical": False},
            chemical_facts={"has_chemical": True},
        )
        assert step1.input.get("has_chemical") is False, (
            f"Explicit False in source_facts must win; got {step1.input.get('has_chemical')!r}"
        )

    def test_CW03_building_has_chemical_not_promoted_to_substance(self):
        """CW-03: BUILDING + chemical_facts has_chemical=True → step1.input["has_chemical"]=True (alias 승격 없음).
        BUILDING has_chemical_substance 경로는 영향받지 않는다."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        step1 = build_saas_leg_step1(
            sector="BUILDING",
            source_facts={"worker_count": 5},
            chemical_facts={"has_chemical": True},
        )
        # has_chemical 은 LEG input 으로 전달됨 (103 vocabulary 포함)
        assert step1.input.get("has_chemical") is True
        # BUILDING alias 스킵: has_chemical 이 has_chemical_substance 로 승격되지 않음
        assert step1.input.get("has_chemical_substance") is None, (
            "has_chemical must NOT be promoted to has_chemical_substance for BUILDING"
        )

    def test_CW04_building_explicit_substance_preserved(self):
        """CW-04: BUILDING 명시 has_chemical_substance → chemical_facts가 건드리지 않음."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        step1 = build_saas_leg_step1(
            sector="BUILDING",
            source_facts={"has_chemical_substance": True},
            chemical_facts={"has_chemical": False},
        )
        assert step1.input.get("has_chemical_substance") is True
        # CHEM has_chemical=False 는 별도 슬롯; has_chemical_substance 를 오염시키지 않음
        assert step1.input.get("has_chemical") is False

    def test_CW05_construction_has_chemical_reaches_step1_input(self):
        """CW-05: CONSTRUCTION + chemical_facts has_chemical=True → step1.input["has_chemical"]=True.
        build_facility(C3)가 이를 has_chemical_substance 로 rename(alias 정책 유지)."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        step1 = build_saas_leg_step1(
            sector="CONSTRUCTION",
            source_facts={"worker_count": 3},
            chemical_facts={"has_chemical": True},
        )
        assert step1.input.get("has_chemical") is True

    def test_CW06_has_chemical_false_from_chem_preserved(self):
        """CW-06: chemical_facts has_chemical=False 는 보존 (truthy filter 금지)."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        step1 = build_saas_leg_step1(
            sector="INDUSTRIAL",
            source_facts={},
            chemical_facts={"has_chemical": False},
        )
        assert step1.input.get("has_chemical") is False, (
            f"False must be preserved; got {step1.input.get('has_chemical')!r}"
        )

    def test_CW07_contract_gaps_not_in_step1_input(self):
        """CW-07: contract_gaps 가 chemical_facts 에 포함돼도 step1.input 에는 없어야 함."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        step1 = build_saas_leg_step1(
            sector="INDUSTRIAL",
            source_facts={},
            chemical_facts={"has_chemical": True, "contract_gaps": ["L4_CONVERT_BLOCKED"]},
        )
        assert "contract_gaps" not in (step1.input or {}), (
            "contract_gaps must not be passed through to LEG input"
        )
        assert step1.input.get("has_chemical") is True

    def test_CW08_chemical_facts_none_backward_compatible(self):
        """CW-08: chemical_facts=None (기본값) → 기존 동작과 동일."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        step1 = build_saas_leg_step1(
            sector="INDUSTRIAL",
            source_facts={"worker_count": 10},
            chemical_facts=None,
        )
        assert step1.input.get("worker_count") == 10
        assert "has_chemical" not in (step1.input or {})

    def test_CW09_chemical_facts_empty_no_change(self):
        """CW-09: chemical_facts={} → 변화 없음."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        step1 = build_saas_leg_step1(
            sector="INDUSTRIAL",
            source_facts={"worker_count": 7},
            chemical_facts={},
        )
        assert step1.input.get("worker_count") == 7
        assert "has_chemical" not in (step1.input or {})


# ─────────────────────────────────────────────────────────────────────────────
# C3 — build_facility C2/C3 전달 검증
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildFacilityChemical:

    def test_C3_01_industrial_has_chemical_in_facility(self):
        """C3-01: INDUSTRIAL has_chemical=True → build_facility facility["has_chemical"]=True."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        from clients.leg_runtime_client import build_facility
        step1 = build_saas_leg_step1(
            sector="INDUSTRIAL",
            source_facts={},
            chemical_facts={"has_chemical": True},
        )
        facility = build_facility(step1)
        assert facility.get("has_chemical") is True, (
            f"INDUSTRIAL: has_chemical must reach facility; got {facility.get('has_chemical')!r}"
        )

    def test_C3_02_construction_has_chemical_renamed_to_substance(self):
        """C3-02: CONSTRUCTION has_chemical=True → build_facility has_chemical_substance=True (alias 정책)."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        from clients.leg_runtime_client import build_facility
        step1 = build_saas_leg_step1(
            sector="CONSTRUCTION",
            source_facts={},
            chemical_facts={"has_chemical": True},
        )
        facility = build_facility(step1)
        assert facility.get("has_chemical_substance") is True, (
            f"CONSTRUCTION: has_chemical must be renamed to has_chemical_substance; "
            f"facility keys: {list(facility.keys())}"
        )
        assert "has_chemical" not in facility, (
            "CONSTRUCTION: original has_chemical key must be removed after rename"
        )

    def test_C3_03_building_explicit_substance_in_facility(self):
        """C3-03: BUILDING has_chemical_substance=True (명시) → build_facility 에 전달."""
        from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
        from clients.leg_runtime_client import build_facility
        step1 = build_saas_leg_step1(
            sector="BUILDING",
            source_facts={"has_chemical_substance": True},
        )
        facility = build_facility(step1)
        assert facility.get("has_chemical_substance") is True, (
            f"BUILDING: explicit has_chemical_substance must reach facility; "
            f"got {facility.get('has_chemical_substance')!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# SD — run_diagnosis() 미수정 확인 (Static)
# ─────────────────────────────────────────────────────────────────────────────

def test_SD01_run_diagnosis_not_modified():
    """SD-01 (Static): run_diagnosis() 에 load_chemical_facts 호출이 없음 — 운영 진단 불변."""
    import inspect
    import services.diagnosis_integrated_svc as svc_mod
    src = inspect.getsource(svc_mod.run_diagnosis)
    assert "load_chemical_facts" not in src, (
        "run_diagnosis() must not call load_chemical_facts — operational path must remain unchanged"
    )
    assert "chem_internal" not in src, (
        "run_diagnosis() must not reference chem_internal_client"
    )
