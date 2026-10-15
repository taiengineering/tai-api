"""
H02-RT: runtime integration tests.
Verifies that run_safe_building_leg correctly threads occupancy_assessment_id
through to the canonical adapter, and that SourceUnresolved propagates.
No real DB required — supabase and adapter are mocked.
"""

import pytest
from unittest.mock import MagicMock, patch

from services.occupancy_capacity.canonical_adapter import SourceUnresolved


def _make_supabase_stub(factory_row: dict | None = None):
    sub = MagicMock()
    fac_exec = MagicMock()
    fac_exec.data = [factory_row] if factory_row else []
    chain = MagicMock()
    chain.execute.return_value = fac_exec
    sub.table.return_value.select.return_value.eq.return_value.limit.return_value = chain
    return sub


_MINIMAL_FACTORY = {
    "id": "fac-test",
    "building_register_updated_at": "2026-01-01T00:00:00Z",
    "building_height": 50.0,
    "floor_count": 5,
    "bdmgtsn": None,
    "mgm_bldrgst_pk": None,
}


class TestH02RuntimeBinding:
    def test_no_assessment_id_does_not_inject_occupancy(self):
        sub = _make_supabase_stub(_MINIMAL_FACTORY)
        consumer = MagicMock()
        consumer.model_dump.return_value = {}

        with patch("services.safe_building_leg_runtime.build_saas_leg_step1", return_value={}) as mock_step1, \
             patch("services.safe_building_leg_runtime.run_leg_diagnosis", return_value={}), \
             patch("services.work_source.store.load_work_rows_optional", return_value=[]), \
             patch("services.material_source.store.load_factory_material_rows_optional", return_value=[]), \
             patch("services.equipment_source.store.load_equipment_rows_optional", return_value=[]):

            from services.safe_building_leg_runtime import run_safe_building_leg
            run_safe_building_leg(sub, "fac-test", consumer, occupancy_assessment_id=None)

            call_kwargs = mock_step1.call_args.kwargs
            source_facts = call_kwargs.get("source_facts", {})
            assert "occupancy_capacity" not in source_facts

    def test_valid_assessment_id_injects_occupancy_capacity(self):
        sub = _make_supabase_stub(_MINIMAL_FACTORY)
        consumer = MagicMock()
        consumer.model_dump.return_value = {}

        from services.occupancy_capacity.legal_registry import RULESET_VERSION, get_ruleset_sha256
        confirmed_row = {
            "id": "asmnt-001",
            "factory_id": "fac-test",
            "status": "CONFIRMED",
            "ruleset_version": RULESET_VERSION,
            "ruleset_sha256": get_ruleset_sha256(),
            "result_numerator": "6000",
            "result_denominator": "1",
            "coverage_attested": True,
        }

        with patch("services.safe_building_leg_runtime.build_saas_leg_step1", return_value={}) as mock_step1, \
             patch("services.safe_building_leg_runtime.run_leg_diagnosis", return_value={}), \
             patch("services.work_source.store.load_work_rows_optional", return_value=[]), \
             patch("services.material_source.store.load_factory_material_rows_optional", return_value=[]), \
             patch("services.equipment_source.store.load_equipment_rows_optional", return_value=[]), \
             patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=confirmed_row):
            from services.safe_building_leg_runtime import run_safe_building_leg
            run_safe_building_leg(sub, "fac-test", consumer, occupancy_assessment_id="asmnt-001")

            call_kwargs = mock_step1.call_args.kwargs
            source_facts = call_kwargs.get("source_facts", {})
            assert source_facts.get("occupancy_capacity") == 6000

    def test_source_unresolved_propagates(self):
        sub = _make_supabase_stub(_MINIMAL_FACTORY)
        consumer = MagicMock()
        consumer.model_dump.return_value = {}

        with patch("services.safe_building_leg_runtime.build_saas_leg_step1", return_value={}), \
             patch("services.safe_building_leg_runtime.run_leg_diagnosis", return_value={}), \
             patch("services.work_source.store.load_work_rows_optional", return_value=[]), \
             patch("services.material_source.store.load_factory_material_rows_optional", return_value=[]), \
             patch("services.equipment_source.store.load_equipment_rows_optional", return_value=[]), \
             patch("services.occupancy_capacity.canonical_adapter.get_assessment", return_value=None):
            from services.safe_building_leg_runtime import run_safe_building_leg
            with pytest.raises(SourceUnresolved):
                run_safe_building_leg(sub, "fac-test", consumer, occupancy_assessment_id="bad-id")


