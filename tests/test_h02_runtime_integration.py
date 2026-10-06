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
    # factories table read
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


_HEAVY_PATCHES = [
    "services.safe_building_leg_runtime.build_saas_leg_step1",
    "services.safe_building_leg_runtime.run_leg_diagnosis",
    # lazy-imported inside function body — patch at source module
    "services.work_source.store.load_work_rows_optional",
    "services.material_source.store.load_factory_material_rows_optional",
    "services.equipment_source.store.load_equipment_rows_optional",
]


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
        import inspect
        fields = SafeBuildingLegBody.model_fields
        assert "occupancy_assessment_id" in fields
        # must be optional (default None)
        assert fields["occupancy_assessment_id"].default is None
