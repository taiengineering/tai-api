"""Tests for EXISTS input path (CURSOR-TASK-002)."""

from constants.exists_mvp_fields import (
    FIELD_CODE_SYNONYMS,
    MVP_FIELD_CODES_BY_SECTOR,
)
from services.exists_input_service import (
    build_factory_column_patch,
    normalize_exists_payload,
    normalize_field_code,
)
from services.input_contract_builder import build_input_contract


def test_normalize_field_code_synonyms_only():
    assert normalize_field_code("has_gas") == "has_high_pressure_gas"
    assert normalize_field_code("has_hazardous") == "has_hazardous_material"
    assert normalize_field_code("has_welding") == "has_welding"


def test_normalize_exists_payload_preserves_field_codes():
    raw = {
        "has_welding": True,
        "has_crane": True,
        "has_gas": True,
        "worker_count": 280,
    }
    out = normalize_exists_payload(raw)
    assert out == {
        "has_welding": True,
        "has_crane": True,
        "has_high_pressure_gas": True,
    }
    assert "worker_count" not in out


def test_build_input_contract_merges_exists_inputs():
    factory_row = {
        "id": "f1",
        "sector": "INDUSTRIAL",
        "ksic_code": "C28",
        "total_worker_count_calc": 280,
        "has_chemical_substance": True,
        "is_hazardous_material": False,
    }
    exists_inputs = {
        "has_welding": True,
        "has_crane": True,
        "has_chemical_substance": True,
        "has_confined_space": False,
    }
    contract = build_input_contract(factory_row, exists_inputs)
    assert contract["factory_id"] == "f1"
    assert contract["sector"] == "INDUSTRIAL"
    assert contract["worker_count"] == 280
    assert contract["has_welding"] is True
    assert contract["has_crane"] is True
    assert contract["has_chemical_substance"] is True
    assert contract.get("has_confined_space") is False


def test_factory_column_patch_maps_without_renaming_field_code():
    factory_row = {
        "is_hazardous_material": False,
        "has_chemical_substance": None,
    }
    patch = build_factory_column_patch(
        {
            "has_welding": True,
            "has_crane": True,
            "has_hazardous_material": True,
            "has_chemical_substance": True,
        },
        factory_row,
    )
    assert "has_welding_work" not in patch
    assert "has_crane" not in patch
    assert patch["is_hazardous_material"] is True
    assert patch["has_chemical_substance"] is True


def test_mvp_sector_sets_count():
    assert len(MVP_FIELD_CODES_BY_SECTOR["INDUSTRIAL"]) == 7
    assert len(MVP_FIELD_CODES_BY_SECTOR["CONSTRUCTION"]) == 7
    assert len(MVP_FIELD_CODES_BY_SECTOR["BUILDING"]) == 3
    assert len(FIELD_CODE_SYNONYMS) == 2


def test_integration_save_and_contract_live():
    import os
    if not os.getenv("SUPABASE_URL"):
        return
    from supabase import create_client
    from services.exists_input_service import save_exists_inputs
    from services.input_contract_builder import (
        build_input_contract_for_factory,
        contract_has_stats,
    )

    url = os.environ["SUPABASE_URL"]
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not key:
        return

    sb = create_client(url, key)
    factory_id = "e9c56af6-5de7-487d-bd2e-0d452291a562"

    save_exists_inputs(
        factory_id,
        {
            "has_welding": True,
            "has_crane": True,
            "has_chemical_substance": True,
        },
        sb,
    )
    contract = build_input_contract_for_factory(factory_id, sb)
    stats = contract_has_stats(contract)
    assert stats["has_true_count"] >= 3
    assert contract["has_welding"] is True
    assert contract["has_crane"] is True
    assert contract["has_chemical_substance"] is True

    fp = (
        sb.table("facility_profiles")
        .select("profile_snapshot")
        .eq("factory_id", factory_id)
        .order("profile_version", desc=True)
        .limit(1)
        .execute()
    )
    snap = fp.data[0]["profile_snapshot"]
    assert "exists_inputs" in snap
    assert snap["exists_inputs"]["has_welding"] is True