class TestH02FirewallPreservation:
    """Verify P0 firewall still holds in P1 context."""

    def test_consumer_direct_occupancy_still_blocked(self):
        from schemas.legal_engine import SafeBuildingConsumerInput
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SafeBuildingConsumerInput(occupancy_capacity=5000)

    def test_leg_input_fields_contains_occupancy(self):
        from clients.leg_runtime_client import _LEG_INPUT_FIELDS
        assert "occupancy_capacity" in _LEG_INPUT_FIELDS

    def test_building_n1_fields_contains_occupancy(self):
        from clients.leg_runtime_client import _BUILDING_N1_FIELDS
        assert "occupancy_capacity" in _BUILDING_N1_FIELDS

    def test_factory_select_no_occupant_capacity(self):
        from services.safe_building_leg_runtime import _FACTORY_SELECT
        assert "occupant_capacity" not in _FACTORY_SELECT

    def test_leg_body_has_occupancy_assessment_id_field(self):
        from schemas.legal_engine import SafeBuildingLegBody
        fields = SafeBuildingLegBody.model_fields
        assert "occupancy_assessment_id" in fields
        assert fields["occupancy_assessment_id"].default is None


class TestH02VoidLifecycleFirewall:
    """DRAFT→VOID must be forbidden; only CONFIRMED→VOID allowed."""

    def test_draft_cannot_be_voided(self):
        from services.occupancy_capacity.store import void_assessment
        sub = MagicMock()
        draft_row = {
            "id": "asmnt-1",
            "factory_id": "fac-1",
            "status": "DRAFT",
            "result_numerator": None,
        }
        with patch("services.occupancy_capacity.store.get_assessment", return_value=draft_row):
            with pytest.raises(ValueError, match="CONFIRMED"):
                void_assessment(sub, "asmnt-1")

    def test_confirmed_can_be_voided(self):
        from services.occupancy_capacity.store import void_assessment
        sub = MagicMock()
        confirmed_row = {
            "id": "asmnt-1",
            "factory_id": "fac-1",
            "status": "CONFIRMED",
            "result_numerator": "5000",
        }
        update_resp = MagicMock()
        update_resp.data = [{"id": "asmnt-1", "status": "VOID"}]
        (sub.table.return_value.update.return_value
         .eq.return_value.eq.return_value.execute.return_value) = update_resp

        with patch("services.occupancy_capacity.store.get_assessment", return_value=confirmed_row):
            result = void_assessment(sub, "asmnt-1")
        assert result["status"] == "VOID"


class TestH02AssessmentSourceContract:
    """PATCH C: wrong factory / DRAFT / VOID status → SourceUnresolved."""

    def test_wrong_factory_raises_source_unresolved(self):
        from services.occupancy_capacity.canonical_adapter import load_confirmed_assessment_context
        from services.occupancy_capacity.legal_registry import RULESET_VERSION, get_ruleset_sha256
        wrong_factory_row = {
            "id": "asmnt-wf",
            "factory_id": "other-factory",
            "status": "CONFIRMED",
            "ruleset_version": RULESET_VERSION,
            "ruleset_sha256": get_ruleset_sha256(),
            "result_numerator": "6000",
            "result_denominator": "1",
        }
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment",
                   return_value=wrong_factory_row):
            with pytest.raises(SourceUnresolved, match="factory"):
                load_confirmed_assessment_context(MagicMock(), "asmnt-wf", "fac-test")

    def test_draft_assessment_raises_source_unresolved(self):
        from services.occupancy_capacity.canonical_adapter import load_confirmed_assessment_context
        draft_row = {
            "id": "asmnt-draft",
            "factory_id": "fac-test",
            "status": "DRAFT",
            "ruleset_version": "any",
            "ruleset_sha256": "any",
            "result_numerator": None,
            "result_denominator": None,
        }
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment",
                   return_value=draft_row):
            with pytest.raises(SourceUnresolved, match="DRAFT"):
                load_confirmed_assessment_context(MagicMock(), "asmnt-draft", "fac-test")

    def test_void_assessment_raises_source_unresolved(self):
        from services.occupancy_capacity.canonical_adapter import load_confirmed_assessment_context
        void_row = {
            "id": "asmnt-void",
            "factory_id": "fac-test",
            "status": "VOID",
            "ruleset_version": "any",
            "ruleset_sha256": "any",
            "result_numerator": None,
            "result_denominator": None,
        }
        with patch("services.occupancy_capacity.canonical_adapter.get_assessment",
                   return_value=void_row):
            with pytest.raises(SourceUnresolved, match="VOID"):
                load_confirmed_assessment_context(MagicMock(), "asmnt-void", "fac-test")
